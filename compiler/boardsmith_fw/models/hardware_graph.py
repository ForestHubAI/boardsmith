# SPDX-License-Identifier: AGPL-3.0-or-later
"""HardwareGraph — deterministic internal model of an Eagle schematic."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PinDirection(str, Enum):
    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"
    POWER = "power"
    PASSIVE = "passive"
    UNKNOWN = "unknown"


class Pin(BaseModel):
    name: str
    number: str
    direction: PinDirection = PinDirection.UNKNOWN
    electrical_type: str = ""
    net: Optional[str] = None


class Component(BaseModel):
    id: str
    name: str  # reference designator, e.g. "U1"
    value: str  # part value, e.g. "BME280"
    package: str = ""
    library: str = ""
    deviceset: str = ""
    description: str = ""
    manufacturer: str = ""
    mpn: str = ""  # manufacturer part number
    pins: list[Pin] = Field(default_factory=list)
    attributes: dict[str, str] = Field(default_factory=dict)


class NetPin(BaseModel):
    component_id: str
    pin_name: str


class Net(BaseModel):
    name: str
    pins: list[NetPin] = Field(default_factory=list)
    is_bus: bool = False
    is_power: bool = False


class BusType(str, Enum):
    I2C = "I2C"
    SPI = "SPI"
    UART = "UART"
    GPIO = "GPIO"
    ADC = "ADC"
    PWM = "PWM"
    CAN = "CAN"
    OTHER = "OTHER"


class BusPinMapping(BaseModel):
    """Maps a bus signal (e.g. SDA, SCL) to the MCU pin that drives it."""
    signal: str  # e.g. "SDA", "SCL", "MOSI"
    net: str
    mcu_pin_name: str  # full pin name from schematic, e.g. "GPIO21/SDA"
    gpio: Optional[str] = None  # extracted GPIO id, e.g. "21" or "PB7"


class Bus(BaseModel):
    name: str
    type: BusType
    nets: list[str] = Field(default_factory=list)
    master_component_id: Optional[str] = None
    slave_component_ids: list[str] = Field(default_factory=list)
    pin_mapping: list[BusPinMapping] = Field(default_factory=list)


class IRQLine(BaseModel):
    net: str
    source_component_id: str
    target_component_id: str
    trigger: Optional[str] = None  # rising, falling, both, level


class PowerDomain(BaseModel):
    name: str
    voltage: str
    nets: list[str] = Field(default_factory=list)
    regulator_component_id: Optional[str] = None


class MCUFamily(str, Enum):
    ESP32 = "esp32"
    ESP32_C3 = "esp32c3"
    STM32 = "stm32"
    RP2040 = "rp2040"
    NRF52 = "nrf52"
    UNKNOWN = "unknown"


class MCUInfo(BaseModel):
    component_id: str
    type: str
    family: MCUFamily = MCUFamily.UNKNOWN
    pins: list[Pin] = Field(default_factory=list)


class GraphMetadata(BaseModel):
    total_components: int = 0
    total_nets: int = 0
    detected_buses: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class HardwareGraph(BaseModel):
    version: str = "1.0.0"
    source: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    mcu: Optional[MCUInfo] = None
    components: list[Component] = Field(default_factory=list)
    nets: list[Net] = Field(default_factory=list)
    buses: list[Bus] = Field(default_factory=list)
    irq_lines: list[IRQLine] = Field(default_factory=list)
    power_domains: list[PowerDomain] = Field(default_factory=list)
    metadata: GraphMetadata = Field(default_factory=GraphMetadata)
