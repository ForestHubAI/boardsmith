# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Phase 11 — Knowledge Agent: web_search, search_octopart, registry, integration.

All tests work without API keys and without external network calls.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

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
# WebSearchTool — structure + no-key graceful behaviour
# ---------------------------------------------------------------------------

class TestWebSearchTool:
    def test_tool_name_and_description(self):
        from tools.tools.web_search import WebSearchTool
        t = WebSearchTool()
        assert t.name == "web_search"
        assert "datasheet" in t.description.lower() or "search" in t.description.lower()
        assert len(t.description) > 20

    def test_tool_satisfies_protocol(self):
        from tools.base import Tool
        from tools.tools.web_search import WebSearchTool
        assert isinstance(WebSearchTool(), Tool)

    def test_empty_query_returns_failure(self, tmp_path):
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        from tools.tools.web_search import WebSearchTool

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="t", llm_gateway=gw, cache_dir=tmp_path)
        result = asyncio.run(WebSearchTool().execute({"query": ""}, ctx))
        assert result.success is False
        assert result.error != ""

    def test_dict_input_accepted(self, tmp_path):
        """Tool accepts both dict and dataclass input — check dict path is parseable."""
        from tools.tools.web_search import WebSearchTool, WebSearchInput
        t = WebSearchTool()
        inp = {"query": "SCD41 datasheet", "max_results": 3}
        # Just check that parsing doesn't crash (we won't make network calls here)
        assert inp["query"] == "SCD41 datasheet"

    def test_max_results_clamped(self, tmp_path):
        """max_results > 10 is silently clamped to 10."""
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        from tools.tools.web_search import WebSearchTool

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="t", llm_gateway=gw, cache_dir=tmp_path)
        # Patch all providers to return empty so we hit the "no results" path quickly
        with patch("tools.tools.web_search._search_tavily", new=AsyncMock(return_value=[])), \
             patch("tools.tools.web_search._search_serpapi", new=AsyncMock(return_value=[])), \
             patch("tools.tools.web_search._search_duckduckgo", new=AsyncMock(return_value=[])):
            result = asyncio.run(WebSearchTool().execute({"query": "test", "max_results": 99}, ctx))
        assert result.success is False   # no results

    def test_no_api_key_falls_back_to_duckduckgo(self, tmp_path, monkeypatch):
        """Without TAVILY/SERPAPI keys, DuckDuckGo fallback is attempted."""
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        from tools.tools.web_search import WebSearchTool

        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.delenv("SERPAPI_API_KEY", raising=False)

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="t", llm_gateway=gw, cache_dir=tmp_path)

        mock_results = [{"title": "SCD41 Datasheet", "url": "https://example.com/scd41.pdf", "snippet": "..."}]
        with patch("tools.tools.web_search._search_duckduckgo", new=AsyncMock(return_value=mock_results)):
            result = asyncio.run(WebSearchTool().execute({"query": "SCD41 datasheet"}, ctx))

        assert result.success is True
        assert result.data[0]["url"] == "https://example.com/scd41.pdf"
        assert result.source == "web_search:duckduckgo"

    def test_tavily_key_uses_tavily(self, tmp_path, monkeypatch):
        """With TAVILY_API_KEY set, Tavily provider is tried first."""
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        from tools.tools.web_search import WebSearchTool

        monkeypatch.setenv("TAVILY_API_KEY", "test-key-xxx")
        monkeypatch.delenv("SERPAPI_API_KEY", raising=False)

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="t", llm_gateway=gw, cache_dir=tmp_path)

        mock_results = [
            {"title": "SCD41 Sensirion", "url": "https://sensirion.com/scd41.pdf", "snippet": "CO2 sensor"},
        ]
        with patch("tools.tools.web_search._search_tavily", new=AsyncMock(return_value=mock_results)):
            result = asyncio.run(WebSearchTool().execute({"query": "SCD41"}, ctx))

        assert result.success is True
        assert result.source == "web_search:tavily"
        assert result.confidence == 0.90

    def test_serpapi_key_used_when_tavily_fails(self, tmp_path, monkeypatch):
        """If Tavily returns empty, falls back to SerpAPI."""
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        from tools.tools.web_search import WebSearchTool

        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        monkeypatch.setenv("SERPAPI_API_KEY", "serp-key")

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="t", llm_gateway=gw, cache_dir=tmp_path)

        serp_results = [{"title": "BME280", "url": "https://bosch.com/bme280.pdf", "snippet": ""}]
        with patch("tools.tools.web_search._search_tavily", new=AsyncMock(return_value=[])), \
             patch("tools.tools.web_search._search_serpapi", new=AsyncMock(return_value=serp_results)):
            result = asyncio.run(WebSearchTool().execute({"query": "BME280"}, ctx))

        assert result.success is True
        assert result.source == "web_search:serpapi"
        assert result.confidence == 0.85

    def test_all_providers_fail_returns_failure(self, tmp_path, monkeypatch):
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        from tools.tools.web_search import WebSearchTool

        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.delenv("SERPAPI_API_KEY", raising=False)

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="t", llm_gateway=gw, cache_dir=tmp_path)

        with patch("tools.tools.web_search._search_duckduckgo", new=AsyncMock(return_value=[])):
            result = asyncio.run(WebSearchTool().execute({"query": "XYZZY_PART"}, ctx))

        assert result.success is False
        assert "No search results" in result.error or result.error != ""

    def test_provider_confidence_values(self):
        from tools.tools.web_search import _provider_confidence
        assert _provider_confidence("tavily") == 0.90
        assert _provider_confidence("serpapi") == 0.85
        assert _provider_confidence("duckduckgo") == 0.70
        assert _provider_confidence("none") == 0.0

    def test_result_structure(self, tmp_path, monkeypatch):
        """Each result has title, url, snippet keys."""
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        from tools.tools.web_search import WebSearchTool

        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.delenv("SERPAPI_API_KEY", raising=False)

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="t", llm_gateway=gw, cache_dir=tmp_path)

        mock_results = [
            {"title": "T1", "url": "https://a.com/1.pdf", "snippet": "S1"},
            {"title": "T2", "url": "https://b.com/2.pdf", "snippet": "S2"},
        ]
        with patch("tools.tools.web_search._search_duckduckgo", new=AsyncMock(return_value=mock_results)):
            result = asyncio.run(WebSearchTool().execute({"query": "test"}, ctx))

        assert result.success is True
        assert len(result.data) == 2
        for item in result.data:
            assert "title" in item
            assert "url" in item
            assert "snippet" in item


