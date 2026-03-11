# SPDX-License-Identifier: AGPL-3.0-or-later
"""Eagle .sch XML parser — deterministic, no LLM.

Parses Eagle .sch files (XML, version 6+/7+/9+) into Component/Net lists.
Uses lxml for robust XML handling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from boardsmith_fw.models.hardware_graph import Component, Net, NetPin, Pin, PinDirection


@dataclass
class ParseResult:
    components: list[Component] = field(default_factory=list)
    nets: list[Net] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_PIN_DIR_MAP: dict[str | None, PinDirection] = {
    "in": PinDirection.INPUT,
    "out": PinDirection.OUTPUT,
    "io": PinDirection.BIDIRECTIONAL,
    "pwr": PinDirection.POWER,
    "sup": PinDirection.POWER,
    "pas": PinDirection.PASSIVE,
}

_POWER_NET_NAMES = {"GND", "VCC", "VDD", "3V3", "5V", "VBAT"}


def parse_eagle_schematic(path: Path) -> ParseResult:
    """Parse an Eagle .sch XML file and return components + nets."""
    tree = etree.parse(str(path))
    root = tree.getroot()

    if root.tag != "eagle":
        raise ValueError("Not a valid Eagle file: missing <eagle> root element")

    schematic = root.find(".//schematic")
    if schematic is None:
        raise ValueError("Not a valid Eagle file: missing <schematic> element")

    warnings: list[str] = []
    pin_lookup = _build_pin_lookup(schematic, warnings)
    components = _parse_parts(schematic, pin_lookup, warnings)
    comp_map = {c.id: c for c in components}
    nets = _parse_nets(schematic, comp_map, warnings)

    return ParseResult(components=components, nets=nets, warnings=warnings)


# ---------------------------------------------------------------------------
# Pin lookup from libraries
# ---------------------------------------------------------------------------

def _build_pin_lookup(
    schematic: etree._Element, warnings: list[str]
) -> dict[str, list[Pin]]:
    """Build a lookup: 'lib::deviceset::device' → list[Pin]."""
    lookup: dict[str, list[Pin]] = {}

    for lib in schematic.iterfind(".//libraries/library"):
        lib_name = lib.get("name", "")
        symbols: dict[str, etree._Element] = {
            s.get("name", ""): s for s in lib.iterfind("symbols/symbol")
        }

        for ds in lib.iterfind("devicesets/deviceset"):
            ds_name = ds.get("name", "")

            # Gather pins from symbol(s) via gates
            all_pins: list[Pin] = []
            for gate in ds.iterfind("gates/gate"):
                sym_name = gate.get("symbol", "")
                symbol = symbols.get(sym_name)
                if symbol is None:
                    continue
                for pin_el in symbol.iterfind("pin"):
                    name = pin_el.get("name", "")
                    direction = _PIN_DIR_MAP.get(pin_el.get("direction"), PinDirection.UNKNOWN)
                    all_pins.append(Pin(
                        name=name,
                        number=name,
                        direction=direction,
                        electrical_type=pin_el.get("direction", "unknown"),
                    ))

            # Resolve physical pad numbers from device/connect
            for device in ds.iterfind("devices/device"):
                dev_name = device.get("name", "")
                connects = {
                    c.get("pin", ""): c.get("pad", "")
                    for c in device.iterfind("connects/connect")
                }
                resolved = [
                    pin.model_copy(update={"number": connects.get(pin.name, pin.number)})
                    for pin in all_pins
                ]
                lookup[f"{lib_name}::{ds_name}::{dev_name}"] = resolved

            # Fallback without device variant
            lookup[f"{lib_name}::{ds_name}"] = all_pins

    return lookup


# ---------------------------------------------------------------------------
# Parts
# ---------------------------------------------------------------------------

def _parse_parts(
    schematic: etree._Element,
    pin_lookup: dict[str, list[Pin]],
    warnings: list[str],
) -> list[Component]:
    components: list[Component] = []

    for part in schematic.iterfind(".//parts/part"):
        name = part.get("name", "")
        value = part.get("value", "")
        library = part.get("library", "")
        deviceset = part.get("deviceset", "")
        device = part.get("device", "")

        key = f"{library}::{deviceset}::{device}"
        fallback = f"{library}::{deviceset}"
        pins = pin_lookup.get(key) or pin_lookup.get(fallback) or []
        if not pins:
            warnings.append(f"Could not resolve pins for part {name} ({key})")

        # Deep-copy pins so each component gets its own mutable list
        pins = [p.model_copy() for p in pins]

        attrs: dict[str, str] = {}
        for attr in part.iterfind("attribute"):
            a_name = attr.get("name", "")
            a_value = attr.get("value", "")
            if a_name:
                attrs[a_name] = a_value

        components.append(Component(
            id=name,
            name=name,
            value=value or deviceset,
            package=device,
            library=library,
            deviceset=deviceset,
            manufacturer=attrs.get("MANUFACTURER", attrs.get("MFR", "")),
            mpn=attrs.get("MPN", attrs.get("PARTNUMBER", value or deviceset)),
            pins=pins,
            attributes=attrs,
        ))

    return components


# ---------------------------------------------------------------------------
# Nets
# ---------------------------------------------------------------------------

def _is_power_net(name: str) -> bool:
    upper = name.upper()
    if upper in _POWER_NET_NAMES:
        return True
    if upper.startswith("+") or upper.startswith("V"):
        return True
    return False


def _parse_nets(
    schematic: etree._Element,
    comp_map: dict[str, Component],
    warnings: list[str],
) -> list[Net]:
    net_map: dict[str, Net] = {}

    for sheet in schematic.iterfind(".//sheets/sheet"):
        for net_el in sheet.iterfind("nets/net"):
            net_name = net_el.get("name", "")
            if net_name not in net_map:
                net_map[net_name] = Net(
                    name=net_name,
                    is_power=_is_power_net(net_name),
                )
            net = net_map[net_name]

            for segment in net_el.iterfind("segment"):
                for pr in segment.iterfind("pinref"):
                    part_name = pr.get("part", "")
                    pin_name = pr.get("pin", "")
                    net.pins.append(NetPin(component_id=part_name, pin_name=pin_name))

                    # Update component pin → net assignment
                    comp = comp_map.get(part_name)
                    if comp:
                        for pin in comp.pins:
                            if pin.name == pin_name:
                                pin.net = net_name

    return list(net_map.values())
