# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool registry — maps tool names to tool instances."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Tool, ToolContext, ToolResult

if TYPE_CHECKING:
    pass


class ToolRegistry:
    """Central registry for all available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool by its name."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Look up a tool by name. Returns None if not found."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())

    async def execute(self, name: str, input: object, context: ToolContext) -> ToolResult:
        """Execute a tool by name. Returns error result if not found."""
        tool = self.get(name)
        if tool is None:
            return ToolResult(
                success=False,
                data=None,
                source="registry",
                confidence=0.0,
                error=f"Tool '{name}' not found. Available: {self.list_tools()}",
            )
        return await tool.execute(input, context)

    def __repr__(self) -> str:
        return f"ToolRegistry({self.list_tools()})"


# ---------------------------------------------------------------------------
# Default registry (populated lazily)
# ---------------------------------------------------------------------------

_default_registry: ToolRegistry | None = None


def get_default_registry() -> ToolRegistry:
    """Return the default registry with all built-in tools registered."""
    global _default_registry
    if _default_registry is None:
        _default_registry = ToolRegistry()
        _register_builtin_tools(_default_registry)
    return _default_registry


def _register_builtin_tools(registry: ToolRegistry) -> None:
    """Register all built-in tools into the registry.

    Tools are imported lazily to avoid heavy dependencies at import time.
    Missing optional dependencies cause a silent skip (not a crash).
    """
    _tool_classes = [
        ("tools.query_knowledge", "QueryKnowledgeTool"),
        ("tools.validate_hir", "ValidateHIRTool"),
        ("tools.download_pdf", "DownloadPDFTool"),
        ("tools.extract_datasheet", "ExtractDatasheetTool"),
        ("tools.web_search", "WebSearchTool"),
        ("tools.search_octopart", "SearchOctopartTool"),
        ("tools.compile_code", "CompileCodeTool"),
        ("tools.analyze_power_design", "AnalyzePowerDesignTool"),
        ("tools.find_component_alternatives", "FindComponentAlternativesTool"),
    ]
    for module_suffix, class_name in _tool_classes:
        try:
            import importlib
            mod = importlib.import_module(f".{module_suffix}", package=__name__.rsplit(".", 1)[0])
            cls = getattr(mod, class_name)
            registry.register(cls())
        except (ImportError, AttributeError):
            pass

    # EDA tools — in boardsmith_hw.agent (different package tree from shared/tools/)
    # Must use absolute importlib.import_module() NOT relative f".{suffix}" pattern
    _eda_tool_classes = [
        ("boardsmith_hw.agent.run_erc", "RunERCTool"),
        ("boardsmith_hw.agent.read_schematic", "ReadSchematicTool"),
        ("boardsmith_hw.agent.search_component", "SearchComponentTool"),
        ("boardsmith_hw.agent.write_schematic", "WriteSchematicPatchTool"),  # Phase 7
        ("boardsmith_hw.agent.verify_components", "VerifyComponentsTool"),    # Phase 10
        ("boardsmith_hw.agent.verify_connectivity", "VerifyConnectivityTool"), # Phase 10
        ("boardsmith_hw.agent.verify_bootability", "VerifyBootabilityTool"),  # Phase 10
        ("boardsmith_hw.agent.verify_power", "VerifyPowerTool"),              # Phase 10
        ("boardsmith_hw.agent.verify_bom", "VerifyBomTool"),                  # Phase 12
        ("boardsmith_hw.agent.verify_pcb_basic", "VerifyPcbBasicTool"),       # Phase 12
    ]
    for module_path, class_name in _eda_tool_classes:
        try:
            import importlib
            mod = importlib.import_module(module_path)  # absolute — no package= kwarg
            cls = getattr(mod, class_name)
            registry.register(cls())
        except (ImportError, AttributeError):
            pass  # synthesizer/ not in path or kicad-cli missing — silent skip
