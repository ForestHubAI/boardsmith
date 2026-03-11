# SPDX-License-Identifier: AGPL-3.0-or-later
"""Constraint Solver — formal validation on the HIR.

Replaces the old heuristic-based conflict_detector and timing_engine
with proper constraint checking against the HIR model.

Each check function validates one category of constraints and returns
Constraint objects with PASS/FAIL/UNKNOWN status.
"""

from __future__ import annotations

from boardsmith_fw.models.hardware_graph import HardwareGraph
from boardsmith_fw.models.hir import (
    HIR,
    Constraint,
    ConstraintSeverity,
    ConstraintStatus,
    InitPhase,
)


def solve_constraints(hir: HIR, graph: HardwareGraph) -> list[Constraint]:
    """Run all constraint checks on the HIR. Returns updated constraint list."""
    constraints: list[Constraint] = []

    constraints.extend(_check_voltage_compatibility(hir))
    constraints.extend(_check_i2c_address_uniqueness(hir))
    constraints.extend(_check_i2c_bus_capacitance(hir))
    constraints.extend(_check_clock_feasibility(hir))
    constraints.extend(_check_pin_uniqueness(hir))
    constraints.extend(_check_pullup_resistors(hir, graph))
    constraints.extend(_check_init_sequence_ordering(hir))
    constraints.extend(_check_power_sequencing(hir))
    constraints.extend(_check_i2c_rise_time(hir))
    constraints.extend(_check_init_phase_coverage(hir))
    constraints.extend(_check_absolute_max_voltage(hir))

    return constraints


# ---------------------------------------------------------------------------
# C1: Voltage compatibility — all devices on a bus tolerate the bus voltage
# ---------------------------------------------------------------------------

def _check_voltage_compatibility(hir: HIR) -> list[Constraint]:
    constraints: list[Constraint] = []

    for bc in hir.bus_contracts:
        master_spec = hir.get_electrical_spec(bc.master_id)
        if not master_spec or not master_spec.io_voltage:
            constraints.append(Constraint(
                id=f"voltage.{bc.bus_name}.master_unknown",
                category="electrical",
                description=f"Cannot verify voltage compatibility on {bc.bus_name}: "
                            f"master IO voltage unknown",
                severity=ConstraintSeverity.WARNING,
                status=ConstraintStatus.UNKNOWN,
                affected_components=[bc.master_id],
            ))
            continue

        master_v = master_spec.io_voltage.nominal

        for slave_id in bc.slave_ids:
            slave_spec = hir.get_electrical_spec(slave_id)
            if not slave_spec or not slave_spec.supply_voltage:
                constraints.append(Constraint(
                    id=f"voltage.{bc.bus_name}.{slave_id}_unknown",
                    category="electrical",
                    description=f"Cannot verify voltage for {slave_id} on {bc.bus_name}: "
                                f"supply voltage unknown",
                    severity=ConstraintSeverity.WARNING,
                    status=ConstraintStatus.UNKNOWN,
                    affected_components=[slave_id],
                ))
                continue

            slave_v = slave_spec.supply_voltage.nominal

            # Check if voltages are compatible
            if abs(master_v - slave_v) > 0.5:
                # Different voltage domains — check 5V tolerance
                if master_v > slave_v and not slave_spec.is_5v_tolerant:
                    constraints.append(Constraint(
                        id=f"voltage.{bc.bus_name}.{slave_id}_mismatch",
                        category="electrical",
                        description=(
                            f"Voltage mismatch on {bc.bus_name}: master at {master_v}V, "
                            f"{slave_id} at {slave_v}V. Level shifter required."
                        ),
                        severity=ConstraintSeverity.ERROR,
                        status=ConstraintStatus.FAIL,
                        affected_components=[bc.master_id, slave_id],
                    ))
                else:
                    constraints.append(Constraint(
                        id=f"voltage.{bc.bus_name}.{slave_id}_ok",
                        category="electrical",
                        description=f"Voltage compatible on {bc.bus_name} (5V tolerant)",
                        severity=ConstraintSeverity.INFO,
                        status=ConstraintStatus.PASS,
                        affected_components=[bc.master_id, slave_id],
                    ))
            else:
                constraints.append(Constraint(
                    id=f"voltage.{bc.bus_name}.{slave_id}_ok",
                    category="electrical",
                    description=f"Voltage compatible on {bc.bus_name}: {master_v}V ≈ {slave_v}V",
                    severity=ConstraintSeverity.INFO,
                    status=ConstraintStatus.PASS,
                    affected_components=[bc.master_id, slave_id],
                ))

    return constraints


