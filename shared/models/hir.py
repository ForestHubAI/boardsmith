# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canonical Hardware Intermediate Representation (HIR) — Pydantic models v1.1.0."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

class SourceType(str, Enum):
    schematic = "schematic"
    prompt = "prompt"
    builtin_db = "builtin_db"
    cache = "cache"
    datasheet = "datasheet"
    user_input = "user_input"
    inference = "inference"


class Provenance(BaseModel):
    source_type: SourceType
    source_ref: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class Voltage(BaseModel):
    nominal: float
    min: float | None = None
    max: float | None = None
    unit: str = "V"

    def contains(self, value: float) -> bool:
        """True if value is within [min, max] (or ±10% tolerance if min/max not set)."""
        lo = self.min if self.min is not None else self.nominal * 0.9
        hi = self.max if self.max is not None else self.nominal * 1.1
        return lo <= value <= hi


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------

class ComponentRole(str, Enum):
    mcu = "mcu"
    sensor = "sensor"
    actuator = "actuator"
    memory = "memory"
    power = "power"
    comms = "comms"
    passive = "passive"
    analog = "analog"   # op-amps, comparators, voltage references, analog mux
    other = "other"


class InterfaceType(str, Enum):
    I2C = "I2C"
    SPI = "SPI"
    UART = "UART"
    GPIO = "GPIO"
    ADC = "ADC"
    PWM = "PWM"
    CAN = "CAN"
    ANALOG_IN  = "ANALOG_IN"   # analog signal input pin (op-amp IN+/IN−, comparator)
    ANALOG_OUT = "ANALOG_OUT"  # analog signal output pin (op-amp OUT, DAC VOUT)
    OTHER = "OTHER"


class Pin(BaseModel):
    name: str
    number: str | None = None
    function: str | None = None
    electrical_type: str | None = None


class Component(BaseModel):
    id: str
    name: str
    role: ComponentRole
    manufacturer: str | None = None
    mpn: str
    package: str | None = None
    interface_types: list[InterfaceType]
    pins: list[Pin] = Field(default_factory=list)
    provenance: Provenance | None = None


# ---------------------------------------------------------------------------
# Nets
# ---------------------------------------------------------------------------

class NetPin(BaseModel):
    component_id: str
    pin_name: str


class Net(BaseModel):
    name: str
    pins: list[NetPin]
    is_bus: bool = False
    is_power: bool = False
    provenance: Provenance | None = None


# ---------------------------------------------------------------------------
# Buses
# ---------------------------------------------------------------------------

class BusType(str, Enum):
    I2C = "I2C"
    SPI = "SPI"
    UART = "UART"
    GPIO = "GPIO"
    ADC = "ADC"
    PWM = "PWM"
    CAN = "CAN"
    OTHER = "OTHER"


class PinMapping(BaseModel):
    signal: str
    net: str
    mcu_pin_name: str | None = None
    gpio: str | None = None


class Bus(BaseModel):
    name: str
    type: BusType
    master_component_id: str
    slave_component_ids: list[str]
    pin_mapping: list[PinMapping] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Bus contracts (protocol-level specs)
# ---------------------------------------------------------------------------

class I2CSpec(BaseModel):
    address: str | None = None          # hex string e.g. "0x76"
    address_bits: int = Field(default=7, ge=7)
    max_clock_hz: int | None = None
    min_clock_hz: int | None = None
    t_rise_ns: int | None = None
    t_fall_ns: int | None = None
    t_su_dat_ns: int | None = None
    t_hd_dat_ns: int | None = None
    t_su_sta_ns: int | None = None
    t_buf_ns: int | None = None
    pullup_ohm_min: int | None = None
    pullup_ohm_max: int | None = None
    bus_capacitance_pf_max: int | None = None


class SPISpec(BaseModel):
    max_clock_hz: int | None = None
    mode: int | None = Field(default=None, ge=0, le=3)
    bit_order: str | None = None        # "MSB" | "LSB"
    cs_active: str | None = None        # "low" | "high"
    cs_setup_ns: int | None = None
    cs_hold_ns: int | None = None


class UARTSpec(BaseModel):
    baud_rate: int | None = None
    data_bits: int | None = None
    stop_bits: int | None = None
    parity: str | None = None           # "none" | "even" | "odd"
    flow_control: str | None = None     # "none" | "rts_cts" | "xon_xoff"


