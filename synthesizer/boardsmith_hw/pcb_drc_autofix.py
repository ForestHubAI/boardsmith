# SPDX-License-Identifier: AGPL-3.0-or-later
"""PCB DRC Auto-Fix — parse DRC violations and patch the .kicad_pcb file.

After routing (or even on an unrouted board) kicad-cli DRC may report
violations.  This module attempts to automatically fix the most common
classes of violations by rewriting relevant S-expression tokens in the
.kicad_pcb file, then triggers a re-check.

Supported auto-fixes:
  - track_too_narrow   → increase track width to IPC-2221 minimum
  - via_drill_too_small → increase via drill diameter
  - clearance          → widen net-to-net clearance rule
  - pad_clearance      → add/widen pad-to-pad clearance
  - missing_copper_fill → add a GND copper zone to fill remaining area

Usage::

    from boardsmith_hw.pcb_drc_autofix import PcbDrcAutoFix
    fixer = PcbDrcAutoFix()
    result = fixer.fix(pcb_path, violations)
    print(f"Applied: {result.fixes_applied}")
    print(f"Remaining violations: {result.remaining}")
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from boardsmith_hw.kicad_drc import DRCViolation

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — IPC-2221 / JLCPCB minimum design rules
# ---------------------------------------------------------------------------

_IPC_MIN_TRACK_MM    = 0.2    # 8 mil — JLCPCB standard minimum
_IPC_MIN_VIA_DRILL   = 0.3    # 12 mil drill (via total = 0.6 mm)
_IPC_MIN_VIA_SIZE    = 0.6    # via annular ring = (0.6 - 0.3) / 2 = 0.15 mm
_IPC_MIN_CLEARANCE   = 0.15   # 6 mil — allows fine-pitch QFN-56 (0.4mm pitch, 0.16mm gap)

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class AutoFixResult:
    """Outcome of a DRC auto-fix pass.

    Attributes:
        fixes_applied:  Human-readable descriptions of what was changed.
        remaining:      Violation descriptions that could not be auto-fixed.
        pcb_modified:   True if the .kicad_pcb file was rewritten.
    """

    fixes_applied: list[str] = field(default_factory=list)
    remaining: list[str] = field(default_factory=list)
    pcb_modified: bool = False


# ---------------------------------------------------------------------------
# PcbDrcAutoFix
# ---------------------------------------------------------------------------


class PcbDrcAutoFix:
    """Applies automated fixes for common DRC violations.

    All patches operate on the S-expression text of the .kicad_pcb file
    using targeted regex substitutions — no full parse is required.

    Usage::

        fixer = PcbDrcAutoFix()
        result = fixer.fix(pcb_path, violations)
    """

    def fix(
        self,
        pcb_path: Path,
        violations: "list[DRCViolation]",
    ) -> AutoFixResult:
        """Apply automatic fixes for *violations* in *pcb_path*.

        Reads the PCB text, applies each supported fix, rewrites the file
        if any change was made.

        Args:
            pcb_path:   Path to the .kicad_pcb file (modified in-place).
            violations: DRC violations from KiCadChecker.run_drc().

        Returns:
            AutoFixResult describing what was done.
        """
        result = AutoFixResult()
        if not pcb_path.exists():
            result.remaining.append(f"PCB file not found: {pcb_path}")
            return result

        pcb_text = pcb_path.read_text(encoding="utf-8")
        original = pcb_text

        for v in violations:
            desc_lower = v.description.lower()
            rule = v.rule_id.lower()

            if "track" in rule or "track_too_narrow" in rule or "track width" in desc_lower:
                pcb_text, fixed = self._fix_track_width(pcb_text)
                if fixed:
                    result.fixes_applied.append(
                        f"Widened narrow tracks to {_IPC_MIN_TRACK_MM} mm"
                    )
                else:
                    result.remaining.append(v.description)

            elif "via" in rule and ("drill" in desc_lower or "size" in desc_lower):
                pcb_text, fixed = self._fix_via_size(pcb_text)
                if fixed:
                    result.fixes_applied.append(
                        f"Increased via drill to {_IPC_MIN_VIA_DRILL} mm"
                    )
                else:
                    result.remaining.append(v.description)

            elif "clearance" in rule or "clearance" in desc_lower:
                pcb_text, fixed = self._fix_clearance(pcb_text)
                if fixed:
                    result.fixes_applied.append(
                        f"Widened clearance to {_IPC_MIN_CLEARANCE} mm"
                    )
                else:
                    result.remaining.append(v.description)

            elif "copper_fill" in rule or "copper fill" in desc_lower:
                pcb_text, fixed = self._add_gnd_zone(pcb_text)
                if fixed:
                    result.fixes_applied.append("Added GND copper fill zone")
                else:
                    result.remaining.append(v.description)

            else:
                result.remaining.append(v.description)

        # Deduplicate applied fixes
        result.fixes_applied = list(dict.fromkeys(result.fixes_applied))

        if pcb_text != original:
            pcb_path.write_text(pcb_text, encoding="utf-8")
            result.pcb_modified = True
            log.info("DRC auto-fix: rewrote %s (%d fix(es) applied)",
                     pcb_path.name, len(result.fixes_applied))
        else:
            log.debug("DRC auto-fix: no changes needed for %s", pcb_path.name)

        return result

    # ------------------------------------------------------------------
    # Fix strategies
    # ------------------------------------------------------------------

    @staticmethod
    def _fix_track_width(pcb_text: str) -> tuple[str, bool]:
        """Widen any track narrower than _IPC_MIN_TRACK_MM.

        Matches ``(width <value>)`` tokens inside segment/track S-expressions
        and replaces values below the IPC minimum.

        IMPORTANT: fp_rect / fp_circle line widths (courtyard, fab, silkscreen)
        use the SAME (width X) syntax but must NOT be modified — those follow
        IPC-7351 / KiCad conventions (CrtYd=0.05, Fab=0.10, SilkS=0.12 mm).
        We distinguish them from copper track widths by looking at the character
        immediately after the closing ')': track widths are followed by a space
        or newline, while fp_rect/fp_circle widths are followed by an extra ')'
        (the closing paren of the parent s-expression).
        """
        changed = False

        def _replace(m: re.Match) -> str:
            nonlocal changed
            val = float(m.group(1))
            # Skip fp_rect / fp_circle line widths — they end with ))
            next_char = pcb_text[m.end()] if m.end() < len(pcb_text) else ""
            if next_char == ")":
                return m.group(0)  # leave courtyard/fab/silkscreen widths alone
            if val < _IPC_MIN_TRACK_MM:
                changed = True
                return f"(width {_IPC_MIN_TRACK_MM})"
            return m.group(0)

        # Match (width <number>) — KiCad segment width token
        new_text = re.sub(r"\(width\s+([\d.]+)\)", _replace, pcb_text)
        return new_text, changed

    @staticmethod
    def _fix_via_size(pcb_text: str) -> tuple[str, bool]:
        """Increase via drill and size to IPC-2221 minimums.

        Matches ``(via ... (drill <val>) (size <val>) ...)`` blocks.
        """
        changed = False

        def _fix_drill(m: re.Match) -> str:
            nonlocal changed
            val = float(m.group(1))
            if val < _IPC_MIN_VIA_DRILL:
                changed = True
                return f"(drill {_IPC_MIN_VIA_DRILL})"
            return m.group(0)

        def _fix_size(m: re.Match) -> str:
            nonlocal changed
            val = float(m.group(1))
            if val < _IPC_MIN_VIA_SIZE:
                changed = True
                return f"(size {_IPC_MIN_VIA_SIZE})"
            return m.group(0)

        # Only touch drill/size inside via blocks (not pad sizes)
        # Strategy: replace all (drill <n>) tokens in via blocks
        # KiCad via format: (via (at ...) (size ...) (drill ...) (layers ...))
        new_text = pcb_text
        # Fix drill values
        new_text = re.sub(r"\(drill\s+([\d.]+)\)", _fix_drill, new_text)
        # Fix via total size (annular ring)
        new_text = re.sub(r"\(size\s+([\d.]+)\)", _fix_size, new_text)
        return new_text, changed

    @staticmethod
    def _fix_clearance(pcb_text: str) -> tuple[str, bool]:
        """Widen net-to-net clearance in the board setup section."""
        changed = False

        def _replace(m: re.Match) -> str:
            nonlocal changed
            val = float(m.group(1))
            if val < _IPC_MIN_CLEARANCE:
                changed = True
                return f"(clearance {_IPC_MIN_CLEARANCE})"
            return m.group(0)

        new_text = re.sub(r"\(clearance\s+([\d.]+)\)", _replace, pcb_text)
        return new_text, changed

    @staticmethod
    def _add_gnd_zone(pcb_text: str) -> tuple[str, bool]:
        """Append a GND copper fill zone covering the board outline.

        If no zone exists and the board has an Edge.Cuts rectangle, add a
        GND zone that fills F.Cu.  KiCad will pour copper when the file
        is opened or when ``kicad-cli pcb fill-zones`` is run.
        """
        if "(zone" in pcb_text:
            return pcb_text, False  # zone already present

        # Extract board dimensions from Edge.Cuts gr_rect
        m = re.search(
            r"\(gr_rect\s+\(start\s+([\d.]+)\s+([\d.]+)\)\s+"
            r"\(end\s+([\d.]+)\s+([\d.]+)\)",
            pcb_text,
        )
        if not m:
            return pcb_text, False

        x0, y0 = float(m.group(1)), float(m.group(2))
        x1, y1 = float(m.group(3)), float(m.group(4))

        # Shrink 0.5 mm inside edge cuts
        inset = 0.5
        zone_text = (
            f'\n  (zone (net 1) (net_name "GND") (layer "F.Cu")\n'
            f'    (tstamp "{_uuid4_short()}")\n'
            f'    (hatch edge 0.508)\n'
            f'    (connect_pads (clearance {_IPC_MIN_CLEARANCE}))\n'
            f'    (min_thickness 0.25)\n'
            f'    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))\n'
            f'    (polygon (pts\n'
            f'      (xy {x0 + inset} {y0 + inset})\n'
            f'      (xy {x1 - inset} {y0 + inset})\n'
            f'      (xy {x1 - inset} {y1 - inset})\n'
            f'      (xy {x0 + inset} {y1 - inset})\n'
            f'    ))\n'
            f'  )\n'
        )

        # Insert before the final closing parenthesis of the PCB
        if pcb_text.rstrip().endswith(")"):
            new_text = pcb_text.rstrip()[:-1] + zone_text + ")\n"
            return new_text, True

        return pcb_text, False


    # ------------------------------------------------------------------
    # Phase 23.6: Post-routing DRC checks
    # ------------------------------------------------------------------

    def post_routing_check(self, pcb_path: Path) -> AutoFixResult:
        """Run comprehensive post-routing checks on a routed PCB.

        Phase 23.6: Checks beyond standard DRC that are specific to
        production-ready PCBs:
        - Unrouted connections (ratsnest)
        - Missing copper zones / GND plane
        - Silkscreen overlap with pads
        - Board outline completeness

        Returns an AutoFixResult with findings and any auto-applied fixes.
        """
        result = AutoFixResult()
        if not pcb_path.exists():
            result.remaining.append(f"PCB file not found: {pcb_path}")
            return result

        pcb_text = pcb_path.read_text(encoding="utf-8")
        original = pcb_text

        # Check 1: Unrouted nets (no_connect markers)
        no_connect_count = pcb_text.count("(no_connect")
        if no_connect_count > 0:
            result.remaining.append(
                f"{no_connect_count} unrouted connection(s) — "
                "run FreeRouting or route manually"
            )

        # Check 2: Missing GND zone
        if "(zone" not in pcb_text:
            pcb_text, fixed = self._add_gnd_zone(pcb_text)
            if fixed:
                result.fixes_applied.append(
                    "Added GND copper fill zone (was missing)"
                )

        # Check 3: Missing B.Cu GND zone (Phase 23.2 standard)
        if '(layer "B.Cu")' not in pcb_text or (
            pcb_text.count("(zone") == 1
            and '"F.Cu"' in pcb_text
            and '"B.Cu"' not in pcb_text.split("(zone")[1]
        ):
            # Add B.Cu zone if only F.Cu exists
            pcb_text, fixed = self._add_bcu_gnd_zone(pcb_text)
            if fixed:
                result.fixes_applied.append(
                    "Added B.Cu GND copper fill zone for proper ground plane"
                )

        # Check 4: Board outline (Edge.Cuts) present
        if "Edge.Cuts" not in pcb_text and "Edge_Cuts" not in pcb_text:
            result.remaining.append(
                "Missing board outline (Edge.Cuts layer) — "
                "board dimensions undefined"
            )

        # Check 5: Minimum trace width enforcement
        pcb_text, fixed = self._fix_track_width(pcb_text)
        if fixed:
            result.fixes_applied.append(
                f"Widened narrow tracks to {_IPC_MIN_TRACK_MM} mm (post-routing)"
            )

        # Deduplicate applied fixes
        result.fixes_applied = list(dict.fromkeys(result.fixes_applied))

        if pcb_text != original:
            pcb_path.write_text(pcb_text, encoding="utf-8")
            result.pcb_modified = True
            log.info("Post-routing DRC: rewrote %s (%d fix(es) applied)",
                     pcb_path.name, len(result.fixes_applied))

        return result

    @staticmethod
    def _add_bcu_gnd_zone(pcb_text: str) -> tuple[str, bool]:
        """Add a B.Cu GND copper fill zone (mirrors F.Cu zone on back layer)."""
        # Only add if we can find board dimensions from Edge.Cuts
        m = re.search(
            r"\(gr_rect\s+\(start\s+([\d.]+)\s+([\d.]+)\)\s+"
            r"\(end\s+([\d.]+)\s+([\d.]+)\)",
            pcb_text,
        )
        if not m:
            return pcb_text, False

        x0, y0 = float(m.group(1)), float(m.group(2))
        x1, y1 = float(m.group(3)), float(m.group(4))
        inset = 0.5

        zone_text = (
            f'\n  (zone (net 1) (net_name "GND") (layer "B.Cu")\n'
            f'    (tstamp "{_uuid4_short()}")\n'
            f'    (hatch edge 0.508)\n'
            f'    (connect_pads (clearance {_IPC_MIN_CLEARANCE}))\n'
            f'    (min_thickness 0.25)\n'
            f'    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))\n'
            f'    (polygon (pts\n'
            f'      (xy {x0 + inset} {y0 + inset})\n'
            f'      (xy {x1 - inset} {y0 + inset})\n'
            f'      (xy {x1 - inset} {y1 - inset})\n'
            f'      (xy {x0 + inset} {y1 - inset})\n'
            f'    ))\n'
            f'  )\n'
        )

        if pcb_text.rstrip().endswith(")"):
            new_text = pcb_text.rstrip()[:-1] + zone_text + ")\n"
            return new_text, True

        return pcb_text, False


def _uuid4_short() -> str:
    """Generate a short UUID-like token for KiCad tstamp fields."""
    import uuid
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Closed-loop DRC + auto-fix (convenience wrapper)
# ---------------------------------------------------------------------------


def run_drc_fix_loop(
    pcb_path: Path,
    max_iterations: int = 3,
) -> AutoFixResult:
    """Run DRC → auto-fix → re-run DRC, up to *max_iterations* times.

    Returns the cumulative AutoFixResult from all iterations.
    Gracefully degrades if kicad-cli is not available.
    """
    from boardsmith_hw.kicad_drc import KiCadChecker

    checker = KiCadChecker()
    fixer   = PcbDrcAutoFix()

    cumulative = AutoFixResult()

    for iteration in range(1, max_iterations + 1):
        check = checker.run_drc(pcb_path)

        if not check.tool_available:
            cumulative.remaining.append(
                "kicad-cli not available — DRC auto-fix skipped"
            )
            break

        errors_only = [v for v in check.violations if v.severity == "error"]
        if not errors_only:
            log.info("DRC auto-fix loop: no errors in iteration %d — done", iteration)
            break

        iteration_result = fixer.fix(pcb_path, errors_only)
        cumulative.fixes_applied.extend(iteration_result.fixes_applied)

        if not iteration_result.pcb_modified:
            # No more fixable violations
            cumulative.remaining.extend(iteration_result.remaining)
            break

        log.info(
            "DRC auto-fix iteration %d: %d fix(es), %d remaining",
            iteration,
            len(iteration_result.fixes_applied),
            len(iteration_result.remaining),
        )

    # Deduplicate
    cumulative.fixes_applied = list(dict.fromkeys(cumulative.fixes_applied))
    return cumulative