# ---------------------------------------------------------------------------
# C2: I2C address uniqueness per bus — per-slave tracking
# ---------------------------------------------------------------------------

def _check_i2c_address_uniqueness(hir: HIR) -> list[Constraint]:
    constraints: list[Constraint] = []

    for bc in hir.bus_contracts:
        if not bc.i2c:
            continue

        # No per-slave data available — fall back to bus-level address
        if not bc.slave_addresses:
            if bc.i2c.address and bc.i2c.address != "0x00":
                constraints.append(Constraint(
                    id=f"i2c_addr.{bc.bus_name}.ok",
                    category="protocol",
                    description=f"I2C bus {bc.bus_name}: address {bc.i2c.address} (no per-slave data)",
                    severity=ConstraintSeverity.INFO,
                    status=ConstraintStatus.PASS,
                    affected_components=bc.slave_ids,
                ))
            continue

        # Invert: address → list of slave_ids using that address
        addr_to_slaves: dict[str, list[str]] = {}
        for slave_id, addr in bc.slave_addresses.items():
            addr_to_slaves.setdefault(addr, []).append(slave_id)

        for addr, slaves in addr_to_slaves.items():
            if len(slaves) > 1:
                constraints.append(Constraint(
                    id=f"i2c_addr.{bc.bus_name}.{addr}.conflict",
                    category="protocol",
                    description=(
                        f"I2C address conflict on {bc.bus_name}: "
                        f"address {addr} used by {', '.join(slaves)}. "
                        f"Use address-select pin (SDO/ADDR) to differentiate."
                    ),
                    severity=ConstraintSeverity.ERROR,
                    status=ConstraintStatus.FAIL,
                    affected_components=slaves,
                ))
            else:
                constraints.append(Constraint(
                    id=f"i2c_addr.{bc.bus_name}.{addr}.ok",
                    category="protocol",
                    description=f"I2C bus {bc.bus_name}: {slaves[0]} @ {addr}",
                    severity=ConstraintSeverity.INFO,
                    status=ConstraintStatus.PASS,
                    affected_components=slaves,
                ))

        # Report slaves without known addresses
        for slave_id in bc.slave_ids:
            if slave_id not in bc.slave_addresses:
                constraints.append(Constraint(
                    id=f"i2c_addr.{bc.bus_name}.{slave_id}.unknown",
                    category="protocol",
                    description=f"I2C bus {bc.bus_name}: address unknown for {slave_id}",
                    severity=ConstraintSeverity.WARNING,
                    status=ConstraintStatus.UNKNOWN,
                    affected_components=[slave_id],
                ))

    return constraints


# ---------------------------------------------------------------------------
# C3: I2C bus capacitance (sum of pin capacitances vs 400pF limit)
# ---------------------------------------------------------------------------

