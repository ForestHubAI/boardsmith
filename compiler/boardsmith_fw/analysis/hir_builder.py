# SPDX-License-Identifier: AGPL-3.0-or-later
"""HIR Builder — transforms HardwareGraph + Knowledge into HIR.

This is the semantic analysis step: raw topology + datasheet knowledge
become formal, validatable hardware contracts.
"""

from __future__ import annotations

from boardsmith_fw.models.component_knowledge import ComponentKnowledge
from boardsmith_fw.models.hardware_graph import HardwareGraph
from boardsmith_fw.models.hir import (
    HIR,
    BusContract,
    CurrentSpec,
    ElectricalSpec,
    I2CSpec,
    InitContract,
    InitPhase,
    InitPhaseSpec,
    PowerDependency,
    PowerRail,
    PowerSequence,
    RegisterRead,
    RegisterWrite,
    SPISpec,
    UARTSpec,
    VoltageLevel,
)


def build_hir(
    graph: HardwareGraph,
    knowledge: list[ComponentKnowledge],
) -> HIR:
    """Build a complete HIR from a HardwareGraph and resolved knowledge."""
    knowledge_map = {k.component_id: k for k in knowledge}

    hir = HIR(source=graph.source)

    hir.electrical_specs = _build_electrical_specs(graph, knowledge_map)
    hir.bus_contracts = _build_bus_contracts(graph, knowledge_map)
    hir.init_contracts = _build_init_contracts(graph, knowledge_map)
    hir.power_sequence = _build_power_sequence(graph, knowledge_map)

    return hir


# ---------------------------------------------------------------------------
# Electrical specs
# ---------------------------------------------------------------------------

_COMMON_VOLTAGES: dict[str, VoltageLevel] = {
    "3V3": VoltageLevel(nominal=3.3, min=3.0, max=3.6),
    "3.3V": VoltageLevel(nominal=3.3, min=3.0, max=3.6),
    "5V": VoltageLevel(nominal=5.0, min=4.5, max=5.5),
    "1V8": VoltageLevel(nominal=1.8, min=1.7, max=1.9),
    "1.8V": VoltageLevel(nominal=1.8, min=1.7, max=1.9),
    "2V5": VoltageLevel(nominal=2.5, min=2.3, max=2.7),
}


def _build_electrical_specs(
    graph: HardwareGraph,
    knowledge_map: dict[str, ComponentKnowledge],
) -> list[ElectricalSpec]:
    specs: list[ElectricalSpec] = []

    for comp in graph.components:
        # Skip passives
        if comp.name and comp.name[0].upper() in ("R", "C", "L", "D"):
            continue

        kn = knowledge_map.get(comp.id)
        spec = ElectricalSpec(component_id=comp.id)

        # Infer supply voltage from power domain connections
        supply_v = _infer_supply_voltage(graph, comp.id)
        if supply_v:
            spec.supply_voltage = supply_v
            spec.io_voltage = supply_v  # default: IO = supply

        # Extract from knowledge timing constraints (common patterns)
        if kn:
            # Use electrical_ratings if available (5.7: structured ratings)
            er = kn.electrical_ratings
            if er:
                if er.vdd_min is not None and er.vdd_max is not None:
                    # Keep the actual operating voltage (inferred from power domain)
                    # as nominal; use ratings to tighten min/max bounds.
                    nominal = spec.supply_voltage.nominal if spec.supply_voltage else (er.vdd_min + er.vdd_max) / 2.0
                    spec.supply_voltage = VoltageLevel(
                        nominal=nominal,
                        min=er.vdd_min,
                        max=er.vdd_max,
                    )
                    spec.io_voltage = spec.supply_voltage
                if er.io_voltage_min is not None and er.io_voltage_max is not None:
                    io_nom = (
                        spec.io_voltage.nominal if spec.io_voltage
                        else (er.io_voltage_min + er.io_voltage_max) / 2.0
                    )
                    spec.io_voltage = VoltageLevel(
                        nominal=io_nom,
                        min=er.io_voltage_min,
                        max=er.io_voltage_max,
                    )
                if er.current_supply_ma is not None:
                    spec.current_draw = CurrentSpec(
                        typical=er.current_supply_ma,
                        max=er.current_supply_max_ma or 0.0,
                    )
                spec.is_5v_tolerant = er.is_5v_tolerant
                spec.abs_max_voltage = er.vdd_abs_max
                spec.temp_min_c = er.temp_min_c
                spec.temp_max_c = er.temp_max_c

            for tc in kn.timing_constraints:
                param = tc.parameter.lower()
                if "supply" in param and "current" in param and tc.typical and not spec.current_draw:
                    try:
                        spec.current_draw = CurrentSpec(
                            typical=float(tc.typical),
                            max=float(tc.max) if tc.max else 0.0,
                            unit=tc.unit or "mA",
                        )
                    except ValueError:
                        pass

            # Input capacitance from notes
            for note in kn.notes:
                if "capacitance" in note.lower() and "pf" in note.lower():
                    try:
                        # Simple extraction: find number before "pF"
                        import re
                        m = re.search(r"(\d+(?:\.\d+)?)\s*pF", note, re.IGNORECASE)
                        if m:
                            spec.input_capacitance_pf = float(m.group(1))
                    except (ValueError, AttributeError):
                        pass

        specs.append(spec)

    return specs


