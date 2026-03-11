# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for SearchComponentTool."""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler"):
    _p = str(REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _make_mock_context():
    ctx = MagicMock()
    ctx.no_llm = False
    return ctx


def _run(coro):
    return asyncio.run(coro)


class TestSearchComponentTool:
    def test_name(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        assert SearchComponentTool().name == "search_component"

    def test_empty_query_returns_failure(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        tool = SearchComponentTool()
        result = _run(tool.execute({"query": ""}, _make_mock_context()))
        assert result.success is False
        assert "No query" in result.error

    def test_missing_query_key_returns_failure(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        tool = SearchComponentTool()
        result = _run(tool.execute({}, _make_mock_context()))
        assert result.success is False

    def test_query_with_results_returns_success(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        tool = SearchComponentTool()
        fake_results = [{"part_number": "ESP32", "description": "WiFi MCU",
                         "value": "ESP32", "package": "QFN", "lcsc_id": "C701341"}]
        with patch("knowledge.db.search", return_value=fake_results):
            result = _run(tool.execute({"query": "ESP32"}, _make_mock_context()))
        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0]["part_number"] == "ESP32"

    def test_result_items_have_required_fields(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        tool = SearchComponentTool()
        fake_results = [{"part_number": "BME280", "description": "Humidity sensor",
                         "value": "BME280", "package": "LGA", "lcsc_id": "C92489"}]
        with patch("knowledge.db.search", return_value=fake_results):
            result = _run(tool.execute({"query": "BME280"}, _make_mock_context()))
        item = result.data[0]
        for key in ("part_number", "description", "lcsc_id"):
            assert key in item, f"Missing: {key}"

    def test_no_results_returns_failure(self):
        from boardsmith_hw.agent.search_component import SearchComponentTool
        tool = SearchComponentTool()
        with patch("knowledge.db.search", return_value=[]), \
             patch("knowledge.db.find_by_mpn", return_value=None):
            result = _run(tool.execute({"query": "NONEXISTENT_XYZ_99999"}, _make_mock_context()))
        assert result.success is False
        assert result.data == []

    def test_real_db_query(self):
        """Smoke test against real boardsmith.db — verifies DB is accessible."""
        from boardsmith_hw.agent.search_component import SearchComponentTool
        tool = SearchComponentTool()
        # Use a generic term likely in any component DB
        result = _run(tool.execute({"query": "resistor"}, _make_mock_context()))
        # DB may or may not have results — just confirm no exception
        assert isinstance(result.data, list)