def _check_i2c_bus_capacitance(hir: HIR) -> list[Constraint]:
    constraints: list[Constraint] = []

    for bc in hir.bus_contracts:
        if not bc.i2c:
            continue

        total_cap_pf = 0.0
        known_count = 0

        all_ids = [bc.master_id] + bc.slave_ids
        for comp_id in all_ids:
            spec = hir.get_electrical_spec(comp_id)
            if spec and spec.input_capacitance_pf:
                total_cap_pf += spec.input_capacitance_pf
                known_count += 1

        if known_count == 0:
            constraints.append(Constraint(
                id=f"i2c_cap.{bc.bus_name}.unknown",
                category="electrical",
                description=f"Cannot verify bus capacitance on {bc.bus_name}: "
                            f"no pin capacitance data available",
                severity=ConstraintSeverity.WARNING,
                status=ConstraintStatus.UNKNOWN,
                affected_components=all_ids,
            ))
        elif bc.i2c.bus_capacitance_pf_max is not None and total_cap_pf > bc.i2c.bus_capacitance_pf_max:
            constraints.append(Constraint(
                id=f"i2c_cap.{bc.bus_name}.exceeded",
                category="electrical",
                description=(
                    f"I2C bus capacitance on {bc.bus_name}: {total_cap_pf:.0f}pF "
                    f"exceeds max {bc.i2c.bus_capacitance_pf_max}pF. "
                    f"Reduce bus length or use bus buffer."
                ),
                severity=ConstraintSeverity.ERROR,
                status=ConstraintStatus.FAIL,
                affected_components=all_ids,
            ))
        else:
            constraints.append(Constraint(
                id=f"i2c_cap.{bc.bus_name}.ok",
                category="electrical",
                description=(
                    f"I2C bus capacitance on {bc.bus_name}: "
                    f"{total_cap_pf:.0f}pF / {bc.i2c.bus_capacitance_pf_max}pF"
                ),
                severity=ConstraintSeverity.INFO,
                status=ConstraintStatus.PASS,
                affected_components=all_ids,
            ))

    return constraints


# ---------------------------------------------------------------------------
# C4: Clock feasibility — configured freq <= min(all slave max freqs)
# ---------------------------------------------------------------------------

def _check_clock_feasibility(hir: HIR) -> list[Constraint]:
    constraints: list[Constraint] = []

    for bc in hir.bus_contracts:
        if bc.i2c:
            max_allowed = bc.i2c.max_clock_hz
            if max_allowed is None or bc.configured_clock_hz is None:
                continue
            if bc.configured_clock_hz > max_allowed:
                constraints.append(Constraint(
                    id=f"clock.{bc.bus_name}.too_fast",
                    category="timing",
                    description=(
                        f"I2C clock on {bc.bus_name}: configured {bc.configured_clock_hz}Hz "
                        f"exceeds max {max_allowed}Hz"
                    ),
                    severity=ConstraintSeverity.ERROR,
                    status=ConstraintStatus.FAIL,
                    affected_components=bc.slave_ids,
                ))
            elif bc.configured_clock_hz > max_allowed * 0.9:
                constraints.append(Constraint(
                    id=f"clock.{bc.bus_name}.near_limit",
                    category="timing",
                    description=(
                        f"I2C clock on {bc.bus_name}: {bc.configured_clock_hz}Hz is "
                        f">90% of max {max_allowed}Hz"
                    ),
                    severity=ConstraintSeverity.WARNING,
                    status=ConstraintStatus.PASS,
                    affected_components=bc.slave_ids,
                ))
            else:
                constraints.append(Constraint(
                    id=f"clock.{bc.bus_name}.ok",
                    category="timing",
                    description=(
                        f"I2C clock on {bc.bus_name}: {bc.configured_clock_hz}Hz "
                        f"within limit of {max_allowed}Hz"
                    ),
                    severity=ConstraintSeverity.INFO,
                    status=ConstraintStatus.PASS,
                    affected_components=bc.slave_ids,
                ))

        if bc.spi:
            max_allowed = bc.spi.max_clock_hz
            if max_allowed is None or bc.configured_clock_hz is None:
                continue
            if bc.configured_clock_hz > max_allowed:
                constraints.append(Constraint(
                    id=f"clock.{bc.bus_name}.too_fast",
                    category="timing",
                    description=(
                        f"SPI clock on {bc.bus_name}: configured {bc.configured_clock_hz}Hz "
                        f"exceeds max {max_allowed}Hz"
                    ),
                    severity=ConstraintSeverity.ERROR,
                    status=ConstraintStatus.FAIL,
                    affected_components=bc.slave_ids,
                ))
            else:
                constraints.append(Constraint(
                    id=f"clock.{bc.bus_name}.ok",
                    category="timing",
                    description=(
                        f"SPI clock on {bc.bus_name}: {bc.configured_clock_hz}Hz "
                        f"within limit of {max_allowed}Hz"
                    ),
                    severity=ConstraintSeverity.INFO,
                    status=ConstraintStatus.PASS,
                    affected_components=bc.slave_ids,
                ))

    return constraints


