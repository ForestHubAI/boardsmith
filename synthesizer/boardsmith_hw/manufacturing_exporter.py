# SPDX-License-Identifier: AGPL-3.0-or-later
"""PCB Manufacturing Exporter — packages fab-ready files for JLCPCB, Seeed Fusion, etc.

Converts existing PCB pipeline output (Gerbers, BOM, .kicad_pcb) into
service-specific order packages:

  ManufacturingExporter().export(
      service="jlcpcb",
      pcb_result=result,
      hir_dict=hir_dict,
      out_dir=Path("./output/manufacturing/jlcpcb"),
  )

Outputs (per service):
  gerbers_{service}.zip    — Gerber + drill files ready to upload
  bom_{service}.csv        — BOM in service-specific format
  cpl_{service}.csv        — Component Placement List (Pick & Place)
  README_{service}.md      — Step-by-step upload instructions

No external dependencies — uses Python stdlib only (zipfile, csv, re, pathlib).
"""
from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from boardsmith_hw.pcb_pipeline import PcbResult

log = logging.getLogger(__name__)

ServiceName = Literal["jlcpcb", "seeed", "pcbway", "generic"]

# ---------------------------------------------------------------------------
# Static LCSC part number map (MPN → LCSC Part #)
# Used for JLCPCB PCBA orders. Keep to the most common components in
# the Boardsmith knowledge base.
# ---------------------------------------------------------------------------

