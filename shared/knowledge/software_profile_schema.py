# SPDX-License-Identifier: AGPL-3.0-or-later
"""Device Software Profile schema — Software Knowledge Layer (Domain 13).

Per-component software knowledge: which drivers exist, their quality,
license compatibility, ecosystem support, and resource footprint.

This is NOT just "store a URL". This is a Software Knowledge Graph.

See DBroadmap.md for the full specification.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SourceType(str, Enum):
    git = "git"
    archive = "archive"
    package_registry = "package_registry"


class IntegrationType(str, Enum):
    source_embed = "source_embed"         # Code copied into project
    git_submodule = "git_submodule"       # Repo as submodule
    package_manager = "package_manager"   # PlatformIO / Zephyr West / idf.py
    wrapper_only = "wrapper_only"         # Only API wrapper, user supplies driver


class MaintenanceStatus(str, Enum):
    active = "active"
    maintained = "maintained"
    stale = "stale"
    deprecated = "deprecated"
    archived = "archived"


class LicenseCompatibility(str, Enum):
    """Compatibility with AGPL-3.0 (Boardsmith's license)."""
    compatible = "compatible"           # MIT, BSD, Apache-2.0
    conditional = "conditional"         # LGPL — dynamic linking ok, source_embed critical
    incompatible = "incompatible"       # Proprietary, NDA
    copyleft_warning = "copyleft_warning"  # GPL — only if end project GPL-compatible


# ---------------------------------------------------------------------------
# Driver Quality Score
# ---------------------------------------------------------------------------

class DriverFootprint(BaseModel):
    """Resource consumption — critical for embedded."""
    flash_bytes: int | None = None
    ram_bytes: int | None = None
    stack_usage_bytes: int | None = None


class DriverQualityScore(BaseModel):
    """Computed from measurable factors.

    Formula:
        quality_score = (
            test_pass_rate      × 0.30
          + maintenance_factor  × 0.25
          + ecosystem_support   × 0.20
          + community_adoption  × 0.10
          + license_score       × 0.15
        )
    """
    test_pass_rate: float = Field(ge=0.0, le=1.0, default=0.5)
    maintenance_factor: float = Field(ge=0.0, le=1.0, default=0.5)
    ecosystem_support: float = Field(ge=0.0, le=1.0, default=0.5)
    community_adoption: float = Field(ge=0.0, le=1.0, default=0.5)
    license_score: float = Field(ge=0.0, le=1.0, default=1.0)

    @property
    def composite(self) -> float:
        return (
            self.test_pass_rate * 0.30
            + self.maintenance_factor * 0.25
            + self.ecosystem_support * 0.20
            + self.community_adoption * 0.10
            + self.license_score * 0.15
        )


# ---------------------------------------------------------------------------
# Driver Option
# ---------------------------------------------------------------------------

class DriverOption(BaseModel):
    """A concrete driver source for a component."""
    name: str                              # "Bosch Official C Driver"
    key: str                               # "bosch_official" — short identifier
    source_type: SourceType
    source_url: str
    license: str                           # "BSD-3-Clause" | "MIT" | "Apache-2.0"
    license_compatibility: LicenseCompatibility = LicenseCompatibility.compatible
    maturity: str = "medium"               # "high" | "medium" | "low" | "experimental"
    ecosystem: list[str] = Field(default_factory=list)   # ["baremetal", "Zephyr", "ESP-IDF"]
    supported_targets: list[str] = Field(default_factory=list)  # ["esp32", "stm32", "rp2040"]
    integration_type: IntegrationType = IntegrationType.source_embed
    last_checked_version: str = ""
    last_checked_date: str = ""            # ISO date
    maintenance_status: MaintenanceStatus = MaintenanceStatus.active
    known_issues: list[str] = Field(default_factory=list)
    footprint: DriverFootprint | None = None
    quality_score: DriverQualityScore | None = None

    @property
    def computed_quality(self) -> float:
        if self.quality_score:
            return self.quality_score.composite
        return 0.5


# ---------------------------------------------------------------------------
# Device Software Profile
# ---------------------------------------------------------------------------

class DeviceSoftwareProfile(BaseModel):
    """Software knowledge per component — which drivers exist, how to integrate them.

    Layer 2 of the three-layer architecture.
    """
    component_mpn: str                     # Reference to ComponentEntry
    protocol: str                          # "I2C" | "SPI" | "UART" | "GPIO"
    driver_options: list[DriverOption] = Field(default_factory=list)
    default_driver_key: str | None = None  # Recommended default per ecosystem
    api_contract_id: str | None = None     # Reference to LogicalDriverContract

    def get_default_driver(self) -> DriverOption | None:
        """Return the default driver option, if set."""
        if not self.default_driver_key:
            return self.driver_options[0] if self.driver_options else None
        for opt in self.driver_options:
            if opt.key == self.default_driver_key:
                return opt
        return None

    def get_drivers_for_target(self, target: str) -> list[DriverOption]:
        """Filter driver options that support a specific target."""
        return [d for d in self.driver_options if target in d.supported_targets]

    def get_compatible_drivers(self) -> list[DriverOption]:
        """Return only license-compatible drivers."""
        return [
            d for d in self.driver_options
            if d.license_compatibility == LicenseCompatibility.compatible
        ]
