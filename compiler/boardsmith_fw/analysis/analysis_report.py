# SPDX-License-Identifier: AGPL-3.0-or-later
"""Generate a human-readable analysis.md from a HardwareGraph."""

from __future__ import annotations

from boardsmith_fw.models.hardware_graph import HardwareGraph


def generate_analysis_report(graph: HardwareGraph) -> str:
    lines: list[str] = []

    lines.append("# Hardware Analysis Report")
    lines.append("")
    lines.append(f"**Source:** {graph.source}")
    lines.append(f"**Generated:** {graph.timestamp}")
    lines.append(f"**Version:** {graph.version}")
    lines.append("")

    # MCU
    lines.append("## MCU")
    if graph.mcu:
        lines.append(f"- **Component:** {graph.mcu.component_id}")
        lines.append(f"- **Type:** {graph.mcu.type}")
        lines.append(f"- **Pins:** {len(graph.mcu.pins)}")
    else:
        lines.append("- No MCU detected (ESP32 identifier not found in parts)")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append(f"- **Total Components:** {graph.metadata.total_components}")
    lines.append(f"- **Total Nets:** {graph.metadata.total_nets}")
    buses_str = ", ".join(graph.metadata.detected_buses) if graph.metadata.detected_buses else "none"
    lines.append(f"- **Detected Buses:** {buses_str}")
    lines.append("")

    # Components table
    lines.append("## Components")
    lines.append("")
    lines.append("| Ref | Value | Package | Library | Pins |")
    lines.append("|-----|-------|---------|---------|------|")
    for comp in graph.components:
        lines.append(f"| {comp.name} | {comp.value} | {comp.package} | {comp.library} | {len(comp.pins)} |")
    lines.append("")

    # Buses
    if graph.buses:
        lines.append("## Detected Buses")
        lines.append("")
        for bus in graph.buses:
            lines.append(f"### {bus.name} ({bus.type.value})")
            lines.append(f"- **Nets:** {', '.join(bus.nets)}")
            if bus.master_component_id:
                lines.append(f"- **Master:** {bus.master_component_id}")
            if bus.slave_component_ids:
                lines.append(f"- **Slaves:** {', '.join(bus.slave_component_ids)}")
            if bus.pin_mapping:
                lines.append("- **Pin Mapping:**")
                for pm in bus.pin_mapping:
                    gpio_str = f" (GPIO {pm.gpio})" if pm.gpio else ""
                    lines.append(f"  - {pm.signal}: {pm.mcu_pin_name}{gpio_str} → net `{pm.net}`")
            lines.append("")

    # IRQ
    if graph.irq_lines:
        lines.append("## IRQ Lines")
        lines.append("")
        lines.append("| Net | Source | Target |")
        lines.append("|-----|--------|--------|")
        for irq in graph.irq_lines:
            lines.append(f"| {irq.net} | {irq.source_component_id} | {irq.target_component_id} |")
        lines.append("")

    # Power
    if graph.power_domains:
        lines.append("## Power Domains")
        lines.append("")
        lines.append("| Name | Voltage |")
        lines.append("|------|---------|")
        for pd in graph.power_domains:
            lines.append(f"| {pd.name} | {pd.voltage} |")
        lines.append("")

    # Warnings
    if graph.metadata.warnings:
        lines.append("## Warnings")
        lines.append("")
        for w in graph.metadata.warnings:
            lines.append(f"- {w}")
        lines.append("")

    return "\n".join(lines)
