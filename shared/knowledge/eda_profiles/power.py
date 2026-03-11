# SPDX-License-Identifier: AGPL-3.0-or-later
"""EDA profiles for power management ICs (LDO, Buck, Charger, Fuel Gauge)."""
from __future__ import annotations

from shared.knowledge.eda_schema import EDAFootprint, EDAPin, EDAProfile, EDASymbol

PROFILES: list[EDAProfile] = [
    EDAProfile(
        mpn="AMS1117-3.3",
        symbol=EDASymbol(
            lib_ref="Regulator_Linear:AMS1117-3.3",
            ref_prefix="U",
            description="AMS1117 3.3V 1A LDO Regulator SOT-223",
            pins=[
                EDAPin("VIN",  "1", "power_in",  "left"),
                EDAPin("GND",  "2", "power_in",  "left"),
                EDAPin("VOUT", "3", "power_out", "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
            pad_count=4,  # 3 pins + tab
            courtyard_width_mm=4.5,
            courtyard_height_mm=6.0,
            lcsc_part_id="C6186",
        ),
        power_pin_domains={"VIN": "VDD_5V", "GND": "GND", "VOUT": "VDD_3V3"},
    ),

    EDAProfile(
        mpn="AMS1117-5.0",
        symbol=EDASymbol(
            lib_ref="Regulator_Linear:AMS1117-5.0",
            ref_prefix="U",
            description="AMS1117 5.0V 800mA LDO — 12V→5V intermediate stage",
            pins=[
                EDAPin("VIN12V", "1", "power_in", "left"),
                EDAPin("GND",    "2", "power_in", "left"),
                EDAPin("VOUT5V", "3", "power_in", "right"),  # power_in to avoid KiCad ERC error
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
            pad_count=4,
            courtyard_width_mm=4.5,
            courtyard_height_mm=6.0,
            lcsc_part_id="C131085",
        ),
        power_pin_domains={"VIN12V": "VDD_12V", "GND": "GND", "VOUT5V": "VDD_5V"},
    ),

    EDAProfile(
        mpn="AP2112K-3.3",
        symbol=EDASymbol(
            lib_ref="Regulator_Linear:AP2112K-3.3",
            ref_prefix="U",
            description="AP2112K 3.3V 600mA Ultra-Low Dropout LDO SOT-25",
            pins=[
                EDAPin("VIN",  "1", "power_in",  "left"),
                EDAPin("GND",  "2", "power_in",  "left"),
                EDAPin("EN",   "3", "input",     "left"),
                EDAPin("VOUT", "4", "power_out", "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_TO_SOT_SMD:SOT-25_HandSoldering",
            pad_count=5,
            courtyard_width_mm=3.5,
            courtyard_height_mm=3.0,
            lcsc_part_id="C51118",
        ),
        power_pin_domains={"VIN": "VDD_5V", "GND": "GND", "VOUT": "VDD_3V3"},
    ),

    EDAProfile(
        mpn="AP2112K-3.3TRG1",
        symbol=EDASymbol(
            lib_ref="Regulator_Linear:AP2112K-3.3",
            ref_prefix="U",
            description="AP2112K 3.3V 600mA LDO Tape & Reel — same as AP2112K-3.3",
            pins=[
                EDAPin("VIN",  "1", "power_in",  "left"),
                EDAPin("GND",  "2", "power_in",  "left"),
                EDAPin("EN",   "3", "input",     "left"),
                EDAPin("VOUT", "4", "power_out", "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_TO_SOT_SMD:SOT-25_HandSoldering",
            pad_count=5,
            courtyard_width_mm=3.5,
            courtyard_height_mm=3.0,
            lcsc_part_id="C51118",
        ),
        power_pin_domains={"VIN": "VDD_5V", "GND": "GND", "VOUT": "VDD_3V3"},
    ),

    EDAProfile(
        mpn="MCP1700-3302E",
        symbol=EDASymbol(
            lib_ref="Regulator_Linear:MCP1700-3302E",
            ref_prefix="U",
            description="MCP1700 250mA Ultra-Low IQ LDO (1.6µA) SOT-23",
            pins=[
                EDAPin("VIN",  "1", "power_in",  "left"),
                EDAPin("VSS",  "2", "power_in",  "left"),
                EDAPin("VOUT", "3", "power_out", "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_TO_SOT_SMD:SOT-23-3_HandSoldering",
            pad_count=3,
            courtyard_width_mm=2.5,
            courtyard_height_mm=3.5,
            lcsc_part_id="C58099",
        ),
        power_pin_domains={"VIN": "VDD_3V7", "VSS": "GND", "VOUT": "VDD_3V3"},
    ),

    EDAProfile(
        mpn="MP2307DN",
        symbol=EDASymbol(
            lib_ref="Regulator_Switching:MP2307DN",
            ref_prefix="U",
            description="MP2307 3A 23V Step-Down Buck Converter SOIC-8",
            pins=[
                EDAPin("VIN",  "1", "power_in",  "left"),
                EDAPin("EN",   "2", "input",     "left"),
                EDAPin("SS",   "3", "input",     "left"),
                EDAPin("FB",   "4", "input",     "left"),
                EDAPin("COMP", "5", "passive",   "left"),
                EDAPin("GND",  "6", "power_in",  "left"),
                EDAPin("SW",   "7", "output",    "right"),
                EDAPin("BST",  "8", "passive",   "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            pad_count=8,
            courtyard_width_mm=5.9,
            courtyard_height_mm=6.9,
            lcsc_part_id="C441540",
        ),
        power_pin_domains={"VIN": "VDD_12V", "GND": "GND"},
    ),

    EDAProfile(
        mpn="TPS563200",
        symbol=EDASymbol(
            lib_ref="Regulator_Switching:TPS563200",
            ref_prefix="U",
            description="TI TPS563200 3A Synchronous Buck Converter SOT-23-6",
            pins=[
                EDAPin("VIN", "1", "power_in",  "left"),
                EDAPin("EN",  "2", "input",     "left"),
                EDAPin("GND", "3", "power_in",  "left"),
                EDAPin("SW",  "4", "output",    "right"),
                EDAPin("FB",  "5", "input",     "right"),
                EDAPin("BST", "6", "passive",   "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_TO_SOT_SMD:SOT-23-6",
            pad_count=6,
            courtyard_width_mm=3.0,
            courtyard_height_mm=3.5,
            lcsc_part_id="C523787",
        ),
        power_pin_domains={"VIN": "VDD_5V", "GND": "GND"},
    ),

    EDAProfile(
        mpn="MP1584EN",
        symbol=EDASymbol(
            lib_ref="Regulator_Switching:MP1584EN",
            ref_prefix="U",
            description="MPS MP1584EN 3A Step-Down Buck SOIC-8",
            pins=[
                EDAPin("VIN",  "1", "power_in",  "left"),
                EDAPin("EN",   "2", "input",     "left"),
                EDAPin("SS",   "3", "input",     "left"),
                EDAPin("FB",   "4", "input",     "left"),
                EDAPin("COMP", "5", "passive",   "left"),
                EDAPin("GND",  "6", "power_in",  "left"),
                EDAPin("SW",   "7", "output",    "right"),
                EDAPin("BST",  "8", "passive",   "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            pad_count=8,
            courtyard_width_mm=5.9,
            courtyard_height_mm=6.9,
            lcsc_part_id="C87538",
        ),
        power_pin_domains={"VIN": "VDD_12V", "GND": "GND"},
    ),

    EDAProfile(
        mpn="TP4056",
        symbol=EDASymbol(
            lib_ref="Battery_Management:TP4056",
            ref_prefix="U",
            description="TP4056 1A Standalone Linear Li-Ion Battery Charger",
            pins=[
                EDAPin("TEMP",  "1", "input",     "left"),
                EDAPin("PROG",  "2", "passive",   "left"),
                EDAPin("GND",   "3", "power_in",  "left"),
                EDAPin("VCC",   "4", "power_in",  "left"),
                EDAPin("BAT",   "5", "power_out", "right"),
                EDAPin("CE",    "6", "input",     "right"),
                EDAPin("STDBY", "7", "output",    "right"),
                EDAPin("CHRG",  "8", "output",    "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_SO:SOP-8_3.9x4.9mm_P1.27mm",
            pad_count=8,
            courtyard_width_mm=5.9,
            courtyard_height_mm=6.9,
            lcsc_part_id="C16581",
        ),
        power_pin_domains={"GND": "GND", "VCC": "VDD_5V", "BAT": "VBAT"},
    ),

    EDAProfile(
        mpn="MCP73831T-2ATI",
        symbol=EDASymbol(
            lib_ref="Battery_Management:MCP73831T-2ATI",
            ref_prefix="U",
            description="MCP73831 500mA Li-Ion/Li-Poly Charge Controller SOT-23-5",
            pins=[
                EDAPin("VDD",  "1", "power_in",  "left"),
                EDAPin("VSS",  "2", "power_in",  "left"),
                EDAPin("PROG", "3", "passive",   "left"),
                EDAPin("STAT", "4", "output",    "right"),
                EDAPin("VBAT", "5", "power_out", "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_TO_SOT_SMD:SOT-23-5_HandSoldering",
            pad_count=5,
            courtyard_width_mm=2.5,
            courtyard_height_mm=3.5,
            lcsc_part_id="C14879",
        ),
        power_pin_domains={"VDD": "VDD_5V", "VSS": "GND", "VBAT": "VBAT"},
    ),

    EDAProfile(
        mpn="MAX17048G+T",
        symbol=EDASymbol(
            lib_ref="Battery_Management:MAX17048G+T",
            ref_prefix="U",
            description="MAX17048 1-Cell Fuel Gauge with ModelGauge I2C (0x36)",
            pins=[
                EDAPin("VDD",   "1", "power_in",     "left"),
                EDAPin("SDA",   "2", "bidirectional", "left"),
                EDAPin("SCL",   "3", "input",         "left"),
                EDAPin("ALRT",  "4", "output",        "left"),
                EDAPin("CELL",  "5", "input",         "right"),
                EDAPin("QSTRT", "6", "input",         "right"),
                EDAPin("VSS",   "7", "power_in",      "right"),
                EDAPin("NC",    "8", "no_connect",    "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_DFN_QFN:DFN-8-1EP_2x3mm_P0.5mm_EP1x2mm",
            pad_count=9,  # 8 + EP
            courtyard_width_mm=4.0,
            courtyard_height_mm=5.0,
            lcsc_part_id="C82886",
        ),
        power_pin_domains={"VDD": "VDD_3V3", "VSS": "GND"},
    ),
]
