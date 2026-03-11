# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for AnthropicProvider.complete_with_tools() and LLMGateway tool-use gate.

GATE-01: complete_with_tools() returns ToolCallResponse; complete() is unchanged.
All tests use mocked Anthropic SDK — no real API calls.

Run: PYTHONPATH=synthesizer:shared:compiler pytest tests/agent/test_anthropic_tool_use.py -x -v
"""
from __future__ import annotations
import asyncio
import inspect
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("anthropic", reason="anthropic SDK not installed (pip install boardsmith[llm])")

REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler"):
    _p = str(REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _run(coro):
    return asyncio.run(coro)


def _make_mock_tool_use_block(tool_id="toolu_01abc", name="run_erc", input_dict=None):
    """Build a mock ToolUseBlock as returned by the Anthropic SDK."""
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = input_dict or {"sch_path": "/tmp/test.kicad_sch"}
    return block


def _make_mock_text_block(text="Let me check that for you."):
    """Build a mock TextBlock (often emitted before tool_use)."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_mock_response(content_blocks, stop_reason="tool_use"):
    """Build a mock Anthropic API response."""
    resp = MagicMock()
    resp.content = content_blocks
    resp.stop_reason = stop_reason
    resp.usage = MagicMock()
    resp.usage.input_tokens = 42
    resp.usage.output_tokens = 17
    return resp


