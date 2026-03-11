# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool: find_component_alternatives — find cheaper or better alternatives to a component.

Uses the shared knowledge DB to locate components in the same category/subcategory
with similar or better specs at lower cost, or with better datasheet coverage.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from tools.base import Tool, ToolContext, ToolResult

log = logging.getLogger(__name__)

_DESCRIPTION = """\
Find alternative components for a given MPN.
Input: {"mpn": "BME280", "reason": "cost" | "availability" | "power" | "any"}
Returns: list of alternatives with rationale and cost comparison."""


class FindComponentAlternativesTool:
    """Search the knowledge DB for alternatives to a given component."""

    name = "find_component_alternatives"
    description = _DESCRIPTION
    input_schema: dict = {
        "type": "object",
        "properties": {
            "mpn": {"type": "string", "description": "Manufacturer part number to find alternatives for"},
            "reason": {"type": "string", "description": "Reason for replacement: availability, cost, footprint, etc.", "default": "any"},
        },
        "required": ["mpn"],
    }

    async def execute(self, input: Any, context: ToolContext) -> ToolResult:
        if isinstance(input, str):
            try:
                input = json.loads(input)
            except json.JSONDecodeError:
                input = {"mpn": input}

        mpn: str = (input.get("mpn", "") if isinstance(input, dict) else str(input)).strip()
        reason: str = (input.get("reason", "any") if isinstance(input, dict) else "any").lower()

        if not mpn:
            return ToolResult(
                success=False, data=None, source="find_component_alternatives",
                confidence=0.0, error="Missing 'mpn' key in input",
            )

        try:
            from knowledge.components import COMPONENTS, find_by_mpn
        except ImportError:
            return ToolResult(
                success=False, data=None, source="find_component_alternatives",
                confidence=0.0, error="knowledge.components not available",
            )

        original = find_by_mpn(mpn)
        if original is None:
            # Try case-insensitive
            mpn_low = mpn.lower()
            for c in COMPONENTS:
                if c.get("mpn", "").lower() == mpn_low:
                    original = c
                    break

        if original is None:
            return ToolResult(
                success=False, data=None, source="find_component_alternatives",
                confidence=0.0, error=f"Component '{mpn}' not found in knowledge DB",
            )

        orig_category = original.get("category", "")
        orig_sub_type = original.get("sub_type", "")
        orig_cost = float(original.get("unit_cost_usd", 0.0))
        orig_ratings = original.get("electrical_ratings", {})
        orig_interfaces = set(original.get("interface_types", []))

        candidates: list[dict[str, Any]] = []
        for comp in COMPONENTS:
            if comp.get("mpn") == original.get("mpn"):
                continue
            if comp.get("category") != orig_category:
                continue
            if orig_sub_type and comp.get("sub_type") != orig_sub_type:
                continue

            alt_cost = float(comp.get("unit_cost_usd", 0.0))
            alt_ratings = comp.get("electrical_ratings", {})
            alt_interfaces = set(comp.get("interface_types", []))

            rationale: list[str] = []

            # Cost check
            cost_saving = orig_cost - alt_cost
            if cost_saving > 0.0:
                rationale.append(f"${cost_saving:.2f} cheaper ({alt_cost:.2f} vs {orig_cost:.2f})")
            elif cost_saving < -0.10:
                rationale.append(f"${-cost_saving:.2f} more expensive")

            # Interface compatibility
            if not orig_interfaces or orig_interfaces == alt_interfaces:
                rationale.append("same interface")
            elif orig_interfaces & alt_interfaces:
                rationale.append(f"compatible interfaces: {', '.join(orig_interfaces & alt_interfaces)}")

            # Power: lower quiescent current
            orig_iq = orig_ratings.get("quiescent_current_ua", None)
            alt_iq = alt_ratings.get("quiescent_current_ua", None)
            if orig_iq and alt_iq and alt_iq < orig_iq * 0.5:
                rationale.append(f"lower quiescent ({alt_iq:.1f} µA vs {orig_iq:.1f} µA)")

            # Datasheet coverage
            orig_cov = original.get("init_contract_coverage", False)
            alt_cov = comp.get("init_contract_coverage", False)
            if alt_cov and not orig_cov:
                rationale.append("has init contract (original does not)")

            # Apply reason filter
            if reason == "cost" and cost_saving <= 0.0:
                continue
            if reason == "power" and not any("quiescent" in r for r in rationale):
                continue

            if rationale:
                candidates.append({
                    "mpn": comp.get("mpn"),
                    "name": comp.get("name", comp.get("mpn")),
                    "manufacturer": comp.get("manufacturer", ""),
                    "unit_cost_usd": alt_cost,
                    "cost_delta_usd": round(alt_cost - orig_cost, 3),
                    "interface_types": list(alt_interfaces),
                    "rationale": rationale,
                    "has_init_contract": comp.get("init_contract_coverage", False),
                })

        candidates.sort(key=lambda c: (c["cost_delta_usd"], not c["has_init_contract"]))

        return ToolResult(
            success=True,
            data={
                "original_mpn": original.get("mpn"),
                "original_cost_usd": orig_cost,
                "query_reason": reason,
                "alternatives": candidates[:5],  # top 5
                "total_found": len(candidates),
            },
            source="find_component_alternatives",
            confidence=0.90,
            metadata={"category": orig_category, "sub_type": orig_sub_type},
        )
