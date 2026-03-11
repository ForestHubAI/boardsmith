# SPDX-License-Identifier: AGPL-3.0-or-later
"""Built-in component knowledge database.

Contains verified, hand-curated knowledge for common components.
This eliminates the need for datasheet extraction for well-known parts.

Components are organized by category in boardsmith_fw/knowledge/components/:
  - sensors.py:      Environmental, IMU, distance, light, current, ADC (~20 parts)
  - displays.py:     OLED, TFT LCD, LED drivers (~7 parts)
  - comms.py:        GNSS, LoRa, 2.4GHz, Ethernet, CAN (~8 parts)
  - memory.py:       SPI Flash, I2C EEPROM, SPI SRAM (~4 parts)
  - motor_power.py:  Stepper/DC motor drivers, PWM controllers (~4 parts)
  - misc.py:         RTC, GPIO expanders, DAC, I2C mux (~6 parts)
"""

from __future__ import annotations

from boardsmith_fw.knowledge.components.comms import REGISTRY as _COMMS
from boardsmith_fw.knowledge.components.displays import REGISTRY as _DISPLAYS
from boardsmith_fw.knowledge.components.memory import REGISTRY as _MEMORY
from boardsmith_fw.knowledge.components.misc import REGISTRY as _MISC
from boardsmith_fw.knowledge.components.motor_power import REGISTRY as _MOTOR_POWER
from boardsmith_fw.knowledge.components.sensors import REGISTRY as _SENSORS
from boardsmith_fw.models.component_knowledge import ComponentKnowledge

# ---------------------------------------------------------------------------
# Merged registry — all categories
# ---------------------------------------------------------------------------

_BUILTIN_REGISTRY: dict[str, callable] = {}
_BUILTIN_REGISTRY.update(_SENSORS)
_BUILTIN_REGISTRY.update(_DISPLAYS)
_BUILTIN_REGISTRY.update(_COMMS)
_BUILTIN_REGISTRY.update(_MEMORY)
_BUILTIN_REGISTRY.update(_MOTOR_POWER)
_BUILTIN_REGISTRY.update(_MISC)


def lookup_builtin(mpn: str) -> ComponentKnowledge | None:
    """Look up built-in knowledge by MPN. Returns a copy or None."""
    key = mpn.upper().strip()
    # Exact match
    if key in _BUILTIN_REGISTRY:
        return _BUILTIN_REGISTRY[key]()
    # Prefix match (e.g. "W25Q128JVSIQ" matches "W25Q128JV")
    for pattern, builder in sorted(_BUILTIN_REGISTRY.items(), key=lambda x: -len(x[0])):
        if key.startswith(pattern):
            return builder()
    return None


def list_builtin_mpns() -> list[str]:
    """List all MPNs with built-in knowledge."""
    return sorted(set(_BUILTIN_REGISTRY.keys()))


def count_unique_components() -> int:
    """Count unique component builder functions (not aliases)."""
    return len(set(id(fn) for fn in _BUILTIN_REGISTRY.values()))


def list_categories() -> dict[str, int]:
    """List component categories with counts."""
    return {
        "sensors": len(_SENSORS),
        "displays": len(_DISPLAYS),
        "comms": len(_COMMS),
        "memory": len(_MEMORY),
        "motor_power": len(_MOTOR_POWER),
        "misc": len(_MISC),
    }
