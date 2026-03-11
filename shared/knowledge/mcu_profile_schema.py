# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCU Device Profile schema — Hardware Knowledge Layer (Domains 1–12).

Every MCU in the knowledge DB gets a complete Reference Design Model:
pins, power domains, clocking, boot/reset, debug, mandatory components,
IO rules, peripheral patterns, layout constraints, firmware bindings,
and provenance metadata.

See DBroadmap.md for the full specification.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Domain 1 — Identity & Variants
# ---------------------------------------------------------------------------

class TemperatureGrade(str, Enum):
    commercial = "commercial"      # 0°C to +70°C
    industrial = "industrial"      # -40°C to +85°C
    automotive = "automotive"      # -40°C to +125°C
    military = "military"          # -55°C to +125°C
    extended = "extended"          # -40°C to +105°C


class DatasheetRef(BaseModel):
    url: str
    version: str | None = None
    date: str | None = None        # ISO date


class MCUIdentity(BaseModel):
    """Domain 1: Extended identity beyond ComponentEntry."""
    vendor: str                    # "Espressif", "STMicroelectronics"
    family: str                    # "ESP32-S3", "STM32G4"
    series: str                    # "ESP32-S3-WROOM-1", "STM32G431"
    mpn: str                       # Full MPN: "ESP32-S3-WROOM-1-N16R8"
    package: str
    pin_count: int
    temperature_grade: TemperatureGrade = TemperatureGrade.industrial
    lifecycle_status: str = "active"
    datasheet_refs: list[DatasheetRef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Domain 2 — Pinout & Multiplexing
# ---------------------------------------------------------------------------

class PinType(str, Enum):
    gpio = "gpio"
    analog = "analog"
    power = "power"
    ground = "ground"
    reset = "reset"
    boot = "boot"
    osc = "osc"
    debug = "debug"
    nc = "nc"                      # no connect
    rf = "rf"                      # antenna / RF trace


class AltFunction(BaseModel):
    function: str                  # "I2C1_SCL", "SPI2_MOSI", "UART3_TX"
    af_number: int | None = None   # STM32: AF0–AF15
    available_modes: list[str] = Field(default_factory=list)


class PinElectrical(BaseModel):
    max_source_ma: float | None = None
    max_sink_ma: float | None = None
    is_5v_tolerant: bool = False
    has_internal_pullup: bool = False
    has_internal_pulldown: bool = False
    pullup_value_ohm: int | None = None
    input_capacitance_pf: float | None = None


class PinDefinition(BaseModel):
    pin_name: str                  # "PA0", "GPIO21", "VDDIO"
    pin_number: str                # Package pad: "1", "A3"
    pin_type: PinType
    default_state: str | None = None   # "input_floating", "high_z", "pull_up"
    boot_strap: bool = False       # Relevant for boot mode?
    electrical: PinElectrical = Field(default_factory=PinElectrical)
    alt_functions: list[AltFunction] = Field(default_factory=list)


class ReservedPin(BaseModel):
    pin_name: str
    reason: str                    # "flash", "psram", "rf_antenna", "internal"
    can_use_as_gpio: bool = False


class PinMap(BaseModel):
    """A recommended pin mapping for a specific use case."""
    name: str                      # "i2c_default", "spi_safe"
    mappings: dict[str, str]       # {"SDA": "GPIO21", "SCL": "GPIO22"}


class MCUPinout(BaseModel):
    """Domain 2: Complete pin model."""
    pins: list[PinDefinition] = Field(default_factory=list)
    reserved_pins: list[ReservedPin] = Field(default_factory=list)
    recommended_pinmaps: list[PinMap] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Domain 3 — Power Tree & Rails
# ---------------------------------------------------------------------------

class CapSpec(BaseModel):
    value: str                     # "100nF", "10µF"
    type: str | None = None        # "X7R", "X5R", "C0G"
    package: str | None = None     # "0402", "0805"
    quantity: int = 1
    voltage_rating: str | None = None


class DecouplingRule(BaseModel):
    domain: str                    # "VDD", "VDDA"
    capacitors: list[CapSpec]
    placement_rule: str            # "within 3mm of pin group"
    pin_group: list[str] = Field(default_factory=list)
    notes: str = ""


class PowerDomain(BaseModel):
    """Domain 3.1: A power domain on the MCU."""
    name: str                      # "VDD", "VDDIO", "VDDA", "VDDUSB", "VBAT"
    nominal_voltage: float
    allowed_range: tuple[float, float]
    max_current_draw_ma: float
    sequencing_order: int | None = None
    ramp_time_ms: float | None = None
    decoupling: list[DecouplingRule] = Field(default_factory=list)
    connected_pin_groups: list[str] = Field(default_factory=list)


class PassiveSpec(BaseModel):
    component_type: str            # "inductor", "capacitor", "resistor"
    value: str
    spec: str | None = None        # "shielded 4.7µH"
    package: str | None = None


class RegulatorOption(BaseModel):
    """Domain 3.3: Recommended voltage regulator."""
    topology: str                  # "ldo" | "buck" | "boost" | "buck_boost"
    recommended_mpns: list[str] = Field(default_factory=list)
    output_voltage: float
    max_current_ma: float
    dropout_voltage: float | None = None
    required_passives: list[PassiveSpec] = Field(default_factory=list)


class ProtectionSpec(BaseModel):
    component_type: str            # "tvs", "schottky", "fuse", "polyfuse"
    recommended_mpns: list[str] = Field(default_factory=list)
    notes: str = ""


class PowerInputPattern(BaseModel):
    """Domain 3.3: Common power input topologies."""
    name: str                      # "usb_5v", "lipo_3v7", "industrial_24v"
    input_voltage_range: tuple[float, float]
    recommended_regulators: list[RegulatorOption] = Field(default_factory=list)
    mandatory_protection: list[ProtectionSpec] = Field(default_factory=list)


class MCUPowerTree(BaseModel):
    """Domain 3: Complete power model."""
    power_domains: list[PowerDomain] = Field(default_factory=list)
    power_input_patterns: list[PowerInputPattern] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Domain 4 — Clocking
# ---------------------------------------------------------------------------

class ClockSourceType(str, Enum):
    internal_rc = "internal_rc"
    external_xtal = "external_xtal"
    external_osc = "external_osc"


class ClockSource(BaseModel):
    type: ClockSourceType
    frequency_hz: int
    accuracy_ppm: int | None = None
    load_capacitance_pf: float | None = None
    recommended_crystals: list[str] = Field(default_factory=list)
    required_caps: list[CapSpec] = Field(default_factory=list)
    layout_constraints: list[str] = Field(default_factory=list)
    osc_pins: list[str] = Field(default_factory=list)


class PLLConfig(BaseModel):
    input_source: str              # "HSE", "HSI", "main_xtal"
    input_divider: int | None = None
    multiplier: int | None = None
    output_divider: int | None = None
    max_output_hz: int | None = None


class ClockConfig(BaseModel):
    """Domain 4: Clock tree model."""
    main_clock: ClockSource
    rtc_clock: ClockSource | None = None
    pll_config: PLLConfig | None = None
    safe_default_mhz: int          # Safe startup frequency (e.g. 8 MHz internal RC)


# ---------------------------------------------------------------------------
# Domain 5 — Reset / Boot / Strap Pins
# ---------------------------------------------------------------------------

class ResetCircuit(BaseModel):
    nrst_pin: str
    recommended_pullup_ohm: int = 10000
    cap_to_gnd_nf: float | None = None
    supervisor_ic: str | None = None


class BootModePin(BaseModel):
    pin: str
    normal_boot_state: str         # "low" | "high"
    pull_resistor: str             # "pull_down_10k" | "pull_up_10k"
    dont_use_as_gpio_until_boot: bool = True
    notes: str = ""


class BootConfig(BaseModel):
    """Domain 5: Reset and boot configuration."""
    reset_circuit: ResetCircuit
    boot_mode_pins: list[BootModePin] = Field(default_factory=list)
    programming_mode_entry: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Domain 6 — Programming & Debug
# ---------------------------------------------------------------------------

class ConnectorSpec(BaseModel):
    name: str                      # "ARM SWD 2x5 1.27mm"
    footprint: str
    alt_footprint: str | None = None
    pinout: dict[str, int] = Field(default_factory=dict)


class DebugInterface(BaseModel):
    """Domain 6: Debug/programming interface."""
    protocol: str                  # "SWD" | "JTAG" | "UART_bootloader" | "USB_DFU"
    pins: dict[str, str]           # {"SWDIO": "PA13", "SWCLK": "PA14"}
    recommended_connector: ConnectorSpec | None = None
    pin_protection: list[ProtectionSpec] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Domain 7 — Mandatory External Components
# ---------------------------------------------------------------------------

class NetTemplate(BaseModel):
    """Which net to connect to which pins."""
    net_name: str
    connected_pins: list[str] = Field(default_factory=list)


class MandatoryComponent(BaseModel):
    """Domain 7: A component that MUST be on the board for this MCU."""
    component_type: str            # "cap" | "resistor" | "crystal" | "tvs" | "inductor" | "ferrite"
    value: str                     # "100nF", "10kΩ", "12pF"
    spec: str = ""                 # "X7R 0402 ±10%"
    quantity_rule: str             # "per_vdd_pin" | "per_rail" | "one_per_board" | "per_bus"
    connectivity: NetTemplate | None = None
    placement: str = ""            # "within 3mm of VDD pin group"
    rationale: str = ""            # "Datasheet Section 4.2: 100nF ceramic per VDD"


# ---------------------------------------------------------------------------
# Domain 8 — IO Electrical Rules
# ---------------------------------------------------------------------------

class LevelShifterSpec(BaseModel):
    from_voltage: float
    to_voltage: float
    recommended_ics: list[str] = Field(default_factory=list)
    bidirectional: bool = True


class IOElectricalRules(BaseModel):
    """Domain 8: Extended IO electrical rules."""
    io_voltage_tolerance_per_domain: dict[str, tuple[float, float]] = Field(default_factory=dict)
    max_source_current_per_pin_ma: float | None = None
    max_sink_current_per_pin_ma: float | None = None
    max_total_current_per_port_ma: float | None = None
    adc_input_range: tuple[float, float] | None = None
    adc_source_impedance_max_ohm: float | None = None
    adc_sampling_cap_pf: float | None = None
    analog_domain_rules: list[str] = Field(default_factory=list)
    esd_rating_hbm_v: int | None = None
    level_shifter_recommendations: list[LevelShifterSpec] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Domain 9 — Peripheral Reference Patterns
# ---------------------------------------------------------------------------

class I2CPattern(BaseModel):
    pullup_value_rule: str         # "4.7kΩ for ≤100kHz, 2.2kΩ for 400kHz"
    pullup_formula: str = "R = t_rise / (0.8473 × C_bus)"
    max_bus_capacitance_pf: int = 400
    recommended_pins: dict[str, list[str]] = Field(default_factory=dict)
    max_devices_per_bus: int = 8


class SPIPattern(BaseModel):
    series_resistor_sck_ohm: int | None = None
    cs_pullup: bool = True
    max_freq_mhz: int = 40
    recommended_pins: dict[str, list[str]] = Field(default_factory=dict)


class UARTPattern(BaseModel):
    recommended_level_shifter: str | None = None
    rx_tx_series_resistor: int | None = None


class CANPattern(BaseModel):
    requires_transceiver: bool = True
    recommended_transceivers: list[str] = Field(default_factory=list)
    termination_resistor_ohm: int = 120


class USBPattern(BaseModel):
    dp_dm_series_resistor_ohm: int = 27
    esd_protection_ic: str | None = None
    connector_footprint: str | None = None
    vbus_protection: str | None = None


class RFPattern(BaseModel):
    keepout_zone_mm: float = 15.0
    matching_network: str | None = None
    ground_plane_requirement: str = ""


class PeripheralPatterns(BaseModel):
    """Domain 9: Reference patterns for standard peripherals."""
    i2c: I2CPattern | None = None
    spi: SPIPattern | None = None
    uart: UARTPattern | None = None
    can: CANPattern | None = None
    usb: USBPattern | None = None
    rf: RFPattern | None = None


# ---------------------------------------------------------------------------
# Domain 10 — PCB / Layout Constraints
# ---------------------------------------------------------------------------

class KeepoutZone(BaseModel):
    name: str                      # "RF antenna", "crystal"
    type: str                      # "no_copper" | "no_component" | "no_via"
    reference_component: str = ""
    area_mm: tuple[float, float] | None = None
    side: str = "top"              # "top" | "bottom" | "both"


class RoutingRule(BaseModel):
    net_class: str                 # "usb_dp_dm" | "power" | "signal"
    trace_width_mm: float
    impedance_ohm: float | None = None
    differential_pair: bool = False
    length_match_mm: float | None = None


class PlacementRule(BaseModel):
    component_type: str            # "decoupling_cap" | "crystal" | "regulator"
    max_distance_mm: float
    reference_pin: str
    layer: str = "same_layer"


class LayoutConstraints(BaseModel):
    """Domain 10: PCB/layout constraints."""
    keepout_zones: list[KeepoutZone] = Field(default_factory=list)
    routing_constraints: list[RoutingRule] = Field(default_factory=list)
    placement_constraints: list[PlacementRule] = Field(default_factory=list)
    stackup_recommendation: str = "2-layer"


# ---------------------------------------------------------------------------
# Domain 11 — Firmware Binding
# ---------------------------------------------------------------------------

class BusConfig(BaseModel):
    bus_type: str                  # "I2C", "SPI", "UART"
    default_speed_hz: int
    default_mode: str | None = None


class FirmwareBinding(BaseModel):
    """Domain 11: Firmware integration hints."""
    clock_tree_defaults: dict[str, Any] = Field(default_factory=dict)
    bus_init_defaults: dict[str, BusConfig] = Field(default_factory=dict)
    pinmux_templates: dict[str, str] = Field(default_factory=dict)
    bootloader_options: list[str] = Field(default_factory=list)
    rtos_hooks: dict[str, str] | None = None
    sdk_framework: str = ""        # "esp-idf" | "pico-sdk" | "stm32hal" | "zephyr"


# ---------------------------------------------------------------------------
# Domain 12 — Provenance & Confidence
# ---------------------------------------------------------------------------

class AttributeProvenance(BaseModel):
    """Domain 12: Per-attribute provenance tracking."""
    source_ref: str                # "ESP32-S3 Datasheet v1.3, Section 4.2.1"
    source_type: str               # "datasheet" | "app_note" | "sdk_header" | "community" | "lab_verified"
    verification_status: str = "unverified"
    confidence_score: float = Field(ge=0.0, le=1.0, default=0.7)
    last_validated_date: str | None = None
    validated_against: str | None = None


# ---------------------------------------------------------------------------
# Top-Level Composite: MCU Device Profile
# ---------------------------------------------------------------------------

class MCUDeviceProfile(BaseModel):
    """Complete MCU Device Profile — Layer 1 Hardware Knowledge.

    One per MPN. Contains everything needed to correctly place an MCU
    on a board and generate valid firmware for it.
    """
    # Domain 1 — Identity
    identity: MCUIdentity

    # Domain 2 — Pinout
    pinout: MCUPinout = Field(default_factory=MCUPinout)

    # Domain 3 — Power
    power: MCUPowerTree = Field(default_factory=MCUPowerTree)

    # Domain 4 — Clocking
    clock: ClockConfig | None = None

    # Domain 5 — Boot/Reset
    boot: BootConfig | None = None

    # Domain 6 — Debug
    debug_interfaces: list[DebugInterface] = Field(default_factory=list)

    # Domain 7 — Mandatory Components
    mandatory_components: list[MandatoryComponent] = Field(default_factory=list)

    # Domain 8 — IO Rules
    io_rules: IOElectricalRules = Field(default_factory=IOElectricalRules)

    # Domain 9 — Peripheral Patterns
    peripheral_patterns: PeripheralPatterns = Field(default_factory=PeripheralPatterns)

    # Domain 10 — Layout Constraints
    layout: LayoutConstraints = Field(default_factory=LayoutConstraints)

    # Domain 11 — Firmware Binding
    firmware: FirmwareBinding = Field(default_factory=FirmwareBinding)

    # Domain 12 — Provenance
    provenance: list[AttributeProvenance] = Field(default_factory=list)