# ---------------------------------------------------------------------------
# C5: Pin uniqueness — no GPIO used by multiple bus signals
# ---------------------------------------------------------------------------

def _check_pin_uniqueness(hir: HIR) -> list[Constraint]:
    constraints: list[Constraint] = []

    gpio_usage: dict[str, list[str]] = {}  # gpio → ["I2C.SDA", "SPI.MOSI"]

    for bc in hir.bus_contracts:
        for signal, gpio in bc.pin_assignments.items():
            label = f"{bc.bus_name}.{signal}"
            gpio_usage.setdefault(gpio, []).append(label)

    for gpio, usages in gpio_usage.items():
        if len(usages) > 1:
            constraints.append(Constraint(
                id=f"pin.gpio{gpio}.conflict",
                category="electrical",
                description=f"GPIO {gpio} assigned to multiple signals: {', '.join(usages)}",
                severity=ConstraintSeverity.ERROR,
                status=ConstraintStatus.FAIL,
            ))
        else:
            constraints.append(Constraint(
                id=f"pin.gpio{gpio}.ok",
                category="electrical",
                description=f"GPIO {gpio} → {usages[0]}",
                severity=ConstraintSeverity.INFO,
                status=ConstraintStatus.PASS,
            ))

    return constraints


# ---------------------------------------------------------------------------
# C6: Pull-up resistors on I2C buses
# ---------------------------------------------------------------------------

def _check_pullup_resistors(hir: HIR, graph: HardwareGraph) -> list[Constraint]:
    constraints: list[Constraint] = []

    for bc in hir.bus_contracts:
        if not bc.i2c:
            continue

        # Check each I2C signal net for a resistor
        for signal in ("SDA", "SCL"):
            gpio = bc.pin_assignments.get(signal)
            if not gpio:
                continue

            # Find the net for this signal
            has_pullup = False
            net_name = None
            for bus in graph.buses:
                if bus.name == bc.bus_name:
                    for n in bus.nets:
                        n_upper = n.upper()
                        if signal in n_upper:
                            net_name = n
                            break
                    break

            if net_name:
                net = next((n for n in graph.nets if n.name == net_name), None)
                if net:
                    for pin_ref in net.pins:
                        comp = next(
                            (c for c in graph.components if c.id == pin_ref.component_id),
                            None,
                        )
                        if comp and comp.name:
                            # Check if this is actually a resistor by reference designator
                            ref = comp.name.upper()
                            if ref.startswith("R") and len(ref) > 1 and ref[1:].lstrip("0123456789") == "":
                                has_pullup = True
                                break

            if has_pullup:
                constraints.append(Constraint(
                    id=f"pullup.{bc.bus_name}.{signal}.ok",
                    category="electrical",
                    description=f"Pull-up resistor found on {signal} ({bc.bus_name})",
                    severity=ConstraintSeverity.INFO,
                    status=ConstraintStatus.PASS,
                ))
            else:
                constraints.append(Constraint(
                    id=f"pullup.{bc.bus_name}.{signal}.missing",
                    category="electrical",
                    description=(
                        f"No pull-up resistor detected on {signal} ({bc.bus_name}). "
                        f"I2C requires pull-ups (typically 4.7k for 100kHz, 2.2k for 400kHz)."
                    ),
                    severity=ConstraintSeverity.WARNING,
                    status=ConstraintStatus.FAIL,
                ))

    return constraints


# ---------------------------------------------------------------------------
# C7: Init sequence ordering — reset before configure, configure before enable
# ---------------------------------------------------------------------------