def _infer_supply_voltage(graph: HardwareGraph, comp_id: str) -> VoltageLevel | None:
    """Infer a component's supply voltage from its power domain connections."""
    for pd in graph.power_domains:
        for net_name in pd.nets:
            net = next((n for n in graph.nets if n.name == net_name), None)
            if not net:
                continue
            for pin_ref in net.pins:
                if pin_ref.component_id == comp_id:
                    # Found a power connection — check voltage
                    v = pd.voltage.upper().replace(" ", "")
                    if v in _COMMON_VOLTAGES:
                        return _COMMON_VOLTAGES[v]
                    # Try to parse as number
                    try:
                        val = float(v.rstrip("V"))
                        return VoltageLevel(nominal=val, min=val * 0.9, max=val * 1.1)
                    except ValueError:
                        pass
    return None


# ---------------------------------------------------------------------------
# Bus contracts
# ---------------------------------------------------------------------------

def _build_bus_contracts(
    graph: HardwareGraph,
    knowledge_map: dict[str, ComponentKnowledge],
) -> list[BusContract]:
    contracts: list[BusContract] = []

    for bus in graph.buses:
        contract = BusContract(
            bus_name=bus.name,
            bus_type=bus.type.value,
            master_id=bus.master_component_id or "",
            slave_ids=list(bus.slave_component_ids),
        )

        # Extract pin assignments
        for pm in bus.pin_mapping:
            if pm.gpio:
                contract.pin_assignments[pm.signal] = pm.gpio

        if bus.type.value == "I2C":
            contract.i2c, contract.slave_addresses = _build_i2c_contract(bus, knowledge_map)
            if contract.i2c:
                contract.configured_clock_hz = contract.i2c.max_clock_hz
        elif bus.type.value == "SPI":
            contract.spi = _build_spi_contract(bus, knowledge_map)
            if contract.spi:
                contract.configured_clock_hz = contract.spi.max_clock_hz
        elif bus.type.value == "UART":
            contract.uart = _build_uart_contract(bus, knowledge_map)

        contracts.append(contract)

    return contracts


def _build_i2c_contract(bus, knowledge_map) -> tuple[I2CSpec | None, dict[str, str]]:
    """Build I2C spec from the strictest slave requirements.

    Returns (I2CSpec, slave_addresses) where slave_addresses maps
    slave_id → i2c_address (e.g. {"U2": "0x76", "U3": "0x77"}).
    """
    if not bus.slave_component_ids:
        return None, {}

    # Start with permissive defaults
    max_clock = 400_000  # Standard-mode default
    first_address = "0x00"
    slave_addresses: dict[str, str] = {}

    for slave_id in bus.slave_component_ids:
        kn = knowledge_map.get(slave_id)
        if not kn:
            continue

        if kn.i2c_address:
            slave_addresses[slave_id] = kn.i2c_address
            if first_address == "0x00":
                first_address = kn.i2c_address  # keep first known as bus-level default

        for tc in kn.timing_constraints:
            param = tc.parameter.lower()
            is_clock = (
                ("clock" in param and "frequency" in param)
                or ("i2c" in param and "freq" in param)
                or ("scl" in param and "freq" in param)
            )
            if is_clock and tc.max:
                try:
                    slave_max = int(float(tc.max))
                    # Take the MINIMUM of all slaves (most restrictive)
                    max_clock = min(max_clock, slave_max)
                except ValueError:
                    pass

    spec = I2CSpec(
        address=first_address,
        max_clock_hz=max_clock,
    )
    return spec, slave_addresses