class TestCompleteWithTools:
    """GATE-01: complete_with_tools() returns correct ToolCallResponse."""

    def test_returns_tool_call_response(self):
        from llm.providers.anthropic import AnthropicProvider
        from llm.types import ToolCallResponse

        tool_block = _make_mock_tool_use_block()
        mock_response = _make_mock_response([tool_block])

        provider = AnthropicProvider(api_key="test-key")

        with patch("anthropic.Anthropic") as MockClient:
            instance = MockClient.return_value
            instance.messages.create.return_value = mock_response

            result = _run(provider.complete_with_tools(
                tools=[{"name": "run_erc", "description": "...", "input_schema": {}}],
                messages=[{"role": "user", "content": "Check ERC"}],
                model="claude-sonnet-4-6",
            ))

        assert isinstance(result, ToolCallResponse)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "toolu_01abc"
        assert result.tool_calls[0].name == "run_erc"
        assert result.tool_calls[0].input == {"sch_path": "/tmp/test.kicad_sch"}

    def test_tool_use_id_in_response(self):
        """tool_use_id must match the block.id from the API response."""
        from llm.providers.anthropic import AnthropicProvider

        tool_block = _make_mock_tool_use_block(tool_id="toolu_UNIQUE_99")
        mock_response = _make_mock_response([tool_block])

        provider = AnthropicProvider(api_key="test-key")

        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = mock_response
            result = _run(provider.complete_with_tools(
                tools=[], messages=[], model="claude-sonnet-4-6",
            ))

        assert result.tool_calls[0].id == "toolu_UNIQUE_99"

    def test_filters_text_blocks(self):
        """TextBlock preamble before tool_use must be ignored (not included in tool_calls)."""
        from llm.providers.anthropic import AnthropicProvider

        text_block = _make_mock_text_block("Let me check.")
        tool_block = _make_mock_tool_use_block()
        mock_response = _make_mock_response([text_block, tool_block])

        provider = AnthropicProvider(api_key="test-key")

        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = mock_response
            result = _run(provider.complete_with_tools(
                tools=[], messages=[], model="claude-sonnet-4-6",
            ))

        # TextBlock must not appear in tool_calls
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "run_erc"

    def test_raw_content_is_sdk_objects(self):
        """raw_content holds SDK content block objects directly (not serialized dicts)."""
        from llm.providers.anthropic import AnthropicProvider

        tool_block = _make_mock_tool_use_block()
        mock_response = _make_mock_response([tool_block])

        provider = AnthropicProvider(api_key="test-key")

        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = mock_response
            result = _run(provider.complete_with_tools(
                tools=[], messages=[], model="claude-sonnet-4-6",
            ))

        # raw_content is the SDK content list, not a manually serialized structure
        assert result.raw_content is mock_response.content

    def test_token_counts(self):
        from llm.providers.anthropic import AnthropicProvider

        tool_block = _make_mock_tool_use_block()
        mock_response = _make_mock_response([tool_block])

        provider = AnthropicProvider(api_key="test-key")

        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = mock_response
            result = _run(provider.complete_with_tools(
                tools=[], messages=[], model="claude-sonnet-4-6",
            ))

        assert result.input_tokens == 42
        assert result.output_tokens == 17

    def test_import_error_without_sdk(self, monkeypatch):
        """Raises ImportError with install hint when anthropic not installed."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "anthropic":
                raise ImportError("No module named 'anthropic'")
            return real_import(name, *args, **kwargs)

        from llm.providers.anthropic import AnthropicProvider
        provider = AnthropicProvider(api_key="test")

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(ImportError, match="pip install boardsmith"):
                _run(provider.complete_with_tools(tools=[], messages=[], model="x"))


class TestCompleteUnchanged:
    """GATE-01: The existing complete() method must not be modified."""

    def test_complete_does_not_reference_tool_use(self):
        """complete() source must not contain 'tool_use' — it is text-only."""
        from llm.providers.anthropic import AnthropicProvider
        src = inspect.getsource(AnthropicProvider.complete)
        assert "tool_use" not in src, (
            "complete() must not reference tool_use — it is a text-only method"
        )

    def test_complete_uses_run_in_executor(self):
        """complete() must use run_in_executor (not a direct sync call)."""
        from llm.providers.anthropic import AnthropicProvider
        src = inspect.getsource(AnthropicProvider.complete)
        assert "run_in_executor" in src

    def test_complete_returns_llm_response(self):
        """complete() must still return LLMResponse (not ToolCallResponse)."""
        from llm.providers.anthropic import AnthropicProvider
        from llm.types import LLMResponse

        text_block = MagicMock()
        text_block.text = "Hello from Claude"
        mock_response = MagicMock()
        mock_response.content = [text_block]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)

        provider = AnthropicProvider(api_key="test-key")

        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = mock_response
            from llm.types import Message
            result = _run(provider.complete(
                messages=[Message(role="user", content="hi")],
                system=None,
                model="claude-sonnet-4-6",
                temperature=0.0,
                max_tokens=100,
            ))

        assert isinstance(result, LLMResponse)
        assert result.content == "Hello from Claude"


class TestNoLLMGate:
    """GATE-01: LLMGateway.complete_with_tools() is gated by no_llm config."""

    def test_no_llm_returns_empty_tool_calls(self):
        from llm.gateway import LLMGateway
        from llm.config import LLMConfig
        from llm.types import ToolCallResponse

        gw = LLMGateway(LLMConfig.no_llm_mode())
        result = _run(gw.complete_with_tools(
            tools=[], messages=[], model="claude-sonnet-4-6",
        ))

        assert isinstance(result, ToolCallResponse)
        assert result.tool_calls == []
        assert result.stop_reason == "no_llm"

    def test_no_anthropic_key_raises(self, monkeypatch):
        from llm.gateway import LLMGateway
        from llm.config import LLMConfig

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # Clear BOARDSMITH_NO_LLM so module-level setdefault from synthesizer tests
        # does not cause LLMConfig.from_env() to produce no_llm=True.
        monkeypatch.delenv("BOARDSMITH_NO_LLM", raising=False)
        # Build config without anthropic key (no_llm=False)
        cfg = LLMConfig.from_env()
        cfg.anthropic_api_key = ""
        gw = LLMGateway(cfg)

        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            _run(gw.complete_with_tools(tools=[], messages=[], model="claude-sonnet-4-6"))