_LCSC_MAP: dict[str, str] = {
    # MCUs / Modules
    "ESP32-WROOM-32":    "C701341",
    "ESP32-WROOM-32D":   "C701342",
    "ESP32-WROOM-32E":   "C2913205",
    "ESP32-C3-MINI-1":   "C2838502",
    "RP2040":            "C2040",
    "STM32F103C8T6":     "C8734",
    "STM32F411CEU6":     "C188786",
    "STM32F401CCU6":     "C164586",
    "nRF52840-QIAA":     "C190794",
    # Sensors
    "BME280":            "C92489",
    "BMP280":            "C92489",
    "MPU6050":           "C24112",
    "MPU-6050":          "C24112",
    "ICM-42688-P":       "C2691144",
    "SCD41":             "C2893871",
    "SHT31-DIS":         "C1749781",
    "AHT20":             "C654522",
    "VL53L0X":           "C91600",
    "APDS-9960":         "C145103",
    "MAX30102":          "C189655",
    "DS18B20":           "C134498",
    # Display / Comms ICs
    "SSD1306":           "C179399",
    "ST7735":            "C24604",
    "AT24C02":           "C2803",
    "W25Q32JVSSIQ":      "C308872",
    "W25Q64JVSSIQ":      "C179171",
    # Power management
    "AMS1117-3.3":       "C6186",
    "AMS1117-5.0":       "C134077",
    "MCP73831T-2ACI/OT": "C14879",
    "IP5306":            "C181692",
    "XC6210B332MR":      "C6021",
    "TPS63020":          "C15623",
    # Op-amps / drivers
    "LM358":             "C7950",
    "MCP4725":           "C47558",
    "DRV8833":           "C50506",
    "TB6612FNG":         "C3625",
    # Passives (common generic values)
    "RC0402FR-0710KL":   "C25744",   # 10k 0402
    "RC0402FR-074K7L":   "C25900",   # 4.7k 0402
    "RC0402FR-07100RL":  "C98220",   # 100R 0402
    "GRM155R71C104KA88D": "C14663",  # 100nF 0402
    "GRM188R61A106KE69D": "C19666",  # 10uF 0805
    "CL10A105KB8NNNC":   "C15849",   # 1uF 0402
    "GRM155R60J104KA01D": "C81521",  # 100nF 0402 (alt)
    # Phase 22.8 / Phase 25.3: New components
    # Level shifters
    "BSS138":            "C2980",    # N-Ch MOSFET level shifter
    "TXS0102":           "C17115",   # 2-bit bidirectional level shifter
    "TXS0104":           "C27792",   # 4-bit bidirectional level shifter
    "TXB0104":           "C70811",   # 4-bit bidirectional auto-dir
    # Buck converters
    "TPS563200":         "C2765621", # 3A synchronous buck 1-17V
    "MP1584EN":          "C17742",   # 3A high frequency buck
    "LM2596S-5.0":       "C29063",   # 3A 5V buck converter
    "LM2596S-3.3":       "C16862",   # 3A 3.3V buck converter
    "XL4016E1":          "C2576",    # 8A high current buck
    # Crystals (HC49 package)
    "ABM8-16.000MHZ-B2-T": "C16177",  # 16MHz HC-49S crystal
    "ABM8-12.000MHZ-B2-T": "C9002",   # 12MHz HC-49S crystal
    "ABM8-8.000MHZ-B2-T":  "C32320",  # 8MHz HC-49S crystal
    "FA-128-16.000MHZ":  "C16177",   # 16MHz crystal (generic alias)
    "FA-128-12.000MHZ":  "C9002",    # 12MHz crystal (generic alias)
    "FA-128-8.000MHZ":   "C32320",   # 8MHz crystal (generic alias)
    # Ferrite beads
    "BLM18PG121SN1D":    "C176672",  # 120Ω 0603 ferrite bead EMI
    "BLM18BD102SN1D":    "C83882",   # 1kΩ 0603 ferrite bead power
    # Debug connectors
    "CONN-SWD-2x5":      "C160191",  # 10-pin 1.27mm SWD header
    "TC2030-MCP-NL":     "C2847674", # Tag-Connect 6-pin SWD
    # Additional sensors
    "SX1276":            "C13029",   # LoRa transceiver 868/915MHz
    "W25Q128JVSIQ":      "C97521",   # 128Mbit SPI NOR Flash
    "W25Q128JVSSIQ":     "C97521",   # 128Mbit SPI NOR Flash (alt)
    "W25Q64FVSSIG":      "C179171",  # 64Mbit SPI NOR Flash
    "AT24C256":          "C9314",    # 256kbit I2C EEPROM
    "DS3231SN":          "C9474",    # RTC I2C precision
    "TP4056":            "C16581",   # Li-Ion charger 1A
    "MCP73831T-2ACI/OT": "C14879",  # Li-Ion charger 500mA
    "CH340G":            "C14267",   # USB-UART bridge
    "CH340C":            "C84681",   # USB-UART bridge (no crystal needed)
    "CP2102":            "C6568",    # USB-UART bridge Silicon Labs
    "INA219":            "C69867",   # Current/power monitor I2C
    "INA226":            "C201876",  # High precision power monitor I2C
    "SN65HVD230":        "C113712",  # CAN bus transceiver 3.3V
    "MAX485":            "C65510",   # RS-485 transceiver
    # Additional transistors / FETs
    "2N7002":            "C8545",    # N-Ch MOSFET SOT-23 60V
    "BC817":             "C52717",   # NPN transistor SOT-23
    "MMBT3904":          "C20526",   # NPN general purpose SOT-23
    # TVS / protection
    "USBLC6-2SC6":       "C7519",    # USB ESD protection SOT-23-6
    "PRTR5V0U2X":        "C85040",   # ESD protection USB ±5V
    # Phase 25+ Industrie-Pack
    "STM32G431CBU6":     "C529330",  # STM32G4 Cortex-M4F 170MHz UFQFPN-48
    "STM32L476RGT6":     "C94835",   # STM32L4 Cortex-M4F 80MHz LQFP-64
    "STM32F746ZGT6":     "C110355",  # STM32F7 Cortex-M7 216MHz LQFP-144
    "LPC55S69JBD100":    "C523945",  # NXP LPC55 Dual M33 LQFP-100
    "ATSAME51J20A-AU":   "C568024",  # Microchip SAM E51 M4F TQFP-64
    "ATmega328P-AU":     "C14877",   # AVR 8-bit Arduino Uno TQFP-32
    "ATmega2560-16AU":   "C7506",    # AVR 8-bit Arduino Mega TQFP-100
    "SMBJ24CA":          "C190218",  # TVS 24V bidirectional SMB
    "SMAJ24CA":          "C247015",  # TVS 24V surge DO-214AC
    "MF-MSMF050-2":      "C17313",   # Polyfuse 500mA resettable 1812
    "LM5164DDAR":        "C559982",  # 42V Industrial Buck 1A SOIC-8
    "TPS7A2033DBVR":     "C427700",  # Low-noise 200mA LDO SOT-23-5
    "TPS3840DL33DBVR":   "C471327",  # Voltage Supervisor 3.3V SOT-23-5
    "MT3608":            "C84817",   # Boost 2A SOT-23-6
    "SP3485EN":          "C8932",    # RS485 3.3V SOIC-8
    "TCAN1042VDRQ1":     "C190733",  # CAN-FD 5Mbps AEC-Q100 SOIC-8
    "KSZ8081RNAIA":      "C141978",  # 10/100 Ethernet PHY QFN-32
    "ADUM1201ARZ":       "C53597",   # Dual Digital Isolator SOIC-8
    "RFM95W":            "C191298",  # LoRa 868/915MHz Module
    "MAX31865ATP+":      "C113297",  # RTD/PT100 Interface TQFN-20
    "ACS712ELCTR-20A-T": "C10681",   # 20A Hall Current Sensor SOIC-8
    "AS5600-ASOM":       "C403220",  # Magnetic Rotary Encoder SOIC-8
    "MAX6675ISA+":       "C17024",   # Thermocouple K-Type SOIC-8
    "SCD41":             "C2893871",  # CO2+Temp+Humidity Sensor
    "TLE4913":           "C2840948", # Hall Effect Switch SOT-23
    "PESD5V0S2BT":       "C83046",   # ESD USB 5V SOT-23
    "PESD3V3S2UT":       "C315958",  # ESD 3.3V Lines SOT-23
    "BLM18BD102SN1D":    "C83882",   # Ferrite 1kΩ 0603 (dup from Phase 25.3)
    "DLW21HN900SQ2L":    "C257927",  # CMC 90Ω 0805
    "DRV8833":           "C50506",   # Dual H-Bridge 1.5A HTSSOP-16
    "ULN2003A":          "C7378",    # 7-ch Darlington SOIC-16
    "TLP281-4":          "C15742",   # Quad Optocoupler SOP-16
    "AO3400A":           "C20917",   # N-MOSFET 30V SOT-23
    "IRF540N":           "C2845",    # N-MOSFET 33A TO-220
    "ADUM3160BRWZ":      "C116022",  # USB Isolator SOIC-16W
    "FM25V10-G":         "C93051",   # 1Mbit FRAM SPI SOIC-8
    "IS25LP128F":        "C179170",  # 128Mbit Ind. SPI NOR SOIC-8
    "CY15B104Q":         "C723028",  # 4Mbit FRAM SPI SOIC-8
    "FT232RL":           "C8690",    # USB-UART FTDI SSOP-28
    "CP2102N":           "C964632",  # USB-UART SiLabs QFN-28
    "NEO-6M":            "C18072",   # GPS Module u-blox
    "HC-05":             "C121149",  # Bluetooth Classic Module
    "MCP1700-3302E":     "C39051",   # 250mA Low-IQ LDO SOT-23
    # Phase 25 audit — fill gaps for all 145 DB components
    # MCUs
    "ESP32-C3-WROOM-02": "C3013797", # ESP32-C3 WROOM-02 module
    "STM32H743VIT6":     "C73795",   # STM32H7 Cortex-M7 LQFP-100
    "STM32F405RGT6":     "C13988",   # STM32F4 Cortex-M4 LQFP-64
    "nRF52840":          "C190794",  # Nordic nRF52840 BLE SoC (alias)
    "MIMXRT1062DVJ6A":   "C472636",  # NXP i.MX RT1062 BGA-196
    "R7FA4M2AD3CFP":     "C2832455", # Renesas RA4M2 Cortex-M33 LQFP-100
    "XMC4700F144K2048":  "C963960",  # Infineon XMC4700 Cortex-M4 LQFP-144
    # Sensors
    "BME680":            "C241476",  # Bosch BME680 gas+env sensor
    "SHTC3":             "C194567",  # Sensirion SHTC3 temp+hum DFN-4
    "MCP9808":           "C128750",  # Microchip MCP9808 temp sensor
    "ADXL345":           "C30809",   # Analog Devices ADXL345 accel
    "LIS3DH":            "C14207",   # ST LIS3DHTR accel LGA-16
    "BNO055":            "C478170",  # Bosch BNO055 9DOF IMU
    "LSM6DSO":           "C2765234", # ST LSM6DSOTR 6DOF IMU
    "TSL2561":           "C125711",  # AMS TSL2561 lux sensor
    "BH1750FVI":         "C78960",   # Rohm BH1750FVI ambient light
    "ADS1115":           "C37593",   # TI ADS1115 16-bit ADC
    "ADS8681":           "C544960",  # TI ADS8681 16-bit SAR ADC
    "AM2302":            "C264919",  # Aosong AM2302 (DHT22) temp+hum
    "HX711":             "C12083",   # Avia HX711 24-bit ADC load cell
    "HC-SR04":           "C424789",  # Ultrasonic range sensor module
    "MAX98357A":         "C1879803", # Maxim I2S class-D amp
    "WM8731":            "C32447",   # Wolfson audio codec QFN-28
    # Displays
    "SH1106":            "C91189",   # SH1106 OLED controller
    "ST7735S":           "C24604",   # Sitronix ST7735S TFT driver
    "ST7789V":           "C64654",   # Sitronix ST7789V TFT driver
    "ILI9341":           "C152420",  # Ilitek ILI9341 TFT driver
    "MAX7219":           "C56832",   # Maxim MAX7219 LED driver
    "HT16K33":           "C2898418", # Holtek HT16K33 LED driver
    # Comms
    "NEO-M8N":           "C473350",  # u-blox NEO-M8N GNSS module
    "nRF24L01+":         "C36668",   # Nordic nRF24L01+ 2.4GHz
    "ENC28J60":          "C7675",    # Microchip ENC28J60 Ethernet
    "W5500":             "C20493",   # WIZnet W5500 Ethernet
    "MCP2515":           "C12174",   # Microchip MCP2515 CAN controller
    "CC1101":            "C29947",   # TI CC1101 sub-GHz transceiver
    "LAN8720A":          "C110817",  # Microchip LAN8720A ETH PHY
    "SIM7600G-H":        "C2988128", # SIMCom 4G LTE-A module
    "SIM800L":           "C113572",  # SIMCom 2G GSM module
    "TCA9548A":          "C130972",  # TI TCA9548A I2C multiplexer
    # Memory
    "W25Q128JV":         "C97521",   # Winbond 128Mbit SPI NOR (alias)
    "AT24C32":           "C12446",   # Atmel 32kbit I2C EEPROM
    "23LC1024":          "C91136",   # Microchip 1Mbit SPI SRAM
    "MICROSD-SLOT-SPI":  "C585356",  # MicroSD card socket
    # Actuators / drivers
    "DRV8825":           "C35068",   # TI DRV8825 stepper driver
    "A4988":             "C73427",   # Allegro A4988 stepper driver
    "PCA9685":           "C28569",   # NXP PCA9685 16-ch PWM
    # Utility / RTC
    "DS3231":            "C9474",    # Maxim DS3231 precision RTC
    "PCF8563":           "C7428",    # NXP PCF8563 RTC I2C
    "MCP23017":          "C16399",   # Microchip MCP23017 GPIO expander
    "PCF8574":           "C7559",    # NXP PCF8574 I2C GPIO expander
    # Discrete / Connectors
    "LTST-C150GKT":      "C44147",   # Lite-On 0603 green LED
    "SKRPACE010":        "C139797",  # Alps tactile switch 6mm
    "2N2222A":           "C358536",  # MMBT2222A NPN SOT-23
    "IRLZ44N":           "C44891",   # IR IRLZ44N N-MOSFET TO-220
    "1N4007":            "C81598",   # 1N4007 rectifier (M7 SMD)
    "MCP6002":           "C7420",    # Microchip MCP6002 dual op-amp
    "LM393":             "C7955",    # TI LM393 dual comparator
    "LM4040":            "C177968",  # TI LM4040 voltage reference
    # Connectors
    "CONN-UART-4PIN":    "C145884",  # 4-pin 2.54mm header
    "CONN-CAN-2PIN":     "C429954",  # 2-pin screw terminal
    "CONN-RS485-2PIN":   "C429954",  # 2-pin screw terminal
    "USB-C-CONN":        "C168688",  # USB-C 16P SMD receptacle
    "CONN-JTAG-2x10":   "C169113",  # 2x10 1.27mm box header
    # Crystals (by board-level MPN alias)
    "HC49-8MHz":         "C32320",   # 8MHz HC-49S crystal
    "HC49-12MHz":        "C9002",    # 12MHz HC-49S crystal
    "HC49-16MHz":        "C16177",   # 16MHz HC-49S crystal
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ComponentPlacement:
    """Placement data for one component (CPL row).

    Attributes:
        designator: Reference designator, e.g. "U1", "R3".
        mid_x_mm:   Centroid X coordinate in mm.
        mid_y_mm:   Centroid Y coordinate in mm.
        layer:      "Top" or "Bottom" (JLCPCB convention).
        rotation:   Rotation in degrees (0–360).
    """

    designator: str
    mid_x_mm: float
    mid_y_mm: float
    layer: str
    rotation: float


@dataclass
class ManufacturingPackage:
    """Result of a complete manufacturing export for one service.

    Attributes:
        service:           Target fab service name.
        out_dir:           Directory where all files were written.
        gerber_zip:        Path to the Gerber ZIP (None if Gerber dir missing).
        bom_csv:           Path to the BOM CSV (None if no BOM entries in HIR).
        cpl_csv:           Path to the CPL CSV (None if .kicad_pcb not found).
        readme:            Path to the README file.
        warnings:          Non-fatal warnings accumulated during export.
        component_count:   Number of BOM line items.
        placements_found:  Number of footprints parsed from .kicad_pcb.
    """

    service: str
    out_dir: Path
    gerber_zip: Path | None
    bom_csv: Path | None
    cpl_csv: Path | None
    readme: Path | None
    warnings: list[str] = field(default_factory=list)
    component_count: int = 0
    placements_found: int = 0
    # Phase 25.2: LCSC coverage tracking
    lcsc_coverage_pct: float = 0.0   # 0.0–100.0: % of BOM lines with LCSC number
    missing_lcsc: list[str] = field(default_factory=list)  # MPNs without LCSC


# ---------------------------------------------------------------------------
# Module-level S-expression parsing helpers
# ---------------------------------------------------------------------------


def _split_footprint_blocks(text: str) -> list[str]:
    """Return a list of raw text blocks, one per (footprint ...) in the PCB file.

    Uses depth-counting to find matching closing parentheses — no full parser needed.
    """
    blocks: list[str] = []
    i = 0
    while True:
        start = text.find("(footprint ", i)
        if start == -1:
            break
        depth = 0
        j = start
        while j < len(text):
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if depth == 0:
                    blocks.append(text[start : j + 1])
                    i = j + 1
                    break
            j += 1
        else:
            # Malformed: no closing parenthesis found — stop
            break
    return blocks


def _extract_reference(block: str) -> str | None:
    """Extract the Reference designator from a footprint block."""
    m = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block)
    return m.group(1) if m else None


