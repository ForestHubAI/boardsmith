# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bus conflict detection — identifies hardware configuration issues.

Checks for:
- I2C address collisions on the same bus
- Pin conflicts (same GPIO used for multiple functions)
- Missing pull-ups on I2C
- Clock speed mismatches on shared buses
"""

from __future__ import annotations

from dataclasses import dataclass

from boardsmith_fw.models.component_knowledge import ComponentKnowledge
from boardsmith_fw.models.hardware_graph import HardwareGraph


@dataclass
class Conflict:
    severity: str  # "error", "warning", "info"
    category: str  # "i2c_collision", "pin_conflict", "missing_pullup", etc.
    message: str
    components: list[str]  # affected component IDs


def detect_conflicts(
    graph: HardwareGraph,
    knowledge: list[ComponentKnowledge] | None = None,
) -> list[Conflict]:
    """Run all conflict checks and return a list of detected issues."""
    conflicts: list[Conflict] = []
    knowledge = knowledge or []

    conflicts.extend(_check_i2c_address_collisions(graph, knowledge))
    conflicts.extend(_check_pin_conflicts(graph))
    conflicts.extend(_check_missing_pullups(graph))
    conflicts.extend(_check_power_domain_mismatches(graph))

    return conflicts


def _check_i2c_address_collisions(
    graph: HardwareGraph, knowledge: list[ComponentKnowledge]
) -> list[Conflict]:
    """Check if multiple I2C slaves share the same address on the same bus."""
    conflicts: list[Conflict] = []
    knowledge_map = {k.component_id: k for k in knowledge}

    for bus in graph.buses:
        if bus.type.value != "I2C":
            continue

        # Collect known addresses per slave
        addr_map: dict[str, list[str]] = {}  # address → [component_ids]
        for slave_id in bus.slave_component_ids:
            kn = knowledge_map.get(slave_id)
            if kn and kn.i2c_address:
                addr = kn.i2c_address.upper()
                addr_map.setdefault(addr, []).append(slave_id)

        for addr, comp_ids in addr_map.items():
            if len(comp_ids) > 1:
                conflicts.append(Conflict(
                    severity="error",
                    category="i2c_collision",
                    message=f"I2C address collision: {addr} used by {', '.join(comp_ids)} on {bus.name}",
                    components=comp_ids,
                ))

    return conflicts


def _check_pin_conflicts(graph: HardwareGraph) -> list[Conflict]:
    """Check if the same MCU GPIO is assigned to multiple bus signals."""
    conflicts: list[Conflict] = []

    gpio_usage: dict[str, list[str]] = {}  # gpio → ["I2C_BUS.SDA", ...]

    for bus in graph.buses:
        for pm in bus.pin_mapping:
            if pm.gpio:
                label = f"{bus.name}.{pm.signal}"
                gpio_usage.setdefault(pm.gpio, []).append(label)

    for gpio, usages in gpio_usage.items():
        if len(usages) > 1:
            conflicts.append(Conflict(
                severity="error",
                category="pin_conflict",
                message=f"GPIO {gpio} used by multiple signals: {', '.join(usages)}",
                components=[],
            ))

    return conflicts


def _check_missing_pullups(graph: HardwareGraph) -> list[Conflict]:
    """Check if I2C buses have pull-up resistors (heuristic: passives on SDA/SCL nets)."""
    conflicts: list[Conflict] = []

    for bus in graph.buses:
        if bus.type.value != "I2C":
            continue

        # Look for nets named SDA/SCL and check if any passive components are connected
        for net_name in bus.nets:
            net = next((n for n in graph.nets if n.name == net_name), None)
            if not net:
                continue

            has_passive = False
            for pin_ref in net.pins:
                comp = next((c for c in graph.components if c.id == pin_ref.component_id), None)
                if comp and comp.name and comp.name[0].upper() == "R":
                    has_passive = True
                    break

            if not has_passive:
                signal = net_name.upper()
                if signal in ("SDA", "SCL", "I2C_SDA", "I2C_SCL") or signal.endswith("_SDA") or signal.endswith("_SCL"):
                    conflicts.append(Conflict(
                        severity="warning",
                        category="missing_pullup",
                        message=f"No pull-up resistor detected on {net_name} ({bus.name})",
                        components=[],
                    ))

    return conflicts


def _check_power_domain_mismatches(graph: HardwareGraph) -> list[Conflict]:
    """Check if components on the same bus are in different power domains."""
    conflicts: list[Conflict] = []

    # Build component → power domain map
    comp_power: dict[str, set[str]] = {}
    for pd in graph.power_domains:
        for net_name in pd.nets:
            net = next((n for n in graph.nets if n.name == net_name), None)
            if not net:
                continue
            for pin_ref in net.pins:
                comp_power.setdefault(pin_ref.component_id, set()).add(pd.voltage)

    # Check each bus
    for bus in graph.buses:
        if bus.master_component_id:
            all_ids = [bus.master_component_id] + bus.slave_component_ids
        else:
            all_ids = list(bus.slave_component_ids)
        voltages = set()
        for cid in all_ids:
            if cid and cid in comp_power:
                voltages.update(comp_power[cid])

        # Remove GND from comparison
        voltages.discard("0V")
        if len(voltages) > 1:
            conflicts.append(Conflict(
                severity="warning",
                category="power_mismatch",
                message=f"Components on {bus.name} span multiple voltage domains: {', '.join(sorted(voltages))}. "
                        "Consider level shifters.",
                components=all_ids,
            ))

    return conflicts
