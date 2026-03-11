# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reference Design Library — known, working hardware design patterns.

Each reference design captures a validated combination of components, buses
and power topology that has been field-tested. The library is used by the
DesignReviewAgent for similarity matching to boost review confidence.

Usage:
    lib = ReferenceDesignLibrary()
    match, conf = lib.find_closest(hir_dict)
    # match: ReferenceDesign | None
    # conf:  0.0–1.0
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReferenceDesign:
    """A single validated reference design."""

    name: str
    description: str
    mcu_family: str              # "esp32" | "rp2040" | "stm32" | "nrf52"
    bus_types: list[str]         # ["I2C", "SPI", "UART"]
    power_source: str            # "usb5v" | "lipo" | "psu" | "aa_battery"
    components: list[str]        # MPN list
    has_display: bool
    has_rf: bool
    sensor_count: int
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Built-in reference designs (10 common patterns)
# ---------------------------------------------------------------------------

_REFERENCE_DESIGNS: list[ReferenceDesign] = [
    ReferenceDesign(
        name="ESP32 I2C Environmental Station",
        description="ESP32-WROOM-32 with BME280 temp/humidity/pressure sensor over I2C, USB power",
        mcu_family="esp32",
        bus_types=["I2C"],
        power_source="usb5v",
        components=["ESP32-WROOM-32", "BME280", "AMS1117-3.3"],
        has_display=False, has_rf=False, sensor_count=1,
        notes=["I2C pull-ups: 4.7kΩ to 3.3V", "100nF decoupling per IC"],
    ),
    ReferenceDesign(
        name="ESP32 Multi-Sensor OLED Node",
        description="ESP32 with BME280 + SSD1306 OLED display over I2C, USB power",
        mcu_family="esp32",
        bus_types=["I2C"],
        power_source="usb5v",
        components=["ESP32-WROOM-32", "BME280", "SSD1306", "AMS1117-3.3"],
        has_display=True, has_rf=False, sensor_count=1,
        notes=["SSD1306 address: 0x3C", "BME280 address: 0x76"],
    ),
    ReferenceDesign(
        name="ESP32 LoRa IoT Sensor",
        description="ESP32 with SX1276 LoRa transceiver via SPI + BME280 I2C",
        mcu_family="esp32",
        bus_types=["I2C", "SPI"],
        power_source="lipo",
        components=["ESP32-WROOM-32", "SX1276", "BME280", "MCP73831T-2ATI", "AP2112K-3.3TRG1"],
        has_display=False, has_rf=True, sensor_count=1,
        notes=["RF antenna keep-out zone", "LiPo charger MCP73831", "Low-noise LDO for RF"],
    ),
    ReferenceDesign(
        name="RP2040 SPI Flash Data Logger",
        description="RP2040 Pico with W25Q128 SPI flash for data logging, USB power",
        mcu_family="rp2040",
        bus_types=["SPI"],
        power_source="usb5v",
        components=["RP2040", "W25Q128JVSIQ"],
        has_display=False, has_rf=False, sensor_count=0,
        notes=["3.3V from internal LDO", "SPI up to 133 MHz"],
    ),
    ReferenceDesign(
        name="RP2040 Multi-I2C Sensor Array",
        description="RP2040 with BME280 + MPU6050 + SCD41 over I2C",
        mcu_family="rp2040",
        bus_types=["I2C"],
        power_source="usb5v",
        components=["RP2040", "BME280", "MPU6050", "SCD41"],
        has_display=False, has_rf=False, sensor_count=3,
        notes=["TCA9548A mux if address conflicts", "SCD41 needs 5s interval"],
    ),
    ReferenceDesign(
        name="ESP32-C3 BLE Sensor Node",
        description="ESP32-C3 with AHT20 I2C sensor, BLE advertisement, battery powered",
        mcu_family="esp32",
        bus_types=["I2C"],
        power_source="lipo",
        components=["ESP32-C3-MINI-1", "AHT20", "MCP73831T-2ATI", "AP2112K-3.3TRG1"],
        has_display=False, has_rf=True, sensor_count=1,
        notes=["BLE 5.0 built-in", "Deep-sleep for battery life"],
    ),
    ReferenceDesign(
        name="STM32 Industrial Sensor Hub",
        description="STM32F103 with multiple SPI/I2C sensors, PSU powered",
        mcu_family="stm32",
        bus_types=["I2C", "SPI", "UART"],
        power_source="psu",
        components=["STM32F103C8T6", "BME280", "MPU6050"],
        has_display=False, has_rf=False, sensor_count=2,
        notes=["3.3V AMS1117 from 5V", "UART debug port"],
    ),
    ReferenceDesign(
        name="nRF52840 BLE Beacon",
        description="nRF52840 with SHT31 humidity sensor, BLE 5 long-range, coin cell",
        mcu_family="nrf52",
        bus_types=["I2C"],
        power_source="aa_battery",
        components=["nRF52840", "SHT31"],
        has_display=False, has_rf=True, sensor_count=1,
        notes=["Ultra-low power: 3µA sleep", "BLE 5 coded PHY for 1km range"],
    ),
    ReferenceDesign(
        name="ESP32 CO2 Monitor with E-Paper",
        description="ESP32 + SCD41 CO2 sensor + 2.9\" e-paper display, USB or battery",
        mcu_family="esp32",
        bus_types=["I2C", "SPI"],
        power_source="lipo",
        components=["ESP32-WROOM-32", "SCD41", "AMS1117-3.3", "MCP73831T-2ATI"],
        has_display=True, has_rf=False, sensor_count=1,
        notes=["SCD41 5s measurement interval", "E-paper SPI interface", "Deep-sleep between readings"],
    ),
    ReferenceDesign(
        name="Battery-Powered IoT Sensor",
        description="ESP32 ultra-low-power node with BME280, LiPo, fuel gauge",
        mcu_family="esp32",
        bus_types=["I2C"],
        power_source="lipo",
        components=["ESP32-WROOM-32", "BME280", "MCP73831T-2ATI", "MAX17048G+T", "AP2112K-3.3TRG1"],
        has_display=False, has_rf=False, sensor_count=1,
        notes=["MAX17048 fuel gauge for battery %", "MCP73831 charger", "Deep-sleep 10µA"],
    ),
]


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def _hir_to_features(hir_dict: dict[str, Any]) -> dict[str, Any]:
    """Extract a feature vector from a HIR dict for similarity comparison."""
    comps = hir_dict.get("components", [])
    bus_contracts = hir_dict.get("bus_contracts", [])

    # MCU family
    mcu_family = "unknown"
    for c in comps:
        mpn_low = c.get("mpn", "").lower()
        if "esp32" in mpn_low:
            mcu_family = "esp32"
        elif "rp2040" in mpn_low:
            mcu_family = "rp2040"
        elif "stm32" in mpn_low or "f103" in mpn_low:
            mcu_family = "stm32"
        elif "nrf52" in mpn_low:
            mcu_family = "nrf52"

    # Bus types
    bus_types: set[str] = set()
    for bc in bus_contracts:
        bt = bc.get("bus_type", "")
        if bt:
            bus_types.add(bt.upper())

    # Component roles
    mpns = [c.get("mpn", "").lower() for c in comps]
    has_display = any(
        kw in m for m in mpns for kw in ("ssd1306", "epd", "epaper", "e-paper", "lcd")
    )
    has_rf = any(
        kw in m for m in mpns for kw in ("sx1276", "sx1262", "nrf24", "cc1101", "esp", "nrf52", "ble")
    )
    sensor_count = sum(
        1 for c in comps
        if c.get("role", "").lower() in ("sensor", "environmental", "imu", "gas", "optical")
        or c.get("category", "").lower() == "sensor"
    )

    # Power source heuristic
    power_source = "usb5v"
    for c in comps:
        mpn_low = c.get("mpn", "").lower()
        if "mcp73831" in mpn_low or "tp4056" in mpn_low or "ip5306" in mpn_low:
            power_source = "lipo"
            break
        if "mt3608" in mpn_low or "mp2307" in mpn_low:
            power_source = "psu"

    return {
        "mcu_family": mcu_family,
        "bus_types": bus_types,
        "has_display": has_display,
        "has_rf": has_rf,
        "sensor_count": sensor_count,
        "power_source": power_source,
    }


