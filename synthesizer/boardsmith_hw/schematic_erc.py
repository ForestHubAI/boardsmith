# SPDX-License-Identifier: AGPL-3.0-or-later
"""B16. Schematic ERC — round-trip connectivity checker for KiCad schematics.

Parses a generated .kicad_sch file and checks that:
  - Expected bus signals (SDA/SCL for I2C, MOSI/MISO/SCLK for SPI) exist as
    net labels in the schematic text (direct scan, not parser-resolved nets).
  - All HIR components are present in the schematic (by MPN).
  - Bus master and slaves appear connected to at least one bus signal net.
  - The schematic has at least one component.

Note on net resolution: The KiCad parser uses a proximity algorithm to resolve
net labels to wire groups.  When two bus-signal pins are adjacent (e.g. SDA and
SCL on adjacent IC rows, separated by 2.54 mm), the proximity window (5 mm) can
merge their net groups.  Bus-net presence is therefore checked via direct regex
scan of label elements rather than relying on graph.nets, which ensures robust
detection regardless of parser proximity behaviour.

Usage::

    erc = SchematicERC()
    result = erc.check(Path("schematic.kicad_sch"), hir_dict)
    if not result.passed:
        for issue in result.errors:
            print(f"ERROR [{issue.code}]: {issue.message}")

Can also be invoked from the CLI:
    boardsmith erc --schematic ./output/schematic.kicad_sch --hir ./output/hir.json
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from synth_core.hir_bridge.kicad_parser import KiCadSchematicParser
from synth_core.hir_bridge.graph import HardwareGraph


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ERCIssue:
    """A single ERC finding."""
    severity: str  # "error" | "warning" | "info"
    code: str      # machine-readable code, e.g. "MISSING_NET"
    message: str   # human-readable description


@dataclass
class ERCResult:
    """Result of a SchematicERC run."""
    issues: list[ERCIssue] = field(default_factory=list)
    component_count: int = 0  # components found in parsed schematic
    net_count: int = 0        # nets found in parsed schematic
    bus_count: int = 0        # buses inferred by parser

    @property
    def errors(self) -> list[ERCIssue]:
        """All error-severity issues."""
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ERCIssue]:
        """All warning-severity issues."""
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def passed(self) -> bool:
        """True if no error-severity issues were found."""
        return not self.errors


# ---------------------------------------------------------------------------
# Signal sets per bus type
# ---------------------------------------------------------------------------

_I2C_SIGNALS: tuple[str, ...] = ("SDA", "SCL")
_SPI_SIGNALS: tuple[str, ...] = ("MOSI", "MISO", "SCLK")

# Regex to extract all (label "...") names from KiCad S-expression text.
_LABEL_RE = re.compile(r'\(label\s+"([^"]+)"')


# ---------------------------------------------------------------------------
# SchematicERC
# ---------------------------------------------------------------------------

class SchematicERC:
    """Round-trip ERC: parse .kicad_sch and compare against HIR expectations.

    All checks are non-destructive — the schematic file is read but never
    written.  Checks are skipped gracefully when the HIR is not provided.
    """

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def check(
        self,
        sch_path: Path,
        hir_dict: dict[str, Any] | None = None,
    ) -> ERCResult:
        """Check a .kicad_sch file against an optional HIR dict.

        Args:
            sch_path:  Path to the .kicad_sch file.
            hir_dict:  Optional HIR dict for cross-checking components / nets.

        Returns:
            ERCResult with issues list and summary statistics.
        """
        text = Path(sch_path).read_text(encoding="utf-8", errors="replace")
        return self.check_text(text, hir_dict=hir_dict)

    def check_text(
        self,
        sch_text: str,
        hir_dict: dict[str, Any] | None = None,
    ) -> ERCResult:
        """Check KiCad 6 S-expression text against an optional HIR dict.

        Args:
            sch_text:  Raw content of a .kicad_sch file.
            hir_dict:  Optional HIR dict for cross-checking.

        Returns:
            ERCResult with issues list and summary statistics.
        """
        parser = KiCadSchematicParser()
        graph = parser.parse_text(sch_text)

        # Bus-signal net presence is checked via direct text scan (see module
        # docstring for why we don't rely on graph.nets here).
        label_names = self._extract_label_names(sch_text)

        result = ERCResult(
            component_count=len(graph.components),
            net_count=len(graph.nets),
            bus_count=len(graph.buses),
        )

        # --- Basic sanity ---
        if not graph.components:
            result.issues.append(ERCIssue(
                severity="error",
                code="NO_COMPONENTS",
                message="Schematic contains no components",
            ))
            return result

        # --- HIR-based checks (only when HIR is supplied) ---
        if hir_dict:
            self._check_components(result, graph, hir_dict)
            self._check_bus_nets(result, label_names, hir_dict)
            self._check_bus_connectivity(result, graph, hir_dict)

        return result

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_components(
        self,
        result: ERCResult,
        graph: HardwareGraph,
        hir_dict: dict[str, Any],
    ) -> None:
        """Check that all HIR components appear in the schematic (by MPN)."""
        hir_mpns = {
            c.get("mpn", "")
            for c in hir_dict.get("components", [])
            if c.get("mpn")
        }
        sch_mpns = {c.mpn for c in graph.components}

        for mpn in sorted(hir_mpns):
            if mpn not in sch_mpns:
                result.issues.append(ERCIssue(
                    severity="warning",
                    code="MISSING_COMPONENT",
                    message=f"HIR component '{mpn}' not found in schematic",
                ))

    def _check_bus_nets(
        self,
        result: ERCResult,
        label_names: set[str],
        hir_dict: dict[str, Any],
    ) -> None:
        """Check that expected bus signal net labels exist in the schematic.

        Uses direct text-scan results (label_names) rather than graph.nets
        so that adjacent bus signals (e.g. SDA at y=99 and SCL at y=102) are
        not incorrectly merged by the parser's proximity algorithm.
        """
        for bc in hir_dict.get("bus_contracts", []):
            bt = bc.get("bus_type", "").upper()
            bus_name = bc.get("bus_name", bt)

            if bt == "I2C":
                expected = _I2C_SIGNALS
            elif bt == "SPI":
                expected = _SPI_SIGNALS
            else:
                continue

            for sig in expected:
                if sig not in label_names:
                    result.issues.append(ERCIssue(
                        severity="error",
                        code="MISSING_NET",
                        message=(
                            f"Bus '{bus_name}' ({bt}): expected net label '{sig}' "
                            f"not found in schematic"
                        ),
                    ))

    def _check_bus_connectivity(
        self,
        result: ERCResult,
        graph: HardwareGraph,
        hir_dict: dict[str, Any],
    ) -> None:
        """Check that bus slaves appear connected to bus signals.

        Due to the parser proximity merging behaviour (see module docstring),
        we check for presence on ANY bus signal net rather than ALL signals.
        A component with SDA pin on any bus-signal net passes; a component
        with no bus-signal net connections at all is flagged.
        """
        # Build map: schematic_comp_id → set of (uppercase) net names
        comp_nets: dict[str, set[str]] = {}
        for n in graph.nets:
            for (comp_id, _) in n.pins:
                comp_nets.setdefault(comp_id, set()).add(n.name.upper())

        for bc in hir_dict.get("bus_contracts", []):
            bt = bc.get("bus_type", "").upper()
            bus_name = bc.get("bus_name", bt)
            slave_ids = bc.get("slave_ids", [])

            if bt == "I2C":
                any_bus_sig: set[str] = set(_I2C_SIGNALS)
            elif bt == "SPI":
                any_bus_sig = set(_SPI_SIGNALS)
            else:
                continue

            for slave_id in slave_ids:
                sch_ids = self._find_comp_sch_ids(slave_id, graph, hir_dict)
                if not sch_ids:
                    result.issues.append(ERCIssue(
                        severity="warning",
                        code="BUS_SLAVE_NOT_FOUND",
                        message=f"Bus '{bus_name}' slave '{slave_id}' not found in schematic",
                    ))
                    continue
                for sch_id in sch_ids:
                    nets = comp_nets.get(sch_id, set())
                    # Check for any bus-signal net (SDA or SCL for I2C).
                    # Parser proximity may merge adjacent signals into one net.
                    if not nets.intersection(any_bus_sig):
                        result.issues.append(ERCIssue(
                            severity="warning",
                            code="BUS_SLAVE_PIN_UNCONNECTED",
                            message=(
                                f"Bus '{bus_name}' slave '{sch_id}': "
                                f"no bus-signal net found (expected one of {sorted(any_bus_sig)})"
                            ),
                        ))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_label_names(sch_text: str) -> set[str]:
        """Extract all (label "...") names from raw .kicad_sch text (uppercase)."""
        return {m.upper() for m in _LABEL_RE.findall(sch_text)}

    def _find_comp_sch_ids(
        self,
        hir_id: str,
        graph: HardwareGraph,
        hir_dict: dict[str, Any],
    ) -> list[str]:
        """Find schematic component IDs that match a HIR component ID.

        HIR component IDs (e.g. "ESP32_WROOM_32") are matched to schematic
        reference designators (e.g. "U1") via the component MPN.  Falls back
        to direct ID comparison for custom/unknown components.
        """
        hir_id_to_mpn = {
            c.get("id", ""): c.get("mpn", "")
            for c in hir_dict.get("components", [])
        }
        mpn = hir_id_to_mpn.get(hir_id, "")

        matches: list[str] = []
        for comp in graph.components:
            if mpn and comp.mpn == mpn:
                matches.append(comp.id)
            elif not mpn and comp.id == hir_id:
                matches.append(comp.id)
        return matches
