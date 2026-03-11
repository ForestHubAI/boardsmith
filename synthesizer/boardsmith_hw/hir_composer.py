# SPDX-License-Identifier: AGPL-3.0-or-later
"""B5. HIR Composer — converts synthesized topology into canonical HIR JSON."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from synth_core.models.hir import (
    HIR, Component, ComponentRole, InterfaceType, Net, NetPin, Bus, BusType,
    BusContract, I2CSpec, SPISpec, UARTSpec, ElectricalSpec, Voltage, CurrentDraw,
    InitContract, InitPhase, InitPhaseTag, RegWrite, RegRead,
    PowerSequence, PowerRail, PowerDependency, Constraint, BOMEntry,
    HIRMetadata, Confidence, ConfidenceSubscores, Provenance, SourceType, Pin,
)
from boardsmith_hw.topology_synthesizer import SynthesizedTopology, TopologyBus, PassiveComponent, VoltageRegulator, AnalogNet, _comp_id
from boardsmith_hw.component_selector import SelectedComponent

_PROMPT_PROV = Provenance(source_type=SourceType.prompt, confidence=0.8)
_DB_PROV = Provenance(source_type=SourceType.builtin_db, confidence=0.95)
_INF_PROV = Provenance(source_type=SourceType.inference, confidence=0.7)


def _role(cat: str) -> ComponentRole:
    try:
        return ComponentRole(cat)
    except ValueError:
        return ComponentRole.other


def _iface(i: str) -> InterfaceType:
    try:
        return InterfaceType[i.upper()]
    except KeyError:
        return InterfaceType.OTHER


def _voltage(nom: float, min_: float | None = None, max_: float | None = None) -> Voltage:
    return Voltage(nominal=nom, min=min_, max=max_)


def compose_hir(
    topology: SynthesizedTopology,
    track: str = "B",
    source: str = "prompt",
    session_id: str | None = None,
    confidence_subscores: dict[str, float] | None = None,
    overall_confidence: float = 0.75,
) -> HIR:
    """Build a canonical HIR from a SynthesizedTopology."""
    components: list[Component] = []
    electrical_specs: list[ElectricalSpec] = []
    init_contracts: list[InitContract] = []
    nets: list[Net] = []
    buses: list[Bus] = []
    bus_contracts: list[BusContract] = []
    bom: list[BOMEntry] = []

    comp_by_id: dict[str, SelectedComponent] = {}
    _seen_comp_ids: set[str] = set()

    # --- Components ---
    for i, sc in enumerate(topology.components):
        cid = _comp_id(sc)
        # Deduplicate: skip if this component_id was already added (LLM
        # sometimes returns the MCU twice).
        if cid in _seen_comp_ids:
            continue
        _seen_comp_ids.add(cid)
        comp_by_id[cid] = sc

        ifaces = [_iface(i) for i in sc.interface_types]
        components.append(Component(
            id=cid,
            name=sc.name,
            role=_role(sc.category),
            manufacturer=sc.manufacturer or None,
            mpn=sc.mpn,
            interface_types=ifaces,
            provenance=_DB_PROV if sc.raw else _PROMPT_PROV,
        ))

        # Electrical specs
        r = sc.raw.get("electrical_ratings", {})
        if r:
            # Priority: explicit vdd_nominal > midpoint of vdd_min/vdd_max > io_voltage_nominal
            # Rationale: vdd_nominal is the core supply (e.g. 1.8V for ICM-42688-P, 12V for TB6612FNG VM),
            # whereas io_voltage_nominal is the I/O interface voltage (may differ from core VDD).
            # Using io_voltage_nominal as vdd_nom would cause nominal > max inconsistencies
            # (e.g. ICM-42688-P: io_voltage_nominal=3.3V but vdd_max=1.89V → 3.3 > 1.89 is wrong).
            vdd_nom = (
                r.get("vdd_nominal")
                or ((r["vdd_min"] + r["vdd_max"]) / 2 if r.get("vdd_min") and r.get("vdd_max") else None)
                or r.get("io_voltage_nominal", 3.3)
            )
            electrical_specs.append(ElectricalSpec(
                component_id=cid,
                supply_voltage=_voltage(vdd_nom, r.get("vdd_min"), r.get("vdd_max")),
                io_voltage=_voltage(
                    r.get("io_voltage_nominal", vdd_nom),
                    r.get("io_voltage_min"),
                    r.get("io_voltage_max"),
                ),
                logic_high_min=r.get("logic_high_min"),
                logic_low_max=r.get("logic_low_max"),
                current_draw=CurrentDraw(
                    typical=r.get("current_draw_typical_ma"),
                    max=r.get("current_draw_max_ma"),
                ) if r.get("current_draw_typical_ma") or r.get("current_draw_max_ma") else None,
                is_5v_tolerant=r.get("is_5v_tolerant"),
                drive_strength_ma=r.get("drive_strength_ma"),
                abs_max_voltage=r.get("abs_max_voltage"),
                temp_min_c=r.get("temp_min_c"),
                temp_max_c=r.get("temp_max_c"),
                provenance=_DB_PROV,
            ))

        # Init contract
        template = sc.raw.get("init_contract_template")
        if template:
            phases: list[InitPhase] = []
            for ph in template.get("phases", []):
                writes = [RegWrite(
                    reg_addr=w["reg_addr"],
                    # Empty value means command-only write (no data byte); use 0x00 as placeholder
                    value=w["value"] if w.get("value") else "0x00",
                    description=w.get("description"), purpose=w.get("purpose"),
                ) for w in ph.get("writes", [])]
                reads = [RegRead(
                    reg_addr=rd["reg_addr"],
                    expected_value=rd.get("expected_value"),
                    mask=rd.get("mask"),
                    description=rd.get("description"),
                ) for rd in ph.get("reads", [])]
                phases.append(InitPhase(
                    phase=InitPhaseTag(ph["phase"]),
                    order=ph.get("order", 0),
                    writes=writes,
                    reads=reads,
                    delay_after_ms=ph.get("delay_after_ms"),
                    provenance=_DB_PROV,
                ))
            init_contracts.append(InitContract(
                component_id=cid,
                component_name=sc.name,
                phases=phases,
            ))

        # BOM (mandatory for Boardsmith)
        bom.append(BOMEntry(
            line_id=f"L{i + 1:03d}",
            component_id=cid,
            mpn=sc.mpn,
            manufacturer=sc.manufacturer or None,
            description=sc.name,
            qty=1.0,
            unit_cost_estimate=sc.unit_cost_usd or None,
            provenance=_DB_PROV,
        ))

    # --- Passive components (pull-ups, decoupling caps, bulk caps) ---
    # NOTE: Net wiring for passives is deferred until after bus nets are
    # created (see "Deferred passive net wiring" block below).  Only
    # component + BOM entries are added here.
    _passive_prov = Provenance(source_type=SourceType.inference, confidence=0.95)
    for j, p in enumerate(topology.passives):
        components.append(Component(
            id=p.comp_id,
            name=f"{p.value}{p.unit} {p.category.capitalize()} ({p.purpose})",
            role=ComponentRole.passive,
            mpn=p.mpn_suggestion,
            interface_types=[],
            provenance=_passive_prov,
        ))
        bom.append(BOMEntry(
            line_id=f"P{j + 1:03d}",
            component_id=p.comp_id,
            mpn=p.mpn_suggestion,
            description=f"{p.value}{p.unit} {p.category} — {p.purpose.replace('_', ' ')}",
            qty=1.0,
            unit_cost_estimate=p.unit_cost_usd,
            provenance=_passive_prov,
        ))

    # --- Voltage Regulators (LDO, auto-synthesized when supply > MCU VDD) ---
    _pwr_prov = Provenance(source_type=SourceType.inference, confidence=0.90)
    ldo_bom_offset = len(topology.passives)
    for k, reg in enumerate(topology.voltage_regulators):
        components.append(Component(
            id=reg.comp_id,
            name=f"{reg.mpn} LDO {reg.input_voltage_nom:.0f}V→{reg.output_voltage_nom:.1f}V",
            role=ComponentRole.power,
            manufacturer=reg.manufacturer,
            mpn=reg.mpn,
            interface_types=[],
            provenance=_pwr_prov,
        ))
        bom.append(BOMEntry(
            line_id=f"V{k + 1:03d}",
            component_id=reg.comp_id,
            mpn=reg.mpn,
            manufacturer=reg.manufacturer,
            description=(
                f"LDO Voltage Regulator {reg.input_rail}→{reg.output_rail} "
                f"({reg.input_voltage_nom:.0f}V→{reg.output_voltage_nom:.1f}V, {reg.max_current_ma:.0f}mA max)"
            ),
            qty=1.0,
            unit_cost_estimate=reg.unit_cost_usd,
            provenance=_pwr_prov,
        ))

    # --- Buses and BusContracts ---
    for tb in topology.buses:
        buses.append(Bus(
            name=tb.name,
            type=BusType[tb.bus_type],
            master_component_id=tb.master_id,
            slave_component_ids=tb.slave_ids,
        ))

        # Synthesize nets for bus signals
        if tb.bus_type == "I2C":
            for signal, gpio in tb.pin_assignments.items():
                net_pins = [NetPin(component_id=tb.master_id, pin_name=gpio)]
                for sid in tb.slave_ids:
                    net_pins.append(NetPin(component_id=sid, pin_name=signal))
                nets.append(Net(
                    name=f"{tb.name}_{signal}",
                    pins=net_pins,
                    is_bus=True,
                    provenance=_INF_PROV,
                ))

        elif tb.bus_type == "SPI":
            # Shared signals: MOSI, MISO, SCK (one net each, shared by all SPI slaves)
            for signal in ("MOSI", "MISO", "SCK"):
                gpio = tb.pin_assignments.get(signal)
                if not gpio:
                    continue
                net_pins = [NetPin(component_id=tb.master_id, pin_name=gpio)]
                for sid in tb.slave_ids:
                    net_pins.append(NetPin(component_id=sid, pin_name=signal))
                nets.append(Net(
                    name=f"{tb.name}_{signal}",
                    pins=net_pins,
                    is_bus=True,
                    provenance=_INF_PROV,
                ))
            # Per-slave CS nets (CS_<slave_id> → MCU GPIO)
            for key, gpio in tb.pin_assignments.items():
                if not key.startswith("CS_"):
                    continue
                slave_id = key[3:]  # strip "CS_"
                if slave_id not in tb.slave_ids:
                    continue
                nets.append(Net(
                    name=f"{tb.name}_CS_{slave_id}",
                    pins=[
                        NetPin(component_id=tb.master_id, pin_name=gpio),
                        NetPin(component_id=slave_id,     pin_name="CS"),
                    ],
                    is_bus=True,
                    provenance=_INF_PROV,
                ))

        elif tb.bus_type == "UART":
            # Check if series resistors exist for this bus (added by peripheral_patterns).
            # If so, split the net: MCU side → {bus}_TX_MCU, connector side → {bus}_TX.
            # The deferred passive wiring will then bridge them via the resistor pads.
            _uart_tx_series = any(
                p.purpose == f"uart_tx_series_{tb.name}" for p in topology.passives
            )
            _uart_rx_series = any(
                p.purpose == f"uart_rx_series_{tb.name}" for p in topology.passives
            )
            # UART crossover for slave pin names:
            #   uart0_TX net (MCU transmit → slave receive): slave pin = "RX" (slave input)
            #   uart0_RX net (MCU receive ← slave transmit): slave pin = "TX" (slave output)
            # This ensures that devices with standard "TX"/"RX" pin names (GPS modules,
            # Bluetooth modules, etc.) get the correct by_hir assignment in kicad_exporter.
            # Devices with non-standard pin names (e.g. MAX485 "DI"/"RO") are unaffected
            # because those pin names don't appear in the HIR net pin list — by_spi handles
            # the alias matching for those peripherals instead.
            _UART_SLAVE_PIN: dict[str, str] = {"TX": "RX", "RX": "TX"}
            for signal in ("TX", "RX"):
                gpio = tb.pin_assignments.get(signal)
                if not gpio:
                    continue
                _slave_pin = _UART_SLAVE_PIN.get(signal, signal)
                _has_series = _uart_tx_series if signal == "TX" else _uart_rx_series
                if _has_series:
                    # MCU pin on {bus}_TX_MCU / {bus}_RX_MCU (R pin1 will be appended here)
                    nets.append(Net(
                        name=f"{tb.name}_{signal}_MCU",
                        pins=[NetPin(component_id=tb.master_id, pin_name=gpio)],
                        is_bus=True,
                        provenance=_INF_PROV,
                    ))
                    # Connector pin(s) on {bus}_TX / {bus}_RX (R pin2 will be appended here)
                    nets.append(Net(
                        name=f"{tb.name}_{signal}",
                        pins=[NetPin(component_id=sid, pin_name=_slave_pin) for sid in tb.slave_ids],
                        is_bus=True,
                        provenance=_INF_PROV,
                    ))
                else:
                    # No series resistor → unified net with all pins
                    net_pins = [NetPin(component_id=tb.master_id, pin_name=gpio)]
                    for sid in tb.slave_ids:
                        net_pins.append(NetPin(component_id=sid, pin_name=_slave_pin))
                    nets.append(Net(
                        name=f"{tb.name}_{signal}",
                        pins=net_pins,
                        is_bus=True,
                        provenance=_INF_PROV,
                    ))

        # Bus contract
        i2c_spec = None
        spi_spec = None
        uart_spec = None
        clock_hz = None

        if tb.bus_type == "I2C":
            # Find minimum max_clock across all participants
            clocks = []
            for cid in [tb.master_id] + tb.slave_ids:
                sc = comp_by_id.get(cid)
                if sc:
                    tc = sc.raw.get("timing_caps", {})
                    if tc.get("i2c_max_clock_hz"):
                        clocks.append(tc["i2c_max_clock_hz"])
            clock_hz = min(clocks) if clocks else 100000
            i2c_spec = I2CSpec(max_clock_hz=clock_hz, address_bits=7)

        elif tb.bus_type == "SPI":
            clocks = []
            spi_mode = 0
            for cid in tb.slave_ids:
                sc = comp_by_id.get(cid)
                if sc:
                    tc = sc.raw.get("timing_caps", {})
                    if tc.get("spi_max_clock_hz"):
                        clocks.append(tc["spi_max_clock_hz"])
                    if tc.get("spi_modes"):
                        spi_mode = tc["spi_modes"][0]
            clock_hz = min(clocks) if clocks else 1000000
            spi_spec = SPISpec(max_clock_hz=clock_hz, mode=spi_mode, bit_order="MSB", cs_active="low")

        pin_assigns = dict(tb.pin_assignments)  # keep CS_ keys so validator can check chip-selects

        # Filter master from slave list (LLM sometimes adds MCU as its own slave)
        _clean_slaves = [s for s in tb.slave_ids if s != tb.master_id]
        bus_contracts.append(BusContract(
            bus_name=tb.name,
            bus_type=tb.bus_type,
            master_id=tb.master_id,
            slave_ids=_clean_slaves,
            configured_clock_hz=clock_hz,
            pin_assignments=pin_assigns,
            slave_addresses=tb.slave_addresses,
            i2c=i2c_spec,
            spi=spi_spec,
            uart=uart_spec,
            provenance=_INF_PROV,
        ))

    # --- Analog signal nets (from circuit template instantiation) ---
    _analog_prov = Provenance(source_type=SourceType.inference, confidence=0.85)
    for an in topology.analog_nets:
        nets.append(Net(
            name=an.name,
            pins=[NetPin(component_id=cid, pin_name=pin_name) for cid, pin_name in an.pins],
            is_bus=an.is_bus,
            is_power=an.is_power,
            provenance=_analog_prov,
        ))

    # --- Deferred passive net wiring ---
    # Passives carry a .nets list (e.g. ["3V3_REG", "GND"]) that specifies
    # which net each pin connects to.  We process them here — AFTER bus and
    # analog nets are created — so that existing nets (like i2c0_SDA) can
    # be found and passive pins appended to them.  If a net doesn't exist
    # yet (e.g. a power rail name), we create it.
    _POWER_NET_NAMES = {"GND", "VIN_5V", "3V3_REG", "VBUS"}
    for p in topology.passives:
        for idx, net_name in enumerate(p.nets):
            pin_name = str(idx + 1)  # "1" for first pin, "2" for second
            existing = next((n for n in nets if n.name == net_name), None)
            if existing:
                existing.pins.append(
                    NetPin(component_id=p.comp_id, pin_name=pin_name)
                )
            else:
                # Create a new net for this passive connection (power rail, etc.)
                nets.append(Net(
                    name=net_name,
                    pins=[NetPin(component_id=p.comp_id, pin_name=pin_name)],
                    is_bus=False,
                    is_power=(net_name in _POWER_NET_NAMES
                              or net_name.upper() in ("GND", "+3V3", "+5V")),
                    provenance=_passive_prov,
                ))

    # --- Actuator / GPIO wiring ---
    # Buttons, transistors, etc. have associated passive nets (e.g.
    # BTN_SKRPACE010_IN from a pullup resistor).  Wire the actuator
    # component and MCU to these signal nets.
    _actuator_prov = Provenance(source_type=SourceType.inference, confidence=0.85)
    _mcu_comp = next(
        (c for c in topology.components if c.category == "mcu"), None
    )
    for sc in topology.components:
        if sc.category != "actuator":
            continue
        cid = _comp_id(sc)
        if cid not in _seen_comp_ids:
            continue  # component wasn't added (shouldn't happen)

        # Detect the signal net created by the actuator's passive
        # (e.g. "BTN_SKRPACE010_IN" from button_pullup passive)
        mpn_key = sc.mpn.replace("-", "_").replace(" ", "_").upper()
        btn_net_name = f"BTN_{mpn_key}_IN"
        btn_net = next((n for n in nets if n.name == btn_net_name), None)
        if btn_net is None:
            continue  # no matching signal net → not a button-type actuator

        # Wire actuator pin 1 → signal net (e.g. BTN_IN)
        btn_net.pins.append(
            NetPin(component_id=cid, pin_name="1")
        )
        # Wire actuator pin 2 → GND
        gnd_net = next((n for n in nets if n.name == "GND"), None)
        if gnd_net:
            gnd_net.pins.append(
                NetPin(component_id=cid, pin_name="2")
            )

        # Wire MCU GPIO → signal net
        if _mcu_comp:
            mcu_cid = _comp_id(_mcu_comp)
            btn_net.pins.append(
                NetPin(component_id=mcu_cid, pin_name="GPIO_BTN")
            )

    # --- Power sequence ---
    # Build a lookup from rail name → regulator for max_current annotation
    _reg_by_output = {r.output_rail: r for r in topology.voltage_regulators}
    _reg_by_input = {r.input_rail: r for r in topology.voltage_regulators}
    rails = [PowerRail(
        name=pr.name,
        voltage=_voltage(pr.voltage_nominal, pr.voltage_min, pr.voltage_max),
        max_current_ma=_reg_by_output[pr.name].max_current_ma if pr.name in _reg_by_output else None,
        provenance=_INF_PROV,
    ) for pr in topology.power_rails]

    # Power dependencies: VIN rail must be stable before regulated rail
    power_deps = [
        PowerDependency(
            source=reg.input_rail,
            target=reg.output_rail,
            min_delay_ms=1,
            description=f"{reg.mpn}: input rail must stabilise before output",
            provenance=_pwr_prov,
        )
        for reg in topology.voltage_regulators
    ]
    power_seq = PowerSequence(rails=rails, dependencies=power_deps)

    # --- Metadata ---
    ss = confidence_subscores or {}
    meta = HIRMetadata(
        created_at=datetime.now(timezone.utc).isoformat(),
        track=track,
        confidence=Confidence(
            overall=overall_confidence,
            subscores=ConfidenceSubscores(
                intent=ss.get("intent"),
                components=ss.get("components"),
                topology=ss.get("topology"),
                electrical=ss.get("electrical"),
            ) if ss else None,
            explanations=[f"Boardsmith synthesis with {len(topology.components)} components"],
        ),
        assumptions=topology.assumptions,
        session_id=session_id,
    )

    return HIR(
        version="1.1.0",
        source=source,
        components=components,
        nets=nets,
        buses=buses,
        bus_contracts=bus_contracts,
        electrical_specs=electrical_specs,
        init_contracts=init_contracts,
        power_sequence=power_seq,
        constraints=[],
        bom=bom,
        metadata=meta,
    )