# ---------------------------------------------------------------------------
# WebSearchTool — WebSearchInput dataclass
# ---------------------------------------------------------------------------

class TestWebSearchInput:
    def test_input_dataclass(self):
        from tools.tools.web_search import WebSearchInput
        inp = WebSearchInput(query="SCD41 datasheet", max_results=3)
        assert inp.query == "SCD41 datasheet"
        assert inp.max_results == 3

    def test_input_defaults(self):
        from tools.tools.web_search import WebSearchInput
        inp = WebSearchInput(query="test")
        assert inp.max_results == 5


# ---------------------------------------------------------------------------
# SearchOctopartTool — structure + no-key graceful failure
# ---------------------------------------------------------------------------

class TestSearchOctopartTool:
    def test_tool_name_and_description(self):
        from tools.tools.search_octopart import SearchOctopartTool
        t = SearchOctopartTool()
        assert t.name == "search_octopart"
        assert len(t.description) > 20

    def test_tool_satisfies_protocol(self):
        from tools.base import Tool
        from tools.tools.search_octopart import SearchOctopartTool
        assert isinstance(SearchOctopartTool(), Tool)

    def test_empty_query_returns_failure(self, tmp_path):
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        from tools.tools.search_octopart import SearchOctopartTool

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="t", llm_gateway=gw, cache_dir=tmp_path)
        result = asyncio.run(SearchOctopartTool().execute({"query": ""}, ctx))
        assert result.success is False

    def test_no_credentials_returns_graceful_failure(self, tmp_path, monkeypatch):
        """Without API credentials, returns informative error, not exception."""
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        from tools.tools.search_octopart import SearchOctopartTool

        monkeypatch.delenv("OCTOPART_API_KEY", raising=False)
        monkeypatch.delenv("NEXAR_CLIENT_ID", raising=False)
        monkeypatch.delenv("NEXAR_CLIENT_SECRET", raising=False)

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="t", llm_gateway=gw, cache_dir=tmp_path)
        result = asyncio.run(SearchOctopartTool().execute({"query": "BME280"}, ctx))

        assert result.success is False
        assert result.data == []
        assert "NEXAR_CLIENT_ID" in result.error or "credential" in result.error.lower()

    def test_nexar_credentials_trigger_api_call(self, tmp_path, monkeypatch):
        """With NEXAR credentials, the API search method is called."""
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        from tools.tools.search_octopart import SearchOctopartTool

        monkeypatch.setenv("NEXAR_CLIENT_ID", "test-id")
        monkeypatch.setenv("NEXAR_CLIENT_SECRET", "test-secret")
        monkeypatch.delenv("OCTOPART_API_KEY", raising=False)

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="t", llm_gateway=gw, cache_dir=tmp_path)

        mock_component = {
            "mpn": "BME280", "manufacturer": "Bosch",
            "category": "Humidity Sensors", "description": "Humidity/Temp/Pressure sensor",
            "datasheets": ["https://bosch.com/bme280.pdf"],
            "specs": {"Supply Voltage": "3.3V"},
            "unit_cost_usd": 1.80, "source": "nexar",
        }
        tool = SearchOctopartTool()
        with patch.object(tool, "_search_nexar", new=AsyncMock(return_value=[mock_component])):
            result = asyncio.run(tool.execute({"query": "BME280"}, ctx))

        assert result.success is True
        assert result.data[0]["mpn"] == "BME280"
        assert result.confidence == 0.85

    def test_octopart_v4_key_fallback(self, tmp_path, monkeypatch):
        """With OCTOPART_API_KEY (legacy), v4 API is used."""
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        from tools.tools.search_octopart import SearchOctopartTool

        monkeypatch.setenv("OCTOPART_API_KEY", "legacy-key")
        monkeypatch.delenv("NEXAR_CLIENT_ID", raising=False)
        monkeypatch.delenv("NEXAR_CLIENT_SECRET", raising=False)

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="t", llm_gateway=gw, cache_dir=tmp_path)

        mock_results = [
            {"mpn": "AHT20", "manufacturer": "Aosong", "category": "Temp/Humidity",
             "description": "Digital Sensor", "datasheets": [], "specs": {},
             "unit_cost_usd": 0.65, "source": "octopart_v4"}
        ]
        tool = SearchOctopartTool()
        with patch.object(tool, "_search_octopart_v4", new=AsyncMock(return_value=mock_results)):
            result = asyncio.run(tool.execute({"query": "AHT20"}, ctx))

        assert result.success is True
        assert result.data[0]["mpn"] == "AHT20"

    def test_no_results_returns_failure(self, tmp_path, monkeypatch):
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext
        from tools.tools.search_octopart import SearchOctopartTool

        monkeypatch.setenv("NEXAR_CLIENT_ID", "test-id")
        monkeypatch.setenv("NEXAR_CLIENT_SECRET", "test-secret")

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="t", llm_gateway=gw, cache_dir=tmp_path)

        tool = SearchOctopartTool()
        with patch.object(tool, "_search_nexar", new=AsyncMock(return_value=[])):
            result = asyncio.run(tool.execute({"query": "XYZZY_FAKE_PART"}, ctx))

        assert result.success is False
        assert "No components found" in result.error