def _check_init_sequence_ordering(hir: HIR) -> list[Constraint]:
    constraints: list[Constraint] = []

    phase_order = {
        InitPhase.RESET: 0,
        InitPhase.CALIBRATE: 1,
        InitPhase.CONFIGURE: 2,
        InitPhase.ENABLE: 3,
        InitPhase.VERIFY: 4,  # verify typically happens last (chip ID check)
    }

    for ic in hir.init_contracts:
        if len(ic.phases) < 2:
            continue

        # Check that phases are in correct order
        prev_order = -1
        ordering_ok = True
        for phase in ic.phases:
            expected = phase_order.get(phase.phase, 99)
            if expected < prev_order:
                constraints.append(Constraint(
                    id=f"init_order.{ic.component_id}.wrong",
                    category="protocol",
                    description=(
                        f"{ic.component_name}: init phase '{phase.phase.value}' "
                        f"appears after a later phase. Expected order: "
                        f"verify → reset → calibrate → configure → enable"
                    ),
                    severity=ConstraintSeverity.WARNING,
                    status=ConstraintStatus.FAIL,
                    affected_components=[ic.component_id],
                ))
                ordering_ok = False
                break
            prev_order = expected

        if ordering_ok:
            phase_names = [p.phase.value for p in ic.phases]
            constraints.append(Constraint(
                id=f"init_order.{ic.component_id}.ok",
                category="protocol",
                description=f"{ic.component_name}: init sequence ok ({' → '.join(phase_names)})",
                severity=ConstraintSeverity.INFO,
                status=ConstraintStatus.PASS,
                affected_components=[ic.component_id],
            ))

    return constraints


# ---------------------------------------------------------------------------
# C8: Power sequencing — verify dependency ordering
# ---------------------------------------------------------------------------

def _check_power_sequencing(hir: HIR) -> list[Constraint]:
    constraints: list[Constraint] = []

    ps = hir.power_sequence
    if not ps.dependencies:
        return constraints

    # Check for circular dependencies
    order = ps.get_startup_order()

    if len(order) > 0:
        constraints.append(Constraint(
            id="power.sequence.ok",
            category="power",
            description=f"Power startup order: {' → '.join(order)}",
            severity=ConstraintSeverity.INFO,
            status=ConstraintStatus.PASS,
        ))

    return constraints


# ---------------------------------------------------------------------------
# C9: I2C rise-time — signal integrity from pullup + bus capacitance
# ---------------------------------------------------------------------------

# I2C rise-time: t_rise = 0.8473 * R_pullup * C_bus (RC to 70% VDD)
# Standard-mode (100kHz): max 1000ns
# Fast-mode (400kHz): max 300ns
# Fast-mode Plus (1MHz): max 120ns


