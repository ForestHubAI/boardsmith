# SPDX-License-Identifier: AGPL-3.0-or-later
"""ESP-IDF Header Parser → MCUDeviceProfile pin tables.

Parses ESP-IDF `soc/` C headers to extract GPIO signal mappings, pin
capabilities, and peripheral configurations.

Key source files (ESP-IDF `components/soc/<chip>/include/soc/`):
  - gpio_sig_map.h  — signal index → GPIO number mapping
  - gpio_num.h      — GPIO number enumerations
  - soc_caps.h      — SoC capability macros (number of I2C, SPI, etc.)
  - periph_defs.h   — peripheral definitions

Header format (simplified gpio_sig_map.h):
  #define I2CEXT0_SCL_IN_IDX    17
  #define I2CEXT0_SDA_IN_IDX    18
  #define SPI3_CLK_IN_IDX       19
  ...
  #define GPIO_PIN_MUX_REG_LIST { IO_MUX_GPIO0_REG, IO_MUX_GPIO1_REG, ... }

Header format (soc_caps.h):
  #define SOC_GPIO_PIN_COUNT       49
  #define SOC_I2C_NUM              2
  #define SOC_SPI_PERIPH_NUM       3
  #define SOC_UART_NUM             3

Usage:
  profile = parse_espidf_headers("/path/to/esp-idf/components/soc/esp32s3/")
  # → MCUDeviceProfile with full GPIO signal map
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from shared.knowledge.mcu_profile_schema import (
    AltFunction,
    AttributeProvenance,
    BootConfig,
    BootModePin,
    ClockConfig,
    ClockSource,
    ClockSourceType,
    MCUDeviceProfile,
    MCUIdentity,
    MCUPinout,
    MCUPowerTree,
    PinDefinition,
    PinElectrical,
    PinMap,
    PinType,
    PowerDomain,
    DecouplingRule,
    CapSpec,
    ReservedPin,
    ResetCircuit,
    TemperatureGrade,
    PeripheralPatterns,
    I2CPattern,
    SPIPattern,
    UARTPattern,
    USBPattern,
    RFPattern,
    IOElectricalRules,
    FirmwareBinding,
    BusConfig,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Regex patterns for ESP-IDF header parsing
# ---------------------------------------------------------------------------

# Signal mapping: #define I2CEXT0_SCL_IN_IDX  17
_SIGNAL_DEFINE_RE = re.compile(
    r"^\s*#define\s+(\w+?)_(IN|OUT)_IDX\s+(\d+)",
    re.MULTILINE,
)

# SoC capabilities: #define SOC_GPIO_PIN_COUNT  49
_SOC_CAP_RE = re.compile(
    r"^\s*#define\s+(SOC_\w+)\s+(\d+)",
    re.MULTILINE,
)

# GPIO pin count
_GPIO_COUNT_RE = re.compile(
    r"^\s*#define\s+(?:SOC_GPIO_PIN_COUNT|GPIO_PIN_COUNT)\s+(\d+)",
    re.MULTILINE,
)

# GPIO pin MUX register (indicates available GPIOs)
_GPIO_NUM_RE = re.compile(
    r"^\s*GPIO_NUM_(\d+)\s*=\s*(\d+)",
    re.MULTILINE,
)

# Reserved GPIO pins (used for flash/PSRAM)
_RESERVED_PIN_RE = re.compile(
    r"//.*(?:flash|psram|spi_flash|SPIRAM|reserved).*GPIO\s*(\d+)",
    re.IGNORECASE | re.MULTILINE,
)

# Strapping/boot pins
_STRAP_PIN_RE = re.compile(
    r"//.*(?:strapping|boot|strap).*GPIO\s*(\d+)",
    re.IGNORECASE | re.MULTILINE,
)

# Peripheral signal name patterns
_I2C_SIG_RE = re.compile(r"^I2C(?:EXT)?(\d+)_(SCL|SDA|SCL_IN|SDA_IN)$", re.IGNORECASE)
_SPI_SIG_RE = re.compile(r"^(?:F?SPI|SPI(\d+))_(CLK|MISO|MOSI|CS\d*|HD|WP|D\d+)$", re.IGNORECASE)
_UART_SIG_RE = re.compile(r"^U(\d+)?(TXD|RXD|CTS|RTS|TX|RX)$", re.IGNORECASE)
_USB_SIG_RE = re.compile(r"^USB_(?:SERIAL_JTAG_)?(DP|DM|D_P|D_N)$", re.IGNORECASE)
_PWM_SIG_RE = re.compile(r"^(?:LEDC|PWM\d*)_(HS|LS)?_?SIG", re.IGNORECASE)
_I2S_SIG_RE = re.compile(r"^I2S\d*_(DATA|WS|BCK|CLK|MCLK)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Intermediate data structures
# ---------------------------------------------------------------------------

@dataclass
class ESPSignalMap:
    """Parsed signal→GPIO mapping from ESP-IDF headers."""
    signal_name: str
    direction: str  # "IN" or "OUT"
    signal_index: int


@dataclass
class ESPParseResult:
    """Intermediate parse result from ESP-IDF headers."""
    chip_name: str = ""
    gpio_count: int = 0
    signals: list[ESPSignalMap] = field(default_factory=list)
    soc_caps: dict[str, int] = field(default_factory=dict)
    reserved_gpios: set[int] = field(default_factory=set)
    strap_gpios: set[int] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Header file parsers
# ---------------------------------------------------------------------------

def _parse_gpio_sig_map(content: str) -> list[ESPSignalMap]:
    """Parse gpio_sig_map.h for signal index definitions."""
    signals: list[ESPSignalMap] = []
    for match in _SIGNAL_DEFINE_RE.finditer(content):
        sig_name = match.group(1)
        direction = match.group(2)
        idx = int(match.group(3))
        signals.append(ESPSignalMap(
            signal_name=sig_name,
            direction=direction,
            signal_index=idx,
        ))
    return signals


def _parse_soc_caps(content: str) -> dict[str, int]:
    """Parse soc_caps.h for SoC capability macros."""
    caps: dict[str, int] = {}
    for match in _SOC_CAP_RE.finditer(content):
        caps[match.group(1)] = int(match.group(2))
    return caps


def _parse_gpio_count(content: str) -> int:
    """Extract total GPIO pin count."""
    m = _GPIO_COUNT_RE.search(content)
    if m:
        return int(m.group(1))
    return 0


def _parse_reserved_pins(content: str) -> set[int]:
    """Extract GPIO numbers marked as reserved (flash/PSRAM)."""
    reserved: set[int] = set()
    for m in _RESERVED_PIN_RE.finditer(content):
        reserved.add(int(m.group(1)))
    return reserved


def _parse_strap_pins(content: str) -> set[int]:
    """Extract GPIO numbers used as strapping/boot pins."""
    straps: set[int] = set()
    for m in _STRAP_PIN_RE.finditer(content):
        straps.add(int(m.group(1)))
    return straps


# ---------------------------------------------------------------------------
# Signal → AltFunction classification
# ---------------------------------------------------------------------------

def _signal_to_function_name(sig: ESPSignalMap) -> str | None:
    """Classify an ESP signal into a standard alt function name.

    Returns None if the signal is internal/not useful for pin mapping.
    """
    name = sig.signal_name.upper()

    # Filter out internal signals
    if any(x in name for x in ("_PAD_", "_LOOPBACK", "_DIRECT", "GPIO_")):
        return None

    # I2C
    m = _I2C_SIG_RE.match(name)
    if m:
        bus_num = m.group(1) or "0"
        signal = m.group(2).replace("_IN", "").replace("_OUT", "")
        return f"I2C{bus_num}_{signal}"

    # SPI
    m = _SPI_SIG_RE.match(name)
    if m:
        bus_num = m.group(1) or ""
        signal = m.group(2)
        return f"SPI{bus_num}_{signal}"

    # UART
    m = _UART_SIG_RE.match(name)
    if m:
        bus_num = m.group(1) or "0"
        signal = m.group(2).upper()
        if signal in ("TXD", "TX"):
            signal = "TX"
        elif signal in ("RXD", "RX"):
            signal = "RX"
        return f"UART{bus_num}_{signal}"

    # USB
    m = _USB_SIG_RE.match(name)
    if m:
        signal = m.group(1).upper()
        if "P" in signal:
            return "USB_DP"
        return "USB_DM"

    # Keep other signals as-is (timer, PWM, I2S, etc.)
    return name


# ---------------------------------------------------------------------------
# Parse from headers or from string content
# ---------------------------------------------------------------------------

def _build_pin_definitions_from_signals(
    parsed: ESPParseResult,
) -> list[PinDefinition]:
    """Build PinDefinition list from parsed ESP-IDF data."""
    gpio_count = parsed.gpio_count or 49  # ESP32-S3 default

    # Collect alt functions per GPIO (from signal map, signals are routable via matrix)
    # ESP32 uses a GPIO matrix — any signal can go to (almost) any pin.
    # We track which signals exist for the chip, not per-pin.

    # Group unique function names
    function_names: set[str] = set()
    for sig in parsed.signals:
        fn = _signal_to_function_name(sig)
        if fn:
            function_names.add(fn)

    pins: list[PinDefinition] = []
    for gpio_num in range(gpio_count):
        pin_name = f"GPIO{gpio_num}"

        # Determine pin type
        if gpio_num in parsed.reserved_gpios:
            pin_type = PinType.gpio  # Still GPIO, but reserved
        elif gpio_num in parsed.strap_gpios:
            pin_type = PinType.boot
        else:
            pin_type = PinType.gpio

        # ESP32 GPIO electrical characteristics
        electrical = PinElectrical(
            max_source_ma=40,
            max_sink_ma=28,
            is_5v_tolerant=False,
            has_internal_pullup=True,
            has_internal_pulldown=True,
            pullup_value_ohm=45000,  # ~45kΩ typical
        )

        # On ESP32, GPIO matrix means any signal can route to any valid GPIO
        # But we mark specific alt functions for known signal capabilities
        alt_functions: list[AltFunction] = []
        # ADC channels are pin-specific
        if gpio_num <= 20:
            alt_functions.append(AltFunction(
                function=f"ADC1_CH{gpio_num}" if gpio_num <= 10 else f"ADC2_CH{gpio_num - 11}",
            ))

        pins.append(PinDefinition(
            pin_name=pin_name,
            pin_number=str(gpio_num),
            pin_type=pin_type,
            boot_strap=gpio_num in parsed.strap_gpios,
            electrical=electrical,
            alt_functions=alt_functions,
        ))

    return pins


def _detect_chip_variant(content: str, soc_caps: dict[str, int]) -> str:
    """Try to detect ESP32 variant from header content."""
    if "esp32s3" in content.lower() or soc_caps.get("SOC_WIFI_SUPPORTED", 0):
        gpio_count = soc_caps.get("SOC_GPIO_PIN_COUNT", 0)
        if gpio_count >= 49:
            return "ESP32-S3"
        elif gpio_count >= 22:
            return "ESP32-C3"
    if "esp32c3" in content.lower():
        return "ESP32-C3"
    if "esp32s2" in content.lower():
        return "ESP32-S2"
    return "ESP32"


# ---------------------------------------------------------------------------
# ESP32 default knowledge (used when headers are incomplete)
# ---------------------------------------------------------------------------

# Well-known reserved GPIOs per chip variant
_ESP32S3_RESERVED = {26, 27, 28, 29, 30, 31, 32}  # PSRAM/Flash
_ESP32S3_STRAPS = {0, 3, 45, 46}  # Boot strapping pins

_ESP32_RESERVED = {6, 7, 8, 9, 10, 11}  # SPI Flash
_ESP32_STRAPS = {0, 2, 5, 12, 15}  # Boot strapping


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_espidf_headers(soc_dir: str | Path) -> MCUDeviceProfile:
    """Parse ESP-IDF soc/ headers directory into MCUDeviceProfile.

    Args:
        soc_dir: Path to ESP-IDF `components/soc/<chip>/include/soc/` directory

    Returns:
        MCUDeviceProfile with parsed pin model and capabilities
    """
    soc_path = Path(soc_dir)
    if not soc_path.exists():
        raise FileNotFoundError(f"ESP-IDF soc directory not found: {soc_path}")

    parsed = ESPParseResult()

    # Parse available header files
    sig_map_file = soc_path / "gpio_sig_map.h"
    if sig_map_file.exists():
        content = sig_map_file.read_text()
        parsed.signals = _parse_gpio_sig_map(content)

    caps_file = soc_path / "soc_caps.h"
    if caps_file.exists():
        content = caps_file.read_text()
        parsed.soc_caps = _parse_soc_caps(content)
        parsed.gpio_count = parsed.soc_caps.get("SOC_GPIO_PIN_COUNT", 0)

    # Read all header content for reserved/strap detection
    all_content = ""
    for hfile in soc_path.glob("*.h"):
        all_content += hfile.read_text()

    parsed.reserved_gpios = _parse_reserved_pins(all_content)
    parsed.strap_gpios = _parse_strap_pins(all_content)
    parsed.chip_name = _detect_chip_variant(all_content, parsed.soc_caps)

    return _assemble_profile(parsed, f"ESP-IDF headers: {soc_path}")


def parse_espidf_header_string(
    gpio_sig_map_content: str,
    soc_caps_content: str = "",
    chip_name: str = "ESP32-S3",
) -> MCUDeviceProfile:
    """Parse ESP-IDF header content from strings (useful for testing).

    Args:
        gpio_sig_map_content: Content of gpio_sig_map.h
        soc_caps_content: Content of soc_caps.h (optional)
        chip_name: Chip variant name

    Returns:
        MCUDeviceProfile
    """
    parsed = ESPParseResult(chip_name=chip_name)
    parsed.signals = _parse_gpio_sig_map(gpio_sig_map_content)

    if soc_caps_content:
        parsed.soc_caps = _parse_soc_caps(soc_caps_content)
        parsed.gpio_count = parsed.soc_caps.get("SOC_GPIO_PIN_COUNT", 0)

    # Apply well-known defaults based on chip name
    if "S3" in chip_name.upper():
        parsed.gpio_count = parsed.gpio_count or 49
        parsed.reserved_gpios = _ESP32S3_RESERVED
        parsed.strap_gpios = _ESP32S3_STRAPS
    elif "C3" in chip_name.upper():
        parsed.gpio_count = parsed.gpio_count or 22
        parsed.reserved_gpios = set()
        parsed.strap_gpios = {2, 8, 9}
    else:
        parsed.gpio_count = parsed.gpio_count or 40
        parsed.reserved_gpios = _ESP32_RESERVED
        parsed.strap_gpios = _ESP32_STRAPS

    return _assemble_profile(parsed, f"ESP-IDF string: {chip_name}")


def _assemble_profile(parsed: ESPParseResult, source_ref: str) -> MCUDeviceProfile:
    """Assemble MCUDeviceProfile from parsed ESP-IDF data."""
    pin_defs = _build_pin_definitions_from_signals(parsed)

    # Build reserved pins list
    reserved: list[ReservedPin] = []
    for gpio in sorted(parsed.reserved_gpios):
        reserved.append(ReservedPin(
            pin_name=f"GPIO{gpio}",
            reason="flash/PSRAM (reserved by SiP module)",
            can_use_as_gpio=False,
        ))

    # Build recommended pin maps from SoC capabilities
    pinmaps: list[PinMap] = []
    if "S3" in parsed.chip_name.upper():
        pinmaps = [
            PinMap(name="i2c0_default", mappings={"SDA": "GPIO8", "SCL": "GPIO9"}),
            PinMap(name="spi2_default", mappings={"SCK": "GPIO12", "MISO": "GPIO13", "MOSI": "GPIO11"}),
            PinMap(name="uart0_default", mappings={"TX": "GPIO43", "RX": "GPIO44"}),
            PinMap(name="uart1_default", mappings={"TX": "GPIO17", "RX": "GPIO18"}),
            PinMap(name="usb_default", mappings={"DP": "GPIO20", "DM": "GPIO19"}),
        ]
    elif "C3" in parsed.chip_name.upper():
        pinmaps = [
            PinMap(name="i2c0_default", mappings={"SDA": "GPIO5", "SCL": "GPIO6"}),
            PinMap(name="spi2_default", mappings={"SCK": "GPIO4", "MISO": "GPIO3", "MOSI": "GPIO7"}),
            PinMap(name="uart0_default", mappings={"TX": "GPIO21", "RX": "GPIO20"}),
        ]
    else:
        pinmaps = [
            PinMap(name="i2c0_default", mappings={"SDA": "GPIO21", "SCL": "GPIO22"}),
            PinMap(name="spi2_default", mappings={"SCK": "GPIO14", "MISO": "GPIO12", "MOSI": "GPIO13"}),
            PinMap(name="uart0_default", mappings={"TX": "GPIO1", "RX": "GPIO3"}),
        ]

    # Determine variant-specific details
    is_s3 = "S3" in parsed.chip_name.upper()

    identity = MCUIdentity(
        vendor="Espressif",
        family=parsed.chip_name,
        series=parsed.chip_name,
        mpn=f"{parsed.chip_name}-WROOM-1" if is_s3 else parsed.chip_name,
        package="SMD module" if is_s3 else "QFN",
        pin_count=parsed.gpio_count,
    )

    # Build peripheral patterns
    soc_caps = parsed.soc_caps
    patterns = PeripheralPatterns(
        i2c=I2CPattern(
            pullup_value_rule="4.7kΩ for ≤100kHz, 2.2kΩ for 400kHz",
        ) if soc_caps.get("SOC_I2C_NUM", 1) > 0 else None,
        spi=SPIPattern(max_freq_mhz=80) if soc_caps.get("SOC_SPI_PERIPH_NUM", 1) > 0 else None,
        uart=UARTPattern() if soc_caps.get("SOC_UART_NUM", 1) > 0 else None,
        usb=USBPattern(
            dp_dm_series_resistor_ohm=27,
            esd_protection_ic="USBLC6-2SC6",
        ) if soc_caps.get("SOC_USB_OTG_SUPPORTED", 0) or is_s3 else None,
        rf=RFPattern(
            keepout_zone_mm=15.0,
            ground_plane_requirement="Solid ground under antenna area",
        ),
    )

    # Boot config — ESP32 strapping pins
    boot_mode_pins: list[BootModePin] = []
    for gpio in sorted(parsed.strap_gpios):
        boot_mode_pins.append(BootModePin(
            pin=f"GPIO{gpio}",
            normal_boot_state="high" if gpio == 0 else "low",
            pull_resistor="pull_up_10k" if gpio == 0 else "pull_down_10k",
            notes=f"Strapping pin GPIO{gpio}",
        ))

    # Firmware binding
    bus_defaults: dict[str, BusConfig] = {}
    for i in range(soc_caps.get("SOC_I2C_NUM", 1)):
        bus_defaults[f"I2C{i}"] = BusConfig(bus_type="I2C", default_speed_hz=400000, default_mode="fast")
    for i in range(soc_caps.get("SOC_UART_NUM", 1)):
        bus_defaults[f"UART{i}"] = BusConfig(bus_type="UART", default_speed_hz=115200)

    return MCUDeviceProfile(
        identity=identity,
        pinout=MCUPinout(
            pins=pin_defs,
            reserved_pins=reserved,
            recommended_pinmaps=pinmaps,
        ),
        power=MCUPowerTree(power_domains=[
            PowerDomain(
                name="VDD3P3",
                nominal_voltage=3.3,
                allowed_range=(3.0, 3.6),
                max_current_draw_ma=500.0,
                sequencing_order=1,
                decoupling=[DecouplingRule(
                    domain="VDD3P3",
                    capacitors=[CapSpec(value="100nF", type="X7R", package="0402")],
                    placement_rule="within 3mm of power pins",
                )],
            ),
        ]),
        clock=ClockConfig(
            main_clock=ClockSource(
                type=ClockSourceType.external_xtal,
                frequency_hz=40_000_000,
                accuracy_ppm=10,
                load_capacitance_pf=12.0,
            ),
            safe_default_mhz=40 if is_s3 else 20,
        ),
        boot=BootConfig(
            reset_circuit=ResetCircuit(
                nrst_pin="EN",
                recommended_pullup_ohm=10000,
                cap_to_gnd_nf=100,
            ),
            boot_mode_pins=boot_mode_pins,
        ),
        io_rules=IOElectricalRules(
            max_source_current_per_pin_ma=40.0,
            max_sink_current_per_pin_ma=28.0,
            esd_rating_hbm_v=2000,
        ),
        peripheral_patterns=patterns,
        firmware=FirmwareBinding(
            bus_init_defaults=bus_defaults,
            sdk_framework="esp-idf",
            bootloader_options=["uart_boot", "usb_dfu"] if is_s3 else ["uart_boot"],
        ),
        provenance=[
            AttributeProvenance(
                source_ref=source_ref,
                source_type="sdk_header",
                verification_status="auto_imported",
                confidence_score=0.88,
            ),
        ],
    )
