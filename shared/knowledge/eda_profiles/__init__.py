# SPDX-License-Identifier: AGPL-3.0-or-later
"""EDA Profile Registry — canonical lookup for symbol, footprint, and pin mapping.

Usage:
    from shared.knowledge.eda_profiles import get_eda_profile, EDA_REGISTRY

    profile = get_eda_profile("BME280")
    if profile:
        print(profile.symbol.ref_prefix)          # "U"
        print(profile.footprint.kicad_name)        # "Package_LGA:Bosch_LGA-8..."
        print(profile.footprint.pad_count)         # 8
        print(profile.effective_pinmap())           # {"1": "1", "2": "2", ...}
"""
from __future__ import annotations

from shared.knowledge.eda_schema import EDAProfile

# Import all category modules
from shared.knowledge.eda_profiles import comms, mcu, passive, power, sensor

# Build registry: MPN (upper) → EDAProfile
_ALL_PROFILES: list[EDAProfile] = (
    mcu.PROFILES
    + sensor.PROFILES
    + power.PROFILES
    + comms.PROFILES
    + passive.PROFILES
)

EDA_REGISTRY: dict[str, EDAProfile] = {p.mpn: p for p in _ALL_PROFILES}


def get_eda_profile(mpn: str) -> EDAProfile | None:
    """Look up an EDA profile by exact MPN.

    Returns None when not found (caller should fall back to symbol_map.py).
    """
    return EDA_REGISTRY.get(mpn)


def list_mpns() -> list[str]:
    """Return all registered MPNs."""
    return list(EDA_REGISTRY.keys())


def has_eda_profile(mpn: str) -> bool:
    """Quick existence check."""
    return mpn in EDA_REGISTRY
