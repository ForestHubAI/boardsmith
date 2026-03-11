# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for ToolDispatcher.

GATE-02: dispatch() routes tool_calls to ToolRegistry and returns tool_result messages.

Run: PYTHONPATH=synthesizer:shared:compiler pytest tests/agent/test_tool_dispatcher.py -x -v
"""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler"):
    _p = str(REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _run(coro):
    return asyncio.run(coro)


def _make_tool_call(tool_id="toolu_01", name="run_erc", input_dict=None):
    from llm.types import ToolCall
    return ToolCall(id=tool_id, name=name, input=input_dict or {"sch_path": "/tmp/t.kicad_sch"})


def _make_mock_registry(tool_name="run_erc", success=True, data=None, error=""):
    """Return a mock ToolRegistry whose execute() returns a ToolResult."""
    from tools.base import ToolResult
    registry = MagicMock()
    registry.execute = AsyncMock(return_value=ToolResult(
        success=success,
        data=data or {"violations": [], "error_count": 0},
        source="kicad_cli_erc",
        confidence=1.0,
        error=error,
    ))
    return registry


def _make_context():
    ctx = MagicMock()
    ctx.no_llm = False
    return ctx


class TestToolDispatcher:
    """GATE-02: dispatch() routes tool_calls to ToolRegistry."""

    def test_dispatch_calls_registry_execute(self):
        """dispatch() calls registry.execute() with correct name, input, context."""
        from llm.dispatcher import ToolDispatcher

        registry = _make_mock_registry()
        dispatcher = ToolDispatcher(registry)
        tc = _make_tool_call(tool_id="toolu_99", name="run_erc",
                              input_dict={"sch_path": "/tmp/test.kicad_sch"})
        ctx = _make_context()

        _run(dispatcher.dispatch([tc], ctx))

        registry.execute.assert_awaited_once_with(
            "run_erc", {"sch_path": "/tmp/test.kicad_sch"}, ctx
        )

    def test_dispatch_multiple_tool_calls(self):
        """dispatch() processes all tool_calls in order."""
        from llm.dispatcher import ToolDispatcher

        registry = _make_mock_registry()
        dispatcher = ToolDispatcher(registry)
        tc1 = _make_tool_call(tool_id="toolu_1", name="run_erc")
        tc2 = _make_tool_call(tool_id="toolu_2", name="run_erc")
        ctx = _make_context()

        results = _run(dispatcher.dispatch([tc1, tc2], ctx))

        assert len(results) == 2
        assert registry.execute.await_count == 2


class TestToolResultShape:
    """GATE-02: tool_result dicts have correct shape with matching tool_use_id."""

    def test_tool_use_id_matches(self):
        """tool_result must carry the same tool_use_id as the ToolCall."""
        from llm.dispatcher import ToolDispatcher

        registry = _make_mock_registry()
        dispatcher = ToolDispatcher(registry)
        tc = _make_tool_call(tool_id="toolu_MATCH_ME")
        ctx = _make_context()

        results = _run(dispatcher.dispatch([tc], ctx))

        assert results[0]["tool_use_id"] == "toolu_MATCH_ME"

    def test_tool_result_type_field(self):
        from llm.dispatcher import ToolDispatcher

        registry = _make_mock_registry()
        dispatcher = ToolDispatcher(registry)
        tc = _make_tool_call()
        ctx = _make_context()

        results = _run(dispatcher.dispatch([tc], ctx))

        assert results[0]["type"] == "tool_result"

    def test_success_result_content_is_json(self):
        """Content of a successful tool_result is valid JSON."""
        from llm.dispatcher import ToolDispatcher

        registry = _make_mock_registry(data={"violations": [], "error_count": 0})
        dispatcher = ToolDispatcher(registry)
        tc = _make_tool_call()
        ctx = _make_context()

        results = _run(dispatcher.dispatch([tc], ctx))

        parsed = json.loads(results[0]["content"])
        assert "violations" in parsed
        assert results[0]["is_error"] is False

    def test_error_result_is_error_true(self):
        """is_error=True when ToolResult.success is False."""
        from llm.dispatcher import ToolDispatcher

        registry = _make_mock_registry(success=False, data=None,
                                        error="kicad-cli not found")
        dispatcher = ToolDispatcher(registry)
        tc = _make_tool_call()
        ctx = _make_context()

        results = _run(dispatcher.dispatch([tc], ctx))

        assert results[0]["is_error"] is True
        assert "kicad-cli" in results[0]["content"]

    def test_make_tool_result_message_shape(self):
        """make_tool_result_message() wraps blocks in a user message dict."""
        from llm.dispatcher import ToolDispatcher

        registry = _make_mock_registry()
        dispatcher = ToolDispatcher(registry)
        blocks = [{"type": "tool_result", "tool_use_id": "x", "content": "{}", "is_error": False}]

        msg = dispatcher.make_tool_result_message(blocks)

        assert msg["role"] == "user"
        assert msg["content"] == blocks
