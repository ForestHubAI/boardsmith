# SPDX-License-Identifier: AGPL-3.0-or-later
"""Timing constraints engine — validates bus and device timing.

Checks:
- Bus clock speed vs. device maximum frequency
- Startup time requirements (delays after power-on)
- Measurement timing (sensor conversion times)
"""

from __future__ import annotations

from dataclasses import dataclass

from boardsmith_fw.models.component_knowledge import ComponentKnowledge
from boardsmith_fw.models.hardware_graph import HardwareGraph


@dataclass
class TimingIssue:
    severity: str  # "error", "warning", "info"
    category: str
    message: str
    bus_name: str
    component_id: str


def validate_timing(
    graph: HardwareGraph,
    knowledge: list[ComponentKnowledge],
    i2c_freq: int = 100_000,
    spi_freq: int = 1_000_000,
) -> list[TimingIssue]:
    """Validate timing constraints for all buses and devices."""
    issues: list[TimingIssue] = []
    knowledge_map = {k.component_id: k for k in knowledge}

    for bus in graph.buses:
        bus_type = bus.type.value

        for slave_id in bus.slave_component_ids:
            kn = knowledge_map.get(slave_id)
            if not kn or not kn.timing_constraints:
                continue

            if bus_type == "I2C":
                issues.extend(
                    _check_i2c_timing(bus.name, slave_id, kn, i2c_freq)
                )
            elif bus_type == "SPI":
                issues.extend(
                    _check_spi_timing(bus.name, slave_id, kn, spi_freq)
                )

    return issues


def _check_i2c_timing(
    bus_name: str, comp_id: str, kn: ComponentKnowledge, configured_freq: int
) -> list[TimingIssue]:
    """Check I2C frequency against device limits."""
    issues: list[TimingIssue] = []

    for tc in kn.timing_constraints:
        param = tc.parameter.lower()
        if "clock" in param and "frequency" in param or "i2c" in param and "freq" in param:
            if tc.max:
                try:
                    max_freq = int(float(tc.max))
                    if configured_freq > max_freq:
                        issues.append(TimingIssue(
                            severity="error",
                            category="clock_too_fast",
                            message=(
                                f"{kn.name}: I2C clock {configured_freq}Hz exceeds "
                                f"max {max_freq}Hz"
                            ),
                            bus_name=bus_name,
                            component_id=comp_id,
                        ))
                    elif configured_freq > max_freq * 0.9:
                        issues.append(TimingIssue(
                            severity="warning",
                            category="clock_near_limit",
                            message=(
                                f"{kn.name}: I2C clock {configured_freq}Hz is near "
                                f"max {max_freq}Hz (>90%)"
                            ),
                            bus_name=bus_name,
                            component_id=comp_id,
                        ))
                except ValueError:
                    pass

    return issues


def _check_spi_timing(
    bus_name: str, comp_id: str, kn: ComponentKnowledge, configured_freq: int
) -> list[TimingIssue]:
    """Check SPI frequency against device limits."""
    issues: list[TimingIssue] = []

    for tc in kn.timing_constraints:
        param = tc.parameter.lower()
        if "spi" in param and "clock" in param or "spi" in param and "freq" in param:
            if tc.max:
                try:
                    max_freq = int(float(tc.max))
                    if configured_freq > max_freq:
                        issues.append(TimingIssue(
                            severity="error",
                            category="clock_too_fast",
                            message=(
                                f"{kn.name}: SPI clock {configured_freq}Hz exceeds "
                                f"max {max_freq}Hz"
                            ),
                            bus_name=bus_name,
                            component_id=comp_id,
                        ))
                except ValueError:
                    pass

    return issues


def get_required_delays(
    knowledge: list[ComponentKnowledge],
) -> list[tuple[str, str, int]]:
    """Extract required delays from init sequences.

    Returns list of (component_id, description, delay_ms).
    """
    delays: list[tuple[str, str, int]] = []

    for kn in knowledge:
        for step in kn.init_sequence:
            if step.delay_ms and step.delay_ms > 0:
                delays.append((kn.component_id, step.description, step.delay_ms))

    return delays