class BusContract(BaseModel):
    bus_name: str
    bus_type: str                       # "I2C" | "SPI" | "UART"
    master_id: str = ""
    slave_ids: list[str] = Field(default_factory=list)
    configured_clock_hz: int | None = None
    pin_assignments: dict[str, str] = Field(default_factory=dict)  # signal -> gpio
    slave_addresses: dict[str, str] = Field(default_factory=dict)  # slave_id -> hex addr
    i2c: I2CSpec | None = None
    spi: SPISpec | None = None
    uart: UARTSpec | None = None
    provenance: Provenance | None = None


# ---------------------------------------------------------------------------
# Electrical specs
# ---------------------------------------------------------------------------

class CurrentDraw(BaseModel):
    typical: float | None = None
    max: float | None = None
    unit: str = "mA"


class ElectricalSpec(BaseModel):
    component_id: str
    supply_voltage: Voltage | None = None
    io_voltage: Voltage | None = None
    logic_high_min: float | None = None
    logic_low_max: float | None = None
    current_draw: CurrentDraw | None = None
    is_5v_tolerant: bool | None = None
    drive_strength_ma: float | None = None
    input_capacitance_pf: float | None = None
    abs_max_voltage: float | None = None
    temp_min_c: float | None = None
    temp_max_c: float | None = None
    provenance: Provenance | None = None


# ---------------------------------------------------------------------------
# Init contracts
# ---------------------------------------------------------------------------

class RegWrite(BaseModel):
    reg_addr: str       # hex "0x..."
    value: str          # hex "0x..."
    description: str | None = None
    purpose: str | None = None


class RegRead(BaseModel):
    reg_addr: str
    expected_value: str | None = None
    mask: str | None = None
    description: str | None = None
    purpose: str | None = None


class InitPhaseTag(str, Enum):
    reset = "reset"
    configure = "configure"
    calibrate = "calibrate"
    enable = "enable"
    verify = "verify"


class InitPhase(BaseModel):
    phase: InitPhaseTag
    order: int = Field(ge=0)
    writes: list[RegWrite] = Field(default_factory=list)
    reads: list[RegRead] = Field(default_factory=list)
    delay_after_ms: int | None = None
    precondition: str | None = None
    postcondition: str | None = None
    provenance: Provenance | None = None


class InitContract(BaseModel):
    component_id: str
    component_name: str | None = None
    phases: list[InitPhase] = Field(default_factory=list)
    irq_gpio: str | None = None      # GPIO number for interrupt/alert pin, e.g. "4"
    irq_trigger: str = "falling"     # "falling" | "rising" | "change"


# ---------------------------------------------------------------------------
# Power sequence
# ---------------------------------------------------------------------------

class PowerRail(BaseModel):
    name: str
    voltage: Voltage
    max_current_ma: float | None = None
    enable_gpio: str | None = None
    startup_delay_ms: int | None = None
    provenance: Provenance | None = None


class PowerDependency(BaseModel):
    source: str
    target: str
    min_delay_ms: int | None = None
    description: str | None = None
    provenance: Provenance | None = None


class PowerSequence(BaseModel):
    rails: list[PowerRail] = Field(default_factory=list)
    dependencies: list[PowerDependency] = Field(default_factory=list)

    def get_startup_order(self) -> list[str]:
        """Return rail names in topological startup order (dependencies first).
        Returns empty list if a circular dependency is detected.
        """
        # Build adjacency: source must come before target
        graph: dict[str, set[str]] = {}
        all_nodes: set[str] = set()
        for dep in self.dependencies:
            all_nodes.add(dep.source)
            all_nodes.add(dep.target)
            graph.setdefault(dep.source, set()).add(dep.target)
            graph.setdefault(dep.target, set())
        for rail in self.rails:
            all_nodes.add(rail.name)
            graph.setdefault(rail.name, set())

        # Kahn's algorithm for topological sort
        in_degree: dict[str, int] = {n: 0 for n in all_nodes}
        for src, targets in graph.items():
            for tgt in targets:
                in_degree[tgt] = in_degree.get(tgt, 0) + 1

        queue = [n for n in all_nodes if in_degree[n] == 0]
        queue.sort()
        order: list[str] = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for neighbor in sorted(graph.get(node, [])):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(all_nodes):
            return []  # circular dependency detected
        return order


# ---------------------------------------------------------------------------
# Constraints / diagnostics
# ---------------------------------------------------------------------------

class ConstraintCategory(str, Enum):
    electrical = "electrical"
    timing = "timing"
    protocol = "protocol"
    power = "power"
    topology = "topology"
    knowledge = "knowledge"
    signal_integrity = "signal_integrity"


