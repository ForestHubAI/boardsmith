# SPDX-License-Identifier: AGPL-3.0-or-later
"""SearchComponentTool — EDA-specific component database search."""
from __future__ import annotations
from typing import Any


class SearchComponentTool:
    name = "search_component"
    description = (
        "Search the Boardsmith component database by MPN, category, or description. "
        "Returns part_number, description, value, package, and LCSC ID. "
        "Always call this before write_schematic_patch to get correct pin names and lib_id."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Component query string (MPN, description, or generic name).",
            }
        },
        "required": ["query"],
    }

    async def execute(self, input: Any, context: Any) -> Any:
        from tools.base import ToolResult
        from knowledge import db  # lazy import — safe with BOARDSMITH_NO_LLM=1

        query = input.get("query", "").strip() if isinstance(input, dict) else ""
        if not query:
            return ToolResult(
                success=False,
                data=[],
                source="builtin_db",
                confidence=0.0,
                error="No query provided",
            )

        try:
            results = db.search(query, limit=5) or []
            # Fallback to exact MPN match if FTS returns nothing
            if not results:
                hit = db.find_by_mpn(query)
                results = [hit] if hit else []

            # Slim output for LLM consumption: keep EDA-relevant fields only
            slim = [
                {
                    "part_number": r.get("part_number", ""),
                    "description": r.get("description", ""),
                    "value": r.get("value", ""),
                    "package": r.get("package", ""),
                    "lcsc_id": r.get("lcsc_id", ""),
                }
                for r in results
            ]
            return ToolResult(
                success=bool(slim),
                data=slim,
                source="builtin_db",
                confidence=0.95 if slim else 0.0,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                data=[],
                source="builtin_db",
                confidence=0.0,
                error=str(exc),
            )
