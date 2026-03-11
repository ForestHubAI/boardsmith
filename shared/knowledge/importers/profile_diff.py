# SPDX-License-Identifier: AGPL-3.0-or-later
"""Profile Diff-Validation — compare imported vs hand-curated MCU profiles.

When importing MCU data from SDK parsers (CubeMX XML, ESP-IDF headers,
Pico SDK), we need to validate the auto-imported data against existing
hand-curated profiles. This module provides:

  1. Structural diff — detect added/removed/changed fields
  2. Pin-level diff — compare pin definitions, alt functions
  3. Domain-level summaries — per-domain comparison report
  4. Confidence scoring — how much the import matches existing data

Usage:
  diff = diff_profiles(imported_profile, existing_profile)
  print(diff.summary)
  # → "42 pins match, 3 pins differ (alt functions), 2 new pins found"
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from shared.knowledge.mcu_profile_schema import MCUDeviceProfile, PinDefinition

log = logging.getLogger(__name__)


class DiffSeverity(str, Enum):
    info = "info"           # New data added, no conflict
    warning = "warning"     # Data differs, but not critical
    error = "error"         # Critical data mismatch


class DiffCategory(str, Enum):
    pin_added = "pin_added"
    pin_removed = "pin_removed"
    pin_type_changed = "pin_type_changed"
    alt_function_added = "alt_function_added"
    alt_function_removed = "alt_function_removed"
    alt_function_changed = "alt_function_changed"
    power_domain_added = "power_domain_added"
    power_domain_removed = "power_domain_removed"
    power_domain_changed = "power_domain_changed"
    identity_changed = "identity_changed"
    clock_changed = "clock_changed"
    boot_changed = "boot_changed"
    peripheral_changed = "peripheral_changed"


@dataclass
class DiffEntry:
    """A single difference between two profiles."""
    category: DiffCategory
    severity: DiffSeverity
    field_path: str         # e.g. "pinout.pins[PA0].alt_functions"
    existing_value: str     # String representation of existing value
    imported_value: str     # String representation of imported value
    message: str


@dataclass
class ProfileDiffReport:
    """Complete diff report between two profiles."""
    imported_mpn: str
    existing_mpn: str
    entries: list[DiffEntry] = field(default_factory=list)

    # Summary statistics
    pins_matching: int = 0
    pins_differing: int = 0
    pins_added: int = 0
    pins_removed: int = 0
    alt_functions_added: int = 0
    alt_functions_removed: int = 0
    domains_matching: int = 0
    domains_differing: int = 0

    @property
    def match_score(self) -> float:
        """0.0–1.0 score of how well imported data matches existing."""
        total_checks = max(
            self.pins_matching + self.pins_differing + self.pins_added + self.pins_removed,
            1,
        )
        return self.pins_matching / total_checks

    @property
    def has_errors(self) -> bool:
        return any(e.severity == DiffSeverity.error for e in self.entries)

    @property
    def has_warnings(self) -> bool:
        return any(e.severity == DiffSeverity.warning for e in self.entries)

    @property
    def summary(self) -> str:
        """Human-readable summary of the diff."""
        parts = []
        if self.pins_matching:
            parts.append(f"{self.pins_matching} pins match")
        if self.pins_differing:
            parts.append(f"{self.pins_differing} pins differ")
        if self.pins_added:
            parts.append(f"{self.pins_added} new pins")
        if self.pins_removed:
            parts.append(f"{self.pins_removed} pins removed")
        if self.alt_functions_added:
            parts.append(f"{self.alt_functions_added} alt-functions added")
        if self.alt_functions_removed:
            parts.append(f"{self.alt_functions_removed} alt-functions removed")

        errors = sum(1 for e in self.entries if e.severity == DiffSeverity.error)
        warnings = sum(1 for e in self.entries if e.severity == DiffSeverity.warning)
        if errors:
            parts.append(f"{errors} errors")
        if warnings:
            parts.append(f"{warnings} warnings")

        return ", ".join(parts) if parts else "no differences"


# ---------------------------------------------------------------------------
# Pin-level comparison
# ---------------------------------------------------------------------------

def _diff_pins(
    imported_pins: list[PinDefinition],
    existing_pins: list[PinDefinition],
    entries: list[DiffEntry],
) -> tuple[int, int, int, int, int, int]:
    """Compare pin lists and append diff entries.

    Returns (matching, differing, added, removed, af_added, af_removed)
    """
    # Index by pin_name
    existing_by_name = {p.pin_name: p for p in existing_pins}
    imported_by_name = {p.pin_name: p for p in imported_pins}

    matching = 0
    differing = 0
    added = 0
    removed = 0
    af_added = 0
    af_removed = 0

    # Check imported pins against existing
    for name, imp_pin in imported_by_name.items():
        if name not in existing_by_name:
            added += 1
            entries.append(DiffEntry(
                category=DiffCategory.pin_added,
                severity=DiffSeverity.info,
                field_path=f"pinout.pins[{name}]",
                existing_value="<not present>",
                imported_value=f"{imp_pin.pin_type.value} pin at position {imp_pin.pin_number}",
                message=f"New pin {name} found in imported data",
            ))
            continue

        ext_pin = existing_by_name[name]
        pin_matches = True

        # Compare pin type
        if imp_pin.pin_type != ext_pin.pin_type:
            pin_matches = False
            entries.append(DiffEntry(
                category=DiffCategory.pin_type_changed,
                severity=DiffSeverity.warning,
                field_path=f"pinout.pins[{name}].pin_type",
                existing_value=ext_pin.pin_type.value,
                imported_value=imp_pin.pin_type.value,
                message=f"Pin {name} type differs: existing={ext_pin.pin_type.value}, imported={imp_pin.pin_type.value}",
            ))

        # Compare alt functions
        ext_af_names = {af.function for af in ext_pin.alt_functions}
        imp_af_names = {af.function for af in imp_pin.alt_functions}

        new_afs = imp_af_names - ext_af_names
        lost_afs = ext_af_names - imp_af_names

        for af_name in new_afs:
            af_added += 1
            entries.append(DiffEntry(
                category=DiffCategory.alt_function_added,
                severity=DiffSeverity.info,
                field_path=f"pinout.pins[{name}].alt_functions",
                existing_value="<not present>",
                imported_value=af_name,
                message=f"Pin {name}: new alt function {af_name}",
            ))

        for af_name in lost_afs:
            af_removed += 1
            entries.append(DiffEntry(
                category=DiffCategory.alt_function_removed,
                severity=DiffSeverity.warning,
                field_path=f"pinout.pins[{name}].alt_functions",
                existing_value=af_name,
                imported_value="<not present>",
                message=f"Pin {name}: existing alt function {af_name} not in import",
            ))

        if new_afs or lost_afs:
            pin_matches = False

        if pin_matches:
            matching += 1
        else:
            differing += 1

    # Check for removed pins (in existing but not in imported)
    for name in existing_by_name:
        if name not in imported_by_name:
            removed += 1
            entries.append(DiffEntry(
                category=DiffCategory.pin_removed,
                severity=DiffSeverity.warning,
                field_path=f"pinout.pins[{name}]",
                existing_value=f"{existing_by_name[name].pin_type.value} pin",
                imported_value="<not present>",
                message=f"Existing pin {name} not found in imported data",
            ))

    return matching, differing, added, removed, af_added, af_removed


# ---------------------------------------------------------------------------
# Domain-level comparison
# ---------------------------------------------------------------------------

def _diff_power_domains(
    imported: MCUDeviceProfile,
    existing: MCUDeviceProfile,
    entries: list[DiffEntry],
) -> tuple[int, int]:
    """Compare power domains. Returns (matching, differing)."""
    ext_domains = {d.name: d for d in existing.power.power_domains}
    imp_domains = {d.name: d for d in imported.power.power_domains}

    matching = 0
    differing = 0

    for name, imp_d in imp_domains.items():
        if name not in ext_domains:
            differing += 1
            entries.append(DiffEntry(
                category=DiffCategory.power_domain_added,
                severity=DiffSeverity.info,
                field_path=f"power.power_domains[{name}]",
                existing_value="<not present>",
                imported_value=f"{imp_d.nominal_voltage}V, {imp_d.max_current_draw_ma}mA",
                message=f"New power domain {name} found in imported data",
            ))
            continue

        ext_d = ext_domains[name]
        if abs(imp_d.nominal_voltage - ext_d.nominal_voltage) > 0.01:
            differing += 1
            entries.append(DiffEntry(
                category=DiffCategory.power_domain_changed,
                severity=DiffSeverity.error,
                field_path=f"power.power_domains[{name}].nominal_voltage",
                existing_value=str(ext_d.nominal_voltage),
                imported_value=str(imp_d.nominal_voltage),
                message=f"Power domain {name} voltage mismatch: existing={ext_d.nominal_voltage}V, imported={imp_d.nominal_voltage}V",
            ))
        else:
            matching += 1

    for name in ext_domains:
        if name not in imp_domains:
            differing += 1
            entries.append(DiffEntry(
                category=DiffCategory.power_domain_removed,
                severity=DiffSeverity.warning,
                field_path=f"power.power_domains[{name}]",
                existing_value=f"{ext_domains[name].nominal_voltage}V",
                imported_value="<not present>",
                message=f"Existing power domain {name} not in imported data",
            ))

    return matching, differing


def _diff_identity(
    imported: MCUDeviceProfile,
    existing: MCUDeviceProfile,
    entries: list[DiffEntry],
) -> None:
    """Compare identity fields."""
    imp_id = imported.identity
    ext_id = existing.identity

    if imp_id.family != ext_id.family:
        entries.append(DiffEntry(
            category=DiffCategory.identity_changed,
            severity=DiffSeverity.error,
            field_path="identity.family",
            existing_value=ext_id.family,
            imported_value=imp_id.family,
            message=f"Family mismatch: existing={ext_id.family}, imported={imp_id.family}",
        ))

    if imp_id.pin_count != ext_id.pin_count and imp_id.pin_count > 0 and ext_id.pin_count > 0:
        entries.append(DiffEntry(
            category=DiffCategory.identity_changed,
            severity=DiffSeverity.warning,
            field_path="identity.pin_count",
            existing_value=str(ext_id.pin_count),
            imported_value=str(imp_id.pin_count),
            message=f"Pin count differs: existing={ext_id.pin_count}, imported={imp_id.pin_count}",
        ))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def diff_profiles(
    imported: MCUDeviceProfile,
    existing: MCUDeviceProfile,
) -> ProfileDiffReport:
    """Compare an imported profile against an existing hand-curated one.

    Args:
        imported: Profile generated by SDK parser
        existing: Hand-curated profile from the knowledge DB

    Returns:
        ProfileDiffReport with detailed comparison
    """
    report = ProfileDiffReport(
        imported_mpn=imported.identity.mpn,
        existing_mpn=existing.identity.mpn,
    )

    # Identity diff
    _diff_identity(imported, existing, report.entries)

    # Pin-level diff
    (
        report.pins_matching,
        report.pins_differing,
        report.pins_added,
        report.pins_removed,
        report.alt_functions_added,
        report.alt_functions_removed,
    ) = _diff_pins(
        imported.pinout.pins,
        existing.pinout.pins,
        report.entries,
    )

    # Power domain diff
    report.domains_matching, report.domains_differing = _diff_power_domains(
        imported, existing, report.entries,
    )

    log.info(
        "Profile diff %s vs %s: %s",
        imported.identity.mpn,
        existing.identity.mpn,
        report.summary,
    )

    return report


def validate_import(
    imported: MCUDeviceProfile,
    existing: MCUDeviceProfile | None = None,
    min_match_score: float = 0.5,
) -> tuple[bool, str]:
    """Validate an imported profile, optionally against existing data.

    Args:
        imported: Profile to validate
        existing: Optional existing profile to diff against
        min_match_score: Minimum match score (0.0–1.0) for approval

    Returns:
        (approved, reason) tuple
    """
    # Basic structural validation
    if not imported.identity.mpn:
        return False, "Missing MPN in identity"

    if not imported.pinout.pins:
        return False, "No pins found in imported profile"

    if not imported.identity.vendor:
        return False, "Missing vendor in identity"

    # If no existing profile, just validate structure
    if existing is None:
        return True, f"New profile for {imported.identity.mpn} — no existing data to compare"

    # Compare against existing
    report = diff_profiles(imported, existing)

    if report.has_errors:
        error_count = sum(1 for e in report.entries if e.severity == DiffSeverity.error)
        return False, f"Import has {error_count} error(s): {report.summary}"

    if report.match_score < min_match_score:
        return False, (
            f"Match score {report.match_score:.2f} below threshold {min_match_score:.2f}: "
            f"{report.summary}"
        )

    return True, f"Import approved (score={report.match_score:.2f}): {report.summary}"
