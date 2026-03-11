# SPDX-License-Identifier: AGPL-3.0-or-later
"""build_hir — deterministic conversion of HardwareGraph + ComponentKnowledge → HIR."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from synth_core.hir_bridge.graph import HardwareGraph
from synth_core.knowledge.resolver import KnowledgeResolver
from synth_core.models.hir import (
    HIR, Component, ComponentRole, InterfaceType, Net, NetPin, Bus, BusType,
    BusContract, I2CSpec, SPISpec, UARTSpec, ElectricalSpec, Voltage, CurrentDraw,
    InitContract, InitPhase, InitPhaseTag, RegWrite, RegRead,
    PowerSequence, PowerRail, Constraint, ConstraintCategory, Severity, ConstraintStatus,
    HIRMetadata, Confidence, Provenance, SourceType, Pin,
)

_DB_PROV = Provenance(source_type=SourceType.builtin_db, confidence=0.95)
_SCH_PROV = Provenance(source_type=SourceType.schematic, confidence=1.0)
_INF_PROV = Provenance(source_type=SourceType.inference, confidence=0.7)


def _role(r: str) -> ComponentRole:
    try:
        return ComponentRole(r)
    except ValueError:
        return ComponentRole.other


def _iface(i: str) -> InterfaceType:
    try:
        return InterfaceType[i.upper()]
    except KeyError:
        return InterfaceType.OTHER


def _bus_type(t: str) -> BusType:
    try:
        return BusType[t.upper()]
    except KeyError:
        return BusType.OTHER


def _voltage(nominal: float, min_: float | None = None, max_: float | None = None) -> Voltage:
    return Voltage(nominal=nominal, min=min_, max=max_)


def build_hir(
    graph: HardwareGraph,
    resolver: KnowledgeResolver | None = None,
    source: str = "schematic",
    track: str = "A",
    session_id: str | None = None,
) -> HIR:
    """Convert a HardwareGraph into a canonical HIR v1.1.0 object."""
    if resolver is None:
        resolver = KnowledgeResolver()

    components: list[Component] = []
    electrical_specs: list[ElectricalSpec] = []
    init_contracts: list[InitContract] = []
    nets: list[Net] = []
    buses: list[Bus] = []
    bus_contracts: list[BusContract] = []

    # --- Components ---
    for gc in graph.components:
        kb = resolver.resolve_mpn(gc.mpn) or {}
        prov = _DB_PROV if kb else _INF_PROV
        if not kb:
            prov = Provenance(source_type=SourceType.schematic, confidence=0.6)

        ifaces = [_iface(i) for i in (gc.interface_types or kb.get("interface_types", []))]
        pins = [Pin(name=p.name, number=p.number, function=p.function, electrical_type=p.electrical_type)
                for p in gc.pins]

        components.append(Component(
            id=gc.id,
            name=gc.name,
            role=_role(gc.role or kb.get("category", "other")),
            manufacturer=gc.manufacturer or kb.get("manufacturer", "") or None,
            mpn=gc.mpn,
            package=gc.package or kb.get("package", "") or None,
            interface_types=ifaces,
            pins=pins,
            provenance=prov,
        ))

        # Electrical specs from KB
        if kb:
            r = kb.get("electrical_ratings", {})
            vdd_nom = (r.get("vdd_min", 0) + r.get("vdd_max", 0)) / 2 if r.get("vdd_min") and r.get("vdd_max") else r.get("io_voltage_nominal", 3.3)
            elec = ElectricalSpec(
                component_id=gc.id,
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
                input_capacitance_pf=r.get("input_capacitance_pf"),
                abs_max_voltage=r.get("abs_max_voltage"),
                temp_min_c=r.get("temp_min_c"),
                temp_max_c=r.get("temp_max_c"),
                provenance=_DB_PROV,
            )
            electrical_specs.append(elec)

            # Init contract from KB template
            template = kb.get("init_contract_template")
            if template:
                phases: list[InitPhase] = []
                for ph in template.get("phases", []):
                    writes = [RegWrite(
                        reg_addr=w["reg_addr"], value=w["value"],
                        description=w.get("description"), purpose=w.get("purpose"),
                    ) for w in ph.get("writes", [])]
                    reads = [RegRead(
                        reg_addr=rd["reg_addr"],
                        expected_value=rd.get("expected_value"),
                        mask=rd.get("mask"),
                        description=rd.get("description"),
                        purpose=rd.get("purpose"),
                    ) for rd in ph.get("reads", [])]
                    phases.append(InitPhase(
                        phase=InitPhaseTag(ph["phase"]),
                        order=ph.get("order", 0),
                        writes=writes,
                        reads=reads,
                        delay_after_ms=ph.get("delay_after_ms"),
                        precondition=ph.get("precondition"),
                        postcondition=ph.get("postcondition"),
                        provenance=_DB_PROV,
                    ))
                init_contracts.append(InitContract(
                    component_id=gc.id,
                    component_name=gc.name,
                    phases=phases,
                ))

    # --- Nets ---
    for gn in graph.nets:
        nets.append(Net(
            name=gn.name,
            pins=[NetPin(component_id=p[0], pin_name=p[1]) for p in gn.pins],
            is_bus=gn.is_bus,
            is_power=gn.is_power,
            provenance=_SCH_PROV,
        ))

    # --- Buses → BusContracts ---
    for gb in graph.buses:
        buses.append(Bus(
            name=gb.name,
            type=_bus_type(gb.type),
            master_component_id=gb.master_id,
            slave_component_ids=gb.slave_ids,
        ))

        # Build slave_addresses from KB
        slave_addresses: dict[str, str] = {}
        for sid in gb.slave_ids:
            sc = graph.get_component(sid)
            if sc:
                kb = resolver.resolve_mpn(sc.mpn) or {}
                addrs = kb.get("known_i2c_addresses", [])
                if addrs:
                    slave_addresses[sid] = addrs[0]

        bt = gb.type.upper()
        i2c_spec = None
        spi_spec = None
        uart_spec = None

        if bt == "I2C":
            # Use lowest max_clock across all participants
            clocks = []
            for cid in [gb.master_id] + gb.slave_ids:
                c = graph.get_component(cid)
                if c:
                    kb = resolver.resolve_mpn(c.mpn) or {}
                    tc = kb.get("timing_caps", {})
                    if tc.get("i2c_max_clock_hz"):
                        clocks.append(tc["i2c_max_clock_hz"])
            max_clock = min(clocks) if clocks else 100000
            i2c_spec = I2CSpec(max_clock_hz=max_clock, address_bits=7)

        elif bt == "SPI":
            clocks = []
            modes = None
            for cid in gb.slave_ids:
                c = graph.get_component(cid)
                if c:
                    kb = resolver.resolve_mpn(c.mpn) or {}
                    tc = kb.get("timing_caps", {})
                    if tc.get("spi_max_clock_hz"):
                        clocks.append(tc["spi_max_clock_hz"])
                    if modes is None and tc.get("spi_modes"):
                        modes = tc["spi_modes"][0]
            spi_spec = SPISpec(
                max_clock_hz=min(clocks) if clocks else 1000000,
                mode=modes,
                bit_order="MSB",
                cs_active="low",
            )

        elif bt == "UART":
            uart_spec = UARTSpec(baud_rate=115200, data_bits=8, stop_bits=1, parity="none", flow_control="none")

        clk_hz = i2c_spec.max_clock_hz if i2c_spec else (spi_spec.max_clock_hz if spi_spec else None)

        bus_contracts.append(BusContract(
            bus_name=gb.name,
            bus_type=bt,
            master_id=gb.master_id,
            slave_ids=gb.slave_ids,
            configured_clock_hz=clk_hz,
            pin_assignments=gb.pin_assignments,
            slave_addresses=slave_addresses,
            i2c=i2c_spec,
            spi=spi_spec,
            uart=uart_spec,
            provenance=_INF_PROV,
        ))

    # --- Power sequence (inferred) ---
    power_rails = [PowerRail(
        name="3V3",
        voltage=_voltage(3.3, 3.0, 3.6),
        provenance=_INF_PROV,
    )]
    power_seq = PowerSequence(rails=power_rails, dependencies=[])

    # --- Metadata ---
    metadata = HIRMetadata(
        created_at=datetime.now(timezone.utc).isoformat(),
        track=track,
        confidence=Confidence(
            overall=0.9 if track == "A" else 0.75,
            explanations=["Derived from schematic with KB lookup" if track == "A" else "Boardsmith synthesis"],
        ),
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
        bom=[],
        metadata=metadata,
    )
