# SPDX-License-Identifier: AGPL-3.0-or-later
"""SCD41 CO2 Sensor — Device Software Profile."""
from shared.knowledge.software_profile_schema import (
    DeviceSoftwareProfile,
    DriverFootprint,
    DriverOption,
    DriverQualityScore,
    IntegrationType,
    LicenseCompatibility,
    MaintenanceStatus,
    SourceType,
)

PROFILE = DeviceSoftwareProfile(
    component_mpn="SCD41",
    protocol="I2C",
    default_driver_key="sensirion_official",
    api_contract_id="co2_sensor_v1",
    driver_options=[
        DriverOption(
            name="Sensirion Official I2C Driver",
            key="sensirion_official",
            source_type=SourceType.git,
            source_url="https://github.com/Sensirion/embedded-i2c-scd4x",
            license="BSD-3-Clause",
            license_compatibility=LicenseCompatibility.compatible,
            maturity="high",
            ecosystem=["baremetal", "ESP-IDF", "Pico-SDK"],
            supported_targets=["esp32", "stm32", "rp2040", "nrf52"],
            integration_type=IntegrationType.source_embed,
            last_checked_version="v1.0.0",
            last_checked_date="2026-01-15",
            maintenance_status=MaintenanceStatus.active,
            footprint=DriverFootprint(flash_bytes=6500, ram_bytes=256),
            quality_score=DriverQualityScore(
                test_pass_rate=0.95,
                maintenance_factor=0.90,
                ecosystem_support=0.80,
                community_adoption=0.60,
                license_score=1.0,
            ),
        ),
        DriverOption(
            name="Sensirion Arduino Library",
            key="sensirion_arduino",
            source_type=SourceType.git,
            source_url="https://github.com/Sensirion/arduino-i2c-scd4x",
            license="BSD-3-Clause",
            license_compatibility=LicenseCompatibility.compatible,
            maturity="high",
            ecosystem=["Arduino"],
            supported_targets=["esp32", "rp2040"],
            integration_type=IntegrationType.package_manager,
            last_checked_version="v0.4.0",
            last_checked_date="2026-01-15",
            maintenance_status=MaintenanceStatus.active,
            footprint=DriverFootprint(flash_bytes=9000, ram_bytes=512),
            quality_score=DriverQualityScore(
                test_pass_rate=0.90,
                maintenance_factor=0.85,
                ecosystem_support=0.35,
                community_adoption=0.55,
                license_score=1.0,
            ),
        ),
    ],
)

from shared.knowledge.software_profiles import register
register(PROFILE)
