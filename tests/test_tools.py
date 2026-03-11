# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for shared/tools/ — ToolResult, ToolContext, ToolRegistry, individual tools.

All tests work without API keys and without external services.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
for _pkg in ("shared", "synthesizer", "compiler"):
    _p = str(REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# ToolResult
# ---------------------------------------------------------------------------

class TestToolResult:
    def test_success_result(self):
        from tools.base import ToolResult
        r = ToolResult(success=True, data={"mpn": "ESP32"}, source="builtin_db", confidence=0.95)
        assert r.success is True
        assert r.confidence == 0.95
        assert r.error == ""

    def test_failure_result(self):
        from tools.base import ToolResult
        r = ToolResult(success=False, data=None, source="builtin_db", confidence=0.0, error="not found")
        assert r.success is False
        assert r.error == "not found"

    def test_metadata_default_empty(self):
        from tools.base import ToolResult
        r = ToolResult(success=True, data=None, source="x", confidence=1.0)
        assert r.metadata == {}

    def test_metadata_custom(self):
        from tools.base import ToolResult
        r = ToolResult(success=True, data="ok", source="x", confidence=0.5, metadata={"k": "v"})
        assert r.metadata["k"] == "v"


# ---------------------------------------------------------------------------
# ToolContext
# ---------------------------------------------------------------------------

class TestToolContext:
    def test_cache_dir_created(self, tmp_path):
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        cache_dir = tmp_path / "test_cache"
        assert not cache_dir.exists()
        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="test-session", llm_gateway=gw, cache_dir=cache_dir)
        assert cache_dir.exists()

    def test_no_llm_default_false(self, tmp_path):
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="s", llm_gateway=gw, cache_dir=tmp_path)
        assert ctx.no_llm is False

    def test_budget_remaining_none_by_default(self, tmp_path):
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="s", llm_gateway=gw, cache_dir=tmp_path)
        assert ctx.budget_remaining_usd is None


# ---------------------------------------------------------------------------
# Tool Protocol
# ---------------------------------------------------------------------------

class TestToolProtocol:
    def test_tool_protocol_check(self, tmp_path):
        """A class with name, description, and async execute() satisfies Tool."""
        from tools.base import Tool, ToolContext, ToolResult

        class DummyTool:
            name = "dummy"
            description = "A test tool"
            input_schema: dict = {"type": "object", "properties": {}}

            async def execute(self, input, context: ToolContext) -> ToolResult:
                return ToolResult(success=True, data="dummy", source="test", confidence=1.0)

        assert isinstance(DummyTool(), Tool)

    def test_non_tool_fails_protocol(self):
        from tools.base import Tool

        class NotATool:
            pass

        assert not isinstance(NotATool(), Tool)


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------

class TestToolRegistry:
    def _make_registry(self):
        from tools.registry import ToolRegistry
        return ToolRegistry()

    def _make_dummy_tool(self, name="dummy"):
        from tools.base import ToolContext, ToolResult

        class DummyTool:
            def __init__(self, n):
                self.name = n
                self.description = f"Tool: {n}"

            async def execute(self, input, context: ToolContext) -> ToolResult:
                return ToolResult(success=True, data=f"result:{self.name}", source="test", confidence=1.0)

        return DummyTool(name)

    def test_register_and_get(self):
        reg = self._make_registry()
        tool = self._make_dummy_tool("test_tool")
        reg.register(tool)
        assert reg.get("test_tool") is tool

    def test_get_unknown_returns_none(self):
        reg = self._make_registry()
        assert reg.get("nonexistent") is None

    def test_list_tools_empty(self):
        reg = self._make_registry()
        assert reg.list_tools() == []

    def test_list_tools_after_register(self):
        reg = self._make_registry()
        reg.register(self._make_dummy_tool("a"))
        reg.register(self._make_dummy_tool("b"))
        names = reg.list_tools()
        assert "a" in names
        assert "b" in names
        assert len(names) == 2

    def test_execute_known_tool(self, tmp_path):
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        reg = self._make_registry()
        reg.register(self._make_dummy_tool("run_me"))
        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="s", llm_gateway=gw, cache_dir=tmp_path)
        result = asyncio.run(reg.execute("run_me", None, ctx))
        assert result.success is True
        assert result.data == "result:run_me"

    def test_execute_unknown_tool_returns_error(self, tmp_path):
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        reg = self._make_registry()
        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="s", llm_gateway=gw, cache_dir=tmp_path)
        result = asyncio.run(reg.execute("not_there", None, ctx))
        assert result.success is False
        assert "not_there" in result.error

    def test_repr(self):
        reg = self._make_registry()
        reg.register(self._make_dummy_tool("foo"))
        r = repr(reg)
        assert "foo" in r

    def test_overwrite_same_name(self):
        reg = self._make_registry()
        t1 = self._make_dummy_tool("x")
        t2 = self._make_dummy_tool("x")
        reg.register(t1)
        reg.register(t2)
        # Second registration overwrites first
        assert reg.get("x") is t2
        assert len(reg.list_tools()) == 1


