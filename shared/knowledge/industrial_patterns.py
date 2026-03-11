# SPDX-License-Identifier: AGPL-3.0-or-later
"""Industrial Pattern Library — versionierte, parametrisierbare Schaltungs-Patterns.

Each IndustrialPattern is a first-class entity that captures a validated
subcircuit block for industrial/professional use:

  - Power input protection chains (24V, reverse polarity, surge)
  - Bus interface protection (USB, RS485, CAN, Ethernet, I2C, SPI)
  - Battery management (charging, power path, protection)
  - ADC input conditioning (divider, clamp, filter)

Patterns are:
  - Parametrisierbar (voltage, current, speed class)
  - Versioniert (semantic versioning)
  - Testbar (ERC/DRC checks als Constraints)
  - Quality-gated (draft → validated → verified)

Usage::

    lib = IndustrialPatternLibrary()
    pattern = lib.get("24v_input_protection_v1")
    # -> IndustrialPattern(...)
    patterns = lib.find_by_category("power_input")
    # -> [IndustrialPattern(...), ...]
    patterns = lib.find_by_keyword("rs485")
    # -> [IndustrialPattern(...)]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ParamSpec:
    """Specification for a pattern parameter."""
    name: str
    type: str                    # "float" | "int" | "str" | "enum"
    default: Any
    description: str = ""
    min: float | None = None
    max: float | None = None
    enum_values: list[str] | None = None


@dataclass
class PatternComponent:
    """A component role within a pattern."""
    role: str                    # "fuse", "tvs", "buck", "esd", "transceiver"
    category: str                # "power" | "comms" | "passive" | "protection"
    required: bool = True
    recommended_mpns: list[str] = field(default_factory=list)
    value_expr: str = ""         # expression for passives, e.g. "120" for Ω
    unit: str = ""               # "Ω" | "F" | "V" | ""
    package: str = ""
    constraints: list[str] = field(default_factory=list)  # e.g. ["V_rating >= V_in * 1.5"]


@dataclass
class PatternNet:
    """A net within the pattern."""
    name: str                    # "{prefix}_VIN", "{prefix}_VOUT"
    connected_roles: list[tuple[str, str]] = field(default_factory=list)  # (role, pin)
    is_power: bool = False
    is_bus: bool = False


@dataclass
class PlacementHint:
    """PCB placement constraint for a component within the pattern."""
    role: str                    # Which component role
    constraint: str              # "within 5mm of connector"
    priority: str = "required"   # "required" | "recommended"


@dataclass
class PatternTestCase:
    """A validation test case for the pattern."""
    name: str
    check_type: str              # "erc" | "drc" | "simulation" | "connectivity"
    description: str = ""
    expected_result: str = "pass"


@dataclass
class IndustrialPattern:
    """A versionierte, parametrisierbare industrielle Schaltungs-Pattern."""
    id: str                              # "24v_input_protection_v1"
    version: str                         # "1.0.0"
    name: str
    description: str
    category: str                        # "power_input" | "bus_protection" | "battery" | "analog_frontend"
    keywords: list[str]                  # lower-case trigger words
    parameters: list[ParamSpec] = field(default_factory=list)
    components: list[PatternComponent] = field(default_factory=list)
    nets: list[PatternNet] = field(default_factory=list)
    placement_hints: list[PlacementHint] = field(default_factory=list)
    erc_checks: list[str] = field(default_factory=list)
    drc_checks: list[str] = field(default_factory=list)
    test_cases: list[PatternTestCase] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    quality_state: str = "validated"     # "draft" | "validated" | "verified"


# ---------------------------------------------------------------------------
# Built-in industrial patterns (10)
# ---------------------------------------------------------------------------

_PATTERNS: list[IndustrialPattern] = [

    # ------------------------------------------------------------------
    # 1. 24V Input Protection Chain
    # CONN → Fuse → TVS → Reverse-Polarity → LC Filter → Buck
    # ------------------------------------------------------------------
    IndustrialPattern(
        id="24v_input_protection_v1",
        version="1.0.0",
        name="24V Industrial Input Protection",
        description=(
            "Complete 24V industrial power input chain: polyfuse for overcurrent, "
            "TVS for surge/transient (IEC 61000-4-5), MOSFET reverse polarity "
            "protection, LC input filter, and step-down regulator to 3.3V/5V. "
            "Suitable for factory automation, sensor nodes, and DIN-rail devices."
        ),
        category="power_input",
        keywords=[
            "24v", "industrial", "power input", "schutz", "protection",
            "din rail", "hutschiene", "factory", "automation",
            "surge", "transient", "reverse polarity", "verpolschutz",
            "iec 61000", "input protection", "eingangsschutz",
        ],
        parameters=[
            ParamSpec("v_in_nom", "float", 24.0, "Nominal input voltage (V)", min=6.0, max=48.0),
            ParamSpec("i_max_a", "float", 1.0, "Maximum load current (A)", min=0.1, max=5.0),
            ParamSpec("v_out", "float", 3.3, "Output voltage (V)", enum_values=["3.3", "5.0"]),
        ],
        components=[
            PatternComponent(
                role="fuse",
                category="protection",
                recommended_mpns=["MF-MSMF050-2", "MF-MSMF110-2"],
                constraints=["I_hold >= i_max_a", "V_max >= v_in_nom * 1.5"],
            ),
            PatternComponent(
                role="tvs",
                category="protection",
                recommended_mpns=["SMBJ24CA", "SMAJ24CA"],
                constraints=["V_rwm >= v_in_nom", "V_br >= v_in_nom * 1.1"],
            ),
            PatternComponent(
                role="rev_pol_mosfet",
                category="protection",
                recommended_mpns=["IRF540N", "SI2301CDS-T1-GE3"],
                value_expr="",
                constraints=["Vds_max >= v_in_nom * 2", "Rds_on <= 50mΩ"],
            ),
            PatternComponent(
                role="input_cap",
                category="passive",
                value_expr="10e-6",
                unit="F",
                package="0805",
                constraints=["V_rating >= v_in_nom * 1.5", "ESR <= 50mΩ"],
            ),
            PatternComponent(
                role="lc_inductor",
                category="passive",
                value_expr="4.7e-6",
                unit="H",
                package="shielded",
                constraints=["I_sat >= i_max_a * 1.3"],
            ),
            PatternComponent(
                role="buck",
                category="power",
                recommended_mpns=["LM2596S-3.3", "LM2596S-5.0", "LM5164DDAR"],
                constraints=["V_in_max >= v_in_nom * 1.5", "I_out >= i_max_a"],
            ),
            PatternComponent(
                role="output_cap",
                category="passive",
                value_expr="100e-6",
                unit="F",
                package="electrolytic_smd",
                constraints=["V_rating >= v_out * 2"],
            ),
        ],
        nets=[
            PatternNet("{prefix}_VIN_RAW", connected_roles=[("fuse", "1")], is_power=True),
            PatternNet("{prefix}_VIN_FUSED", connected_roles=[("fuse", "2"), ("tvs", "1"), ("rev_pol_mosfet", "S")], is_power=True),
            PatternNet("{prefix}_VIN_PROT", connected_roles=[("rev_pol_mosfet", "D"), ("lc_inductor", "1"), ("input_cap", "1")], is_power=True),
            PatternNet("{prefix}_VIN_FILT", connected_roles=[("lc_inductor", "2"), ("buck", "VIN")], is_power=True),
            PatternNet("{prefix}_VOUT", connected_roles=[("buck", "VOUT"), ("output_cap", "1")], is_power=True),
            PatternNet("GND", connected_roles=[("tvs", "2"), ("input_cap", "2"), ("buck", "GND"), ("output_cap", "2")], is_power=True),
        ],
        placement_hints=[
            PlacementHint("fuse", "within 5mm of input connector", "required"),
            PlacementHint("tvs", "within 5mm of input connector, after fuse", "required"),
            PlacementHint("input_cap", "within 3mm of buck VIN pin", "required"),
            PlacementHint("output_cap", "within 3mm of buck VOUT pin", "required"),
        ],
        erc_checks=[
            "TVS clamping voltage < buck abs_max_vin",
            "Fuse I_trip > i_max_a * 1.25",
            "Buck V_in_max > TVS clamping voltage",
        ],
        drc_checks=[
            "Power traces >= 0.5mm width for i_max_a up to 2A",
            "GND return path uninterrupted from connector to buck GND",
        ],
        test_cases=[
            PatternTestCase("connectivity", "erc", "All power nets connected"),
            PatternTestCase("protection_order", "erc", "Fuse before TVS before buck"),
            PatternTestCase("voltage_headroom", "simulation", "TVS clamp < buck max VIN"),
        ],
        notes=[
            "Fuse → TVS → Rev-Pol → Filter → Buck is the canonical order",
            "TVS must be bidirectional for AC-coupled transients on DC rails",
            "Rev-Pol MOSFET: P-channel high-side or N-channel low-side",
            "LC filter reduces EMI from buck switching noise back to input",
        ],
    ),

    # ------------------------------------------------------------------
    # 2. USB Device MCU Pattern
    # USB-C → ESD → VBUS Sense → 5V → LDO → MCU
    # ------------------------------------------------------------------
    IndustrialPattern(
        id="usb_device_mcu_v1",
        version="1.0.0",
        name="USB Device MCU Interface",
        description=(
            "Complete USB-C device interface for MCU: USB-C connector with "
            "CC resistors (5.1kΩ for UFP/device), ESD protection on D+/D-/VBUS, "
            "VBUS ferrite bead, and 3.3V LDO from 5V VBUS. "
            "Supports USB 2.0 Full-Speed and Low-Speed."
        ),
        category="bus_protection",
        keywords=[
            "usb", "usb-c", "usb device", "type-c", "usb 2.0",
            "vbus", "esd", "usb connector", "usb interface",
            "usb power", "usb mcu",
        ],
        parameters=[
            ParamSpec("usb_speed", "enum", "full_speed", "USB speed class",
                      enum_values=["low_speed", "full_speed"]),
            ParamSpec("v_mcu", "float", 3.3, "MCU operating voltage (V)"),
        ],
        components=[
            PatternComponent(
                role="connector",
                category="connector",
                recommended_mpns=["USB-C-CONN"],
            ),
            PatternComponent(
                role="cc_r1",
                category="passive",
                value_expr="5100",
                unit="Ω",
                package="0402",
                constraints=["5.1kΩ ±1% for UFP (device) role"],
            ),
            PatternComponent(
                role="cc_r2",
                category="passive",
                value_expr="5100",
                unit="Ω",
                package="0402",
            ),
            PatternComponent(
                role="esd",
                category="protection",
                recommended_mpns=["USBLC6-2SC6"],
                constraints=["capacitance < 2pF per line"],
            ),
            PatternComponent(
                role="vbus_ferrite",
                category="passive",
                recommended_mpns=["BLM18BD102SN1D"],
                constraints=["I_rated >= 500mA"],
            ),
            PatternComponent(
                role="vbus_cap",
                category="passive",
                value_expr="10e-6",
                unit="F",
                package="0805",
            ),
            PatternComponent(
                role="dp_series_r",
                category="passive",
                value_expr="27",
                unit="Ω",
                package="0402",
            ),
            PatternComponent(
                role="dm_series_r",
                category="passive",
                value_expr="27",
                unit="Ω",
                package="0402",
            ),
            PatternComponent(
                role="ldo",
                category="power",
                recommended_mpns=["AMS1117-3.3", "MCP1700-3302E"],
                constraints=["V_out == v_mcu", "I_out >= 300mA"],
            ),
        ],
        nets=[
            PatternNet("{prefix}_VBUS", connected_roles=[("connector", "VBUS"), ("vbus_ferrite", "1")], is_power=True),
            PatternNet("{prefix}_VBUS_FILT", connected_roles=[("vbus_ferrite", "2"), ("vbus_cap", "1"), ("esd", "VBUS"), ("ldo", "VIN")], is_power=True),
            PatternNet("{prefix}_DP", connected_roles=[("connector", "D+"), ("esd", "IO1"), ("dp_series_r", "1")], is_bus=True),
            PatternNet("{prefix}_DM", connected_roles=[("connector", "D-"), ("esd", "IO2"), ("dm_series_r", "1")], is_bus=True),
            PatternNet("{prefix}_DP_MCU", connected_roles=[("dp_series_r", "2")], is_bus=True),
            PatternNet("{prefix}_DM_MCU", connected_roles=[("dm_series_r", "2")], is_bus=True),
            PatternNet("{prefix}_CC1", connected_roles=[("connector", "CC1"), ("cc_r1", "1")]),
            PatternNet("{prefix}_CC2", connected_roles=[("connector", "CC2"), ("cc_r2", "1")]),
            PatternNet("{prefix}_V_MCU", connected_roles=[("ldo", "VOUT")], is_power=True),
            PatternNet("GND", connected_roles=[("connector", "GND"), ("esd", "GND"), ("vbus_cap", "2"), ("cc_r1", "2"), ("cc_r2", "2"), ("ldo", "GND")], is_power=True),
        ],
        placement_hints=[
            PlacementHint("esd", "within 3mm of USB connector", "required"),
            PlacementHint("cc_r1", "within 5mm of USB connector CC pins", "required"),
            PlacementHint("dp_series_r", "between ESD and MCU, close to MCU", "recommended"),
            PlacementHint("vbus_cap", "within 3mm of LDO input", "required"),
        ],
        erc_checks=[
            "CC resistors = 5.1kΩ for device role",
            "ESD capacitance < 2pF per data line",
            "Series resistors on D+/D- = 27Ω for USB 2.0",
        ],
        notes=[
            "5.1kΩ CC resistors identify the port as UFP (device/sink)",
            "D+/D- traces should be 90Ω differential impedance",
            "ESD IC must be placed closest to connector, before series resistors",
        ],
    ),

    # ------------------------------------------------------------------
    # 3. RS-485 Node
    # ------------------------------------------------------------------
    IndustrialPattern(
        id="rs485_node_v1",
        version="1.0.0",
        name="RS-485 Bus Node",
        description=(
            "RS-485 half-duplex bus node: transceiver with ESD protection, "
            "termination resistor (120Ω, optional), bias resistors for idle "
            "bus state, and screw terminal connector. "
            "Suitable for Modbus RTU, industrial sensor networks."
        ),
        category="bus_protection",
        keywords=[
            "rs485", "rs-485", "modbus", "modbus rtu", "industrial bus",
            "halbduplex", "half-duplex", "differential", "differentiell",
            "feldbus", "fieldbus", "485", "transceiver",
        ],
        parameters=[
            ParamSpec("baudrate", "int", 9600, "Baud rate", min=300, max=10_000_000),
            ParamSpec("termination", "bool", True, "Include 120Ω termination"),
            ParamSpec("cable_length_m", "float", 100.0, "Max cable length (m)", min=1.0, max=1200.0),
        ],
        components=[
            PatternComponent(
                role="transceiver",
                category="comms",
                recommended_mpns=["SP3485EN", "MAX485ESA"],
                constraints=["V_io compatible with MCU logic level"],
            ),
            PatternComponent(
                role="esd",
                category="protection",
                recommended_mpns=["PESD3V3S2UT"],
                constraints=["TVS on A/B lines"],
            ),
            PatternComponent(
                role="term_r",
                category="passive",
                required=False,
                value_expr="120",
                unit="Ω",
                package="0402",
                constraints=["Only at end-of-line nodes"],
            ),
            PatternComponent(
                role="bias_r_pullup",
                category="passive",
                value_expr="560",
                unit="Ω",
                package="0402",
                constraints=["Bias A line high when bus idle"],
            ),
            PatternComponent(
                role="bias_r_pulldown",
                category="passive",
                value_expr="560",
                unit="Ω",
                package="0402",
                constraints=["Bias B line low when bus idle"],
            ),
            PatternComponent(
                role="decoupling",
                category="passive",
                value_expr="100e-9",
                unit="F",
                package="0402",
            ),
            PatternComponent(
                role="connector",
                category="connector",
                recommended_mpns=["CONN-RS485-2PIN"],
            ),
        ],
        nets=[
            PatternNet("{prefix}_A", connected_roles=[("transceiver", "A"), ("esd", "IO1"), ("term_r", "1"), ("bias_r_pullup", "2"), ("connector", "A")], is_bus=True),
            PatternNet("{prefix}_B", connected_roles=[("transceiver", "B"), ("esd", "IO2"), ("term_r", "2"), ("bias_r_pulldown", "1"), ("connector", "B")], is_bus=True),
            PatternNet("{prefix}_TX", connected_roles=[("transceiver", "DI")]),
            PatternNet("{prefix}_RX", connected_roles=[("transceiver", "RO")]),
            PatternNet("{prefix}_DE_RE", connected_roles=[("transceiver", "DE"), ("transceiver", "RE_N")]),
            PatternNet("{prefix}_VCC", connected_roles=[("transceiver", "VCC"), ("decoupling", "1"), ("bias_r_pullup", "1")], is_power=True),
            PatternNet("GND", connected_roles=[("transceiver", "GND"), ("esd", "GND"), ("decoupling", "2"), ("bias_r_pulldown", "2")], is_power=True),
        ],
        placement_hints=[
            PlacementHint("esd", "within 3mm of screw terminal connector", "required"),
            PlacementHint("transceiver", "within 10mm of connector", "recommended"),
            PlacementHint("decoupling", "within 3mm of transceiver VCC", "required"),
        ],
        erc_checks=[
            "DE and RE directly connected (half-duplex) or separately driven",
            "ESD TVS before transceiver A/B pins",
            "Bias resistors pull A high, B low for defined idle state",
        ],
        notes=[
            "120Ω termination only at BOTH ends of the bus (first and last node)",
            "Bias resistors ensure defined state when bus is idle (no driver active)",
            "DE/RE can be tied together for half-duplex with GPIO direction control",
            "For cable > 300m, reduce baud rate below 115200",
        ],
    ),

    # ------------------------------------------------------------------
    # 4. CAN / CAN-FD Node
    # ------------------------------------------------------------------
    IndustrialPattern(
        id="can_node_v1",
        version="1.0.0",
        name="CAN / CAN-FD Bus Node",
        description=(
            "CAN bus node with transceiver, 120Ω termination, ESD protection, "
            "common-mode choke for EMC, and screw terminal. "
            "Supports classic CAN (1 Mbps) and CAN-FD (5 Mbps)."
        ),
        category="bus_protection",
        keywords=[
            "can", "can-fd", "canbus", "can bus", "can transceiver",
            "automotive", "j1939", "canopen", "obdii", "obd2",
            "fahrzeug", "vehicle", "industrial can",
        ],
        parameters=[
            ParamSpec("speed_class", "enum", "can_fd", "CAN speed class",
                      enum_values=["classic_1m", "can_fd_2m", "can_fd_5m"]),
            ParamSpec("termination", "bool", True, "Include 120Ω termination"),
        ],
        components=[
            PatternComponent(
                role="transceiver",
                category="comms",
                recommended_mpns=["TCAN1042VDRQ1", "MCP2562FD-E/SN"],
                constraints=["CAN-FD capable if speed_class != classic_1m"],
            ),
            PatternComponent(
                role="esd",
                category="protection",
                recommended_mpns=["PESD5V0S2BT"],
                constraints=["Bidirectional TVS on CANH/CANL"],
            ),
            PatternComponent(
                role="cmc",
                category="passive",
                recommended_mpns=["DLW21HN900SQ2L"],
                constraints=["Common-mode impedance >= 90Ω at 100MHz"],
            ),
            PatternComponent(
                role="term_r",
                category="passive",
                required=False,
                value_expr="120",
                unit="Ω",
                package="0402",
            ),
            PatternComponent(
                role="decoupling",
                category="passive",
                value_expr="100e-9",
                unit="F",
                package="0402",
            ),
            PatternComponent(
                role="connector",
                category="connector",
                recommended_mpns=["CONN-CAN-2PIN"],
            ),
        ],
        nets=[
            PatternNet("{prefix}_CANH", connected_roles=[("transceiver", "CANH"), ("cmc", "1A"), ("esd", "IO1")], is_bus=True),
            PatternNet("{prefix}_CANL", connected_roles=[("transceiver", "CANL"), ("cmc", "1B"), ("esd", "IO2")], is_bus=True),
            PatternNet("{prefix}_CANH_BUS", connected_roles=[("cmc", "2A"), ("term_r", "1"), ("connector", "CANH")], is_bus=True),
            PatternNet("{prefix}_CANL_BUS", connected_roles=[("cmc", "2B"), ("term_r", "2"), ("connector", "CANL")], is_bus=True),
            PatternNet("{prefix}_TXD", connected_roles=[("transceiver", "TXD")]),
            PatternNet("{prefix}_RXD", connected_roles=[("transceiver", "RXD")]),
            PatternNet("{prefix}_VCC", connected_roles=[("transceiver", "VCC"), ("decoupling", "1")], is_power=True),
            PatternNet("GND", connected_roles=[("transceiver", "GND"), ("esd", "GND"), ("decoupling", "2")], is_power=True),
        ],
        placement_hints=[
            PlacementHint("esd", "within 3mm of CAN connector", "required"),
            PlacementHint("cmc", "between transceiver and connector", "required"),
            PlacementHint("decoupling", "within 3mm of transceiver VCC", "required"),
        ],
        erc_checks=[
            "ESD TVS before common-mode choke",
            "120Ω termination only at bus endpoints",
            "Common-mode choke between transceiver and connector",
        ],
        notes=[
            "Signal order: Transceiver → CMC → ESD → Connector",
            "120Ω termination at BOTH ends of bus only",
            "For CAN-FD, ensure transceiver supports data phase bit rate",
            "Split termination (2×60Ω + 4.7nF to GND) improves EMC",
        ],
    ),

    # ------------------------------------------------------------------
    # 5. Li-Ion Charging + Power Path
    # ------------------------------------------------------------------
    IndustrialPattern(
        id="liion_charging_powerpath_v1",
        version="1.0.0",
        name="Li-Ion Charging with Power Path",
        description=(
            "Single-cell Li-Ion/LiPo charging with USB input, battery protection "
            "(OVP, UVP, OCP), and power path management for simultaneous charge "
            "and system operation. Includes fuel gauge for battery monitoring."
        ),
        category="battery",
        keywords=[
            "battery", "batterie", "lipo", "li-ion", "lithium",
            "charging", "laden", "charger", "ladegerät",
            "power path", "load sharing", "fuel gauge",
            "akku", "battery management", "bms", "1s",
        ],
        parameters=[
            ParamSpec("charge_current_ma", "float", 500.0, "Charge current (mA)", min=100.0, max=1000.0),
            ParamSpec("v_out", "float", 3.3, "System output voltage (V)"),
        ],
        components=[
            PatternComponent(
                role="charger",
                category="power",
                recommended_mpns=["TP4056"],
                constraints=["V_in compatible with USB 5V", "I_charge = charge_current_ma"],
            ),
            PatternComponent(
                role="protection_ic",
                category="protection",
                recommended_mpns=["DW01A-G"],
                constraints=["1S Li-Ion protection: OVP 4.3V, UVP 2.4V, OCP"],
            ),
            PatternComponent(
                role="protection_mosfets",
                category="protection",
                recommended_mpns=["FS8205A"],
                constraints=["Dual N-MOSFET for charge/discharge switching"],
            ),
            PatternComponent(
                role="ldo",
                category="power",
                recommended_mpns=["MCP1700-3302E", "AMS1117-3.3"],
                constraints=["V_out == v_out", "V_dropout < 0.5V"],
            ),
            PatternComponent(
                role="bat_cap",
                category="passive",
                value_expr="10e-6",
                unit="F",
                package="0805",
            ),
            PatternComponent(
                role="out_cap",
                category="passive",
                value_expr="10e-6",
                unit="F",
                package="0805",
            ),
        ],
        nets=[
            PatternNet("{prefix}_VUSB", connected_roles=[("charger", "VIN")], is_power=True),
            PatternNet("{prefix}_VBAT", connected_roles=[("charger", "VBAT"), ("protection_ic", "VDD"), ("bat_cap", "1"), ("ldo", "VIN")], is_power=True),
            PatternNet("{prefix}_BAT_P", connected_roles=[("protection_mosfets", "S1")], is_power=True),
            PatternNet("{prefix}_BAT_N", connected_roles=[("protection_mosfets", "S2")]),
            PatternNet("{prefix}_VOUT", connected_roles=[("ldo", "VOUT"), ("out_cap", "1")], is_power=True),
            PatternNet("GND", connected_roles=[("charger", "GND"), ("bat_cap", "2"), ("ldo", "GND"), ("out_cap", "2")], is_power=True),
        ],
        placement_hints=[
            PlacementHint("charger", "near USB connector input", "required"),
            PlacementHint("protection_ic", "near battery connector", "required"),
            PlacementHint("bat_cap", "within 3mm of charger VBAT pin", "required"),
        ],
        erc_checks=[
            "Protection IC OVP threshold > charger float voltage (4.2V)",
            "Protection IC UVP threshold > LDO minimum VIN",
            "LDO dropout + v_out < battery min voltage (3.0V)",
        ],
        notes=[
            "DW01A + FS8205A is the standard 1S protection combo",
            "TP4056 Rprog sets charge current: 1.2kΩ = 1A, 2.4kΩ = 500mA",
            "For load sharing: add Schottky diode from VUSB to VOUT (bypass battery)",
            "Fuel gauge (MAX17048) optional on I2C for SOC monitoring",
        ],
    ),

    # ------------------------------------------------------------------
    # 6. ADC Input Protection
    # ------------------------------------------------------------------
    IndustrialPattern(
        id="adc_input_protection_v1",
        version="1.0.0",
        name="ADC Input Protection & Conditioning",
        description=(
            "Input protection and signal conditioning for MCU ADC pins: "
            "voltage divider to scale down high voltages, RC low-pass anti-aliasing "
            "filter, TVS/clamp diodes for overvoltage protection. "
            "Suitable for industrial sensor inputs (0-10V, 0-24V)."
        ),
        category="analog_frontend",
        keywords=[
            "adc", "analog input", "eingang", "schutz", "protection",
            "voltage divider", "spannungsteiler", "clamp", "anti-aliasing",
            "input conditioning", "signalaufbereitung", "0-10v", "0-24v",
            "adc protection", "adc filter",
        ],
        parameters=[
            ParamSpec("v_in_max", "float", 24.0, "Max input voltage (V)", min=3.3, max=60.0),
            ParamSpec("v_adc_max", "float", 3.3, "ADC reference voltage (V)"),
            ParamSpec("cutoff_hz", "float", 1000.0, "Anti-aliasing filter cutoff (Hz)", min=10.0),
        ],
        components=[
            PatternComponent(
                role="r_div_high",
                category="passive",
                value_expr="(v_in_max / v_adc_max - 1) * 10000",
                unit="Ω",
                package="0402",
                constraints=["±1% tolerance for accuracy"],
            ),
            PatternComponent(
                role="r_div_low",
                category="passive",
                value_expr="10000",
                unit="Ω",
                package="0402",
                constraints=["±1% tolerance for accuracy"],
            ),
            PatternComponent(
                role="r_filter",
                category="passive",
                value_expr="1000",
                unit="Ω",
                package="0402",
            ),
            PatternComponent(
                role="c_filter",
                category="passive",
                value_expr="1 / (2 * 3.14159 * cutoff_hz * 1000)",
                unit="F",
                package="0402",
                constraints=["X7R or C0G dielectric"],
            ),
            PatternComponent(
                role="clamp_tvs",
                category="protection",
                recommended_mpns=["PESD3V3S2UT"],
                constraints=["Clamp voltage < v_adc_max + 0.3V"],
            ),
        ],
        nets=[
            PatternNet("{prefix}_VIN", connected_roles=[("r_div_high", "1")]),
            PatternNet("{prefix}_DIV_MID", connected_roles=[("r_div_high", "2"), ("r_div_low", "1"), ("r_filter", "1")]),
            PatternNet("{prefix}_FILT", connected_roles=[("r_filter", "2"), ("c_filter", "1"), ("clamp_tvs", "IO1")]),
            PatternNet("{prefix}_ADC", connected_roles=[("clamp_tvs", "IO1")]),
            PatternNet("GND", connected_roles=[("r_div_low", "2"), ("c_filter", "2"), ("clamp_tvs", "GND")], is_power=True),
        ],
        placement_hints=[
            PlacementHint("clamp_tvs", "within 3mm of MCU ADC pin", "required"),
            PlacementHint("c_filter", "within 5mm of MCU ADC pin", "required"),
            PlacementHint("r_div_high", "near input connector", "recommended"),
        ],
        erc_checks=[
            "Divider output < v_adc_max at v_in_max",
            "TVS clamp voltage < ADC absolute max input",
            "Filter cutoff < ADC sample rate / 2 (Nyquist)",
        ],
        notes=[
            "R_div ratio: V_out = V_in × R_low / (R_high + R_low)",
            "Series R (r_filter) limits current into ADC pin during overvoltage",
            "TVS/clamp is last line of defense — place closest to MCU",
        ],
    ),

    # ------------------------------------------------------------------
    # 7. Ethernet RMII PHY
    # ------------------------------------------------------------------
    IndustrialPattern(
        id="ethernet_rmii_phy_v1",
        version="1.0.0",
        name="Ethernet RMII PHY Interface",
        description=(
            "10/100 Ethernet PHY interface using RMII: PHY IC, RJ45 with "
            "integrated magnetics, ESD protection, 50MHz clock, and "
            "decoupling. Connects to MCU via RMII bus."
        ),
        category="bus_protection",
        keywords=[
            "ethernet", "rmii", "phy", "10/100", "rj45", "lan",
            "netzwerk", "network", "tcp/ip", "magnetics",
            "ethernet phy", "phy interface",
        ],
        parameters=[
            ParamSpec("phy_mpn", "enum", "LAN8720A", "PHY IC",
                      enum_values=["LAN8720A", "KSZ8081RNAIA"]),
        ],
        components=[
            PatternComponent(
                role="phy",
                category="comms",
                recommended_mpns=["LAN8720A", "KSZ8081RNAIA"],
            ),
            PatternComponent(
                role="rj45_mag",
                category="connector",
                recommended_mpns=["HR911105A"],
                constraints=["Integrated magnetics, LED indicators"],
            ),
            PatternComponent(
                role="esd",
                category="protection",
                recommended_mpns=["PESD3V3S2UT"],
            ),
            PatternComponent(
                role="xtal_25mhz",
                category="passive",
                value_expr="25e6",
                unit="Hz",
                constraints=["25MHz crystal for PHY, 50MHz RMII clock derived internally"],
            ),
            PatternComponent(
                role="decoupling_avdd",
                category="passive",
                value_expr="100e-9",
                unit="F",
                package="0402",
            ),
            PatternComponent(
                role="decoupling_dvdd",
                category="passive",
                value_expr="100e-9",
                unit="F",
                package="0402",
            ),
            PatternComponent(
                role="bulk_cap",
                category="passive",
                value_expr="10e-6",
                unit="F",
                package="0805",
            ),
        ],
        nets=[
            PatternNet("{prefix}_TXD0", connected_roles=[("phy", "TXD0")], is_bus=True),
            PatternNet("{prefix}_TXD1", connected_roles=[("phy", "TXD1")], is_bus=True),
            PatternNet("{prefix}_TX_EN", connected_roles=[("phy", "TX_EN")], is_bus=True),
            PatternNet("{prefix}_RXD0", connected_roles=[("phy", "RXD0")], is_bus=True),
            PatternNet("{prefix}_RXD1", connected_roles=[("phy", "RXD1")], is_bus=True),
            PatternNet("{prefix}_CRS_DV", connected_roles=[("phy", "CRS_DV")], is_bus=True),
            PatternNet("{prefix}_REF_CLK", connected_roles=[("phy", "REF_CLK")], is_bus=True),
            PatternNet("{prefix}_MDIO", connected_roles=[("phy", "MDIO")], is_bus=True),
            PatternNet("{prefix}_MDC", connected_roles=[("phy", "MDC")], is_bus=True),
            PatternNet("{prefix}_TX_P", connected_roles=[("phy", "TX+"), ("rj45_mag", "TX+")]),
            PatternNet("{prefix}_TX_N", connected_roles=[("phy", "TX-"), ("rj45_mag", "TX-")]),
            PatternNet("{prefix}_RX_P", connected_roles=[("phy", "RX+"), ("rj45_mag", "RX+")]),
            PatternNet("{prefix}_RX_N", connected_roles=[("phy", "RX-"), ("rj45_mag", "RX-")]),
        ],
        placement_hints=[
            PlacementHint("phy", "within 20mm of RJ45 connector", "required"),
            PlacementHint("xtal_25mhz", "within 5mm of PHY crystal pins", "required"),
            PlacementHint("decoupling_avdd", "within 3mm of PHY AVDD pin", "required"),
        ],
        erc_checks=[
            "PHY AVDD and DVDD both have decoupling",
            "RMII REF_CLK = 50MHz (provided by PHY or external)",
            "TX+/TX- and RX+/RX- are differential pairs",
        ],
        notes=[
            "LAN8720A generates 50MHz REF_CLK internally from 25MHz crystal",
            "Keep PHY-to-magnetics traces short and matched length",
            "RJ45 with integrated magnetics simplifies layout",
            "MDIO needs 1.5kΩ pull-up to DVDD",
        ],
    ),

    # ------------------------------------------------------------------
    # 8. LoRa RF Frontend
    # ------------------------------------------------------------------
    IndustrialPattern(
        id="lora_rf_frontend_v1",
        version="1.0.0",
        name="LoRa RF Frontend",
        description=(
            "LoRa transceiver (SX1276/SX1262) frontend with SPI interface, "
            "antenna matching network, GND keepout zone, decoupling, "
            "and SMA/U.FL antenna connector."
        ),
        category="bus_protection",
        keywords=[
            "lora", "lorawan", "rf", "funk", "wireless", "868mhz", "915mhz",
            "sx1276", "sx1262", "rfm95", "antenna", "antenne",
            "long range", "iot", "lpwan",
        ],
        parameters=[
            ParamSpec("frequency_mhz", "enum", "868", "Operating frequency",
                      enum_values=["433", "868", "915"]),
            ParamSpec("tx_power_dbm", "float", 14.0, "TX power (dBm)", min=2.0, max=20.0),
        ],
        components=[
            PatternComponent(
                role="transceiver",
                category="comms",
                recommended_mpns=["SX1276", "RFM95W"],
            ),
            PatternComponent(
                role="antenna_conn",
                category="connector",
                constraints=["SMA edge-mount or U.FL"],
            ),
            PatternComponent(
                role="decoupling_vdd",
                category="passive",
                value_expr="100e-9",
                unit="F",
                package="0402",
            ),
            PatternComponent(
                role="decoupling_bulk",
                category="passive",
                value_expr="10e-6",
                unit="F",
                package="0805",
            ),
            PatternComponent(
                role="matching_c1",
                category="passive",
                value_expr="dependent_on_frequency",
                unit="F",
                package="0402",
                constraints=["Frequency-dependent matching network"],
            ),
            PatternComponent(
                role="matching_l1",
                category="passive",
                value_expr="dependent_on_frequency",
                unit="H",
                package="0402",
                constraints=["Frequency-dependent matching network"],
            ),
        ],
        nets=[
            PatternNet("{prefix}_MOSI", connected_roles=[("transceiver", "MOSI")], is_bus=True),
            PatternNet("{prefix}_MISO", connected_roles=[("transceiver", "MISO")], is_bus=True),
            PatternNet("{prefix}_SCK", connected_roles=[("transceiver", "SCK")], is_bus=True),
            PatternNet("{prefix}_NSS", connected_roles=[("transceiver", "NSS")], is_bus=True),
            PatternNet("{prefix}_DIO0", connected_roles=[("transceiver", "DIO0")]),
            PatternNet("{prefix}_RESET", connected_roles=[("transceiver", "RESET")]),
            PatternNet("{prefix}_RF_OUT", connected_roles=[("transceiver", "RF_OUT"), ("matching_c1", "1")]),
            PatternNet("{prefix}_ANT", connected_roles=[("matching_l1", "2"), ("antenna_conn", "SIG")]),
            PatternNet("{prefix}_VDD", connected_roles=[("transceiver", "VDD"), ("decoupling_vdd", "1"), ("decoupling_bulk", "1")], is_power=True),
            PatternNet("GND", connected_roles=[("transceiver", "GND"), ("decoupling_vdd", "2"), ("decoupling_bulk", "2"), ("antenna_conn", "GND")], is_power=True),
        ],
        placement_hints=[
            PlacementHint("transceiver", "antenna trace < 10mm, no vias in RF path", "required"),
            PlacementHint("matching_c1", "within 2mm of transceiver RF pin", "required"),
            PlacementHint("antenna_conn", "board edge, ground plane underneath", "required"),
            PlacementHint("decoupling_vdd", "within 2mm of transceiver VDD", "required"),
        ],
        erc_checks=[
            "RF output through matching network to antenna",
            "No unconnected DIO pins (at least DIO0 for IRQ)",
        ],
        drc_checks=[
            "15mm keepout zone around antenna — no copper, no components",
            "Solid GND plane under transceiver and RF trace",
            "50Ω impedance-controlled trace from matching to antenna",
        ],
        notes=[
            "Matching network values are frequency-specific — use manufacturer reference",
            "Keep GND plane solid under entire RF section",
            "RFM95W module has matching network built-in — skip matching_c1/l1",
            "SX1276 bare chip needs external matching (see Semtech AN1200.16)",
        ],
    ),

    # ------------------------------------------------------------------
    # 9. I2C Bus Protected (External)
    # ------------------------------------------------------------------
    IndustrialPattern(
        id="i2c_bus_protected_v1",
        version="1.0.0",
        name="Protected I2C Bus (External Cable)",
        description=(
            "I2C bus protection for external cable connections: pull-ups, "
            "ESD protection on SDA/SCL, optional I2C multiplexer for "
            "address conflicts, and RC filter for noise immunity."
        ),
        category="bus_protection",
        keywords=[
            "i2c", "iic", "twi", "protected", "extern", "external",
            "kabel", "cable", "esd", "i2c bus", "i2c protection",
            "pull-up", "pullup",
        ],
        parameters=[
            ParamSpec("speed_hz", "int", 100_000, "I2C speed (Hz)",
                      enum_values=["100000", "400000", "1000000"]),
            ParamSpec("device_count", "int", 3, "Number of I2C devices", min=1, max=8),
            ParamSpec("cable_length_m", "float", 0.5, "Cable length (m)", min=0.0, max=3.0),
        ],
        components=[
            PatternComponent(
                role="pullup_sda",
                category="passive",
                value_expr="4700 if speed_hz <= 100000 else (2200 if speed_hz <= 400000 else 1000)",
                unit="Ω",
                package="0402",
            ),
            PatternComponent(
                role="pullup_scl",
                category="passive",
                value_expr="4700 if speed_hz <= 100000 else (2200 if speed_hz <= 400000 else 1000)",
                unit="Ω",
                package="0402",
            ),
            PatternComponent(
                role="esd",
                category="protection",
                recommended_mpns=["PESD3V3S2UT"],
                constraints=["Low capacitance < 10pF per line for I2C"],
            ),
            PatternComponent(
                role="r_series_sda",
                category="passive",
                value_expr="33",
                unit="Ω",
                package="0402",
                constraints=["Series R for cable noise filtering"],
            ),
            PatternComponent(
                role="r_series_scl",
                category="passive",
                value_expr="33",
                unit="Ω",
                package="0402",
            ),
        ],
        nets=[
            PatternNet("{prefix}_SDA_MCU", connected_roles=[("r_series_sda", "1")], is_bus=True),
            PatternNet("{prefix}_SCL_MCU", connected_roles=[("r_series_scl", "1")], is_bus=True),
            PatternNet("{prefix}_SDA", connected_roles=[("r_series_sda", "2"), ("pullup_sda", "2"), ("esd", "IO1")], is_bus=True),
            PatternNet("{prefix}_SCL", connected_roles=[("r_series_scl", "2"), ("pullup_scl", "2"), ("esd", "IO2")], is_bus=True),
            PatternNet("{prefix}_VCC", connected_roles=[("pullup_sda", "1"), ("pullup_scl", "1")], is_power=True),
            PatternNet("GND", connected_roles=[("esd", "GND")], is_power=True),
        ],
        placement_hints=[
            PlacementHint("esd", "at connector, before pull-ups", "required"),
            PlacementHint("pullup_sda", "within 10mm of MCU I2C pins", "recommended"),
        ],
        erc_checks=[
            "Pull-up value matches I2C speed mode",
            "ESD TVS capacitance + cable capacitance < max bus capacitance",
            "Total bus capacitance < 400pF (standard) / 550pF (fast)",
        ],
        notes=[
            "Pull-up to 3.3V rail, NOT to 5V (unless level-shifted)",
            "For cable > 1m, consider I2C bus extender (P82B715)",
            "Series resistors (33Ω) help with cable reflections and EMI",
        ],
    ),

    # ------------------------------------------------------------------
    # 10. SPI Bus Standard
    # ------------------------------------------------------------------
    IndustrialPattern(
        id="spi_bus_standard_v1",
        version="1.0.0",
        name="SPI Bus Standard Interface",
        description=(
            "Standard SPI bus interface with CS pull-ups (keep slaves deselected "
            "during boot), SCK series resistor for EMI reduction, ESD protection "
            "for external connections, and proper decoupling."
        ),
        category="bus_protection",
        keywords=[
            "spi", "spi bus", "serial peripheral", "mosi", "miso",
            "sck", "chip select", "cs", "ss", "spi interface",
        ],
        parameters=[
            ParamSpec("speed_mhz", "float", 10.0, "SPI clock speed (MHz)", min=0.1, max=50.0),
            ParamSpec("slave_count", "int", 1, "Number of SPI slaves", min=1, max=4),
            ParamSpec("external", "bool", False, "External cable connection (adds ESD)"),
        ],
        components=[
            PatternComponent(
                role="r_sck_series",
                category="passive",
                value_expr="33",
                unit="Ω",
                package="0402",
                constraints=["Reduces SCK ringing and EMI"],
            ),
            PatternComponent(
                role="cs_pullup",
                category="passive",
                value_expr="10000",
                unit="Ω",
                package="0402",
                constraints=["One per CS line, keeps slave deselected during boot"],
            ),
            PatternComponent(
                role="esd",
                category="protection",
                required=False,
                recommended_mpns=["PESD3V3S2UT"],
                constraints=["Only for external connections"],
            ),
        ],
        nets=[
            PatternNet("{prefix}_MOSI", connected_roles=[], is_bus=True),
            PatternNet("{prefix}_MISO", connected_roles=[], is_bus=True),
            PatternNet("{prefix}_SCK_MCU", connected_roles=[("r_sck_series", "1")], is_bus=True),
            PatternNet("{prefix}_SCK", connected_roles=[("r_sck_series", "2")], is_bus=True),
            PatternNet("{prefix}_CS0", connected_roles=[("cs_pullup", "2")]),
            PatternNet("{prefix}_VCC", connected_roles=[("cs_pullup", "1")], is_power=True),
        ],
        placement_hints=[
            PlacementHint("r_sck_series", "close to MCU SCK pin", "recommended"),
            PlacementHint("cs_pullup", "close to slave CS pin", "recommended"),
        ],
        erc_checks=[
            "Each CS line has pull-up to VCC",
            "SCK series resistor present",
        ],
        notes=[
            "CS pull-ups prevent false slave activation during MCU boot/reset",
            "SCK series resistor (33Ω) reduces EMI and signal ringing",
            "For SPI > 20MHz, consider controlled-impedance traces",
        ],
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class IndustrialPatternLibrary:
    """Library of validated industrial hardware patterns."""

    def __init__(self, patterns: list[IndustrialPattern] | None = None) -> None:
        self._patterns = patterns if patterns is not None else list(_PATTERNS)
        self._by_id: dict[str, IndustrialPattern] = {p.id: p for p in self._patterns}

    def get(self, pattern_id: str) -> IndustrialPattern | None:
        """Return a pattern by exact ID, or None."""
        return self._by_id.get(pattern_id)

    def find_by_category(self, category: str) -> list[IndustrialPattern]:
        """Return all patterns in a given category."""
        return [p for p in self._patterns if p.category == category]

    def find_by_keyword(self, text: str) -> list[IndustrialPattern]:
        """Return patterns whose keywords appear in text (case-insensitive)."""
        low = text.lower()
        scored: list[tuple[int, IndustrialPattern]] = []
        for p in self._patterns:
            hits = sum(1 for kw in p.keywords if kw in low)
            if hits:
                scored.append((hits, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored]

    def find_by_quality(self, min_quality: str = "validated") -> list[IndustrialPattern]:
        """Return patterns at or above a quality level."""
        levels = {"draft": 0, "validated": 1, "verified": 2}
        min_level = levels.get(min_quality, 0)
        return [p for p in self._patterns if levels.get(p.quality_state, 0) >= min_level]

    def all_patterns(self) -> list[IndustrialPattern]:
        """Return all registered patterns."""
        return list(self._patterns)

    def pattern_ids(self) -> list[str]:
        """Return all pattern IDs."""
        return list(self._by_id.keys())
