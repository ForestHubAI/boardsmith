# SPDX-License-Identifier: AGPL-3.0-or-later
"""MPU6050 IMU — Device Software Profile."""
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
    component_mpn="MPU6050",
    protocol="I2C",
    default_driver_key="invensense_empl",
    api_contract_id="imu_sensor_v1",
    driver_options=[
        DriverOption(
            name="InvenSense Embedded MotionDriver",
            key="invensense_empl",
            source_type=SourceType.git,
            source_url="https://github.com/jrowberg/i2cdevlib",
            license="MIT",
            license_compatibility=LicenseCompatibility.compatible,
            maturity="high",
            ecosystem=["baremetal", "Arduino", "ESP-IDF"],
            supported_targets=["esp32", "stm32", "rp2040"],
            integration_type=IntegrationType.source_embed,
            last_checked_version="master",
            last_checked_date="2026-01-15",
            maintenance_status=MaintenanceStatus.maintained,
            known_issues=["Legacy sensor — consider LSM6DS3/ICM-42688 for new designs"],
            footprint=DriverFootprint(flash_bytes=15000, ram_bytes=2048),
            quality_score=DriverQualityScore(
                test_pass_rate=0.80,
                maintenance_factor=0.60,
                ecosystem_support=0.70,
                community_adoption=0.95,
                license_score=1.0,
            ),
        ),
        DriverOption(
            name="Adafruit MPU6050 Library",
            key="adafruit",
            source_type=SourceType.git,
            source_url="https://github.com/adafruit/Adafruit_MPU6050",
            license="MIT",
            license_compatibility=LicenseCompatibility.compatible,
            maturity="high",
            ecosystem=["Arduino"],
            supported_targets=["esp32", "rp2040"],
            integration_type=IntegrationType.package_manager,
            last_checked_version="v2.2.6",
            last_checked_date="2026-01-15",
            maintenance_status=MaintenanceStatus.active,
            known_issues=["Arduino-only, requires Adafruit_Sensor"],
            footprint=DriverFootprint(flash_bytes=18000, ram_bytes=1024),
            quality_score=DriverQualityScore(
                test_pass_rate=0.85,
                maintenance_factor=0.85,
                ecosystem_support=0.40,
                community_adoption=0.85,
                license_score=1.0,
            ),
        ),
    ],
)

from shared.knowledge.software_profiles import register
register(PROFILE)