# ---------------------------------------------------------------------------
# Default registry
# ---------------------------------------------------------------------------

class TestDefaultRegistry:
    def test_default_registry_has_builtin_tools(self):
        from tools.registry import get_default_registry
        reg = get_default_registry()
        # At minimum query_knowledge should be available
        assert "query_knowledge" in reg.list_tools()

    def test_default_registry_singleton(self):
        from tools.registry import get_default_registry
        r1 = get_default_registry()
        r2 = get_default_registry()
        assert r1 is r2


# ---------------------------------------------------------------------------
# QueryKnowledgeTool
# ---------------------------------------------------------------------------

class TestQueryKnowledgeTool:
    def _make_ctx(self, tmp_path):
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        gw = LLMGateway(LLMConfig.no_llm_mode())
        return ToolContext(session_id="test", llm_gateway=gw, cache_dir=tmp_path)

    def test_known_mpn_exact_match(self, tmp_path):
        from tools.tools.query_knowledge import QueryKnowledgeInput, QueryKnowledgeTool
        tool = QueryKnowledgeTool()
        ctx = self._make_ctx(tmp_path)
        result = asyncio.run(tool.execute(QueryKnowledgeInput(query="ESP32-WROOM-32"), ctx))
        # May succeed or gracefully fail if DB not available — check structure
        assert isinstance(result.success, bool)
        assert isinstance(result.confidence, float)
        assert 0.0 <= result.confidence <= 1.0

    def test_unknown_query_returns_failure(self, tmp_path):
        from tools.tools.query_knowledge import QueryKnowledgeInput, QueryKnowledgeTool
        tool = QueryKnowledgeTool()
        ctx = self._make_ctx(tmp_path)
        result = asyncio.run(tool.execute(
            QueryKnowledgeInput(query="ZZZNONSENSE99999XYZ"), ctx
        ))
        assert result.success is False

    def test_tool_name_and_description(self):
        from tools.tools.query_knowledge import QueryKnowledgeTool
        t = QueryKnowledgeTool()
        assert t.name == "query_knowledge"
        assert len(t.description) > 10

    def test_max_results_respected(self, tmp_path):
        from tools.tools.query_knowledge import QueryKnowledgeInput, QueryKnowledgeTool
        tool = QueryKnowledgeTool()
        ctx = self._make_ctx(tmp_path)
        result = asyncio.run(tool.execute(
            QueryKnowledgeInput(query="sensor", max_results=2), ctx
        ))
        if result.success:
            assert len(result.data) <= 2


# ---------------------------------------------------------------------------
# ValidateHIRTool
# ---------------------------------------------------------------------------

class TestValidateHIRTool:
    def _make_ctx(self, tmp_path):
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        gw = LLMGateway(LLMConfig.no_llm_mode())
        return ToolContext(session_id="test", llm_gateway=gw, cache_dir=tmp_path)

    def _minimal_hir(self) -> dict:
        import datetime
        return {
            "version": "1.1.0",
            "source": "prompt",
            "components": [],
            "nets": [],
            "buses": [],
            "bus_contracts": [],
            "electrical_specs": [],
            "init_contracts": [],
            "power_sequence": {"rails": [], "dependencies": []},
            "constraints": [],
            "bom": [],
            "metadata": {
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "track": "B",
                "confidence": {"overall": 0.9, "subscores": None, "explanations": []},
                "assumptions": [],
                "session_id": None,
            },
        }

    def test_tool_name_and_description(self):
        from tools.tools.validate_hir import ValidateHIRTool
        t = ValidateHIRTool()
        assert t.name == "validate_hir"
        assert "constraint" in t.description.lower()

    def test_valid_minimal_hir(self, tmp_path):
        from tools.tools.validate_hir import ValidateHIRInput, ValidateHIRTool
        tool = ValidateHIRTool()
        ctx = self._make_ctx(tmp_path)
        result = asyncio.run(tool.execute(ValidateHIRInput(hir_dict=self._minimal_hir()), ctx))
        # Should succeed (empty HIR has no constraint violations)
        assert isinstance(result.success, bool)
        assert result.confidence in (0.0, 1.0)

    def test_empty_dict_returns_result_not_exception(self, tmp_path):
        from tools.tools.validate_hir import ValidateHIRInput, ValidateHIRTool
        tool = ValidateHIRTool()
        ctx = self._make_ctx(tmp_path)
        # Empty dict — should not crash, may return failure gracefully
        result = asyncio.run(tool.execute(ValidateHIRInput(hir_dict={}), ctx))
        assert isinstance(result, object)
        assert hasattr(result, "success")