def _extract_at(block: str) -> tuple[float | None, float | None, float]:
    """Extract (at X Y [ROTATION]) from the first 'at' in a footprint block.

    Returns (x, y, rotation). Rotation defaults to 0.0 when omitted.
    Returns (None, None, 0.0) if no (at ...) found.
    """
    m = re.search(r"\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)", block)
    if not m:
        return (None, None, 0.0)
    x = float(m.group(1))
    y = float(m.group(2))
    rot = float(m.group(3)) if m.group(3) else 0.0
    return (x, y, rot)


def _extract_layer(block: str) -> str | None:
    """Extract the layer string from a footprint block header.

    Matches: (footprint "..." (layer "F.Cu")
    """
    m = re.search(r'\(footprint\s+"[^"]*"\s+\(layer\s+"([^"]+)"', block)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Service-specific README instruction helpers
# ---------------------------------------------------------------------------


def _jlcpcb_instructions(pkg: ManufacturingPackage) -> list[str]:
    zip_name = pkg.gerber_zip.name if pkg.gerber_zip else "gerbers_jlcpcb.zip"
    lines = [
        "## JLCPCB Upload Instructions",
        "",
        "### Step 1 — Basic PCB Order",
        "1. Go to https://jlcpcb.com/",
        "2. Click **Order Now**",
        f"3. Upload `{zip_name}`",
        "4. Configure board specs (layers, PCB color, surface finish, thickness)",
        "5. Review the preview and confirm",
        "",
    ]
    if pkg.bom_csv and pkg.cpl_csv:
        bom_name = pkg.bom_csv.name
        cpl_name = pkg.cpl_csv.name
        lines += [
            "### Step 2 — Add SMT Assembly (PCBA)",
            "1. After uploading Gerbers, enable **PCB Assembly**",
            "2. Select **Assemble top side** (or bottom side as needed)",
            "3. Click **Confirm** to proceed to the BOM upload step",
            f"4. Upload `{bom_name}` as the Bill of Materials",
            f"5. Upload `{cpl_name}` as the Component Placement List",
            "6. JLCPCB will match components by LCSC Part # — review the match list",
            "7. Components with a blank LCSC Part # must be sourced manually",
            "   — search https://lcsc.com/ by MPN to find the part number",
            "8. Confirm the assembly preview and place the order",
            "",
            "### LCSC Part Number Notes",
            "- The `LCSC Part #` column is pre-filled for common components",
            "- Blank entries mean the component is not in the LCSC catalogue",
            "  or could not be automatically identified",
            "- Double-check all part numbers before ordering",
            "",
        ]
    return lines


