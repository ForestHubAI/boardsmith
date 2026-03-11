# SPDX-License-Identifier: AGPL-3.0-or-later
"""EDA profiles for communication ICs (RF, transceiver, USB-UART, Ethernet, GSM)."""
from __future__ import annotations

from shared.knowledge.eda_schema import EDAFootprint, EDAPin, EDAProfile, EDASymbol

PROFILES: list[EDAProfile] = [
    EDAProfile(
        mpn="SX1276",
        symbol=EDASymbol(
            lib_ref="RF_Module:SX1276",
            ref_prefix="U",
            description="Semtech SX1276 LoRa/FSK Transceiver SPI",
            pins=[
                EDAPin("VDD",   "1",  "power_in",  "left"),
                EDAPin("GND",   "2",  "power_in",  "left"),
                EDAPin("MOSI",  "3",  "input",     "left"),
                EDAPin("MISO",  "4",  "output",    "right"),
                EDAPin("SCLK",  "5",  "input",     "left"),
                EDAPin("NSS",   "6",  "input",     "left"),
                EDAPin("RESET", "7",  "input",     "left"),
                EDAPin("DIO0",  "8",  "output",    "right"),
                EDAPin("DIO1",  "9",  "output",    "right"),
                EDAPin("RXTX",  "10", "output",    "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_DFN_QFN:QFN-28_5x5mm_P0.65mm",
            pad_count=29,  # 28 + EP
            courtyard_width_mm=7.0,
            courtyard_height_mm=7.0,
            lcsc_part_id="C97648",
        ),
        power_pin_domains={"VDD": "VDD_3V3", "GND": "GND"},
    ),

    EDAProfile(
        mpn="SN65HVD230",
        symbol=EDASymbol(
            lib_ref="Interface_CAN_LIN:SN65HVD230",
            ref_prefix="U",
            description="SN65HVD230 3.3V CAN Bus Transceiver SOIC-8",
            pins=[
                EDAPin("TXD",  "1", "input",        "left"),
                EDAPin("GND",  "2", "power_in",     "left"),
                EDAPin("VCC",  "3", "power_in",     "left"),
                EDAPin("RXD",  "4", "output",       "right"),
                EDAPin("Vref", "5", "output",       "right"),
                EDAPin("CANL", "6", "bidirectional","right"),
                EDAPin("CANH", "7", "bidirectional","right"),
                EDAPin("RS",   "8", "input",        "left"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            pad_count=8,
            courtyard_width_mm=5.9,
            courtyard_height_mm=6.9,
            lcsc_part_id="C136759",
        ),
        power_pin_domains={"GND": "GND", "VCC": "VDD_3V3"},
    ),

    EDAProfile(
        mpn="MAX485",
        symbol=EDASymbol(
            lib_ref="Interface_RS485:MAX485",
            ref_prefix="U",
            description="MAX485 Low-Power RS-485/RS-422 Transceiver SOIC-8",
            pins=[
                EDAPin("RO",  "1", "output",       "right"),
                EDAPin("~RE", "2", "input",        "left"),
                EDAPin("DE",  "3", "input",        "left"),
                EDAPin("DI",  "4", "input",        "left"),
                EDAPin("GND", "5", "power_in",     "left"),
                EDAPin("A",   "6", "bidirectional","right"),
                EDAPin("B",   "7", "bidirectional","right"),
                EDAPin("VCC", "8", "power_in",     "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            pad_count=8,
            courtyard_width_mm=5.9,
            courtyard_height_mm=6.9,
            lcsc_part_id="C12487",
        ),
        power_pin_domains={"GND": "GND", "VCC": "VDD_3V3"},
    ),

    EDAProfile(
        mpn="LAN8720A",
        symbol=EDASymbol(
            lib_ref="Interface_Ethernet:LAN8720A",
            ref_prefix="U",
            description="Microchip LAN8720A 10/100 Ethernet PHY RMII QFN-24",
            pins=[
                EDAPin("VDD",    "1",  "power_in",     "left"),
                EDAPin("GND",    "2",  "power_in",     "left"),
                EDAPin("TXD0",   "3",  "output",       "right"),
                EDAPin("TXD1",   "4",  "output",       "right"),
                EDAPin("TXEN",   "5",  "output",       "right"),
                EDAPin("RXD0",   "6",  "input",        "right"),
                EDAPin("RXD1",   "7",  "input",        "right"),
                EDAPin("RXER",   "8",  "input",        "right"),
                EDAPin("CRS_DV", "9",  "input",        "right"),
                EDAPin("MDIO",   "10", "bidirectional","left"),
                EDAPin("MDC",    "11", "input",        "left"),
                EDAPin("REFCLK", "12", "input",        "left"),
                EDAPin("NRST",   "13", "input",        "left"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_DFN_QFN:QFN-24_4x4mm_P0.5mm",
            pad_count=25,
            courtyard_width_mm=6.0,
            courtyard_height_mm=6.0,
            lcsc_part_id="C14889",
        ),
        power_pin_domains={"VDD": "VDD_3V3", "GND": "GND"},
    ),

    EDAProfile(
        mpn="SIM7600G-H",
        symbol=EDASymbol(
            lib_ref="RF_Module:SIM7600G-H",
            ref_prefix="U",
            description="SIMCom SIM7600G LTE Cat-4 Module (UART)",
            pins=[
                EDAPin("VCC",    "1", "power_in", "left"),
                EDAPin("GND",    "2", "power_in", "left"),
                EDAPin("TXD",    "3", "output",   "right"),
                EDAPin("RXD",    "4", "input",    "right"),
                EDAPin("PWRKEY", "5", "input",    "left"),
                EDAPin("RESET",  "6", "input",    "left"),
                EDAPin("STATUS", "7", "output",   "right"),
                EDAPin("RI",     "8", "output",   "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical",
            pad_count=10,
            courtyard_width_mm=7.0,
            courtyard_height_mm=6.5,
        ),
        power_pin_domains={"VCC": "VDD_3V8", "GND": "GND"},
    ),

    EDAProfile(
        mpn="TCA9548A",
        symbol=EDASymbol(
            lib_ref="Interface_Multiplexer:TCA9548A",
            ref_prefix="U",
            description="TI TCA9548A 8-Channel I2C Bus Switch/Mux TSSOP-24",
            pins=[
                EDAPin("VCC",   "1",  "power_in",     "left"),
                EDAPin("GND",   "2",  "power_in",     "left"),
                EDAPin("SDA",   "3",  "bidirectional","left"),
                EDAPin("SCL",   "4",  "input",        "left"),
                EDAPin("A0",    "5",  "input",        "left"),
                EDAPin("A1",    "6",  "input",        "left"),
                EDAPin("A2",    "7",  "input",        "left"),
                EDAPin("RESET", "8",  "input",        "left"),
                EDAPin("SD0",   "9",  "bidirectional","right"),
                EDAPin("SC0",   "10", "bidirectional","right"),
                EDAPin("SD1",   "11", "bidirectional","right"),
                EDAPin("SC1",   "12", "bidirectional","right"),
                EDAPin("SD2",   "13", "bidirectional","right"),
                EDAPin("SC2",   "14", "bidirectional","right"),
                EDAPin("SD3",   "15", "bidirectional","right"),
                EDAPin("SC3",   "16", "bidirectional","right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm",
            pad_count=24,
            courtyard_width_mm=5.5,
            courtyard_height_mm=9.0,
            lcsc_part_id="C130026",
        ),
        power_pin_domains={"VCC": "VDD_3V3", "GND": "GND"},
    ),

    EDAProfile(
        mpn="USBLC6-2SC6",
        symbol=EDASymbol(
            lib_ref="Protection:USBLC6-2SC6",
            ref_prefix="U",
            description="STMicro USBLC6-2SC6 USB ESD Protection SOT-23-6",
            pins=[
                EDAPin("VCC",  "1", "power_in",     "left"),
                EDAPin("I/O1", "2", "bidirectional","right"),
                EDAPin("GND",  "3", "power_in",     "left"),
                EDAPin("I/O2", "4", "bidirectional","right"),
                EDAPin("I/O3", "5", "bidirectional","right"),
                EDAPin("I/O4", "6", "bidirectional","right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_TO_SOT_SMD:SOT-23-6",
            pad_count=6,
            courtyard_width_mm=3.5,
            courtyard_height_mm=3.1,
            lcsc_part_id="C7519",
        ),
        power_pin_domains={"VCC": "VDD_5V", "GND": "GND"},
    ),

    EDAProfile(
        mpn="TJA1051T/3",
        symbol=EDASymbol(
            lib_ref="Interface_CAN_LIN:TJA1051T",
            ref_prefix="U",
            description="NXP TJA1051T/3 3.3V CAN Bus Transceiver SOIC-8",
            pins=[
                EDAPin("TXD",  "1", "input",        "left"),
                EDAPin("GND",  "2", "power_in",     "left"),
                EDAPin("VCC",  "3", "power_in",     "left"),
                EDAPin("RXD",  "4", "output",       "right"),
                EDAPin("VIO",  "5", "power_in",     "left"),
                EDAPin("CANL", "6", "bidirectional","right"),
                EDAPin("CANH", "7", "bidirectional","right"),
                EDAPin("STB",  "8", "input",        "left"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            pad_count=8,
            courtyard_width_mm=5.9,
            courtyard_height_mm=6.9,
            lcsc_part_id="C7452",
        ),
        power_pin_domains={"GND": "GND", "VCC": "VDD_5V", "VIO": "VDD_3V3"},
    ),

    EDAProfile(
        mpn="SP3485EN-L/TR",
        symbol=EDASymbol(
            lib_ref="Interface_RS485:SP3485",
            ref_prefix="U",
            description="Sipex SP3485 3.3V RS-485/RS-422 Transceiver SOIC-8",
            pins=[
                EDAPin("RO",  "1", "output",       "right"),
                EDAPin("~RE", "2", "input",        "left"),
                EDAPin("DE",  "3", "input",        "left"),
                EDAPin("DI",  "4", "input",        "left"),
                EDAPin("GND", "5", "power_in",     "left"),
                EDAPin("A",   "6", "bidirectional","right"),
                EDAPin("B",   "7", "bidirectional","right"),
                EDAPin("VCC", "8", "power_in",     "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            pad_count=8,
            courtyard_width_mm=5.9,
            courtyard_height_mm=6.9,
            lcsc_part_id="C6999",
        ),
        power_pin_domains={"GND": "GND", "VCC": "VDD_3V3"},
    ),

    EDAProfile(
        mpn="PRTR5V0U2X",
        symbol=EDASymbol(
            lib_ref="Protection:PRTR5V0U2X",
            ref_prefix="U",
            description="Nexperia PRTR5V0U2X USB ESD Protection SOT-363",
            pins=[
                EDAPin("VCC",  "1", "power_in",     "left"),
                EDAPin("D+",   "2", "bidirectional","right"),
                EDAPin("GND",  "3", "power_in",     "left"),
                EDAPin("D-",   "4", "bidirectional","right"),
                EDAPin("VBUS", "5", "power_in",     "left"),
                EDAPin("OE",   "6", "input",        "left"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_TO_SOT_SMD:SOT-363_SC-70-6",
            pad_count=6,
            courtyard_width_mm=2.9,
            courtyard_height_mm=2.5,
            lcsc_part_id="C12333",
        ),
        power_pin_domains={"VCC": "VDD_3V3", "VBUS": "VDD_5V", "GND": "GND"},
    ),
]
