# SPDX-License-Identifier: AGPL-3.0-or-later
"""Firmware Review Agent — Static firmware quality check.

Reviews generated firmware without compilation:
  - Counts TODO/FIXME placeholders in source files
  - Checks required file presence (main source + build file)
  - Reports a quality score: 1.0 = no issues, -0.05 per TODO

Gracefully handles missing or empty firmware directories.

Usage::

    from agents.firmware_review_agent import FirmwareReviewAgent
    agent = FirmwareReviewAgent()
    result = agent.review(Path("output/firmware"))
    print(result.score, result.todo_count, result.issues)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Source file extensions to scan for TODOs
# ---------------------------------------------------------------------------

_SOURCE_EXTENSIONS = {
    ".c", ".cpp", ".cc", ".cxx",
    ".h", ".hpp",
    ".py",
    ".rs",
    ".go",
    ".ino",
    ".S", ".s",
}

# Patterns for TODO / FIXME / placeholder comments
_TODO_PATTERN = re.compile(
    r"//\s*TODO\b|/\*\s*TODO\b|#\s*TODO\b"
    r"|//\s*FIXME\b|/\*\s*FIXME\b|#\s*FIXME\b"
    r"|//\s*STUB\b|#\s*STUB\b"
    r"|//\s*PLACEHOLDER\b|#\s*PLACEHOLDER\b",
    re.IGNORECASE,
)

# Files that must be present for a "compilable" firmware package
_REQUIRED_SIGNATURES = [
    # At least one of these name patterns must match a file
    re.compile(r"main\.(c|cpp|ino|rs|py)$", re.IGNORECASE),
    re.compile(r"(CMakeLists\.txt|platformio\.ini|Makefile|Cargo\.toml|setup\.py)$"),
]

# Score penalty per TODO (capped so score never goes below 0.0)
_PENALTY_PER_TODO = 0.05

# Maximum number of TODO lines to report individually
_MAX_REPORTED_TODOS = 10


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FirmwareTodo:
    """A single TODO/FIXME/STUB placeholder in the firmware source."""

    file_path: str        # Relative path within firmware_dir
    line_number: int
    text: str             # The comment text (truncated to 80 chars)


@dataclass
class FirmwareReviewResult:
    """Result of a firmware static review.

    Attributes:
        score:         Quality score 0.0–1.0 (1.0 = no issues).
        todo_count:    Total number of TODO/FIXME/STUB placeholders found.
        file_count:    Number of source files scanned.
        has_entry_point: True if a main source file was found.
        has_build_file:  True if a CMakeLists.txt / platformio.ini etc. was found.
        compilable:    True if no TODOs and all required files present.
        issues:        Human-readable list of problems.
        todos:         First N individual TODO instances (for display).
    """

    score: float
    todo_count: int
    file_count: int
    has_entry_point: bool = False
    has_build_file: bool = False
    compilable: bool = False
    issues: list[str] = field(default_factory=list)
    todos: list[FirmwareTodo] = field(default_factory=list)

    def summary(self) -> str:
        """Return a one-line summary string."""
        status = "OK" if self.compilable else "ISSUES"
        return (
            f"Firmware [{status}] "
            f"score={self.score:.2f} "
            f"todos={self.todo_count} "
            f"files={self.file_count}"
        )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class FirmwareReviewAgent:
    """Static firmware quality reviewer.

    Does NOT invoke a compiler — purely static analysis of generated code.

    Usage::

        agent = FirmwareReviewAgent()
        result = agent.review(Path("output/firmware"))
    """

    def review(self, firmware_dir: Optional[Path]) -> FirmwareReviewResult:
        """Review firmware source files in firmware_dir.

        Args:
            firmware_dir: Path to directory containing generated firmware.
                          May be None or non-existent (returns fallback).

        Returns:
            FirmwareReviewResult with score, todo count, and issue list.
        """
        if firmware_dir is None or not Path(firmware_dir).exists():
            return FirmwareReviewResult(
                score=0.0,
                todo_count=0,
                file_count=0,
                has_entry_point=False,
                has_build_file=False,
                compilable=False,
                issues=["Firmware directory does not exist — firmware was not generated"],
            )

        firmware_dir = Path(firmware_dir)

        # Collect all source files recursively
        source_files = [
            f for f in firmware_dir.rglob("*")
            if f.is_file() and f.suffix in _SOURCE_EXTENSIONS
        ]
        # Also collect build files
        all_files = list(firmware_dir.rglob("*"))

        file_count = len(source_files)
        issues: list[str] = []
        todos: list[FirmwareTodo] = []
        total_todo_count = 0

        # ------------------------------------------------------------------
        # Scan for TODOs
        # ------------------------------------------------------------------
        for src_file in source_files:
            try:
                lines = src_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                for lineno, line in enumerate(lines, start=1):
                    if _TODO_PATTERN.search(line):
                        total_todo_count += 1
                        if len(todos) < _MAX_REPORTED_TODOS:
                            todos.append(FirmwareTodo(
                                file_path=str(src_file.relative_to(firmware_dir)),
                                line_number=lineno,
                                text=line.strip()[:80],
                            ))
            except OSError:
                pass

        # ------------------------------------------------------------------
        # Required files check
        # ------------------------------------------------------------------
        all_file_names = [f.name for f in all_files if f.is_file()]
        all_file_paths = [str(f) for f in all_files if f.is_file()]

        has_entry_point = any(
            _REQUIRED_SIGNATURES[0].search(name) for name in all_file_names
        )
        has_build_file = any(
            _REQUIRED_SIGNATURES[1].search(name) for name in all_file_names
        )

        if not has_entry_point:
            issues.append("No main source file found (main.c / main.cpp / main.py / ...)")

        if not has_build_file:
            issues.append(
                "No build file found (CMakeLists.txt / platformio.ini / Makefile / ...)"
            )

        if file_count == 0:
            issues.append("No source files found in firmware directory")

        # ------------------------------------------------------------------
        # TODO issues
        # ------------------------------------------------------------------
        if total_todo_count > 0:
            issues.append(
                f"{total_todo_count} TODO/FIXME placeholder(s) in generated code — "
                "firmware not ready for compilation"
            )
            for todo in todos[:5]:
                issues.append(f"  {todo.file_path}:{todo.line_number}: {todo.text}")
            if total_todo_count > _MAX_REPORTED_TODOS:
                remaining = total_todo_count - _MAX_REPORTED_TODOS
                issues.append(f"  ... and {remaining} more")

        # ------------------------------------------------------------------
        # Score
        # ------------------------------------------------------------------
        score = 1.0 - (_PENALTY_PER_TODO * total_todo_count)
        if not has_entry_point:
            score -= 0.20
        if not has_build_file:
            score -= 0.10
        if file_count == 0:
            score = 0.0
        score = max(0.0, min(1.0, round(score, 3)))

        compilable = (
            total_todo_count == 0
            and has_entry_point
            and has_build_file
            and file_count > 0
        )

        return FirmwareReviewResult(
            score=score,
            todo_count=total_todo_count,
            file_count=file_count,
            has_entry_point=has_entry_point,
            has_build_file=has_build_file,
            compilable=compilable,
            issues=issues,
            todos=todos,
        )
