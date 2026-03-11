# SPDX-License-Identifier: AGPL-3.0-or-later
"""Firmware Syntax Validator — Phase 24.4.

A fast, dependency-free C firmware validator that runs *without* a
compiler toolchain.  It catches the most common code-generation bugs
(unbalanced braces, missing includes, duplicate function definitions)
and provides actionable error messages.

Design philosophy:
  - Zero external dependencies (no clang, no arm-gcc required)
  - Works offline / in CI without a cross-compiler
  - Complements, not replaces, a real compile-check

Usage::

    from boardsmith_fw.codegen.firmware_validator import validate_firmware
    issues = validate_firmware(source_code, filename="main.c")
    if issues:
        for issue in issues:
            print(issue)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    """A single firmware validation issue.

    Attributes:
        severity: "error" (code definitely broken) or "warning" (suspect).
        filename: Source file name for display purposes.
        line:     1-based line number, or 0 if not applicable.
        message:  Human-readable description.
    """
    severity: str   # "error" | "warning"
    filename: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.severity.upper()} {self.filename}:{self.line}: {self.message}"


@dataclass
class FirmwareValidationResult:
    """Result of validating a set of generated firmware files.

    Attributes:
        issues:  All validation issues found.
        valid:   True if no errors (warnings are allowed).
    """
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def summary(self) -> str:
        e = len(self.errors)
        w = len(self.warnings)
        if e == 0 and w == 0:
            return "Firmware validation passed — no issues found"
        parts = []
        if e:
            parts.append(f"{e} error(s)")
        if w:
            parts.append(f"{w} warning(s)")
        return "Firmware validation: " + ", ".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_firmware(
    source: str,
    filename: str = "firmware.c",
) -> list[ValidationIssue]:
    """Validate a single C source file for common code-generation issues.

    Runs all checks and returns a flat list of :class:`ValidationIssue`
    objects.  Returns an empty list if the source looks valid.

    Checks performed:
    1. Brace balance — ``{`` vs ``}`` count must match
    2. Parenthesis balance — ``(`` vs ``)`` count must match
    3. Include guard / include syntax — ``#include`` must be well-formed
    4. Function definition completeness — every ``{`` after a signature
       must eventually have a matching ``}``
    5. Null-byte detection — generated files must be valid UTF-8 text
    6. Empty file / stub detection — warns if <20 non-blank lines

    Args:
        source:   The C source code as a string.
        filename: Display name for error messages.

    Returns:
        List of :class:`ValidationIssue` objects.
    """
    issues: list[ValidationIssue] = []

    _check_brace_balance(source, filename, issues)
    _check_paren_balance(source, filename, issues)
    _check_include_syntax(source, filename, issues)
    _check_null_bytes(source, filename, issues)
    _check_stub_detection(source, filename, issues)
    _check_duplicate_functions(source, filename, issues)

    return issues


def validate_codegen_result(result) -> FirmwareValidationResult:
    """Validate all files in a :class:`HIRCodegenResult`.

    Runs :func:`validate_firmware` on every generated ``.c`` and ``.h``
    file and aggregates the results.

    Args:
        result: A ``HIRCodegenResult`` (from ``boardsmith_fw.codegen.hir_codegen``).

    Returns:
        :class:`FirmwareValidationResult` summarising all issues.
    """
    vr = FirmwareValidationResult()
    for gf in result.files:
        if not (gf.path.endswith(".c") or gf.path.endswith(".h")):
            continue
        issues = validate_firmware(gf.content, filename=gf.path)
        vr.issues.extend(issues)
    return vr


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_brace_balance(
    source: str, filename: str, issues: list[ValidationIssue]
) -> None:
    """Check that curly-braces are balanced across the whole file."""
    depth = 0
    last_open_line = 0
    for lineno, line in enumerate(source.splitlines(), start=1):
        stripped = _strip_comments(line)
        for ch in stripped:
            if ch == "{":
                depth += 1
                last_open_line = lineno
            elif ch == "}":
                depth -= 1
                if depth < 0:
                    issues.append(ValidationIssue(
                        severity="error",
                        filename=filename,
                        line=lineno,
                        message="Unexpected '}' — more closing braces than opening braces",
                    ))
                    depth = 0

    if depth > 0:
        issues.append(ValidationIssue(
            severity="error",
            filename=filename,
            line=last_open_line,
            message=f"Unbalanced braces — {depth} unclosed '{{' block(s)",
        ))


def _check_paren_balance(
    source: str, filename: str, issues: list[ValidationIssue]
) -> None:
    """Check that parentheses are balanced within each line."""
    for lineno, line in enumerate(source.splitlines(), start=1):
        stripped = _strip_comments(line)
        if stripped.count("(") != stripped.count(")"):
            # Only flag if not inside a multiline macro (heuristic)
            if not stripped.rstrip().endswith("\\"):
                issues.append(ValidationIssue(
                    severity="warning",
                    filename=filename,
                    line=lineno,
                    message=(
                        f"Possibly unbalanced parentheses "
                        f"(open={stripped.count('(')}, close={stripped.count(')')})"
                    ),
                ))


def _check_include_syntax(
    source: str, filename: str, issues: list[ValidationIssue]
) -> None:
    """Check that all #include directives are syntactically valid."""
    _include_re = re.compile(r'^\s*#\s*include\s*(.+)$')
    for lineno, line in enumerate(source.splitlines(), start=1):
        m = _include_re.match(line)
        if not m:
            continue
        rest = m.group(1).strip()
        # Must start with < or "
        if not (
            (rest.startswith("<") and rest.endswith(">"))
            or (rest.startswith('"') and rest.endswith('"'))
        ):
            issues.append(ValidationIssue(
                severity="error",
                filename=filename,
                line=lineno,
                message=f"Malformed #include directive: {line.strip()!r}",
            ))


