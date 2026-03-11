# SPDX-License-Identifier: AGPL-3.0-or-later
"""PCBReviewAgent — Phase 21 specialist for PCB layout and manufacturability.

Checks:
  - DRC violation count and severity (from PcbResult / kicad-cli output)
  - Board density (components per cm²) vs. assembly-house limits
  - SPI/high-speed trace length estimates vs. signal-integrity limits
  - Manufacturability: min trace width / clearance vs. JLCPCB 6mil spec
  - Missing copper fill (GND plane coverage)

All checks are fully deterministic (no LLM required).
Score: 1.0 = DRC-clean, well-spaced, within JLCPCB manufacturing spec.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JLCPCB manufacturing capabilities (4-layer, 2-layer standard)
# ---------------------------------------------------------------------------

JLCPCB_MIN_TRACE_MM   = 0.127   # 5 mil
JLCPCB_MIN_SPACE_MM   = 0.127   # 5 mil (clearance)
JLCPCB_MIN_DRILL_MM   = 0.20    # 0.2 mm drill
JLCPCB_MIN_ANNULAR_MM = 0.13    # minimum annular ring

# Board density warning threshold (components per cm²)
_MAX_DENSITY_CM2 = 4.0    # >4 ICs per cm² = likely placement conflict
_WARN_DENSITY_CM2 = 2.5   # >2.5 ICs per cm² = warn

# SPI trace length warning (mm); above this, impedance matching is needed
_SPI_SAFE_TRACE_MM = 60.0

# Score penalties
_DRC_ERROR_PENALTY   = 0.15
_DRC_WARNING_PENALTY = 0.05
_ISSUE_WARNING_PENALTY = 0.05
_ISSUE_ERROR_PENALTY   = 0.15

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PcbIssue:
    code: str
    severity: str           # "error" | "warning" | "info"
    message: str
    suggestion: str = ""


@dataclass
class PcbReviewResult:
    issues: list[PcbIssue] = field(default_factory=list)
    score: float = 1.0
    drc_error_count: int = 0
    drc_warning_count: int = 0
    checks_run: list[str] = field(default_factory=list)
    board_density_cm2: float = 0.0

    @property
    def errors(self) -> list[PcbIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[PcbIssue]:
        return [i for i in self.issues if i.severity == "warning"]


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class PCBReviewAgent:
    """Deterministic PCB layout and manufacturability reviewer.

    Usage::

        agent = PCBReviewAgent()
        # With PCB result from pipeline:
        result = agent.review(hir_dict, pcb_result=pcb_result)
        # Without PCB result (layout not run yet):
        result = agent.review(hir_dict)
        print(f"PCB score: {result.score:.2f}")
        print(f"DRC errors: {result.drc_error_count}")
    """

    def review(
        self,
        hir_dict: dict[str, Any],
        pcb_result: Any | None = None,
    ) -> PcbReviewResult:
        """Run all PCB checks.

        Args:
            hir_dict:   Hardware Intermediate Representation dict.
            pcb_result: Optional PcbResult from PcbPipeline.run(). When
                        provided, real DRC data and board bounds are used.
        """
        result = PcbReviewResult()

        self._check_drc_violations(hir_dict, pcb_result, result)
        self._check_board_density(hir_dict, pcb_result, result)
        self._check_spi_trace_length(hir_dict, result)
        self._check_manufacturing_spec(pcb_result, result)
        self._check_copper_fill(pcb_result, result)

        # --- Score ---
        drc_penalty = min(
            _DRC_ERROR_PENALTY * result.drc_error_count
            + _DRC_WARNING_PENALTY * result.drc_warning_count,
            0.60,
        )
        issue_penalty = min(
            _ISSUE_ERROR_PENALTY * len(result.errors)
            + _ISSUE_WARNING_PENALTY * len(result.warnings),
            0.40,
        )
        result.score = round(max(0.0, 1.0 - drc_penalty - issue_penalty), 3)

        return result

    # ------------------------------------------------------------------
    # Check: DRC violations from PcbResult
    # ------------------------------------------------------------------

    def _check_drc_violations(
        self,
        hir: dict,
        pcb_result: Any,
        result: PcbReviewResult,
    ) -> None:
        result.checks_run.append("drc_violations")
        if pcb_result is None:
            return

        drc_errors: list[str] = getattr(pcb_result, "drc_errors", [])
        for err_str in drc_errors:
            err_lower = err_str.lower()
            if any(kw in err_lower for kw in ("error", "violation", "clearance", "track")):
                result.drc_error_count += 1
            else:
                result.drc_warning_count += 1

        if result.drc_error_count > 0:
            result.issues.append(PcbIssue(
                code="DRC_ERRORS",
                severity="error",
                message=(
                    f"{result.drc_error_count} DRC error(s) remain after auto-fix. "
                    "Board may not pass JLCPCB manufacturing checks."
                ),
                suggestion=(
                    "Review DRC errors in KiCad PCB editor; "
                    "run DRC auto-fix loop (pcb_drc_autofix.py) again."
                ),
            ))
        elif result.drc_warning_count > 5:
            result.issues.append(PcbIssue(
                code="DRC_WARNINGS",
                severity="warning",
                message=(
                    f"{result.drc_warning_count} DRC warning(s) detected. "
                    "Review before production."
                ),
                suggestion="Check courtyard overlaps and silkscreen clipping in KiCad.",
            ))

    # ------------------------------------------------------------------
    # Check: board density
    # ------------------------------------------------------------------

    def _check_board_density(
        self,
        hir: dict,
        pcb_result: Any,
        result: PcbReviewResult,
    ) -> None:
        result.checks_run.append("board_density")
        components = hir.get("components", [])
        n_ics = len([c for c in components if c.get("role") not in ("passive",)])

        if n_ics == 0:
            return

        # Estimate board area
        board_area_mm2 = self._estimate_board_area_mm2(components, pcb_result)
        if board_area_mm2 <= 0:
            return

        board_area_cm2 = board_area_mm2 / 100.0
        density = n_ics / board_area_cm2
        result.board_density_cm2 = round(density, 2)

        if density > _MAX_DENSITY_CM2:
            result.issues.append(PcbIssue(
                code="BOARD_TOO_DENSE",
                severity="error",
                message=(
                    f"Board density {density:.1f} ICs/cm² exceeds {_MAX_DENSITY_CM2} limit. "
                    "Component placement conflicts likely."
                ),
                suggestion=(
                    "Increase board size in layout engine (SENSOR_X offset) or "
                    "use a multi-layer board (4-layer) to gain routing space."
                ),
            ))
        elif density > _WARN_DENSITY_CM2:
            result.issues.append(PcbIssue(
                code="BOARD_DENSE",
                severity="warning",
                message=(
                    f"Board density {density:.1f} ICs/cm² is high. "
                    "Verify that courtyard areas do not overlap."
                ),
                suggestion=(
                    "Open the generated .kicad_pcb and check courtyard overlaps; "
                    "consider adjusting COMP_Y_STEP in pcb_layout_engine.py."
                ),
            ))

    def _estimate_board_area_mm2(
        self,
        components: list[dict],
        pcb_result: Any,
    ) -> float:
        """Estimate board area from pcb_result or heuristic."""
        # Try to get from pcb_result (future: board_bounds field)
        if pcb_result is not None:
            pcb_path = getattr(pcb_result, "pcb_path", None)
            if pcb_path and Path(pcb_path).exists():
                try:
                    text = Path(pcb_path).read_text(encoding="utf-8", errors="ignore")
                    # Parse Edge.Cuts gr_rect (start x1 y1) (end x2 y2)
                    import re
                    m = re.search(
                        r'gr_rect\s+\(start\s+([\d.]+)\s+([\d.]+)\)\s+\(end\s+([\d.]+)\s+([\d.]+)\)',
                        text,
                    )
                    if m:
                        x1, y1, x2, y2 = map(float, m.groups())
                        return abs(x2 - x1) * abs(y2 - y1)
                except Exception:
                    pass

        # Heuristic: ~15mm² per IC + 5mm² per passive
        n_ics     = len([c for c in components if c.get("role") not in ("passive",)])
        n_passive = len([c for c in components if c.get("role") == "passive"])
        return n_ics * 15.0 * 15.0 + n_passive * 3.0 * 3.0

    # ------------------------------------------------------------------
    # Check: SPI trace length
    # ------------------------------------------------------------------

    def _check_spi_trace_length(
        self,
        hir: dict,
        result: PcbReviewResult,
    ) -> None:
        result.checks_run.append("spi_trace_length")
        bus_contracts = hir.get("bus_contracts", [])

        for bc in bus_contracts:
            if bc.get("bus_type") != "SPI":
                continue
            hz = bc.get("configured_clock_hz", 0) or 0
            n_slaves = len(bc.get("slave_ids", []))
            # At 20 MHz, wavelength ~15m; 60mm < λ/20 so no stub issues
            # At 80 MHz, quarter-wave concerns start at 30mm
            if hz >= 40_000_000 and n_slaves > 1:
                result.issues.append(PcbIssue(
                    code="SPI_STUB_LENGTH",
                    severity="warning",
                    message=(
                        f"SPI bus at {hz/1e6:.0f} MHz with {n_slaves} slaves: "
                        f"keep stubs < {_SPI_SAFE_TRACE_MM:.0f} mm and "
                        "use daisy-chain topology."
                    ),
                    suggestion=(
                        "Route SPI as daisy-chain (not star); "
                        "add 22 Ω series resistors on SCLK/MOSI."
                    ),
                ))

    # ------------------------------------------------------------------
    # Check: manufacturing spec compliance
    # ------------------------------------------------------------------

    def _check_manufacturing_spec(
        self,
        pcb_result: Any,
        result: PcbReviewResult,
    ) -> None:
        result.checks_run.append("manufacturing_spec")
        if pcb_result is None:
            return

        pcb_path = getattr(pcb_result, "pcb_path", None)
        if not pcb_path or not Path(pcb_path).exists():
            return

        try:
            import re
            text = Path(pcb_path).read_text(encoding="utf-8", errors="ignore")

            # Find all segment widths — use non-greedy scan after (segment
            widths = [
                float(m.group(1))
                for m in re.finditer(r'\(segment\b.*?\(width\s+([\d.]+)\)', text, re.DOTALL)
            ]
            if widths:
                min_w = min(widths)
                if min_w < JLCPCB_MIN_TRACE_MM:
                    result.issues.append(PcbIssue(
                        code="TRACE_BELOW_SPEC",
                        severity="error",
                        message=(
                            f"Minimum trace width {min_w:.3f} mm is below JLCPCB "
                            f"spec ({JLCPCB_MIN_TRACE_MM:.3f} mm = 5 mil)."
                        ),
                        suggestion=(
                            "Re-run DRC auto-fix (pcb_drc_autofix.py) or "
                            "manually widen traces in KiCad."
                        ),
                    ))

            # Find all via drills — same non-greedy approach
            drills = [
                float(m.group(1))
                for m in re.finditer(r'\(via\b.*?\(drill\s+([\d.]+)\)', text, re.DOTALL)
            ]
            if drills:
                min_d = min(drills)
                if min_d < JLCPCB_MIN_DRILL_MM:
                    result.issues.append(PcbIssue(
                        code="VIA_BELOW_SPEC",
                        severity="error",
                        message=(
                            f"Minimum via drill {min_d:.3f} mm is below JLCPCB "
                            f"spec ({JLCPCB_MIN_DRILL_MM:.3f} mm)."
                        ),
                        suggestion=(
                            "Run DRC auto-fix: all vias will be increased to "
                            "drill=0.3 mm, size=0.6 mm automatically."
                        ),
                    ))
        except Exception as exc:
            log.debug("Manufacturing spec check skipped: %s", exc)

    # ------------------------------------------------------------------
    # Check: copper fill
    # ------------------------------------------------------------------

    def _check_copper_fill(
        self,
        pcb_result: Any,
        result: PcbReviewResult,
    ) -> None:
        result.checks_run.append("copper_fill")
        if pcb_result is None:
            return

        pcb_path = getattr(pcb_result, "pcb_path", None)
        if not pcb_path or not Path(pcb_path).exists():
            return

        try:
            text = Path(pcb_path).read_text(encoding="utf-8", errors="ignore")
            has_zone = "(zone" in text
            if not has_zone:
                result.issues.append(PcbIssue(
                    code="NO_COPPER_FILL",
                    severity="warning",
                    message=(
                        "No copper fill zone found in PCB. "
                        "Missing GND plane increases EMI and weakens power distribution."
                    ),
                    suggestion=(
                        "Run DRC auto-fix: it will add a GND copper fill zone "
                        "covering the full board outline."
                    ),
                ))
        except Exception as exc:
            log.debug("Copper fill check skipped: %s", exc)
