# SPDX-License-Identifier: AGPL-3.0-or-later
"""EDA profiles for passives, connectors, level shifters, actuators, and discretes."""
from __future__ import annotations

from shared.knowledge.eda_schema import EDAFootprint, EDAPin, EDAProfile, EDASymbol

PROFILES: list[EDAProfile] = [
    # --- Level Shifters ---
    EDAProfile(
        mpn="TXB0104",
        symbol=EDASymbol(
            lib_ref="Logic_LevelTranslator:TXB0104",
            ref_prefix="U",
            description="TI TXB0104 4-bit Bidirectional Voltage-Level Shifter TSSOP-14",
            pins=[
                EDAPin("VCCA", "1",  "power_in",     "left"),
                EDAPin("VCCB", "2",  "power_in",     "left"),
                EDAPin("GND",  "3",  "power_in",     "left"),
                EDAPin("OE",   "4",  "input",        "left"),
                EDAPin("A1",   "5",  "bidirectional","left"),
                EDAPin("A2",   "6",  "bidirectional","left"),
                EDAPin("A3",   "7",  "bidirectional","left"),
                EDAPin("A4",   "8",  "bidirectional","left"),
                EDAPin("B1",   "9",  "bidirectional","right"),
                EDAPin("B2",   "10", "bidirectional","right"),
                EDAPin("B3",   "11", "bidirectional","right"),
                EDAPin("B4",   "12", "bidirectional","right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
            pad_count=14,
            courtyard_width_mm=5.5,
            courtyard_height_mm=6.0,
            lcsc_part_id="C53434",
        ),
        power_pin_domains={"VCCA": "VDD_3V3", "VCCB": "VDD_5V", "GND": "GND"},
    ),

    EDAProfile(
        mpn="TXS0102",
        symbol=EDASymbol(
            lib_ref="Logic_LevelTranslator:TXS0102",
            ref_prefix="U",
            description="TI TXS0102 2-bit Bidirectional Level Shifter VSSOP-8",
            pins=[
                EDAPin("VCCA", "1", "power_in",     "left"),
                EDAPin("A1",   "2", "bidirectional","left"),
                EDAPin("A2",   "3", "bidirectional","left"),
                EDAPin("GND",  "4", "power_in",     "left"),
                EDAPin("OE",   "5", "input",        "left"),
                EDAPin("B2",   "6", "bidirectional","right"),
                EDAPin("B1",   "7", "bidirectional","right"),
                EDAPin("VCCB", "8", "power_in",     "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_SO:VSSOP-8_3.0x3.0mm_P0.65mm",
            pad_count=8,
            courtyard_width_mm=5.0,
            courtyard_height_mm=5.0,
            lcsc_part_id="C17206",
        ),
        power_pin_domains={"VCCA": "VDD_3V3", "VCCB": "VDD_5V", "GND": "GND"},
    ),

    EDAProfile(
        mpn="BSS138",
        symbol=EDASymbol(
            lib_ref="Device:Q_NMOS_GSD",
            ref_prefix="Q",
            description="BSS138 N-Channel MOSFET for open-drain level shifting SOT-23",
            pins=[
                EDAPin("G", "1", "input",  "left"),
                EDAPin("S", "2", "passive","left"),
                EDAPin("D", "3", "passive","right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_TO_SOT_SMD:SOT-23",
            pad_count=3,
            courtyard_width_mm=2.5,
            courtyard_height_mm=3.5,
            lcsc_part_id="C52895",
        ),
        power_pin_domains={},
    ),

    # --- Actuators / Motor Drivers ---
    EDAProfile(
        mpn="TB6612FNG",
        symbol=EDASymbol(
            lib_ref="Motor_Driver:TB6612FNG",
            ref_prefix="U",
            description="Toshiba TB6612FNG Dual H-Bridge Motor Driver SSOP-24",
            pins=[
                EDAPin("VM",   "1",  "power_in", "left"),
                EDAPin("VCC",  "2",  "power_in", "left"),
                EDAPin("GND",  "3",  "power_in", "left"),
                EDAPin("AIN1", "4",  "input",    "left"),
                EDAPin("AIN2", "5",  "input",    "left"),
                EDAPin("PWMA", "6",  "input",    "left"),
                EDAPin("BIN1", "7",  "input",    "left"),
                EDAPin("BIN2", "8",  "input",    "left"),
                EDAPin("PWMB", "9",  "input",    "left"),
                EDAPin("STBY", "10", "input",    "left"),
                EDAPin("AO1",  "11", "output",   "right"),
                EDAPin("AO2",  "12", "output",   "right"),
                EDAPin("BO1",  "13", "output",   "right"),
                EDAPin("BO2",  "14", "output",   "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_SO:SSOP-24_5.3x8.2mm_P0.65mm",
            pad_count=24,
            courtyard_width_mm=7.5,
            courtyard_height_mm=10.0,
            lcsc_part_id="C98728",
        ),
        power_pin_domains={"VM": "VM_MOTOR", "VCC": "VDD_3V3", "GND": "GND"},
    ),

    EDAProfile(
        mpn="IRLZ44N",
        symbol=EDASymbol(
            lib_ref="Device:Q_NMOS_GSD",
            ref_prefix="Q",
            description="IRLZ44N N-Channel Logic-Level MOSFET 55V 47A TO-220",
            pins=[
                EDAPin("G", "1", "input",  "left"),
                EDAPin("D", "2", "passive","right"),
                EDAPin("S", "3", "passive","left"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_TO_SOT_THT:TO-220-3_Vertical",
            pad_count=3,
            courtyard_width_mm=8.0,
            courtyard_height_mm=15.0,
        ),
        power_pin_domains={},
    ),

    EDAProfile(
        mpn="1N4007",
        symbol=EDASymbol(
            lib_ref="Device:D",
            ref_prefix="D",
            description="1N4007 1A 1000V Rectifier / Flyback Diode DO-41",
            pins=[
                EDAPin("A", "1", "passive","left"),
                EDAPin("K", "2", "passive","right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal",
            pad_count=2,
            courtyard_width_mm=5.0,
            courtyard_height_mm=4.0,
        ),
        power_pin_domains={},
    ),

    # --- Connectors ---
    EDAProfile(
        mpn="USB-C-CONN",
        symbol=EDASymbol(
            lib_ref="Connector_USB:USB_C_Receptacle_GCT_USB4085",
            ref_prefix="J",
            description="USB-C Receptacle Connector",
            pins=[
                EDAPin("VBUS", "1", "power_in",     "left"),
                EDAPin("GND",  "2", "power_in",     "left"),
                EDAPin("D+",   "3", "bidirectional","right"),
                EDAPin("D-",   "4", "bidirectional","right"),
                EDAPin("CC1",  "5", "passive",      "right"),
                EDAPin("CC2",  "6", "passive",      "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Connector_USB:USB_C_Receptacle_GCT_USB4085",
            pad_count=14,
            courtyard_width_mm=10.0,
            courtyard_height_mm=7.0,
        ),
        power_pin_domains={"VBUS": "VBUS", "GND": "GND"},
    ),

    EDAProfile(
        mpn="CONN-SWD-2x5",
        symbol=EDASymbol(
            lib_ref="Connector_Debug:ARM_SWD_10",
            ref_prefix="J",
            description="ARM SWD 2x5 1.27mm Debug Header",
            pins=[
                EDAPin("VTref", "1", "power_in",     "left"),
                EDAPin("SWDIO", "2", "bidirectional","right"),
                EDAPin("GND",   "3", "power_in",     "left"),
                EDAPin("SWCLK", "4", "input",        "right"),
                EDAPin("NRST",  "5", "input",        "right"),
                EDAPin("SWO",   "6", "output",       "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical",
            pad_count=10,
            courtyard_width_mm=7.0,
            courtyard_height_mm=5.0,
        ),
        power_pin_domains={"VTref": "VDD_3V3", "GND": "GND"},
    ),

    EDAProfile(
        mpn="CONN-JTAG-2x10",
        symbol=EDASymbol(
            lib_ref="Connector_Debug:ARM_JTAG_20",
            ref_prefix="J",
            description="JTAG 2x10 2.54mm Debug Header",
            pins=[
                EDAPin("VTref", "1",  "power_in",     "left"),
                EDAPin("TMS",   "2",  "bidirectional","right"),
                EDAPin("GND",   "3",  "power_in",     "left"),
                EDAPin("TCK",   "4",  "input",        "right"),
                EDAPin("TDI",   "5",  "input",        "right"),
                EDAPin("TDO",   "6",  "output",       "right"),
                EDAPin("TRST",  "7",  "input",        "right"),
                EDAPin("NRST",  "8",  "input",        "right"),
                EDAPin("GND2",  "9",  "power_in",     "left"),
                EDAPin("GND3",  "10", "power_in",     "left"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Connector_PinHeader_2.54mm:PinHeader_2x10_P2.54mm_Vertical",
            pad_count=20,
            courtyard_width_mm=7.0,
            courtyard_height_mm=28.0,
        ),
        power_pin_domains={"VTref": "VDD_3V3", "GND": "GND", "GND2": "GND", "GND3": "GND"},
    ),

    EDAProfile(
        mpn="CONN-CAN-2PIN",
        symbol=EDASymbol(
            lib_ref="Connector:Screw_Terminal_01x02",
            ref_prefix="J",
            description="2-pin Screw Terminal for CAN bus (CANH/CANL) 5mm pitch",
            pins=[
                EDAPin("CANH", "1", "passive","right"),
                EDAPin("CANL", "2", "passive","right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal",
            pad_count=2,
            courtyard_width_mm=12.0,
            courtyard_height_mm=6.0,
        ),
        power_pin_domains={},
    ),

    EDAProfile(
        mpn="CONN-RS485-2PIN",
        symbol=EDASymbol(
            lib_ref="Connector:Screw_Terminal_01x02",
            ref_prefix="J",
            description="2-pin Screw Terminal for RS-485 (A/B) 5mm pitch",
            pins=[
                EDAPin("A", "1", "passive","right"),
                EDAPin("B", "2", "passive","right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal",
            pad_count=2,
            courtyard_width_mm=12.0,
            courtyard_height_mm=6.0,
        ),
        power_pin_domains={},
    ),

    EDAProfile(
        mpn="MICROSD-SLOT-SPI",
        symbol=EDASymbol(
            lib_ref="Connector_Card:SD_Molex_104031-0811_Horizontal",
            ref_prefix="J",
            description="MicroSD Card Slot (SPI mode)",
            pins=[
                EDAPin("VDD",  "1", "power_in", "left"),
                EDAPin("GND",  "2", "power_in", "left"),
                EDAPin("MOSI", "3", "input",    "left"),
                EDAPin("MISO", "4", "output",   "right"),
                EDAPin("SCLK", "5", "input",    "left"),
                EDAPin("CS",   "6", "input",    "left"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Connector_Card:SD_Molex_104031-0811_Horizontal",
            pad_count=9,
            courtyard_width_mm=16.0,
            courtyard_height_mm=15.0,
        ),
        power_pin_domains={"VDD": "VDD_3V3", "GND": "GND"},
    ),

    # --- Ferrite Bead ---
    EDAProfile(
        mpn="BLM18PG121SN1D",
        symbol=EDASymbol(
            lib_ref="Device:Ferrite_Bead",
            ref_prefix="FB",
            description="Murata 120Ω@100MHz Ferrite Bead 0603",
            pins=[
                EDAPin("~", "1", "passive","left"),
                EDAPin("~", "2", "passive","right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Inductor_SMD:L_0603_1608Metric",
            pad_count=2,
            courtyard_width_mm=2.3,
            courtyard_height_mm=1.8,
            lcsc_part_id="C1015",
        ),
        power_pin_domains={},
    ),

    # --- Crystals ---
    EDAProfile(
        mpn="HC49-8MHZ",
        symbol=EDASymbol(
            lib_ref="Device:Crystal",
            ref_prefix="Y",
            description="8MHz HC-49S Crystal for STM32",
            pins=[
                EDAPin("~", "1", "passive","left"),
                EDAPin("~", "2", "passive","right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Crystal:Crystal_HC49-U_Vertical",
            pad_count=2,
            courtyard_width_mm=6.0,
            courtyard_height_mm=4.5,
            lcsc_part_id="C115962",
        ),
        power_pin_domains={},
    ),

    EDAProfile(
        mpn="HC49-12MHZ",
        symbol=EDASymbol(
            lib_ref="Device:Crystal",
            ref_prefix="Y",
            description="12MHz HC-49S Crystal for RP2040",
            pins=[
                EDAPin("~", "1", "passive","left"),
                EDAPin("~", "2", "passive","right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Crystal:Crystal_HC49-U_Vertical",
            pad_count=2,
            courtyard_width_mm=6.0,
            courtyard_height_mm=4.5,
            lcsc_part_id="C115961",
        ),
        power_pin_domains={},
    ),

    EDAProfile(
        mpn="HC49-16MHZ",
        symbol=EDASymbol(
            lib_ref="Device:Crystal",
            ref_prefix="Y",
            description="16MHz HC-49S Crystal for STM32",
            pins=[
                EDAPin("~", "1", "passive","left"),
                EDAPin("~", "2", "passive","right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Crystal:Crystal_HC49-U_Vertical",
            pad_count=2,
            courtyard_width_mm=6.0,
            courtyard_height_mm=4.5,
            lcsc_part_id="C115963",
        ),
        power_pin_domains={},
    ),

    # --- Specific passives (commonly referenced by MPN in BOM) ---
    EDAProfile(
        mpn="RC0402FR-074K7L",
        symbol=EDASymbol(
            lib_ref="Device:R",
            ref_prefix="R",
            description="4.7kΩ 1% 0402 Resistor (I2C pull-up)",
            pins=[
                EDAPin("~", "1", "passive","left"),
                EDAPin("~", "2", "passive","right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Resistor_SMD:R_0402_1005Metric",
            pad_count=2,
            courtyard_width_mm=1.5,
            courtyard_height_mm=1.2,
            lcsc_part_id="C25900",
        ),
        power_pin_domains={},
    ),

    EDAProfile(
        mpn="GRM155R71C104KA88D",
        symbol=EDASymbol(
            lib_ref="Device:C",
            ref_prefix="C",
            description="100nF 16V X7R 0402 Capacitor (decoupling)",
            pins=[
                EDAPin("~", "1", "passive","left"),
                EDAPin("~", "2", "passive","right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Capacitor_SMD:C_0402_1005Metric",
            pad_count=2,
            courtyard_width_mm=1.5,
            courtyard_height_mm=1.2,
            lcsc_part_id="C307331",
        ),
        power_pin_domains={},
    ),

    EDAProfile(
        mpn="GRM188R61A106KE69D",
        symbol=EDASymbol(
            lib_ref="Device:C",
            ref_prefix="C",
            description="10µF 10V X5R 0603 Capacitor (bulk decoupling)",
            pins=[
                EDAPin("~", "1", "passive","left"),
                EDAPin("~", "2", "passive","right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Capacitor_SMD:C_0603_1608Metric",
            pad_count=2,
            courtyard_width_mm=2.3,
            courtyard_height_mm=1.8,
            lcsc_part_id="C13585",
        ),
        power_pin_domains={},
    ),
]
