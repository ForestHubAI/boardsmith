# SPDX-License-Identifier: AGPL-3.0-or-later
"""TDD tests for EDA tool registration in shared/tools/registry.py.

RED phase: Tests written before the registry extension is implemented.
Requires PYTHONPATH=synthesizer:shared:compiler for EDA tools to be importable.
"""
from __future__ import annotations


class TestRegistryEDATools:
    """EDA tools must be registered in the default registry when synthesizer/ is in path."""

    def _fresh_registry(self):
        """Return a fresh ToolRegistry with all built-in tools registered."""
        from tools.registry import ToolRegistry, _register_builtin_tools
        reg = ToolRegistry()
        _register_builtin_tools(reg)
        return reg

    def test_run_erc_registered(self):
        reg = self._fresh_registry()
        tools = reg.list_tools()
        assert "run_erc" in tools, f"run_erc not in registry: {tools}"

    def test_read_schematic_registered(self):
        reg = self._fresh_registry()
        tools = reg.list_tools()
        assert "read_schematic" in tools, f"read_schematic not in registry: {tools}"

    def test_search_component_registered(self):
        reg = self._fresh_registry()
        tools = reg.list_tools()
        assert "search_component" in tools, f"search_component not in registry: {tools}"

    def test_eda_tools_use_absolute_import_pattern(self):
        """Registry code must use absolute import (no package= kwarg) for EDA tools."""
        import inspect
        from tools import registry
        src = inspect.getsource(registry)
        # The EDA module paths must appear as absolute strings in registry source
        assert "boardsmith_hw.agent.run_erc" in src
        assert "boardsmith_hw.agent.read_schematic" in src
        assert "boardsmith_hw.agent.search_component" in src

    def test_existing_tools_still_present(self):
        """Adding EDA tools must not remove any of the original 9 built-in tools."""
        reg = self._fresh_registry()
        tools = reg.list_tools()
        core_tools = {
            "query_knowledge", "validate_hir", "download_pdf",
            "extract_datasheet", "web_search", "search_octopart",
            "compile_code",
        }
        missing = core_tools - set(tools)
        assert not missing, f"Original tools removed from registry: {missing}"

    def test_total_tool_count_at_least_10(self):
        """With synthesizer in path, registry should have at least 10 tools (7 core + 3 EDA)."""
        reg = self._fresh_registry()
        tools = reg.list_tools()
        assert len(tools) >= 10, f"Expected >= 10 tools, got {len(tools)}: {tools}"

    def test_eda_tools_silent_skip_without_crash(self):
        """Registry must not raise if boardsmith_hw.agent is absent (simulated by importlib)."""
        from tools.registry import ToolRegistry, _register_builtin_tools
        import sys
        # Temporarily hide boardsmith_hw to simulate absent synthesizer/
        saved = {k: v for k, v in sys.modules.items() if "boardsmith_hw" in k}
        for key in saved:
            del sys.modules[key]

        # Patch importlib.import_module to raise ImportError for boardsmith_hw.agent.*
        import importlib
        original_import_module = importlib.import_module

        def patched_import_module(name, *args, **kwargs):
            if name.startswith("boardsmith_hw.agent"):
                raise ImportError(f"Simulated missing: {name}")
            return original_import_module(name, *args, **kwargs)

        importlib.import_module = patched_import_module
        try:
            reg = ToolRegistry()
            _register_builtin_tools(reg)  # Must not raise
            tools = reg.list_tools()
            # EDA tools should be absent but no crash
            assert "run_erc" not in tools
            assert "read_schematic" not in tools
            assert "search_component" not in tools
        finally:
            importlib.import_module = original_import_module
            sys.modules.update(saved)

    def test_get_default_registry_includes_eda_tools(self):
        """get_default_registry() singleton also includes EDA tools."""
        import tools.registry as reg_mod
        # Reset singleton to force re-registration
        reg_mod._default_registry = None
        from tools.registry import get_default_registry
        reg = get_default_registry()
        tools = reg.list_tools()
        assert "run_erc" in tools
        assert "read_schematic" in tools
        assert "search_component" in tools
        # Restore singleton state
        reg_mod._default_registry = None
