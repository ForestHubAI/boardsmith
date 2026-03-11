# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool: validate_hir — run the constraint solver on a HIR dict."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..base import ToolContext, ToolResult


@dataclass
class ValidateHIRInput:
    hir_dict: dict[str, Any]


class ValidateHIRTool:
    """Validates a HIR dict using the Track A constraint solver."""

    name = "validate_hir"
    description = (
        "Run the 11 formal constraint checks on a HIR dict. "
        "Returns pass/fail status per constraint."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "hir_dict": {"type": "object", "description": "HIR dict to validate"},
        },
        "required": ["hir_dict"],
    }

    async def execute(self, input: ValidateHIRInput, context: ToolContext) -> ToolResult:
        try:
            from boardsmith_fw.api.compiler import validate_hir_dict
        except ImportError:
            return ToolResult(
                success=False,
                data=None,
                source="constraint_solver",
                confidence=0.0,
                error="compiler/boardsmith_fw not available in PYTHONPATH",
            )

        try:
            report = validate_hir_dict(input.hir_dict)
            all_pass = all(
                c.get("status") != "FAIL"
                for c in report.get("constraints", [])
            )
            return ToolResult(
                success=all_pass,
                data=report,
                source="constraint_solver",
                confidence=1.0,
                metadata={"all_pass": all_pass},
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                source="constraint_solver",
                confidence=0.0,
                error=str(e),
            )
