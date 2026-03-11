# SPDX-License-Identifier: AGPL-3.0-or-later
"""License tier detection and key validation.

The license tier is determined by:
  1. Environment variable ``BOARDSMITH_LICENSE_KEY``
  2. Config file ``~/.boardsmith/license.key``
  3. Default: ``COMMUNITY`` (no key needed)

Key format and validation logic will be finalized before commercial launch.
For now, this module provides the tier abstraction that the rest of the
codebase can depend on.
"""
from __future__ import annotations

import os
from enum import Enum
from pathlib import Path


class LicenseTier(str, Enum):
    """License tiers controlling feature availability."""

    COMMUNITY = "community"
    COMMERCIAL = "commercial"
    ENTERPRISE = "enterprise"


_LICENSE_KEY_PATH = Path.home() / ".boardsmith" / "license.key"

_cached_tier: LicenseTier | None = None


def _read_license_key() -> str | None:
    """Read the license key from env or file."""
    key = os.environ.get("BOARDSMITH_LICENSE_KEY")
    if key:
        return key.strip()

    if _LICENSE_KEY_PATH.exists():
        try:
            return _LICENSE_KEY_PATH.read_text().strip()
        except OSError:
            return None

    return None


def _validate_key(key: str) -> LicenseTier:
    """Validate a license key and return its tier.

    TODO: Implement cryptographic key validation before commercial launch.
    For now, this is a placeholder that checks key prefixes.
    """
    if key.startswith("vh-ent-"):
        return LicenseTier.ENTERPRISE
    if key.startswith("vh-com-"):
        return LicenseTier.COMMERCIAL
    return LicenseTier.COMMUNITY


def get_current_tier() -> LicenseTier:
    """Determine the current license tier.

    Returns COMMUNITY if no valid key is found. Result is cached for
    the lifetime of the process.
    """
    global _cached_tier

    if _cached_tier is not None:
        return _cached_tier

    key = _read_license_key()
    if key:
        _cached_tier = _validate_key(key)
    else:
        _cached_tier = LicenseTier.COMMUNITY

    return _cached_tier


def reset_cache() -> None:
    """Clear the cached tier (useful for testing)."""
    global _cached_tier
    _cached_tier = None
