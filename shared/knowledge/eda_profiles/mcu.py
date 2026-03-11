# SPDX-License-Identifier: AGPL-3.0-or-later
"""EDA profiles for MCU / SoC components."""
from __future__ import annotations

from shared.knowledge.eda_schema import EDAFootprint, EDAPin, EDAProfile, EDASymbol

PROFILES: list[EDAProfile] = [
    EDAProfile(
        mpn="ESP32-C3-WROOM-02",
        symbol=EDASymbol(
            lib_ref="RF_Module:ESP32-C3-WROOM-02",
            ref_prefix="U",
            description="ESP32-C3 Wi-Fi+BLE RISC-V Module",
            pins=[
                EDAPin("3V3",        "1",  "power_in",      "left"),
                EDAPin("GND",        "2",  "power_in",      "left"),
                EDAPin("EN",         "3",  "input",         "left"),
                EDAPin("IO8/SDA",    "4",  "bidirectional", "right"),
                EDAPin("IO9/SCL",    "5",  "bidirectional", "right"),
                EDAPin("IO7/MOSI",   "6",  "bidirectional", "right"),
                EDAPin("IO2/MISO",   "7",  "bidirectional", "right"),
                EDAPin("IO6/SCLK",   "8",  "bidirectional", "right"),
                EDAPin("IO10/CS",    "9",  "bidirectional", "right"),
                EDAPin("TXD0",       "10", "output",        "right"),
                EDAPin("RXD0",       "11", "input",         "right"),
                EDAPin("USB_D+",     "12", "bidirectional", "right"),
                EDAPin("USB_D-",     "13", "bidirectional", "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="RF_Module:ESP32-C3-WROOM-02",
            pad_count=13,
            courtyard_width_mm=21.0,
            courtyard_height_mm=20.0,
        ),
        power_pin_domains={"3V3": "VDD_3V3", "GND": "GND"},
    ),

    EDAProfile(
        mpn="ESP32-WROOM-32",
        symbol=EDASymbol(
            lib_ref="RF_Module:ESP32-WROOM-32",
            ref_prefix="U",
            description="ESP32 WiFi+BT Module",
            pins=[
                EDAPin("3V3",       "1",  "power_in",      "left"),
                EDAPin("GND",       "2",  "power_in",      "left"),
                EDAPin("EN",        "3",  "input",         "left"),
                EDAPin("IO21/SDA",  "4",  "bidirectional", "right"),
                EDAPin("IO22/SCL",  "5",  "bidirectional", "right"),
                EDAPin("IO23/MOSI", "6",  "bidirectional", "right"),
                EDAPin("IO19/MISO", "7",  "bidirectional", "right"),
                EDAPin("IO18/SCLK", "8",  "bidirectional", "right"),
                EDAPin("IO5/CS",    "9",  "bidirectional", "right"),
                EDAPin("TXD0",      "10", "output",        "right"),
                EDAPin("RXD0",      "11", "input",         "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="RF_Module:ESP32-WROOM-32",
            pad_count=11,
            courtyard_width_mm=21.0,
            courtyard_height_mm=20.0,
        ),
        power_pin_domains={"3V3": "VDD_3V3", "GND": "GND"},
    ),

    EDAProfile(
        mpn="RP2040",
        symbol=EDASymbol(
            lib_ref="MCU_RaspberryPi:RP2040",
            ref_prefix="U",
            description="Raspberry Pi RP2040 Dual-Core ARM Cortex-M0+ MCU",
            pins=[
                EDAPin("DVDD",       "1",  "power_in",      "left"),
                EDAPin("IOVDD",      "2",  "power_in",      "left"),
                EDAPin("GND",        "3",  "power_in",      "left"),
                EDAPin("GP4/SDA",    "4",  "bidirectional", "right"),
                EDAPin("GP5/SCL",    "5",  "bidirectional", "right"),
                EDAPin("GP19/MOSI",  "6",  "bidirectional", "right"),
                EDAPin("GP16/MISO",  "7",  "bidirectional", "right"),
                EDAPin("GP18/SCLK",  "8",  "bidirectional", "right"),
                EDAPin("GP17/CS",    "9",  "bidirectional", "right"),
                EDAPin("USB_DP",     "10", "bidirectional", "right"),
                EDAPin("USB_DM",     "11", "bidirectional", "right"),
                EDAPin("SWDIO",      "12", "bidirectional", "right"),
                EDAPin("SWCLK",      "13", "input",         "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP5.6x5.6mm",
            pad_count=57,  # 56 + 1 exposed pad
            courtyard_width_mm=9.0,
            courtyard_height_mm=9.0,
            lcsc_part_id="C2040",
        ),
        power_pin_domains={"DVDD": "VDD_1V1", "IOVDD": "VDD_3V3", "GND": "GND"},
    ),

    EDAProfile(
        mpn="nRF52840",
        symbol=EDASymbol(
            lib_ref="MCU_Nordic:nRF52840",
            ref_prefix="U",
            description="Nordic nRF52840 BLE+USB ARM Cortex-M4 SoC",
            pins=[
                EDAPin("VDD",        "1",  "power_in",      "left"),
                EDAPin("GND",        "2",  "power_in",      "left"),
                EDAPin("P0.12/SDA",  "3",  "bidirectional", "right"),
                EDAPin("P0.11/SCL",  "4",  "bidirectional", "right"),
                EDAPin("P0.13/MOSI", "5",  "bidirectional", "right"),
                EDAPin("P0.14/MISO", "6",  "bidirectional", "right"),
                EDAPin("P0.15/SCLK", "7",  "bidirectional", "right"),
                EDAPin("P0.16/CS",   "8",  "bidirectional", "right"),
                EDAPin("USBD+",      "9",  "bidirectional", "right"),
                EDAPin("USBD-",      "10", "bidirectional", "right"),
                EDAPin("SWDIO",      "11", "bidirectional", "right"),
                EDAPin("SWDCLK",     "12", "input",         "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_DFN_QFN:AQFN-73_7x7mm_P0.5mm",
            pad_count=74,  # 73 + 1 EP
            courtyard_width_mm=9.0,
            courtyard_height_mm=9.0,
        ),
        power_pin_domains={"VDD": "VDD_3V3", "GND": "GND"},
    ),

    EDAProfile(
        mpn="STM32F103C8T6",
        symbol=EDASymbol(
            lib_ref="MCU_ST_STM32F1:STM32F103C8Tx",
            ref_prefix="U",
            description="STM32F103 ARM Cortex-M3 72MHz MCU LQFP-48",
            pins=[
                EDAPin("VDD",      "1",  "power_in",      "left"),
                EDAPin("GND",      "2",  "power_in",      "left"),
                EDAPin("VDDA",     "3",  "power_in",      "left"),
                EDAPin("PB7/SDA",  "4",  "bidirectional", "right"),
                EDAPin("PB6/SCL",  "5",  "bidirectional", "right"),
                EDAPin("PA7/MOSI", "6",  "bidirectional", "right"),
                EDAPin("PA6/MISO", "7",  "bidirectional", "right"),
                EDAPin("PA5/SCLK", "8",  "bidirectional", "right"),
                EDAPin("PA4/CS",   "9",  "bidirectional", "right"),
                EDAPin("PA9/TX",   "10", "output",        "right"),
                EDAPin("PA10/RX",  "11", "input",         "right"),
                EDAPin("NRST",     "12", "input",         "left"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_QFP:LQFP-48_7x7mm_P0.5mm",
            pad_count=48,
            courtyard_width_mm=9.0,
            courtyard_height_mm=9.0,
            lcsc_part_id="C8734",
        ),
        power_pin_domains={"VDD": "VDD_3V3", "GND": "GND", "VDDA": "VDD_3V3_ANA"},
    ),

    EDAProfile(
        mpn="STM32G431CBU6",
        symbol=EDASymbol(
            lib_ref="MCU_ST_STM32G4:STM32G431CBUx",
            ref_prefix="U",
            description="STM32G431 ARM Cortex-M4 170MHz MCU UFQFPN-48",
            pins=[
                EDAPin("VDD",      "1",  "power_in",      "left"),
                EDAPin("GND",      "2",  "power_in",      "left"),
                EDAPin("VDDA",     "3",  "power_in",      "left"),
                EDAPin("VBAT",     "4",  "power_in",      "left"),
                EDAPin("PB7/SDA",  "5",  "bidirectional", "right"),
                EDAPin("PB6/SCL",  "6",  "bidirectional", "right"),
                EDAPin("PA7/MOSI", "7",  "bidirectional", "right"),
                EDAPin("PA6/MISO", "8",  "bidirectional", "right"),
                EDAPin("PA5/SCLK", "9",  "bidirectional", "right"),
                EDAPin("PA4/CS",   "10", "bidirectional", "right"),
                EDAPin("PA9/TX",   "11", "output",        "right"),
                EDAPin("PA10/RX",  "12", "input",         "right"),
                EDAPin("NRST",     "13", "input",         "left"),
                EDAPin("PA13/SWDIO","14","bidirectional", "right"),
                EDAPin("PA14/SWCLK","15","input",         "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_DFN_QFN:UFQFPN-48_7x7mm_P0.5mm",
            pad_count=49,  # 48 + 1 EP
            courtyard_width_mm=9.0,
            courtyard_height_mm=9.0,
        ),
        power_pin_domains={
            "VDD": "VDD_3V3", "GND": "GND",
            "VDDA": "VDD_3V3_ANA", "VBAT": "VBAT",
        },
    ),

    EDAProfile(
        mpn="STM32H743VIT6",
        symbol=EDASymbol(
            lib_ref="MCU_ST_STM32H7:STM32H743VITx",
            ref_prefix="U",
            description="STM32H743 ARM Cortex-M7 480MHz MCU LQFP-100",
            pins=[
                EDAPin("VDD",      "1",  "power_in",      "left"),
                EDAPin("GND",      "2",  "power_in",      "left"),
                EDAPin("VDDA",     "3",  "power_in",      "left"),
                EDAPin("PB7/SDA",  "4",  "bidirectional", "right"),
                EDAPin("PB6/SCL",  "5",  "bidirectional", "right"),
                EDAPin("PB5/MOSI", "6",  "bidirectional", "right"),
                EDAPin("PB4/MISO", "7",  "bidirectional", "right"),
                EDAPin("PB3/SCLK", "8",  "bidirectional", "right"),
                EDAPin("PA15/CS",  "9",  "bidirectional", "right"),
                EDAPin("PA9/TX",   "10", "output",        "right"),
                EDAPin("PA10/RX",  "11", "input",         "right"),
                EDAPin("NRST",     "12", "input",         "left"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_QFP:LQFP-100_14x14mm_P0.5mm",
            pad_count=100,
            courtyard_width_mm=16.0,
            courtyard_height_mm=16.0,
        ),
        power_pin_domains={"VDD": "VDD_3V3", "GND": "GND", "VDDA": "VDD_3V3_ANA"},
    ),
]