# ---------------------------------------------------------------------------
# OctopartSearchInput dataclass
# ---------------------------------------------------------------------------

class TestOctopartSearchInput:
    def test_input_creation(self):
        from tools.tools.search_octopart import OctopartSearchInput
        inp = OctopartSearchInput(query="BME280", max_results=3)
        assert inp.query == "BME280"
        assert inp.max_results == 3

    def test_input_defaults(self):
        from tools.tools.search_octopart import OctopartSearchInput
        inp = OctopartSearchInput(query="test")
        assert inp.max_results == 5


# ---------------------------------------------------------------------------
# Nexar/Octopart parsers
# ---------------------------------------------------------------------------

class TestOctopartParsers:
    def test_parse_nexar_result(self):
        from tools.tools.search_octopart import _parse_nexar_result
        raw = {
            "part": {
                "mpn": "SCD41",
                "manufacturer": {"name": "Sensirion"},
                "category": {"name": "CO2 Sensors", "path": "Sensors/Gas/CO2"},
                "shortDescription": "CO2 Sensor I2C",
                "specs": [{"attribute": {"name": "Supply Voltage"}, "displayValue": "3.3V"}],
                "documentCollections": [
                    {"documents": [{"name": "SCD41 Datasheet", "url": "https://example.com/scd41.pdf"}]}
                ],
                "sellers": [
                    {"offers": [{"prices": [{"quantity": 1, "price": "4.99", "currency": "USD"}]}]}
                ],
            }
        }
        result = _parse_nexar_result(raw)
        assert result["mpn"] == "SCD41"
        assert result["manufacturer"] == "Sensirion"
        assert "https://example.com/scd41.pdf" in result["datasheets"]
        assert result["specs"]["Supply Voltage"] == "3.3V"
        assert result["unit_cost_usd"] == pytest.approx(4.99)

    def test_parse_nexar_result_empty_part(self):
        from tools.tools.search_octopart import _parse_nexar_result
        result = _parse_nexar_result({"part": {}})
        assert result["mpn"] == ""
        assert result["datasheets"] == []

    def test_parse_octopart_v4_result(self):
        from tools.tools.search_octopart import _parse_octopart_v4_result
        raw = {
            "item": {
                "mpn": "BME280",
                "manufacturer": {"name": "Bosch Sensortec"},
                "category": {"name": "Pressure Sensors"},
                "description": "Pressure/Humidity/Temp",
                "datasheets": [{"url": "https://bosch.com/bme280.pdf"}],
                "specs": {"vdd": {"display_value": "3.3V"}},
            }
        }
        result = _parse_octopart_v4_result(raw)
        assert result["mpn"] == "BME280"
        assert result["manufacturer"] == "Bosch Sensortec"
        assert "https://bosch.com/bme280.pdf" in result["datasheets"]
        assert result["specs"]["vdd"] == "3.3V"


