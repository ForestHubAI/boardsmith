# SPDX-License-Identifier: AGPL-3.0-or-later
"""Project configuration — .boardsmith-fw.yaml schema and loader.

Allows users to override auto-detected settings:
  - Bus frequencies, UART baud rates
  - Custom pin assignments
  - Target MCU override
  - LLM model selection
  - FreeRTOS task configuration
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class I2CConfig(BaseModel):
    frequency: int = 100000  # Hz
    port: int = 0  # I2C_NUM_0


class SPIConfig(BaseModel):
    frequency: int = 1000000  # Hz
    mode: int = 0  # SPI mode 0-3
    host: str = "SPI2_HOST"


class UARTConfig(BaseModel):
    baud_rate: int = 9600
    data_bits: int = 8
    stop_bits: int = 1
    parity: str = "none"  # none, even, odd
    port: int = 1  # UART_NUM_1


class PinOverride(BaseModel):
    signal: str  # e.g. "SDA", "MOSI", "TX"
    gpio: str  # e.g. "21", "PB7"


class ProjectConfig(BaseModel):
    """Root configuration loaded from .boardsmith-fw.yaml."""
    target: str = "auto"  # auto, esp32, stm32
    lang: str = "c"  # c, cpp
    model: str = "gpt-4o"  # LLM model

    i2c: I2CConfig = Field(default_factory=I2CConfig)
    spi: SPIConfig = Field(default_factory=SPIConfig)
    uart: UARTConfig = Field(default_factory=UARTConfig)

    pin_overrides: list[PinOverride] = Field(default_factory=list)

    component_overrides: dict[str, dict[str, str]] = Field(default_factory=dict)
    # e.g. {"U2": {"i2c_address": "0x77"}}

    rtos: bool = False  # Generate FreeRTOS task structure
    rtos_stack_size: int = 4096

    description: str = "Boardsmith-FW generated firmware"

    output_dir: str = "generated_firmware"
    cache_dir: str = ".cache"

    extra_defines: dict[str, str] = Field(default_factory=dict)
    # e.g. {"CONFIG_LOG_LEVEL": "3"}


def load_config(project_dir: Path | None = None) -> ProjectConfig:
    """Load config from .boardsmith-fw.yaml in the given directory, or defaults."""
    if project_dir is None:
        project_dir = Path.cwd()

    yaml_path = project_dir / ".boardsmith-fw.yaml"
    yml_path = project_dir / ".boardsmith-fw.yml"

    config_path = yaml_path if yaml_path.exists() else (yml_path if yml_path.exists() else None)

    if config_path is None:
        return ProjectConfig()

    try:
        import yaml
    except ImportError:
        # PyYAML not installed — return defaults
        return ProjectConfig()

    try:
        data = yaml.safe_load(config_path.read_text()) or {}
        return ProjectConfig(**data)
    except Exception:
        return ProjectConfig()


def generate_default_config() -> str:
    """Generate a commented default .boardsmith-fw.yaml."""
    return """\
# Boardsmith-FW Project Configuration
# Place this file as .boardsmith-fw.yaml in your project root.

# Target MCU platform (auto-detected from schematic if "auto")
target: auto  # auto | esp32 | stm32

# Output language
lang: c  # c | cpp

# LLM model for enhanced code generation (requires OPENAI_API_KEY)
model: gpt-4o

# Firmware description
description: "Boardsmith-FW generated firmware"

# Output directories
output_dir: generated_firmware
cache_dir: .cache

# Bus configuration overrides
i2c:
  frequency: 100000  # Hz (100kHz standard, 400kHz fast mode)
  port: 0            # I2C peripheral number

spi:
  frequency: 1000000  # Hz
  mode: 0             # SPI mode (0-3)
  host: SPI2_HOST

uart:
  baud_rate: 9600
  data_bits: 8
  stop_bits: 1
  parity: none  # none | even | odd
  port: 1

# Pin overrides — force specific GPIO assignments
# pin_overrides:
#   - signal: SDA
#     gpio: "21"
#   - signal: SCL
#     gpio: "22"

# Component overrides — override auto-detected values
# component_overrides:
#   U2:
#     i2c_address: "0x77"  # BME280 with SDO=VDD

# FreeRTOS task generation
rtos: false
rtos_stack_size: 4096

# Extra #define values for the generated code
# extra_defines:
#   CONFIG_LOG_LEVEL: "3"
#   SENSOR_READ_INTERVAL_MS: "1000"
"""
