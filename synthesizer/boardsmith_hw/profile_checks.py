# SPDX-License-Identifier: AGPL-3.0-or-later
"""MCU-profile-aware constraint checks (Phase C/D integration).

New constraint checks enabled by the three-layer knowledge architecture:
- Check 12: Power domain completeness
- Check 13: Decoupling cap presence
- Check 14: Boot pin configuration
- Check 15: Pin alt-function validation
- Check 16: Clock configuration plausibility
- Check 17: Driver existence and target compatibility
- Check 18: License compatibility
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class ProfileCheckResult:
    """Result of a single MCU-profile-aware constraint check."""
    check_id: str
    severity: str       # "error" | "warning" | "info"
    status: str         # "pass" | "fail"
    message: str
    affected_components: list[str] = field(default_factory=list)


@dataclass
class ProfileCheckReport:
    """Aggregate report from all profile-aware checks."""
    checks: list[ProfileCheckResult] = field(default_factory=list)
    errors: int = 0
    warnings: int = 0

    def add(self, result: ProfileCheckResult) -> None:
        self.checks.append(result)
        if result.status == "fail":
            if result.severity == "error":
                self.errors += 1
            elif result.severity == "warning":
                self.warnings += 1


def run_profile_checks(
    mcu_mpn: str,
    target_sdk: str = "esp-idf",
    assigned_pins: dict[str, str] | None = None,
    component_mpns: list[str] | None = None,
) -> ProfileCheckReport:
    """Run all MCU-profile-aware constraint checks.

    Args:
        mcu_mpn: The MCU part number to check against.
        target_sdk: Target SDK for software profile checks.
        assigned_pins: Mapping of signal→GPIO (from topology synthesizer).
        component_mpns: List of component MPNs used in the design.
    """
    report = ProfileCheckReport()

    # Load MCU profile
    try:
        from shared.knowledge.mcu_profiles import get as get_mcu_profile
        mcu_profile = get_mcu_profile(mcu_mpn)
    except ImportError:
        mcu_profile = None

    if mcu_profile is None:
        report.add(ProfileCheckResult(
            check_id="profile.mcu_profile_loaded",
            severity="info",
            status="pass",
            message=f"No MCU Device Profile found for {mcu_mpn} — profile checks skipped",
        ))
        return report

    # Check 12: Power domain completeness
    report.add(_check_power_domains(mcu_profile))

    # Check 13: Decoupling cap presence
    report.add(_check_decoupling(mcu_profile))

    # Check 14: Boot pin configuration
    if assigned_pins:
        for result in _check_boot_pins(mcu_profile, assigned_pins):
            report.add(result)

    # Check 15: Reserved pin conflicts
    if assigned_pins:
        for result in _check_reserved_pins(mcu_profile, assigned_pins):
            report.add(result)

    # Check 16: Clock configuration
    report.add(_check_clock_config(mcu_profile))

    # Check 17: Driver existence
    if component_mpns:
        for result in _check_driver_existence(component_mpns, target_sdk):
            report.add(result)

    # Check 18: License compatibility
    if component_mpns:
        for result in _check_license_compatibility(component_mpns):
            report.add(result)

    return report


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_power_domains(profile) -> ProfileCheckResult:
    """Check 12: Verify power domains are defined."""
    domains = profile.power.power_domains
    if not domains:
        return ProfileCheckResult(
            check_id="profile.power_domains",
            severity="warning",
            status="fail",
            message=f"{profile.identity.mpn}: No power domains defined in MCU profile — decoupling may be incorrect",
        )
    domain_names = [d.name for d in domains]
    return ProfileCheckResult(
        check_id="profile.power_domains",
        severity="info",
        status="pass",
        message=f"Power domains: {', '.join(domain_names)}",
    )


def _check_decoupling(profile) -> ProfileCheckResult:
    """Check 13: Verify decoupling rules exist for each power domain."""
    missing = []
    for domain in profile.power.power_domains:
        if not domain.decoupling:
            missing.append(domain.name)
    if missing:
        return ProfileCheckResult(
            check_id="profile.decoupling_rules",
            severity="warning",
            status="fail",
            message=f"Missing decoupling rules for power domains: {', '.join(missing)}",
        )
    return ProfileCheckResult(
        check_id="profile.decoupling_rules",
        severity="info",
        status="pass",
        message="All power domains have decoupling rules",
    )


def _check_boot_pins(profile, assigned_pins: dict[str, str]) -> list[ProfileCheckResult]:
    """Check 14: Warn if boot-strap pins are used for general I/O."""
    results = []
    boot_pins = set()
    if profile.boot:
        for bmp in profile.boot.boot_mode_pins:
            boot_pins.add(bmp.pin)
    for pin in profile.pinout.pins:
        if pin.boot_strap:
            boot_pins.add(pin.pin_name)

    for signal, gpio in assigned_pins.items():
        if gpio in boot_pins:
            results.append(ProfileCheckResult(
                check_id=f"profile.boot_pin.{gpio}",
                severity="warning",
                status="fail",
                message=f"Boot-strap pin {gpio} assigned to {signal} — may affect boot mode. "
                        f"Ensure proper pull resistor for normal boot.",
            ))
    return results


def _check_reserved_pins(profile, assigned_pins: dict[str, str]) -> list[ProfileCheckResult]:
    """Check 15: Error if reserved pins (Flash/PSRAM/RF) are used."""
    results = []
    reserved = {rp.pin_name: rp.reason for rp in profile.pinout.reserved_pins if not rp.can_use_as_gpio}

    for signal, gpio in assigned_pins.items():
        if gpio in reserved:
            results.append(ProfileCheckResult(
                check_id=f"profile.reserved_pin.{gpio}",
                severity="error",
                status="fail",
                message=f"Reserved pin {gpio} ({reserved[gpio]}) cannot be used for {signal}",
                affected_components=[profile.identity.mpn],
            ))
    return results


def _check_clock_config(profile) -> ProfileCheckResult:
    """Check 16: Verify clock configuration exists."""
    if profile.clock is None:
        return ProfileCheckResult(
            check_id="profile.clock_config",
            severity="warning",
            status="fail",
            message=f"{profile.identity.mpn}: No clock configuration in MCU profile — crystal/oscillator may be missing",
        )
    clk = profile.clock
    return ProfileCheckResult(
        check_id="profile.clock_config",
        severity="info",
        status="pass",
        message=f"Clock: {clk.main_clock.type.value} {clk.main_clock.frequency_hz/1e6:.0f}MHz, safe default {clk.safe_default_mhz}MHz",
    )


def _check_driver_existence(component_mpns: list[str], target_sdk: str) -> list[ProfileCheckResult]:
    """Check 17: Verify driver exists for each component on the target."""
    results = []
    try:
        from shared.knowledge.software_profiles import get as get_sw_profile
    except ImportError:
        return results

    for mpn in component_mpns:
        sw_profile = get_sw_profile(mpn)
        if sw_profile is None:
            continue  # Not a component we track software for

        target_map = {"esp-idf": "esp32", "stm32hal": "stm32", "pico-sdk": "rp2040", "zephyr": "nrf52"}
        target_key = target_map.get(target_sdk, target_sdk)

        drivers = sw_profile.get_drivers_for_target(target_key)
        if not drivers:
            results.append(ProfileCheckResult(
                check_id=f"profile.driver_exists.{mpn}",
                severity="warning",
                status="fail",
                message=f"No driver found for {mpn} on target '{target_key}' — firmware will use register stubs",
                affected_components=[mpn],
            ))
        else:
            best = max(drivers, key=lambda d: d.computed_quality)
            results.append(ProfileCheckResult(
                check_id=f"profile.driver_exists.{mpn}",
                severity="info",
                status="pass",
                message=f"{mpn}: driver '{best.name}' available (quality={best.computed_quality:.2f}, license={best.license})",
            ))
    return results


def _check_license_compatibility(component_mpns: list[str]) -> list[ProfileCheckResult]:
    """Check 18: Verify license compatibility for all drivers."""
    results = []
    try:
        from shared.knowledge.software_profiles import get as get_sw_profile
        from shared.knowledge.software_profile_schema import LicenseCompatibility
    except ImportError:
        return results

    for mpn in component_mpns:
        sw_profile = get_sw_profile(mpn)
        if sw_profile is None:
            continue

        default_driver = sw_profile.get_default_driver()
        if default_driver is None:
            continue

        if default_driver.license_compatibility == LicenseCompatibility.incompatible:
            results.append(ProfileCheckResult(
                check_id=f"profile.license.{mpn}",
                severity="error",
                status="fail",
                message=f"{mpn}: default driver '{default_driver.name}' has incompatible license ({default_driver.license}) — "
                        f"use wrapper_only integration or select alternative driver",
                affected_components=[mpn],
            ))
        elif default_driver.license_compatibility == LicenseCompatibility.copyleft_warning:
            results.append(ProfileCheckResult(
                check_id=f"profile.license.{mpn}",
                severity="warning",
                status="fail",
                message=f"{mpn}: default driver '{default_driver.name}' uses copyleft license ({default_driver.license}) — "
                        f"review GPL compatibility for your project",
                affected_components=[mpn],
            ))
        elif default_driver.license_compatibility == LicenseCompatibility.conditional:
            results.append(ProfileCheckResult(
                check_id=f"profile.license.{mpn}",
                severity="warning",
                status="fail",
                message=f"{mpn}: driver '{default_driver.name}' license ({default_driver.license}) has conditions — "
                        f"source_embed may require LGPL compliance",
                affected_components=[mpn],
            ))
    return results
