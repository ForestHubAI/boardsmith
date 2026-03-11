# SPDX-License-Identifier: AGPL-3.0-or-later
"""KiCad symbol + footprint mapping for known components.

Maps MPN strings to KiCad symbol definitions (pins, footprint, ref prefix).
Unknown MPNs fall back to _generic_symbol() which auto-generates pins
from the component's interface_types list.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PinDef:
    name: str
    number: str
    type: str = "bidirectional"   # input | output | bidirectional | power_in | power_out | passive
    side: str = "left"            # left | right


@dataclass
class SymbolDef:
    ref_prefix: str   # "U", "R", "C", "J", …
    footprint: str    # KiCad footprint reference e.g. "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
    pins: list[PinDef] = field(default_factory=list)
    description: str = ""
    kicad_ref: str = ""  # KiCad canonical name "LibName:PartName", "" if not in KiCad


# ---------------------------------------------------------------------------
# Known component symbol definitions
# ---------------------------------------------------------------------------

SYMBOL_MAP: dict[str, SymbolDef] = {
    # --- MCUs ---
    "ESP32-C3-WROOM-02": SymbolDef(
        ref_prefix="U",
        footprint="RF_Module:ESP32-C3-WROOM-02",
        description="ESP32-C3 Wi-Fi+BLE RISC-V Module",
        # Real castellated pad numbers per ESP32-C3-WROOM-02 datasheet + KiCad RF_Module symbol:
        # Left column (top→bottom): 1=3V3, 2=EN, 3=IO4, 4=IO5, 5=IO6, 6=IO7, 7=IO8, 8=IO9, 9=GND
        # Right column (bottom→top): 10=IO10, 11=IO20/RXD0, 12=IO21/TXD0, 13=IO18(USB_D-),
        #                            14=IO19(USB_D+), 15=IO3, 16=IO2, 17=IO1, 18=IO0
        # Pad 19 = GND (thermal pad underside)
        pins=[
            # Left column (top→bottom, per datasheet): pads 1-9
            PinDef("3V3",        "1",  "power_in",     "left"),
            PinDef("EN",         "2",  "input",        "left"),
            PinDef("IO4",        "3",  "bidirectional","left"),   # fix: was "right"
            PinDef("IO5",        "4",  "bidirectional","left"),   # fix: was "right"
            PinDef("IO6/SCLK",   "5",  "bidirectional","left"),   # fix: was "right"
            PinDef("IO7/MOSI",   "6",  "bidirectional","left"),   # fix: was "right"
            PinDef("IO8/SDA",    "7",  "bidirectional","left"),   # fix: was "right"
            PinDef("IO9/SCL",    "8",  "bidirectional","left"),   # fix: was "right"
            PinDef("GND",        "9",  "power_in",     "left"),
            # Right column (bottom→top, per datasheet): pads 10-18
            PinDef("IO10/CS",    "10", "bidirectional","right"),
            PinDef("RXD0",       "11", "input",        "right"),
            PinDef("TXD0",       "12", "output",       "right"),
            PinDef("USB_D-",     "13", "bidirectional","right"),
            PinDef("USB_D+",     "14", "bidirectional","right"),
            PinDef("IO3",        "15", "bidirectional","right"),
            PinDef("IO2/MISO",   "16", "bidirectional","right"),
            PinDef("IO1",        "17", "bidirectional","right"),
            PinDef("IO0",        "18", "bidirectional","right"),
        ],

    kicad_ref="RF_Module:ESP32-C3-WROOM-02",),
    "ESP32-WROOM-32": SymbolDef(
        ref_prefix="U",
        footprint="RF_Module:ESP32-WROOM-32",
        description="ESP32 WiFi+BT Module",
        # Real castellated pad numbers per Espressif ESP32-WROOM-32 datasheet + KiCad RF_Module symbol:
        # Left column  (pads 1-15, x=-8.75): 1=GND, 2=3V3, 3=EN, 4=IO36, 5=IO39,
        #   6=IO34, 7=IO35, 8=IO32, 9=IO33, 10=IO25, 11=IO26, 12=IO27, 13=IO14, 14=IO12, 15=IO13(bottom-L)
        # Right column (pads 24-38, x=+8.75): 24=IO15, 25=IO2, 26=IO0, 27=IO4, 28=IO16,
        #   29=IO17, 30=IO5, 31=IO18/SCLK, 32=IO19/MISO, 33=NC, 34=IO21, 35=RXD0, 36=TXD0, 37=IO22, 38=IO23
        # Pads 16-23 = bottom row (not modelled), Pad 39 = GND thermal
        pins=[
            # Left column (pads 1-15, per KiCad RF_Module:ESP32-WROOM-32)
            PinDef("GND",       "1",  "power_in",     "left"),
            PinDef("3V3",       "2",  "power_in",     "left"),
            PinDef("EN",        "3",  "input",        "left"),
            PinDef("IO36",      "4",  "input",        "left"),   # fix: was missing
            PinDef("IO39",      "5",  "input",        "left"),   # fix: was missing
            PinDef("IO34",      "6",  "input",        "left"),   # fix: was missing
            PinDef("IO35",      "7",  "input",        "left"),   # fix: was missing
            PinDef("IO32",      "8",  "bidirectional","left"),   # fix: was missing
            PinDef("IO33",      "9",  "bidirectional","left"),   # fix: was missing
            PinDef("IO25",      "10", "bidirectional","left"),   # fix: was missing
            PinDef("IO26",      "11", "bidirectional","left"),   # fix: was missing
            PinDef("IO27",      "12", "bidirectional","left"),   # fix: was missing
            PinDef("IO14",      "13", "bidirectional","left"),   # fix: was missing
            PinDef("IO12",      "14", "bidirectional","left"),   # fix: was missing
            # Right column (pads 24-38, per KiCad RF_Module:ESP32-WROOM-32)
            PinDef("IO15",      "24", "bidirectional","right"),
            PinDef("IO2",       "25", "bidirectional","right"),
            PinDef("IO0",       "26", "bidirectional","right"),
            PinDef("IO4",       "27", "bidirectional","right"),
            PinDef("IO16",      "28", "bidirectional","right"),
            PinDef("IO17",      "29", "bidirectional","right"),
            PinDef("IO5/CS",    "30", "bidirectional","right"),
            PinDef("IO18/SCLK", "31", "bidirectional","right"),
            PinDef("IO19/MISO", "32", "bidirectional","right"),
            PinDef("IO21/SDA",  "34", "bidirectional","right"),
            PinDef("RXD0",      "35", "input",        "right"),
            PinDef("TXD0",      "36", "output",       "right"),
            PinDef("IO22/SCL",  "37", "bidirectional","right"),
            PinDef("IO23/MOSI", "38", "bidirectional","right"),
        ],
    
    kicad_ref="RF_Module:ESP32-WROOM-32",),
    "ESP32-S3-WROOM-1": SymbolDef(
        ref_prefix="U",
        footprint="RF_Module:ESP32-S3-WROOM-1",
        description="ESP32-S3 Wi-Fi+BLE Dual-core LX7 Module",
        # Real castellated pad numbers per Espressif ESP32-S3-WROOM-1 datasheet + KiCad RF_Module symbol:
        # Left column (1-14, top→bottom): 1=GND, 2=3V3, 3=EN, 4=IO4, 5=IO5, 6=IO6, 7=IO7,
        #   8=IO15, 9=IO16, 10=IO17, 11=IO18, 12=IO8(SDA), 13=USB_D-(IO19), 14=USB_D+(IO20)
        # Right column (27-40, top→bottom): ..., 36=RXD0(IO44), 37=TXD0(IO43), 38=IO2,
        #   39=IO1, 40=IO0; also 17=IO9(SCL), 18=IO10(CS), 19=IO11(MOSI), 20=IO12(SCLK), 21=IO13(MISO)
        # Pad 41 = GND (thermal)
        pins=[
            # Left column (pads 1-14, top→bottom per datasheet)
            PinDef("GND",        "1",  "power_in",     "left"),
            PinDef("3V3",        "2",  "power_in",     "left"),
            PinDef("EN",         "3",  "input",        "left"),
            PinDef("IO8/SDA",    "12", "bidirectional","left"),   # fix: was "right"
            PinDef("USB_D-",     "13", "bidirectional","left"),   # fix: was "right" (IO19)
            PinDef("USB_D+",     "14", "bidirectional","left"),   # fix: was "right" (IO20)
            # Right column (pads 17-21, 36-37 per datasheet)
            PinDef("IO9/SCL",    "17", "bidirectional","right"),
            PinDef("IO10/CS",    "18", "bidirectional","right"),
            PinDef("IO11/MOSI",  "19", "bidirectional","right"),
            PinDef("IO12/SCLK",  "20", "bidirectional","right"),
            PinDef("IO13/MISO",  "21", "bidirectional","right"),
            PinDef("RXD0",       "36", "input",        "right"),
            PinDef("TXD0",       "37", "output",       "right"),
        ],
    
    kicad_ref="RF_Module:ESP32-S3-WROOM-1",),
    "STM32F746ZGT6": SymbolDef(
        ref_prefix="U",
        footprint="Package_QFP:LQFP-144_20x20mm_P0.5mm",
        description="STM32F7 Cortex-M7 216MHz High-Performance",
        # Physical pad numbers from STM32F746ZG LQFP-144 datasheet (DS10916).
        # Confirmed via Utmel/Digi-Key snippet: PA5=41, PA6=42, PA7=43, PA9=101, PA10=102,
        # PA11=103, PA12=104, PA13=105, PA14=109, PB6=136, PB7=137.
        # NRST=14, VDDA=21, VSSA=22, VDD=1 (primary), VSS=23 (primary), BOOT0=138.
        # PA11 and PA12 are single physical pads with both USB and CAN alternate functions.
        # They were previously listed twice (CAN + USB) — merged to avoid duplicate pad error.
        # Multiple VDD pads: 1, 24, 47, 73, 96, 120, 143 (all must be connected on PCB).
        # Multiple VSS pads: 23, 46, 72, 95, 119, 144 (all must be connected on PCB).
        pins=[
            PinDef("VDD",              "1",   "power_in",     "left"),
            PinDef("VSS",              "23",  "power_in",     "left"),
            PinDef("VDDA",             "21",  "power_in",     "left"),
            PinDef("NRST",             "14",  "input",        "left"),
            PinDef("BOOT0",            "138", "input",        "left"),
            PinDef("PB6/SCL",          "136", "bidirectional","right"),
            PinDef("PB7/SDA",          "137", "bidirectional","right"),
            PinDef("PA5/SCK",          "41",  "bidirectional","right"),
            PinDef("PA6/MISO",         "42",  "bidirectional","right"),
            PinDef("PA7/MOSI",         "43",  "bidirectional","right"),
            PinDef("PA9/TX",           "101", "output",       "right"),
            PinDef("PA10/RX",          "102", "input",        "right"),
            PinDef("PA11/DM/CAN_RX",   "103", "bidirectional","right"),  # USB OTG DM + CAN1_RX
            PinDef("PA12/DP/CAN_TX",   "104", "bidirectional","right"),  # USB OTG DP + CAN1_TX
            PinDef("PA13/SWDIO",       "105", "bidirectional","right"),
            PinDef("PA14/SWCLK",       "109", "input",        "right"),
            PinDef("PA4",              "40",  "bidirectional","right"),
            PinDef("PB12",             "73",  "bidirectional","right"),
            PinDef("PE11",             "55",  "bidirectional","right"),
            PinDef("PG10",             "125", "bidirectional","right"),
        ],
    
    kicad_ref="MCU_ST_STM32F7:STM32F746ZGTx",),
    "MIMXRT1062DVJ6A": SymbolDef(
        ref_prefix="U",
        footprint="Package_BGA:BGA-196_12x12mm_Layout14x14_P0.8mm",
        description="NXP i.MX RT1062 Crossover MCU 600MHz",
        # Physical MAPBGA-196 ball IDs from IMXRT1060CEC datasheet Rev.4 (NXP, 04/2024),
        # Tables 85–86 (supply contacts + functional contacts).
        # Ball IDs are alphanumeric: row letter (A–N) + column number (1–14).
        # VDD_SOC_IN supply distributed across F6/F7/F8/F9/G6/G9/H6/H9/J9 — representative F7 used.
        # VSS distributed across 19 balls — representative G7 used.
        # ENET_MDC/MDIO are ALT0 mux on GPIO_EMC_40/41 (balls A7/C7), per NXP RM IOMUXC + CircuitPython.
        # JTAG_TMS/TCK are ALT0 on GPIO_AD_B0_06/07 (balls E14/F12).
        # POR_B is the physical system cold-reset input (VDD_SNVS_IN domain), ball M7.
        pins=[
            PinDef("VDD_SOC_IN",  "F7",  "power_in",     "left"),   # representative; also F6/F8/F9/G6/G9/H6/H9/J9
            PinDef("VSS",         "G7",  "power_in",     "left"),   # representative; 19 GND balls total
            PinDef("VDD_SNVS_IN", "M9",  "power_in",     "left"),
            PinDef("POR_B",       "M7",  "input",        "left"),   # active-low cold reset (= RESET_B)
            PinDef("GPIO_AD_B0_02/LPI2C1_SCL", "M11", "bidirectional","right"),
            PinDef("GPIO_AD_B0_03/LPI2C1_SDA", "G11", "bidirectional","right"),
            PinDef("GPIO_SD_B0_00/LPSPI1_SCK", "J4",  "bidirectional","right"),
            PinDef("GPIO_SD_B0_01",            "J3",  "bidirectional","right"),
            PinDef("GPIO_SD_B0_02/LPSPI1_MOSI","J1",  "output",      "right"),
            PinDef("GPIO_SD_B0_03/LPSPI1_MISO","K1",  "input",       "right"),
            PinDef("GPIO_AD_B0_12/LPI2C1_SCL", "K14", "bidirectional","right"),
            PinDef("GPIO_AD_B0_13/LPI2C1_SDA", "L14", "bidirectional","right"),
            PinDef("GPIO_AD_B1_08/LPI2C2_SCL", "H13", "bidirectional","right"),
            PinDef("GPIO_AD_B1_09/LPI2C2_SDA", "M13", "bidirectional","right"),
            PinDef("USB_OTG1_DP",              "L8",  "bidirectional","right"),
            PinDef("USB_OTG1_DN",              "M8",  "bidirectional","right"),
            PinDef("ENET_MDC",                 "A7",  "output",      "right"),   # GPIO_EMC_40 ALT0
            PinDef("ENET_MDIO",                "C7",  "bidirectional","right"),  # GPIO_EMC_41 ALT0
            PinDef("JTAG_TMS/SWDIO",           "E14", "bidirectional","right"),  # GPIO_AD_B0_06 ALT0
            PinDef("JTAG_TCK/SWCLK",           "F12", "input",       "right"),  # GPIO_AD_B0_07 ALT0
            PinDef("GPIO_AD_B0_00",            "M14", "bidirectional","right"),
            PinDef("GPIO_AD_B0_01",            "H10", "bidirectional","right"),
            PinDef("GPIO_AD_B0_04",            "F11", "bidirectional","right"),
        ],
    ),
    "LPC55S69JBD100": SymbolDef(
        ref_prefix="U",
        footprint="Package_QFP:LQFP-100_14x14mm_P0.5mm",
        description="NXP LPC55S69 Dual Cortex-M33 TrustZone",
        # Physical pad numbers from NXP LPC55S6x datasheet Rev.2.5 (2024-08-29), Table 3.
        # LQFP-100 (HLQFP100) — pads 1–100 CCW from notch.
        # VDD (I/O supply) at pads 8,15,16,25,43,44,54,63,69,75,84,95,100 — representative pad 8.
        # SWDIO = PIO0_11 (pad 13), SWDCLK = PIO0_12 (pad 12) — default SWD pads at reset.
        # SPI: PIO0_20/MOSI=74, PIO0_18/MISO=56, PIO0_19/SCK=90, PIO0_14/SSEL0=72 (FC3/FC4).
        # UART FC0: PIO0_30/TX=94, PIO0_29/RX=92. I2C FC0: PIO0_23/SCL=20, PIO0_24/SDA=70.
        # NOTE: PIO0_2 (pad 81) and PIO0_3 (pad 83) are JTAG TRST/TCK — NOT SWD pins.
        pins=[
            PinDef("VDD",              "8",  "power_in",     "left"),   # representative; also 15/16/25/43/44/54/63/69/75/84/95/100
            PinDef("VDDA",             "9",  "power_in",     "left"),
            PinDef("VSS",              "10", "power_in",     "left"),   # VSSA analog ground
            PinDef("RESETN",           "32", "input",        "left"),
            PinDef("PIO0_11/SWDIO",    "13", "bidirectional","right"),
            PinDef("PIO0_12/SWDCLK",   "12", "input",        "right"),
            PinDef("PIO0_23/I2C0_SCL", "20", "bidirectional","right"),
            PinDef("PIO0_24/I2C0_SDA", "70", "bidirectional","right"),
            PinDef("PIO0_20/MOSI",     "74", "output",       "right"),
            PinDef("PIO0_18/MISO",     "56", "input",        "right"),
            PinDef("PIO0_19/SCK",      "90", "bidirectional","right"),
            PinDef("PIO0_14/SSEL0",    "72", "input",        "right"),
            PinDef("PIO0_30/FC0_TX",   "94", "output",       "right"),
            PinDef("PIO0_29/FC0_RX",   "92", "input",        "right"),
            PinDef("PIO1_1",            "40", "bidirectional","right"),   # LPC55S69 GPIO PIO1_1, pad 40
        ],
    ),
    "RP2040": SymbolDef(
        ref_prefix="U",
        footprint="Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm",
        description="Raspberry Pi RP2040 MCU",
        # Physical pad numbers from RP2040 QFN-56 datasheet (CCW from pad 1 at
        # top of west side): West=1-14, South=15-28, East=29-42, North=43-56, EP=57
        pins=[
            # --- West side (pads 1-14, top to bottom) ---
            PinDef("GP0/TX",    "1",  "output",       "left"),
            PinDef("GP1/RX",    "2",  "input",        "left"),
            PinDef("GND",       "3",  "power_in",     "left"),
            PinDef("GP2",       "4",  "bidirectional","left"),
            PinDef("GP3",       "5",  "bidirectional","left"),
            PinDef("GP4/SDA",   "6",  "bidirectional","left"),
            PinDef("GP5/SCL",   "7",  "bidirectional","left"),
            PinDef("GP6",       "8",  "bidirectional","left"),
            PinDef("GP7",       "9",  "bidirectional","left"),
            PinDef("IOVDD",     "10", "power_in",     "left"),
            PinDef("GND2",      "11", "power_in",     "left"),
            PinDef("USB_DM",    "12", "bidirectional","left"),
            PinDef("USB_DP",    "13", "bidirectional","left"),
            PinDef("VDD_USB",   "14", "power_in",     "left"),
            # --- South side (pads 15-28, left to right) ---
            PinDef("GND3",      "15", "power_in",     "right"),
            PinDef("GND4",      "16", "power_in",     "right"),
            PinDef("GP8",       "17", "bidirectional","right"),
            PinDef("GP9",       "18", "bidirectional","right"),
            PinDef("GP10",      "19", "bidirectional","right"),
            PinDef("GP11",      "20", "bidirectional","right"),
            PinDef("GP12",      "21", "bidirectional","right"),
            PinDef("GP13",      "22", "bidirectional","right"),
            PinDef("IOVDD2",    "23", "power_in",     "right"),
            PinDef("GND5",      "24", "power_in",     "right"),
            PinDef("GP14",      "25", "bidirectional","right"),
            PinDef("GP15",      "26", "bidirectional","right"),
            PinDef("GP16/MISO", "27", "bidirectional","right"),
            PinDef("GP17/CS",   "28", "bidirectional","right"),
            # --- East side (pads 29-42, bottom to top) ---
            PinDef("GP18/SCLK", "29", "bidirectional","right"),
            PinDef("GP19/MOSI", "30", "bidirectional","right"),
            PinDef("GND6",      "31", "power_in",     "right"),
            PinDef("DVDD",      "32", "power_in",     "right"),
            PinDef("GP20",      "33", "bidirectional","right"),
            PinDef("GP21",      "34", "bidirectional","right"),
            PinDef("GND7",      "35", "power_in",     "right"),
            PinDef("IOVDD3",    "36", "power_in",     "right"),
            PinDef("GP22",      "37", "bidirectional","right"),
            PinDef("GND8",      "38", "power_in",     "right"),
            PinDef("TESTEN",    "39", "no_connect",   "right"),
            PinDef("SWCLK",     "40", "input",        "right"),
            PinDef("SWDIO",     "41", "bidirectional","right"),
            PinDef("GND9",      "42", "power_in",     "right"),
            # --- North side (pads 43-56, right to left) ---
            PinDef("DVDD2",     "43", "power_in",     "right"),
            PinDef("GP25",      "44", "bidirectional","right"),
            PinDef("GP26/A0",   "45", "bidirectional","right"),
            PinDef("GP27/A1",   "46", "bidirectional","right"),
            PinDef("GP28/A2",   "47", "bidirectional","right"),
            PinDef("GND10",     "48", "power_in",     "right"),
            PinDef("VREG_VIN",  "49", "power_in",     "right"),
            PinDef("VREG_VOUT", "50", "passive",      "right"),
            PinDef("ADC_AVDD",  "51", "power_in",     "right"),
            PinDef("GND11",     "52", "power_in",     "right"),
            PinDef("XIN",       "53", "input",        "right"),
            PinDef("XOUT",      "54", "output",       "right"),
            PinDef("GND12",     "55", "power_in",     "right"),
            PinDef("DVDD3",     "56", "power_in",     "right"),
            # EP: thermal pad (pad 57)
            PinDef("GND_EP",    "57", "power_in",     "right"),
        ],
    
    kicad_ref="MCU_RaspberryPi:RP2040",),
    "nRF52840": SymbolDef(
        ref_prefix="U",
        footprint="Package_DFN_QFN:Nordic_AQFN-73-1EP_7x7mm_P0.5mm",
        description="Nordic nRF52840 BLE+USB SoC",
        # AQFN-73 uses BGA alphanumeric pad IDs (not integers!).
        # Source: KiCad MCU_Nordic.kicad_sym official symbol (generator_version "9.0")
        # Selected pad IDs for the exposed GPIO/power signals:
        #   B1=VDD, B7=VSS(GND), AD2=VBUS, AD4=D-, AD6=D+
        #   L1=P0.06(TX), N1=P0.08(RX)
        #   T2=P0.11(SCL,TRACEDATA2), U1=P0.12(SDA,TRACEDATA1)
        #   AD8=P0.13(MOSI), AC9=P0.14(MISO), AD10=P0.15(SCLK), AC11=P0.16(CS)
        #   AC24=SWDIO, AA24=SWDCLK
        # EP (exposed pad) = GND; VDDH=Y2; DEC* pads require decoupling caps
        pins=[
            PinDef("VDD",       "B1",   "power_in",     "left"),   # was "1"
            PinDef("GND",       "B7",   "power_in",     "left"),   # was "2"
            PinDef("P0.12/SDA", "U1",   "bidirectional","right"),  # was "3"
            PinDef("P0.11/SCL", "T2",   "bidirectional","right"),  # was "4"
            PinDef("P0.13/MOSI","AD8",  "bidirectional","right"),  # was "5"
            PinDef("P0.14/MISO","AC9",  "bidirectional","right"),  # was "6"
            PinDef("P0.15/SCLK","AD10", "bidirectional","right"),  # was "7"
            PinDef("P0.16/CS",  "AC11", "bidirectional","right"),  # was "8"
            PinDef("P0.06/TX",  "L1",   "output",       "right"),  # was "9"
            PinDef("P0.08/RX",  "N1",   "input",        "right"),  # was "10"
            PinDef("USBD+",     "AD6",  "bidirectional","right"),  # was "11"
            PinDef("USBD-",     "AD4",  "bidirectional","right"),  # was "12"
            PinDef("SWDIO",     "AC24", "bidirectional","right"),  # was "13"
            PinDef("SWDCLK",    "AA24", "input",        "right"),  # was "14"
        ],
    
    kicad_ref="MCU_Nordic:nRF52840",),
    "STM32F103C8T6": SymbolDef(
        ref_prefix="U",
        footprint="Package_QFP:LQFP-48_7x7mm_P0.5mm",
        description="STM32F103 ARM Cortex-M3 MCU",
        # Physical pad numbers from STM32F103C8T6 LQFP-48 datasheet (DS5319 Rev20):
        # CCW from notch: 1=VBAT, 2=PC13, 3=PC14, 4=PC15, 5=PD0, 6=PD1, 7=NRST, 8=VSSA,
        # 9=VDDA, 10=PA0..17=PA7, 18=PB0, 19=PB1, 20=PB2, 21=PB10, 22=PB11,
        # 23=VSS_1, 24=VDD_1, 25=PB12..28=PB15, 29=PA8..34=PA13, 35=VSS_2, 36=VDD_2,
        # 37=PA14, 38=PA15, 39=PB3..43=PB7, 44=BOOT0, 45=PB8, 46=PB9, 47=VSS_3, 48=VDD_3
        pins=[
            PinDef("VDD",        "24", "power_in",     "left"),   # VDD_1 (first VDD pad)
            PinDef("GND",        "23", "power_in",     "left"),   # VSS_1 (first VSS pad)
            PinDef("VDDA",       "9",  "power_in",     "left"),
            PinDef("NRST",       "7",  "input",        "left"),
            PinDef("BOOT0",      "44", "input",        "left"),   # pull to GND for normal boot
            PinDef("PB7/SDA",    "43", "bidirectional","right"),
            PinDef("PB6/SCL",    "42", "bidirectional","right"),
            PinDef("PA7/MOSI",   "17", "bidirectional","right"),
            PinDef("PA6/MISO",   "16", "bidirectional","right"),
            PinDef("PA5/SCLK",   "15", "bidirectional","right"),
            PinDef("PA4/CS",     "14", "bidirectional","right"),
            PinDef("PA9/TX",     "30", "output",       "right"),
            PinDef("PA10/RX",    "31", "input",        "right"),
            # Extra GPIOs for SPI CS and other uses
            PinDef("PB12",       "25", "bidirectional","right"),
            PinDef("PB0",        "18", "bidirectional","right"),
            PinDef("PA3",        "13", "bidirectional","right"),
            PinDef("PA11/CAN_RX","32", "input",        "right"),
            PinDef("PA12/CAN_TX","33", "output",       "right"),
            PinDef("PA13/SWDIO", "34", "bidirectional","right"),
            PinDef("PA14/SWCLK", "37", "input",        "right"),
        ],
    
    kicad_ref="MCU_ST_STM32F1:STM32F103C8Tx",),
    "STM32H743VIT6": SymbolDef(
        ref_prefix="U",
        footprint="Package_QFP:LQFP-100_14x14mm_P0.5mm",
        description="STM32H743 ARM Cortex-M7 480MHz MCU",
        # Physical pad numbers from STM32H743VI LQFP-100 datasheet (DS12110).
        # VDD at multiple pads: 11, 27, 50, 75, 100 (use 11 as primary).
        # VSS at multiple pads: 10, 26, 49, 74, 99 (use 10 as primary).
        # NRST=25, VDDA=22, VSSA=23, BOOT0=60.
        # PB-port SPI1: PB3=89, PB4=90, PB5=91, PB6=92, PB7=93.
        # PA-port UART/USB/CAN: PA9=67, PA10=68, PA11=69, PA12=70, PA13=72, PA14=76, PA15=77.
        pins=[
            PinDef("VDD",          "11", "power_in",     "left"),
            PinDef("GND",          "10", "power_in",     "left"),
            PinDef("VDDA",         "22", "power_in",     "left"),
            PinDef("NRST",         "25", "input",        "left"),
            PinDef("BOOT0",        "60", "input",        "left"),
            PinDef("PB7/SDA",      "93", "bidirectional","right"),
            PinDef("PB6/SCL",      "92", "bidirectional","right"),
            PinDef("PB5/MOSI",     "91", "bidirectional","right"),
            PinDef("PB4/MISO",     "90", "bidirectional","right"),
            PinDef("PB3/SCLK",     "89", "bidirectional","right"),
            PinDef("PA15/CS",      "77", "bidirectional","right"),
            PinDef("PA9/TX",       "67", "output",       "right"),
            PinDef("PA10/RX",      "68", "input",        "right"),
            PinDef("PA4",          "40", "bidirectional","right"),
            PinDef("PB12",         "51", "bidirectional","right"),
            PinDef("PE3",          "2",  "bidirectional","right"),
            PinDef("PE11",         "42", "bidirectional","right"),
            PinDef("PA11/CAN_RX",  "69", "input",        "right"),
            PinDef("PA12/CAN_TX",  "70", "output",       "right"),
            PinDef("PA13/SWDIO",   "72", "bidirectional","right"),
            PinDef("PA14/SWCLK",   "76", "input",        "right"),
        ],
    
    kicad_ref="MCU_ST_STM32H7:STM32H743VITx",),
    "STM32F405RGT6": SymbolDef(
        ref_prefix="U",
        footprint="Package_QFP:LQFP-64_10x10mm_P0.5mm",
        description="STM32F405 ARM Cortex-M4 168MHz MCU with I2S",
        # Physical pad numbers from STM32F405RGT6 LQFP-64 (DS8597 + sunpcb F407 cross-ref + F401 LQFP-64 confirmed):
        # LQFP-64 layout identical to STM32F401/F407 LQFP-64 (same package pinout across F4 family).
        # Note: PE port does NOT exist in LQFP-64 (only in LQFP-100/144) — PE3 removed.
        # Multiple VDD pads: 19, 32, 48, 64 → use 19 as primary.
        # Multiple VSS pads: 18, 31, 47, 63 → use 18 as primary.
        pins=[
            PinDef("VDD",         "19", "power_in",     "left"),
            PinDef("GND",         "18", "power_in",     "left"),
            PinDef("VDDA",        "13", "power_in",     "left"),
            PinDef("NRST",        "7",  "input",        "left"),
            PinDef("BOOT0",       "60", "input",        "left"),
            PinDef("PB7/SDA",     "59", "bidirectional","right"),
            PinDef("PB6/SCL",     "58", "bidirectional","right"),
            PinDef("PA7/MOSI",    "23", "bidirectional","right"),
            PinDef("PA6/MISO",    "22", "bidirectional","right"),
            PinDef("PA5/SCLK",    "21", "bidirectional","right"),
            PinDef("PA4/CS",      "20", "bidirectional","right"),
            PinDef("PA9/TX",      "42", "output",       "right"),
            PinDef("PA10/RX",     "43", "input",        "right"),
            PinDef("PC7/I2S_MCK", "38", "output",       "right"),
            PinDef("PC10/I2S_SCK","51", "output",       "right"),
            PinDef("PC12/I2S_SD", "53", "output",       "right"),
            PinDef("PA15",        "50", "bidirectional","right"),
            PinDef("PB5",         "57", "bidirectional","right"),  # replaces PE3 (doesn't exist in LQFP-64)
            PinDef("PB12",        "33", "bidirectional","right"),
            PinDef("PA11/CAN_RX", "44", "input",        "right"),
            PinDef("PA12/CAN_TX", "45", "output",       "right"),
            PinDef("PA13/SWDIO",  "46", "bidirectional","right"),
            PinDef("PA14/SWCLK",  "49", "input",        "right"),
        ],
    
    kicad_ref="MCU_ST_STM32F4:STM32F405RGTx",),

    # --- Sensors ---
    # Convention: LEFT = inputs from MCU (bus pins, power, control)
    #             RIGHT = outputs to system (INT, GPIO, multiplexed channels)
    "ADS8681": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:TSSOP-16_4.4x5mm_P0.65mm",
        description="TI ADS8681 16-Bit 1MSPS SPI ADC",
        # TSSOP-16 pinout (TI ADS868x datasheet SBAS477C, Table 1):
        # 1=ALARM/SDO-1, 2=SDO-0, 3=CONVST/CS, 4=SDI, 5=RST,
        # 6=DGND, 7=AVDD, 8=SCLK, 9=AGND, 10=REFIO, 11=REFGND,
        # 12=REFCAP, 13=DVDD, 14=INM, 15=INP, 16=RVS
        pins=[
            PinDef("ALARM",    "1",  "output",       "right"),  # overrange alarm / secondary SDO
            PinDef("SDO/MISO", "2",  "output",       "right"),
            PinDef("CONVST/CS","3",  "input",        "left"),   # chip-select & conversion start
            PinDef("SDI/MOSI", "4",  "input",        "left"),
            PinDef("RST",      "5",  "input",        "left"),
            PinDef("DGND",     "6",  "power_in",     "left"),
            PinDef("AVDD",     "7",  "power_in",     "left"),
            PinDef("SCLK",     "8",  "input",        "left"),
            PinDef("AGND",     "9",  "power_in",     "left"),
            PinDef("REFIO",    "10", "passive",      "right"),  # external reference I/O
            PinDef("REFGND",   "11", "power_in",     "left"),
            PinDef("REFCAP",   "12", "passive",      "right"),  # internal reference bypass cap
            PinDef("DVDD",     "13", "power_in",     "left"),
            PinDef("INM",      "14", "input",        "right"),
            PinDef("INP",      "15", "input",        "right"),
            PinDef("RVS",      "16", "passive",      "right"),  # range/voltage-select
        ],
    ),
    "BME280": SymbolDef(
        ref_prefix="U",
        footprint="Package_LGA:Bosch_LGA-8_2.5x2.5mm_P0.65mm_ClockwisePinNumbering",
        description="Bosch BME280 Temp/Humidity/Pressure",
        # Physical pad numbers per Bosch BME280 datasheet + Bosch_LGA-8 KiCad footprint:
        # Top row L→R: pad1=SDO, pad2=VDD, pad3=GND, pad4=GND
        # Bottom row R→L: pad5=SDI/SDA, pad6=CSB, pad7=SCK/SCL, pad8=SAO
        pins=[
            PinDef("SDO/SA0", "1", "input",        "left"),  # I2C addr sel: tie to GND (0x76) or VDD (0x77)
            PinDef("VDD",     "2", "power_in",     "left"),
            PinDef("GND",     "3", "power_in",     "left"),
            PinDef("GND2",    "4", "power_in",     "left"),  # second GND pad, must be connected
            PinDef("SDI/SDA", "5", "bidirectional","right"),
            PinDef("CSB",     "6", "input",        "right"), # tie to VDD for I2C mode
            PinDef("SCK/SCL", "7", "input",        "right"),
            PinDef("VDDIO",   "8", "power_in",     "left"),  # interface supply voltage (Bosch BME280 DS, Table 2)
        ],
    
    kicad_ref="Sensor:BME280",),
    "BMP280": SymbolDef(
        ref_prefix="U",
        footprint="Package_LGA:Bosch_LGA-8_2x2.5mm_P0.65mm_ClockwisePinNumbering",
        description="Bosch BMP280 Pressure/Temperature Sensor",
        pins=[
            PinDef("SDO/SA0", "1", "input",        "left"),
            PinDef("VDD",     "2", "power_in",     "left"),
            PinDef("GND",     "3", "power_in",     "left"),
            PinDef("GND2",    "4", "power_in",     "left"),
            PinDef("SDI/SDA", "5", "bidirectional","right"),
            PinDef("CSB",     "6", "input",        "right"),
            PinDef("SCK/SCL", "7", "input",        "right"),
            PinDef("VDDIO",   "8", "power_in",     "left"),  # interface supply voltage (Bosch BMP280 DS)
        ],
    
    kicad_ref="Sensor_Pressure:BMP280",),
    "AHT20": SymbolDef(
        ref_prefix="U",
        footprint="Package_DFN_QFN:DFN-6-1EP_3x3mm_P1mm_EP1.5x2.4mm",
        description="ASAIR AHT20 Temperature+Humidity",
        # DFN-6 pinout (ASAIR AHT20 datasheet): 1=SDA, 2=GND, 3=NC, 4=NC, 5=VDD, 6=SCL
        pins=[
            PinDef("SDA", "1", "bidirectional", "left"),
            PinDef("GND", "2", "power_in",      "left"),
            PinDef("NC1", "3", "no_connect",    "left"),
            PinDef("NC2", "4", "no_connect",    "left"),
            PinDef("VDD", "5", "power_in",      "left"),
            PinDef("SCL", "6", "input",         "left"),
        ],
    ),
    "SHTC3": SymbolDef(
        ref_prefix="U",
        footprint="Sensor_Humidity:Sensirion_DFN-4-1EP_2x2mm_P1mm_EP0.7x1.6mm",
        description="Sensirion SHTC3 Temp/Humidity",
        # DFN-4 pinout (Sensirion SHTC3 datasheet, Table 1):
        # 1=SDA, 2=VDD, 3=GND, 4=SCL   (EP=GND thermal pad, same net as pin 3)
        pins=[
            PinDef("SDA", "1", "bidirectional","left"),
            PinDef("VDD", "2", "power_in",     "left"),
            PinDef("GND", "3", "power_in",     "left"),
            PinDef("SCL", "4", "input",        "left"),
        ],
    
    kicad_ref="Sensor_Humidity:SHTC3",),
    # ADS1115 — TI 16-bit 4-channel ADC with I2C (MSOP-10)
    "ADS1115": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:MSOP-10_3x3mm_P0.5mm",
        description="TI ADS1115 16-bit 4-ch I2C ADC",
        # MSOP-10 pinout per TI ADS1115 datasheet SBAS444E:
        # 1=ADDR, 2=ALERT/RDY, 3=GND, 4=AIN0, 5=AIN1, 6=AIN2, 7=AIN3, 8=VDD, 9=SDA, 10=SCL
        pins=[
            PinDef("ADDR",      "1", "input",         "left"),
            PinDef("ALERT/RDY", "2", "output",        "right"),
            PinDef("GND",       "3", "power_in",      "left"),
            PinDef("AIN0",      "4", "input",         "left"),
            PinDef("AIN1",      "5", "input",         "left"),
            PinDef("AIN2",      "6", "input",         "left"),
            PinDef("AIN3",      "7", "input",         "left"),
            PinDef("VDD",       "8", "power_in",      "left"),
            PinDef("SDA",       "9", "bidirectional", "left"),
            PinDef("SCL",       "10","input",         "left"),
        ],
    ),
    "INA226": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        description="TI INA226 Power Monitor",
        # SOIC-8 pinout (TI INA226 datasheet SBOS547):
        # 1=IN+, 2=IN-, 3=ALERT, 4=GND, 5=SDA, 6=SCL, 7=A0, 8=VS
        # Note: SOIC-8 has only A0 (not A1); VSSOP-10 has both A0 and A1
        pins=[
            PinDef("IN+",   "1", "input",         "left"),
            PinDef("IN-",   "2", "input",         "left"),
            PinDef("ALERT", "3", "output",        "right"),
            PinDef("GND",   "4", "power_in",      "left"),
            PinDef("SDA",   "5", "bidirectional", "left"),
            PinDef("SCL",   "6", "input",         "left"),
            PinDef("A0",    "7", "input",         "left"),
            PinDef("VS",    "8", "power_in",      "left"),
        ],
    # Note: KiCad INA226 is VSSOP-10; our entry uses SOIC-8 (different package) — no kicad_ref
    ),
    "MPU-6050": SymbolDef(
        ref_prefix="U",
        footprint="Sensor_Motion:InvenSense_QFN-24_4x4mm_P0.5mm",
        description="InvenSense MPU-6050 6-axis IMU",
        # QFN-24 pinout per InvenSense MPU-6000/6050 Product Specification:
        # VDD=13, GND=18, SDA=24, SCL=23, AD0=9, INT=12, EP=GND (pad 25)
        pins=[
            PinDef("AD0", "9",  "input",        "left"),
            PinDef("INT", "12", "output",       "right"),
            PinDef("VDD", "13", "power_in",     "left"),
            PinDef("GND", "18", "power_in",     "left"),
            PinDef("SCL", "23", "input",        "left"),
            PinDef("SDA", "24", "bidirectional","left"),
        ],
    
    kicad_ref="Sensor_Motion:MPU-6050",),
    "ICM-42688-P": SymbolDef(
        ref_prefix="U",
        footprint="Package_LGA:LGA-14_3x2.5mm_P0.5mm_LayoutBorder3x4y",
        description="TDK ICM-42688-P 6-axis IMU",
        # LGA-14 pinout per TDK DS-000347 v1.7:
        # AP_SDO/AD0=1, INT1=4, GND=9, VDD=10, VDDIO=11, AP_CS=12, AP_SCL=13, AP_SDA=14
        pins=[
            PinDef("SDO/AD0", "1",  "output",       "right"),
            PinDef("INT1",    "4",  "output",       "right"),
            PinDef("GND",     "9",  "power_in",     "left"),
            PinDef("VDD",     "10", "power_in",     "left"),
            PinDef("VDDIO",   "11", "power_in",     "left"),
            PinDef("CS",      "12", "input",        "left"),
            PinDef("SCL/SCLK","13", "input",        "left"),
            PinDef("SDA/SDI", "14", "bidirectional","left"),
        ],
    ),
    "VL53L0X": SymbolDef(
        ref_prefix="U",
        footprint="Sensor_Distance:ST_VL53L1x",
        description="ST VL53L0X ToF Distance Sensor",
        # LCC-12 pinout (ST VL53L0X datasheet DS11555 Rev 6, Figure 6):
        # 1=AVDD, 2=AVDDVCSEL, 3=GND, 4=XSHUT, 5=GPIO1,
        # 6=DNC, 7=DNC, 8=DNC, 9=SCL, 10=SDA, 11=GNDD, 12=AVSS
        # Pads 6/7/8 are DNC (do not connect — internal laser driver)
        pins=[
            PinDef("AVDD",     "1",  "power_in",     "left"),
            PinDef("AVDDVCSEL","2",  "power_in",     "left"),   # VCSEL supply (connect to AVDD)
            PinDef("GND",      "3",  "power_in",     "left"),
            PinDef("XSHUT",    "4",  "input",        "left"),   # active-low shutdown
            PinDef("GPIO1",    "5",  "output",       "right"),  # interrupt / data ready
            PinDef("SCL",      "9",  "input",        "left"),
            PinDef("SDA",      "10", "bidirectional","left"),
            PinDef("GNDD",     "11", "power_in",     "left"),
            PinDef("AVSS",     "12", "power_in",     "left"),
        ],
    ),
    "SSD1306": SymbolDef(
        ref_prefix="U",
        footprint="Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.1x3.1mm",
        description="Solomon SSD1306 OLED Controller",
        # NOTE: SSD1306 is only available as a bare die (COG, SSD1306TR1 = 207-pad wire-bond).
        # It does NOT exist as a discrete QFN-32 IC. This symbol uses the die pad numbers
        # from the SSD1306 application note / COG specification (Solomon Systech SSD1306 Rev 1.1):
        # VDD=21(logic supply), VSS=30(logic GND), VCC=2(panel supply 7-15V),
        # D1(SDA/MOSI)=11, D0(SCL/SCLK)=12, RES#=16, D/C#=15, CS#=17, BS1=20, BS2=19
        # BS1=0,BS2=0 → I2C; BS1=1,BS2=0 → SPI (4-wire); BS1=0,BS2=1 → SPI (3-wire)
        pins=[
            PinDef("VDD",   "21", "power_in",     "left"),   # logic supply (1.65-3.3V)
            PinDef("VSS",   "30", "power_in",     "left"),   # logic GND
            PinDef("VCC",   "2",  "power_in",     "left"),   # panel supply (7-15V); use 12V typ.
            PinDef("SDA/D1","11", "bidirectional","left"),
            PinDef("SCL/D0","12", "input",        "left"),
            PinDef("RES",   "16", "input",        "left"),
            PinDef("D/C",   "15", "input",        "left"),
            PinDef("CS",    "17", "input",        "left"),
            PinDef("BS1",   "20", "input",        "left"),   # interface select bit 1
            PinDef("BS2",   "19", "input",        "left"),   # interface select bit 2
        ],
    ),

    "ST7735S": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:SOP-20_7.5x12.8mm_P1.27mm",
        description="Sitronix ST7735S 1.8\" TFT LCD Controller (SPI)",
        pins=[
            PinDef("VDD",   "1", "power_in",     "left"),
            PinDef("GND",   "2", "power_in",     "left"),
            PinDef("SDA/MOSI","3","input",        "left"),
            PinDef("SDO/MISO","4","output",       "left"),
            PinDef("SCL/SCLK","5","input",        "left"),
            PinDef("CS",    "6", "input",         "left"),
            PinDef("D/C",   "7", "input",         "left"),
            PinDef("RES",   "8", "input",         "left"),
            PinDef("BLK",   "9", "input",         "left"),
        ],
    ),
    "W25Q128JV": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        description="Winbond W25Q128JV 128Mbit SPI NOR Flash",
        # SOIC-8 pinout per W25Q128JV datasheet:
        # 1=CS, 2=DO(MISO), 3=WP, 4=GND, 5=DI(MOSI), 6=CLK, 7=HOLD, 8=VCC
        pins=[
            PinDef("CS",       "1", "input",    "left"),
            PinDef("DO/MISO",  "2", "output",   "right"),
            PinDef("WP",       "3", "input",    "left"),
            PinDef("GND",      "4", "power_in", "left"),
            PinDef("DI/MOSI",  "5", "input",    "left"),
            PinDef("CLK/SCLK", "6", "input",    "left"),
            PinDef("HOLD",     "7", "input",    "left"),
            PinDef("VCC",      "8", "power_in", "left"),
        ],
    ),

    # --- LoRa / RF ---
    "SX1276": SymbolDef(
        ref_prefix="U",
        footprint="Package_DFN_QFN:QFN-28-1EP_6x6mm_P0.65mm_EP4.8x4.8mm",
        description="Semtech SX1276 LoRa/FSK Transceiver",
        # Physical pad numbers from KiCad official RF.kicad_symdir/SX1276.kicad_sym (master, 2026).
        # QFN-28-1EP, 6x6mm, 0.65mm pitch. Exposed thermal pad = pad 29 = GND.
        # Power architecture: VBAT_xxx pads (3/14/24) are 3.3V supply inputs → all connect to VDD.
        #   VR_ANA(2), VR_DIG(4), VR_PA(25) are internal LDO *outputs* — add bypass caps only.
        # GND at pads 15, 23, 26 and EP=29 (all same net).
        # RF: RFI_LF=1, RFO_LF=28, RFI_HF=21, RFO_HF=22. Crystal: XTA=5, XTB=6.
        # SPI bus: SCK=16, MISO=17, MOSI=18, NSS=19. DIO0-5: pads 8-13.
        # PA_BOOST(27): RF output node for boost PA path — not a power supply.
        pins=[
            PinDef("VDD_ANA",     "3",  "power_in",     "left"),    # VBAT_ANA — analog section 3.3V supply
            PinDef("VDD_DIG",     "14", "power_in",     "left"),    # VBAT_DIG — digital section 3.3V supply
            PinDef("VDD_RF",      "24", "power_in",     "left"),    # VBAT_RF  — RF section 3.3V supply
            PinDef("GND",         "15", "power_in",     "left"),    # pads 15/23/26/29(EP) all GND
            PinDef("VR_ANA",      "2",  "passive",      "left"),    # internal analog LDO output — bypass cap only
            PinDef("VR_DIG",      "4",  "passive",      "left"),    # internal digital LDO output — bypass cap only
            PinDef("~{RESET}",    "7",  "input",        "left"),
            PinDef("XTA",         "5",  "passive",      "left"),    # crystal / TCXO
            PinDef("XTB",         "6",  "passive",      "left"),
            PinDef("SCK",         "16", "input",        "left"),
            PinDef("MOSI",        "18", "input",        "left"),
            PinDef("MISO",        "17", "output",       "right"),
            PinDef("NSS",         "19", "input",        "left"),
            PinDef("DIO0",        "8",  "bidirectional","right"),
            PinDef("DIO1",        "9",  "bidirectional","right"),
            PinDef("DIO2",        "10", "bidirectional","right"),
            PinDef("DIO3",        "11", "bidirectional","right"),
            PinDef("DIO4",        "12", "bidirectional","right"),
            PinDef("DIO5",        "13", "bidirectional","right"),
            PinDef("RXTX/RF_MOD","20",  "output",       "right"),   # antenna switch control
            PinDef("RFI_LF",      "1",  "input",        "right"),   # LF path RF input
            PinDef("RFO_LF",      "28", "output",       "right"),   # LF path RF output
            PinDef("RFI_HF",      "21", "input",        "right"),   # HF path RF input
            PinDef("RFO_HF",      "22", "output",       "right"),   # HF path RF output
            PinDef("PA_BOOST",    "27", "output",       "right"),   # boost PA RF output node
        ],
    
    kicad_ref="RF:SX1276",),

    # --- GNSS / GPS ---
    "NEO-M8N": SymbolDef(
        ref_prefix="U",
        footprint="RF_GPS:ublox_NEO",
        description="u-blox NEO-M8N GNSS Receiver Module",
        pins=[
            PinDef("VCC",      "1", "power_in",     "left"),
            PinDef("GND",      "2", "power_in",     "left"),
            PinDef("TX",       "3", "output",        "right"),
            PinDef("RX",       "4", "input",         "right"),
            PinDef("SDA",      "5", "bidirectional", "right"),
            PinDef("SCL",      "6", "input",         "right"),
            PinDef("TIMEPULSE","7", "output",        "right"),
            PinDef("RESET_N",  "8", "input",         "left"),
        ],
    
    kicad_ref="RF_GPS:NEO-M8N",),

    # --- Memory ---
    "MICROSD-SLOT-SPI": SymbolDef(
        ref_prefix="J",
        footprint="Connector_Card:microSD_HC_Molex_104031-0811",
        description="MicroSD Card Slot (SPI mode)",
        pins=[
            PinDef("VDD",  "1", "power_in",  "left"),
            PinDef("GND",  "2", "power_in",  "left"),
            PinDef("MOSI", "3", "input",     "left"),
            PinDef("MISO", "4", "output",    "right"),
            PinDef("SCLK", "5", "input",     "left"),
            PinDef("CS",   "6", "input",     "left"),
        ],
    ),

    # --- Connectors ---
    "USB-C-CONN": SymbolDef(
        ref_prefix="J",
        footprint="Connector_USB:USB_C_Receptacle_GCT_USB4085",
        description="USB-C Receptacle Connector",
        # GCT USB4085 pad names: A1/A12/B1/B12=GND, A4/A9=VBUS, A5=CC1, A6=D-, A7=D+, B5=CC2, B6=D-, B7=D+, S1=Shield
        pins=[
            PinDef("VBUS", "A4", "power_in",     "left"),
            PinDef("GND",  "A1", "power_in",     "left"),
            PinDef("D+",   "A7", "bidirectional","right"),
            PinDef("D-",   "A6", "bidirectional","right"),
            PinDef("CC1",  "A5", "passive",      "right"),
            PinDef("CC2",  "B5", "passive",      "right"),
        ],
    ),

    # --- Logic / Level Shifters ---
    "TXB0104": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
        description="TI TXB0104 4-bit Bidirectional Voltage-Level Shifter",
        # TSSOP-14 pinout (TI SCDS239 datasheet):
        # 1=VCCA, 2=A1, 3=A2, 4=A3, 5=A4, 6=NC, 7=GND,
        # 8=OE,   9=NC, 10=B4,11=B3,12=B2,13=B1, 14=VCCB
        # Note: B channels are in REVERSE order on the package (B4 at top, B1 at bottom)
        pins=[
            PinDef("VCCA", "1",  "power_in",     "left"),
            PinDef("A1",   "2",  "bidirectional","left"),
            PinDef("A2",   "3",  "bidirectional","left"),
            PinDef("A3",   "4",  "bidirectional","left"),
            PinDef("A4",   "5",  "bidirectional","left"),
            PinDef("NC1",  "6",  "no_connect",   "left"),
            PinDef("GND",  "7",  "power_in",     "left"),
            PinDef("OE",   "8",  "input",        "left"),
            PinDef("NC2",  "9",  "no_connect",   "right"),
            PinDef("B4",   "10", "bidirectional","right"),
            PinDef("B3",   "11", "bidirectional","right"),
            PinDef("B2",   "12", "bidirectional","right"),
            PinDef("B1",   "13", "bidirectional","right"),
            PinDef("VCCB", "14", "power_in",     "right"),
        ],
    ),

    # --- Comms / Mux ---
    "TCA9548A": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm",
        description="TI TCA9548A 8-channel I2C Multiplexer",
        # TSSOP-24 pinout (TI SCPS209G datasheet, Table 1):
        # 1=A0, 2=A1, 3=RESET, 4=SD0, 5=SC0, 6=SD1, 7=SC1, 8=SD2, 9=SC2,
        # 10=SD3,11=SC3,12=GND, 13=SD4,14=SC4,15=SD5,16=SC5,17=SD6,18=SC6,
        # 19=SD7,20=SC7, 21=A2, 22=SCL, 23=SDA, 24=VCC
        pins=[
            PinDef("A0",    "1",  "input",        "left"),
            PinDef("A1",    "2",  "input",        "left"),
            PinDef("RESET", "3",  "input",        "left"),
            PinDef("SD0",   "4",  "bidirectional","right"),
            PinDef("SC0",   "5",  "bidirectional","right"),
            PinDef("SD1",   "6",  "bidirectional","right"),
            PinDef("SC1",   "7",  "bidirectional","right"),
            PinDef("SD2",   "8",  "bidirectional","right"),
            PinDef("SC2",   "9",  "bidirectional","right"),
            PinDef("SD3",   "10", "bidirectional","right"),
            PinDef("SC3",   "11", "bidirectional","right"),
            PinDef("GND",   "12", "power_in",     "left"),
            PinDef("SD4",   "13", "bidirectional","right"),
            PinDef("SC4",   "14", "bidirectional","right"),
            PinDef("SD5",   "15", "bidirectional","right"),
            PinDef("SC5",   "16", "bidirectional","right"),
            PinDef("SD6",   "17", "bidirectional","right"),
            PinDef("SC6",   "18", "bidirectional","right"),
            PinDef("SD7",   "19", "bidirectional","right"),
            PinDef("SC7",   "20", "bidirectional","right"),
            PinDef("A2",    "21", "input",        "left"),
            PinDef("SCL",   "22", "input",        "left"),
            PinDef("SDA",   "23", "bidirectional","left"),
            PinDef("VCC",   "24", "power_in",     "left"),
        ],
    ),

    # --- Power (LDOs) ---
    "AMS1117-3.3": SymbolDef(
        ref_prefix="U",
        footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        description="AMS1117 3.3V 1A LDO Regulator",
        # SOT-223 pinout (AMS1117 datasheet): 1=GND/ADJ, 2=OUTPUT, 3=INPUT
        # SOT-223-3_TabPin2: tab IS pad 2 (same pad number) — no separate tab pin needed
        pins=[
            PinDef("GND",  "1", "power_in",  "left"),   # ADJ on fixed → GND reference
            PinDef("VOUT", "2", "power_out", "right"),  # OUTPUT (pad 2 = also tab in SOT-223-3_TabPin2)
            PinDef("VIN",  "3", "power_in",  "left"),   # INPUT
        ],
    
    kicad_ref="Regulator_Linear:AMS1117-3.3",),
    "AP2112K-3.3": SymbolDef(
        ref_prefix="U",
        footprint="Package_TO_SOT_SMD:SOT-23-5_HandSoldering",
        description="AP2112K 3.3V 600mA LDO Regulator",
        # SOT-23-5 (SOT-25) pinout (Diodes Inc AP2112K datasheet): 1=EN, 2=GND, 3=IN, 4=NC, 5=OUT
        pins=[
            PinDef("EN",   "1", "input",     "left"),
            PinDef("GND",  "2", "power_in",  "left"),
            PinDef("VIN",  "3", "power_in",  "left"),
            PinDef("NC",   "4", "no_connect","left"),
            PinDef("VOUT", "5", "power_out", "right"),
        ],
    
    kicad_ref="Regulator_Linear:AP2112K-3.3",),
    # AP2112K-3.3TRG1: Tape-and-reel variant — same electrical symbol as AP2112K-3.3.
    # VIN maps to "+5V" net (VIN in _VIN_KEYWORDS), so in a cascade it connects to the
    # 5V intermediate rail from AMS1117-5.0.  VOUT maps to "+3V3" (VOUT in _3V3_KEYWORDS).
    "AP2112K-3.3TRG1": SymbolDef(
        ref_prefix="U",
        footprint="Package_TO_SOT_SMD:SOT-23-5_HandSoldering",
        description="AP2112K 3.3V 600mA LDO Regulator (Tape & Reel)",
        # SOT-23-5 (SOT-25) pinout: 1=EN, 2=GND, 3=IN, 4=NC, 5=OUT
        pins=[
            PinDef("EN",   "1", "input",     "left"),
            PinDef("GND",  "2", "power_in",  "left"),
            PinDef("VIN",  "3", "power_in",  "left"),
            PinDef("NC",   "4", "no_connect","left"),
            PinDef("VOUT", "5", "power_out", "right"),
        ],
    
    kicad_ref="Regulator_Linear:AP2112K-3.3",),
    "MCP1700-3302E": SymbolDef(
        ref_prefix="U",
        footprint="Package_TO_SOT_SMD:SOT-23-3",
        description="MCP1700 250mA Ultra-Low Quiescent LDO (1.6µA Iq) — battery IoT",
        pins=[
            PinDef("VIN",  "1", "power_in", "left"),
            PinDef("VSS",  "2", "power_in", "left"),
            PinDef("VOUT", "3", "power_out","right"),
        ],
    ),
    # AMS1117-5.0: 5V 800mA LDO — used as intermediate 12V→5V stage.
    # Pin "VIN12V" maps to "+12V" net (12V in "_12V_KEYWORDS").
    # Pin "VOUT5V" maps to "+5V" net ("5V" in "_VIN_KEYWORDS" substring).
    # VOUT5V uses power_in type (not power_out) to avoid KiCad 9 ERC
    # "power_out + power_out" when a second LDO (AP2112K) also has power_out VOUT.
    # KiCad treats (power) global symbols as implicit drivers, so the +5V net
    # is "driven" by the "(power)" +5V symbol — no "power pin not driven" error.
    "AMS1117-5.0": SymbolDef(
        ref_prefix="U",
        footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        description="AMS1117 5.0V 800mA LDO Regulator (12V→5V intermediate rail)",
        # SOT-223 pinout: 1=GND/ADJ, 2=OUTPUT, 3=INPUT, tab=OUTPUT
        # VOUT5V uses power_in (not power_out) to avoid KiCad 9 ERC "power_out+power_out" when cascaded
        # SOT-223-3_TabPin2: tab IS pad 2 (same pad number) — no separate tab pin needed
        pins=[
            PinDef("GND",    "1", "power_in", "left"),   # ADJ → GND reference
            PinDef("VOUT5V", "2", "power_in", "right"),  # 5V output → "+5V" net; power_in avoids ERC conflict (pad 2 = also tab)
            PinDef("VIN12V", "3", "power_in", "left"),   # 12V input → "+12V" net
        ],
    
    kicad_ref="Regulator_Linear:AMS1117-5.0",),
    # LM2940CT-3.3: 1A, 26V max-input LDO — suited for 24V industrial supplies.
    # TO-220 package, low dropout (~0.5V at 1A), reverse-battery protection.
    "LM2940CT-3.3": SymbolDef(
        ref_prefix="U",
        footprint="Package_TO_SOT_THT:TO-220-3_Vertical",
        description="LM2940CT 3.3V 1A LDO Regulator (26V max input, 24V industrial)",
        # TO-220 pinout (LM2940C datasheet, TI): 1=OUTPUT, 2=INPUT, 3=GND
        pins=[
            PinDef("VOUT", "1", "power_out", "right"),  # OUTPUT
            PinDef("VIN",  "2", "power_in",  "left"),   # INPUT
            PinDef("GND",  "3", "power_in",  "left"),   # GROUND
        ],
    ),
    "MP2307DN": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        description="MP2307 3A 23V Step-Down Buck Converter",
        # SOIC-8 pinout per MPS MP2307 datasheet:
        # 1=BS(BST), 2=IN(VIN), 3=SW, 4=GND, 5=FB, 6=COMP, 7=EN, 8=SS
        pins=[
            PinDef("BST",   "1", "passive",  "right"),
            PinDef("VIN",   "2", "power_in", "left"),
            PinDef("SW",    "3", "output",   "right"),
            PinDef("GND",   "4", "power_in", "left"),
            PinDef("FB",    "5", "input",    "right"),
            PinDef("COMP",  "6", "passive",  "right"),
            PinDef("EN",    "7", "input",    "left"),
            PinDef("SS",    "8", "passive",  "left"),
        ],
    ),
    "TP4056": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        description="TP4056 1A Standalone Linear Li-Ion Battery Charger",
        pins=[
            PinDef("TEMP",  "1", "input",    "left"),
            PinDef("PROG",  "2", "passive",  "left"),
            PinDef("GND",   "3", "power_in", "left"),
            PinDef("VCC",   "4", "power_in", "left"),
            PinDef("BAT",   "5", "power_out","right"),
            PinDef("STDBY", "6", "output",   "right"),  # per Nanjing Top Power TP4056 DS Rev2.4
            PinDef("CHRG",  "7", "output",   "right"),
            PinDef("CE",    "8", "input",    "left"),
        ],
    ),
    "MCP73831T-2ATI": SymbolDef(
        ref_prefix="U",
        footprint="Package_TO_SOT_SMD:SOT-23-5_HandSoldering",
        description="MCP73831 500mA Single-Cell Li-Ion/Li-Poly Charge Management Controller",
        # SOT-23-5 pinout (Microchip MCP73831 datasheet): 1=STAT, 2=VDD, 3=VSS, 4=PROG, 5=VBAT
        pins=[
            PinDef("STAT", "1", "output",    "right"),
            PinDef("VDD",  "2", "power_in",  "left"),
            PinDef("VSS",  "3", "power_in",  "left"),
            PinDef("PROG", "4", "passive",   "left"),
            PinDef("VBAT", "5", "power_out", "right"),
        ],
    ),
    "MAX17048G+T": SymbolDef(
        ref_prefix="U",
        footprint="Package_DFN_QFN:DFN-8-1EP_2x2mm_P0.5mm_EP0.8x1.6mm",
        description="MAX17048 1-Cell/2-Cell Fuel Gauge with ModelGauge (I2C, 0x36)",
        # TDFN-8 2x2mm pinout per Analog Devices MAX17048 datasheet:
        # 1=GND, 2=CELL, 3=VDD, 4=GND, 5=ALRT, 6=QSTRT, 7=SCL, 8=SDA, EP=GND
        pins=[
            PinDef("GND",   "1", "power_in",     "left"),
            PinDef("CELL",  "2", "input",         "right"),
            PinDef("VDD",   "3", "power_in",     "left"),
            PinDef("GND2",  "4", "power_in",     "left"),
            PinDef("ALRT",  "5", "output",       "right"),
            PinDef("QSTRT", "6", "input",         "left"),
            PinDef("SCL",   "7", "input",         "left"),
            PinDef("SDA",   "8", "bidirectional", "left"),
        ],
    ),

    # --- Sensors ---
    "HC-SR04": SymbolDef(
        ref_prefix="U",
        footprint="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
        description="HC-SR04 Ultrasonic Distance Sensor Module (through-hole, 4-pin)",
        pins=[
            PinDef("VCC",   "1", "power_in",     "left"),
            PinDef("TRIG",  "2", "input",         "right"),
            PinDef("ECHO",  "3", "output",        "right"),
            PinDef("GND",   "4", "power_in",      "left"),
        ],
    ),

    # --- Discrete semiconductors ---
    "IRLZ44N": SymbolDef(
        ref_prefix="Q",
        footprint="Package_TO_SOT_THT:TO-220-3_Vertical",
        description="IRLZ44N N-Channel Logic-Level MOSFET 55V 47A TO-220",
        pins=[
            PinDef("G",  "1", "input",    "left"),
            PinDef("D",  "2", "passive",  "right"),
            PinDef("S",  "3", "passive",  "left"),
        ],
    ),
    "1N4007": SymbolDef(
        ref_prefix="D",
        footprint="Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal",
        description="1N4007 1A 1000V Rectifier / Flyback Diode DO-41",
        pins=[
            PinDef("A",  "1", "passive", "left"),
            PinDef("K",  "2", "passive", "right"),
        ],
    ),

    # --- Transceivers ---
    "SN65HVD230": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        description="SN65HVD230 CAN Bus Transceiver 3.3V SOIC-8",
        # SOIC-8 pinout per TI SN65HVD23x datasheet (SLOS346G):
        # 1=D(TXD), 2=GND, 3=VCC, 4=R(RXD), 5=Vref, 6=CANH, 7=CANL, 8=RS
        pins=[
            PinDef("TXD",  "1", "input",         "left"),
            PinDef("GND",  "2", "power_in",       "left"),
            PinDef("VCC",  "3", "power_in",       "left"),
            PinDef("RXD",  "4", "output",         "right"),
            PinDef("Vref", "5", "output",         "right"),
            PinDef("CANH", "6", "bidirectional",  "right"),
            PinDef("CANL", "7", "bidirectional",  "right"),
            PinDef("RS",   "8", "input",          "left"),
        ],
    
    kicad_ref="Interface_CAN_LIN:SN65HVD230",),
    "MAX485": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        description="MAX485 Low-Power RS-485/RS-422 Transceiver SOIC-8",
        pins=[
            PinDef("RO",   "1", "output",         "right"),
            PinDef("~RE",  "2", "input",          "left"),
            PinDef("DE",   "3", "input",          "left"),
            PinDef("DI",   "4", "input",          "left"),
            PinDef("GND",  "5", "power_in",       "left"),
            PinDef("A",    "6", "bidirectional",  "right"),
            PinDef("B",    "7", "bidirectional",  "right"),
            PinDef("VCC",  "8", "power_in",       "left"),
        ],
    ),

    # --- Communication modules ---
    "LAN8720A": SymbolDef(
        ref_prefix="U",
        footprint="Package_DFN_QFN:VQFN-24-1EP_4x4mm_P0.5mm_EP2.5x2.5mm_ThermalVias",
        description="Microchip LAN8720A 10/100 Ethernet PHY",
        # VQFN-24 pinout per Microchip DS00002165B + KiCad Interface_Ethernet:LAN8720A:
        # VDDIO=9, VDD1A=19, GND=EP(25), TXD0=17, TXD1=18, TXEN=16
        # RXD0=8, RXD1=7, RXER=10, CRS_DV=11, MDIO=12, MDC=13, nINT/REFCLK=14, nRST=15
        pins=[
            PinDef("VDDIO",   "9",  "power_in",     "left"),
            PinDef("VDD1A",   "19", "power_in",     "left"),
            PinDef("GND",     "25", "power_in",     "left"),   # exposed pad
            PinDef("TXEN",    "16", "output",       "right"),
            PinDef("TXD0",    "17", "output",       "right"),
            PinDef("TXD1",    "18", "output",       "right"),
            PinDef("RXD0",    "8",  "input",        "right"),
            PinDef("RXD1",    "7",  "input",        "right"),
            PinDef("RXER",    "10", "input",        "right"),
            PinDef("CRS_DV",  "11", "input",        "right"),
            PinDef("MDIO",    "12", "bidirectional","left"),
            PinDef("MDC",     "13", "input",        "left"),
            PinDef("REFCLK",  "14", "input",        "left"),
            PinDef("NRST",    "15", "input",        "left"),
        ],
    
    kicad_ref="Interface_Ethernet:LAN8720A",),
    "SIM7600G-H": SymbolDef(
        ref_prefix="U",
        footprint="Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical",
        description="SIMCom SIM7600G LTE Cat-4 Module (UART)",
        pins=[
            PinDef("VCC",    "1",  "power_in",  "left"),
            PinDef("GND",    "2",  "power_in",  "left"),
            PinDef("TXD",    "3",  "output",    "right"),
            PinDef("RXD",    "4",  "input",     "right"),
            PinDef("PWRKEY", "5",  "input",     "left"),
            PinDef("RESET",  "6",  "input",     "left"),
            PinDef("STATUS", "7",  "output",    "right"),
            PinDef("RI",     "8",  "output",    "right"),
        ],
    ),
    "MAX98357A": SymbolDef(
        ref_prefix="U",
        footprint="Package_DFN_QFN:TQFN-16-1EP_3x3mm_P0.5mm_EP1.23x1.23mm",
        description="Maxim MAX98357A I2S Class-D Audio Amplifier",
        # TQFN-16 pinout per MAX98357A datasheet (Maxim, Rev 4):
        # 1=DIN, 2=GAIN_SLOT, 3=GND, 4=/SD_MODE, 5-6=GND, 7=VDD
        # 8=GND, 9=OUTP, 10=OUTN, 11-13=GND, 14=LRCLK, 15=GND, 16=BCLK
        # 17=EP (thermal pad = GND)
        # Source: KiCad Audio:MAX98357A symbol (verified against datasheet)
        pins=[
            PinDef("VDD",      "7",  "power_in",  "left"),
            PinDef("GND",      "3",  "power_in",  "left"),
            PinDef("BCLK",     "16", "input",     "left"),
            PinDef("LRCLK",    "14", "input",     "left"),
            PinDef("DIN",      "1",  "input",     "left"),
            PinDef("SD_MODE",  "4",  "input",     "left"),
            PinDef("GAIN_SLOT","2",  "input",     "left"),
            PinDef("OUTP",     "9",  "output",    "right"),
            PinDef("OUTN",     "10", "output",    "right"),
            PinDef("GND_EP",   "17", "power_in",  "left"),
        ],
    kicad_ref="Audio:MAX98357A",),
    "WM8731": SymbolDef(
        ref_prefix="U",
        footprint="Package_DFN_QFN:QFN-28-1EP_5x5mm_P0.5mm_EP3.35x3.35mm",
        description="Wolfson WM8731 Audio Codec I2S/I2C",
        # Physical pad numbers from KiCad Audio.kicad_symdir/WM8731CLSEFL.kicad_sym (master, 2026).
        # QFN-28-1EP, 5x5mm, 0.5mm pitch. EP = pad 29 = AGND (thermal pad).
        # Cirrus Logic/Wolfson WM8731 (also WM8731L). Two package options:
        #   WM8731CLSEFL / WM8731CSEFL = QFN-28 (this entry, 5x5mm)
        #   WM8731SEDS = SSOP-28 (different pinout — DBVDD=1, XTI/MCLK=25, etc.)
        # I2C control: SCLK=28 (clock), SDIN=27 (data), CSB=26 (I2C addr sel / SPI CS), MODE=25
        pins=[
            PinDef("XTI/MCLK",  "1",  "input",        "left"),    # master clock / crystal in
            PinDef("XTO",        "2",  "output",       "right"),   # crystal out
            PinDef("DCVDD",      "3",  "power_in",     "left"),    # digital core supply
            PinDef("DGND",       "4",  "power_in",     "left"),
            PinDef("DBVDD",      "5",  "power_in",     "left"),    # digital buffer supply
            PinDef("CLKOUT",     "6",  "output",       "right"),
            PinDef("BCLK",       "7",  "input",        "left"),    # I2S bit clock
            PinDef("DACDAT",     "8",  "input",        "left"),    # I2S DAC data in
            PinDef("DACLRC",     "9",  "input",        "left"),    # I2S DAC L/R clock
            PinDef("ADCDAT",     "10", "output",       "right"),   # I2S ADC data out
            PinDef("ADCLRC",     "11", "output",       "right"),   # I2S ADC L/R clock
            PinDef("HPVDD",      "12", "power_in",     "left"),    # headphone output supply
            PinDef("LHPOUT",     "13", "output",       "right"),   # left headphone out
            PinDef("RHPOUT",     "14", "output",       "right"),   # right headphone out
            PinDef("HPGND",      "15", "power_in",     "left"),    # headphone ground
            PinDef("LOUT",       "16", "output",       "right"),   # left line out
            PinDef("ROUT",       "17", "output",       "right"),   # right line out
            PinDef("AVDD",       "18", "power_in",     "left"),    # analog supply
            PinDef("AGND",       "19", "power_in",     "left"),
            PinDef("VMID",       "20", "passive",      "right"),   # mid-supply bypass cap
            PinDef("MICBIAS",    "21", "output",       "right"),   # microphone bias voltage
            PinDef("MICIN",      "22", "input",        "right"),   # microphone input
            PinDef("RLINEIN",    "23", "input",        "right"),   # right line in
            PinDef("LLINEIN",    "24", "input",        "right"),   # left line in
            PinDef("MODE",       "25", "input",        "left"),    # 0=I2C ctrl, 1=SPI ctrl
            PinDef("~{CSB}",     "26", "input",        "left"),    # I2C addr (0=0x1A,1=0x1B) / SPI CS
            PinDef("SDIN",       "27", "bidirectional","left"),    # control interface data
            PinDef("SCLK",       "28", "input",        "left"),    # control interface clock
        ],
    
    kicad_ref="Audio:WM8731CLSEFL",),
    "TB6612FNG": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:SSOP-24_5.3x8.2mm_P0.65mm",
        description="Toshiba TB6612FNG Dual H-Bridge Motor Driver",
        # SSOP-24 pinout per Toshiba TB6612FNG datasheet (2014-10-01):
        # AO1=1,2; PGND=3,4,9,10; AO2=5,6; BO2=7,8; BO1=11,12; VM=13,14,24
        # PWMB=15; BIN2=16; BIN1=17; GND=18; STBY=19; VCC=20; AIN1=21; AIN2=22; PWMA=23
        pins=[
            PinDef("AO1",  "1",  "output",    "right"),
            PinDef("PGND", "3",  "power_in",  "left"),
            PinDef("AO2",  "5",  "output",    "right"),
            PinDef("BO2",  "7",  "output",    "right"),
            PinDef("BO1",  "11", "output",    "right"),
            PinDef("VM",   "13", "power_in",  "left"),
            PinDef("PWMB", "15", "input",     "left"),
            PinDef("BIN2", "16", "input",     "left"),
            PinDef("BIN1", "17", "input",     "left"),
            PinDef("GND",  "18", "power_in",  "left"),
            PinDef("STBY", "19", "input",     "left"),
            PinDef("VCC",  "20", "power_in",  "left"),
            PinDef("AIN1", "21", "input",     "left"),
            PinDef("AIN2", "22", "input",     "left"),
            PinDef("PWMA", "23", "input",     "left"),
        ],
    
    kicad_ref="Driver_Motor:TB6612FNG",),
    "SIM800L": SymbolDef(
        ref_prefix="U",
        footprint="Connector_PinHeader_2.00mm:PinHeader_2x08_P2.00mm_Vertical",
        description="SIM800L GSM/GPRS Module (UART, 2x8 2mm header)",
        pins=[
            PinDef("VCC",      "1",  "power_in",  "left"),
            PinDef("GND",      "2",  "power_in",  "left"),
            PinDef("TXD",      "3",  "output",    "right"),
            PinDef("RXD",      "4",  "input",     "right"),
            PinDef("RST",      "5",  "input",     "left"),
            PinDef("PWRKEY",   "6",  "input",     "left"),
            PinDef("DTR",      "7",  "input",     "left"),
            PinDef("RING",     "8",  "output",    "right"),
            PinDef("STATUS",   "9",  "output",    "right"),
            PinDef("NETLIGHT", "10", "output",    "right"),
        ],
    ),

    # --- Solar power management ---
    "SPV1040": SymbolDef(
        ref_prefix="U",
        footprint="Package_TO_SOT_SMD:TSOT-23-6",
        description="STMicroelectronics SPV1040 MPPT Solar Boost Converter TSOT-23-6",
        # TSOT-23-6 pinout per ST SPV1040 datasheet Table 3:
        # 1=VIN, 2=GND, 3=VOUT, 4=MPPSET, 5=LX (switch node), 6=LX
        pins=[
            PinDef("VIN",    "1", "power_in",  "left"),
            PinDef("GND",    "2", "power_in",  "left"),
            PinDef("VOUT",   "3", "passive",   "right"),   # boost output node — not a direct +3V3 rail driver
            PinDef("MPPSET", "4", "input",     "left"),   # MPPT set point resistor
            PinDef("LX",     "5", "output",    "right"),  # inductor switch node
        ],
    ),
    "BQ24650": SymbolDef(
        ref_prefix="U",
        footprint="Package_DFN_QFN:VQFN-20-1EP_4x4mm_P0.65mm_EP2.5x2.5mm",
        description="TI BQ24650 Solar Battery Charger Controller VQFN-20",
        # VQFN-20 pinout per TI BQ24650 datasheet (SLUSA11C):
        # Key signals: VCC=1, GND=10,21, MPPSET=2, TS=3, STAT1=4, STAT2=5
        # ISET=6, VSET=7, SRN=8, SRP=9, PH=11, HIDRV=12, LODRV=13
        # ACDET=14, BTST=15, REGN=16, VREF=17, VREG=18, MODESEL=19, PACK=20
        pins=[
            PinDef("VCC",     "1",  "power_in",  "left"),
            PinDef("MPPSET",  "2",  "input",     "left"),   # MPPT set-point resistor
            PinDef("TS",      "3",  "input",     "left"),   # NTC thermistor input
            PinDef("STAT1",   "4",  "output",    "right"),  # charge status 1
            PinDef("STAT2",   "5",  "output",    "right"),  # charge status 2
            PinDef("ISET",    "6",  "input",     "left"),   # charge current set resistor
            PinDef("VSET",    "7",  "input",     "left"),   # charge voltage set resistor
            PinDef("SRN",     "8",  "input",     "left"),   # current sense resistor -
            PinDef("SRP",     "9",  "input",     "left"),   # current sense resistor +
            PinDef("GND",     "10", "power_in",  "left"),
            PinDef("PH",      "11", "output",    "right"),  # high-side FET source/inductor
            PinDef("HIDRV",   "12", "output",    "right"),  # high-side gate drive
            PinDef("LODRV",   "13", "output",    "right"),  # low-side gate drive
            PinDef("ACDET",   "14", "input",     "left"),   # AC/solar adapter detect
            PinDef("BTST",    "15", "passive",   "right"),  # high-side gate bootstrap
            PinDef("REGN",    "16", "power_out", "right"),  # internal LDO output
            PinDef("VREF",    "17", "passive",   "right"),  # voltage reference cap
            PinDef("VREG",    "18", "input",     "left"),   # charge voltage regulation
            PinDef("MODESEL", "19", "input",     "left"),   # chemistry select
            PinDef("PACK",    "20", "power_out", "right"),  # battery pack +
            PinDef("GND_EP",  "21", "power_in",  "left"),  # exposed pad
        ],
    ),

    # --- Connectors ---
    "CONN-CAN-2PIN": SymbolDef(
        ref_prefix="J",
        footprint="TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal",
        description="2-pin Screw Terminal for CAN bus (CANH/CANL) 5mm pitch",
        pins=[
            PinDef("CANH", "1", "passive", "right"),
            PinDef("CANL", "2", "passive", "right"),
        ],
    ),
    "CONN-RS485-2PIN": SymbolDef(
        ref_prefix="J",
        footprint="TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal",
        description="2-pin Screw Terminal for RS-485 bus (A/B) 5mm pitch",
        pins=[
            PinDef("A", "1", "passive", "right"),
            PinDef("B", "2", "passive", "right"),
        ],
    ),
    "CONN-UART-4PIN": SymbolDef(
        ref_prefix="J",
        footprint="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
        description="4-pin 2.54mm pin header for UART (VCC, GND, TX, RX)",
        pins=[
            PinDef("VCC", "1", "power_in", "left"),
            PinDef("GND", "2", "power_in", "left"),
            # TX/RX are passive on the connector side — direction depends on the
            # connected device, so marking as "output" causes pin_to_pin ERC
            # errors when the MCU's TX (Output) connects to this TX pin.
            PinDef("TX",  "3", "passive",  "right"),
            PinDef("RX",  "4", "passive",  "right"),
        ],
    ),

    # --- Passives (used for reference-designator lookup) ---
    # R / C generics are handled by _generic_symbol; entries here are for
    # specific MPNs that appear in the BOM.
    "RC0402FR-074K7L": SymbolDef(
        ref_prefix="R",
        footprint="Resistor_SMD:R_0402_1005Metric",
        description="4.7kΩ 1% 0402 Resistor (I2C pull-up)",
        pins=[
            PinDef("~", "1", "passive", "left"),
            PinDef("~", "2", "passive", "right"),
        ],
    ),
    "RC0402FR-07100RL": SymbolDef(
        ref_prefix="R",
        footprint="Resistor_SMD:R_0402_1005Metric",
        description="100Ω 1% 0402 Resistor (gate/series resistor)",
        pins=[
            PinDef("~", "1", "passive", "left"),
            PinDef("~", "2", "passive", "right"),
        ],
    ),
    "RC0402FR-07470RL": SymbolDef(
        ref_prefix="R",
        footprint="Resistor_SMD:R_0402_1005Metric",
        description="470Ω 1% 0402 Resistor (UART series protection)",
        pins=[
            PinDef("~", "1", "passive", "left"),
            PinDef("~", "2", "passive", "right"),
        ],
    ),
    "GRM155R71C104KA88D": SymbolDef(
        ref_prefix="C",
        footprint="Capacitor_SMD:C_0402_1005Metric",
        description="100nF 16V X7R 0402 Capacitor (decoupling)",
        pins=[
            PinDef("~", "1", "passive", "left"),
            PinDef("~", "2", "passive", "right"),
        ],
    ),
    "GRM188R61A106KE69D": SymbolDef(
        ref_prefix="C",
        footprint="Capacitor_SMD:C_0603_1608Metric",
        description="10µF 10V X5R 0603 Capacitor (bulk)",
        pins=[
            PinDef("~", "1", "passive", "left"),
            PinDef("~", "2", "passive", "right"),
        ],
    ),

    # --- Level Shifters (Phase 22.8) ---
    "BSS138": SymbolDef(
        ref_prefix="Q",
        footprint="Package_TO_SOT_SMD:SOT-23",
        description="BSS138 N-Channel MOSFET Level Shifter SOT-23",
        pins=[
            PinDef("G", "1", "input",   "left"),
            PinDef("S", "2", "passive", "left"),
            PinDef("D", "3", "passive", "right"),
        ],
    ),
    "TXS0102": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:VSSOP-8_3x3mm_P0.65mm",
        description="TI TXS0102 2-Bit Bidirectional Level Shifter",
        # VSSOP-8 (DCU/DCT) pinout per TI TXS0102 datasheet (SCES743):
        # 1=VCCA, 2=A1, 3=A2, 4=GND, 5=B2, 6=OE, 7=VCCB, 8=B1
        pins=[
            PinDef("VCCA", "1", "power_in",      "left"),
            PinDef("A1",   "2", "bidirectional",  "left"),
            PinDef("A2",   "3", "bidirectional",  "left"),
            PinDef("GND",  "4", "power_in",       "left"),
            PinDef("B2",   "5", "bidirectional",  "right"),
            PinDef("OE",   "6", "input",          "left"),
            PinDef("VCCB", "7", "power_in",       "right"),
            PinDef("B1",   "8", "bidirectional",  "right"),
        ],
    ),

    # --- Buck Converters (Phase 22.8) ---
    "TPS563200": SymbolDef(
        ref_prefix="U",
        footprint="Package_TO_SOT_SMD:SOT-23-6",
        description="TI TPS563200 3A Synchronous Buck Converter",
        # SOT-23-6 (DDC) pinout per TI TPS563200 datasheet (SLVSBE5):
        # 1=GND, 2=SW, 3=VIN, 4=VBST(BST), 5=EN, 6=FB
        pins=[
            PinDef("GND", "1", "power_in",  "left"),
            PinDef("SW",  "2", "output",    "right"),
            PinDef("VIN", "3", "power_in",  "left"),
            PinDef("BST", "4", "passive",   "right"),
            PinDef("EN",  "5", "input",     "left"),
            PinDef("FB",  "6", "input",     "right"),
        ],
    
    kicad_ref="Regulator_Switching:TPS563200",),
    "MP1584EN": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        description="MPS MP1584EN 3A Step-Down Buck Converter",
        # SOIC-8 pinout per MPS MP1584EN datasheet Rev 1.0:
        # 1=SW, 2=EN, 3=COMP, 4=FB, 5=GND, 6=FREQ, 7=VIN, 8=BST
        pins=[
            PinDef("SW",   "1", "output",   "right"),
            PinDef("EN",   "2", "input",    "left"),
            PinDef("COMP", "3", "passive",  "right"),
            PinDef("FB",   "4", "input",    "right"),
            PinDef("GND",  "5", "power_in", "left"),
            PinDef("FREQ", "6", "passive",  "left"),
            PinDef("VIN",  "7", "power_in", "left"),
            PinDef("BST",  "8", "passive",  "right"),
        ],
    ),

    # --- Ferrite Bead (Phase 22.8) ---
    "BLM18PG121SN1D": SymbolDef(
        ref_prefix="FB",
        footprint="Inductor_SMD:L_0603_1608Metric",
        description="Murata 120Ω@100MHz Ferrite Bead 0603",
        pins=[
            PinDef("~", "1", "passive", "left"),
            PinDef("~", "2", "passive", "right"),
        ],
    ),

    # --- Crystals (Phase 22.8) ---
    "HC49-8MHZ": SymbolDef(
        ref_prefix="Y",
        footprint="Crystal:Crystal_HC49-U_Vertical",
        description="8MHz HC-49S Crystal for STM32",
        pins=[
            PinDef("~", "1", "passive", "left"),
            PinDef("~", "2", "passive", "right"),
        ],
    ),
    "HC49-12MHZ": SymbolDef(
        ref_prefix="Y",
        footprint="Crystal:Crystal_HC49-U_Vertical",
        description="12MHz HC-49S Crystal for RP2040",
        pins=[
            PinDef("~", "1", "passive", "left"),
            PinDef("~", "2", "passive", "right"),
        ],
    ),
    "HC49-16MHZ": SymbolDef(
        ref_prefix="Y",
        footprint="Crystal:Crystal_HC49-U_Vertical",
        description="16MHz HC-49S Crystal for STM32",
        pins=[
            PinDef("~", "1", "passive", "left"),
            PinDef("~", "2", "passive", "right"),
        ],
    ),
    "HC49-32MHZ": SymbolDef(
        ref_prefix="Y",
        footprint="Crystal:Crystal_HC49-U_Vertical",
        description="32MHz HC-49S Crystal (ESP32/high-speed MCU)",
        pins=[
            PinDef("~", "1", "passive", "left"),
            PinDef("~", "2", "passive", "right"),
        ],
    ),

    # --- RF Antenna Connector ---
    "CONN-ANT-UFL": SymbolDef(
        ref_prefix="J",
        footprint="Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical",
        description="U.FL/IPEX RF Antenna Connector (50Ω coaxial)",
        pins=[
            PinDef("RF",  "1", "passive", "right"),
            PinDef("GND", "2", "power_in", "left"),
        ],
    ),

    # --- Debug Connectors (Phase 22.8) ---
    "CONN-SWD-2x5": SymbolDef(
        ref_prefix="J",
        footprint="Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical",
        description="ARM SWD 2x5 1.27mm Debug Header",
        pins=[
            PinDef("VTref", "1", "power_in",     "left"),
            PinDef("SWDIO", "2", "bidirectional", "right"),
            PinDef("GND",   "3", "power_in",      "left"),
            PinDef("SWCLK", "4", "input",         "right"),
            PinDef("NRST",  "5", "passive",        "right"),
            PinDef("SWO",   "6", "output",        "right"),
        ],
    ),
    "CONN-JTAG-2x10": SymbolDef(
        ref_prefix="J",
        footprint="Connector_PinHeader_2.54mm:PinHeader_2x10_P2.54mm_Vertical",
        description="JTAG 2x10 2.54mm Debug Header",
        pins=[
            PinDef("VTref", "1",  "power_in",     "left"),
            PinDef("TMS",   "2",  "bidirectional", "right"),
            PinDef("GND",   "3",  "power_in",      "left"),
            PinDef("TCK",   "4",  "input",         "right"),
            PinDef("TDI",   "5",  "input",         "right"),
            PinDef("TDO",   "6",  "output",        "right"),
            PinDef("TRST",  "7",  "input",         "right"),
            PinDef("NRST",  "8",  "input",         "right"),
            PinDef("GND2",  "9",  "power_in",      "left"),
            PinDef("GND3",  "10", "power_in",      "left"),
        ],
    ),

    # --- Industrie MCUs (Phase 25+) ---

    "STM32G431CBU6": SymbolDef(
        ref_prefix="U",
        footprint="Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm",   # UFQFPN-48 (CBU6 = 48-pin)
        description="STM32G4 Cortex-M4F 170MHz Industrial",
        # Physical pad numbers from KiCad MCU_ST_STM32G4.kicad_sym → STM32G431CBUx (UFQFPN-48).
        # STM32G431CBU6 = C-package = 48-pin UFQFPN (7x7mm). Pads 1–48, EP=pad 49 (GND).
        # VDD distributed: pads 23, 35, 48 → representative 23.
        # VSS = EP (pad 49). VDDA = 21.  VBAT = 1 (RTC/backup supply, tie to VDD if unused).
        # NOTE: NRST and BOOT0 are not in the KiCad symbol for UFQFPN-48; pad 7 = PG10/NRST.
        # SPI1 default: PA5=SCK=13, PA6=MISO=14, PA7=MOSI=15, PA4=CS=12.
        # I2C1:  PB6=SCL=44, PB7=SDA=45. UART1: PA9=TX=31, PA10=RX=32.
        # CAN/USB: PA11=33, PA12=34. SWD: PA13=36, PA14=37.
        # Extra CS/GPIO: PB12=25, PB0=17, PA3=11.
        pins=[
            PinDef("VDD",        "23", "power_in",     "left"),   # also pads 35 and 48
            PinDef("VSS",        "49", "power_in",     "left"),   # exposed thermal pad
            PinDef("VDDA",       "21", "power_in",     "left"),
            PinDef("VBAT",       "1",  "power_in",     "left"),   # tie to VDD if no RTC battery
            PinDef("PG10/NRST",  "7",  "input",        "left"),   # NRST alternate function on PG10
            PinDef("PA0",        "8",  "bidirectional","right"),
            PinDef("PA1",        "9",  "bidirectional","right"),
            PinDef("PA2",        "10", "bidirectional","right"),
            PinDef("PA3",        "11", "bidirectional","right"),
            PinDef("PA4",        "12", "bidirectional","right"),
            PinDef("PA5/SCK",    "13", "bidirectional","right"),
            PinDef("PA6/MISO",   "14", "bidirectional","right"),
            PinDef("PA7/MOSI",   "15", "bidirectional","right"),
            PinDef("PB0",        "17", "bidirectional","right"),
            PinDef("PA9/TX",     "31", "output",       "right"),
            PinDef("PA10/RX",    "32", "input",        "right"),
            PinDef("PA11/CAN_RX","33", "input",        "right"),
            PinDef("PA12/CAN_TX","34", "output",       "right"),
            PinDef("PA13/SWDIO", "36", "bidirectional","right"),
            PinDef("PA14/SWCLK", "37", "input",        "right"),
            PinDef("PB12",       "25", "bidirectional","right"),
            PinDef("PB6/SCL",    "44", "bidirectional","right"),
            PinDef("PB7/SDA",    "45", "bidirectional","right"),
        ],
    
    kicad_ref="MCU_ST_STM32G4:STM32G431CBUx",),
    "STM32L476RGT6": SymbolDef(
        ref_prefix="U",
        footprint="Package_QFP:LQFP-64_10x10mm_P0.5mm",
        description="STM32L4 Cortex-M4F 80MHz Ultra-Low-Power",
        # Physical pad numbers from STM32L476RGT6 LQFP-64 (DS10198 Rev11).
        # STM32L4 LQFP-64 ("R" package) uses same standard pin layout as STM32F4 LQFP-64:
        # pin 7=NRST, pin 13=VDDA, pin 18=VSS, pin 19=VDD, pin 21=PA5, pin 22=PA6,
        # pin 23=PA7, pin 42=PA9, pin 43=PA10, pin 46=PA13, pin 49=PA14,
        # pin 58=PB6, pin 59=PB7, pin 60=BOOT0. Confirmed via Nucleo-L476RG schematic.
        # Multiple VDD: 19, 32, 48, 64 (all connected on PCB). Multiple VSS: 18, 31, 47, 63.
        pins=[
            PinDef("VDD",       "19", "power_in",     "left"),
            PinDef("VSS",       "18", "power_in",     "left"),
            PinDef("VDDA",      "13", "power_in",     "left"),  # ADC/DAC analog supply; must be ≥ VDD
            PinDef("NRST",      "7",  "input",        "left"),
            PinDef("BOOT0",     "60", "input",        "left"),
            PinDef("PB6/SCL",   "58", "bidirectional","right"),
            PinDef("PB7/SDA",   "59", "bidirectional","right"),
            PinDef("PA5/SCK",   "21", "bidirectional","right"),
            PinDef("PA6/MISO",  "22", "bidirectional","right"),
            PinDef("PA7/MOSI",  "23", "bidirectional","right"),
            PinDef("PA9/TX",    "42", "output",       "right"),
            PinDef("PA10/RX",   "43", "input",        "right"),
            PinDef("PA13/SWDIO","46", "bidirectional","right"),
            PinDef("PA14/SWCLK","49", "input",        "right"),
        ],
    
    kicad_ref="MCU_ST_STM32L4:STM32L476RGTx",),
    "ATmega328P-AU": SymbolDef(
        ref_prefix="U",
        footprint="Package_QFP:TQFP-32_7x7mm_P0.8mm",
        description="ATmega328P Arduino Uno/Nano MCU",
        # Physical pad numbers from ATmega328P TQFP-32 datasheet (Microchip DS40002061B, Table 2).
        # TQFP-32 pinout is COMPLETELY DIFFERENT from DIP-28!
        # Pin 1=PD3/INT1, Pin 2=PD4, Pin 3=GND, Pin 4=VCC, Pin 5=GND, Pin 6=VCC,
        # Pin 7=PB6/XTAL1, Pin 8=PB7/XTAL2, Pin 9=PD5, Pin 10=PD6, Pin 11=PD7,
        # Pin 12=PB0, Pin 13=PB1, Pin 14=PB2, Pin 15=PB3/MOSI, Pin 16=PB4/MISO,
        # Pin 17=PB5/SCK, Pin 18=AVCC, Pin 19=ADC6, Pin 20=AREF, Pin 21=GND,
        # Pin 22=ADC7, Pin 23=PC0, Pin 24=PC1, Pin 25=PC2, Pin 26=PC3,
        # Pin 27=PC4/SDA, Pin 28=PC5/SCL, Pin 29=PC6/RESET, Pin 30=PD0/RXD,
        # Pin 31=PD1/TXD, Pin 32=PD2/INT0
        # Dual VCC: 4 and 6 (both must be connected). Dual GND: 3, 5, 21 (all must be connected).
        pins=[
            PinDef("VCC",      "4",  "power_in",     "left"),
            PinDef("GND",      "3",  "power_in",     "left"),
            PinDef("AVCC",     "18", "power_in",     "left"),
            PinDef("AREF",     "20", "passive",      "left"),   # analog ref; decouple to GND
            PinDef("RESET",    "29", "input",        "left"),   # PC6, active-low
            PinDef("PB6/XTAL1","7",  "input",        "left"),
            PinDef("PB7/XTAL2","8",  "output",       "left"),
            PinDef("PB5/SCK",  "17", "bidirectional","right"),
            PinDef("PB4/MISO", "16", "bidirectional","right"),
            PinDef("PB3/MOSI", "15", "bidirectional","right"),
            PinDef("PB2/SS",   "14", "bidirectional","right"),  # SPI hardware slave-select (CS)
            PinDef("PC4/SDA",  "27", "bidirectional","right"),
            PinDef("PC5/SCL",  "28", "bidirectional","right"),
            PinDef("PD0/RX",   "30", "input",        "right"),
            PinDef("PD1/TX",   "31", "output",       "right"),
            PinDef("PD2/INT0", "32", "bidirectional","right"),
            PinDef("PD3/INT1", "1",  "bidirectional","right"),
        ],
    
    kicad_ref="MCU_Microchip_ATmega:ATmega328P-A",),
    "ATmega2560-16AU": SymbolDef(
        ref_prefix="U",
        footprint="Package_QFP:TQFP-100_14x14mm_P0.5mm",
        description="ATmega2560 Arduino Mega MCU",
        # Physical pad numbers from ATmega2560 TQFP-100 datasheet (Microchip DS2549, Table 2).
        # Pin 1=PG5, Pin 2=PE0/RXD0, Pin 3=PE1/TXD0, Pin 10=VCC, Pin 11=GND,
        # Pin 19=PB1/SCK, Pin 20=PB2/MOSI, Pin 21=PB3/MISO, Pin 30=RESET,
        # Pin 31=VCC, Pin 33=XTAL2, Pin 34=XTAL1, Pin 43=PD0/SCL, Pin 44=PD1/SDA,
        # Pin 63=PJ0/RXD3, Pin 64=PJ1/TXD3, Pin 98=AREF, Pin 100=AVCC
        # Multiple VCC: 10, 31, 51, 71 (all must be connected). Multiple GND: 11, 32, 52, 72.
        pins=[
            PinDef("VCC",      "10", "power_in",     "left"),
            PinDef("GND",      "11", "power_in",     "left"),
            PinDef("AVCC",     "100","power_in",     "left"),
            PinDef("AREF",     "98", "passive",      "left"),   # analog reference; decouple to GND
            PinDef("RESET",    "30", "input",        "left"),   # active-low reset
            PinDef("XTAL1",    "34", "input",        "left"),
            PinDef("XTAL2",    "33", "output",       "left"),
            PinDef("PB1/SCK",  "19", "bidirectional","right"),
            PinDef("PB2/MOSI", "20", "bidirectional","right"),
            PinDef("PB3/MISO", "21", "bidirectional","right"),
            PinDef("PD0/SCL",  "43", "bidirectional","right"),
            PinDef("PD1/SDA",  "44", "bidirectional","right"),
            PinDef("PE0/RX0",  "2",  "input",        "right"),
            PinDef("PE1/TX0",  "3",  "output",       "right"),
            PinDef("IO5/PD5",  "9",  "bidirectional","right"),   # Arduino digital pin 5 (PD5)
        ],

    kicad_ref="MCU_Microchip_ATmega:ATmega2560-16A",),

    # --- Industrial ICs ---

    "SP3485EN": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        description="SP3485 3.3V RS485 Transceiver",
        # SOIC-8 pinout (Exar SP3485 datasheet Rev A):
        # 1=RO, 2=RE#, 3=DE, 4=DI, 5=GND, 6=A, 7=B, 8=VCC
        pins=[
            PinDef("RO",   "1", "output",       "right"),
            PinDef("RE#",  "2", "input",        "left"),
            PinDef("DE",   "3", "input",        "left"),
            PinDef("DI",   "4", "input",        "left"),
            PinDef("GND",  "5", "power_in",     "left"),
            PinDef("A",    "6", "bidirectional","right"),
            PinDef("B",    "7", "bidirectional","right"),
            PinDef("VCC",  "8", "power_in",     "left"),
        ],
    
    kicad_ref="Interface_UART:SP3485EN",),
    "TCAN1042VDRQ1": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        description="TCAN1042V CAN-FD Transceiver",
        # SOIC-8 pinout (TI TCAN1042-Q1 datasheet): 1=TXD, 2=GND, 3=VCC, 4=RXD, 5=nSTBY, 6=CANL, 7=CANH, 8=Vref
        pins=[
            PinDef("TXD",   "1", "input",         "left"),
            PinDef("GND",   "2", "power_in",      "left"),
            PinDef("VCC",   "3", "power_in",      "left"),
            PinDef("RXD",   "4", "output",        "right"),
            PinDef("nSTBY", "5", "input",         "left"),
            PinDef("CANL",  "6", "bidirectional", "right"),
            PinDef("CANH",  "7", "bidirectional", "right"),
            PinDef("Vref",  "8", "output",        "right"),
        ],
    ),
    "ADUM1201ARZ": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        description="ADuM1201 Dual Digital Isolator",
        # SOIC-8 pinout per Analog Devices ADuM1200/ADuM1201 datasheet Rev.L:
        # 1=VDD1, 2=VOA(out A to side1), 3=VIB(in B from side1), 4=GND1,
        # 5=GND2, 6=VOB(out B to side2), 7=VIA(in A from side2), 8=VDD2
        # Channel A direction: VIA(7,side2) → VOA(2,side1)
        # Channel B direction: VIB(3,side1) → VOB(6,side2)
        pins=[
            PinDef("VDD1",  "1", "power_in",     "left"),
            PinDef("VOA",   "2", "output",       "left"),   # ch.A output emerges on side1
            PinDef("VIB",   "3", "input",        "left"),   # ch.B input enters on side1
            PinDef("GND1",  "4", "power_in",     "left"),
            PinDef("GND2",  "5", "power_in",     "right"),
            PinDef("VOB",   "6", "output",       "right"),  # ch.B output emerges on side2
            PinDef("VIA",   "7", "input",        "right"),  # ch.A input enters on side2
            PinDef("VDD2",  "8", "power_in",     "right"),
        ],
    ),
    "DRV8833": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm",
        description="DRV8833 Dual H-Bridge 1.5A",
        # HTSSOP-16 (PWP) pinout per TI DRV8833 datasheet (SLVSAR1 Rev.E):
        # 1=nSLEEP, 2=AOUT1, 3=AISEN, 4=AOUT2, 5=BOUT2, 6=BISEN, 7=BOUT1,
        # 8=nFAULT, 9=BIN1, 10=BIN2, 11=VCP, 12=VM, 13=GND, 14=VINT, 15=AIN2, 16=AIN1, EP=GND
        pins=[
            PinDef("nSLEEP", "1",  "input",        "left"),
            PinDef("AOUT1",  "2",  "output",       "right"),
            PinDef("AISEN",  "3",  "passive",      "right"),
            PinDef("AOUT2",  "4",  "output",       "right"),
            PinDef("BOUT2",  "5",  "output",       "right"),
            PinDef("BISEN",  "6",  "passive",      "right"),
            PinDef("BOUT1",  "7",  "output",       "right"),
            PinDef("nFAULT", "8",  "output",       "right"),
            PinDef("BIN1",   "9",  "input",        "left"),
            PinDef("BIN2",   "10", "input",        "left"),
            PinDef("VCP",    "11", "passive",      "right"),
            PinDef("VM",     "12", "power_in",     "left"),
            PinDef("GND",    "13", "power_in",     "left"),
            PinDef("VINT",   "14", "passive",      "right"),
            PinDef("AIN2",   "15", "input",        "left"),
            PinDef("AIN1",   "16", "input",        "left"),
        ],
    ),
    "ULN2003A": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
        description="ULN2003A 7-Ch Darlington",
        pins=[
            PinDef("IN1",  "1",  "input",  "left"),
            PinDef("IN2",  "2",  "input",  "left"),
            PinDef("IN3",  "3",  "input",  "left"),
            PinDef("IN4",  "4",  "input",  "left"),
            PinDef("IN5",  "5",  "input",  "left"),
            PinDef("IN6",  "6",  "input",  "left"),
            PinDef("IN7",  "7",  "input",  "left"),
            PinDef("GND",  "8",  "power_in","left"),
            PinDef("COM",  "9",  "passive","right"),
            PinDef("OUT7", "10", "output", "right"),
            PinDef("OUT6", "11", "output", "right"),
            PinDef("OUT5", "12", "output", "right"),
            PinDef("OUT4", "13", "output", "right"),
            PinDef("OUT3", "14", "output", "right"),
            PinDef("OUT2", "15", "output", "right"),
            PinDef("OUT1", "16", "output", "right"),
        ],
    ),
    "CH340G": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
        description="CH340G USB-UART Bridge",
        # SOP-16 pinout per WCH CH340DS1 datasheet v3B:
        # 1=GND, 2=TXD, 3=RXD, 4=V3, 5=UD+, 6=UD-, 7=XI, 8=XO,
        # 9=CTS#, 10=DSR#, 11=RI#, 12=DCD#, 13=DTR#, 14=RTS#, 15=R232, 16=VCC
        pins=[
            PinDef("GND",  "1",  "power_in",     "left"),
            PinDef("TXD",  "2",  "output",       "right"),
            PinDef("RXD",  "3",  "input",        "left"),
            PinDef("V3",   "4",  "passive",      "right"),  # 3.3V int. reg. output, bypass with 100nF cap
            PinDef("D+",   "5",  "bidirectional","left"),
            PinDef("D-",   "6",  "bidirectional","left"),
            PinDef("XI",   "7",  "passive",      "left"),
            PinDef("XO",   "8",  "passive",      "right"),
            PinDef("VCC",  "16", "power_in",     "left"),
        ],
    
    kicad_ref="Interface_USB:CH340G",),
    "FT232RL": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:SSOP-28_5.3x10.2mm_P0.65mm",
        description="FT232RL USB-UART FTDI",
        # SSOP-28 pinout per FTDI DS_FT232R datasheet:
        # TXD=1, RTS#=3, VCCIO=4, RXD=5, GND=7, CTS#=10 (NOT 11!),
        # USBDP=15, USBDM=16, 3V3OUT=17, VCC=20. Pin 11=CBUS4.
        pins=[
            PinDef("TXD",    "1",  "output",       "right"),
            PinDef("RTS#",   "3",  "output",       "right"),
            PinDef("VCCIO",  "4",  "power_in",     "left"),
            PinDef("RXD",    "5",  "input",        "left"),
            PinDef("GND",    "7",  "power_in",     "left"),
            PinDef("CTS#",   "10", "input",        "right"),
            PinDef("USBDP",  "15", "bidirectional","left"),
            PinDef("USBDM",  "16", "bidirectional","left"),
            PinDef("3V3OUT", "17", "power_out",    "right"),
            PinDef("VCC",    "20", "power_in",     "left"),
        ],
    
    kicad_ref="Interface_USB:FT232RL",),

    # ------------------------------------------------------------------
    # DS18B20 — 1-Wire Temperature Sensor (TO-92)
    # ------------------------------------------------------------------
    "DS18B20": SymbolDef(
        ref_prefix="U",
        footprint="Package_TO_SOT_THT:TO-92_Inline",
        description="DS18B20 1-Wire Digital Temperature Sensor",
        pins=[
            PinDef("GND",  "1", "power_in",  "left"),
            PinDef("DQ",   "2", "bidirectional", "right"),
            PinDef("VDD",  "3", "power_in",  "left"),
        ],
    
    kicad_ref="Sensor_Temperature:DS18B20",),

    # ------------------------------------------------------------------
    # MCP9808 — I2C Precision Temperature Sensor (MSOP-8)
    # ------------------------------------------------------------------
    "MCP9808": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:MSOP-8_3x3mm_P0.65mm",
        description="MCP9808 High-Accuracy I2C Temperature Sensor",
        # MSOP-8 pinout (Microchip MCP9808 datasheet): 1=A2, 2=A1, 3=A0, 4=SDA, 5=SCL, 6=ALERT, 7=GND, 8=VDD
        pins=[
            PinDef("A2",    "1", "input",         "left"),
            PinDef("A1",    "2", "input",         "left"),
            PinDef("A0",    "3", "input",         "left"),
            PinDef("SDA",   "4", "bidirectional", "left"),
            PinDef("SCL",   "5", "input",         "left"),
            PinDef("ALERT", "6", "output",        "right"),
            PinDef("GND",   "7", "power_in",      "left"),
            PinDef("VDD",   "8", "power_in",      "left"),
        ],
    ),

    # ------------------------------------------------------------------
    # INA219 — I2C Current/Power Monitor (SOT-23-5 / MSOP-8)
    # ------------------------------------------------------------------
    "INA219": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:MSOP-8_3x3mm_P0.65mm",
        description="INA219 Bidirectional Current/Power Monitor",
        # MSOP-8 (DGK) pinout per TI INA219 datasheet SBOS448G:
        # Left: IN+(1), IN-(2), A1(3), A0(4)  Right: SDA(5), SCL(6), VS(7), GND(8)
        # NOTE: address pins (A1,A0) are at 3,4 — NOT at 5,6!
        pins=[
            PinDef("IN+",  "1", "input",         "left"),
            PinDef("IN-",  "2", "input",         "left"),
            PinDef("A1",   "3", "input",         "left"),
            PinDef("A0",   "4", "input",         "left"),
            PinDef("SDA",  "5", "bidirectional", "right"),
            PinDef("SCL",  "6", "input",         "right"),
            PinDef("VS",   "7", "power_in",      "right"),
            PinDef("GND",  "8", "power_in",      "left"),
        ],
    # Note: KiCad INA219AxD is SOIC-8 (DIP-8 footprint); our entry uses MSOP-8 — no kicad_ref
    ),

    # ------------------------------------------------------------------
    # AS5600 — Magnetic Rotary Encoder (SOIC-8)
    # ------------------------------------------------------------------
    "AS5600-ASOM": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        description="AS5600 12-bit Magnetic Rotary Position Sensor",
        # SOIC-8 pinout per AMS-OSRAM AS5600 datasheet:
        # 1=VDD5V, 2=VDD3V3, 3=OUT, 4=GND, 5=PGO, 6=SDA, 7=SCL, 8=DIR
        pins=[
            PinDef("VDD5V", "1", "power_in",     "left"),
            PinDef("VDD3V3","2", "power_in",     "left"),
            PinDef("OUT",   "3", "output",       "right"),
            PinDef("GND",   "4", "power_in",     "left"),
            PinDef("PGO",   "5", "passive",      "left"),
            PinDef("SDA",   "6", "bidirectional","left"),
            PinDef("SCL",   "7", "input",        "left"),
            PinDef("DIR",   "8", "input",        "left"),
        ],
    ),

    # ------------------------------------------------------------------
    # MAX7219 — LED Matrix Driver (DIP-24 / SOIC-24)
    # ------------------------------------------------------------------
    "MAX7219": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:SOIC-24W_7.5x15.4mm_P1.27mm",
        description="MAX7219 8-Digit LED Display Driver",
        # SOIC-24W pinout (Maxim MAX7219/MAX7221 datasheet):
        # 1=DIN, 2=DIG0, 3=DIG4, 4=GND, 5=DIG6, 6=DIG2, 7=DIG3, 8=DIG7,
        # 9=GND2, 10=VDD, 11=DIG5, 12=DIG1, 13=LOAD, 14=CLK, 15=DOUT,
        # 16=SEGG, 17=SEGB, 18=SEGC, 19=SEGE, 20=SEGD, 21=SEGF, 22=SEGDP, 23=SEGA, 24=ISET
        pins=[
            PinDef("DIN",   "1",  "input",    "left"),
            PinDef("DIG0",  "2",  "output",   "right"),
            PinDef("DIG4",  "3",  "output",   "right"),
            PinDef("GND",   "4",  "power_in", "left"),
            PinDef("DIG6",  "5",  "output",   "right"),
            PinDef("DIG2",  "6",  "output",   "right"),
            PinDef("DIG3",  "7",  "output",   "right"),
            PinDef("DIG7",  "8",  "output",   "right"),
            PinDef("GND2",  "9",  "power_in", "left"),
            PinDef("VDD",   "10", "power_in", "left"),
            PinDef("DIG5",  "11", "output",   "right"),
            PinDef("DIG1",  "12", "output",   "right"),
            PinDef("LOAD",  "13", "input",    "left"),
            PinDef("CLK",   "14", "input",    "left"),
            PinDef("DOUT",  "15", "output",   "right"),
            PinDef("SEGG",  "16", "output",   "right"),
            PinDef("SEGB",  "17", "output",   "right"),
            PinDef("SEGC",  "18", "output",   "right"),
            PinDef("SEGE",  "19", "output",   "right"),
            PinDef("SEGD",  "20", "output",   "right"),
            PinDef("SEGF",  "21", "output",   "right"),
            PinDef("SEGDP", "22", "output",   "right"),
            PinDef("SEGA",  "23", "output",   "right"),
            PinDef("ISET",  "24", "passive",  "left"),
        ],
    ),

    # ------------------------------------------------------------------
    # MAX31865 — RTD-to-Digital Converter (TSSOP-20)
    # ------------------------------------------------------------------
    "MAX31865ATP+": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm",
        description="MAX31865 RTD-to-Digital Converter (PT100)",
        # TSSOP-20 (ATP+) pinout (Maxim MAX31865 datasheet 19-7016):
        # 1=VDD, 2=GND, 3=CS, 4=SDI, 5=SDO, 6=SCLK, 7=DRDY/FAULT, 8=NC,
        # 9=FORCE+, 10=RTDIN+, 11=RTDIN-, 12=FORCE-, 13=REFIN+, 14=REFIN-, 15=BIAS, 16-20=NC
        pins=[
            PinDef("VDD",    "1",  "power_in",  "left"),
            PinDef("GND",    "2",  "power_in",  "left"),
            PinDef("CS",     "3",  "input",     "left"),
            PinDef("SDI",    "4",  "input",     "left"),
            PinDef("SDO",    "5",  "output",    "right"),
            PinDef("SCLK",   "6",  "input",     "left"),
            PinDef("DRDY",   "7",  "output",    "right"),  # open-drain, active LOW; reads fault via SPI
            PinDef("NC",     "8",  "no_connect","left"),
            PinDef("FORCE+", "9",  "passive",   "right"),  # RTD force+ terminal
            PinDef("RTDIN+", "10", "passive",   "right"),  # RTD measurement+
            PinDef("RTDIN-", "11", "passive",   "right"),  # RTD measurement-
            PinDef("FORCE-", "12", "passive",   "right"),  # RTD force- terminal
            PinDef("REFIN+", "13", "passive",   "right"),  # Reference resistor+
            PinDef("REFIN-", "14", "passive",   "right"),  # Reference resistor-
            PinDef("BIAS",   "15", "input",     "left"),   # Tie HIGH to enable RTD bias voltage
            PinDef("NC2",    "16", "no_connect","left"),
            PinDef("NC3",    "17", "no_connect","left"),
            PinDef("NC4",    "18", "no_connect","left"),
            PinDef("NC5",    "19", "no_connect","left"),
            PinDef("NC6",    "20", "no_connect","left"),
        ],
    ),

    # ------------------------------------------------------------------
    # MAX6675 — K-Type Thermocouple Interface (SOIC-8)
    # ------------------------------------------------------------------
    "MAX6675ISA+": SymbolDef(
        ref_prefix="U",
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        description="MAX6675 K-Type Thermocouple-to-Digital Converter",
        pins=[
            PinDef("GND",   "1", "power_in", "left"),
            PinDef("T-",    "2", "input",    "right"),
            PinDef("T+",    "3", "input",    "right"),
            PinDef("VCC",   "4", "power_in", "left"),
            PinDef("SCK",   "5", "input",    "left"),
            PinDef("CS",    "6", "input",    "left"),
            PinDef("SO",    "7", "output",   "right"),
            PinDef("NC",    "8", "passive",  "left"),
        ],
    ),

    # ------------------------------------------------------------------
    # W5500 — Ethernet Controller (LQFP-48)
    # ------------------------------------------------------------------
    "W5500": SymbolDef(
        ref_prefix="U",
        footprint="Package_QFP:LQFP-48_7x7mm_P0.5mm",
        description="W5500 Hardwired TCP/IP Ethernet Controller",
        # LQFP-48 pinout per WIZnet W5500 datasheet v1.1.0:
        # VDD=28, GND=29, SCSn=32, SCLK=33, MISO=34, MOSI=35, INTn=36, RSTn=37
        pins=[
            PinDef("VDD",    "28", "power_in",      "left"),
            PinDef("GND",    "29", "power_in",      "left"),
            PinDef("SCSn",   "32", "input",          "left"),
            PinDef("SCLK",   "33", "input",          "left"),
            PinDef("MISO",   "34", "output",         "right"),
            PinDef("MOSI",   "35", "input",          "left"),
            PinDef("INTn",   "36", "output",         "right"),
            PinDef("RSTn",   "37", "input",          "left"),
        ],
    
    kicad_ref="Interface_Ethernet:W5500",),

    # ------------------------------------------------------------------
    # RFM95W — LoRa Module (matching SX1276 pinout)
    # ------------------------------------------------------------------
    "RFM95W": SymbolDef(
        ref_prefix="U",
        footprint="RF_Module:HOPERF_RFM9XW_SMD",
        description="RFM95W LoRa Transceiver Module 868/915MHz",
        pins=[
            PinDef("GND",   "1",  "power_in",      "left"),
            PinDef("MISO",  "2",  "output",         "right"),
            PinDef("MOSI",  "3",  "input",          "left"),
            PinDef("SCK",   "4",  "input",          "left"),
            PinDef("NSS",   "5",  "input",          "left"),
            PinDef("RESET", "6",  "input",          "left"),
            PinDef("DIO0",  "7",  "output",         "right"),
            PinDef("ANT",   "8",  "passive",        "right"),
            PinDef("VCC",   "9",  "power_in",       "left"),
            PinDef("DIO1",  "10", "output",         "right"),
            PinDef("DIO2",  "11", "output",         "right"),
            PinDef("DIO5",  "12", "output",         "right"),
        ],
    ),
}


# ---------------------------------------------------------------------------
# Package → KiCad footprint fallback (for MPNs not in SYMBOL_MAP)
# ---------------------------------------------------------------------------

FOOTPRINT_FALLBACK: dict[str, str] = {
    "SOIC-8":    "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "SOT-23":    "Package_TO_SOT_SMD:SOT-23",
    "SOT-23-5":  "Package_TO_SOT_SMD:SOT-23-5",
    "SOT-223":   "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
    "SOT-25":    "Package_TO_SOT_SMD:SOT-23-5_HandSoldering",  # SOT-25 = SOT-23-5 compatible
    "QFN-24":    "Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.65x2.65mm",
    "QFN-32":    "Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.1x3.1mm",
    "LGA-8":     "Package_LGA:Bosch_LGA-8_3x3mm_P0.8mm_ClockwisePinNumbering",
    "TSSOP-24":  "Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm",
    "LQFP-48":   "Package_QFP:LQFP-48_7x7mm_P0.5mm",
    "0402":      "Resistor_SMD:R_0402_1005Metric",
    "RC0402":    "Resistor_SMD:R_0402_1005Metric",
    "C0402":     "Capacitor_SMD:C_0402_1005Metric",
    "0603":      "Resistor_SMD:R_0603_1608Metric",
    "C0603":     "Capacitor_SMD:C_0603_1608Metric",
    "0805":      "Resistor_SMD:R_0805_2012Metric",
    # Vishay WSL2512 series — 2512 power shunt resistor (6.35×3.2mm)
    "WSL25":     "Resistor_SMD:R_2512_6332Metric",
    "2512":      "Resistor_SMD:R_2512_6332Metric",
    # Tactile push-button families (Alps SKRP/SKQG, Panasonic EVQ, TE FSM, etc.)
    # footprint_mapper does substring matching so "SKRP" catches SKRPACE010, etc.
    "SKRP":      "Button_Switch_SMD:SW_Push_SPST_NO_Alps_SKRK",
    "SKQG":      "Button_Switch_SMD:SW_Push_SPST_NO_Alps_SKRK",
    "SKRT":      "Button_Switch_SMD:SW_Push_SPST_NO_Alps_SKRK",
    "EVQ":       "Button_Switch_SMD:Panasonic_EVQPUL_EVQPUC",
    "TACT":      "Button_Switch_SMD:SW_Push_SPST_NO_Alps_SKRK",
    # SMD LED families — LTST: Lite-On 0603 LEDs, HSMF: Avago, TLMS: Vishay
    "LTST":      "LED_SMD:LED_0603_1608Metric",
    "HSMF":      "LED_SMD:LED_0603_1608Metric",
    "TLMS":      "LED_SMD:LED_0603_1608Metric",
    "TLMG":      "LED_SMD:LED_0603_1608Metric",
}


# ---------------------------------------------------------------------------
# Generic symbol factory for unknown MPNs
# ---------------------------------------------------------------------------

def _generic_symbol(mpn: str, role: str, interface_types: list[str]) -> SymbolDef:
    """Build a minimal symbol for MPNs not in SYMBOL_MAP."""
    prefix_map = {
        "mcu":     "U",
        "sensor":  "U",
        "power":   "U",
        "comms":   "U",
        "passive": "C",
        "other":   "U",
        "actuator": "U",
    }
    prefix = prefix_map.get(role, "U")
    # Detect passive sub-type from MPN pattern
    if role == "passive":
        mpn_upper = mpn.upper()
        if not mpn_upper:
            # Empty MPN — circuit-template resistors have no mpn_hint.
            # Real capacitors always receive a proper Murata/KEMET MPN; any
            # passive that arrives here with an empty MPN is almost certainly a
            # circuit-template resistor (feedback, input, bias, …).
            prefix = "R"
        elif mpn_upper.startswith(("R_", "R0", "RC", "ERJ", "CRCW", "RES", "WSL")):
            prefix = "R"
        elif mpn_upper.startswith(("L_", "L0", "IND", "SRR", "NR")):
            prefix = "L"
        elif mpn_upper.startswith(("D_", "LED", "BAV", "1N", "SS")):
            prefix = "D"
        elif mpn_upper.startswith(("FB", "BLM")):
            prefix = "FB"
        # else stays "C" (capacitors, default for passives)

    # Passives (R, C, L, D, FB) always use 2 anonymous passive-type pins.
    # The generic VDD/GND power_in pins below are for ICs only — placing them
    # on resistors/caps causes _power_connections() to emit spurious extra
    # wires and power symbols, generating "unconnected wire endpoint" ERC warnings.
    if role == "passive":
        footprint_map = {
            "R": "Resistor_SMD:R_0402_1005Metric",
            "C": "Capacitor_SMD:C_0402_1005Metric",
            "L": "Inductor_SMD:L_0402_1005Metric",
            "D": "Diode_SMD:D_SOD-123",
            "FB": "Inductor_SMD:L_0402_1005Metric",
        }
        return SymbolDef(
            ref_prefix=prefix,
            footprint=footprint_map.get(prefix, "Resistor_SMD:R_0402_1005Metric"),
            pins=[
                PinDef("~", "1", "passive", "left"),
                PinDef("~", "2", "passive", "right"),
            ],
            description=f"Passive {mpn}",
        )

    footprint = "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"

    # Actuator sub-types: buttons/switches get a 2-pin passive-like symbol
    mpn_upper = mpn.upper()
    _is_button = role == "actuator" and any(
        kw in mpn_upper for kw in ("SKRP", "SKQG", "EVQ", "KSC", "TACT", "FSM", "PTS", "DTSM")
    )
    if _is_button:
        prefix = "SW"
        # Pick the closest KiCad-stock footprint for the button MPN family.
        # SKRP/SKQG series: Alps SMD tactile push button
        # EVQ/Panasonic: use Panasonic EVQPUL (2.5×1.6mm) as generic fallback
        _mpn_u = mpn.upper()
        if any(k in _mpn_u for k in ("SKRP", "SKQG", "SKRT")):
            footprint = "Button_Switch_SMD:SW_Push_SPST_NO_Alps_SKRK"
        elif any(k in _mpn_u for k in ("EVQ",)):
            footprint = "Button_Switch_SMD:Panasonic_EVQPUL_EVQPUC"
        else:
            footprint = "Button_Switch_SMD:SW_Push_SPST_NO_Alps_SKRK"
        return SymbolDef(
            ref_prefix=prefix,
            footprint=footprint,
            pins=[
                PinDef("1", "1", "passive", "left"),
                PinDef("2", "2", "passive", "right"),
            ],
            description=f"Push button {mpn}",
        )

    pins: list[PinDef] = [
        PinDef("VDD", "1", "power_in", "left"),
        PinDef("GND", "2", "power_in", "left"),
    ]
    pin_num = 3

    # MCUs are SPI masters: use bidirectional to avoid output-output ERC errors
    # when connecting to SPI slaves that have MISO as output.
    _is_mcu = role == "mcu"

    for iface in interface_types:
        if iface == "I2C":
            pins += [
                PinDef("SDA",  str(pin_num),     "bidirectional", "right"),
                PinDef("SCL",  str(pin_num + 1), "input",         "right"),
            ]
            pin_num += 2
        elif iface == "SPI":
            if _is_mcu:
                # MCU master: bidirectional avoids pin_to_pin / pin_not_driven ERC
                pins += [
                    PinDef("MOSI", str(pin_num),     "bidirectional", "right"),
                    PinDef("MISO", str(pin_num + 1), "bidirectional", "right"),
                    PinDef("SCLK", str(pin_num + 2), "bidirectional", "right"),
                    PinDef("CS",   str(pin_num + 3), "bidirectional", "right"),
                ]
            else:
                # Peripheral slave: MOSI in, MISO out, SCLK in, CS in
                pins += [
                    PinDef("MOSI", str(pin_num),     "input",  "right"),
                    PinDef("MISO", str(pin_num + 1), "output", "right"),
                    PinDef("SCLK", str(pin_num + 2), "input",  "right"),
                    PinDef("CS",   str(pin_num + 3), "input",  "right"),
                ]
            pin_num += 4
        elif iface == "UART":
            pins += [
                PinDef("TX", str(pin_num),     "output", "right"),
                PinDef("RX", str(pin_num + 1), "input",  "right"),
            ]
            pin_num += 2
        elif iface == "GPIO":
            pins.append(PinDef("GPIO", str(pin_num), "bidirectional", "right"))
            pin_num += 1

    return SymbolDef(
        ref_prefix=prefix,
        footprint=footprint,
        pins=pins,
        description=f"Generic {mpn}",
    )


# ---------------------------------------------------------------------------
# KiCad Symbol → SymbolDef converter (used by Flow 1)
# ---------------------------------------------------------------------------

# KiCad side heuristic: power_in and input pins go left, everything else right.
# This is the same convention used throughout symbol_map.py.
_KICAD_LEFT_TYPES = frozenset(("power_in", "input"))


def _kicad_to_symboldef(sym: "KiCadSymbol") -> SymbolDef:  # type: ignore[name-defined]
    """Convert a KiCadSymbol into a SymbolDef compatible with the rest of the system.

    Hidden pins (redundant power/GND copies) are filtered out — they are not
    needed in schematic generation and cause duplicate-pin ERC issues.
    """
    # Map KiCad ref property to our ref_prefix convention
    # KiCad symbols store the Reference property (U/R/C/…)
    # We infer it from the lib name as a fallback.
    lib = sym.lib_name.lower()
    if "mcu" in lib or "audio" in lib or "rf" in lib or "sensor" in lib \
            or "interface" in lib or "regulator" in lib or "isolator" in lib \
            or "memory" in lib or "display" in lib or "driver" in lib \
            or "analog" in lib:
        ref_prefix = "U"
    else:
        ref_prefix = "U"

    pins = [
        PinDef(
            name=p.name,
            number=p.number,
            type=p.pin_type,
            side="left" if p.pin_type in _KICAD_LEFT_TYPES else "right",
        )
        for p in sym.pins
        if not p.hidden
    ]

    return SymbolDef(
        ref_prefix=ref_prefix,
        footprint=sym.footprint,
        pins=pins,
        description=sym.description,
        kicad_ref=f"{sym.lib_name}:{sym.part_name}",
    )


# ---------------------------------------------------------------------------
# 3-Flow component lookup
# ---------------------------------------------------------------------------

def get_symbol_def(mpn: str, role: str = "", interface_types: list[str] | None = None) -> SymbolDef:
    """Look up a SymbolDef using 3-flow priority.

    Resolution order:
      Flow 1: KiCad local library   — exact, verified (when KiCad installed)
      Flow 2: shared EDA profiles   — Pydantic-validated, canonical
      Flow 3: SYMBOL_MAP            — hand-curated DB (always available)
      Flow 4: _generic_symbol       — auto-generated from interface_types
    """
    # Flow 1: KiCad local library (zero hallucinations, canonical pin numbers)
    # Try both import paths: repo-root context ("synthesizer.tools") and
    # synthesizer-root context ("tools") to handle different invocation styles.
    try:
        try:
            from synthesizer.tools.kicad_library import KiCadLibrary, KICAD_AVAILABLE
        except ImportError:
            from tools.kicad_library import KiCadLibrary, KICAD_AVAILABLE  # type: ignore[import]
        if KICAD_AVAILABLE:
            sym = KiCadLibrary().lookup_any(mpn)
            if sym is not None:
                return _kicad_to_symboldef(sym)
    except Exception:
        pass  # KiCad not available or import error — fall through

    # Flow 2: Shared EDA profiles (Pydantic-validated)
    try:
        from shared.knowledge.eda_profiles import get_eda_profile
        profile = get_eda_profile(mpn)
        if profile is not None:
            return SymbolDef(
                ref_prefix=profile.symbol.ref_prefix,
                footprint=profile.footprint.kicad_name,
                description=profile.symbol.description,
                pins=[
                    PinDef(
                        name=p.name,
                        number=p.number,
                        type=p.electrical_type,
                        side=p.side,
                    )
                    for p in profile.symbol.pins
                ],
            )
    except Exception:
        pass  # shared package not available — fall through

    # Flow 3: Our hand-curated DB
    if mpn in SYMBOL_MAP:
        return SYMBOL_MAP[mpn]
    # Case-insensitive match
    mpn_lower = mpn.lower()
    for key, sdef in SYMBOL_MAP.items():
        if key.lower() == mpn_lower:
            return sdef

    # Flow 4: Auto-generated from interface_types
    return _generic_symbol(mpn, role, interface_types or [])