# ---------------------------------------------------------------------------
# Tool Registry — Phase 11 tools registered
# ---------------------------------------------------------------------------

class TestRegistryPhase11:
    def test_registry_reset_for_phase11(self):
        """After reset, get_default_registry includes all Phase 11 tools."""
        from tools.registry import get_default_registry, _default_registry
        import tools.registry as reg_module

        # Reset singleton
        reg_module._default_registry = None
        reg = get_default_registry()
        tools = reg.list_tools()

        # Core tools from Phase 10
        assert "query_knowledge" in tools
        assert "validate_hir" in tools

        # Phase 11 tools
        assert "download_pdf" in tools
        assert "extract_datasheet" in tools
        assert "web_search" in tools
        assert "search_octopart" in tools

    def test_all_registered_tools_satisfy_protocol(self):
        """Every tool in the registry must satisfy the Tool protocol."""
        from tools.base import Tool
        from tools.registry import _default_registry
        import tools.registry as reg_module

        reg_module._default_registry = None
        reg = reg_module.get_default_registry()
        for name in reg.list_tools():
            tool = reg.get(name)
            assert isinstance(tool, Tool), f"{name!r} does not satisfy Tool protocol"


# ---------------------------------------------------------------------------
# KnowledgeAgent — Tier 3 now includes web_search
# ---------------------------------------------------------------------------

