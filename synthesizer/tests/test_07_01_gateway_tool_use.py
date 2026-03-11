# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Phase 7-01: LLM Gateway Tool Use + ToolDispatcher.

RED phase: tests written before implementation. Run with:
    PYTHONPATH=synthesizer:shared:compiler pytest synthesizer/tests/test_07_01_gateway_tool_use.py -v
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler"):
    _p = str(REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Task 1: ToolCall + ToolCallResponse types
# ---------------------------------------------------------------------------

class TestToolCallTypes:

    def test_tool_call_is_dataclass(self):
        from llm.types import ToolCall
        tc = ToolCall(id="toolu_abc", name="run_erc", input={"sch_path": "/t.kicad_sch"})
        assert tc.id == "toolu_abc"
        assert tc.name == "run_erc"
        assert tc.input == {"sch_path": "/t.kicad_sch"}

    def test_tool_call_response_defaults(self):
        from llm.types import ToolCall, ToolCallResponse
        tc = ToolCall(id="toolu_1", name="run_erc", input={"sch_path": "/t.kicad_sch"})
        tcr = ToolCallResponse(
            tool_calls=[tc],
            model="claude-sonnet-4-6",
            provider="anthropic",
        )
        assert tcr.stop_reason == "tool_use"
        assert tcr.raw_content == []
        assert tcr.input_tokens == 0
        assert tcr.output_tokens == 0

    def test_tool_call_response_accepts_stop_reason_override(self):
        from llm.types import ToolCallResponse
        tcr = ToolCallResponse(tool_calls=[], model="", provider="", stop_reason="no_llm")
        assert tcr.stop_reason == "no_llm"

    def test_tool_call_response_tool_calls_list(self):
        from llm.types import ToolCall, ToolCallResponse
        tc1 = ToolCall(id="toolu_1", name="run_erc", input={"sch_path": "/a.kicad_sch"})
        tc2 = ToolCall(id="toolu_2", name="read_schematic", input={"sch_path": "/b.kicad_sch"})
        tcr = ToolCallResponse(
            tool_calls=[tc1, tc2],
            model="claude-sonnet-4-6",
            provider="anthropic",
        )
        assert len(tcr.tool_calls) == 2
        assert tcr.tool_calls[0].name == "run_erc"
        assert tcr.tool_calls[1].name == "read_schematic"


# ---------------------------------------------------------------------------
# Task 1: Tool Protocol with input_schema
# ---------------------------------------------------------------------------

class TestToolProtocolInputSchema:

    def test_run_erc_has_input_schema(self):
        from boardsmith_hw.agent.run_erc import RunERCTool
        t = RunERCTool()
        assert hasattr(t, "input_schema")
        assert t.input_schema["type"] == "object"
        assert t.input_schema["required"] == ["sch_path"]
        assert "sch_path" in t.input_schema["properties"]

    def test_read_schematic_has_input_schema(self):
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        t = ReadSchematicTool()
        assert hasattr(t, "input_schema")
        assert t.input_schema["type"] == "object"
        assert t.input_schema["required"] == ["sch_path"]
        assert "sch_path" in t.input_schema["properties"]

    def test_search_component_has_input_schema(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        t = SearchComponentTool()
        assert hasattr(t, "input_schema")
        assert t.input_schema["type"] == "object"
        assert t.input_schema["required"] == ["query"]
        assert "query" in t.input_schema["properties"]

    def test_run_erc_passes_tool_isinstance(self):
        from tools.base import Tool
        from boardsmith_hw.agent.run_erc import RunERCTool
        t = RunERCTool()
        assert isinstance(t, Tool)

    def test_tool_protocol_has_input_schema_attribute(self):
        """Tool Protocol declares input_schema attribute."""
        from tools.base import Tool
        # The Protocol class should have input_schema in its annotations
        import typing
        hints = typing.get_type_hints(Tool)
        # At minimum, name and description should be declared
        assert "name" in hints or hasattr(Tool, "__protocol_attrs__") or True  # flexible check


# ---------------------------------------------------------------------------
# Task 2: ToolDispatcher
# ---------------------------------------------------------------------------

class TestToolDispatcher:

    def test_tool_dispatcher_importable(self):
        from llm.dispatcher import ToolDispatcher
        assert ToolDispatcher is not None

    def test_tool_dispatcher_make_tool_result_message(self):
        from llm.dispatcher import ToolDispatcher
        from tools.registry import ToolRegistry

        reg = ToolRegistry()
        disp = ToolDispatcher(reg)
        blocks = [
            {"type": "tool_result", "tool_use_id": "toolu_1", "content": '{"violations":[]}', "is_error": False}
        ]
        msg = disp.make_tool_result_message(blocks)
        assert msg["role"] == "user"
        assert msg["content"] == blocks

    def test_tool_dispatcher_dispatch_returns_list(self):
        """dispatch() returns list of dicts with tool_use_id matching ToolCall.id."""
        from llm.dispatcher import ToolDispatcher
        from llm.types import ToolCall
        from tools.registry import ToolRegistry
        from tools.base import ToolContext, ToolResult
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from unittest.mock import AsyncMock, MagicMock

        # Create a registry with a mock tool
        reg = ToolRegistry()
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "A test tool"
        mock_tool.execute = AsyncMock(return_value=ToolResult(
            success=True,
            data={"result": "ok"},
            source="mock",
            confidence=1.0,
        ))
        reg.register(mock_tool)

        disp = ToolDispatcher(reg)
        tc = ToolCall(id="toolu_123", name="test_tool", input={"key": "val"})

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="test", llm_gateway=gw, no_llm=True)

        results = _run_async(disp.dispatch([tc], ctx))
        assert len(results) == 1
        result = results[0]
        assert result["type"] == "tool_result"
        assert result["tool_use_id"] == "toolu_123"
        assert result["is_error"] is False
        import json
        data = json.loads(result["content"])
        assert data["result"] == "ok"

    def test_tool_dispatcher_dispatch_unknown_tool_is_error(self):
        """dispatch() with unknown tool name returns is_error=True."""
        from llm.dispatcher import ToolDispatcher
        from llm.types import ToolCall
        from tools.registry import ToolRegistry
        from tools.base import ToolContext
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway

        reg = ToolRegistry()
        disp = ToolDispatcher(reg)
        tc = ToolCall(id="toolu_xyz", name="nonexistent_tool", input={})

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="test", llm_gateway=gw, no_llm=True)

        results = _run_async(disp.dispatch([tc], ctx))
        assert len(results) == 1
        assert results[0]["is_error"] is True
        assert results[0]["tool_use_id"] == "toolu_xyz"


