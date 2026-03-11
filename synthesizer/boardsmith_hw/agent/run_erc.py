# SPDX-License-Identifier: AGPL-3.0-or-later
"""RunERCTool — wraps KiCadChecker for LLM-callable ERC."""
from __future__ import annotations
from pathlib import Path
from typing import Any

# Fixable rule IDs: violations the ERCAgent can patch programmatically
_FIXABLE_RULE_IDS = frozenset({
    "pin_not_connected",
    "pin_unconnected",
    "power_pin_not_driven",
    "missing_power_flag",
})


def _format_violations(result: Any) -> list[dict]:
    """Format DRC violations into structured dicts for LLM consumption."""
    return [
        {
            "message": v.description,
            "severity": v.severity,
            "fixable": v.rule_id in _FIXABLE_RULE_IDS,
            "rule_id": v.rule_id,
            "items": v.items[:3],
        }
        for v in result.violations
    ]


class RunERCTool:
    """LLM-callable tool that runs KiCad ERC and returns structured violations."""

    name = "run_erc"
    description = (
        "Run KiCad Electrical Rules Check on a .kicad_sch file. "
        "Returns structured violation list with severity and fixable classification. "
        "Returns empty violations list if ERC passes clean."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "sch_path": {
                "type": "string",
                "description": "Absolute path to the .kicad_sch file to check.",
            }
        },
        "required": ["sch_path"],
    }

    async def execute(self, input: Any, context: Any) -> Any:
        from tools.base import ToolResult
        # Lazy import — never at module level to keep import-clean
        from boardsmith_hw.kicad_drc import KiCadChecker

        sch_path = Path(input["sch_path"])
        checker = KiCadChecker()
        result = checker.run_erc(sch_path)
        violations = _format_violations(result)
        return ToolResult(
            success=True,
            data={"violations": violations, "error_count": result.error_count},
            source="kicad_cli_erc",
            confidence=1.0 if result.tool_available else 0.0,
            metadata={"passed": result.passed, "note": result.note},
        )
