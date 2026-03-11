# SPDX-License-Identifier: AGPL-3.0-or-later
"""HardwareGraph — in-memory representation of a parsed schematic or design."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraphPin:
    name: str
    number: str = ""
    function: str = ""
    electrical_type: str = ""


@dataclass
class GraphComponent:
    id: str
    name: str
    mpn: str
    role: str = "other"           # mcu, sensor, actuator, memory, power, comms, other
    manufacturer: str = ""
    package: str = ""
    interface_types: list[str] = field(default_factory=list)
    pins: list[GraphPin] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphNet:
    name: str
    pins: list[tuple[str, str]] = field(default_factory=list)  # (component_id, pin_name)
    is_power: bool = False
    is_bus: bool = False


@dataclass
class GraphBus:
    name: str
    type: str                     # I2C, SPI, UART, ...
    master_id: str = ""
    slave_ids: list[str] = field(default_factory=list)
    net_names: list[str] = field(default_factory=list)
    pin_assignments: dict[str, str] = field(default_factory=dict)  # signal -> gpio


@dataclass
class HardwareGraph:
    """Parsed schematic topology — input to HIR builder."""
    components: list[GraphComponent] = field(default_factory=list)
    nets: list[GraphNet] = field(default_factory=list)
    buses: list[GraphBus] = field(default_factory=list)
    source_file: str = ""

    def get_component(self, cid: str) -> GraphComponent | None:
        for c in self.components:
            if c.id == cid:
                return c
        return None

    def get_nets_for_component(self, cid: str) -> list[GraphNet]:
        return [n for n in self.nets if any(p[0] == cid for p in n.pins)]

    def get_buses_for_component(self, cid: str) -> list[GraphBus]:
        return [b for b in self.buses if b.master_id == cid or cid in b.slave_ids]

    @classmethod
    def from_dict(cls, data: dict) -> "HardwareGraph":
        """Deserialize from JSON dict (for testing / import)."""
        g = cls(source_file=data.get("source_file", ""))
        for c in data.get("components", []):
            pins = [GraphPin(**p) for p in c.get("pins", [])]
            g.components.append(GraphComponent(
                id=c["id"], name=c["name"], mpn=c.get("mpn", ""),
                role=c.get("role", "other"), manufacturer=c.get("manufacturer", ""),
                package=c.get("package", ""), interface_types=c.get("interface_types", []),
                pins=pins, properties=c.get("properties", {}),
            ))
        for n in data.get("nets", []):
            pins = [(p["component_id"], p["pin_name"]) for p in n.get("pins", [])]
            g.nets.append(GraphNet(
                name=n["name"], pins=pins,
                is_power=n.get("is_power", False), is_bus=n.get("is_bus", False),
            ))
        for b in data.get("buses", []):
            g.buses.append(GraphBus(
                name=b["name"], type=b["type"],
                master_id=b.get("master_id", ""), slave_ids=b.get("slave_ids", []),
                net_names=b.get("net_names", []), pin_assignments=b.get("pin_assignments", {}),
            ))
        return g