def _build_spi_contract(bus, knowledge_map) -> SPISpec | None:
    if not bus.slave_component_ids:
        return None

    max_clock = 10_000_000
    spi_mode = 0

    for slave_id in bus.slave_component_ids:
        kn = knowledge_map.get(slave_id)
        if not kn:
            continue

        if kn.spi_mode is not None:
            spi_mode = kn.spi_mode

        for tc in kn.timing_constraints:
            param = tc.parameter.lower()
            if ("spi" in param or "sck" in param) and ("freq" in param or "clock" in param):
                if tc.max:
                    try:
                        slave_max = int(float(tc.max))
                        max_clock = min(max_clock, slave_max)
                    except ValueError:
                        pass

    return SPISpec(max_clock_hz=max_clock, mode=spi_mode)


def _build_uart_contract(bus, knowledge_map) -> UARTSpec | None:
    baud = 115200

    for slave_id in bus.slave_component_ids:
        kn = knowledge_map.get(slave_id)
        if not kn:
            continue
        for tc in kn.timing_constraints:
            param = tc.parameter.lower()
            if "baud" in param and tc.typical:
                try:
                    baud = int(float(tc.typical))
                except ValueError:
                    pass

    return UARTSpec(baud_rate=baud)


# ---------------------------------------------------------------------------
# Init contracts
# ---------------------------------------------------------------------------

def _build_init_contracts(
    graph: HardwareGraph,
    knowledge_map: dict[str, ComponentKnowledge],
) -> list[InitContract]:
    contracts: list[InitContract] = []

    for comp in graph.components:
        kn = knowledge_map.get(comp.id)
        if not kn or not kn.init_sequence:
            continue

        contract = InitContract(
            component_id=comp.id,
            component_name=kn.name or comp.value,
        )

        # Classify init steps into phases
        phases: dict[InitPhase, InitPhaseSpec] = {}

        for step in kn.init_sequence:
            phase = _classify_init_step(step.description)

            if phase not in phases:
                phases[phase] = InitPhaseSpec(
                    phase=phase,
                    order=len(phases),
                )

            phase_spec = phases[phase]

            if step.reg_addr and step.value:
                phase_spec.writes.append(RegisterWrite(
                    reg_addr=step.reg_addr,
                    value=step.value,
                    description=step.description,
                    purpose=phase.value,
                ))
            elif step.reg_addr and not step.value:
                phase_spec.reads.append(RegisterRead(
                    reg_addr=step.reg_addr,
                    description=step.description,
                    purpose=phase.value,
                ))

            if step.delay_ms and step.delay_ms > (phase_spec.delay_after_ms or 0):
                phase_spec.delay_after_ms = step.delay_ms

        # Add chip ID verification if we have registers
        if kn.registers:
            chip_id_reg = next(
                (r for r in kn.registers if "chip" in r.name.lower() or "id" in r.name.lower()),
                None,
            )
            if chip_id_reg:
                verify_phase = InitPhaseSpec(
                    phase=InitPhase.VERIFY,
                    order=len(phases),
                    reads=[RegisterRead(
                        reg_addr=chip_id_reg.address,
                        expected_value=chip_id_reg.fields[0].default_value if chip_id_reg.fields else None,
                        description=f"Verify {kn.name} chip ID",
                        purpose="chip_id",
                    )],
                    precondition="Device powered and bus initialized",
                )
                phases[InitPhase.VERIFY] = verify_phase

        contract.phases = sorted(phases.values(), key=lambda p: p.order)

        # Populate IRQ pin if this component has an interrupt line in the graph
        irq_gpio, irq_trigger = _find_irq_gpio(graph, comp.id)
        if irq_gpio:
            contract.irq_gpio = irq_gpio
            contract.irq_trigger = irq_trigger

        contracts.append(contract)

    return contracts


