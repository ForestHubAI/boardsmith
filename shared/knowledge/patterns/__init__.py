# SPDX-License-Identifier: AGPL-3.0-or-later
"""DB-3: Pattern Library registry.

Usage:
    from shared.knowledge.patterns import (
        PATTERN_REGISTRY, BUNDLE_REGISTRY,
        get_pattern, get_bundle, list_pattern_ids,
    )

    pattern = get_pattern("i2c_pullup_v1")
    resolved = pattern.resolve_parameters({"bus_speed_hz": 400_000})
"""
from __future__ import annotations

from shared.knowledge.patterns.pattern_schema import CircuitPattern, PatternBundle
from shared.knowledge.patterns.all_patterns import PATTERNS
from shared.knowledge.patterns.bundles import BUNDLES

PATTERN_REGISTRY: dict[str, CircuitPattern] = {p.pattern_id: p for p in PATTERNS}
BUNDLE_REGISTRY: dict[str, PatternBundle] = {b.bundle_id: b for b in BUNDLES}


def get_pattern(pattern_id: str) -> CircuitPattern | None:
    """Look up a pattern by its ID. Returns None if not found."""
    return PATTERN_REGISTRY.get(pattern_id)


def get_bundle(bundle_id: str) -> PatternBundle | None:
    """Look up a bundle by its ID. Returns None if not found."""
    return BUNDLE_REGISTRY.get(bundle_id)


def list_pattern_ids() -> list[str]:
    """Return all registered pattern IDs."""
    return list(PATTERN_REGISTRY.keys())


def list_bundle_ids() -> list[str]:
    """Return all registered bundle IDs."""
    return list(BUNDLE_REGISTRY.keys())


def find_patterns_by_category(category: str) -> list[CircuitPattern]:
    """Return all patterns in the given category."""
    return [p for p in PATTERNS if p.category == category]


def find_patterns_by_trigger(interface_type: str) -> list[CircuitPattern]:
    """Return patterns whose trigger references the given interface type.

    Simple substring match — for exact evaluation use eval(pattern.trigger, ctx).
    """
    needle = interface_type.upper()
    return [
        p for p in PATTERNS
        if needle in p.trigger.upper() or interface_type in p.trigger
    ]
