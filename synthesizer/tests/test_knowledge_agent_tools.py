# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Phase 11 — Knowledge Agent tools, cache merge, provenance, and promotion.

Tests cover:
  1. Agent has all 5 tools (query_knowledge, search_octopart, web_search, download_pdf, extract_datasheet)
  2. Cache merge enriches data from multiple sources
  3. Provenance tracking per field
  4. Improved cache search (filename + content)
  5. Promote quality check / format helpers
  6. No-LLM mode skips agent
  7. Dynamic modality lookup via tags
  8. Result-to-dict includes extended fields
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure shared and synthesizer are importable
_repo = Path(__file__).parent.parent.parent
for _sub in ("shared", "synthesizer", "compiler"):
    _p = str(_repo / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# 1. Agent has all 5 tools
# ---------------------------------------------------------------------------

class TestAgentToolRegistration:
    """Verify the agent registers all 5 tools in _run_agent."""

    def test_agent_has_all_five_tools(self):
        from agents.knowledge_agent import KnowledgeAgent

        agent = KnowledgeAgent(cache_dir=Path("/tmp/boardsmith_test_cache_tools"))

        # We mock the gateway and react_loop to capture the tools dict
        captured_tools: dict = {}

        async def mock_react_loop(task, tools, gateway, context, max_steps, task_type):
            captured_tools.update(tools)
            from agents.react_loop import ReActResult
            return ReActResult(answer="", steps=[], success=False, error="mock")

        mock_gw = MagicMock()
        mock_gw.is_llm_available.return_value = True

        with patch("agents.react_loop.run_react_loop", side_effect=mock_react_loop):
            asyncio.get_event_loop().run_until_complete(agent._run_agent("test query", mock_gw))

        expected_tools = {"query_knowledge", "search_octopart", "web_search", "download_pdf", "extract_datasheet"}
        assert set(captured_tools.keys()) == expected_tools, (
            f"Expected tools {expected_tools}, got {set(captured_tools.keys())}"
        )

    def test_agent_task_prompt_mentions_octopart(self):
        """The task prompt should guide the agent to use Octopart and web_search."""
        from agents.knowledge_agent import KnowledgeAgent

        agent = KnowledgeAgent(cache_dir=Path("/tmp/boardsmith_test_cache_prompt"))

        captured_task: list[str] = []

        async def mock_react_loop(task, tools, gateway, context, max_steps, task_type):
            captured_task.append(task)
            from agents.react_loop import ReActResult
            return ReActResult(answer="", steps=[], success=False, error="mock")

        mock_gw = MagicMock()
        mock_gw.is_llm_available.return_value = True

        with patch("agents.react_loop.run_react_loop", side_effect=mock_react_loop):
            asyncio.get_event_loop().run_until_complete(agent._run_agent("SCD41", mock_gw))

        assert captured_task, "Task was not captured"
        task_text = captured_task[0].lower()
        assert "octopart" in task_text or "search_octopart" in task_text
        assert "web_search" in task_text or "web search" in task_text


# ---------------------------------------------------------------------------
# 2. Cache merge
# ---------------------------------------------------------------------------

class TestCacheMerge:
    """Test that merging cache entries enriches data without losing information."""

    def test_merge_fills_empty_fields(self):
        from agents.knowledge_agent import KnowledgeAgent

        existing = {
            "mpn": "SCD41",
            "name": "SCD41 CO2 Sensor",
            "manufacturer": "",
            "category": "sensor",
            "interface_types": ["I2C"],
            "electrical_ratings": {"vdd_min": 2.4, "vdd_max": 5.5},
            "known_i2c_addresses": ["0x62"],
            "unit_cost_usd": 0.0,
            "tags": ["co2"],
            "package": "",
            "description": "",
            "timing_caps": {},
            "_provenance": {"source": "agent_extracted", "confidence": 0.6, "field_sources": {}},
        }

        new = {
            "mpn": "SCD41",
            "name": "SCD41 CO2 Sensor",
            "manufacturer": "Sensirion",
            "category": "sensor",
            "interface_types": ["I2C"],
            "electrical_ratings": {"vdd_min": 2.4, "vdd_max": 5.5, "current_draw_typical_ma": 19.0},
            "known_i2c_addresses": ["0x62"],
            "unit_cost_usd": 12.50,
            "tags": ["co2", "environmental"],
            "package": "DFN-10",
            "description": "CO2, temperature, and humidity sensor",
            "timing_caps": {"i2c_max_clock_hz": 100000},
            "_provenance": {"source": "octopart:nexar", "confidence": 0.8, "field_sources": {}},
        }

        merged = KnowledgeAgent._merge_dicts(existing, new, "octopart:nexar")

        assert merged["manufacturer"] == "Sensirion"
        assert merged["package"] == "DFN-10"
        assert merged["description"] == "CO2, temperature, and humidity sensor"
        assert merged["unit_cost_usd"] == 12.50
        assert "environmental" in merged["tags"]
        assert "co2" in merged["tags"]
        assert merged["electrical_ratings"]["current_draw_typical_ma"] == 19.0
        assert merged["timing_caps"]["i2c_max_clock_hz"] == 100000
        # Original data preserved
        assert merged["electrical_ratings"]["vdd_min"] == 2.4
        assert merged["known_i2c_addresses"] == ["0x62"]

    def test_merge_does_not_overwrite_existing(self):
        from agents.knowledge_agent import KnowledgeAgent

        existing = {
            "mpn": "SCD41",
            "manufacturer": "Sensirion",
            "electrical_ratings": {"vdd_min": 2.4},
            "tags": ["co2"],
            "_provenance": {"source": "octopart", "confidence": 0.8, "field_sources": {}},
        }
        new = {
            "mpn": "SCD41",
            "manufacturer": "Unknown",  # worse data — but not empty
            "electrical_ratings": {"vdd_min": 0},  # zero = empty
            "tags": ["sensor"],
            "_provenance": {"source": "web", "confidence": 0.5, "field_sources": {}},
        }

        merged = KnowledgeAgent._merge_dicts(existing, new, "web")

        # Existing manufacturer should NOT be overwritten (merge only fills empty)
        assert merged["manufacturer"] == "Sensirion"
        assert merged["electrical_ratings"]["vdd_min"] == 2.4
        # Tags should be unioned
        assert "co2" in merged["tags"]
        assert "sensor" in merged["tags"]


# ---------------------------------------------------------------------------
# 3. Provenance tracking
# ---------------------------------------------------------------------------

class TestProvenance:
    """Test that field-level provenance is tracked correctly."""

    def test_field_sources_tracked(self):
        from agents.knowledge_agent import KnowledgeAgent

        existing = {
            "mpn": "SCD41",
            "manufacturer": "",
            "package": "",
            "description": "",
            "electrical_ratings": {},
            "timing_caps": {},
            "tags": [],
            "interface_types": [],
            "known_i2c_addresses": [],
            "unit_cost_usd": 0,
            "_provenance": {"source": "agent", "confidence": 0.5, "field_sources": {}},
        }
        new = {
            "mpn": "SCD41",
            "manufacturer": "Sensirion",
            "package": "DFN-10",
            "description": "CO2 sensor",
            "electrical_ratings": {"vdd_min": 2.4},
            "timing_caps": {"i2c_max_clock_hz": 100000},
            "tags": ["co2"],
            "interface_types": ["I2C"],
            "known_i2c_addresses": ["0x62"],
            "unit_cost_usd": 12.5,
            "_provenance": {"source": "octopart", "confidence": 0.8, "field_sources": {}},
        }

        merged = KnowledgeAgent._merge_dicts(existing, new, "octopart")
        fs = merged["_provenance"]["field_sources"]

        assert fs["manufacturer"] == "octopart"
        assert fs["package"] == "octopart"
        assert fs["description"] == "octopart"
        assert fs["electrical_ratings.vdd_min"] == "octopart"
        assert fs["timing_caps.i2c_max_clock_hz"] == "octopart"
        assert fs["unit_cost_usd"] == "octopart"

    def test_confidence_takes_max(self):
        from agents.knowledge_agent import KnowledgeAgent

        existing = {
            "mpn": "X",
            "_provenance": {"source": "a", "confidence": 0.9, "field_sources": {}},
        }
        new = {
            "mpn": "X",
            "_provenance": {"source": "b", "confidence": 0.5, "field_sources": {}},
        }

        merged = KnowledgeAgent._merge_dicts(existing, new, "b")
        assert merged["_provenance"]["confidence"] == 0.9


# ---------------------------------------------------------------------------
# 4. Cache search by content
# ---------------------------------------------------------------------------

class TestCacheSearch:
    """Test improved cache search that looks inside JSON content."""

    def test_cache_search_by_mpn_content(self, tmp_path):
        from agents.knowledge_agent import KnowledgeAgent

        cache_dir = tmp_path / "knowledge"
        cache_dir.mkdir()

        # Save with a non-matching filename
        (cache_dir / "SENSIRION_SCD41.json").write_text(json.dumps({
            "mpn": "SCD41",
            "name": "SCD41 CO2 Sensor",
            "manufacturer": "Sensirion",
            "category": "sensor",
            "interface_types": ["I2C"],
            "electrical_ratings": {"vdd_min": 2.4, "vdd_max": 5.5},
            "known_i2c_addresses": ["0x62"],
            "unit_cost_usd": 12.50,
            "tags": ["co2"],
        }))

        agent = KnowledgeAgent(cache_dir=cache_dir)
        result = agent._query_cache("SCD41")

        assert result is not None
        assert result.mpn == "SCD41"
        assert result.source == "local_cache"

    def test_cache_search_filename_match(self, tmp_path):
        from agents.knowledge_agent import KnowledgeAgent

        cache_dir = tmp_path / "knowledge"
        cache_dir.mkdir()

        (cache_dir / "SCD41.json").write_text(json.dumps({
            "mpn": "SCD41",
            "name": "SCD41",
            "manufacturer": "Sensirion",
            "category": "sensor",
        }))

        agent = KnowledgeAgent(cache_dir=cache_dir)
        result = agent._query_cache("SCD41")
        assert result is not None
        assert result.mpn == "SCD41"

    def test_cache_search_no_match(self, tmp_path):
        from agents.knowledge_agent import KnowledgeAgent

        cache_dir = tmp_path / "knowledge"
        cache_dir.mkdir()

        (cache_dir / "BME280.json").write_text(json.dumps({"mpn": "BME280"}))

        agent = KnowledgeAgent(cache_dir=cache_dir)
        result = agent._query_cache("SCD41")
        assert result is None


# ---------------------------------------------------------------------------
# 5. Promote quality check / format helpers
# ---------------------------------------------------------------------------

class TestPromoteHelpers:
    """Test the _build_component_entry and _format_component_entry helpers."""

    def test_build_component_entry(self):
        sys.path.insert(0, str(_repo / "boardsmith_cli"))
        from main import _build_component_entry

        data = {
            "mpn": "SCD41",
            "manufacturer": "Sensirion",
            "name": "SCD41 CO2 Sensor",
            "category": "sensor",
            "interface_types": ["I2C"],
            "electrical_ratings": {"vdd_min": 2.4, "vdd_max": 5.5},
            "known_i2c_addresses": ["0x62"],
            "unit_cost_usd": 12.50,
            "tags": ["co2"],
        }

        entry = _build_component_entry(data)
        assert entry["mpn"] == "SCD41"
        assert entry["manufacturer"] == "Sensirion"
        assert entry["category"] == "sensor"
        assert entry["electrical_ratings"]["vdd_min"] == 2.4

    def test_format_component_entry(self):
        sys.path.insert(0, str(_repo / "boardsmith_cli"))
        from main import _format_component_entry

        entry = {
            "mpn": "SCD41",
            "manufacturer": "Sensirion",
            "name": "SCD41 CO2 Sensor",
            "category": "sensor",
            "interface_types": ["I2C"],
            "package": "DFN-10",
            "description": "CO2 sensor",
            "electrical_ratings": {"vdd_min": 2.4},
            "known_i2c_addresses": ["0x62"],
            "i2c_address_selectable": False,
            "init_contract_coverage": False,
            "init_contract_template": {},
            "unit_cost_usd": 12.50,
            "tags": ["co2"],
        }

        formatted = _format_component_entry(entry)
        assert '"mpn": "SCD41"' in formatted
        assert '"manufacturer": "Sensirion"' in formatted
        assert '"vdd_min": 2.4' in formatted
        assert formatted.startswith("    {")
        assert formatted.endswith("},")


# ---------------------------------------------------------------------------
# 6. No-LLM skips agent
# ---------------------------------------------------------------------------

class TestNoLLMMode:
    """Verify that without LLM, the agent tier is skipped."""

    def test_no_llm_agent_skipped(self, tmp_path):
        from agents.knowledge_agent import KnowledgeAgent

        agent = KnowledgeAgent(
            gateway=None,
            cache_dir=tmp_path / "knowledge",
        )

        # No gateway → agent tier is skipped, result should be None
        # for an unknown component
        result = asyncio.get_event_loop().run_until_complete(
            agent.find("UNKNOWN_XYZ_12345")
        )
        assert result is None


# ---------------------------------------------------------------------------
# 7. Dynamic modality lookup
# ---------------------------------------------------------------------------

class TestDynamicModalityLookup:
    """Test that _get_modality_sensors returns dynamic results from DB."""

    def test_static_modality_returns_static(self):
        from boardsmith_hw.component_selector import _get_modality_sensors

        result = _get_modality_sensors("temperature")
        assert "BME280" in result

    def test_unknown_modality_searches_tags(self):
        from boardsmith_hw.component_selector import _get_modality_sensors

        # This should search the DB by tags — result depends on DB contents
        result = _get_modality_sensors("co2")
        assert isinstance(result, list)

    def test_empty_modality_returns_empty(self):
        from boardsmith_hw.component_selector import _get_modality_sensors

        result = _get_modality_sensors("nonexistent_modality_xyz")
        assert result == []


# ---------------------------------------------------------------------------
# 8. Result-to-dict includes extended fields
# ---------------------------------------------------------------------------

class TestResultToDict:
    """Test that _result_to_dict includes provenance and extended fields."""

    def test_result_to_dict_has_provenance(self):
        from agents.knowledge_agent import AgentComponentResult, KnowledgeAgent

        result = AgentComponentResult(
            mpn="TEST",
            name="Test Component",
            manufacturer="TestCo",
            category="sensor",
            interface_types=["I2C"],
            electrical_ratings={"vdd_min": 3.0},
            known_i2c_addresses=[],
            unit_cost_usd=1.0,
            tags=["test"],
            confidence=0.75,
            source="agent_extracted",
            raw={"package": "QFN-16", "description": "A test component"},
            agent_trace=["Step 1: search_octopart"],
        )

        d = KnowledgeAgent._result_to_dict(result)

        assert d["package"] == "QFN-16"
        assert d["description"] == "A test component"
        assert "_provenance" in d
        assert d["_provenance"]["source"] == "agent_extracted"
        assert d["_provenance"]["confidence"] == 0.75
        assert "discovered_at" in d["_provenance"]
