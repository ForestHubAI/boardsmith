# SPDX-License-Identifier: AGPL-3.0-or-later
"""JLCPCB Parts Availability Validator.

Checks whether BOM components are available in JLCPCB's SMT assembly catalog
(LCSC part numbers), classifies parts as Basic/Extended/Not-Found, and
estimates assembly surcharges.

JLCPCB part tiers:
  Basic:    Free to use in SMT assembly; in-stock guaranteed.
  Extended: $3 USD per part type setup fee; usually available.
  Not found: Must be hand-soldered or sourced separately.

Usage::

    from boardsmith_hw.jlcpcb_validator import JLCPCBValidator
    validator = JLCPCBValidator()
    report = validator.validate(hir_dict)
    print(report.summary())
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# JLCPCB parts catalog (subset of common IoT/embedded components)
# Format: MPN (upper) → (lcsc_part, tier, description, package)
# Tiers: "basic" | "extended" | "not_found"
# ---------------------------------------------------------------------------

_JLCPCB_CATALOG: dict[str, dict] = {
    # ── Microcontrollers ────────────────────────────────────────────────────
    "ESP32-WROOM-32":      {"lcsc": "C701341", "tier": "extended",
                            "desc": "ESP32 Wi-Fi+BT module", "pkg": "SMD-38P"},
    "ESP32-WROOM-32D":     {"lcsc": "C473012", "tier": "extended",
                            "desc": "ESP32 Wi-Fi+BT module 4MB", "pkg": "SMD-38P"},
    "ESP32-C3-MINI-1":     {"lcsc": "C2934560", "tier": "extended",
                            "desc": "ESP32-C3 Wi-Fi+BLE module", "pkg": "SMD-52P"},
    "RP2040":              {"lcsc": "C2040",    "tier": "extended",
                            "desc": "Raspberry Pi RP2040 MCU", "pkg": "QFN-56"},
    "STM32F103C8T6":       {"lcsc": "C8734",    "tier": "extended",
                            "desc": "STM32F1 ARM Cortex-M3", "pkg": "LQFP-48"},
    "STM32F401CCU6":       {"lcsc": "C188665",  "tier": "extended",
                            "desc": "STM32F4 ARM Cortex-M4", "pkg": "UFQFPN-48"},
    "STM32G031K8T6":       {"lcsc": "C784702",  "tier": "extended",
                            "desc": "STM32G0 ARM Cortex-M0+", "pkg": "LQFP-32"},
    "NRF52840-QIAA":       {"lcsc": "C190794",  "tier": "extended",
                            "desc": "Nordic nRF52840 BLE SoC", "pkg": "AAQFN-73"},
    "ATTINY85-20SU":       {"lcsc": "C89852",   "tier": "extended",
                            "desc": "Atmel ATtiny85 8-bit AVR", "pkg": "SOIC-8"},
    "ATMEGA328P-AU":       {"lcsc": "C14877",   "tier": "extended",
                            "desc": "Atmel ATmega328P AVR", "pkg": "TQFP-32"},

    # ── Sensors ─────────────────────────────────────────────────────────────
    "BME280":              {"lcsc": "C92489",   "tier": "extended",
                            "desc": "Temp/humidity/pressure sensor", "pkg": "LGA-8"},
    "BME680":              {"lcsc": "C119417",  "tier": "extended",
                            "desc": "Air quality sensor", "pkg": "LGA-8"},
    "BMP280":              {"lcsc": "C74498",   "tier": "extended",
                            "desc": "Pressure/temperature sensor", "pkg": "LGA-8"},
    "MPU-6050":            {"lcsc": "C24112",   "tier": "extended",
                            "desc": "6-axis IMU (accel+gyro)", "pkg": "QFN-24"},
    "ICM-42688-P":         {"lcsc": "C2655030", "tier": "extended",
                            "desc": "6-axis IMU high performance", "pkg": "LGA-14"},
    "SHT31-DIS-B2.5KS":   {"lcsc": "C512136",  "tier": "extended",
                            "desc": "Temp+humidity sensor", "pkg": "DFN-8"},
    "SCD41":               {"lcsc": "C2960089", "tier": "extended",
                            "desc": "CO2 + temp + humidity sensor", "pkg": "DFN-8"},
    "SGP30":               {"lcsc": "C2636871", "tier": "extended",
                            "desc": "TVOC/eCO2 gas sensor", "pkg": "DFN-6"},
    "VL53L0X":             {"lcsc": "C91538",   "tier": "extended",
                            "desc": "ToF distance sensor", "pkg": "LGA-12"},
    "AS5600":              {"lcsc": "C2662290", "tier": "extended",
                            "desc": "Magnetic angle sensor 12-bit", "pkg": "SOIC-8"},
    "MAX31855KASA+":       {"lcsc": "C5156854", "tier": "extended",
                            "desc": "Thermocouple-to-digital K-type", "pkg": "SOIC-8"},

    # ── RF / Wireless ────────────────────────────────────────────────────────
    "SX1276":              {"lcsc": "C13029",   "tier": "extended",
                            "desc": "LoRa transceiver 868/915MHz", "pkg": "QFN-28"},
    "SX1262":              {"lcsc": "C2687054", "tier": "extended",
                            "desc": "LoRa transceiver", "pkg": "QFN-24"},
    "CC1101":              {"lcsc": "C18400",   "tier": "extended",
                            "desc": "Sub-1GHz RF transceiver", "pkg": "QLP-20"},
    "NRF24L01+":           {"lcsc": "C8690",    "tier": "extended",
                            "desc": "2.4GHz RF transceiver", "pkg": "QFN-20"},

    # ── Power Management ────────────────────────────────────────────────────
    "AMS1117-3.3":         {"lcsc": "C6186",    "tier": "basic",
                            "desc": "LDO 3.3V 800mA", "pkg": "SOT-223"},
    "AMS1117-5.0":         {"lcsc": "C6187",    "tier": "basic",
                            "desc": "LDO 5V 800mA", "pkg": "SOT-223"},
    "AP2112K-3.3TRG1":     {"lcsc": "C51118",   "tier": "basic",
                            "desc": "LDO 3.3V 600mA CMOS", "pkg": "SOT-23-5"},
    "MCP1700-3302E":       {"lcsc": "C6618",    "tier": "extended",
                            "desc": "LDO 3.3V 250mA ultra-low IQ", "pkg": "SOT-23-3"},
    "MCP1700-3302E/TO":    {"lcsc": "C6618",    "tier": "extended",
                            "desc": "LDO 3.3V 250mA ultra-low IQ", "pkg": "SOT-23-3"},
    "MCP73831T-2ATI":      {"lcsc": "C14879",   "tier": "extended",
                            "desc": "Li-Po charger 500mA", "pkg": "SOT-23-5"},
    "TP4056":              {"lcsc": "C16581",   "tier": "basic",
                            "desc": "Li-Po charger 1A", "pkg": "SOP-8"},
    "MT3608":              {"lcsc": "C84818",   "tier": "basic",
                            "desc": "Boost converter 2A 28V", "pkg": "SOT-23-6"},
    "TPS63020DSJR":        {"lcsc": "C133660",  "tier": "extended",
                            "desc": "Buck-boost converter", "pkg": "VSON-14"},
    "IP5306":              {"lcsc": "C181692",  "tier": "basic",
                            "desc": "Li-Po charge/boost 2.1A", "pkg": "SOP-8"},

    # ── Displays / Interfaces ────────────────────────────────────────────────
    "SSD1306":             {"lcsc": "C2040",    "tier": "not_found",
                            "desc": "OLED driver — buy as module", "pkg": "module"},
    "WS2812B":             {"lcsc": "C114586",  "tier": "basic",
                            "desc": "RGB LED (addressable)", "pkg": "5050"},
    "WS2812B-2020":        {"lcsc": "C2976072", "tier": "basic",
                            "desc": "RGB LED (addressable) 2020", "pkg": "2020"},

    # ── Memory ──────────────────────────────────────────────────────────────
    "W25Q128JVSIQ":        {"lcsc": "C97521",   "tier": "basic",
                            "desc": "128Mbit SPI NOR Flash", "pkg": "SOIC-8"},
    "W25Q64JVSSIQ":        {"lcsc": "C179171",  "tier": "basic",
                            "desc": "64Mbit SPI NOR Flash", "pkg": "SOIC-8"},
    "W25Q32JVSSIQ":        {"lcsc": "C179171",  "tier": "basic",
                            "desc": "32Mbit SPI NOR Flash", "pkg": "SOIC-8"},

    # ── Interface ICs ────────────────────────────────────────────────────────
    "TCA9548A":            {"lcsc": "C130026",  "tier": "extended",
                            "desc": "I2C multiplexer 8-channel", "pkg": "SSOP-24"},
    "CH340G":              {"lcsc": "C14267",   "tier": "basic",
                            "desc": "USB-to-UART bridge", "pkg": "SOIC-16"},
    "CH340C":              {"lcsc": "C84681",   "tier": "basic",
                            "desc": "USB-to-UART bridge with crystal", "pkg": "SOP-16"},
    "CP2102":              {"lcsc": "C6568",    "tier": "basic",
                            "desc": "USB-to-UART bridge", "pkg": "QFN-28"},
    "MAX485":              {"lcsc": "C132856",  "tier": "basic",
                            "desc": "RS-485/RS-422 transceiver", "pkg": "SOIC-8"},
    "SN65HVD230DR":        {"lcsc": "C186705",  "tier": "extended",
                            "desc": "CAN bus transceiver", "pkg": "SOIC-8"},

    # ── Passives (common values — always basic) ──────────────────────────────
    "RC0402FR-0710KL":     {"lcsc": "C25744",   "tier": "basic",
                            "desc": "10kΩ 0402 resistor", "pkg": "0402"},
    "RC0402FR-074K7L":     {"lcsc": "C25744",   "tier": "basic",
                            "desc": "4.7kΩ 0402 resistor", "pkg": "0402"},
    "GRM155R61A104KA01D":  {"lcsc": "C52923",   "tier": "basic",
                            "desc": "100nF 0402 cap", "pkg": "0402"},
    "GRM188R61E106KA73D":  {"lcsc": "C45783",   "tier": "basic",
                            "desc": "10µF 0603 cap", "pkg": "0603"},
}

# Extended setup fee per part type (USD)
_EXTENDED_SETUP_FEE_USD = 3.00

# Minimum order quantities / notes
_TIER_NOTES = {
    "basic":     "No setup fee. In-stock at JLCPCB.",
    "extended":  f"${_EXTENDED_SETUP_FEE_USD:.0f} setup fee per part type.",
    "not_found": "Not in JLCPCB catalog — hand-solder or order separately.",
}


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------


@dataclass
class ComponentAvailability:
    """JLCPCB availability for one BOM line item."""

    component_id: str
    mpn: str
    lcsc_part: Optional[str]
    tier: str          # "basic" | "extended" | "not_found"
    description: str
    package: str
    note: str = ""


@dataclass
class JLCPCBReport:
    """Full JLCPCB BOM validation report."""

    items: list[ComponentAvailability] = field(default_factory=list)
    basic_count: int = 0
    extended_count: int = 0
    not_found_count: int = 0
    estimated_setup_fee_usd: float = 0.0

    def summary(self) -> str:
        lines = [
            "JLCPCB SMT Assembly Report",
            f"  Basic parts:    {self.basic_count}  (no fee)",
            f"  Extended parts: {self.extended_count}  "
            f"(${self.estimated_setup_fee_usd:.0f} total setup fee)",
            f"  Not in catalog: {self.not_found_count}  (hand-solder or DNF)",
        ]
        if self.not_found_count:
            not_found = [
                f"    ⚠ {i.component_id} ({i.mpn})"
                for i in self.items if i.tier == "not_found"
            ]
            lines.extend(not_found)
        if self.extended_count:
            ext = [
                f"    $ {i.component_id} ({i.mpn}) — {i.lcsc_part}"
                for i in self.items if i.tier == "extended"
            ]
            lines.extend(ext)
        return "\n".join(lines)

    def to_bom_csv(self) -> str:
        """Return BOM in JLCPCB CPL/BOM CSV format."""
        lines = [
            "Comment,Designator,Footprint,LCSC Part #"
        ]
        for item in self.items:
            lcsc = item.lcsc_part or ""
            lines.append(
                f'"{item.mpn}","{item.component_id}","{item.package}","{lcsc}"'
            )
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class JLCPCBValidator:
    """Validates HIR BOM against JLCPCB SMT parts catalog.

    Usage::

        v = JLCPCBValidator()
        report = v.validate(hir_dict)
        print(report.summary())
    """

    def __init__(self) -> None:
        # Normalised lookup: UPPER(MPN) → catalog entry
        self._catalog = {k.upper(): v for k, v in _JLCPCB_CATALOG.items()}

    def lookup(self, mpn: str) -> Optional[dict]:
        """Look up a part by MPN. Returns catalog entry or None."""
        key = mpn.upper().strip()
        if key in self._catalog:
            return self._catalog[key]
        # Partial match (e.g. "ESP32-WROOM-32" prefix)
        for catalog_key, entry in self._catalog.items():
            if key.startswith(catalog_key) or catalog_key.startswith(key):
                return entry
        return None

    def validate(self, hir: dict) -> JLCPCBReport:
        """Validate all components in an HIR dict.

        Skips power-only and passive components with no MPN.
        """
        report = JLCPCBReport()
        components = hir.get("components", [])

        for comp in components:
            comp_id = comp.get("id", "unknown")
            mpn = comp.get("mpn", "").strip()
            if not mpn:
                continue

            entry = self.lookup(mpn)
            if entry:
                avail = ComponentAvailability(
                    component_id=comp_id,
                    mpn=mpn,
                    lcsc_part=entry["lcsc"],
                    tier=entry["tier"],
                    description=entry["desc"],
                    package=entry["pkg"],
                    note=_TIER_NOTES[entry["tier"]],
                )
            else:
                avail = ComponentAvailability(
                    component_id=comp_id,
                    mpn=mpn,
                    lcsc_part=None,
                    tier="not_found",
                    description="Unknown",
                    package="",
                    note=_TIER_NOTES["not_found"],
                )

            report.items.append(avail)

        # Aggregate counters
        for item in report.items:
            if item.tier == "basic":
                report.basic_count += 1
            elif item.tier == "extended":
                report.extended_count += 1
            else:
                report.not_found_count += 1

        report.estimated_setup_fee_usd = (
            report.extended_count * _EXTENDED_SETUP_FEE_USD
        )
        return report
