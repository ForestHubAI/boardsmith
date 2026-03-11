# SPDX-License-Identifier: AGPL-3.0-or-later
"""Eagle netlist text-format parser (fallback when .sch is not available).

Expected format (Eagle "Export → Netlist"):
    Part <name> <value> <package> <library>
    Net  <name> <part>.<pin> <part>.<pin> ...
"""

from __future__ import annotations

from pathlib import Path

from boardsmith_fw.models.hardware_graph import Component, Net, NetPin, Pin, PinDirection

_POWER_NAMES = {"GND", "VCC", "VDD", "3V3", "5V"}


def parse_eagle_netlist(path: Path):
    """Parse a plain-text Eagle netlist export."""
    lines = [
        ln.strip()
        for ln in path.read_text().splitlines()
        if ln.strip() and not ln.strip().startswith("*")
    ]

    components: list[Component] = []
    nets: list[Net] = []
    comp_map: dict[str, Component] = {}
    warnings: list[str] = []

    section = ""

    for line in lines:
        if line.startswith("Partlist") or line.startswith("Part "):
            section = "parts"
            if line.startswith("Part "):
                continue
            continue
        if line.startswith("Netlist") or line.startswith("Net "):
            section = "nets"
            if line.startswith("Net "):
                continue
            continue
        if line.startswith("---") or line.startswith("==="):
            continue

        if section == "parts":
            tokens = line.split()
            if len(tokens) >= 2:
                comp = Component(
                    id=tokens[0],
                    name=tokens[0],
                    value=tokens[1] if len(tokens) > 1 else "",
                    package=tokens[2] if len(tokens) > 2 else "",
                    library=tokens[3] if len(tokens) > 3 else "",
                )
                components.append(comp)
                comp_map[comp.id] = comp

        elif section == "nets":
            tokens = line.split()
            if len(tokens) >= 2:
                net_name = tokens[0]
                pin_refs: list[NetPin] = []
                is_power = net_name.upper() in _POWER_NAMES or net_name.startswith("+")

                for ref in tokens[1:]:
                    dot = ref.rfind(".")
                    if dot > 0:
                        comp_id = ref[:dot]
                        pin_name = ref[dot + 1 :]
                        pin_refs.append(NetPin(component_id=comp_id, pin_name=pin_name))

                        comp = comp_map.get(comp_id)
                        if comp and not any(p.name == pin_name for p in comp.pins):
                            comp.pins.append(Pin(
                                name=pin_name,
                                number=pin_name,
                                direction=PinDirection.UNKNOWN,
                                net=net_name,
                            ))

                nets.append(Net(name=net_name, pins=pin_refs, is_power=is_power))

    from boardsmith_fw.parser.eagle_parser import ParseResult

    return ParseResult(components=components, nets=nets, warnings=warnings)