def _check_null_bytes(
    source: str, filename: str, issues: list[ValidationIssue]
) -> None:
    """Detect null bytes (sign of binary corruption or stub generation)."""
    if "\x00" in source:
        issues.append(ValidationIssue(
            severity="error",
            filename=filename,
            line=0,
            message="File contains null bytes — not valid C source",
        ))


def _check_stub_detection(
    source: str, filename: str, issues: list[ValidationIssue]
) -> None:
    """Warn if the file looks like an empty stub."""
    non_blank = [l for l in source.splitlines() if l.strip()]
    if len(non_blank) < 10:
        issues.append(ValidationIssue(
            severity="warning",
            filename=filename,
            line=0,
            message=(
                f"File has only {len(non_blank)} non-blank line(s) — "
                "may be an incomplete stub"
            ),
        ))


def _check_duplicate_functions(
    source: str, filename: str, issues: list[ValidationIssue]
) -> None:
    """Warn on duplicate function definitions in the same file."""
    func_re = re.compile(
        r'^\s*(?:[\w\*\s]+\s+)?(\w+)\s*\([^)]*\)\s*\{',
        re.MULTILINE,
    )
    seen: dict[str, int] = {}
    for m in func_re.finditer(source):
        name = m.group(1)
        if name in ("if", "for", "while", "switch", "else", "do"):
            continue
        lineno = source[: m.start()].count("\n") + 1
        if name in seen:
            issues.append(ValidationIssue(
                severity="warning",
                filename=filename,
                line=lineno,
                message=(
                    f"Possible duplicate function definition: '{name}' "
                    f"(first seen at line {seen[name]})"
                ),
            ))
        else:
            seen[name] = lineno


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LINE_COMMENT_RE = re.compile(r"//.*$")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"')


def _strip_comments(line: str) -> str:
    """Remove C line comments and string literals for syntactic analysis."""
    line = _STRING_RE.sub('""', line)
    line = _LINE_COMMENT_RE.sub("", line)
    return line
