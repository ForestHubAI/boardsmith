# SPDX-License-Identifier: AGPL-3.0-or-later
"""GraphBuilder — deterministic bus/IRQ/power detection from parsed components + nets."""

from __future__ import annotations

import re

from boardsmith_fw.models.hardware_graph import (
    Bus,
    BusPinMapping,
    BusType,
    Component,
    HardwareGraph,
    IRQLine,
    MCUFamily,
    MCUInfo,
    Net,
    PowerDomain,
)

_I2C_SIGNALS = {"SDA", "SCL", "I2C_SDA", "I2C_SCL"}
_SPI_SIGNALS = {"MOSI", "MISO", "SCK", "SCLK", "CS", "SS", "NSS"}
_UART_SIGNALS = {"TX", "RX", "TXD", "RXD", "UART_TX", "UART_RX"}
_CAN_SIGNALS = {"CANH", "CANL", "CAN_TX", "CAN_RX"}
_ADC_SIGNALS = {"ADC", "AIN", "ADC_IN", "VSEN", "VSENSE"}
_PWM_SIGNALS = {"PWM", "PWM_OUT", "LED_PWM"}

_ESP32_C3_IDS = [
    "ESP32-C3", "ESP32C3", "ESP32-C6", "ESP32C6",
    "ESP32-H2", "ESP32H2",
]

_ESP32_IDS = [
    "ESP32", "ESP-32", "ESP32-WROOM", "ESP32-WROVER",
    "ESP32-S3", "ESP32S3",
]

_STM32_IDS = [
    "STM32", "STM32F", "STM32L", "STM32G", "STM32H", "STM32U", "STM32W", "STM32C",
    "STM32F0", "STM32F1", "STM32F2", "STM32F3", "STM32F4", "STM32F7",
    "STM32L0", "STM32L1", "STM32L4", "STM32L5",
    "STM32G0", "STM32G4",
    "STM32H5", "STM32H7",
    "STM32U5",
]

_RP2040_IDS = [
    "RP2040", "RP-2040", "PICO", "RASPBERRY PI PICO",
    "RP2350", "RP-2350", "PICO2", "PICO W",
]

_NRF52_IDS = [
    "NRF52", "NRF-52", "NRF52832", "NRF52840",
    "NRF52810", "NRF52811", "NRF52820", "NRF52833",
]

_IRQ_PATTERNS = ["INT", "IRQ", "DRDY", "ALERT", "ALARM", "EXTI"]

_VOLTAGE_PATTERNS: list[tuple[str, str]] = [
    ("3V3", "3.3V"), ("3.3V", "3.3V"), ("+3V3", "3.3V"), ("+3.3V", "3.3V"),
    ("5V", "5V"), ("+5V", "5V"),
    ("1V8", "1.8V"), ("1.8V", "1.8V"), ("+1V8", "1.8V"),
    ("12V", "12V"), ("+12V", "12V"),
    ("VCC", "VCC"), ("VDD", "VDD"), ("GND", "0V"), ("VBAT", "VBAT"),
]


def build_hardware_graph(
    source: str, components: list[Component], nets: list[Net]
) -> HardwareGraph:
    graph = HardwareGraph(source=source, components=components, nets=nets)
    graph.mcu = _detect_mcu(components)
    graph.buses = _detect_buses(nets, components)
    graph.irq_lines = _detect_irq_lines(nets, components)
    graph.power_domains = _detect_power_domains(nets)

    if graph.mcu:
        for bus in graph.buses:
            bus.pin_mapping = _resolve_pin_mapping(bus, nets, graph.mcu, components)

    graph.metadata.total_components = len(components)
    graph.metadata.total_nets = len(nets)
    graph.metadata.detected_buses = [f"{b.type.value}: {b.name}" for b in graph.buses]
    return graph


# ---------------------------------------------------------------------------

