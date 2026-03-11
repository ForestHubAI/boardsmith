# SPDX-License-Identifier: AGPL-3.0-or-later
"""Board Schema Parser — converts YAML board definition into HardwareGraph.

This enables the full boardsmith-fw pipeline (HIR → Constraints → Codegen)
without requiring an Eagle or KiCad schematic file.

Usage:
    from boardsmith_fw.parser.board_schema_parser import parse_board_schema
    graph = parse_board_schema(Path("board.yaml"))
"""

from __future__ import annotations

from pathlib import Path

import yaml

from boardsmith_fw.models.board_schema import BoardSchemaBoard, BoardSchemaBus, BoardSchemaRoot
from boardsmith_fw.models.hardware_graph import (
    Bus,
    BusPinMapping,
    BusType,
    Component,
    HardwareGraph,
    MCUFamily,
    MCUInfo,
    Net,
    NetPin,
    PowerDomain,
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_board_schema(path: Path) -> HardwareGraph:
    """Parse a board schema YAML file into a HardwareGraph."""
    text = path.read_text(encoding="utf-8")
    return parse_board_schema_text(text, source=str(path))


def parse_board_schema_text(text: str, source: str = "<schema>") -> HardwareGraph:
    """Parse board schema YAML text into a HardwareGraph."""
    raw = yaml.safe_load(text)
    schema = BoardSchemaRoot(**raw)
    return _build_graph(schema.board, source)


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def _build_graph(board: BoardSchemaBoard, source: str) -> HardwareGraph:
    graph = HardwareGraph(source=source)

    # MCU component
    mcu_comp = _make_mcu_component(board)
    graph.components.append(mcu_comp)
    graph.mcu = _make_mcu_info(board, mcu_comp)

    # Device components + buses
    for bus_def in board.buses:
        bus, nets, device_comps = _make_bus(bus_def, mcu_comp.id)
        graph.buses.append(bus)
        graph.nets.extend(nets)
        graph.components.extend(device_comps)

    # Power domains
    for rail in board.power:
        pd = PowerDomain(
            name=rail.name,
            voltage=str(rail.voltage),
            nets=[f"VCC_{rail.name}"],
        )
        graph.power_domains.append(pd)

    # Update metadata
    graph.metadata.total_components = len(graph.components)
    graph.metadata.total_nets = len(graph.nets)
    graph.metadata.detected_buses = [b.name for b in graph.buses]

    return graph


# ---------------------------------------------------------------------------
# MCU helpers
# ---------------------------------------------------------------------------

def _make_mcu_component(board: BoardSchemaBoard) -> Component:
    mpn = board.mcu.mpn
    return Component(
        id=board.mcu.id,
        name=board.mcu.id,
        value=mpn,
        mpn=mpn,
        description=board.mcu.description or f"{mpn} microcontroller",
    )


def _make_mcu_info(board: BoardSchemaBoard, comp: Component) -> MCUInfo:
    family_str = board.mcu.family.lower()
    mpn_lower = board.mcu.mpn.lower()

    if family_str == "auto" or family_str == "":
        if any(tag in mpn_lower for tag in ("esp32-c3", "esp32c3", "esp32-c6", "esp32c6", "esp32-h2", "esp32h2")):
            family = MCUFamily.ESP32_C3
        elif "esp32" in mpn_lower:
            family = MCUFamily.ESP32
        elif "stm32" in mpn_lower:
            family = MCUFamily.STM32
        elif "rp2040" in mpn_lower or "pico" in mpn_lower:
            family = MCUFamily.RP2040
        elif "nrf52" in mpn_lower:
            family = MCUFamily.NRF52
        else:
            family = MCUFamily.UNKNOWN
    else:
        family = MCUFamily(family_str) if family_str in MCUFamily._value2member_map_ else MCUFamily.UNKNOWN

    return MCUInfo(
        component_id=comp.id,
        type=board.mcu.mpn,
        family=family,
    )


# ---------------------------------------------------------------------------
# Bus helpers
# ---------------------------------------------------------------------------

def _make_bus(
    bus_def: BoardSchemaBus,
    mcu_id: str,
) -> tuple[Bus, list[Net], list[Component]]:
    """Build a Bus, its Nets, and device Components from a bus definition."""
    bus_type = _resolve_bus_type(bus_def.type)

    slave_ids = [d.id for d in bus_def.devices]

    # Pin mappings
    pin_mappings = _make_pin_mappings(bus_def, bus_type)

    # Nets: one per pin signal
    nets = _make_nets(bus_def, mcu_id, slave_ids)

    bus = Bus(
        name=bus_def.name,
        type=bus_type,
        nets=[n.name for n in nets],
        master_component_id=mcu_id,
        slave_component_ids=slave_ids,
        pin_mapping=pin_mappings,
    )

    # Device components
    device_comps = [_make_device_component(d) for d in bus_def.devices]

    return bus, nets, device_comps


def _resolve_bus_type(type_str: str) -> BusType:
    mapping = {
        "i2c": BusType.I2C,
        "spi": BusType.SPI,
        "uart": BusType.UART,
        "can": BusType.CAN,
        "adc": BusType.ADC,
        "pwm": BusType.PWM,
    }
    return mapping.get(type_str.lower(), BusType.OTHER)


def _make_pin_mappings(bus_def: BoardSchemaBus, bus_type: BusType) -> list[BusPinMapping]:
    mappings = []
    for signal, gpio_str in bus_def.pins.items():
        # Normalize GPIO string: "GPIO21" → "21", "PB7" → "PB7"
        gpio = _normalize_gpio(gpio_str)
        mappings.append(BusPinMapping(
            signal=signal.upper(),
            net=f"{bus_def.name}_{signal.upper()}",
            mcu_pin_name=gpio_str,
            gpio=gpio,
        ))
    return mappings


def _normalize_gpio(gpio_str: str) -> str:
    """Extract GPIO number or port pin from string.

    "GPIO21" → "21", "PA5" → "PA5", "21" → "21"
    """
    s = gpio_str.strip()
    upper = s.upper()
    if upper.startswith("GPIO"):
        return s[4:]  # strip "GPIO" prefix
    return s


def _make_nets(bus_def: BoardSchemaBus, mcu_id: str, slave_ids: list[str]) -> list[Net]:
    nets = []
    for signal in bus_def.pins:
        net_name = f"{bus_def.name}_{signal.upper()}"
        pins = [NetPin(component_id=mcu_id, pin_name=signal.upper())]
        for sid in slave_ids:
            pins.append(NetPin(component_id=sid, pin_name=signal.upper()))
        nets.append(Net(name=net_name, pins=pins))
    return nets


def _make_device_component(device) -> Component:
    mpn = device.mpn
    comp = Component(
        id=device.id,
        name=device.id,
        value=mpn,
        mpn=mpn,
        description=device.description or mpn,
    )
    # Attach a stub pin so knowledge resolver can match
    if device.address:
        comp.attributes["i2c_address"] = device.address
    return comp