def _check_i2c_rise_time(hir: HIR) -> list[Constraint]:
    """Check I2C signal integrity: rise time from pullup R and bus C."""
    constraints: list[Constraint] = []

    for bc in hir.bus_contracts:
        if not bc.i2c:
            continue

        # Gather bus capacitance from ElectricalSpecs
        total_cap_pf = 0.0
        cap_known = False
        all_ids = [bc.master_id] + bc.slave_ids
        for comp_id in all_ids:
            spec = hir.get_electrical_spec(comp_id)
            if spec and spec.input_capacitance_pf:
                total_cap_pf += spec.input_capacitance_pf
                cap_known = True

        # Add PCB trace estimate if we have component data
        if cap_known:
            total_cap_pf += 10.0  # ~10pF for short PCB traces

        # Determine which rise-time limit applies
        clock = bc.configured_clock_hz or bc.i2c.max_clock_hz
        if clock is None:
            clock = 100_000  # default to standard mode
        if clock > 400_000:
            mode_name, max_rise_ns = "fast_plus", 120
        elif clock > 100_000:
            mode_name, max_rise_ns = "fast", 300
        else:
            mode_name, max_rise_ns = "standard", 1000

        # If we have explicit t_rise from I2CSpec, use it directly
        if bc.i2c.t_rise_ns is not None:
            actual_rise = bc.i2c.t_rise_ns
            if actual_rise > max_rise_ns:
                constraints.append(Constraint(
                    id=f"rise_time.{bc.bus_name}.too_slow",
                    category="signal_integrity",
                    description=(
                        f"I2C rise time on {bc.bus_name}: {actual_rise}ns "
                        f"exceeds {mode_name}-mode limit of {max_rise_ns}ns. "
                        f"Use stronger pull-ups or reduce bus capacitance."
                    ),
                    severity=ConstraintSeverity.ERROR,
                    status=ConstraintStatus.FAIL,
                    affected_components=all_ids,
                ))
            else:
                margin = 100.0 * (1.0 - actual_rise / max_rise_ns)
                constraints.append(Constraint(
                    id=f"rise_time.{bc.bus_name}.ok",
                    category="signal_integrity",
                    description=(
                        f"I2C rise time on {bc.bus_name}: {actual_rise}ns "
                        f"within {mode_name}-mode limit ({margin:.0f}% margin)"
                    ),
                    severity=ConstraintSeverity.INFO,
                    status=ConstraintStatus.PASS,
                    affected_components=all_ids,
                ))
            continue

        # Calculate rise time from R_pullup and C_bus
        if not cap_known:
            constraints.append(Constraint(
                id=f"rise_time.{bc.bus_name}.unknown",
                category="signal_integrity",
                description=(
                    f"Cannot calculate rise time on {bc.bus_name}: "
                    f"no pin capacitance data"
                ),
                severity=ConstraintSeverity.WARNING,
                status=ConstraintStatus.UNKNOWN,
                affected_components=all_ids,
            ))
            continue

        # Use typical pullup (mid-range of I2CSpec bounds)
        r_pullup = (bc.i2c.pullup_ohm_min + bc.i2c.pullup_ohm_max) / 2.0
        # t_rise = 0.8473 * R * C (time to reach 0.7 * VDD)
        cap_farads = total_cap_pf * 1e-12
        rise_time_s = 0.8473 * r_pullup * cap_farads
        rise_time_ns = rise_time_s * 1e9

        if rise_time_ns > max_rise_ns:
            needed_r = max_rise_ns * 1e-9 / (0.8473 * cap_farads)
            constraints.append(Constraint(
                id=f"rise_time.{bc.bus_name}.too_slow",
                category="signal_integrity",
                description=(
                    f"I2C rise time on {bc.bus_name}: ~{rise_time_ns:.0f}ns "
                    f"(R={r_pullup:.0f}ohm, C={total_cap_pf:.0f}pF) "
                    f"exceeds {mode_name}-mode limit of {max_rise_ns}ns. "
                    f"Reduce pullup to <={needed_r:.0f}ohm."
                ),
                severity=ConstraintSeverity.ERROR,
                status=ConstraintStatus.FAIL,
                affected_components=all_ids,
            ))
        elif rise_time_ns > max_rise_ns * 0.8:
            margin = 100.0 * (1.0 - rise_time_ns / max_rise_ns)
            constraints.append(Constraint(
                id=f"rise_time.{bc.bus_name}.tight",
                category="signal_integrity",
                description=(
                    f"I2C rise time on {bc.bus_name}: ~{rise_time_ns:.0f}ns "
                    f"(R={r_pullup:.0f}ohm, C={total_cap_pf:.0f}pF) "
                    f"only {margin:.0f}% margin to {mode_name} {max_rise_ns}ns"
                ),
                severity=ConstraintSeverity.WARNING,
                status=ConstraintStatus.PASS,
                affected_components=all_ids,
            ))
        else:
            margin = 100.0 * (1.0 - rise_time_ns / max_rise_ns)
            constraints.append(Constraint(
                id=f"rise_time.{bc.bus_name}.ok",
                category="signal_integrity",
                description=(
                    f"I2C rise time on {bc.bus_name}: ~{rise_time_ns:.0f}ns "
                    f"(R={r_pullup:.0f}ohm, C={total_cap_pf:.0f}pF) "
                    f"{margin:.0f}% margin ({mode_name} {max_rise_ns}ns)"
                ),
                severity=ConstraintSeverity.INFO,
                status=ConstraintStatus.PASS,
                affected_components=all_ids,
            ))

    return constraints


# ---------------------------------------------------------------------------
# C10: Init phase coverage — verify all critical phases present
# ---------------------------------------------------------------------------

