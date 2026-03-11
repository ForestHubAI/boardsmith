# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool: query_knowledge — look up components in the local knowledge DB."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..base import ToolContext, ToolResult


@dataclass
class QueryKnowledgeInput:
    query: str            # MPN, category, or keyword
    max_results: int = 5


class QueryKnowledgeTool:
    """Searches the shared knowledge DB for components matching a query."""

    name = "query_knowledge"
    description = (
        "Search the local component knowledge database by MPN, category, "
        "or keyword. Returns matching components with specs."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "MPN, category, or keyword to search"},
            "max_results": {"type": "integer", "description": "Maximum results to return", "default": 5},
        },
        "required": ["query"],
    }

    async def execute(self, input: Any, context: ToolContext) -> ToolResult:
        # Accept both dict (from ReAct loop) and QueryKnowledgeInput dataclass
        if isinstance(input, dict):
            query = input.get("query", input.get("raw", "")).strip()
            max_results = int(input.get("max_results", 5))
        else:
            query = input.query.strip()
            max_results = input.max_results

        if not query:
            return ToolResult(
                success=False,
                data=[],
                source="builtin_db",
                confidence=0.0,
                error="No query provided",
            )

        try:
            from knowledge import db
        except ImportError:
            return ToolResult(
                success=False,
                data=[],
                source="builtin_db",
                confidence=0.0,
                error="shared/knowledge not available in PYTHONPATH",
            )

        results = []

        # 1. Exact MPN match
        exact = db.find_by_mpn(query)
        if exact:
            results = [exact]
        else:
            # 2. Full-text search (FTS5)
            fts_results = db.search(query, limit=max_results)
            if fts_results:
                results = fts_results
            else:
                # 3. Fallback: tag or category match
                q_lower = query.lower()
                for entry in db.get_all():
                    mpn = entry.get("mpn", "").lower()
                    tags = [t.lower() for t in entry.get("tags", [])]
                    cat = entry.get("category", "").lower()
                    desc = entry.get("description", "").lower()
                    if (q_lower in mpn or q_lower in cat or q_lower in desc
                            or any(q_lower in t for t in tags)):
                        results.append(entry)
                        if len(results) >= max_results:
                            break

        if not results:
            return ToolResult(
                success=False,
                data=[],
                source="builtin_db",
                confidence=0.0,
                error=f"No component found for query: '{query}'",
            )

        # Slim down output for LLM context (strip large fields)
        slim = []
        for c in results[:max_results]:
            slim.append({
                "mpn": c.get("mpn"),
                "name": c.get("name"),
                "manufacturer": c.get("manufacturer"),
                "category": c.get("category"),
                "sub_type": c.get("sub_type"),
                "interface_types": c.get("interface_types", []),
                "mounting": c.get("mounting"),
                "package": c.get("package"),
                "description": c.get("description"),
                "electrical_ratings": c.get("electrical_ratings", {}),
                "capabilities": c.get("capabilities", {}),
                "unit_cost_usd": c.get("unit_cost_usd"),
                "tags": c.get("tags", []),
                "datasheet_url": c.get("datasheet_url"),
                "library_support": c.get("library_support", []),
            })

        return ToolResult(
            success=True,
            data=slim,
            source="builtin_db",
            confidence=0.95,
            metadata={"query": query, "total_found": len(results)},
        )
