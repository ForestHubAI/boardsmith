# SPDX-License-Identifier: AGPL-3.0-or-later
"""EDA profiles for sensor / measurement ICs."""
from __future__ import annotations

from shared.knowledge.eda_schema import EDAFootprint, EDAPin, EDAProfile, EDASymbol

PROFILES: list[EDAProfile] = [
    EDAProfile(
        mpn="BME280",
        symbol=EDASymbol(
            lib_ref="Sensor:BME280",
            ref_prefix="U",
            description="Bosch BME280 Temperature/Humidity/Pressure I2C/SPI",
            pins=[
                EDAPin("VDD",     "1", "power_in",      "left"),
                EDAPin("GND",     "2", "power_in",      "left"),
                EDAPin("SDI/SDA", "3", "bidirectional", "left"),
                EDAPin("SCK/SCL", "4", "input",         "left"),
                EDAPin("SDO/SA0", "5", "input",         "left"),
                EDAPin("CSB",     "6", "input",         "left"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_LGA:Bosch_LGA-8_2.5x2.5mm_P0.65mm",
            pad_count=8,
            courtyard_width_mm=4.5,
            courtyard_height_mm=4.5,
            lcsc_part_id="C17024",
        ),
        power_pin_domains={"VDD": "VDD_3V3", "GND": "GND"},
    ),

    EDAProfile(
        mpn="AHT20",
        symbol=EDASymbol(
            lib_ref="Sensor:AHT20",
            ref_prefix="U",
            description="ASAIR AHT20 Temperature+Humidity I2C",
            pins=[
                EDAPin("VDD", "1", "power_in",      "left"),
                EDAPin("GND", "2", "power_in",      "left"),
                EDAPin("SDA", "3", "bidirectional", "left"),
                EDAPin("SCL", "4", "input",         "left"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_DFN_QFN:DFN-6_3x3mm_P1mm",
            pad_count=6,
            courtyard_width_mm=5.0,
            courtyard_height_mm=5.0,
            lcsc_part_id="C654673",
        ),
        power_pin_domains={"VDD": "VDD_3V3", "GND": "GND"},
    ),

    EDAProfile(
        mpn="SHTC3",
        symbol=EDASymbol(
            lib_ref="Sensor:SHTC3",
            ref_prefix="U",
            description="Sensirion SHTC3 Temperature/Humidity I2C (0x70)",
            pins=[
                EDAPin("VDD", "1", "power_in",      "left"),
                EDAPin("GND", "2", "power_in",      "left"),
                EDAPin("SDA", "3", "bidirectional", "left"),
                EDAPin("SCL", "4", "input",         "left"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_DFN_QFN:DFN-4_2x2mm_P0.5mm",
            pad_count=4,
            courtyard_width_mm=4.0,
            courtyard_height_mm=4.0,
            lcsc_part_id="C194656",
        ),
        power_pin_domains={"VDD": "VDD_3V3", "GND": "GND"},
    ),

    EDAProfile(
        mpn="INA226",
        symbol=EDASymbol(
            lib_ref="Sensor:INA226",
            ref_prefix="U",
            description="TI INA226 36V 16-bit Power Monitor I2C",
            pins=[
                EDAPin("VS",  "1", "power_in",      "left"),
                EDAPin("GND", "2", "power_in",      "left"),
                EDAPin("IN+", "3", "input",         "left"),
                EDAPin("IN-", "4", "input",         "left"),
                EDAPin("SDA", "5", "bidirectional", "left"),
                EDAPin("SCL", "6", "input",         "left"),
                EDAPin("A0",  "7", "input",         "left"),
                EDAPin("A1",  "8", "input",         "left"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            pad_count=8,
            courtyard_width_mm=5.9,
            courtyard_height_mm=6.9,
            lcsc_part_id="C138710",
        ),
        power_pin_domains={"VS": "VDD_3V3", "GND": "GND"},
    ),

    EDAProfile(
        mpn="MPU-6050",
        symbol=EDASymbol(
            lib_ref="Sensor:MPU-6050",
            ref_prefix="U",
            description="InvenSense MPU-6050 6-Axis IMU I2C",
            pins=[
                EDAPin("VDD", "1", "power_in",      "left"),
                EDAPin("GND", "2", "power_in",      "left"),
                EDAPin("SDA", "3", "bidirectional", "left"),
                EDAPin("SCL", "4", "input",         "left"),
                EDAPin("AD0", "5", "input",         "left"),
                EDAPin("INT", "6", "output",        "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_QFN:QFN-24_4x4mm_P0.5mm",
            pad_count=25,  # 24 + EP
            courtyard_width_mm=6.0,
            courtyard_height_mm=6.0,
            lcsc_part_id="C24112",
        ),
        power_pin_domains={"VDD": "VDD_3V3", "GND": "GND"},
    ),

    EDAProfile(
        mpn="ICM-42688-P",
        symbol=EDASymbol(
            lib_ref="Sensor:ICM-42688-P",
            ref_prefix="U",
            description="TDK ICM-42688-P 6-Axis IMU I2C/SPI",
            pins=[
                EDAPin("VDD",      "1", "power_in",      "left"),
                EDAPin("GND",      "2", "power_in",      "left"),
                EDAPin("SDA/SDI",  "3", "bidirectional", "left"),
                EDAPin("SCL/SCLK", "4", "input",         "left"),
                EDAPin("SDO/AD0",  "5", "input",         "left"),
                EDAPin("CS",       "6", "input",         "left"),
                EDAPin("INT1",     "7", "output",        "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_LGA:LGA-14_3x3mm",
            pad_count=14,
            courtyard_width_mm=5.0,
            courtyard_height_mm=5.0,
            lcsc_part_id="C2693720",
        ),
        power_pin_domains={"VDD": "VDD_3V3", "GND": "GND"},
    ),

    EDAProfile(
        mpn="VL53L0X",
        symbol=EDASymbol(
            lib_ref="Sensor:VL53L0X",
            ref_prefix="U",
            description="ST VL53L0X Time-of-Flight Distance Sensor I2C",
            pins=[
                EDAPin("VDD",   "1", "power_in",      "left"),
                EDAPin("GND",   "2", "power_in",      "left"),
                EDAPin("SDA",   "3", "bidirectional", "left"),
                EDAPin("SCL",   "4", "input",         "left"),
                EDAPin("XSHUT", "5", "input",         "left"),
                EDAPin("GPIO1", "6", "output",        "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_LCC:ST_VL53L0X",
            pad_count=12,
            courtyard_width_mm=5.0,
            courtyard_height_mm=5.0,
            lcsc_part_id="C91854",
        ),
        power_pin_domains={"VDD": "VDD_2V8", "GND": "GND"},
    ),

    EDAProfile(
        mpn="ADS8681",
        symbol=EDASymbol(
            lib_ref="Analog:ADS8681",
            ref_prefix="U",
            description="TI ADS8681 16-bit 1MSPS SPI ADC",
            pins=[
                EDAPin("VDD",      "1", "power_in", "left"),
                EDAPin("GND",      "2", "power_in", "left"),
                EDAPin("SDI/MOSI", "3", "input",    "left"),
                EDAPin("SDO/MISO", "4", "output",   "right"),
                EDAPin("SCLK",     "5", "input",    "left"),
                EDAPin("CS",       "6", "input",    "left"),
                EDAPin("INP",      "7", "input",    "right"),
                EDAPin("INM",      "8", "input",    "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_SO:TSSOP-16_4.4x5mm_P0.65mm",
            pad_count=16,
            courtyard_width_mm=6.5,
            courtyard_height_mm=7.0,
        ),
        power_pin_domains={"VDD": "VDD_3V3", "GND": "GND"},
    ),

    EDAProfile(
        mpn="SSD1306",
        symbol=EDASymbol(
            lib_ref="Display:SSD1306",
            ref_prefix="U",
            description="Solomon SSD1306 128x64 OLED Controller I2C/SPI",
            pins=[
                EDAPin("VDD",    "1", "power_in",      "left"),
                EDAPin("GND",    "2", "power_in",      "left"),
                EDAPin("SDA/D1", "3", "bidirectional", "left"),
                EDAPin("SCL/D0", "4", "input",         "left"),
                EDAPin("RES",    "5", "input",         "left"),
                EDAPin("D/C",    "6", "input",         "left"),
                EDAPin("CS",     "7", "input",         "left"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_QFN:QFN-32_5x5mm_P0.5mm",
            pad_count=33,  # 32 + EP
            courtyard_width_mm=7.0,
            courtyard_height_mm=7.0,
        ),
        power_pin_domains={"VDD": "VDD_3V3", "GND": "GND"},
    ),

    EDAProfile(
        mpn="HC-SR04",
        symbol=EDASymbol(
            lib_ref="Sensor:HC-SR04",
            ref_prefix="U",
            description="HC-SR04 Ultrasonic Distance Sensor Module",
            pins=[
                EDAPin("VCC",  "1", "power_in", "left"),
                EDAPin("TRIG", "2", "input",    "right"),
                EDAPin("ECHO", "3", "output",   "right"),
                EDAPin("GND",  "4", "power_in", "left"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
            pad_count=4,
            courtyard_width_mm=7.5,
            courtyard_height_mm=4.5,
        ),
        power_pin_domains={"VCC": "VDD_5V", "GND": "GND"},
    ),
]