def _seeed_instructions(pkg: ManufacturingPackage) -> list[str]:
    zip_name = pkg.gerber_zip.name if pkg.gerber_zip else "gerbers_seeed.zip"
    return [
        "## Seeed Fusion PCB Upload Instructions",
        "",
        "1. Go to https://www.seeedstudio.com/fusion_pcb.html",
        "2. Click **Upload Gerber Files**",
        f"3. Upload `{zip_name}`",
        "4. Configure board options (layers, color, quantity)",
        "5. For PCBA: use the Seeed Fusion PCBA portal separately",
        f"   — upload `{pkg.bom_csv.name}`" if pkg.bom_csv else "",
        "",
    ]


def _pcbway_instructions(pkg: ManufacturingPackage) -> list[str]:
    zip_name = pkg.gerber_zip.name if pkg.gerber_zip else "gerbers_pcbway.zip"
    return [
        "## PCBWay Upload Instructions",
        "",
        "1. Go to https://www.pcbway.com/",
        "2. Click **Quick Order PCB**",
        f"3. Upload `{zip_name}`",
        "4. Configure specs and submit for quote",
        "5. For assembly: use PCBWay's PCB+Assembly quote option",
        f"   — upload `{pkg.bom_csv.name}` and `{pkg.cpl_csv.name}`"
        if (pkg.bom_csv and pkg.cpl_csv)
        else "",
        "",
    ]


