# SPDX-License-Identifier: AGPL-3.0-or-later
"""Seed data package — aggregates all category modules into ALL_COMPONENTS."""
from __future__ import annotations

from knowledge.schema import ComponentEntry

from knowledge.seed import mcu, power, sensor, display, comms, memory, actuator, other

ALL_COMPONENTS: list[ComponentEntry] = (
    mcu.COMPONENTS
    + power.COMPONENTS
    + sensor.COMPONENTS
    + display.COMPONENTS
    + comms.COMPONENTS
    + memory.COMPONENTS
    + actuator.COMPONENTS
    + other.COMPONENTS
)

__all__ = ["ALL_COMPONENTS"]
