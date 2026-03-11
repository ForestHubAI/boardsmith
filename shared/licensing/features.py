# SPDX-License-Identifier: AGPL-3.0-or-later
"""Feature flag registry for tier-gated functionality.

Usage::

    from shared.licensing import Feature, is_available

    if is_available(Feature.COMPLIANCE_ENGINE):
        run_compliance_check(hir)
    else:
        logger.info("Compliance engine requires Enterprise license")
"""
from __future__ import annotations

from enum import Enum

from shared.licensing.checker import LicenseTier, get_current_tier


class Feature(str, Enum):
    """All gated features with their required tier."""

    # Community (always available)
    CORE_SYNTHESIS = "core_synthesis"
    CORE_KNOWLEDGE = "core_knowledge"
    KICAD_EXPORT = "kicad_export"
    BASIC_CONSTRAINTS = "basic_constraints"
    MULTI_TARGET = "multi_target"

    # Commercial
    CLOSED_SOURCE_USE = "closed_source_use"
    SAAS_DEPLOYMENT = "saas_deployment"

    # Enterprise
    ENTERPRISE_KNOWLEDGE = "enterprise_knowledge"
    COMPLIANCE_ENGINE = "compliance_engine"
    POWER_BUDGET_MODEL = "power_budget_model"
    THERMAL_MODEL = "thermal_model"
    MULTI_RAIL_OPTIMIZATION = "multi_rail_optimization"
    ADVANCED_PCB_ROUTING = "advanced_pcb_routing"
    MANUFACTURING_INTEGRATION = "manufacturing_integration"
    AUDIT_LOGS = "audit_logs"
    DESIGN_HISTORY = "design_history"
    ENTERPRISE_REPORTING = "enterprise_reporting"


# Maps each feature to the minimum tier required.
_FEATURE_TIERS: dict[Feature, LicenseTier] = {
    # Community
    Feature.CORE_SYNTHESIS: LicenseTier.COMMUNITY,
    Feature.CORE_KNOWLEDGE: LicenseTier.COMMUNITY,
    Feature.KICAD_EXPORT: LicenseTier.COMMUNITY,
    Feature.BASIC_CONSTRAINTS: LicenseTier.COMMUNITY,
    Feature.MULTI_TARGET: LicenseTier.COMMUNITY,
    # Commercial
    Feature.CLOSED_SOURCE_USE: LicenseTier.COMMERCIAL,
    Feature.SAAS_DEPLOYMENT: LicenseTier.COMMERCIAL,
    # Enterprise
    Feature.ENTERPRISE_KNOWLEDGE: LicenseTier.ENTERPRISE,
    Feature.COMPLIANCE_ENGINE: LicenseTier.ENTERPRISE,
    Feature.POWER_BUDGET_MODEL: LicenseTier.ENTERPRISE,
    Feature.THERMAL_MODEL: LicenseTier.ENTERPRISE,
    Feature.MULTI_RAIL_OPTIMIZATION: LicenseTier.ENTERPRISE,
    Feature.ADVANCED_PCB_ROUTING: LicenseTier.ENTERPRISE,
    Feature.MANUFACTURING_INTEGRATION: LicenseTier.ENTERPRISE,
    Feature.AUDIT_LOGS: LicenseTier.ENTERPRISE,
    Feature.DESIGN_HISTORY: LicenseTier.ENTERPRISE,
    Feature.ENTERPRISE_REPORTING: LicenseTier.ENTERPRISE,
}

_TIER_RANK = {
    LicenseTier.COMMUNITY: 0,
    LicenseTier.COMMERCIAL: 1,
    LicenseTier.ENTERPRISE: 2,
}


def is_available(feature: Feature) -> bool:
    """Check if a feature is available under the current license tier."""
    required = _FEATURE_TIERS.get(feature, LicenseTier.ENTERPRISE)
    current = get_current_tier()
    return _TIER_RANK[current] >= _TIER_RANK[required]


def required_tier(feature: Feature) -> LicenseTier:
    """Return the minimum tier required for a feature."""
    return _FEATURE_TIERS.get(feature, LicenseTier.ENTERPRISE)
