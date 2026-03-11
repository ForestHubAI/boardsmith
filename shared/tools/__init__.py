# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool System for Boardsmith agents.

Provides a standardized interface for agent actions (7 built-in tools):
- query_knowledge: Search local component DB
- validate_hir: Run constraint solver
- download_pdf: Download and cache PDF datasheets
- extract_datasheet: Extract specs from PDF via LLM
- web_search: Search the web for components and docs
- search_octopart: Parametric component search via Nexar/Octopart
- compile_code: Firmware compilation check

Quick start:
    from tools.registry import get_default_registry
    from tools.base import ToolContext

    registry = get_default_registry()
    context = ToolContext(session_id="test", llm_gateway=gateway)
    result = await registry.execute("query_knowledge", {"query": "BME280"}, context)
"""

from .base import Tool, ToolContext, ToolResult
from .registry import ToolRegistry, get_default_registry

__all__ = [
    "Tool",
    "ToolContext",
    "ToolResult",
    "ToolRegistry",
    "get_default_registry",
]