def _check_init_phase_coverage(hir: HIR) -> list[Constraint]:
    """Verify that init contracts cover essential phases."""
    constraints: list[Constraint] = []

    for ic in hir.init_contracts:
        if not ic.phases:
            constraints.append(Constraint(
                id=f"init_coverage.{ic.component_id}.empty",
                category="protocol",
                description=f"{ic.component_name}: no init phases defined",
                severity=ConstraintSeverity.WARNING,
                status=ConstraintStatus.FAIL,
                affected_components=[ic.component_id],
            ))
            continue

        phase_types = {p.phase for p in ic.phases}
        total_writes = sum(len(p.writes) for p in ic.phases)
        total_reads = sum(len(p.reads) for p in ic.phases)

        issues: list[str] = []

        # Every component should have at least one write
        if total_writes == 0:
            issues.append("no register writes (missing config?)")

        # Reset phase important for reliable startup
        if InitPhase.RESET not in phase_types and total_writes > 0:
            issues.append("no RESET phase (stale state risk)")

        # Writes without reads means no chip ID verification
        if total_writes > 0 and total_reads == 0:
            issues.append("no register reads (no chip ID verify)")

        if issues:
            constraints.append(Constraint(
                id=f"init_coverage.{ic.component_id}.incomplete",
                category="protocol",
                description=(
                    f"{ic.component_name}: {'; '.join(issues)}"
                ),
                severity=ConstraintSeverity.WARNING,
                status=ConstraintStatus.FAIL,
                affected_components=[ic.component_id],
            ))
        else:
            constraints.append(Constraint(
                id=f"init_coverage.{ic.component_id}.ok",
                category="protocol",
                description=(
                    f"{ic.component_name}: init complete "
                    f"({len(phase_types)} phases, "
                    f"{total_writes}W/{total_reads}R)"
                ),
                severity=ConstraintSeverity.INFO,
                status=ConstraintStatus.PASS,
                affected_components=[ic.component_id],
            ))

    return constraints


# ---------------------------------------------------------------------------
# C11: Absolute maximum voltage — supply voltage must not exceed abs max
# ---------------------------------------------------------------------------

def _check_absolute_max_voltage(hir: HIR) -> list[Constraint]:
    """Check that component supply voltages do not exceed absolute maximum ratings."""
    constraints: list[Constraint] = []

    for spec in hir.electrical_specs:
        if spec.abs_max_voltage is None:
            continue
        if spec.supply_voltage is None:
            continue

        actual_v = spec.supply_voltage.nominal
        abs_max = spec.abs_max_voltage
        rated_max = spec.supply_voltage.max

        if actual_v > abs_max:
            constraints.append(Constraint(
                id=f"abs_max.{spec.component_id}.exceeded",
                category="electrical",
                description=(
                    f"{spec.component_id}: supply voltage {actual_v}V exceeds "
                    f"absolute maximum {abs_max}V — component may be damaged!"
                ),
                severity=ConstraintSeverity.ERROR,
                status=ConstraintStatus.FAIL,
                affected_components=[spec.component_id],
            ))
        elif rated_max and actual_v > rated_max:
            constraints.append(Constraint(
                id=f"abs_max.{spec.component_id}.over_rated",
                category="electrical",
                description=(
                    f"{spec.component_id}: supply voltage {actual_v}V exceeds "
                    f"rated maximum {rated_max}V (abs max {abs_max}V)"
                ),
                severity=ConstraintSeverity.WARNING,
                status=ConstraintStatus.FAIL,
                affected_components=[spec.component_id],
            ))
        else:
            margin = 100.0 * (1.0 - actual_v / abs_max)
            constraints.append(Constraint(
                id=f"abs_max.{spec.component_id}.ok",
                category="electrical",
                description=(
                    f"{spec.component_id}: {actual_v}V within abs max "
                    f"{abs_max}V ({margin:.0f}% margin)"
                ),
                severity=ConstraintSeverity.INFO,
                status=ConstraintStatus.PASS,
                affected_components=[spec.component_id],
            ))

    return constraints