def _generic_instructions(pkg: ManufacturingPackage) -> list[str]:
    zip_name = pkg.gerber_zip.name if pkg.gerber_zip else "gerbers_generic.zip"
    lines = [
        "## Upload Instructions (Generic)",
        "",
        f"1. Upload `{zip_name}` to your PCB fab (RS-274X format, standard KiCad naming)",
        "2. Configure board specs as required by your fab",
    ]
    if pkg.bom_csv:
        lines.append(f"3. Use `{pkg.bom_csv.name}` for component sourcing")
    if pkg.cpl_csv:
        lines.append(
            f"4. Use `{pkg.cpl_csv.name}` for SMT assembly placement (Pick & Place)"
        )
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# ManufacturingExporter
# ---------------------------------------------------------------------------


class ManufacturingExporter:
    """Packages PCB manufacturing files for upload to fab services.

    Reads the output of PcbPipeline (Gerbers, .kicad_pcb, BOM from HIR) and
    produces a service-specific order package in the given output directory.

    Usage::

        from boardsmith_hw.manufacturing_exporter import ManufacturingExporter

        exporter = ManufacturingExporter()
        pkg = exporter.export(
            service="jlcpcb",
            pcb_result=result,      # PcbResult from PcbPipeline.run()
            hir_dict=hir_dict,
            out_dir=Path("./output/manufacturing/jlcpcb"),
        )
        print(f"Gerber ZIP: {pkg.gerber_zip}")
        print(f"BOM CSV:    {pkg.bom_csv}")
        print(f"CPL CSV:    {pkg.cpl_csv}")
    """

    SUPPORTED_SERVICES: tuple[str, ...] = ("jlcpcb", "seeed", "pcbway", "generic")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export(
        self,
        service: str,
        pcb_result: "PcbResult",
        hir_dict: dict[str, Any],
        out_dir: Path,
    ) -> ManufacturingPackage:
        """Create a complete fab-ready package for the given service.

        Args:
            service:    Target fab service: "jlcpcb" | "seeed" | "pcbway" | "generic".
            pcb_result: Output of PcbPipeline.run().
            hir_dict:   HIR as a plain dict (used for BOM extraction).
            out_dir:    Directory where all output files are written.

        Returns:
            ManufacturingPackage with paths to all generated files.
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        warnings: list[str] = []
        pkg = ManufacturingPackage(
            service=service,
            out_dir=out_dir,
            gerber_zip=None,
            bom_csv=None,
            cpl_csv=None,
            readme=None,
        )

        # ------------------------------------------------------------------
        # 1. Gerber ZIP
        # ------------------------------------------------------------------
        if pcb_result.gerber_dir and pcb_result.gerber_dir.exists():
            stem = pcb_result.pcb_path.stem if pcb_result.pcb_path else "pcb"
            zip_bytes = self.package_gerbers_zip(pcb_result.gerber_dir, stem, service)
            zip_path = out_dir / f"gerbers_{service}.zip"
            zip_path.write_bytes(zip_bytes)
            pkg.gerber_zip = zip_path
            log.info("Gerber ZIP written to %s", zip_path)
            if not pcb_result.real_gerbers:
                warnings.append(
                    "Gerbers are placeholder stubs — install kicad-cli and re-run "
                    "`boardsmith pcb` to generate real, manufacturable Gerber files"
                )
        else:
            warnings.append("No gerber_dir found — Gerber ZIP skipped. Run `boardsmith pcb` first.")

        # ------------------------------------------------------------------
        # 2. BOM CSV
        # ------------------------------------------------------------------
        bom_entries: list[dict[str, Any]] = hir_dict.get("bom", [])
        footprints: dict[str, str] = pcb_result.footprints or {}
        pkg.component_count = len(bom_entries)

        if bom_entries:
            if service == "jlcpcb":
                bom_text = self.build_jlcpcb_bom(bom_entries, footprints)
            else:
                bom_text = self.build_generic_bom(bom_entries, footprints)
            bom_path = out_dir / f"bom_{service}.csv"
            bom_path.write_text(bom_text, encoding="utf-8")
            pkg.bom_csv = bom_path
            log.info("BOM CSV written to %s (%d entries)", bom_path, len(bom_entries))
            # Phase 25.2: LCSC coverage tracking
            pkg.lcsc_coverage_pct, pkg.missing_lcsc = self.compute_lcsc_coverage(bom_entries)
            if pkg.lcsc_coverage_pct < 80.0 and service == "jlcpcb":
                warnings.append(
                    f"LCSC coverage is only {pkg.lcsc_coverage_pct:.0f}% "
                    f"({len(pkg.missing_lcsc)} MPNs missing LCSC numbers: "
                    f"{', '.join(pkg.missing_lcsc[:5])}"
                    + (f", +{len(pkg.missing_lcsc) - 5} more" if len(pkg.missing_lcsc) > 5 else "")
                    + "). Search https://lcsc.com/ to fill in missing part numbers."
                )
        else:
            warnings.append("No BOM entries in HIR — BOM CSV skipped")

        # ------------------------------------------------------------------
        # 3. CPL CSV (from .kicad_pcb)
        # ------------------------------------------------------------------
        if pcb_result.pcb_path and pcb_result.pcb_path.exists():
            placements = self.parse_cpl_from_pcb(pcb_result.pcb_path)
            pkg.placements_found = len(placements)
            if placements:
                cpl_text = self.build_cpl_csv(placements)
                cpl_path = out_dir / f"cpl_{service}.csv"
                cpl_path.write_text(cpl_text, encoding="utf-8")
                pkg.cpl_csv = cpl_path
                log.info("CPL CSV written to %s (%d placements)", cpl_path, len(placements))
            else:
                warnings.append(
                    "No footprint placements found in .kicad_pcb — CPL skipped"
                )
        else:
            warnings.append("No .kicad_pcb file found — CPL skipped. Run `boardsmith pcb` first.")

        # ------------------------------------------------------------------
        # 4. README
        # ------------------------------------------------------------------
        readme_text = self._make_readme(service, pkg, pcb_result)
        readme_path = out_dir / f"README_{service}.md"
        readme_path.write_text(readme_text, encoding="utf-8")
        pkg.readme = readme_path

        pkg.warnings = warnings
        log.info(
            "Manufacturing export complete: service=%s dir=%s components=%d placements=%d",
            service,
            out_dir,
            pkg.component_count,
            pkg.placements_found,
        )
        return pkg

    # ------------------------------------------------------------------
    # CPL parsing
    # ------------------------------------------------------------------

    def parse_cpl_from_pcb(self, pcb_path: Path) -> list[ComponentPlacement]:
        """Extract component placement data from a .kicad_pcb S-expression file.

        Uses a depth-counting block splitter — no full S-expression parser needed.
        Works with both real kicad-cli PCBs and PcbLayoutEngine-generated stubs.

        Args:
            pcb_path: Path to the .kicad_pcb file.

        Returns:
            List of ComponentPlacement, one per footprint found.
        """
        text = pcb_path.read_text(encoding="utf-8", errors="replace")
        placements: list[ComponentPlacement] = []

        for block in _split_footprint_blocks(text):
            ref = _extract_reference(block)
            at_x, at_y, at_rot = _extract_at(block)
            layer_raw = _extract_layer(block)

            if ref is None or at_x is None:
                continue

            layer = "Top" if (layer_raw and "F.Cu" in layer_raw) else "Bottom"
            placements.append(
                ComponentPlacement(
                    designator=ref,
                    mid_x_mm=at_x,
                    mid_y_mm=at_y,
                    layer=layer,
                    rotation=at_rot,
                )
            )

        return placements

    # ------------------------------------------------------------------
    # BOM generation
    # ------------------------------------------------------------------

    def build_jlcpcb_bom(
        self,
        bom_entries: list[dict[str, Any]],
        footprints: dict[str, str],
    ) -> str:
        """Generate a JLCPCB-format BOM CSV with component grouping.

        Phase 25.1: Components with the same MPN + footprint are consolidated
        into a single row with comma-separated designators and summed quantities.
        JLCPCB requires this format for PCBA orders.

        Columns: Comment, Designator, Footprint, LCSC Part #

        Args:
            bom_entries: List of HIR BOM dicts (component_id, mpn, description, qty).
            footprints:  {comp_id: kicad_footprint_string} from PcbResult.footprints.

        Returns:
            CSV text (UTF-8, comma-delimited).
        """
        # Phase 25.1: Group by (mpn, footprint) for JLCPCB-compatible BOM
        # Key: (mpn, fp_name) → {"description", "lcsc", "designators": [], "qty": int}
        groups: dict[tuple[str, str], dict[str, Any]] = {}

        for entry in bom_entries:
            comp_id = entry.get("component_id", "")
            mpn = entry.get("mpn", "")
            description = entry.get("description", mpn or comp_id)
            qty = int(entry.get("qty", 1))

            fp_raw = footprints.get(comp_id, "")
            fp_name = fp_raw.split(":")[-1] if ":" in fp_raw else fp_raw
            lcsc = self._lookup_lcsc(mpn)

            key = (mpn or comp_id, fp_name)
            if key not in groups:
                groups[key] = {
                    "description": description,
                    "fp_name": fp_name,
                    "lcsc": lcsc,
                    "designators": [],
                    "qty": 0,
                    "mpn": mpn,
                }
            groups[key]["designators"].append(comp_id)
            groups[key]["qty"] += qty

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])

        for group in groups.values():
            designator_str = ", ".join(group["designators"])
            writer.writerow([
                group["description"],
                designator_str,
                group["fp_name"],
                group["lcsc"],
            ])

        return buf.getvalue()

    def compute_lcsc_coverage(
        self,
        bom_entries: list[dict[str, Any]],
    ) -> tuple[float, list[str]]:
        """Compute LCSC part number coverage for a BOM.

        Phase 25.2: Returns (coverage_pct, missing_mpns) where coverage_pct is
        the percentage of unique MPNs that have an LCSC number (0.0–100.0).
        missing_mpns is a sorted list of MPNs without LCSC numbers.

        Args:
            bom_entries: List of HIR BOM dicts.

        Returns:
            (coverage_pct, missing_mpns) tuple.
        """
        if not bom_entries:
            return (100.0, [])

        unique_mpns = {e.get("mpn", "") for e in bom_entries if e.get("mpn")}
        if not unique_mpns:
            return (0.0, [])

        missing: list[str] = sorted(
            mpn for mpn in unique_mpns if not self._lookup_lcsc(mpn)
        )
        covered = len(unique_mpns) - len(missing)
        pct = 100.0 * covered / len(unique_mpns)
        return (pct, missing)

    def build_generic_bom(
        self,
        bom_entries: list[dict[str, Any]],
        footprints: dict[str, str],
    ) -> str:
        """Generate a generic BOM CSV suitable for Seeed Fusion, PCBWay, or manual ordering.

        Columns: Line, MPN, Manufacturer, Description, Qty, Footprint, Reference

        Args:
            bom_entries: List of HIR BOM dicts.
            footprints:  {comp_id: kicad_footprint_string} from PcbResult.footprints.

        Returns:
            CSV text (UTF-8, comma-delimited).
        """
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["Line", "MPN", "Manufacturer", "Description", "Qty", "Footprint", "Reference"]
        )

        for i, entry in enumerate(bom_entries, start=1):
            comp_id = entry.get("component_id", "")
            mpn = entry.get("mpn", "")
            manufacturer = entry.get("manufacturer", "")
            description = entry.get("description", mpn or comp_id)
            qty = int(entry.get("qty", 1))

            fp_raw = footprints.get(comp_id, "")
            fp_name = fp_raw.split(":")[-1] if ":" in fp_raw else fp_raw

            line_id = entry.get("line_id", str(i))
            writer.writerow([line_id, mpn, manufacturer, description, qty, fp_name, comp_id])

        return buf.getvalue()

    # ------------------------------------------------------------------
    # CPL CSV
    # ------------------------------------------------------------------

    def build_cpl_csv(self, placements: list[ComponentPlacement]) -> str:
        """Generate a CPL (Component Placement List) CSV for SMT assembly ordering.

        Columns (JLCPCB format): Designator, Mid X, Mid Y, Layer, Rotation
        Coordinates are in mm. Rotation is in degrees.

        Args:
            placements: List of ComponentPlacement from parse_cpl_from_pcb().

        Returns:
            CSV text (UTF-8, comma-delimited).
        """
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])

        for p in placements:
            writer.writerow(
                [
                    p.designator,
                    f"{p.mid_x_mm:.4f}mm",
                    f"{p.mid_y_mm:.4f}mm",
                    p.layer,
                    f"{p.rotation:.2f}",
                ]
            )

        return buf.getvalue()

    # ------------------------------------------------------------------
    # Gerber ZIP
    # ------------------------------------------------------------------

    def package_gerbers_zip(
        self,
        gerber_dir: Path,
        stem: str,
        service: str,
    ) -> bytes:
        """Package all Gerber and drill files into a ZIP ready for fab upload.

        Collects all *.gbr and *.drl files from gerber_dir.
        Files are stored at the ZIP root (no subdirectory) — this is the
        required format for JLCPCB, Seeed Fusion, and PCBWay.

        KiCad layer naming ({stem}-F_Cu.gbr etc.) is accepted by all major fabs
        without renaming.

        Args:
            gerber_dir: Directory containing *.gbr and *.drl files.
            stem:       PCB stem name (used for log messages only).
            service:    Target service (reserved for future per-service renaming).

        Returns:
            Raw ZIP bytes.
        """
        buf = io.BytesIO()
        gerber_files = sorted(
            list(gerber_dir.glob("*.gbr")) + list(gerber_dir.glob("*.drl"))
        )

        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for f in gerber_files:
                zf.write(f, arcname=f.name)

        if not gerber_files:
            log.warning("No Gerber/drill files found in %s", gerber_dir)
        else:
            log.debug(
                "Gerber ZIP: %d files from %s (stem=%s)", len(gerber_files), gerber_dir, stem
            )

        return buf.getvalue()

    # ------------------------------------------------------------------
    # README
    # ------------------------------------------------------------------

    def _make_readme(
        self,
        service: str,
        pkg: ManufacturingPackage,
        pcb_result: "PcbResult",
    ) -> str:
        """Generate a Markdown README with fab-specific upload instructions."""
        lines: list[str] = [f"# Manufacturing Files — {service.upper()}", ""]

        # File inventory
        lines += ["## Generated Files", ""]
        if pkg.gerber_zip:
            lines.append(f"- `{pkg.gerber_zip.name}` — Gerber + drill files (upload this to the fab)")
        if pkg.bom_csv:
            lines.append(f"- `{pkg.bom_csv.name}` — Bill of Materials")
        if pkg.cpl_csv:
            lines.append(f"- `{pkg.cpl_csv.name}` — Component Placement List (Pick & Place)")
        lines.append("")

        # PCB status
        lines += ["## PCB Status", ""]
        routed_str = (
            "Routed" if pcb_result.routed else f"Unrouted (router: {pcb_result.router_method})"
        )
        gerber_str = (
            "Real Gerbers (generated by kicad-cli)"
            if pcb_result.real_gerbers
            else "Stub placeholders — REPLACE with real Gerbers before ordering"
        )
        lines += [
            f"- Routing: {routed_str}",
            f"- Gerbers: {gerber_str}",
            "",
        ]

        if not pcb_result.real_gerbers:
            lines += [
                "> **WARNING:** The Gerber files in this package are stubs generated without",
                "> kicad-cli. They cannot be used for actual PCB manufacturing.",
                "> Install kicad-cli and re-run `boardsmith pcb` to produce real Gerber files.",
                "",
            ]

        # Service-specific instructions
        if service == "jlcpcb":
            lines += _jlcpcb_instructions(pkg)
        elif service == "seeed":
            lines += _seeed_instructions(pkg)
        elif service == "pcbway":
            lines += _pcbway_instructions(pkg)
        else:
            lines += _generic_instructions(pkg)

        # Warnings section
        if pkg.warnings:
            lines += ["## Warnings", ""]
            for w in pkg.warnings:
                lines.append(f"- {w}")
            lines.append("")

        lines += [
            "---",
            "*Generated by [Boardsmith](https://github.com/boardsmith) ManufacturingExporter*",
            "",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # LCSC lookup
    # ------------------------------------------------------------------

    def _lookup_lcsc(self, mpn: str) -> str:
        """Return the LCSC part number for an MPN, or empty string if unknown."""
        if not mpn:
            return ""
        # Exact match
        if mpn in _LCSC_MAP:
            return _LCSC_MAP[mpn]
        # Case-insensitive match
        mpn_upper = mpn.upper()
        for key, lcsc in _LCSC_MAP.items():
            if key.upper() == mpn_upper:
                return lcsc
        return ""
