# SPDX-License-Identifier: AGPL-3.0-or-later
"""DB-3: All 15 MVP circuit patterns.

Organised in four categories:
  - Interface patterns  (I2C, SPI, UART, CAN, RS485, USB)
  - Protection patterns (TVS, reverse polarity, ESD, reset)
  - Power patterns      (LDO bypass, buck converter, decoupling, MOSFET low-side)
  - Analog patterns     (ADC divider, crystal load)
"""
from __future__ import annotations

from shared.knowledge.patterns.pattern_schema import (
    CircuitPattern,
    OutputComponent,
    OutputNet,
    PatternParameter,
)

PATTERNS: list[CircuitPattern] = [

    # =========================================================================
    # INTERFACE PATTERNS
    # =========================================================================

    # -------------------------------------------------------------------------
    # 1. I2C Pull-Up Resistors
    # -------------------------------------------------------------------------
    CircuitPattern(
        pattern_id="i2c_pullup_v1",
        category="interface",
        name="I2C Pull-Up Resistors",
        description=(
            "Adds two pull-up resistors on SDA and SCL to VDD. "
            "Resistor value is computed from the I2C rise-time spec and estimated bus capacitance: "
            "R = t_rise / (0.8473 × C_bus). "
            "Standard mode (100 kHz): t_rise = 1000 ns. "
            "Fast mode (400 kHz): t_rise = 300 ns. "
            "Fast mode+ (1 MHz): t_rise = 120 ns."
        ),
        trigger="interface_type == 'I2C'",
        parameters=[
            PatternParameter(
                name="bus_speed_hz", type="int", default=100_000,
                min=10_000, max=5_000_000, unit="Hz",
                description="I2C bus speed",
            ),
            PatternParameter(
                name="bus_cap_pf", type="float", default=50.0,
                min=5.0, max=400.0, unit="pF",
                description="Estimated total bus capacitance (traces + pins)",
            ),
            PatternParameter(
                name="vdd_rail", type="str", default="VDD_3V3",
                description="Supply rail to pull up to",
            ),
        ],
        output_components=[
            OutputComponent(
                role="R_pull_sda",
                category="resistor",
                value_expr=(
                    "(1000e-9 if bus_speed_hz < 400_000 else "
                    "300e-9 if bus_speed_hz < 1_000_000 else 120e-9) "
                    "/ (0.8473 * bus_cap_pf * 1e-12)"
                ),
                unit="Ω",
                package="0402",
                mpn_suggestion="RC0402FR-074K7L",
                nets=["{vdd_rail}", "{bus}_SDA"],
                description="SDA pull-up resistor",
            ),
            OutputComponent(
                role="R_pull_scl",
                category="resistor",
                value_expr=(
                    "(1000e-9 if bus_speed_hz < 400_000 else "
                    "300e-9 if bus_speed_hz < 1_000_000 else 120e-9) "
                    "/ (0.8473 * bus_cap_pf * 1e-12)"
                ),
                unit="Ω",
                package="0402",
                mpn_suggestion="RC0402FR-074K7L",
                nets=["{vdd_rail}", "{bus}_SCL"],
                description="SCL pull-up resistor",
            ),
        ],
        output_nets=[
            OutputNet(name="{bus}_SDA", roles=["R_pull_sda"]),
            OutputNet(name="{bus}_SCL", roles=["R_pull_scl"]),
        ],
        validations=[
            "r_pull_sda_ohm > 0",
            "r_pull_sda_ohm <= 10000",  # max 10kΩ per I2C spec
        ],
        notes=[
            "Use one pair of pull-ups per bus, not per device.",
            "Reduce value (e.g. 2.2kΩ) for long buses or high capacitance.",
            "For 5V I2C, pull up to 5V; ensure all devices are 5V-tolerant.",
        ],
        references=["UM10204 — I2C Bus Specification Rev 7.0, §7.1"],
    ),

    # -------------------------------------------------------------------------
    # 2. SPI Series Resistor + CS Pull-Up
    # -------------------------------------------------------------------------
    CircuitPattern(
        pattern_id="spi_series_resistor_v1",
        category="interface",
        name="SPI Series Resistor & CS Pull-Up",
        description=(
            "Adds a 33Ω series resistor on SCK to reduce EMI/ringing, "
            "and 10kΩ pull-up resistors on each CS line to keep slaves "
            "deselected (CS high) during MCU boot."
        ),
        trigger="interface_type == 'SPI'",
        parameters=[
            PatternParameter(
                name="sck_series_r_ohm", type="int", default=33,
                min=0, max=100, unit="Ω",
                description="SCK series resistor value",
            ),
            PatternParameter(
                name="cs_pullup_r_ohm", type="int", default=10_000,
                min=1_000, max=100_000, unit="Ω",
                description="CS pull-up resistor value",
            ),
            PatternParameter(
                name="vdd_rail", type="str", default="VDD_3V3",
                description="Rail for CS pull-ups",
            ),
        ],
        output_components=[
            OutputComponent(
                role="R_sck",
                category="resistor",
                value_expr="sck_series_r_ohm",
                unit="Ω",
                package="0402",
                mpn_suggestion="RC0402FR-0733RL",
                nets=["{bus}_SCK_MCU", "{bus}_SCK"],
                description="SCK series resistor — EMI reduction",
            ),
            OutputComponent(
                role="R_cs",
                category="resistor",
                value_expr="cs_pullup_r_ohm",
                unit="Ω",
                package="0402",
                mpn_suggestion="RC0402FR-0710KL",
                nets=["{vdd_rail}", "{bus}_CS"],
                description="CS pull-up — boot-safe slave deselect",
            ),
        ],
        output_nets=[
            OutputNet(name="{bus}_SCK", roles=["R_sck"]),
            OutputNet(name="{bus}_CS",  roles=["R_cs"]),
        ],
        validations=["sck_series_r_ohm >= 0"],
        notes=[
            "Place SCK series resistor close to the MCU pin.",
            "Add one R_cs per CS line if multiple slaves share the bus.",
        ],
    ),

    # -------------------------------------------------------------------------
    # 3. CAN Transceiver + Termination
    # -------------------------------------------------------------------------
    CircuitPattern(
        pattern_id="can_transceiver_v1",
        category="interface",
        name="CAN Bus Transceiver + Termination",
        description=(
            "Adds an SN65HVD230 (3.3V) or TJA1051 (5V) CAN transceiver IC "
            "between the MCU UART-CAN/CANFD port and the CAN bus differential pair. "
            "Optionally adds split 60Ω termination (2 × 120Ω in series with a 4.7nF cap to GND) "
            "for nodes on the bus end. Only one pair of termination resistors per bus segment."
        ),
        trigger="interface_type == 'CAN'",
        parameters=[
            PatternParameter(
                name="v_supply", type="float", default=3.3,
                description="Transceiver supply voltage (3.3 or 5.0 V)",
            ),
            PatternParameter(
                name="add_termination", type="bool", default=True,
                description="Add 120Ω split termination at this node",
            ),
        ],
        output_components=[
            OutputComponent(
                role="U_trx",
                category="ic",
                package="SOIC-8",
                mpn_suggestion="SN65HVD230DR",
                nets=["VDD_3V3", "GND", "{bus}_TX", "{bus}_RX", "CAN_H", "CAN_L"],
                description="CAN bus transceiver",
            ),
            OutputComponent(
                role="C_bypass_trx",
                category="capacitor",
                value_expr="100e-9",
                unit="F",
                package="0402",
                nets=["VDD_3V3", "GND"],
                description="Transceiver bypass capacitor",
            ),
            OutputComponent(
                role="R_term_a",
                category="resistor",
                value_expr="120",
                unit="Ω",
                package="0402",
                mpn_suggestion="RC0402FR-07120RL",
                nets=["CAN_H", "CAN_TERM_MID"],
                description="Termination resistor — CAN_H half",
            ),
            OutputComponent(
                role="R_term_b",
                category="resistor",
                value_expr="120",
                unit="Ω",
                package="0402",
                mpn_suggestion="RC0402FR-07120RL",
                nets=["CAN_TERM_MID", "CAN_L"],
                description="Termination resistor — CAN_L half",
            ),
            OutputComponent(
                role="C_term",
                category="capacitor",
                value_expr="4.7e-9",
                unit="F",
                package="0402",
                nets=["CAN_TERM_MID", "GND"],
                description="Split termination capacitor (common-mode filtering)",
            ),
        ],
        output_nets=[
            OutputNet(name="CAN_H",       roles=["U_trx", "R_term_a"]),
            OutputNet(name="CAN_L",       roles=["U_trx", "R_term_b"]),
            OutputNet(name="CAN_TERM_MID", roles=["R_term_a", "R_term_b", "C_term"]),
        ],
        validations=["v_supply in (3.3, 5.0)"],
        notes=[
            "SN65HVD230 for 3.3V MCUs, TJA1051T for 5V systems.",
            "Add termination only at physical bus ends — typically 2 of N nodes.",
            "Split termination (2×120Ω + cap) improves common-mode noise rejection.",
        ],
        references=["ISO 11898-2", "SN65HVD230 datasheet SLIS050"],
    ),

    # -------------------------------------------------------------------------
    # 4. RS-485 Transceiver + Bias + Termination
    # -------------------------------------------------------------------------
    CircuitPattern(
        pattern_id="rs485_transceiver_v1",
        category="interface",
        name="RS-485 Transceiver + Bias + Termination",
        description=(
            "Adds a MAX485 or SN75176 RS-485 transceiver, optional 560Ω fail-safe "
            "bias resistors (pull A high, B low when bus is idle), and 120Ω line termination."
        ),
        trigger="interface_type == 'RS485'",
        parameters=[
            PatternParameter(
                name="add_termination", type="bool", default=True,
                description="Add 120Ω termination at this node",
            ),
            PatternParameter(
                name="add_bias", type="bool", default=True,
                description="Add 560Ω fail-safe bias resistors",
            ),
        ],
        output_components=[
            OutputComponent(
                role="U_trx",
                category="ic",
                package="SOIC-8",
                mpn_suggestion="MAX485ESA+",
                nets=["VDD_5V", "GND", "{bus}_TX", "{bus}_RX", "{bus}_DE", "RS485_A", "RS485_B"],
                description="RS-485 transceiver",
            ),
            OutputComponent(
                role="C_bypass_trx",
                category="capacitor",
                value_expr="100e-9",
                unit="F",
                package="0402",
                nets=["VDD_5V", "GND"],
            ),
            OutputComponent(
                role="R_term",
                category="resistor",
                value_expr="120",
                unit="Ω",
                package="0402",
                mpn_suggestion="RC0402FR-07120RL",
                nets=["RS485_A", "RS485_B"],
                description="Line termination",
            ),
            OutputComponent(
                role="R_bias_a",
                category="resistor",
                value_expr="560",
                unit="Ω",
                package="0402",
                nets=["VDD_5V", "RS485_A"],
                description="Fail-safe bias — A high",
            ),
            OutputComponent(
                role="R_bias_b",
                category="resistor",
                value_expr="560",
                unit="Ω",
                package="0402",
                nets=["RS485_B", "GND"],
                description="Fail-safe bias — B low",
            ),
        ],
        output_nets=[
            OutputNet(name="RS485_A", roles=["U_trx", "R_term", "R_bias_a"]),
            OutputNet(name="RS485_B", roles=["U_trx", "R_term", "R_bias_b"]),
        ],
        validations=[],
        notes=[
            "Only one termination resistor per physical bus end.",
            "Bias resistors ensure defined idle state when all transmitters are disabled.",
            "Use a TVS on RS485_A/B for industrial installations.",
        ],
    ),

    # -------------------------------------------------------------------------
    # 5. USB ESD Protection
    # -------------------------------------------------------------------------
    CircuitPattern(
        pattern_id="usb_esd_protection_v1",
        category="protection",
        name="USB D+/D− ESD Protection",
        description=(
            "Adds 27Ω series resistors on D+ and D− for impedance matching and "
            "current limiting, plus a USBLC6-2SC6 dual-line TVS for IEC 61000-4-2 "
            "Level 4 ESD protection."
        ),
        trigger="interface_type == 'USB'",
        parameters=[
            PatternParameter(
                name="series_r_ohm", type="int", default=27,
                min=0, max=56, unit="Ω",
                description="D+/D− series resistors for impedance matching",
            ),
        ],
        output_components=[
            OutputComponent(
                role="R_dp",
                category="resistor",
                value_expr="series_r_ohm",
                unit="Ω",
                package="0402",
                mpn_suggestion="RC0402FR-0727RL",
                nets=["USB_DP_MCU", "USB_DP"],
                description="D+ series resistor",
            ),
            OutputComponent(
                role="R_dm",
                category="resistor",
                value_expr="series_r_ohm",
                unit="Ω",
                package="0402",
                mpn_suggestion="RC0402FR-0727RL",
                nets=["USB_DM_MCU", "USB_DM"],
                description="D− series resistor",
            ),
            OutputComponent(
                role="U_tvs",
                category="ic",
                package="SOT-23-6",
                mpn_suggestion="USBLC6-2SC6",
                nets=["USB_DP", "USB_DM", "VBUS", "GND"],
                description="Dual-line TVS for USB ESD (IEC 61000-4-2 L4)",
            ),
        ],
        output_nets=[
            OutputNet(name="USB_DP",     roles=["R_dp", "U_tvs"]),
            OutputNet(name="USB_DM",     roles=["R_dm", "U_tvs"]),
        ],
        validations=["series_r_ohm <= 56"],
        notes=[
            "Place USBLC6-2SC6 as close as possible to the USB connector.",
            "Route D+/D− as differential pair with 90Ω impedance.",
            "Series resistors also limit inrush and protect against bus contention.",
        ],
        references=["USBLC6-2SC6 datasheet", "IEC 61000-4-2"],
    ),

    # -------------------------------------------------------------------------
    # 6. UART Level Shifter
    # -------------------------------------------------------------------------
    CircuitPattern(
        pattern_id="uart_level_shifter_v1",
        category="interface",
        name="UART 3.3V ↔ 5V Level Shifter",
        description=(
            "Inserts a bidirectional level shifter (TXS0102 or BSS138+resistor) "
            "between a 3.3V MCU UART and a 5V device. "
            "TXS0102 is preferred for speeds up to 24 Mbit/s."
        ),
        trigger="uart_voltage_mismatch == True",
        parameters=[
            PatternParameter(
                name="vcc_low_v", type="float", default=3.3, unit="V",
                description="Low-voltage side (MCU)",
            ),
            PatternParameter(
                name="vcc_high_v", type="float", default=5.0, unit="V",
                description="High-voltage side (device)",
            ),
        ],
        output_components=[
            OutputComponent(
                role="U_ls",
                category="ic",
                package="SOT-23-6",
                mpn_suggestion="TXS0102DCUR",
                nets=["VDD_3V3", "VDD_5V", "GND", "{bus}_TX", "{bus}_RX",
                      "{bus}_TX_5V", "{bus}_RX_5V"],
                description="Bidirectional voltage-level translator",
            ),
            OutputComponent(
                role="C_bypass_a",
                category="capacitor",
                value_expr="100e-9",
                unit="F",
                package="0402",
                nets=["VDD_3V3", "GND"],
            ),
            OutputComponent(
                role="C_bypass_b",
                category="capacitor",
                value_expr="100e-9",
                unit="F",
                package="0402",
                nets=["VDD_5V", "GND"],
            ),
        ],
        output_nets=[
            OutputNet(name="{bus}_TX",    roles=["U_ls"]),
            OutputNet(name="{bus}_RX",    roles=["U_ls"]),
            OutputNet(name="{bus}_TX_5V", roles=["U_ls"]),
            OutputNet(name="{bus}_RX_5V", roles=["U_ls"]),
        ],
        validations=["vcc_low_v < vcc_high_v"],
        notes=[
            "TXS0102 is auto-direction — no direction control pin needed for UART.",
            "For I2C, use PCA9306 (open-drain compatible).",
        ],
    ),

    # =========================================================================
    # PROTECTION PATTERNS
    # =========================================================================

    # -------------------------------------------------------------------------
    # 7. TVS + Polyfuse Input Protection
    # -------------------------------------------------------------------------
    CircuitPattern(
        pattern_id="tvs_input_protection_v1",
        category="protection",
        name="TVS + Polyfuse Input Protection",
        description=(
            "Protects a supply or signal input against overvoltage transients and "
            "overcurrent. A polyfuse (resettable fuse) limits steady-state overcurrent; "
            "a TVS clamps transient spikes."
        ),
        trigger="protection == 'overvoltage' or input_type == 'external_supply'",
        parameters=[
            PatternParameter(
                name="v_clamp", type="float", default=5.5, unit="V",
                description="TVS clamping voltage",
            ),
            PatternParameter(
                name="i_trip_a", type="float", default=0.5, unit="A",
                description="Polyfuse trip current",
            ),
        ],
        output_components=[
            OutputComponent(
                role="F1",
                category="fuse",
                package="0805",
                mpn_suggestion="MF-MSMF050/16X",
                nets=["VIN_RAW", "VIN_FUSED"],
                description="Polyfuse — overcurrent protection",
            ),
            OutputComponent(
                role="D_tvs",
                category="diode",
                package="SOD-123",
                mpn_suggestion="SMBJ5.0A",
                nets=["VIN_FUSED", "GND"],
                description="TVS diode — overvoltage clamp",
            ),
        ],
        output_nets=[
            OutputNet(name="VIN_RAW",    roles=["F1"], is_power=True),
            OutputNet(name="VIN_FUSED",  roles=["F1", "D_tvs"], is_power=True),
        ],
        validations=["v_clamp > 0", "i_trip_a > 0"],
        notes=[
            "Place TVS as close as possible to the connector.",
            "Use bidirectional TVS for AC or polarity-uncertain signals.",
        ],
    ),

    # -------------------------------------------------------------------------
    # 8. Reverse Polarity Protection (P-FET)
    # -------------------------------------------------------------------------
    CircuitPattern(
        pattern_id="reverse_polarity_v1",
        category="protection",
        name="Reverse Polarity Protection (P-FET)",
        description=(
            "A P-channel MOSFET in the positive supply path provides ideal-diode "
            "reverse-polarity protection with near-zero forward drop (compared to a "
            "series Schottky diode). The gate pull-down keeps the FET on during normal "
            "operation; reversed polarity turns it off."
        ),
        trigger="protection == 'reverse_polarity'",
        parameters=[
            PatternParameter(
                name="max_current_a", type="float", default=2.0, unit="A",
                description="Maximum continuous load current",
            ),
            PatternParameter(
                name="v_in_max", type="float", default=24.0, unit="V",
                description="Maximum input voltage",
            ),
        ],
        output_components=[
            OutputComponent(
                role="Q1",
                category="ic",
                package="SOT-23",
                mpn_suggestion="DMG2305UX-7",  # -20V, 4A P-FET
                nets=["VIN_RAW", "VIN_PROT", "GND"],
                description="P-channel MOSFET — reverse polarity switch",
            ),
            OutputComponent(
                role="R_gate",
                category="resistor",
                value_expr="10000",
                unit="Ω",
                package="0402",
                mpn_suggestion="RC0402FR-0710KL",
                nets=["VIN_RAW", "PFET_GATE"],
                description="Gate pull-down to source (keep FET on)",
            ),
        ],
        output_nets=[
            OutputNet(name="VIN_RAW",   roles=["Q1"], is_power=True),
            OutputNet(name="VIN_PROT",  roles=["Q1"], is_power=True),
            OutputNet(name="PFET_GATE", roles=["Q1", "R_gate"]),
        ],
        validations=["max_current_a > 0", "v_in_max > 0"],
        notes=[
            "Choose FET with V_DS > v_in_max × 1.5 and I_D > max_current_a × 1.5.",
            "Add a TVS (tvs_input_protection_v1) before this for full protection.",
        ],
    ),

    # -------------------------------------------------------------------------
    # 9. Reset Circuit (RC + Pull-Up)
    # -------------------------------------------------------------------------
    CircuitPattern(
        pattern_id="reset_circuit_v1",
        category="protection",
        name="Reset Circuit (RC + Pull-Up)",
        description=(
            "Power-on reset (POR) circuit for active-low NRST pin. "
            "A pull-up resistor and filter capacitor form an RC delay at power-on. "
            "Optionally, an external reset supervisor (e.g. MCP811) monitors VDD."
        ),
        trigger="has_nrst == True or has_reset == True",
        parameters=[
            PatternParameter(
                name="pullup_r_ohm", type="int", default=10_000,
                min=1_000, max=100_000, unit="Ω",
                description="Pull-up resistor value",
            ),
            PatternParameter(
                name="filter_c_nf", type="float", default=100.0,
                min=1.0, max=1000.0, unit="nF",
                description="Filter capacitor (RC time constant with pull-up R)",
            ),
            PatternParameter(
                name="vdd_rail", type="str", default="VDD_3V3",
                description="Supply rail for pull-up",
            ),
        ],
        output_components=[
            OutputComponent(
                role="R_pull",
                category="resistor",
                value_expr="pullup_r_ohm",
                unit="Ω",
                package="0402",
                mpn_suggestion="RC0402FR-0710KL",
                nets=["{vdd_rail}", "NRST"],
                description="NRST pull-up resistor",
            ),
            OutputComponent(
                role="C_filter",
                category="capacitor",
                value_expr="filter_c_nf * 1e-9",
                unit="F",
                package="0402",
                nets=["NRST", "GND"],
                description="NRST filter capacitor",
            ),
        ],
        output_nets=[
            OutputNet(name="NRST", roles=["R_pull", "C_filter"]),
        ],
        validations=["pullup_r_ohm > 0", "filter_c_nf > 0"],
        notes=[
            "RC time constant = R × C. Default: 10kΩ × 100nF = 1 ms.",
            "Keep NRST net short — susceptible to noise.",
            "Add a tactile button between NRST and GND for manual reset.",
        ],
    ),

    # =========================================================================
    # POWER PATTERNS
    # =========================================================================

    # -------------------------------------------------------------------------
    # 10. LDO Bypass Capacitors
    # -------------------------------------------------------------------------
    CircuitPattern(
        pattern_id="ldo_bypass_v1",
        category="power",
        name="LDO Input/Output Bypass Capacitors",
        description=(
            "Adds the recommended bypass capacitors for a linear regulator (LDO). "
            "Input: bulk electrolytic + ceramic bypass. "
            "Output: bulk for transient response + ceramic bypass for HF stability."
        ),
        trigger="component_category == 'power' and sub_type == 'ldo'",
        parameters=[
            PatternParameter(
                name="c_in_bulk_uf", type="float", default=10.0, unit="µF",
                description="Input bulk capacitance",
            ),
            PatternParameter(
                name="c_out_bulk_uf", type="float", default=10.0, unit="µF",
                description="Output bulk capacitance",
            ),
        ],
        output_components=[
            OutputComponent(
                role="C_in_bulk",
                category="capacitor",
                value_expr="c_in_bulk_uf * 1e-6",
                unit="F",
                package="0805",
                nets=["VIN_LDO", "GND"],
                description="LDO input bulk capacitor",
            ),
            OutputComponent(
                role="C_in_bypass",
                category="capacitor",
                value_expr="100e-9",
                unit="F",
                package="0402",
                nets=["VIN_LDO", "GND"],
                description="LDO input bypass capacitor (HF)",
            ),
            OutputComponent(
                role="C_out_bulk",
                category="capacitor",
                value_expr="c_out_bulk_uf * 1e-6",
                unit="F",
                package="0805",
                nets=["VOUT_LDO", "GND"],
                description="LDO output bulk capacitor",
            ),
            OutputComponent(
                role="C_out_bypass",
                category="capacitor",
                value_expr="100e-9",
                unit="F",
                package="0402",
                nets=["VOUT_LDO", "GND"],
                description="LDO output bypass capacitor (HF)",
            ),
        ],
        output_nets=[
            OutputNet(name="VIN_LDO",  roles=["C_in_bulk", "C_in_bypass"],   is_power=True),
            OutputNet(name="VOUT_LDO", roles=["C_out_bulk", "C_out_bypass"],  is_power=True),
        ],
        validations=["c_in_bulk_uf > 0", "c_out_bulk_uf > 0"],
        notes=[
            "Use X5R/X7R dielectric — avoid Y5V for power supply caps.",
            "Check LDO datasheet for minimum ESR requirement on output cap.",
            "Place bypass caps as close as possible to the LDO pins.",
        ],
    ),

    # -------------------------------------------------------------------------
    # 11. Buck Converter Support Network
    # -------------------------------------------------------------------------
    CircuitPattern(
        pattern_id="buck_converter_v1",
        category="power",
        name="Buck Converter Support Network",
        description=(
            "Adds the passive support network for a synchronous buck converter: "
            "input and output bulk capacitors, a bootstrap capacitor, "
            "and the feedback resistor divider to set output voltage."
        ),
        trigger="component_category == 'power' and sub_type == 'buck'",
        parameters=[
            PatternParameter(
                name="v_in", type="float", default=12.0, unit="V",
                description="Input voltage",
            ),
            PatternParameter(
                name="v_out", type="float", default=5.0, unit="V",
                description="Target output voltage",
            ),
            PatternParameter(
                name="i_out_a", type="float", default=1.0, unit="A",
                description="Maximum output current",
            ),
            PatternParameter(
                name="f_sw_hz", type="int", default=500_000, unit="Hz",
                description="Switching frequency",
            ),
            PatternParameter(
                name="r_fb_bot_ohm", type="float", default=10_000.0, unit="Ω",
                description="Feedback divider bottom resistor (fixed)",
            ),
            PatternParameter(
                name="v_ref", type="float", default=0.8, unit="V",
                description="IC internal reference voltage",
                formula="0.8",
            ),
        ],
        output_components=[
            OutputComponent(
                role="C_in",
                category="capacitor",
                value_expr="22e-6",
                unit="F",
                package="0805",
                nets=["VIN_BUCK", "GND"],
                description="Buck input bulk capacitor",
            ),
            OutputComponent(
                role="C_in_bypass",
                category="capacitor",
                value_expr="100e-9",
                unit="F",
                package="0402",
                nets=["VIN_BUCK", "GND"],
            ),
            OutputComponent(
                role="C_out",
                category="capacitor",
                value_expr="22e-6",
                unit="F",
                package="1206",
                nets=["VOUT_BUCK", "GND"],
                description="Buck output bulk capacitor",
            ),
            OutputComponent(
                role="C_out_bypass",
                category="capacitor",
                value_expr="100e-9",
                unit="F",
                package="0402",
                nets=["VOUT_BUCK", "GND"],
            ),
            OutputComponent(
                role="C_boot",
                category="capacitor",
                value_expr="100e-9",
                unit="F",
                package="0402",
                nets=["SW_NODE", "BOOT"],
                description="Bootstrap capacitor",
            ),
            OutputComponent(
                role="R_fb_top",
                category="resistor",
                value_expr="r_fb_bot_ohm * (v_out / v_ref - 1)",
                unit="Ω",
                package="0402",
                nets=["VOUT_BUCK", "FB_NODE"],
                description="Feedback divider top — sets V_out",
            ),
            OutputComponent(
                role="R_fb_bot",
                category="resistor",
                value_expr="r_fb_bot_ohm",
                unit="Ω",
                package="0402",
                nets=["FB_NODE", "GND"],
                description="Feedback divider bottom",
            ),
        ],
        output_nets=[
            OutputNet(name="VIN_BUCK",  roles=["C_in", "C_in_bypass"],       is_power=True),
            OutputNet(name="VOUT_BUCK", roles=["C_out", "C_out_bypass", "R_fb_top"], is_power=True),
            OutputNet(name="FB_NODE",   roles=["R_fb_top", "R_fb_bot"]),
        ],
        validations=["v_out < v_in", "i_out_a > 0"],
        notes=[
            "R_fb_top = R_fb_bot × (V_out / V_ref − 1). Check IC datasheet for V_ref.",
            "Place C_in close to VIN and GND pins of the IC.",
            "Inductor value: L = V_out × (1 − D) / (ΔI_L × f_sw) where D = V_out / V_in.",
        ],
    ),

    # -------------------------------------------------------------------------
    # 12. Decoupling Capacitors per MCU Power Pin
    # -------------------------------------------------------------------------
    CircuitPattern(
        pattern_id="decoupling_per_pin_v1",
        category="power",
        name="MCU Decoupling Capacitors per Power Pin",
        description=(
            "Adds 100 nF bypass capacitors for each MCU power supply pin, "
            "plus one 10 µF bulk capacitor per power domain. "
            "This is mandatory for all MCUs per Cortex-M and ESP32 application notes."
        ),
        trigger="component_category == 'mcu'",
        parameters=[
            PatternParameter(
                name="c_bypass_nf", type="float", default=100.0, unit="nF",
                description="Bypass capacitor per VDD pin",
            ),
            PatternParameter(
                name="c_bulk_uf", type="float", default=10.0, unit="µF",
                description="Bulk capacitor per power domain",
            ),
        ],
        output_components=[
            OutputComponent(
                role="C_bypass",
                category="capacitor",
                value_expr="c_bypass_nf * 1e-9",
                unit="F",
                package="0402",
                mpn_suggestion="GRM155R71C104KA88D",
                nets=["{power_domain}", "GND"],
                description="100 nF per VDD pin (one instance per pin)",
                quantity=1,  # instantiator adds one per VDD pin
            ),
            OutputComponent(
                role="C_bulk",
                category="capacitor",
                value_expr="c_bulk_uf * 1e-6",
                unit="F",
                package="0805",
                mpn_suggestion="GRM188R61A106KE69D",
                nets=["{power_domain}", "GND"],
                description="10 µF bulk per power domain (one per domain)",
                quantity=1,
            ),
        ],
        output_nets=[
            OutputNet(name="{power_domain}", roles=["C_bypass", "C_bulk"], is_power=True),
        ],
        validations=["c_bypass_nf > 0", "c_bulk_uf > 0"],
        notes=[
            "Place 100 nF caps within 0.5 mm of each VDD pin.",
            "Use X5R/X7R ceramic; avoid Y5V.",
            "Add ferrite bead between digital VDD and analog VDDA if MCU has ADC.",
        ],
        references=["ARM Cortex-M Design Start application note", "ESP32 Hardware Design Guidelines"],
    ),

    # -------------------------------------------------------------------------
    # 13. N-FET Low-Side Switch
    # -------------------------------------------------------------------------
    CircuitPattern(
        pattern_id="mosfet_low_side_v1",
        category="power",
        name="N-Channel MOSFET Low-Side Switch",
        description=(
            "Controls an inductive load (motor, relay, solenoid) with an N-FET "
            "in the low-side switch topology. A gate resistor limits gate charge "
            "current; a flyback diode protects against inductive kick."
        ),
        trigger="load_type == 'inductive' or load_switch == 'low_side'",
        parameters=[
            PatternParameter(
                name="v_load", type="float", default=12.0, unit="V",
                description="Load supply voltage",
            ),
            PatternParameter(
                name="i_load_a", type="float", default=2.0, unit="A",
                description="Continuous load current",
            ),
            PatternParameter(
                name="r_gate_ohm", type="int", default=10, unit="Ω",
                description="Gate series resistor (slew-rate limiting)",
            ),
        ],
        output_components=[
            OutputComponent(
                role="Q1",
                category="ic",
                package="SOT-23",
                mpn_suggestion="IRLZ44NPBF",
                nets=["LOAD_HI", "LOAD_LO", "GND", "MCU_PWM"],
                description="N-FET low-side switch",
            ),
            OutputComponent(
                role="R_gate",
                category="resistor",
                value_expr="r_gate_ohm",
                unit="Ω",
                package="0402",
                mpn_suggestion="RC0402FR-0710RL",
                nets=["MCU_PWM_MCU", "MCU_PWM"],
                description="Gate series resistor",
            ),
            OutputComponent(
                role="D_flyback",
                category="diode",
                package="SOD-123",
                mpn_suggestion="1N4007",
                nets=["GND", "LOAD_HI"],
                description="Flyback diode across load",
            ),
        ],
        output_nets=[
            OutputNet(name="LOAD_HI",  roles=["Q1", "D_flyback"], is_power=True),
            OutputNet(name="LOAD_LO",  roles=["Q1"]),
            OutputNet(name="MCU_PWM",  roles=["Q1", "R_gate"]),
        ],
        validations=["v_load > 0", "i_load_a > 0", "r_gate_ohm >= 0"],
        notes=[
            "Choose FET with V_GS(th) < 2.5V for 3.3V MCU drive.",
            "For high-side switching, use P-FET or a gate driver IC.",
            "Use a Schottky diode (e.g. 1N5819) for faster switching loads.",
        ],
    ),

    # =========================================================================
    # ANALOG PATTERNS
    # =========================================================================

    # -------------------------------------------------------------------------
    # 14. ADC Voltage Divider + Anti-Alias Filter
    # -------------------------------------------------------------------------
    CircuitPattern(
        pattern_id="adc_divider_v1",
        category="analog",
        name="ADC Voltage Divider + Anti-Alias RC Filter",
        description=(
            "Scales a high-voltage signal to the MCU ADC input range using a "
            "resistive voltage divider, followed by a first-order RC anti-alias "
            "filter. Output impedance must be much lower than ADC sample impedance."
        ),
        trigger="analog_input == 'voltage_divider' or adc_input_range_v < v_signal_max",
        parameters=[
            PatternParameter(
                name="v_in_max", type="float", default=12.0, unit="V",
                description="Maximum input voltage to scale",
            ),
            PatternParameter(
                name="v_adc_max", type="float", default=3.3, unit="V",
                description="ADC full-scale input voltage",
            ),
            PatternParameter(
                name="r_total_ohm", type="float", default=100_000.0, unit="Ω",
                description="Total divider impedance (R_top + R_bot)",
            ),
            PatternParameter(
                name="f_cutoff_hz", type="float", default=1_000.0, unit="Hz",
                description="Anti-alias filter cutoff frequency",
                formula="1000.0",
            ),
        ],
        output_components=[
            OutputComponent(
                role="R_top",
                category="resistor",
                value_expr="r_total_ohm * (1 - v_adc_max / v_in_max)",
                unit="Ω",
                package="0402",
                description="Divider top resistor",
            ),
            OutputComponent(
                role="R_bot",
                category="resistor",
                value_expr="r_total_ohm * v_adc_max / v_in_max",
                unit="Ω",
                package="0402",
                description="Divider bottom resistor",
            ),
            OutputComponent(
                role="C_filter",
                category="capacitor",
                value_expr=(
                    "1 / (2 * 3.14159 * f_cutoff_hz * "
                    "(r_total_ohm * v_adc_max / v_in_max))"
                ),
                unit="F",
                package="0402",
                description="Anti-alias filter capacitor",
            ),
        ],
        output_nets=[
            OutputNet(name="ADC_IN_SCALED", roles=["R_top", "R_bot", "C_filter"]),
        ],
        validations=[
            "v_adc_max <= v_in_max",
            "r_total_ohm > 0",
            "f_cutoff_hz > 0",
        ],
        notes=[
            "Output impedance of divider = R_top ∥ R_bot — must be < ADC source impedance spec.",
            "Lower r_total_ohm for high-frequency signals; higher for low-power.",
            "Sample rate must be ≥ 2 × f_cutoff_hz (Nyquist).",
        ],
    ),

    # -------------------------------------------------------------------------
    # 15. Crystal Oscillator Load Capacitors
    # -------------------------------------------------------------------------
    CircuitPattern(
        pattern_id="crystal_load_v1",
        category="analog",
        name="Crystal Oscillator Load Capacitors",
        description=(
            "Adds the two load capacitors for a crystal oscillator circuit. "
            "C_load = (C1 × C2) / (C1 + C2) + C_stray. "
            "For matched caps C1 = C2: C_load = C1/2 + C_stray → C1 = 2 × (C_load − C_stray). "
            "A series resistor limits current to the crystal (optional, per MCU appnote)."
        ),
        trigger="component_category == 'crystal' or interface_type == 'oscillator'",
        parameters=[
            PatternParameter(
                name="c_load_pf", type="float", default=12.5, unit="pF",
                description="Crystal specified load capacitance",
            ),
            PatternParameter(
                name="c_stray_pf", type="float", default=5.0, unit="pF",
                description="Estimated PCB stray capacitance",
            ),
            PatternParameter(
                name="r_series_ohm", type="int", default=0, unit="Ω",
                description="Optional series resistor for drive-level limiting (0 = omit)",
            ),
        ],
        output_components=[
            OutputComponent(
                role="C_xtal1",
                category="capacitor",
                value_expr="max(1e-12, 2 * (c_load_pf - c_stray_pf) * 1e-12)",
                unit="F",
                package="0402",
                nets=["XTAL_IN", "GND"],
                description="Crystal load capacitor — XIN side",
            ),
            OutputComponent(
                role="C_xtal2",
                category="capacitor",
                value_expr="max(1e-12, 2 * (c_load_pf - c_stray_pf) * 1e-12)",
                unit="F",
                package="0402",
                nets=["XTAL_OUT", "GND"],
                description="Crystal load capacitor — XOUT side",
            ),
            OutputComponent(
                role="R_series",
                category="resistor",
                value_expr="r_series_ohm",
                unit="Ω",
                package="0402",
                nets=["XTAL_OUT_MCU", "XTAL_OUT"],
                description="Series resistor for drive level limiting (omit if 0)",
            ),
        ],
        output_nets=[
            OutputNet(name="XTAL_IN",  roles=["C_xtal1"]),
            OutputNet(name="XTAL_OUT", roles=["C_xtal2", "R_series"]),
        ],
        validations=[
            "c_load_pf > c_stray_pf",
            "c_stray_pf >= 0",
        ],
        notes=[
            "Keep crystal and load caps as close together as possible.",
            "Add a guard ring around the crystal oscillator traces.",
            "Do not route any high-speed signals near XTAL_IN / XTAL_OUT.",
        ],
        references=["IEC 60444 oscillator design guidelines", "Silicon Labs AN0016.1"],
    ),
]