class Severity(str, Enum):
    error = "error"
    warning = "warning"
    info = "info"
    # Uppercase aliases for v1.0 backward compatibility (ConstraintSeverity.ERROR etc.)
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ConstraintStatus(str, Enum):
    pass_ = "pass"
    fail = "fail"
    unknown = "unknown"
    # Uppercase aliases for v1.0 backward compatibility
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"

    # Allow "pass" as value name (Python keyword workaround)
    @classmethod
    def _missing_(cls, value: object) -> "ConstraintStatus | None":
        if value == "pass":
            return cls.pass_
        return None


class Constraint(BaseModel):
    id: str
    category: ConstraintCategory | str
    description: str
    severity: Severity = Severity.info
    status: ConstraintStatus = ConstraintStatus.unknown
    details: str | None = None
    affected_components: list[str] = Field(default_factory=list)
    suggested_fixes: list[str] = Field(default_factory=list)
    path: str | None = None
    provenance: Provenance | None = None

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        d = super().model_dump(**kwargs)
        # Normalize "pass_" -> "pass" in output
        if d.get("status") == "pass_":
            d["status"] = "pass"
        return d


# ---------------------------------------------------------------------------
# BOM
# ---------------------------------------------------------------------------

class BOMEntry(BaseModel):
    line_id: str
    component_id: str
    mpn: str
    manufacturer: str | None = None
    description: str | None = None
    qty: float = Field(ge=1)
    unit_cost_estimate: float | None = None
    currency: str = "USD"
    availability: str | None = None
    provenance: Provenance | None = None


# ---------------------------------------------------------------------------
# Metadata / confidence
# ---------------------------------------------------------------------------

class ConfidenceSubscores(BaseModel):
    intent: float | None = Field(default=None, ge=0.0, le=1.0)
    components: float | None = Field(default=None, ge=0.0, le=1.0)
    topology: float | None = Field(default=None, ge=0.0, le=1.0)
    electrical: float | None = Field(default=None, ge=0.0, le=1.0)


class Confidence(BaseModel):
    overall: float = Field(ge=0.0, le=1.0)
    subscores: ConfidenceSubscores | None = None
    explanations: list[str] = Field(default_factory=list)


class HIRMetadata(BaseModel):
    created_at: str         # ISO 8601 datetime
    track: str              # "A" | "B"
    confidence: Confidence
    assumptions: list[str] = Field(default_factory=list)
    session_id: str | None = None


# ---------------------------------------------------------------------------
# Root HIR
# ---------------------------------------------------------------------------

class HIR(BaseModel):
    version: str = "1.1.0"
    source: str = ""                    # "prompt" | "schematic" | "hybrid"
    components: list[Component] = Field(default_factory=list)
    nets: list[Net] = Field(default_factory=list)
    buses: list[Bus] = Field(default_factory=list)
    bus_contracts: list[BusContract] = Field(default_factory=list)
    electrical_specs: list[ElectricalSpec] = Field(default_factory=list)
    init_contracts: list[InitContract] = Field(default_factory=list)
    power_sequence: PowerSequence = Field(default_factory=PowerSequence)
    constraints: list[Constraint] = Field(default_factory=list)
    bom: list[BOMEntry] = Field(default_factory=list)
    metadata: HIRMetadata | None = None

    # ------------------------------------------------------------------
    # Query helpers (v1.0 API — kept for backward compatibility)
    # ------------------------------------------------------------------

    def get_bus_contract(self, bus_name: str) -> "BusContract | None":
        return next((b for b in self.bus_contracts if b.bus_name == bus_name), None)

    def get_init_contract(self, component_id: str) -> "InitContract | None":
        return next((c for c in self.init_contracts if c.component_id == component_id), None)

    def get_electrical_spec(self, component_id: str) -> "ElectricalSpec | None":
        return next((e for e in self.electrical_specs if e.component_id == component_id), None)

    def get_failing_constraints(self) -> "list[Constraint]":
        return [c for c in self.constraints if c.status == ConstraintStatus.fail]

    def get_errors(self) -> "list[Constraint]":
        return [
            c for c in self.constraints
            if c.status == ConstraintStatus.fail and c.severity == Severity.error
        ]

    def is_valid(self) -> bool:
        """True if no ERROR-severity constraints are failing."""
        return len(self.get_errors()) == 0

    def _ensure_metadata(self) -> HIRMetadata:
        """Return metadata, creating a default Track-A metadata if not set."""
        if self.metadata is not None:
            return self.metadata
        return HIRMetadata(
            created_at=datetime.now(timezone.utc).isoformat(),
            track="A",
            confidence=Confidence(overall=1.0),
        )

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        d = super().model_dump(**kwargs)
        # Fix status "pass_" → "pass" in constraints
        for c in d.get("constraints", []):
            if c.get("status") == "pass_":
                c["status"] = "pass"
        return d
