# SPDX-License-Identifier: AGPL-3.0-or-later
"""ToolDispatcher — routes LLM tool_calls to Python tool instances via ToolRegistry."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tools.base import ToolContext
    from tools.registry import ToolRegistry
    from llm.types import ToolCall


class ToolDispatcher:
    """Routes ToolCallResponse.tool_calls to registered Python tool instances.

    Produces tool_result message content blocks for the next API call.
    Instantiate with a ToolRegistry; call dispatch() after each complete_with_tools().
    """

    def __init__(self, registry: "ToolRegistry") -> None:
        self._registry = registry

    async def dispatch(
        self,
        tool_calls: list["ToolCall"],
        context: "ToolContext",
    ) -> list[dict[str, Any]]:
        """Execute all tool_calls and return tool_result content blocks.

        Each result dict has shape:
            {"type": "tool_result", "tool_use_id": str, "content": str, "is_error": bool}

        tool_use_id MUST match the original ToolCall.id for the API to accept the result.
        content is always a JSON string (or error string on failure).
        """
        results: list[dict[str, Any]] = []
        for tc in tool_calls:
            tool_result = await self._registry.execute(tc.name, tc.input, context)
            if tool_result.success:
                content_str = json.dumps(tool_result.data)
            else:
                content_str = tool_result.error or json.dumps({"error": "tool failed"})
            results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": content_str,
                "is_error": not tool_result.success,
            })
        return results

    def make_tool_result_message(self, tool_result_blocks: list[dict[str, Any]]) -> dict[str, Any]:
        """Wrap tool_result blocks into a user message dict for the next API call."""
        return {"role": "user", "content": tool_result_blocks}