def _detect_mcu(components: list[Component]) -> MCUInfo | None:
    for comp in components:
        text = f"{comp.value} {comp.deviceset} {comp.mpn}".upper()
        # Check ESP32-C3/C6/H2 RISC-V variants BEFORE generic ESP32
        for c3_id in _ESP32_C3_IDS:
            if c3_id in text:
                return MCUInfo(component_id=comp.id, type=c3_id, family=MCUFamily.ESP32_C3, pins=comp.pins)
        for esp_id in _ESP32_IDS:
            if esp_id in text:
                return MCUInfo(component_id=comp.id, type=esp_id, family=MCUFamily.ESP32, pins=comp.pins)
        for stm_id in _STM32_IDS:
            if stm_id in text:
                return MCUInfo(component_id=comp.id, type=stm_id, family=MCUFamily.STM32, pins=comp.pins)
        for rp_id in _RP2040_IDS:
            if rp_id in text:
                return MCUInfo(component_id=comp.id, type=rp_id, family=MCUFamily.RP2040, pins=comp.pins)
        for nrf_id in _NRF52_IDS:
            if nrf_id in text:
                return MCUInfo(component_id=comp.id, type=nrf_id, family=MCUFamily.NRF52, pins=comp.pins)
    return None


def _is_mcu(comp_id: str, components: list[Component]) -> bool:
    comp = next((c for c in components if c.id == comp_id), None)
    if not comp:
        return False
    text = f"{comp.value} {comp.deviceset} {comp.mpn}".upper()
    return (
        any(mid in text for mid in _ESP32_C3_IDS)
        or any(mid in text for mid in _ESP32_IDS)
        or any(mid in text for mid in _STM32_IDS)
        or any(mid in text for mid in _RP2040_IDS)
        or any(mid in text for mid in _NRF52_IDS)
    )


def _is_passive(comp_id: str, components: list[Component]) -> bool:
    comp = next((c for c in components if c.id == comp_id), None)
    if not comp:
        return False
    ref = comp.name.upper()
    return ref[:1] in ("R", "C", "L", "D")


def _find_matching_nets(nets: list[Net], signals: set[str]) -> list[Net]:
    matched: list[Net] = []
    for net in nets:
        upper = net.name.upper()
        for sig in signals:
            if upper == sig or upper.endswith(f"_{sig}") or upper.startswith(f"{sig}_"):
                matched.append(net)
                break
    return matched


def _connected_ids(nets: list[Net]) -> list[str]:
    ids: set[str] = set()
    for net in nets:
        for pin in net.pins:
            ids.add(pin.component_id)
    return list(ids)


def _make_bus(
    name: str, bus_type: BusType, nets: list[Net], components: list[Component]
) -> Bus:
    ids = _connected_ids(nets)
    return Bus(
        name=name,
        type=bus_type,
        nets=[n.name for n in nets],
        master_component_id=next((i for i in ids if _is_mcu(i, components)), None),
        slave_component_ids=[
            i for i in ids
            if not _is_mcu(i, components) and not _is_passive(i, components)
        ],
    )


def _detect_buses(nets: list[Net], components: list[Component]) -> list[Bus]:
    buses: list[Bus] = []
    for signals, name, btype, min_count in [
        (_I2C_SIGNALS, "I2C_BUS", BusType.I2C, 2),
        (_SPI_SIGNALS, "SPI_BUS", BusType.SPI, 2),
        (_UART_SIGNALS, "UART_BUS", BusType.UART, 2),
        (_CAN_SIGNALS, "CAN_BUS", BusType.CAN, 1),
        (_ADC_SIGNALS, "ADC_BUS", BusType.ADC, 1),
        (_PWM_SIGNALS, "PWM_BUS", BusType.PWM, 1),
    ]:
        matched = _find_matching_nets(nets, signals)
        if len(matched) >= min_count:
            buses.append(_make_bus(name, btype, matched, components))
    return buses


def _detect_irq_lines(nets: list[Net], components: list[Component]) -> list[IRQLine]:
    lines: list[IRQLine] = []
    for net in nets:
        upper = net.name.upper()
        if not any(p in upper for p in _IRQ_PATTERNS):
            continue
        if len(net.pins) < 2:
            continue
        source = next((p for p in net.pins if not _is_mcu(p.component_id, components)), None)
        target = next((p for p in net.pins if _is_mcu(p.component_id, components)), None)
        if source and target:
            lines.append(IRQLine(
                net=net.name,
                source_component_id=source.component_id,
                target_component_id=target.component_id,
            ))
    return lines


