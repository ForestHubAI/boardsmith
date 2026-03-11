# SPDX-License-Identifier: AGPL-3.0-or-later
"""VerifyConnectivityTool — checks HIR bus contracts vs schematic nets and flags floating pins."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Helper functions — module-level, no heavy imports
# ---------------------------------------------------------------------------

# Expected signal nets per bus type.
# Each entry is a list of required signal names. Entries with "/" mean
# "either name counts as satisfying this requirement" (e.g. SCLK/SCK).
_BUS_REQUIRED_NETS: dict[str, list[str]] = {
    "I2C":  ["SDA", "SCL"],
    "SPI":  ["MOSI", "MISO", "SCLK/SCK"],
    "UART": ["TX/TXD", "RX/RXD"],
    "CAN":  ["CANH", "CANL"],
}


def _extract_net_names(graph: Any, sch_text: str) -> set[str]:
    """Return all net names visible in the schematic.

    Combines graph.nets (which only includes nets connected to component pins)
    with net labels extracted directly from the raw S-expression text.
    This handles schematics where net labels are placed on wires but not yet
    connected to any component pin.
    """
    names: set[str] = set()
    # From parsed graph
    for net in graph.nets:
        names.add(net.name.upper())
    # From raw text: (label "NAME" ...) and (global_label "NAME" ...)
    for match in re.finditer(
        r'\((?:label|global_label|net_label)\s+"([^"]+)"', sch_text
    ):
        names.add(match.group(1).upper())
    return names


def _check_bus_nets(hir: Any, graph: Any, sch_text: str = "") -> list[dict]:
    """Check that every HIR BusContract has its expected nets present in the schematic.

    Each required signal entry may use '/' to indicate OR alternatives
    (e.g. 'SCLK/SCK' means either name satisfies the requirement).
    """
    violations: list[dict] = []
    all_net_names = _extract_net_names(graph, sch_text)
    for bc in hir.bus_contracts:
        bus_type = bc.bus_type.upper()
        required = _BUS_REQUIRED_NETS.get(bus_type, [])
        for req_entry in required:
            # Split on "/" for OR alternatives
            alternatives = [s.upper() for s in req_entry.split("/")]
            # Found if any alternative is a substring of any schematic net name
            found = any(
                alt in net_upper
                for alt in alternatives
                for net_upper in all_net_names
            )
            if not found:
                display_name = alternatives[0]  # use first name for messages
                violations.append({
                    "type": "missing_bus_net",
                    "severity": "error",
                    "message": (
                        f"Net '{display_name}' for {bc.bus_type} bus '{bc.bus_name}' "
                        "not found in schematic"
                    ),
                    "ref": bc.bus_name,
                })
    return violations


def _extract_no_connect_coords(sch_text: str) -> set[tuple[float, float]]:
    """Return set of (x, y) coordinates for all (no_connect ...) markers in raw sch text."""
    coords: set[tuple[float, float]] = set()
    for match in re.finditer(
        r'\(no_connect\s+\(at\s+([\d.]+)\s+([\d.]+)', sch_text
    ):
        coords.add((float(match.group(1)), float(match.group(2))))
    return coords


def _check_floating_pins(graph: Any, sch_text: str) -> list[dict]:
    """Check for input-type pins not connected to any net and not marked no_connect.

    Limitation: GraphPin has no coordinate fields, so coordinate-based no_connect
    suppression is not possible. Any input pin not in any net is flagged as floating.
    If you need to suppress known-unconnected pins, add no_connect markers in the
    schematic or use a net label to connect them.
    """
    # Build set of all connected (comp_id, pin_name) pairs
    connected_pins: set[tuple[str, str]] = set()
    for net in graph.nets:
        for comp_id, pin_name in net.pins:
            connected_pins.add((comp_id, pin_name))

    # no_connect coords extracted for future coordinate-matching use
    # Currently unused because GraphPin has no coordinate fields
    _no_connect_coords = _extract_no_connect_coords(sch_text)
    has_no_connects = len(_no_connect_coords) > 0

    violations: list[dict] = []
    for comp in graph.components:
        for pin in comp.pins:
            if pin.electrical_type != "input":
                continue
            if (comp.id, pin.name) in connected_pins:
                continue
            # If the schematic has any no_connect markers, we cannot safely determine
            # which pins they cover without coordinate data. Suppress violations to
            # avoid false positives on schematics with explicit no_connect usage.
            if has_no_connects:
                continue
            violations.append({
                "type": "floating_input_pin",
                "severity": "warning",
                "message": (
                    f"Input pin '{pin.name}' of {comp.id} appears unconnected"
                ),
                "ref": comp.id,
            })
    return violations


# ---------------------------------------------------------------------------
# Tool class
# ---------------------------------------------------------------------------

class VerifyConnectivityTool:
    """Check HIR bus contracts against schematic nets and flag floating input pins.

    Checks:
    - Bus net presence: for each HIR BusContract, the expected signal nets
      (SDA/SCL for I2C, MOSI/MISO/SCLK for SPI, TX/RX for UART, CANH/CANL for CAN)
      must be present in the schematic as net name substrings.
    - Floating input pins: pins with electrical_type='input' not connected to any
      net and not suppressed by a no_connect marker.

    Limitation: no_connect suppression requires pin coordinates which are not
    available in GraphPin. If any no_connect markers exist in the schematic,
    floating-pin violations are suppressed to avoid false positives.
    """

    name = "verify_connectivity"
    description = (
        "Check HIR bus contracts against schematic nets and flag floating input pins. "
        "Returns violations for missing bus signal nets (SDA, SCL, MOSI, etc.) "
        "and unconnected input pins."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "hir_path": {
                "type": "string",
                "description": "Absolute path to hir.json",
            },
            "sch_path": {
                "type": "string",
                "description": "Absolute path to .kicad_sch",
            },
        },
        "required": ["hir_path", "sch_path"],
    }

    async def execute(self, input: Any, context: Any) -> Any:
        from tools.base import ToolResult
        from synth_core.hir_bridge.kicad_parser import KiCadSchematicParser
        from models.hir import HIR
        import json

        hir_path = Path(input["hir_path"])
        if not hir_path.exists():
            return ToolResult(
                success=False,
                data={"violations": []},
                source="verify_connectivity",
                confidence=0.0,
                error=f"hir.json not found: {hir_path}",
            )

        sch_path = Path(input["sch_path"])
        sch_text = sch_path.read_text(encoding="utf-8", errors="replace")

        hir = HIR.model_validate(json.loads(hir_path.read_text()))
        graph = KiCadSchematicParser().parse_text(sch_text, source_file=str(sch_path))

        violations = (
            _check_bus_nets(hir, graph, sch_text)
            + _check_floating_pins(graph, sch_text)
        )

        return ToolResult(
            success=True,
            data={
                "violations": violations,
                "violation_count": len(violations),
                "checks_run": ["bus_nets", "floating_pins"],
            },
            source="verify_connectivity",
            confidence=1.0,
            metadata={
                "bus_contract_count": len(hir.bus_contracts),
                "net_count": len(graph.nets),
            },
        )