def _find_irq_gpio(
    graph: HardwareGraph,
    component_id: str,
) -> tuple[str | None, str]:
    """Return (gpio_number, trigger) for the IRQ line driven by component_id.

    Returns (None, "falling") if no IRQ line is found.
    """
    mcu_id = graph.mcu.component_id if graph.mcu else None

    for irq in graph.irq_lines:
        if irq.source_component_id != component_id:
            continue

        # Find MCU pin connected to this IRQ net
        net = next((n for n in graph.nets if n.name == irq.net), None)
        if net is None:
            continue

        for net_pin in net.pins:
            if net_pin.component_id == mcu_id:
                gpio = _parse_gpio_number(net_pin.pin_name)
                if gpio:
                    trigger = irq.trigger or "falling"
                    return gpio, trigger

    return None, "falling"


import re as _re


def _parse_gpio_number(pin_name: str) -> str | None:
    """Extract GPIO number from an MCU pin name.

    Examples:
        "GPIO4"         → "4"
        "GPIO21/SDA"    → "21"
        "PA5"           → "5"
        "P0.04"         → "4"
        "IO4"           → "4"
    """
    # ESP32/RP2040: GPIO4, IO4, GPIO21/SDA
    m = _re.search(r"(?:GPIO|IO)(\d+)", pin_name, _re.IGNORECASE)
    if m:
        return m.group(1)
    # STM32: PA5, PB12, PC3
    m = _re.search(r"P[A-Z](\d+)", pin_name, _re.IGNORECASE)
    if m:
        return m.group(1)
    # nRF52: P0.04
    m = _re.search(r"P\d+\.(\d+)", pin_name, _re.IGNORECASE)
    if m:
        return m.group(1)
    return None


_PHASE_KEYWORDS: dict[str, InitPhase] = {
    "reset": InitPhase.RESET,
    "soft reset": InitPhase.RESET,
    "power-on": InitPhase.RESET,
    "config": InitPhase.CONFIGURE,
    "mode": InitPhase.CONFIGURE,
    "oversampling": InitPhase.CONFIGURE,
    "filter": InitPhase.CONFIGURE,
    "standby": InitPhase.CONFIGURE,
    "calibrat": InitPhase.CALIBRATE,
    "compensat": InitPhase.CALIBRATE,
    "trim": InitPhase.CALIBRATE,
    "enable": InitPhase.ENABLE,
    "start": InitPhase.ENABLE,
    "normal mode": InitPhase.ENABLE,
    "measurement": InitPhase.ENABLE,
    "verify": InitPhase.VERIFY,
    "check": InitPhase.VERIFY,
    "read id": InitPhase.VERIFY,
}


def _classify_init_step(description: str) -> InitPhase:
    desc_lower = description.lower()
    for keyword, phase in _PHASE_KEYWORDS.items():
        if keyword in desc_lower:
            return phase
    return InitPhase.CONFIGURE


# ---------------------------------------------------------------------------
# Power sequencing
# ---------------------------------------------------------------------------

def _build_power_sequence(
    graph: HardwareGraph,
    knowledge_map: dict[str, ComponentKnowledge],
) -> PowerSequence:
    seq = PowerSequence()

    for pd in graph.power_domains:
        v_str = pd.voltage.upper().replace(" ", "")
        voltage = _COMMON_VOLTAGES.get(v_str)
        if not voltage:
            try:
                val = float(v_str.rstrip("V"))
                voltage = VoltageLevel(nominal=val, min=val * 0.9, max=val * 1.1)
            except ValueError:
                voltage = VoltageLevel(nominal=0.0)

        rail = PowerRail(
            name=pd.name,
            voltage=voltage,
        )
        seq.rails.append(rail)

    # Build dependencies: higher voltage rails should come up before lower
    # (common pattern: 3.3V before 1.8V for core logic)
    sorted_rails = sorted(seq.rails, key=lambda r: -r.voltage.nominal)
    for i in range(len(sorted_rails) - 1):
        seq.dependencies.append(PowerDependency(
            source=sorted_rails[i].name,
            target=sorted_rails[i + 1].name,
            min_delay_ms=1,
            description=f"{sorted_rails[i].name} must be stable before {sorted_rails[i + 1].name}",
        ))

    # Components with init delays depend on their power rail
    for comp in graph.components:
        kn = knowledge_map.get(comp.id)
        if not kn or not kn.init_sequence:
            continue
        startup_delay = 0
        for step in kn.init_sequence:
            if step.delay_ms:
                startup_delay = max(startup_delay, step.delay_ms)

    return seq
