# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reference Design Template schema — Hardware Knowledge Layer.

N templates per MCU family. Each template captures a complete power topology,
debug header, peripheral pattern set, and layout constraints for a specific
application context (e.g. USB dev board, battery sensor node, industrial hub).

See DBroadmap.md for the full specification.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .mcu_profile_schema import (
    DebugInterface,
    LayoutConstraints,
    MandatoryComponent,
    PeripheralPatterns,
    PinMap,
    PowerInputPattern,
    ProtectionSpec,
    RegulatorOption,
)


class TemplateIdentity(BaseModel):
    """Which MCU families and application contexts this template covers."""
    name: str                          # "USB Dev Board", "Battery Sensor Node"
    description: str = ""
    applicable_families: list[str]     # ["ESP32-S3", "STM32G4", "RP2040"]
    application_context: str = ""      # "prototyping", "industrial", "wearable"
    board_size_mm: tuple[float, float] | None = None   # width × height


class PowerTopology(BaseModel):
    """Complete power supply chain for this template."""
    input_pattern: PowerInputPattern
    regulators: list[RegulatorOption] = Field(default_factory=list)
    protection: list[ProtectionSpec] = Field(default_factory=list)
    notes: str = ""


class ReferenceDesignTemplate(BaseModel):
    """A complete reference design template for a given MCU + application context.

    Captures: HOW to use the MCU in a specific context.
    The MCU Device Profile captures WHAT the MCU is.
    """
    identity: TemplateIdentity

    # Power supply design
    power: PowerTopology | None = None

    # Pin assignments for this context
    pin_assignments: list[PinMap] = Field(default_factory=list)

    # Debug interface configuration
    debug: DebugInterface | None = None

    # Which peripherals are active in this template
    peripherals: PeripheralPatterns = Field(default_factory=PeripheralPatterns)

    # Additional mandatory components beyond MCU profile
    additional_components: list[MandatoryComponent] = Field(default_factory=list)

    # Layout constraints specific to this template
    layout: LayoutConstraints = Field(default_factory=LayoutConstraints)

    # BOM cost estimate
    estimated_bom_cost_usd: float | None = None
