# SPDX-License-Identifier: AGPL-3.0-or-later
"""W25Q128 SPI Flash — Device Software Profile."""
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
    component_mpn="W25Q128",
    protocol="SPI",
    default_driver_key="generic_spiflash",
    api_contract_id="flash_storage_v1",
    driver_options=[
        DriverOption(
            name="Generic SPI Flash Driver",
            key="generic_spiflash",
            source_type=SourceType.git,
            source_url="https://github.com/Mbed-TLS/mbedtls",  # Often bundled with flash utils
            license="Apache-2.0",
            license_compatibility=LicenseCompatibility.compatible,
            maturity="high",
            ecosystem=["baremetal", "ESP-IDF", "Pico-SDK"],
            supported_targets=["esp32", "stm32", "rp2040"],
            integration_type=IntegrationType.source_embed,
            last_checked_version="v1.0.0",
            last_checked_date="2026-01-15",
            maintenance_status=MaintenanceStatus.active,
            footprint=DriverFootprint(flash_bytes=5000, ram_bytes=256),
            quality_score=DriverQualityScore(
                test_pass_rate=0.90,
                maintenance_factor=0.80,
                ecosystem_support=0.80,
                community_adoption=0.70,
                license_score=1.0,
            ),
        ),
        DriverOption(
            name="Adafruit SPIFlash Library",
            key="adafruit_spiflash",
            source_type=SourceType.git,
            source_url="https://github.com/adafruit/Adafruit_SPIFlash",
            license="MIT",
            license_compatibility=LicenseCompatibility.compatible,
            maturity="high",
            ecosystem=["Arduino"],
            supported_targets=["esp32", "rp2040"],
            integration_type=IntegrationType.package_manager,
            last_checked_version="v4.3.4",
            last_checked_date="2026-01-15",
            maintenance_status=MaintenanceStatus.active,
            known_issues=["Arduino-only, requires Adafruit_TinyUSB for USB MSC"],
            footprint=DriverFootprint(flash_bytes=15000, ram_bytes=2048),
            quality_score=DriverQualityScore(
                test_pass_rate=0.85,
                maintenance_factor=0.85,
                ecosystem_support=0.40,
                community_adoption=0.80,
                license_score=1.0,
            ),
        ),
        DriverOption(
            name="Zephyr SPI NOR Flash Driver",
            key="zephyr_intree",
            source_type=SourceType.package_registry,
            source_url="zephyr://drivers/flash/spi_nor",
            license="Apache-2.0",
            license_compatibility=LicenseCompatibility.compatible,
            maturity="high",
            ecosystem=["Zephyr"],
            supported_targets=["nrf52", "stm32"],
            integration_type=IntegrationType.package_manager,
            last_checked_version="v3.6.0",
            last_checked_date="2026-01-15",
            maintenance_status=MaintenanceStatus.active,
            quality_score=DriverQualityScore(
                test_pass_rate=0.95,
                maintenance_factor=0.95,
                ecosystem_support=0.40,
                community_adoption=0.65,
                license_score=1.0,
            ),
        ),
    ],
)

from shared.knowledge.software_profiles import register
register(PROFILE)
