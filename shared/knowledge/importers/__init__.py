# SPDX-License-Identifier: AGPL-3.0-or-later
"""SDK Parsers & Import Pipeline — Phase F Automation.

Provides parsers that convert vendor SDK data into MCUDeviceProfile objects:
  - STM32CubeMX XML → MCUProfile (pin tables, alt functions, power domains)
  - ESP-IDF soc/ headers → Pin signal maps
  - Pico SDK headers → RP2040 alt functions

Also provides:
  - SPDX-based license compatibility matrix
  - Profile diff-validation (imported vs hand-curated)
"""
