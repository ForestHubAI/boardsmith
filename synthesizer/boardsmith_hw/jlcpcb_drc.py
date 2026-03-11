# SPDX-License-Identifier: AGPL-3.0-or-later
"""JLCPCB Design Rules Checker — validates PCB S-expression against JLCPCB constraints.

Checks manufacturing constraints from the .kicad_pcb file without requiring kicad-cli.
All limits are sourced from the JLCPCB Standard PCB Capabilities page (2024).

Usage::

    from boardsmith_hw.jlcpcb_drc import JLCPCBDRCChecker

    checker = JLCPCBDRCChecker()
    result = checker.check(pcb_path)
    if not result.valid:
        for issue in result.errors:
            print(f"[ERROR] {issue.message}")
    print(result.summary())
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# JLCPCB Standard PCB Manufacturing Limits (2024)
# ---------------------------------------------------------------------------

# Board dimensions (standard tier, mm)
BOARD_MAX_WIDTH_MM = 500.0
BOARD_MAX_HEIGHT_MM = 500.0
BOARD_MIN_WIDTH_MM = 5.0
BOARD_MIN_HEIGHT_MM = 5.0
# Standard tier (cheapest): ≤100×100mm. Above = extended price.
BOARD_STANDARD_MAX_MM = 100.0

# Trace + copper constraints (mm)
TRACK_WIDTH_MIN_MM = 0.127          # 5mil — absolute minimum
TRACK_CLEARANCE_MIN_MM = 0.127      # 5mil — absolute minimum
COPPER_EDGE_CLEARANCE_MIN_MM = 0.2  # copper to edge

# Drill / via constraints (mm)
DRILL_MIN_DIAMETER_MM = 0.2         # 0.2mm = 7.87mil minimum
DRILL_RECOMMENDED_MM = 0.3          # 0.3mm recommended for reliable yield
VIA_ANNULAR_RING_MIN_MM = 0.1       # min copper ring around via hole
VIA_SIZE_MIN_MM = DRILL_MIN_DIAMETER_MM + 2 * VIA_ANNULAR_RING_MIN_MM  # 0.4mm

# Assembly constraints (SMT)
COMPONENT_HEIGHT_MAX_MM = 6.5       # max body height for standard SMT assembly


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DRCIssue:
    """A single DRC violation or warning."""

    severity: str   # "error" | "warning" | "info"
    rule: str       # Short rule name, e.g. "min_track_width"
    message: str    # Human-readable description
    value: float | None = None    # Measured value (mm), if applicable
    limit: float | None = None    # Rule limit (mm), if applicable

    def __str__(self) -> str:
        parts = [f"[{self.severity.upper()}] {self.rule}: {self.message}"]
        if self.value is not None and self.limit is not None:
            parts.append(f"(measured={self.value:.3f}mm, limit={self.limit:.3f}mm)")
        return " ".join(parts)


@dataclass
class JLCPCBDRCResult:
    """Result of a JLCPCB DRC check.

    Attributes:
        pcb_path:       Path to the checked .kicad_pcb file (or None for in-memory).
        issues:         All DRC issues (errors + warnings + info).
        board_width_mm: Estimated board width from Edge.Cuts bounding box.
        board_height_mm: Estimated board height from Edge.Cuts bounding box.
        track_count:    Number of copper tracks parsed.
        via_count:      Number of vias parsed.
        drill_count:    Number of drill holes parsed.
    """

    pcb_path: Path | None
    issues: list[DRCIssue] = field(default_factory=list)
    board_width_mm: float = 0.0
    board_height_mm: float = 0.0
    track_count: int = 0
    via_count: int = 0
    drill_count: int = 0

    @property
    def errors(self) -> list[DRCIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[DRCIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def valid(self) -> bool:
        """True when there are no error-level DRC violations."""
        return len(self.errors) == 0

    def summary(self) -> str:
        """Return a human-readable summary of the DRC result."""
        lines: list[str] = ["=== JLCPCB DRC Summary ==="]
        if self.board_width_mm > 0:
            lines.append(
                f"Board size: {self.board_width_mm:.1f} × {self.board_height_mm:.1f} mm"
            )
        lines.append(
            f"Tracks: {self.track_count}, Vias: {self.via_count}, "
            f"Drills: {self.drill_count}"
        )
        lines.append(
            f"DRC: {len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        )
        if self.issues:
            lines.append("")
            for issue in self.issues:
                lines.append(str(issue))
        if self.valid:
            lines.append("\n✓ Board passes JLCPCB design rules.")
        else:
            lines.append(
                f"\n✗ {len(self.errors)} error(s) must be fixed before ordering."
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# JLCPCBDRCChecker
# ---------------------------------------------------------------------------


class JLCPCBDRCChecker:
    """Checks a .kicad_pcb S-expression file against JLCPCB manufacturing constraints.

    Works without kicad-cli — uses regex-based S-expression parsing.
    Checks board dimensions, copper trace widths, drill sizes, and via geometry.

    Usage::

        checker = JLCPCBDRCChecker()
        result = checker.check(Path("output/board.kicad_pcb"))
        print(result.summary())
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self, pcb_path: Path) -> JLCPCBDRCResult:
        """Run all JLCPCB DRC checks on a .kicad_pcb file.

        Args:
            pcb_path: Path to the .kicad_pcb file.

        Returns:
            JLCPCBDRCResult with all issues.
        """
        text = pcb_path.read_text(encoding="utf-8", errors="replace")
        return self.check_text(text, pcb_path)

    def check_text(self, pcb_text: str, pcb_path: Path | None = None) -> JLCPCBDRCResult:
        """Run all JLCPCB DRC checks on PCB S-expression text.

        Useful for testing without a real file.

        Args:
            pcb_text:  Raw .kicad_pcb S-expression text.
            pcb_path:  Optional path for error messages.

        Returns:
            JLCPCBDRCResult with all issues.
        """
        result = JLCPCBDRCResult(pcb_path=pcb_path)

        # Parse geometry
        board_w, board_h = self._parse_board_dimensions(pcb_text)
        result.board_width_mm = board_w
        result.board_height_mm = board_h

        track_widths = self._parse_track_widths(pcb_text)
        result.track_count = len(track_widths)

        via_drills, via_sizes = self._parse_via_geometry(pcb_text)
        result.via_count = len(via_drills)
        result.drill_count = len(via_drills)

        # Run checks
        result.issues.extend(self._check_board_dimensions(board_w, board_h))
        result.issues.extend(self._check_track_widths(track_widths))
        result.issues.extend(self._check_via_geometry(via_drills, via_sizes))
        result.issues.extend(self._check_edge_cuts(pcb_text))

        return result

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_board_dimensions(self, text: str) -> tuple[float, float]:
        """Estimate board dimensions from Edge.Cuts line/rect elements.

        Returns (width_mm, height_mm). Returns (0, 0) if no edge cuts found.
        """
        # Collect all (start X Y) and (end X Y) from gr_line on Edge.Cuts
        edge_x: list[float] = []
        edge_y: list[float] = []

        # Match (gr_line (start X Y) (end X Y) ... (layer "Edge.Cuts"))
        # or (gr_rect (start X Y) (end X Y) ... (layer "Edge.Cuts"))
        for pattern in (
            r'\(gr_line\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\)',
            r'\(gr_rect\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\)',
        ):
            for m in re.finditer(pattern, text):
                edge_x.extend([float(m.group(1)), float(m.group(3))])
                edge_y.extend([float(m.group(2)), float(m.group(4))])

        if not edge_x:
            return (0.0, 0.0)

        width = max(edge_x) - min(edge_x)
        height = max(edge_y) - min(edge_y)
        return (abs(width), abs(height))

    def _parse_track_widths(self, text: str) -> list[float]:
        """Parse all copper track (segment) widths from PCB text.

        Returns list of widths in mm (may include duplicates).
        """
        widths: list[float] = []
        # (segment (start X Y) (end X Y) (width W) ...)
        # Use (?:[^)(]|\([^)]*\))* to skip over nested (start/end) groups.
        for m in re.finditer(
            r'\(segment\b(?:[^)(]|\([^)]*\))*\(width\s+([\d.]+)\)', text
        ):
            widths.append(float(m.group(1)))
        return widths

    def _parse_via_geometry(self, text: str) -> tuple[list[float], list[float]]:
        """Parse via drill diameters and pad sizes from PCB text.

        Returns (drill_diameters_mm, via_sizes_mm).
        """
        drills: list[float] = []
        sizes: list[float] = []
        # Extract each (via ...) block, handling one level of nested (attr val) groups.
        # (?:[^)(]|\([^)]*\))* matches non-paren chars or simple (...) sub-expressions.
        via_block_re = re.compile(
            r'\(via\b(?:[^)(]|\([^)]*\))*\)'
        )
        for via_m in via_block_re.finditer(text):
            block = via_m.group(0)
            size_m = re.search(r'\(size\s+([\d.]+)\)', block)
            drill_m = re.search(r'\(drill\s+([\d.]+)\)', block)
            if drill_m:
                drills.append(float(drill_m.group(1)))
            if size_m:
                sizes.append(float(size_m.group(1)))
        return (drills, sizes)

    # ------------------------------------------------------------------
    # Check methods
    # ------------------------------------------------------------------

    def _check_board_dimensions(self, width: float, height: float) -> list[DRCIssue]:
        issues: list[DRCIssue] = []

        if width == 0.0 and height == 0.0:
            issues.append(DRCIssue(
                severity="warning",
                rule="board_outline",
                message="No Edge.Cuts found — board outline is missing. "
                        "JLCPCB requires an Edge.Cuts layer to define the board shape.",
            ))
            return issues

        if width > BOARD_MAX_WIDTH_MM:
            issues.append(DRCIssue(
                severity="error",
                rule="board_max_width",
                message=f"Board width {width:.1f}mm exceeds JLCPCB maximum {BOARD_MAX_WIDTH_MM}mm",
                value=width, limit=BOARD_MAX_WIDTH_MM,
            ))
        if height > BOARD_MAX_HEIGHT_MM:
            issues.append(DRCIssue(
                severity="error",
                rule="board_max_height",
                message=f"Board height {height:.1f}mm exceeds JLCPCB maximum {BOARD_MAX_HEIGHT_MM}mm",
                value=height, limit=BOARD_MAX_HEIGHT_MM,
            ))
        if width < BOARD_MIN_WIDTH_MM:
            issues.append(DRCIssue(
                severity="error",
                rule="board_min_width",
                message=f"Board width {width:.1f}mm is below JLCPCB minimum {BOARD_MIN_WIDTH_MM}mm",
                value=width, limit=BOARD_MIN_WIDTH_MM,
            ))
        if height < BOARD_MIN_HEIGHT_MM:
            issues.append(DRCIssue(
                severity="error",
                rule="board_min_height",
                message=f"Board height {height:.1f}mm is below JLCPCB minimum {BOARD_MIN_HEIGHT_MM}mm",
                value=height, limit=BOARD_MIN_HEIGHT_MM,
            ))
        # Standard vs extended price tier
        if width > BOARD_STANDARD_MAX_MM or height > BOARD_STANDARD_MAX_MM:
            issues.append(DRCIssue(
                severity="info",
                rule="board_extended_price",
                message=f"Board {width:.1f}×{height:.1f}mm exceeds standard 100×100mm — "
                        "extended pricing applies at JLCPCB.",
            ))
        return issues

    def _check_track_widths(self, widths: list[float]) -> list[DRCIssue]:
        issues: list[DRCIssue] = []
        if not widths:
            return issues

        min_width = min(widths)
        if min_width < TRACK_WIDTH_MIN_MM:
            issues.append(DRCIssue(
                severity="error",
                rule="min_track_width",
                message=(
                    f"Minimum track width {min_width:.3f}mm is below JLCPCB "
                    f"minimum {TRACK_WIDTH_MIN_MM}mm (5mil). "
                    "Narrowest trace will be un-manufacturable."
                ),
                value=min_width,
                limit=TRACK_WIDTH_MIN_MM,
            ))
        elif min_width < 0.15:
            issues.append(DRCIssue(
                severity="warning",
                rule="narrow_track_width",
                message=(
                    f"Minimum track width {min_width:.3f}mm is between 0.127mm and 0.15mm — "
                    "acceptable but at the edge of JLCPCB tolerances. "
                    "Wider traces (≥0.2mm) are recommended for reliability."
                ),
                value=min_width,
                limit=0.15,
            ))
        return issues

    def _check_via_geometry(
        self, drills: list[float], sizes: list[float]
    ) -> list[DRCIssue]:
        issues: list[DRCIssue] = []
        if not drills:
            return issues

        min_drill = min(drills)
        if min_drill < DRILL_MIN_DIAMETER_MM:
            issues.append(DRCIssue(
                severity="error",
                rule="min_via_drill",
                message=(
                    f"Minimum via drill diameter {min_drill:.3f}mm is below "
                    f"JLCPCB minimum {DRILL_MIN_DIAMETER_MM}mm. "
                    "The via hole will not be manufacturable."
                ),
                value=min_drill,
                limit=DRILL_MIN_DIAMETER_MM,
            ))
        elif min_drill < DRILL_RECOMMENDED_MM:
            issues.append(DRCIssue(
                severity="warning",
                rule="small_via_drill",
                message=(
                    f"Minimum via drill diameter {min_drill:.3f}mm is below "
                    f"recommended {DRILL_RECOMMENDED_MM}mm. "
                    "Smaller vias have higher defect rates. "
                    "Use ≥0.3mm drill when possible."
                ),
                value=min_drill,
                limit=DRILL_RECOMMENDED_MM,
            ))

        if sizes:
            min_size = min(sizes)
            if min_size < VIA_SIZE_MIN_MM:
                issues.append(DRCIssue(
                    severity="error",
                    rule="min_via_size",
                    message=(
                        f"Minimum via pad size {min_size:.3f}mm is below "
                        f"JLCPCB minimum {VIA_SIZE_MIN_MM}mm "
                        f"(drill + 2×{VIA_ANNULAR_RING_MIN_MM}mm annular ring)."
                    ),
                    value=min_size,
                    limit=VIA_SIZE_MIN_MM,
                ))

        return issues

    def _check_edge_cuts(self, text: str) -> list[DRCIssue]:
        """Check that Edge.Cuts layer is present and contains outline data."""
        issues: list[DRCIssue] = []
        has_edge = (
            '"Edge.Cuts"' in text
            or '"Edge_Cuts"' in text
            or "Edge.Cuts" in text
        )
        if not has_edge:
            issues.append(DRCIssue(
                severity="error",
                rule="missing_edge_cuts",
                message=(
                    "Edge.Cuts layer not found in PCB file. "
                    "JLCPCB requires a closed board outline on the Edge.Cuts layer."
                ),
            ))
        return issues