def _detect_power_domains(nets: list[Net]) -> list[PowerDomain]:
    domains: list[PowerDomain] = []
    for net in nets:
        upper = net.name.upper()
        for pattern, voltage in _VOLTAGE_PATTERNS:
            if upper == pattern.upper():
                domains.append(PowerDomain(name=net.name, voltage=voltage, nets=[net.name]))
                break
    return domains


# ---------------------------------------------------------------------------
# Pin mapping: extract MCU GPIO numbers from schematic pin names
# ---------------------------------------------------------------------------

# Patterns: "GPIO21/SDA" → 21, "PB7/SDA" → PB7, "PA5/SCK" → PA5, "GPIO_NUM_21" → 21
_GPIO_PATTERNS = [
    re.compile(r"GPIO_?(\d+)"),            # GPIO21, GPIO_21, GPIO_NUM_21
    re.compile(r"(P[A-K]\d{1,2})"),        # PA0, PB7, PC13 (STM32)
    re.compile(r"IO(\d+)"),                # IO21 (some ESP32 naming)
]

# Maps bus signal names to the signal type they represent
_SIGNAL_KEYWORDS: dict[str, str] = {
    "SDA": "SDA", "I2C_SDA": "SDA",
    "SCL": "SCL", "I2C_SCL": "SCL",
    "MOSI": "MOSI", "MISO": "MISO",
    "SCK": "SCK", "SCLK": "SCK",
    "CS": "CS", "SS": "CS", "NSS": "CS",
    "TX": "TX", "TXD": "TX", "UART_TX": "TX",
    "RX": "RX", "RXD": "RX", "UART_RX": "RX",
    "CANH": "CANH", "CANL": "CANL",
    "CAN_TX": "CAN_TX", "CAN_RX": "CAN_RX",
    "ADC": "ADC", "AIN": "ADC", "ADC_IN": "ADC",
    "PWM": "PWM", "PWM_OUT": "PWM",
}


def _extract_gpio(pin_name: str) -> str | None:
    """Extract GPIO identifier from a pin name like 'GPIO21/SDA' or 'PB7/SDA'."""
    for pat in _GPIO_PATTERNS:
        m = pat.search(pin_name.upper())
        if m:
            return m.group(1)
    return None


def _classify_signal(net_name: str) -> str | None:
    """Classify a net name to a bus signal type (SDA, SCL, MOSI, etc.)."""
    upper = net_name.upper()
    # Direct match
    if upper in _SIGNAL_KEYWORDS:
        return _SIGNAL_KEYWORDS[upper]
    # Suffix match: "I2C1_SDA" → SDA
    for kw, sig in _SIGNAL_KEYWORDS.items():
        if upper.endswith(f"_{kw}") or upper.startswith(f"{kw}_"):
            return sig
    return None


def _resolve_pin_mapping(
    bus: Bus, nets: list[Net], mcu: MCUInfo, components: list[Component]
) -> list[BusPinMapping]:
    """For each net in the bus, find the MCU pin driving it and extract GPIO."""
    mappings: list[BusPinMapping] = []
    mcu_comp = next((c for c in components if c.id == mcu.component_id), None)
    if not mcu_comp:
        return mappings

    for net_name in bus.nets:
        signal = _classify_signal(net_name)
        if not signal:
            continue

        net = next((n for n in nets if n.name == net_name), None)
        if not net:
            continue

        # Find the MCU pin connected to this net
        mcu_pin_ref = next(
            (pr for pr in net.pins if pr.component_id == mcu.component_id), None
        )
        if not mcu_pin_ref:
            continue

        # Look up full pin info from MCU component
        mcu_pin = next(
            (p for p in mcu_comp.pins if p.name == mcu_pin_ref.pin_name), None
        )
        pin_name = mcu_pin.name if mcu_pin else mcu_pin_ref.pin_name
        gpio = _extract_gpio(pin_name)

        mappings.append(BusPinMapping(
            signal=signal,
            net=net_name,
            mcu_pin_name=pin_name,
            gpio=gpio,
        ))

    return mappings
