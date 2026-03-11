# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool: analyze_power_design — run the power budget calculator on a HIR dict.

Returns a structured power analysis report including per-rail status,
overcurrent warnings, and LDO dropout risk.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from tools.base import Tool, ToolContext, ToolResult

log = logging.getLogger(__name__)

_DESCRIPTION = """\
Analyze the power budget of a hardware design HIR.
Input: {"hir": <HIR dict>, "safety_margin": 0.20}
Returns: per-rail budget (load_ma, regulator_ma, passes) and overall pass/fail."""


class AnalyzePowerDesignTool:
    """Run the boardsmith_hw.power_budget calculator on a HIR dict."""

    name = "analyze_power_design"
    description = _DESCRIPTION
    input_schema: dict = {
        "type": "object",
        "properties": {
            "hir": {"type": "object", "description": "HIR dict to analyze"},
            "safety_margin": {"type": "number", "description": "Power budget safety margin (0.0-1.0)", "default": 0.20},
        },
        "required": ["hir"],
    }

    async def execute(self, input: Any, context: ToolContext) -> ToolResult:
        if isinstance(input, str):
            try:
                input = json.loads(input)
            except json.JSONDecodeError:
                return ToolResult(
                    success=False, data=None, source="analyze_power_design",
                    confidence=0.0, error="Input must be JSON with 'hir' key",
                )

        hir_dict = input.get("hir") if isinstance(input, dict) else None
        if not hir_dict:
            return ToolResult(
                success=False, data=None, source="analyze_power_design",
                confidence=0.0, error="Missing 'hir' key in input",
            )

        safety_margin: float = float(input.get("safety_margin", 0.20))

        try:
            from boardsmith_hw.power_budget import calculate_power_budget
            budget = calculate_power_budget(hir_dict, safety_margin=safety_margin)
        except ImportError:
            # Fallback: basic check without the full module
            return self._minimal_check(hir_dict)
        except Exception as exc:
            log.warning("Power budget calculation failed: %s", exc)
            return ToolResult(
                success=False, data=None, source="analyze_power_design",
                confidence=0.0, error=str(exc),
            )

        rails_data = []
        for rail in budget.rails:
            rd: dict[str, Any] = {
                "name": rail.rail_name,
                "voltage_v": rail.supply_voltage,
                "total_load_ma": round(rail.total_load_ma, 1),
                "regulator_mpn": rail.regulator_mpn,
                "regulator_max_ma": rail.regulator_max_ma,
                "passes": rail.passes,
                "loads": [
                    {"comp_id": lo.comp_id, "mpn": lo.mpn,
                     "current_ma": round(lo.current_ma, 1), "source": lo.source}
                    for lo in rail.loads
                ],
            }
            if rail.margin_ma is not None:
                rd["margin_ma"] = round(rail.margin_ma, 1)
            if rail.utilisation_pct is not None:
                rd["utilisation_pct"] = round(rail.utilisation_pct, 1)
            rails_data.append(rd)

        result_data: dict[str, Any] = {
            "passes": budget.passes,
            "total_load_ma": round(budget.total_load_ma, 1),
            "safety_margin_pct": int(safety_margin * 100),
            "rails": rails_data,
            "summary": budget.summary_lines(),
        }

        return ToolResult(
            success=True,
            data=result_data,
            source="analyze_power_design",
            confidence=0.95,
            metadata={"rail_count": len(budget.rails), "passes": budget.passes},
        )

    @staticmethod
    def _minimal_check(hir_dict: dict[str, Any]) -> ToolResult:
        """Fallback when power_budget module is unavailable."""
        comps = hir_dict.get("components", [])
        total_ma = 0.0
        for c in comps:
            if c.get("role", "").lower() in ("passive", "power", "connector"):
                continue
            ratings = c.get("electrical_ratings", {})
            total_ma += float(ratings.get("current_draw_max_ma", 10.0))

        return ToolResult(
            success=True,
            data={
                "passes": total_ma < 800.0,
                "total_load_ma": round(total_ma, 1),
                "safety_margin_pct": 20,
                "rails": [],
                "summary": [f"Total load: {total_ma:.0f} mA (minimal estimate)"],
            },
            source="analyze_power_design:minimal",
            confidence=0.50,
        )
