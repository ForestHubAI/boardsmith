# SPDX-License-Identifier: AGPL-3.0-or-later
"""B9. Confidence Engine — computes overall and per-subsystem confidence scores."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from synth_core.hir_bridge.validator import DiagnosticsReport


@dataclass
class ConfidenceResult:
    overall: float
    subscores: dict[str, float] = field(default_factory=dict)
    explanations: list[str] = field(default_factory=list)
    hitl_required: bool = False
    hitl_messages: list[str] = field(default_factory=list)
    llm_boosted_stages: list[str] = field(default_factory=list)
    # Gate thresholds from spec
    AUTO_PROCEED_THRESHOLD = 0.85
    CONFIRM_THRESHOLD = 0.65


class ConfidenceEngine:
    """Computes confidence and HITL gate decisions."""

    def compute(
        self,
        intent_confidence: float,
        component_confidence: float,
        topology_confidence: float,
        validation_report: DiagnosticsReport,
        assumptions: list[str],
        hir_dict: dict[str, Any] | None = None,
        llm_boosted_stages: list[str] | None = None,
        profile_errors: int = 0,
        profile_warnings: int = 0,
        driver_quality: float | None = None,
    ) -> ConfidenceResult:
        """Compute overall confidence from sub-scores and diagnostics."""
        explanations: list[str] = []
        hitl_messages: list[str] = []

        # Electrical confidence from validation
        errors = sum(1 for c in validation_report.constraints
                     if c.severity.value == "error" and c.status.value == "fail")
        warnings = sum(1 for c in validation_report.constraints
                       if c.severity.value == "warning")
        unknowns = sum(1 for c in validation_report.constraints
                       if c.status.value == "unknown")

        electrical_conf = 1.0
        if errors > 0:
            electrical_conf = 0.0
            explanations.append(f"{errors} error(s) in validation")
        elif warnings > 0:
            electrical_conf = max(0.4, 1.0 - 0.1 * warnings)
            explanations.append(f"{warnings} warning(s) in validation")
        if unknowns > 0:
            electrical_conf *= max(0.5, 1.0 - 0.05 * unknowns)
            explanations.append(f"{unknowns} unknown constraint(s)")

        subscores = {
            "intent": intent_confidence,
            "components": component_confidence,
            "topology": topology_confidence,
            "electrical": electrical_conf,
        }

        # Driver quality subscore (from MCU/software profile checks)
        if driver_quality is not None:
            subscores["driver_quality"] = driver_quality
            explanations.append(f"Driver quality score: {driver_quality:.2f}")

        # Profile check penalties
        if profile_errors > 0:
            subscores["electrical"] = max(0.0, subscores["electrical"] - 0.15 * profile_errors)
            explanations.append(f"{profile_errors} MCU profile error(s)")
        if profile_warnings > 0:
            subscores["electrical"] = max(0.2, subscores["electrical"] - 0.05 * profile_warnings)
            explanations.append(f"{profile_warnings} MCU profile warning(s)")

        # Weighted average (with optional driver_quality)
        weights = {"intent": 0.25, "components": 0.30, "topology": 0.20, "electrical": 0.25}
        if "driver_quality" in subscores:
            # Re-balance: reduce others slightly to include driver_quality
            weights = {
                "intent": 0.22, "components": 0.26, "topology": 0.18,
                "electrical": 0.22, "driver_quality": 0.12,
            }
        overall = sum(subscores[k] * weights[k] for k in subscores)

        # Assumption penalty
        penalty = 0.015 * len(assumptions)
        overall = max(0.0, overall - penalty)
        if assumptions:
            explanations.append(f"{len(assumptions)} assumption(s) reduce confidence by {penalty:.2f}")

        # LLM-boost signal — small bonus per stage that was actively boosted
        llm_stages = llm_boosted_stages or []
        if llm_stages:
            boost = 0.01 * len(llm_stages)
            overall = min(1.0, overall + boost)
            explanations.append(f"LLM-boost applied in: {', '.join(llm_stages)} (+{boost:.2f})")

        # HITL gate checks
        hitl_required = False

        if overall < ConfidenceResult.CONFIRM_THRESHOLD:
            hitl_required = True
            hitl_messages.append(f"Overall confidence {overall:.2f} below threshold {ConfidenceResult.CONFIRM_THRESHOLD}")

        if errors > 0:
            hitl_required = True
            hitl_messages.append(f"{errors} unresolved error constraint(s) require review")

        if unknowns > 3:
            hitl_required = True
            hitl_messages.append(f"{unknowns} unknown constraints — missing component knowledge")

        # Check for safety-critical components
        if hir_dict:
            comps = hir_dict.get("components", [])
            actuators = [c for c in comps if c.get("role") == "actuator"]
            if actuators:
                hitl_required = True
                hitl_messages.append("Safety-critical actuators detected — require manual review")

        return ConfidenceResult(
            overall=round(overall, 3),
            subscores={k: round(v, 3) for k, v in subscores.items()},
            explanations=explanations,
            hitl_required=hitl_required,
            hitl_messages=hitl_messages,
            llm_boosted_stages=list(llm_stages),
        )