def _similarity(features: dict[str, Any], design: ReferenceDesign) -> float:
    """Compute 0.0–1.0 similarity between feature vector and reference design."""
    score = 0.0

    # MCU family match (weight 0.30)
    if features["mcu_family"] == design.mcu_family:
        score += 0.30

    # Bus type overlap (weight 0.25) — Jaccard on sets
    f_buses = features["bus_types"]
    d_buses = set(design.bus_types)
    if f_buses or d_buses:
        intersection = len(f_buses & d_buses)
        union = len(f_buses | d_buses)
        score += 0.25 * (intersection / union if union else 1.0)

    # Power source (weight 0.20)
    if features["power_source"] == design.power_source:
        score += 0.20

    # Display match (weight 0.10)
    if features["has_display"] == design.has_display:
        score += 0.10

    # RF match (weight 0.10)
    if features["has_rf"] == design.has_rf:
        score += 0.10

    # Sensor count proximity (weight 0.05) — decay for mismatch
    sc_diff = abs(features["sensor_count"] - design.sensor_count)
    score += 0.05 * max(0.0, 1.0 - sc_diff * 0.33)

    return round(score, 3)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ReferenceDesignLibrary:
    """Library of known-good hardware design patterns."""

    def __init__(self, designs: list[ReferenceDesign] | None = None) -> None:
        self._designs = designs if designs is not None else list(_REFERENCE_DESIGNS)

    def find_closest(
        self, hir_dict: dict[str, Any]
    ) -> tuple[ReferenceDesign | None, float]:
        """Return (best_match, confidence) for the given HIR.

        Returns (None, 0.0) when the library is empty.
        """
        if not self._designs:
            return None, 0.0

        features = _hir_to_features(hir_dict)
        best: ReferenceDesign | None = None
        best_score = 0.0

        for design in self._designs:
            s = _similarity(features, design)
            if s > best_score:
                best_score = s
                best = design

        return best, best_score

    def all_designs(self) -> list[ReferenceDesign]:
        """Return all reference designs."""
        return list(self._designs)
