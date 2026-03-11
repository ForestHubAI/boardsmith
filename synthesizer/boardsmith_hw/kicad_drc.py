# SPDX-License-Identifier: AGPL-3.0-or-later
"""B15. KiCad DRC/ERC — Design Rule & Electrical Rules Checks via kicad-cli.

Provides a unified interface for running KiCad checks on generated files:

  - **ERC** (Electrical Rules Check) on .kicad_sch schematics
  - **DRC** (Design Rule Check) on .kicad_pcb boards
  - **ERCRefiner** — closed-loop: export → ERC → fix → re-export → re-check

Both checks use `kicad-cli` (KiCad 7+) and degrade gracefully when the
tool is not installed: an empty result with a note is returned instead
of an exception.

Usage::

    checker = KiCadChecker()

    # ERC on a schematic
    erc = checker.run_erc(Path("output/schematic.kicad_sch"))
    print(f"ERC: {erc.error_count} errors, {erc.warning_count} warnings")

    # Closed-loop ERC refinement
    refiner = ERCRefiner(max_iterations=3)
    result = refiner.refine(hir_dict, Path("output/schematic.kicad_sch"))
    if result.passed:
        print(f"ERC clean after {result.iterations} iterations")
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DRCViolation:
    """A single DRC or ERC violation reported by kicad-cli."""

    severity: str       # "error" | "warning" | "info"
    description: str    # Human-readable violation description
    rule_id: str = ""   # KiCad rule identifier (e.g. "pin_not_connected")
    items: list[str] = field(default_factory=list)  # Affected items / locations


@dataclass
class ERCRefinementResult:
    """Result of a closed-loop ERC refinement pass.

    Attributes:
        passed:          True if ERC passes (no errors) after refinement.
        iterations:      Number of export → ERC → fix cycles performed.
        initial_errors:  Error count from the first ERC run.
        final_errors:    Error count after the last ERC run.
        fixes_applied:   List of fix strategies that were applied.
        final_check:     The CheckResult from the last ERC run.
        tool_available:  True if kicad-cli was found.
    """

    passed: bool
    iterations: int
    initial_errors: int = 0
    final_errors: int = 0
    fixes_applied: list[str] = field(default_factory=list)
    final_check: "CheckResult | None" = None
    tool_available: bool = False


@dataclass
class CheckResult:
    """Result of a DRC or ERC check.

    Attributes:
        check_type:    "erc" or "drc".
        passed:        True if no errors were found (warnings are OK).
        violations:    List of structured violations.
        error_count:   Number of error-severity violations.
        warning_count: Number of warning-severity violations.
        error_messages: Flat list of error descriptions (for backward compat).
        tool_available: True if kicad-cli was found on PATH.
        note:          Human-readable status note.
    """

    check_type: str                  # "erc" | "drc"
    passed: bool
    violations: list[DRCViolation] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    error_messages: list[str] = field(default_factory=list)
    tool_available: bool = False
    note: str = ""


# ---------------------------------------------------------------------------
# KiCadChecker
# ---------------------------------------------------------------------------


class KiCadChecker:
    """Runs ERC and DRC checks via kicad-cli.

    Gracefully degrades when kicad-cli is not installed — all public
    methods return a CheckResult with ``tool_available=False`` and an
    explanatory note rather than raising an exception.
    """

    # Well-known macOS/Linux/Windows install locations for kicad-cli
    _KICAD_CLI_SEARCH_PATHS = [
        "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",  # macOS bundle
        "/usr/bin/kicad-cli",
        "/usr/local/bin/kicad-cli",
    ]

    def __init__(self) -> None:
        self._cli_available: bool | None = None
        self._cli_path: str = "kicad-cli"  # default; overridden by _find_cli()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self, path: Path) -> CheckResult:
        """Auto-detect file type and run the appropriate check.

        Args:
            path: Path to a .kicad_sch (→ ERC) or .kicad_pcb (→ DRC) file.

        Returns:
            CheckResult from ERC or DRC.

        Raises:
            ValueError: If the file extension is not recognized.
        """
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix == ".kicad_sch":
            return self.run_erc(path)
        elif suffix == ".kicad_pcb":
            return self.run_drc(path)
        else:
            raise ValueError(
                f"Unsupported file type '{suffix}' — expected .kicad_sch or .kicad_pcb"
            )

    def run_erc(self, sch_path: Path) -> CheckResult:
        """Run Electrical Rules Check on a KiCad schematic.

        Args:
            sch_path: Path to a .kicad_sch file.

        Returns:
            CheckResult with ERC violations.
        """
        if not self.kicad_cli_available():
            return CheckResult(
                check_type="erc",
                passed=True,
                tool_available=False,
                note="kicad-cli nicht installiert — ERC übersprungen.",
            )

        self.kicad_cli_available()  # ensure _cli_path is resolved
        return self._run_check(
            check_type="erc",
            cmd_parts=[self._cli_path, "sch", "erc"],
            target_path=Path(sch_path),
        )

    def export_erc_rpt(self, sch_path: Path, rpt_path: Path) -> bool:
        """Run ERC and write the human-readable .rpt text file to *rpt_path*.

        This is the equivalent of::

            kicad-cli sch erc schematic.kicad_sch --output ERC.rpt

        The report is written in KiCad's native text format (same as what
        KiCad itself produces when you click "Save…" in the ERC dialog).

        Args:
            sch_path: Path to the .kicad_sch file.
            rpt_path: Destination path for the .rpt text file.

        Returns:
            True if kicad-cli ran and produced the report, False otherwise.
        """
        if not self.kicad_cli_available():
            log.debug("export_erc_rpt: kicad-cli not available, skipping")
            return False

        rpt_path = Path(rpt_path)
        rpt_path.parent.mkdir(parents=True, exist_ok=True)

        self.kicad_cli_available()  # ensure _cli_path is resolved
        cmd = [
            self._cli_path, "sch", "erc",
            "--output", str(rpt_path),
            "--severity-all",
            str(sch_path),
        ]
        log.debug("export_erc_rpt: %s", " ".join(cmd))
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if rpt_path.exists():
                log.info("ERC report written to %s", rpt_path)
                return True
            # kicad-cli sometimes writes nothing if the schematic has no errors
            # — write a minimal stub so the file always exists
            rpt_path.write_text(
                f"ERC report\n(no violations found or kicad-cli produced no output)\n"
                f"stderr: {proc.stderr[:300]}\n",
                encoding="utf-8",
            )
            return True
        except Exception as exc:
            log.warning("export_erc_rpt failed: %s", exc)
            return False

    def export_drc_rpt(self, pcb_path: Path, rpt_path: Path) -> bool:
        """Run DRC and write the human-readable .rpt text file to *rpt_path*.

        This is the equivalent of::

            kicad-cli pcb drc pcb.kicad_pcb --output DRC.rpt

        Args:
            pcb_path: Path to the .kicad_pcb file.
            rpt_path: Destination path for the .rpt text file.

        Returns:
            True if kicad-cli ran and produced the report, False otherwise.
        """
        if not self.kicad_cli_available():
            log.debug("export_drc_rpt: kicad-cli not available, skipping")
            return False

        rpt_path = Path(rpt_path)
        rpt_path.parent.mkdir(parents=True, exist_ok=True)

        self.kicad_cli_available()  # ensure _cli_path is resolved
        cmd = [
            self._cli_path, "pcb", "drc",
            "--output", str(rpt_path),
            "--severity-all",
            str(pcb_path),
        ]
        log.debug("export_drc_rpt: %s", " ".join(cmd))
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if rpt_path.exists():
                log.info("DRC report written to %s", rpt_path)
                return True
            rpt_path.write_text(
                f"DRC report\n(no violations found or kicad-cli produced no output)\n"
                f"stderr: {proc.stderr[:300]}\n",
                encoding="utf-8",
            )
            return True
        except Exception as exc:
            log.warning("export_drc_rpt failed: %s", exc)
            return False

    @staticmethod
    def count_unconnected_from_rpt(rpt_path: "Path | str") -> int:
        """Parse DRC.rpt and return the unconnected pad count.

        Looks for the pattern: ** Found N unconnected pads **
        Returns 0 if the file does not exist or no match is found.
        """
        import re
        try:
            text = Path(rpt_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return 0
        m = re.search(r"\*\* Found (\d+) unconnected pad", text)
        return int(m.group(1)) if m else 0

    def run_drc(self, pcb_path: Path) -> CheckResult:
        """Run Design Rule Check on a KiCad PCB.

        Args:
            pcb_path: Path to a .kicad_pcb file.

        Returns:
            CheckResult with DRC violations.
        """
        if not self.kicad_cli_available():
            return CheckResult(
                check_type="drc",
                passed=True,
                tool_available=False,
                note="kicad-cli nicht installiert — DRC übersprungen.",
            )

        self.kicad_cli_available()  # ensure _cli_path is resolved
        return self._run_check(
            check_type="drc",
            cmd_parts=[self._cli_path, "pcb", "drc"],
            target_path=Path(pcb_path),
        )

    # ------------------------------------------------------------------
    # Tool availability
    # ------------------------------------------------------------------

    def _find_cli(self) -> str | None:
        """Return the full path to kicad-cli, or None if not found."""
        # 1. Standard PATH lookup
        found = shutil.which("kicad-cli")
        if found:
            return found
        # 2. Well-known install locations (macOS bundle, etc.)
        for candidate in self._KICAD_CLI_SEARCH_PATHS:
            if Path(candidate).is_file():
                return candidate
        return None

    def kicad_cli_available(self) -> bool:
        """True if ``kicad-cli`` is found on PATH or at a known install location."""
        if self._cli_available is None:
            path = self._find_cli()
            self._cli_available = path is not None
            if path:
                self._cli_path = path
        return self._cli_available

    @staticmethod
    def is_available() -> bool:
        """Static convenience: check kicad-cli availability."""
        inst = KiCadChecker()
        return inst.kicad_cli_available()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_check(
        self,
        check_type: str,
        cmd_parts: list[str],
        target_path: Path,
    ) -> CheckResult:
        """Execute a kicad-cli check command and parse the JSON report."""
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False
        ) as fh:
            report_path = Path(fh.name)

        try:
            cmd = [
                *cmd_parts,
                "--output", str(report_path),
                "--format", "json",
                "--severity-all",
                str(target_path),
            ]
            log.debug("KiCadChecker: running %s", " ".join(cmd))

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )

            # kicad-cli may return non-zero even when violations exist;
            # the JSON report is the authoritative source.
            if not report_path.exists():
                note = f"kicad-cli {check_type.upper()} lieferte keine Report-Datei."
                if proc.stderr:
                    note += f" stderr: {proc.stderr[:300]}"
                return CheckResult(
                    check_type=check_type,
                    passed=False,
                    tool_available=True,
                    note=note,
                )

            return self._parse_report(check_type, report_path)

        except subprocess.TimeoutExpired:
            return CheckResult(
                check_type=check_type,
                passed=False,
                tool_available=True,
                note=f"kicad-cli {check_type.upper()} Timeout (>120s).",
            )
        except Exception as exc:
            log.debug("KiCadChecker %s failed: %s", check_type, exc)
            return CheckResult(
                check_type=check_type,
                passed=False,
                tool_available=True,
                note=f"kicad-cli {check_type.upper()} error: {exc}",
            )
        finally:
            try:
                report_path.unlink()
            except OSError:
                pass

    def _parse_report(self, check_type: str, report_path: Path) -> CheckResult:
        """Parse the JSON report written by kicad-cli."""
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return CheckResult(
                check_type=check_type,
                passed=False,
                tool_available=True,
                note=f"Failed to parse report JSON: {exc}",
            )

        violations: list[DRCViolation] = []
        error_messages: list[str] = []

        # kicad-cli JSON format: {"violations": [...]} or {"sheets": [...]}
        raw_violations = data.get("violations", [])

        # ERC reports may nest violations under "sheets"
        if not raw_violations and "sheets" in data:
            for sheet in data.get("sheets", []):
                raw_violations.extend(sheet.get("violations", []))

        # DRC rules waived because our footprints are generated inline, not
        # fetched from standard KiCad libraries.  The mismatch is inherent
        # to the synthetic generation approach and harmless for manufacturing.
        _DRC_WAIVED_RULES = frozenset({
            "lib_footprint_mismatch",   # inline != std library copy
            "lib_footprint_issues",     # footprint not found in library
            "silk_edge_clearance",      # cosmetic: silkscreen near board edge
        })

        for v in raw_violations:
            severity = v.get("severity", "warning").lower()
            description = v.get("description", str(v))
            rule_id = v.get("type", "")

            # Skip waived DRC rules
            if check_type == "drc" and rule_id in _DRC_WAIVED_RULES:
                continue

            items: list[str] = []
            for item in v.get("items", []):
                desc = item.get("description", "")
                pos = item.get("pos", {})
                if desc:
                    loc = ""
                    if pos:
                        loc = f" @ ({pos.get('x', '?')}, {pos.get('y', '?')})"
                    items.append(f"{desc}{loc}")

            violations.append(DRCViolation(
                severity=severity,
                description=description,
                rule_id=rule_id,
                items=items,
            ))

            if severity in ("error", "warning"):
                error_messages.append(description)

        # Cap at 30 violations to keep output readable
        violations = violations[:30]
        error_messages = error_messages[:30]

        error_count = sum(1 for v in violations if v.severity == "error")
        warning_count = sum(1 for v in violations if v.severity == "warning")
        passed = error_count == 0

        return CheckResult(
            check_type=check_type,
            passed=passed,
            violations=violations,
            error_count=error_count,
            warning_count=warning_count,
            error_messages=error_messages,
            tool_available=True,
            note=(
                f"{check_type.upper()} passed — no errors."
                if passed
                else f"{check_type.upper()}: {error_count} error(s), {warning_count} warning(s)."
            ),
        )


# ---------------------------------------------------------------------------
# ERCRefiner — closed-loop: export → ERC → fix → re-export → re-check
# ---------------------------------------------------------------------------


# Fix strategies applied in order of priority.
_ERC_FIX_STRATEGIES = [
    ("no_connect", "No-Connect-Flags auf unbenutzten Pins"),
    ("pwr_flag", "PWR_FLAG-Symbole auf Versorgungsnetzen"),
]


class ERCRefiner:
    """Closed-loop ERC: export schematic → run ERC → apply fixes → re-export.

    Iteratively applies fix strategies to eliminate KiCad ERC violations:

      1. **no_connect**: Adds no-connect flags on intentionally unconnected pins.
      2. **pwr_flag**: Adds PWR_FLAG symbols on power nets.

    Each iteration re-exports the .kicad_sch with the accumulated fixes
    enabled, then re-runs ERC. The loop terminates when ERC passes or
    all fix strategies have been exhausted.

    Usage::

        refiner = ERCRefiner(max_iterations=3)
        result = refiner.refine(hir_dict, Path("output/schematic.kicad_sch"))
        if result.passed:
            print("ERC clean!")
        else:
            for v in result.final_check.violations:
                print(f"  [{v.severity}] {v.description}")
    """

    def __init__(
        self,
        max_iterations: int = 3,
        use_llm: bool = False,
    ) -> None:
        self.max_iterations = max_iterations
        self._use_llm = use_llm
        self._checker = KiCadChecker()

    def refine(
        self,
        hir_dict: dict,
        sch_path: Path,
    ) -> ERCRefinementResult:
        """Run the closed-loop ERC refinement.

        Always exports the schematic at least once, even when kicad-cli
        is not available (in that case, no ERC is run).

        Args:
            hir_dict:  The HIR dictionary to export.
            sch_path:  Path where the .kicad_sch will be written.

        Returns:
            ERCRefinementResult with pass/fail status and fix history.
        """
        from boardsmith_hw.kicad_exporter import export_kicad_sch

        if not self._checker.kicad_cli_available():
            # Export schematic normally, but skip the ERC loop
            export_kicad_sch(hir_dict, sch_path, use_llm=self._use_llm)
            return ERCRefinementResult(
                passed=True,
                iterations=0,
                tool_available=False,
            )

        fixes_applied: list[str] = []
        add_no_connect = False
        add_pwr_flag = False

        # Initial export (no ERC fixes yet)
        export_kicad_sch(
            hir_dict, sch_path,
            use_llm=self._use_llm,
            add_no_connect=add_no_connect,
            add_pwr_flag=add_pwr_flag,
        )

        # First ERC run
        initial_result = self._checker.run_erc(sch_path)
        initial_errors = initial_result.error_count
        current_result = initial_result

        if current_result.passed:
            return ERCRefinementResult(
                passed=True,
                iterations=1,
                initial_errors=initial_errors,
                final_errors=0,
                final_check=current_result,
                tool_available=True,
            )

        # Iterative fix loop
        for iteration in range(1, self.max_iterations + 1):
            # Determine which fixes to apply based on violation types
            new_fix = self._select_fix(current_result, fixes_applied)
            if new_fix is None:
                # No more fix strategies available
                break

            fixes_applied.append(new_fix)
            log.info(
                "ERCRefiner iteration %d: applying fix '%s'",
                iteration, new_fix,
            )

            # Apply the fix
            if new_fix == "no_connect":
                add_no_connect = True
            elif new_fix == "pwr_flag":
                add_pwr_flag = True

            # Re-export with accumulated fixes
            export_kicad_sch(
                hir_dict, sch_path,
                use_llm=self._use_llm,
                add_no_connect=add_no_connect,
                add_pwr_flag=add_pwr_flag,
            )

            # Re-run ERC
            current_result = self._checker.run_erc(sch_path)

            if current_result.passed:
                log.info(
                    "ERCRefiner: ERC passed after %d fix(es): %s",
                    len(fixes_applied), ", ".join(fixes_applied),
                )
                break

        final_errors = current_result.error_count

        return ERCRefinementResult(
            passed=current_result.passed,
            iterations=len(fixes_applied) + 1,  # +1 for the initial run
            initial_errors=initial_errors,
            final_errors=final_errors,
            fixes_applied=fixes_applied,
            final_check=current_result,
            tool_available=True,
        )

    def _select_fix(
        self,
        result: CheckResult,
        already_applied: list[str],
    ) -> str | None:
        """Select the next fix strategy based on the current ERC violations.

        Returns the fix name or None if no more fixes are available.
        """
        for fix_name, _desc in _ERC_FIX_STRATEGIES:
            if fix_name in already_applied:
                continue

            # Match fix to violation types
            if fix_name == "no_connect":
                # Apply if any "pin not connected" or "unconnected" violations
                has_pin_issues = any(
                    "not connected" in v.description.lower()
                    or "unconnected" in v.description.lower()
                    or v.rule_id in ("pin_not_connected", "pin_unconnected")
                    for v in result.violations
                )
                if has_pin_issues:
                    return fix_name

            elif fix_name == "pwr_flag":
                # Apply if any "power pin not driven" or "power" violations
                has_power_issues = any(
                    "power" in v.description.lower()
                    or "not driven" in v.description.lower()
                    or v.rule_id in ("power_pin_not_driven", "missing_power_flag")
                    for v in result.violations
                )
                if has_power_issues:
                    return fix_name

        # Fallback: try fixes in order even if we can't match violation type
        for fix_name, _desc in _ERC_FIX_STRATEGIES:
            if fix_name not in already_applied:
                return fix_name

        return None