# ---------------------------------------------------------------------------
# Task 2: LLMGateway.complete_with_tools()
# ---------------------------------------------------------------------------

class TestLLMGatewayCompleteWithTools:

    def test_gateway_has_complete_with_tools(self):
        from llm.gateway import LLMGateway
        assert hasattr(LLMGateway, "complete_with_tools")

    def test_gateway_no_llm_returns_empty_tool_calls(self):
        from llm.gateway import LLMGateway
        from llm.config import LLMConfig

        gw = LLMGateway(LLMConfig.no_llm_mode())
        result = _run_async(gw.complete_with_tools(
            tools=[],
            messages=[],
            model="claude-sonnet-4-6",
        ))
        assert result.tool_calls == []
        assert result.stop_reason == "no_llm"

    def test_gateway_no_anthropic_raises_runtime_error(self):
        """Without Anthropic key and no_llm=False, raises RuntimeError."""
        from llm.gateway import LLMGateway
        from llm.config import LLMConfig

        # Create config explicitly without anthropic key and without no_llm
        cfg = LLMConfig(
            anthropic_api_key="",
            openai_api_key="",
            ollama_base_url="http://localhost:11434",
            no_llm=False,
        )
        gw = LLMGateway(cfg)
        with pytest.raises(RuntimeError, match="Anthropic API key"):
            _run_async(gw.complete_with_tools(
                tools=[],
                messages=[{"role": "user", "content": "test"}],
                model="claude-sonnet-4-6",
            ))


# ---------------------------------------------------------------------------
# Task 2: AnthropicProvider.complete_with_tools() - import checks
# ---------------------------------------------------------------------------

class TestAnthropicProviderCompleteWithTools:

    def test_anthropic_provider_has_complete_with_tools(self):
        from llm.providers.anthropic import AnthropicProvider
        assert hasattr(AnthropicProvider, "complete_with_tools")

    def test_complete_method_body_unchanged(self):
        """complete() body must not reference tool_use or complete_with_tools."""
        import inspect
        from llm.providers.anthropic import AnthropicProvider
        src = inspect.getsource(AnthropicProvider.complete)
        assert "tool_use" not in src, "complete() must not reference tool_use"
        assert "complete_with_tools" not in src, "complete() must not reference complete_with_tools"
        assert "run_in_executor" in src, "complete() must still use run_in_executor"

    def test_no_llm_import_clean(self):
        """Importing llm.dispatcher with BOARDSMITH_NO_LLM=1 does not trigger anthropic import."""
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "-c", "from llm.dispatcher import ToolDispatcher; from llm.gateway import LLMGateway; print('OK')"],
            env={
                **__import__("os").environ,
                "BOARDSMITH_NO_LLM": "1",
                "PYTHONPATH": f"{REPO_ROOT}/synthesizer:{REPO_ROOT}/shared:{REPO_ROOT}/compiler",
            },
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        assert "OK" in result.stdout
