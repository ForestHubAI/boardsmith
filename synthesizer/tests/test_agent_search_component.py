# SPDX-License-Identifier: AGPL-3.0-or-later
"""TDD tests for SearchComponentTool — boardsmith_hw/agent/search_component.py.

RED phase: tests written before implementation.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    """Run a coroutine synchronously."""
    return asyncio.run(coro)


def make_ctx():
    """Make a minimal ToolContext mock."""
    ctx = MagicMock()
    ctx.no_llm = False
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSearchComponentToolAttributes:
    def test_name_is_search_component(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        t = SearchComponentTool()
        assert t.name == "search_component"

    def test_description_is_non_empty(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        t = SearchComponentTool()
        assert len(t.description) > 10

    def test_description_mentions_lcsc(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        t = SearchComponentTool()
        assert "lcsc" in t.description.lower() or "LCSC" in t.description


class TestSearchComponentToolExecute:
    def test_empty_query_returns_failure(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        t = SearchComponentTool()
        with patch("knowledge.db") as mock_db:
            result = run(t.execute({"query": ""}, make_ctx()))
        assert result.success is False
        assert result.error is not None
        assert "query" in result.error.lower() or "No query" in result.error

    def test_missing_query_key_returns_failure(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        t = SearchComponentTool()
        with patch("knowledge.db") as mock_db:
            result = run(t.execute({}, make_ctx()))
        assert result.success is False

    def test_non_dict_input_returns_failure(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        t = SearchComponentTool()
        with patch("knowledge.db") as mock_db:
            result = run(t.execute("not a dict", make_ctx()))
        assert result.success is False

    def test_valid_query_returns_success_with_results(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        t = SearchComponentTool()
        mock_results = [
            {
                "part_number": "ESP32-WROOM-32",
                "description": "ESP32 WiFi+BT Module",
                "value": "",
                "package": "SMD",
                "lcsc_id": "C701341",
                "datasheet_url": "https://example.com",
            }
        ]
        with patch("knowledge.db") as mock_db:
            mock_db.search.return_value = mock_results
            mock_db.find_by_mpn.return_value = None
            result = run(t.execute({"query": "ESP32"}, make_ctx()))

        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) >= 1

    def test_result_items_have_required_keys(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        t = SearchComponentTool()
        mock_results = [
            {
                "part_number": "ESP32-WROOM-32",
                "description": "ESP32 WiFi+BT Module",
                "value": "",
                "package": "SMD",
                "lcsc_id": "C701341",
            }
        ]
        with patch("knowledge.db") as mock_db:
            mock_db.search.return_value = mock_results
            mock_db.find_by_mpn.return_value = None
            result = run(t.execute({"query": "ESP32"}, make_ctx()))

        assert result.success is True
        item = result.data[0]
        for key in ("part_number", "description", "lcsc_id"):
            assert key in item, f"Missing key: {key}"

    def test_fts_no_results_falls_back_to_mpn(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        t = SearchComponentTool()
        mpn_hit = {
            "part_number": "STM32F103C8T6",
            "description": "STM32 microcontroller",
            "value": "",
            "package": "LQFP48",
            "lcsc_id": "C8734",
        }
        with patch("knowledge.db") as mock_db:
            mock_db.search.return_value = []
            mock_db.find_by_mpn.return_value = mpn_hit
            result = run(t.execute({"query": "STM32F103C8T6"}, make_ctx()))

        assert result.success is True
        assert result.data[0]["part_number"] == "STM32F103C8T6"

    def test_completely_unknown_query_returns_failure_without_raising(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        t = SearchComponentTool()
        with patch("knowledge.db") as mock_db:
            mock_db.search.return_value = []
            mock_db.find_by_mpn.return_value = None
            result = run(t.execute({"query": "nonexistent_xyz_99999"}, make_ctx()))

        assert result.success is False
        assert isinstance(result.data, list)
        assert len(result.data) == 0

    def test_db_exception_does_not_raise(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        t = SearchComponentTool()
        with patch("knowledge.db") as mock_db:
            mock_db.search.side_effect = RuntimeError("DB exploded")
            result = run(t.execute({"query": "ESP32"}, make_ctx()))

        assert result.success is False
        assert result.error is not None
        assert "DB exploded" in result.error

    def test_source_is_builtin_db(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        t = SearchComponentTool()
        with patch("knowledge.db") as mock_db:
            mock_db.search.return_value = [{"part_number": "X", "description": "Y", "lcsc_id": "Z", "value": "", "package": ""}]
            mock_db.find_by_mpn.return_value = None
            result = run(t.execute({"query": "X"}, make_ctx()))

        assert result.source == "builtin_db"

    def test_confidence_0_for_empty_result(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        t = SearchComponentTool()
        with patch("knowledge.db") as mock_db:
            mock_db.search.return_value = []
            mock_db.find_by_mpn.return_value = None
            result = run(t.execute({"query": "nothing"}, make_ctx()))

        assert result.confidence == 0.0

    def test_confidence_positive_for_found_results(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        t = SearchComponentTool()
        with patch("knowledge.db") as mock_db:
            mock_db.search.return_value = [{"part_number": "R1", "description": "Resistor", "lcsc_id": "C1", "value": "10k", "package": "0402"}]
            mock_db.find_by_mpn.return_value = None
            result = run(t.execute({"query": "resistor"}, make_ctx()))

        assert result.confidence > 0.0


class TestSearchComponentNoLLMImports:
    def test_no_llm_imports_at_module_level(self):
        """Confirm no anthropic/openai imports at module level."""
        import importlib, sys, inspect
        # Remove cached module if present
        for mod in list(sys.modules.keys()):
            if "boardsmith_hw.agent.search_component" in mod:
                del sys.modules[mod]

        import boardsmith_hw.agent.search_component as m
        src = inspect.getsource(m)
        top_level_lines = [l for l in src.splitlines() if l.startswith("import ") or l.startswith("from ")]
        for line in top_level_lines:
            assert "anthropic" not in line, f"anthropic imported at top level: {line}"
            assert "openai" not in line, f"openai imported at top level: {line}"


class TestAgentToolsInit:
    def test_all_three_tools_exported(self):
        """tools/__init__.py must export RunERCTool, ReadSchematicTool, SearchComponentTool."""
        from boardsmith_hw.agent.tools import RunERCTool, ReadSchematicTool, SearchComponentTool
        assert RunERCTool is not None
        assert ReadSchematicTool is not None
        assert SearchComponentTool is not None

    def test_all_three_in_dunder_all(self):
        import boardsmith_hw.agent.tools as pkg
        assert "SearchComponentTool" in pkg.__all__
        assert "RunERCTool" in pkg.__all__
        assert "ReadSchematicTool" in pkg.__all__
