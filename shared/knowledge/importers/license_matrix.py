# SPDX-License-Identifier: AGPL-3.0-or-later
"""SPDX-based License Compatibility Matrix.

Deterministic license checking for the Software Knowledge Layer.
Evaluates compatibility of driver/library licenses with Boardsmith's AGPL-3.0
license and determines whether a given integration type is allowed.

Rules (from DBroadmap.md):
  MIT / BSD-2 / BSD-3 / Apache-2.0  → compatible (all integration types)
  LGPL-2.1 / LGPL-3.0               → conditional (dynamic linking ok, source_embed critical)
  GPL-2.0 / GPL-3.0                 → copyleft_warning (only if end project GPL-compatible)
  Proprietary / NDA                  → incompatible (wrapper_only only)

Usage:
  result = check_license_compatibility("MIT", "source_embed")
  # → LicenseCheckResult(compatible=True, level="compatible", ...)

  results = audit_driver_licenses(software_profile)
  # → list of LicenseCheckResult per driver option
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums and types
# ---------------------------------------------------------------------------

class CompatibilityLevel(str, Enum):
    """License compatibility level with AGPL-3.0."""
    compatible = "compatible"           # Full green — all integration types ok
    conditional = "conditional"         # Yellow — some integration types restricted
    copyleft_warning = "copyleft_warning"  # Orange — only if end project is GPL-compatible
    incompatible = "incompatible"       # Red — wrapper_only or reject


class IntegrationType(str, Enum):
    """How a library is integrated into the generated project."""
    source_embed = "source_embed"
    git_submodule = "git_submodule"
    package_manager = "package_manager"
    wrapper_only = "wrapper_only"


@dataclass
class LicenseCheckResult:
    """Result of a license compatibility check."""
    spdx_id: str
    integration_type: str
    level: CompatibilityLevel
    allowed: bool
    message: str
    action: str  # "green", "yellow_warning", "orange_warning", "red_block"


# ---------------------------------------------------------------------------
# SPDX License Database
# ---------------------------------------------------------------------------

# Canonical SPDX ID → (CompatibilityLevel, human-readable name)
_LICENSE_DB: dict[str, tuple[CompatibilityLevel, str]] = {
    # Permissive — fully compatible
    "MIT": (CompatibilityLevel.compatible, "MIT License"),
    "BSD-2-Clause": (CompatibilityLevel.compatible, "BSD 2-Clause"),
    "BSD-3-Clause": (CompatibilityLevel.compatible, "BSD 3-Clause"),
    "Apache-2.0": (CompatibilityLevel.compatible, "Apache License 2.0"),
    "ISC": (CompatibilityLevel.compatible, "ISC License"),
    "Zlib": (CompatibilityLevel.compatible, "zlib License"),
    "BSL-1.0": (CompatibilityLevel.compatible, "Boost Software License 1.0"),
    "Unlicense": (CompatibilityLevel.compatible, "The Unlicense"),
    "CC0-1.0": (CompatibilityLevel.compatible, "Creative Commons Zero 1.0"),
    "0BSD": (CompatibilityLevel.compatible, "Zero-Clause BSD"),
    "MIT-0": (CompatibilityLevel.compatible, "MIT No Attribution"),

    # Weak copyleft — conditional
    "LGPL-2.1-only": (CompatibilityLevel.conditional, "LGPL 2.1"),
    "LGPL-2.1-or-later": (CompatibilityLevel.conditional, "LGPL 2.1+"),
    "LGPL-3.0-only": (CompatibilityLevel.conditional, "LGPL 3.0"),
    "LGPL-3.0-or-later": (CompatibilityLevel.conditional, "LGPL 3.0+"),
    "MPL-2.0": (CompatibilityLevel.conditional, "Mozilla Public License 2.0"),
    "EPL-2.0": (CompatibilityLevel.conditional, "Eclipse Public License 2.0"),

    # Strong copyleft — warning
    "GPL-2.0-only": (CompatibilityLevel.copyleft_warning, "GPL 2.0"),
    "GPL-2.0-or-later": (CompatibilityLevel.copyleft_warning, "GPL 2.0+"),
    "GPL-3.0-only": (CompatibilityLevel.copyleft_warning, "GPL 3.0"),
    "GPL-3.0-or-later": (CompatibilityLevel.copyleft_warning, "GPL 3.0+"),
    "AGPL-3.0-only": (CompatibilityLevel.compatible, "AGPL 3.0 (same license)"),
    "AGPL-3.0-or-later": (CompatibilityLevel.compatible, "AGPL 3.0+ (same license)"),

    # Proprietary / unknown
    "LicenseRef-Proprietary": (CompatibilityLevel.incompatible, "Proprietary License"),
    "LicenseRef-NDA": (CompatibilityLevel.incompatible, "NDA-restricted"),
}

# Aliases: common non-canonical names → canonical SPDX
_SPDX_ALIASES: dict[str, str] = {
    # Case-insensitive matching is done in normalize_spdx_id
    "MIT": "MIT",
    "BSD-2": "BSD-2-Clause",
    "BSD-3": "BSD-3-Clause",
    "BSD2": "BSD-2-Clause",
    "BSD3": "BSD-3-Clause",
    "APACHE2": "Apache-2.0",
    "APACHE-2": "Apache-2.0",
    "APACHE 2.0": "Apache-2.0",
    "LGPL2.1": "LGPL-2.1-only",
    "LGPL-2.1": "LGPL-2.1-only",
    "LGPL3": "LGPL-3.0-only",
    "LGPL-3": "LGPL-3.0-only",
    "LGPL-3.0": "LGPL-3.0-only",
    "GPL2": "GPL-2.0-only",
    "GPL-2": "GPL-2.0-only",
    "GPL-2.0": "GPL-2.0-only",
    "GPL3": "GPL-3.0-only",
    "GPL-3": "GPL-3.0-only",
    "GPL-3.0": "GPL-3.0-only",
    "AGPL3": "AGPL-3.0-only",
    "AGPL-3": "AGPL-3.0-only",
    "AGPL-3.0": "AGPL-3.0-only",
    "PROPRIETARY": "LicenseRef-Proprietary",
    "NDA": "LicenseRef-NDA",
    "COMMERCIAL": "LicenseRef-Proprietary",
    "MPL2": "MPL-2.0",
    "MPL-2": "MPL-2.0",
}


# Integration type restrictions per compatibility level
_INTEGRATION_RULES: dict[CompatibilityLevel, dict[str, bool]] = {
    CompatibilityLevel.compatible: {
        "source_embed": True,
        "git_submodule": True,
        "package_manager": True,
        "wrapper_only": True,
    },
    CompatibilityLevel.conditional: {
        "source_embed": False,   # LGPL source embed creates derivative work
        "git_submodule": True,   # Dynamic linking / separate compilation ok
        "package_manager": True, # Separate compilation ok
        "wrapper_only": True,
    },
    CompatibilityLevel.copyleft_warning: {
        "source_embed": False,
        "git_submodule": False,  # GPL requires entire project to be GPL
        "package_manager": False,
        "wrapper_only": True,    # Only wrapper API, user supplies the library
    },
    CompatibilityLevel.incompatible: {
        "source_embed": False,
        "git_submodule": False,
        "package_manager": False,
        "wrapper_only": True,    # Only wrapper_only for proprietary
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_spdx_id(license_str: str) -> str:
    """Normalize a license string to canonical SPDX identifier.

    Handles common aliases and case variations.

    Args:
        license_str: License name or SPDX ID (e.g. "MIT", "Apache 2.0", "GPL-3")

    Returns:
        Canonical SPDX identifier (e.g. "MIT", "Apache-2.0", "GPL-3.0-only")
    """
    cleaned = license_str.strip()

    # Direct match
    if cleaned in _LICENSE_DB:
        return cleaned

    # Check aliases (case-insensitive)
    upper = cleaned.upper().replace(" ", "").replace("_", "")
    for alias_key, canonical in _SPDX_ALIASES.items():
        if upper == alias_key.upper().replace(" ", "").replace("_", ""):
            return canonical

    # Try case-insensitive match against DB keys
    for db_key in _LICENSE_DB:
        if cleaned.upper() == db_key.upper():
            return db_key

    # Unknown — treat as potentially incompatible
    return cleaned


def get_compatibility_level(spdx_id: str) -> CompatibilityLevel:
    """Get the AGPL-3.0 compatibility level for a license.

    Args:
        spdx_id: Canonical SPDX identifier

    Returns:
        CompatibilityLevel enum value
    """
    canonical = normalize_spdx_id(spdx_id)
    if canonical in _LICENSE_DB:
        return _LICENSE_DB[canonical][0]

    # Unknown license — treat as incompatible to be safe
    log.warning("Unknown license SPDX ID: %s — treating as incompatible", spdx_id)
    return CompatibilityLevel.incompatible


def check_license_compatibility(
    license_str: str,
    integration_type: str = "source_embed",
) -> LicenseCheckResult:
    """Check if a license is compatible with a given integration type.

    Args:
        license_str: License name or SPDX ID
        integration_type: How the library is integrated (source_embed, git_submodule, etc.)

    Returns:
        LicenseCheckResult with compatibility assessment
    """
    canonical = normalize_spdx_id(license_str)
    level = get_compatibility_level(canonical)

    rules = _INTEGRATION_RULES.get(level, _INTEGRATION_RULES[CompatibilityLevel.incompatible])
    allowed = rules.get(integration_type, False)

    # Build human-readable message
    license_name = _LICENSE_DB.get(canonical, (level, canonical))[1]

    if level == CompatibilityLevel.compatible:
        message = f"{license_name} is fully compatible with AGPL-3.0."
        action = "green"
    elif level == CompatibilityLevel.conditional:
        if allowed:
            message = f"{license_name}: {integration_type} is acceptable (separate compilation)."
            action = "yellow_warning"
        else:
            message = (
                f"{license_name}: {integration_type} creates a derivative work — "
                f"requires LGPL compliance. Use package_manager or wrapper_only instead."
            )
            action = "yellow_warning"
    elif level == CompatibilityLevel.copyleft_warning:
        if allowed:
            message = f"{license_name}: only wrapper_only integration is safe without GPL-ifying the project."
            action = "orange_warning"
        else:
            message = (
                f"{license_name}: {integration_type} would require the entire project "
                f"to be GPL-licensed. Only wrapper_only is allowed."
            )
            action = "orange_warning"
    else:
        if allowed:
            message = f"{license_name}: only wrapper_only is permitted. User must supply library separately."
            action = "red_block"
        else:
            message = f"{license_name}: {integration_type} is NOT allowed. License is incompatible with AGPL-3.0."
            action = "red_block"

    return LicenseCheckResult(
        spdx_id=canonical,
        integration_type=integration_type,
        level=level,
        allowed=allowed,
        message=message,
        action=action,
    )


def audit_software_profile(profile) -> list[LicenseCheckResult]:
    """Audit all driver options in a DeviceSoftwareProfile.

    Args:
        profile: A DeviceSoftwareProfile object

    Returns:
        List of LicenseCheckResult, one per driver option
    """
    results: list[LicenseCheckResult] = []

    for option in profile.driver_options:
        integration = option.integration_type if hasattr(option, "integration_type") else "source_embed"
        license_id = option.license_spdx if hasattr(option, "license_spdx") else "MIT"

        # Convert IntegrationType enum to string if needed
        if hasattr(integration, "value"):
            integration = integration.value

        result = check_license_compatibility(license_id, integration)
        results.append(result)

    return results


def get_all_known_licenses() -> dict[str, tuple[str, str]]:
    """Get all known licenses with their compatibility level and name.

    Returns:
        Dict of SPDX ID → (compatibility_level, human_name)
    """
    return {
        spdx_id: (level.value, name)
        for spdx_id, (level, name) in _LICENSE_DB.items()
    }
