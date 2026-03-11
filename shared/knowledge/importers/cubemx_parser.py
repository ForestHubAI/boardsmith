# SPDX-License-Identifier: AGPL-3.0-or-later
"""STM32CubeMX XML Parser → MCUDeviceProfile.

Parses the STM32CubeMX MCU XML database files (*.xml) that ship with
STM32CubeMX.  These XML files describe every pin, alternate function,
IP block, and power domain for each STM32 variant.

Typical XML structure (simplified):
  <Mcu ClockTree="..." Family="STM32G4" Line="STM32G4x1" ...>
    <Pin Name="PA0" Position="10" Type="I/O">
      <Signal Name="ADC1_IN1" />
      <Signal Name="TIM2_CH1" IOModes="..." />
      <Signal Name="USART2_CTS" />
    </Pin>
    <IP Name="I2C1" Version="..." />
    <IP Name="SPI1" Version="..." />
  </Mcu>

Usage:
  profile = parse_cubemx_xml("/path/to/STM32G431CBUx.xml")
  # → MCUDeviceProfile with full pin model + alt functions
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
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
    MandatoryComponent,
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
    CANPattern,
    USBPattern,
    IOElectricalRules,
    DebugInterface,
    FirmwareBinding,
    BusConfig,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pin-type classification
# ---------------------------------------------------------------------------

# Map CubeMX pin Type attribute → our PinType enum
_CUBEMX_TYPE_MAP: dict[str, PinType] = {
    "I/O": PinType.gpio,
    "Power": PinType.power,
    "Reset": PinType.reset,
    "Boot": PinType.boot,
    "MonoIO": PinType.gpio,
}

# Signal name patterns for classification
_POWER_PIN_RE = re.compile(r"^(VDD|VDDA|VDDUSB|VBAT|VREF)", re.IGNORECASE)
_GND_PIN_RE = re.compile(r"^(VSS|VSSA|GND)", re.IGNORECASE)
_OSC_PIN_RE = re.compile(r"^P[A-Z]\d+.*(OSC|RCC_OSC)", re.IGNORECASE)
_BOOT_PIN_RE = re.compile(r"^BOOT\d", re.IGNORECASE)
_RESET_PIN_RE = re.compile(r"^NRST", re.IGNORECASE)
_DEBUG_PIN_RE = re.compile(r"^(JTDI|JTDO|JTMS|JTCK|JTRST|SWDIO|SWCLK|SWO)", re.IGNORECASE)

# Alt-function → AF number extraction
_AF_NUMBER_RE = re.compile(r"GPIO_AF(\d+)")

# Peripheral signal patterns for recommended pin-maps
_I2C_SIGNAL_RE = re.compile(r"^(I2C\d+)_(SCL|SDA)$")
_SPI_SIGNAL_RE = re.compile(r"^(SPI\d+)_(SCK|MISO|MOSI|NSS)$")
_USART_SIGNAL_RE = re.compile(r"^(U?S?ART\d+|LPUART\d+)_(TX|RX)$")
_CAN_SIGNAL_RE = re.compile(r"^(FD?CAN\d+)_(TX|RX)$")
_USB_SIGNAL_RE = re.compile(r"^USB_(DP|DM|D\+|D-)$")
_ADC_SIGNAL_RE = re.compile(r"^(ADC\d+)_(IN\d+)$")
_TIM_SIGNAL_RE = re.compile(r"^(TIM\d+)_(CH\d+|ETR)$")


# ---------------------------------------------------------------------------
# CubeMX XML parsing result
# ---------------------------------------------------------------------------

@dataclass
class CubeMXParseResult:
    """Intermediate parse result before profile assembly."""
    mcu_name: str = ""
    family: str = ""
    line: str = ""
    package: str = ""
    pin_count: int = 0
    pins: list[dict] = field(default_factory=list)
    ips: list[dict] = field(default_factory=list)
    clock_tree: str = ""


def _classify_pin_type(pin_name: str, cubemx_type: str) -> PinType:
    """Determine PinType from CubeMX pin name and type attribute."""
    if _GND_PIN_RE.match(pin_name):
        return PinType.ground
    if _POWER_PIN_RE.match(pin_name):
        return PinType.power
    if _RESET_PIN_RE.match(pin_name):
        return PinType.reset
    if _BOOT_PIN_RE.match(pin_name):
        return PinType.boot
    if _OSC_PIN_RE.match(pin_name):
        return PinType.osc
    return _CUBEMX_TYPE_MAP.get(cubemx_type, PinType.gpio)


def _extract_af_number(signal_name: str, io_modes: str | None) -> int | None:
    """Extract AF number from CubeMX signal IOModes or naming convention."""
    if io_modes:
        m = _AF_NUMBER_RE.search(io_modes)
        if m:
            return int(m.group(1))
    return None


def _is_debug_signal(signal_name: str) -> bool:
    """Check if a signal is a debug/programming signal."""
    return bool(_DEBUG_PIN_RE.match(signal_name))


def _signal_to_alt_function(signal_name: str, io_modes: str | None = None) -> AltFunction:
    """Convert a CubeMX signal to an AltFunction."""
    af_num = _extract_af_number(signal_name, io_modes)

    # Determine available modes for I2C signals
    available_modes: list[str] = []
    if _I2C_SIGNAL_RE.match(signal_name):
        available_modes = ["standard", "fast"]

    return AltFunction(
        function=signal_name,
        af_number=af_num,
        available_modes=available_modes,
    )


# ---------------------------------------------------------------------------
# XML → CubeMXParseResult
# ---------------------------------------------------------------------------

def _parse_xml_tree(root: ET.Element) -> CubeMXParseResult:
    """Parse a CubeMX MCU XML element into intermediate result."""
    result = CubeMXParseResult()

    # MCU-level attributes
    result.mcu_name = root.get("RefName", root.get("Name", ""))
    result.family = root.get("Family", "")
    result.line = root.get("Line", "")
    result.package = root.get("Package", "")
    result.clock_tree = root.get("ClockTree", "")

    pin_count = root.get("IONb", "0")
    try:
        result.pin_count = int(pin_count)
    except ValueError:
        result.pin_count = 0

    # Parse Pin elements
    for pin_el in root.iter("Pin"):
        pin_data: dict = {
            "name": pin_el.get("Name", ""),
            "position": pin_el.get("Position", ""),
            "type": pin_el.get("Type", "I/O"),
            "signals": [],
        }
        for sig_el in pin_el.iter("Signal"):
            sig_name = sig_el.get("Name", "")
            if sig_name and sig_name not in ("GPIO",):
                pin_data["signals"].append({
                    "name": sig_name,
                    "io_modes": sig_el.get("IOModes"),
                })
        result.pins.append(pin_data)

    # Parse IP (peripheral) elements
    for ip_el in root.iter("IP"):
        result.ips.append({
            "name": ip_el.get("Name", ""),
            "instance": ip_el.get("InstanceName", ip_el.get("Name", "")),
            "version": ip_el.get("Version", ""),
        })

    # If pin_count wasn't in attributes, count GPIO-type pins
    if result.pin_count == 0:
        result.pin_count = len(result.pins)

    return result


# ---------------------------------------------------------------------------
# CubeMXParseResult → MCUDeviceProfile
# ---------------------------------------------------------------------------

def _build_pin_definitions(parsed: CubeMXParseResult) -> list[PinDefinition]:
    """Convert parsed pin data to PinDefinition list."""
    pins: list[PinDefinition] = []

    for pdata in parsed.pins:
        name = pdata["name"]
        position = pdata["position"]
        cubemx_type = pdata["type"]

        pin_type = _classify_pin_type(name, cubemx_type)

        # Default electrical characteristics for STM32 GPIO pins
        electrical = PinElectrical()
        if pin_type == PinType.gpio:
            electrical = PinElectrical(
                max_source_ma=20,
                max_sink_ma=20,
                is_5v_tolerant="FT" in name or pin_type == PinType.gpio,
                has_internal_pullup=True,
                has_internal_pulldown=True,
            )

        # Determine boot_strap
        boot_strap = _BOOT_PIN_RE.match(name) is not None

        # Default state
        default_state = None
        if boot_strap:
            default_state = "pull_down"

        # Convert signals to alt functions
        alt_functions: list[AltFunction] = []
        for sig in pdata["signals"]:
            af = _signal_to_alt_function(sig["name"], sig.get("io_modes"))
            alt_functions.append(af)

        # Detect debug pins
        is_debug = any(_is_debug_signal(sig["name"]) for sig in pdata["signals"])
        if is_debug and pin_type == PinType.gpio:
            pin_type = PinType.debug

        pins.append(PinDefinition(
            pin_name=name,
            pin_number=position,
            pin_type=pin_type,
            default_state=default_state,
            boot_strap=boot_strap,
            electrical=electrical,
            alt_functions=alt_functions,
        ))

    return pins


def _build_reserved_pins(pins: list[PinDefinition]) -> list[ReservedPin]:
    """Identify reserved pins (debug, boot, oscillator)."""
    reserved: list[ReservedPin] = []
    for pin in pins:
        if pin.pin_type == PinType.debug:
            reserved.append(ReservedPin(
                pin_name=pin.pin_name,
                reason=f"Debug ({', '.join(af.function for af in pin.alt_functions)})",
                can_use_as_gpio=False,
            ))
        elif pin.pin_type == PinType.osc:
            reserved.append(ReservedPin(
                pin_name=pin.pin_name,
                reason="Oscillator",
                can_use_as_gpio=False,
            ))
    return reserved


def _build_recommended_pinmaps(
    pins: list[PinDefinition],
) -> list[PinMap]:
    """Extract recommended pin maps from alt-function analysis."""
    # Collect first-found pin for each peripheral signal
    peripheral_pins: dict[str, dict[str, str]] = {}  # "I2C1" → {"SCL": "PB6", ...}

    for pin in pins:
        if pin.pin_type not in (PinType.gpio, PinType.debug):
            continue
        for af in pin.alt_functions:
            # I2C
            m = _I2C_SIGNAL_RE.match(af.function)
            if m:
                periph = m.group(1).lower()
                signal = m.group(2)
                peripheral_pins.setdefault(periph, {})
                peripheral_pins[periph].setdefault(signal, pin.pin_name)
                continue

            # SPI
            m = _SPI_SIGNAL_RE.match(af.function)
            if m:
                periph = m.group(1).lower()
                signal = m.group(2)
                peripheral_pins.setdefault(periph, {})
                peripheral_pins[periph].setdefault(signal, pin.pin_name)
                continue

            # UART
            m = _USART_SIGNAL_RE.match(af.function)
            if m:
                periph = m.group(1).lower()
                signal = m.group(2)
                peripheral_pins.setdefault(periph, {})
                peripheral_pins[periph].setdefault(signal, pin.pin_name)
                continue

            # CAN
            m = _CAN_SIGNAL_RE.match(af.function)
            if m:
                periph = m.group(1).lower()
                signal = m.group(2)
                peripheral_pins.setdefault(periph, {})
                peripheral_pins[periph].setdefault(signal, pin.pin_name)
                continue

            # USB
            m = _USB_SIGNAL_RE.match(af.function)
            if m:
                signal = m.group(1).replace("+", "P").replace("-", "M")
                peripheral_pins.setdefault("usb", {})
                peripheral_pins["usb"].setdefault(signal, pin.pin_name)
                continue

    # Build PinMap objects
    pinmaps: list[PinMap] = []
    for periph, mappings in sorted(peripheral_pins.items()):
        pinmaps.append(PinMap(
            name=f"{periph}_default",
            mappings=mappings,
        ))

    return pinmaps


def _build_power_tree(parsed: CubeMXParseResult) -> MCUPowerTree:
    """Build standard STM32 power tree from pin data."""
    # Detect power domains from pin names
    domain_names: set[str] = set()
    for pdata in parsed.pins:
        name = pdata["name"]
        if _POWER_PIN_RE.match(name):
            # Normalize: VDD_1, VDD_2 → VDD
            base = re.sub(r"[_\d]+$", "", name.upper())
            domain_names.add(base)

    domains: list[PowerDomain] = []
    for dname in sorted(domain_names):
        voltage = 3.3
        vrange = (1.71, 3.6)
        current = 150.0

        if "VBAT" in dname:
            vrange = (1.55, 3.6)
            current = 1.0
        elif "VDDA" in dname:
            vrange = (1.62, 3.6)
            current = 20.0

        domains.append(PowerDomain(
            name=dname,
            nominal_voltage=voltage,
            allowed_range=vrange,
            max_current_draw_ma=current,
            sequencing_order=1,
            decoupling=[DecouplingRule(
                domain=dname,
                capacitors=[CapSpec(value="100nF", type="X7R", package="0402")],
                placement_rule=f"within 3mm of {dname} pins",
            )],
        ))

    return MCUPowerTree(power_domains=domains)


def _build_clock_config(parsed: CubeMXParseResult) -> ClockConfig:
    """Build clock config with STM32-standard HSE + PLL."""
    # Detect oscillator pins
    osc_pins: list[str] = []
    for pdata in parsed.pins:
        if "OSC_IN" in pdata["name"] or "OSC_OUT" in pdata["name"]:
            osc_pins.append(pdata["name"])

    return ClockConfig(
        main_clock=ClockSource(
            type=ClockSourceType.external_xtal,
            frequency_hz=8_000_000,
            accuracy_ppm=20,
            load_capacitance_pf=20.0,
            osc_pins=osc_pins[:2] if osc_pins else [],
            required_caps=[
                CapSpec(value="20pF", type="C0G", package="0402", quantity=2),
            ],
        ),
        safe_default_mhz=16,  # HSI16 for STM32G4 family
    )


def _build_boot_config(pins: list[PinDefinition]) -> BootConfig:
    """Build boot config from detected boot pins."""
    boot_mode_pins: list[BootModePin] = []
    nrst_pin = "NRST"

    for pin in pins:
        if _BOOT_PIN_RE.match(pin.pin_name):
            boot_mode_pins.append(BootModePin(
                pin=pin.pin_name,
                normal_boot_state="low",
                pull_resistor="pull_down_10k",
                notes=f"LOW=boot from Flash (normal). Pin {pin.pin_number}.",
            ))

    return BootConfig(
        reset_circuit=ResetCircuit(
            nrst_pin=nrst_pin,
            recommended_pullup_ohm=10000,
            cap_to_gnd_nf=100,
        ),
        boot_mode_pins=boot_mode_pins,
    )


def _build_debug_interfaces(pins: list[PinDefinition]) -> list[DebugInterface]:
    """Detect debug interfaces from pin alt functions."""
    swd_pins: dict[str, str] = {}
    for pin in pins:
        for af in pin.alt_functions:
            if af.function == "SWDIO":
                swd_pins["SWDIO"] = pin.pin_name
            elif af.function == "SWCLK":
                swd_pins["SWCLK"] = pin.pin_name
            elif af.function.startswith("JTDO") or af.function == "SWO":
                swd_pins["SWO"] = pin.pin_name

    interfaces: list[DebugInterface] = []
    if swd_pins:
        interfaces.append(DebugInterface(
            protocol="SWD",
            pins=swd_pins,
        ))
    return interfaces


def _build_peripheral_patterns(parsed: CubeMXParseResult) -> PeripheralPatterns:
    """Build peripheral patterns based on detected IPs."""
    ip_names = {ip["name"].upper() for ip in parsed.ips}

    i2c = I2CPattern(
        pullup_value_rule="4.7kΩ for ≤100kHz, 2.2kΩ for 400kHz",
    ) if any("I2C" in n for n in ip_names) else None

    spi = SPIPattern(
        max_freq_mhz=42,
    ) if any("SPI" in n for n in ip_names) else None

    uart = UARTPattern(
        rx_tx_series_resistor=100,
    ) if any("USART" in n or "UART" in n or "LPUART" in n for n in ip_names) else None

    can = CANPattern(
        requires_transceiver=True,
        recommended_transceivers=["SN65HVD230", "MCP2551"],
        termination_resistor_ohm=120,
    ) if any("CAN" in n or "FDCAN" in n for n in ip_names) else None

    usb = USBPattern(
        dp_dm_series_resistor_ohm=27,
        esd_protection_ic="USBLC6-2SC6",
    ) if any("USB" in n for n in ip_names) else None

    return PeripheralPatterns(
        i2c=i2c, spi=spi, uart=uart, can=can, usb=usb,
    )


def _build_firmware_binding(parsed: CubeMXParseResult) -> FirmwareBinding:
    """Build firmware binding with STM32 HAL defaults."""
    bus_defaults: dict[str, BusConfig] = {}

    for ip in parsed.ips:
        name = ip["name"].upper()
        if "I2C" in name:
            bus_defaults[ip["instance"]] = BusConfig(
                bus_type="I2C", default_speed_hz=400000, default_mode="fast",
            )
        elif "SPI" in name:
            bus_defaults[ip["instance"]] = BusConfig(
                bus_type="SPI", default_speed_hz=10000000, default_mode="mode_0",
            )
        elif "USART" in name or "UART" in name or "LPUART" in name:
            bus_defaults[ip["instance"]] = BusConfig(
                bus_type="UART", default_speed_hz=115200,
            )
        elif "CAN" in name or "FDCAN" in name:
            bus_defaults[ip["instance"]] = BusConfig(
                bus_type="CAN", default_speed_hz=500000,
            )

    return FirmwareBinding(
        bus_init_defaults=bus_defaults,
        sdk_framework="stm32hal",
        bootloader_options=["uart_boot", "swd_flash"],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_cubemx_xml(xml_path: str | Path) -> MCUDeviceProfile:
    """Parse a STM32CubeMX MCU XML file into a MCUDeviceProfile.

    Args:
        xml_path: Path to the CubeMX XML file (e.g. STM32G431CBUx.xml)

    Returns:
        Fully populated MCUDeviceProfile
    """
    path = Path(xml_path)
    if not path.exists():
        raise FileNotFoundError(f"CubeMX XML not found: {path}")

    tree = ET.parse(path)
    root = tree.getroot()

    # Handle namespaced XML (CubeMX uses a default namespace sometimes)
    # Strip namespace if present
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]

    parsed = _parse_xml_tree(root)
    log.info("Parsed CubeMX XML: %s (%d pins, %d IPs)",
             parsed.mcu_name, len(parsed.pins), len(parsed.ips))

    # Build all sub-models
    pin_defs = _build_pin_definitions(parsed)
    reserved = _build_reserved_pins(pin_defs)
    pinmaps = _build_recommended_pinmaps(pin_defs)

    # Derive package from MCU name or XML attributes
    package = parsed.package or "LQFP"

    # Build identity
    # Try to extract MPN from RefName (e.g. "STM32G431CBUx" → "STM32G431CBU6")
    mpn = parsed.mcu_name
    if mpn.endswith("x"):
        mpn = mpn[:-1] + "6"  # Common convention: x → 6 (industrial temp)

    # Extract series from line/family
    series = parsed.line or parsed.family

    identity = MCUIdentity(
        vendor="STMicroelectronics",
        family=parsed.family,
        series=series,
        mpn=mpn,
        package=package,
        pin_count=parsed.pin_count or len(pin_defs),
        temperature_grade=TemperatureGrade.industrial,
        lifecycle_status="active",
    )

    profile = MCUDeviceProfile(
        identity=identity,
        pinout=MCUPinout(
            pins=pin_defs,
            reserved_pins=reserved,
            recommended_pinmaps=pinmaps,
        ),
        power=_build_power_tree(parsed),
        clock=_build_clock_config(parsed),
        boot=_build_boot_config(pin_defs),
        debug_interfaces=_build_debug_interfaces(pin_defs),
        mandatory_components=[
            MandatoryComponent(
                component_type="cap",
                value="100nF",
                spec="X7R 0402 ±10%",
                quantity_rule="per_vdd_pin",
                placement="within 3mm of each VDD pin",
                rationale="STM32 AN4488: 100nF ceramic per VDD pin",
            ),
        ],
        io_rules=IOElectricalRules(
            max_source_current_per_pin_ma=20.0,
            max_sink_current_per_pin_ma=20.0,
            max_total_current_per_port_ma=100.0,
            esd_rating_hbm_v=2000,
        ),
        peripheral_patterns=_build_peripheral_patterns(parsed),
        firmware=_build_firmware_binding(parsed),
        provenance=[
            AttributeProvenance(
                source_ref=f"STM32CubeMX XML: {path.name}",
                source_type="sdk_header",
                verification_status="auto_imported",
                confidence_score=0.85,
            ),
        ],
    )

    return profile


def parse_cubemx_xml_string(xml_string: str, source_name: str = "<string>") -> MCUDeviceProfile:
    """Parse a CubeMX XML string (useful for testing without files).

    Args:
        xml_string: XML content as string
        source_name: Name for provenance tracking

    Returns:
        MCUDeviceProfile
    """
    root = ET.fromstring(xml_string)

    # Strip namespace if present
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]

    parsed = _parse_xml_tree(root)

    pin_defs = _build_pin_definitions(parsed)
    reserved = _build_reserved_pins(pin_defs)
    pinmaps = _build_recommended_pinmaps(pin_defs)

    mpn = parsed.mcu_name
    if mpn.endswith("x"):
        mpn = mpn[:-1] + "6"

    identity = MCUIdentity(
        vendor="STMicroelectronics",
        family=parsed.family,
        series=parsed.line or parsed.family,
        mpn=mpn,
        package=parsed.package or "LQFP",
        pin_count=parsed.pin_count or len(pin_defs),
    )

    return MCUDeviceProfile(
        identity=identity,
        pinout=MCUPinout(
            pins=pin_defs,
            reserved_pins=reserved,
            recommended_pinmaps=pinmaps,
        ),
        power=_build_power_tree(parsed),
        clock=_build_clock_config(parsed),
        boot=_build_boot_config(pin_defs),
        debug_interfaces=_build_debug_interfaces(pin_defs),
        peripheral_patterns=_build_peripheral_patterns(parsed),
        firmware=_build_firmware_binding(parsed),
        provenance=[
            AttributeProvenance(
                source_ref=f"STM32CubeMX XML: {source_name}",
                source_type="sdk_header",
                verification_status="auto_imported",
                confidence_score=0.85,
            ),
        ],
    )
