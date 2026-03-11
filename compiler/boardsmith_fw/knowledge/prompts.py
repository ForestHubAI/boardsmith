# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLM prompts for structured datasheet extraction.

Each prompt targets a specific section of a datasheet and instructs the LLM
to return well-formed JSON that maps directly to our ComponentKnowledge model.
"""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are an expert embedded systems engineer who extracts structured data \
from IC datasheets. You return ONLY valid JSON — no markdown, no explanation, \
no commentary. If a field cannot be determined from the provided text, \
use null or omit it.
"""

EXTRACTION_PROMPT = """\
Extract structured component knowledge from this datasheet text.

Return a single JSON object with EXACTLY these fields:

{{
  "name": "<component name, e.g. BME280>",
  "manufacturer": "<manufacturer name>",
  "mpn": "<manufacturer part number>",
  "description": "<one-line description>",
  "category": "<sensor|display|memory|rf_transceiver|motor_driver|rtc|io_expander|dac|ethernet|can_controller|other>",
  "interface": "<I2C|SPI|UART|GPIO|ANALOG|OTHER>",
  "i2c_address": "<default hex address like 0x76, or null if not I2C>",
  "spi_mode": <0-3 or null if not SPI>,
  "registers": [
    {{
      "address": "<hex address, e.g. 0xD0>",
      "name": "<register name>",
      "description": "<short description>",
      "fields": [
        {{
          "name": "<field name>",
          "bits": "<bit range, e.g. 7:5 or 3>",
          "description": "<field description>",
          "default_value": "<default bits or empty>"
        }}
      ]
    }}
  ],
  "init_sequence": [
    {{
      "order": <1-based>,
      "reg_addr": "<hex register address or empty>",
      "value": "<hex value to write or empty>",
      "description": "<what this step does>",
      "delay_ms": <milliseconds to wait or null>
    }}
  ],
  "timing_constraints": [
    {{
      "parameter": "<parameter name, e.g. I2C clock frequency>",
      "min": "<min value or empty>",
      "typical": "<typical value or empty>",
      "max": "<max value or empty>",
      "unit": "<Hz, ms, us, mA, V, etc.>"
    }}
  ],
  "notes": ["<important usage notes>"]
}}

RULES:
- Extract ALL registers you can find in the text, especially:
  chip ID / WHO_AM_I, control/config registers, status registers, data output registers
- For init_sequence, create a practical startup sequence:
  1. Reset (if available)
  2. Wait for reset
  3. Verify chip ID (if available)
  4. Configure operating mode
  5. Enable measurements/features
- For timing_constraints, include:
  bus clock frequency (max), startup/power-on time, conversion/measurement time,
  supply current (typical and max)
- Use hex addresses with 0x prefix
- Register fields are optional — only include if bit positions are clear
- If the chip uses a command-based interface (not registers), use the command
  byte as the "address" field

DATASHEET TEXT:
{datasheet_text}
"""

# Shorter prompt for when we only have partial text (e.g. a register table)
REGISTER_EXTRACTION_PROMPT = """\
Extract register information from this datasheet excerpt.

Return a JSON array of register objects:
[
  {{
    "address": "<hex>",
    "name": "<name>",
    "description": "<description>",
    "fields": [
      {{"name": "<field>", "bits": "<range>", "description": "<desc>", "default_value": "<val>"}}
    ]
  }}
]

TEXT:
{text}
"""

TIMING_EXTRACTION_PROMPT = """\
Extract timing and electrical specifications from this datasheet excerpt.

Return a JSON array of timing constraint objects:
[
  {{
    "parameter": "<parameter name>",
    "min": "<min value or empty>",
    "typical": "<typical value or empty>",
    "max": "<max value or empty>",
    "unit": "<unit>"
  }}
]

Include: bus frequencies, startup times, conversion times, supply current/voltage.

TEXT:
{text}
"""