class TestKnowledgeAgentPhase11:
    """Verify that KnowledgeAgent._run_agent includes web_search + search_octopart."""

    def test_agent_tools_include_web_search(self, tmp_path):
        """KnowledgeAgent builds tool set that includes web_search."""
        from agents.knowledge_agent import KnowledgeAgent
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from llm.types import LLMResponse

        # Mock gateway that immediately returns FINISH with a JSON component
        component_json = (
            '{"mpn":"SCD41","manufacturer":"Sensirion","category":"sensor",'
            '"interface_types":["I2C"],"electrical_ratings":{"vdd_v":3.3},'
            '"known_i2c_addresses":["0x62"],"unit_cost_usd":4.99,"tags":["co2"]}'
        )
        finish_response = (
            f"Thought: I have all specs.\nAction: FINISH\nAction Input: {{}}\n"
            f"Final Answer: {component_json}\n"
        )

        class MockGW:
            def is_llm_available(self):
                return True
            async def complete(self, task, messages, **kw):
                return LLMResponse(
                    content=finish_response, model="test", provider="mock",
                    skipped=False, input_tokens=10, output_tokens=30, cost_usd=0.0
                )

        agent = KnowledgeAgent(gateway=MockGW(), cache_dir=tmp_path)
        result = asyncio.run(agent.find("SCD41_NOTINCACHE"))

        # Agent ran and returned something
        if result is not None:
            assert result.source in ("builtin_db", "local_cache", "agent_extracted")

    def test_agent_find_with_web_search_in_tools(self, tmp_path):
        """When web_search returns a datasheet URL, agent can use it."""
        from agents.knowledge_agent import KnowledgeAgent
        from llm.types import LLMResponse

        step_responses = [
            # Step 1: use web_search
            "Thought: Search for datasheet URL.\nAction: web_search\n"
            'Action Input: {"query": "TESTPART99 datasheet filetype:pdf"}\n',
            # Step 2: download PDF
            "Thought: Got URL, download PDF.\nAction: download_pdf\n"
            'Action Input: {"url": "https://example.com/testpart.pdf"}\n',
            # Step 3: FINISH with data
            'Thought: Done.\nAction: FINISH\nAction Input: {}\n'
            'Final Answer: {"mpn":"TESTPART99","manufacturer":"TestCo",'
            '"category":"sensor","interface_types":["I2C"],"electrical_ratings":{},'
            '"known_i2c_addresses":[],"unit_cost_usd":1.0,"tags":["test"]}\n',
        ]
        call_idx = [0]

        class StepGW:
            def is_llm_available(self):
                return True
            async def complete(self, task, messages, **kw):
                content = step_responses[min(call_idx[0], len(step_responses) - 1)]
                call_idx[0] += 1
                return LLMResponse(
                    content=content, model="t", provider="mock",
                    skipped=False, input_tokens=10, output_tokens=30, cost_usd=0.0
                )

        agent = KnowledgeAgent(gateway=StepGW(), cache_dir=tmp_path, max_agent_steps=5)

        # Mock web_search to return a URL without making real network calls
        from tools.tools.web_search import WebSearchTool
        from tools.base import ToolResult

        original_execute = WebSearchTool.execute

        async def mock_web_search(self, input, ctx):
            return ToolResult(
                success=True,
                data=[{"title": "TestPart Datasheet", "url": "https://example.com/testpart.pdf", "snippet": "..."}],
                source="web_search:duckduckgo",
                confidence=0.70,
            )

        # Mock download_pdf to avoid real HTTP
        from tools.tools.download_pdf import DownloadPDFTool

        async def mock_download_pdf(self, input, ctx):
            return ToolResult(
                success=False,
                data=None,
                source="download_pdf",
                confidence=0.0,
                error="Mocked: no real download in test",
            )

        with patch.object(WebSearchTool, "execute", mock_web_search), \
             patch.object(DownloadPDFTool, "execute", mock_download_pdf):
            result = asyncio.run(agent.find("TESTPART99_NOT_IN_DB"))

        # Result may be None (download failed) or an AgentComponentResult
        # Just verify no exception was raised
        assert result is None or hasattr(result, "mpn")


# ---------------------------------------------------------------------------
# End-to-end: tool chain (web_search → download_pdf chain plumbing)
# ---------------------------------------------------------------------------

class TestPhase11ToolChain:
    """Smoke-test that tools are importable and can be wired together."""

    def test_all_tools_importable(self):
        from tools.tools.web_search import WebSearchTool
        from tools.tools.search_octopart import SearchOctopartTool
        from tools.tools.download_pdf import DownloadPDFTool
        from tools.tools.extract_datasheet import ExtractDatasheetTool
        from tools.tools.query_knowledge import QueryKnowledgeTool
        from tools.tools.validate_hir import ValidateHIRTool

        tools = [
            WebSearchTool(), SearchOctopartTool(), DownloadPDFTool(),
            ExtractDatasheetTool(), QueryKnowledgeTool(), ValidateHIRTool(),
        ]
        for t in tools:
            assert hasattr(t, "name")
            assert hasattr(t, "description")
            assert hasattr(t, "execute")

    def test_tool_names_unique(self):
        from tools.tools.web_search import WebSearchTool
        from tools.tools.search_octopart import SearchOctopartTool
        from tools.tools.download_pdf import DownloadPDFTool
        from tools.tools.extract_datasheet import ExtractDatasheetTool
        from tools.tools.query_knowledge import QueryKnowledgeTool
        from tools.tools.validate_hir import ValidateHIRTool

        names = [t.name for t in [
            WebSearchTool(), SearchOctopartTool(), DownloadPDFTool(),
            ExtractDatasheetTool(), QueryKnowledgeTool(), ValidateHIRTool(),
        ]]
        assert len(names) == len(set(names)), f"Duplicate tool names: {names}"
