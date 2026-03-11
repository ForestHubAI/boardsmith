# SPDX-License-Identifier: AGPL-3.0-or-later
"""Board Schema — declarative YAML board definition models.

Allows defining hardware without an Eagle/KiCad schematic:

    boardsmith_fw_schema: "1.0"
    board:
      name: "My Sensor Board"
      mcu:
        mpn: ESP32-WROOM-32
        id: U1
        family: esp32
      buses:
        - name: I2C_0
          type: I2C
          clock_hz: 400000
          pins:
            SDA: GPIO21
            SCL: GPIO22
          devices:
            - id: U2
              mpn: BME280
              address: "0x76"
      power:
        - name: 3V3
          voltage: 3.3
          components: [U2]
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class BoardSchemaMCU(BaseModel):
    """MCU definition in the board schema."""
    id: str = "U1"
    mpn: str                         # e.g. "ESP32-WROOM-32", "STM32F411CEU6", "RP2040"
    family: str = "auto"             # "esp32", "stm32", "rp2040", "auto"
    description: str = ""


class BoardSchemaDevice(BaseModel):
    """A peripheral device on a bus."""
    id: str                          # reference designator, e.g. "U2"
    mpn: str                         # manufacturer part number, e.g. "BME280"
    address: Optional[str] = None    # I2C hex address, e.g. "0x76"
    description: str = ""


class BoardSchemaBus(BaseModel):
    """A bus with its pin assignments and connected devices."""
    name: str                        # e.g. "I2C_0", "SPI_FLASH"
    type: str                        # "I2C", "SPI", "UART", "CAN", "ADC", "PWM"
    pins: dict[str, str] = Field(default_factory=dict)   # signal → GPIO, e.g. {"SDA": "GPIO21"}
    clock_hz: Optional[int] = None   # bus clock (I2C/SPI)
    baud_rate: Optional[int] = None  # UART baud rate
    devices: list[BoardSchemaDevice] = Field(default_factory=list)


class BoardSchemaPower(BaseModel):
    """A power rail definition."""
    name: str                        # e.g. "3V3", "1V8_CORE"
    voltage: float                   # nominal voltage in V
    components: list[str] = Field(default_factory=list)  # component IDs on this rail


class BoardSchemaRoot(BaseModel):
    """Top-level board schema — parsed from YAML."""
    boardsmith_fw_schema: str = "1.0"
    board: BoardSchemaBoard


class BoardSchemaBoard(BaseModel):
    """The board definition block."""
    name: str = ""
    mcu: BoardSchemaMCU
    buses: list[BoardSchemaBus] = Field(default_factory=list)
    power: list[BoardSchemaPower] = Field(default_factory=list)


# Fix forward reference
BoardSchemaRoot.model_rebuild()
