# SPDX-License-Identifier: AGPL-3.0-or-later
"""--no-llm deterministic fallback test suite.

Verifies that the entire Boardsmith synthesis pipeline produces valid output
without any LLM API calls. Every pipeline stage (B1–B9) must work in
regex/deterministic mode with graceful degradation.

Run:
    PYTHONPATH=synthesizer:shared:compiler pytest synthesizer/tests/test_no_llm.py -v
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

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
    """Run an async coroutine in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# LLM Gateway — no-llm mode
# ---------------------------------------------------------------------------

class TestLLMGatewayNoLLM:

    def test_no_llm_config(self):
        from llm.config import LLMConfig
        cfg = LLMConfig.no_llm_mode()
        assert cfg.no_llm is True

    def test_gateway_returns_skipped(self):
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from llm.types import Message, TaskType

        gw = LLMGateway(LLMConfig.no_llm_mode())
        resp = gw.complete_sync(
            task=TaskType.INTENT_PARSE,
            messages=[Message(role="user", content="test")],
        )
        assert resp.skipped is True
        assert resp.content == ""

    def test_gateway_not_available_in_no_llm(self):
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway

        gw = LLMGateway(LLMConfig.no_llm_mode())
        assert gw.is_llm_available() is False

    def test_cost_tracker_zero(self):
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway

        gw = LLMGateway(LLMConfig.no_llm_mode())
        summary = gw.get_cost_summary()
        assert summary.total_usd == 0.0
        assert summary.total_tokens == 0


# ---------------------------------------------------------------------------
# Config — TOML loading
# ---------------------------------------------------------------------------

class TestConfigTOML:

    def test_from_env_without_toml(self, monkeypatch):
        """Config works fine when no llm.toml exists."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("BOARDSMITH_NO_LLM", raising=False)

        from llm.config import LLMConfig
        # Use a non-existent path
        cfg = LLMConfig.from_env(toml_path=Path("/tmp/nonexistent/llm.toml"))
        assert cfg.anthropic_api_key == ""
        assert cfg.no_llm is False

    def test_from_toml_file(self, tmp_path):
        """Config reads from a llm.toml file."""
        toml_file = tmp_path / "llm.toml"
        toml_file.write_text(
            '[providers]\nanthropic_api_key = "test-key-123"\n\n'
            '[behavior]\nbudget_limit_usd = 10.0\n\n'
            '[models]\nintent_parse = "claude-haiku-4-5-20251001"\n\n'
            '[search]\ntavily_api_key = "tvly-test"\n'
        )

        from llm.config import LLMConfig
        import os
        # Ensure env vars don't interfere
        old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            cfg = LLMConfig.from_env(toml_path=toml_file)
            assert cfg.anthropic_api_key == "test-key-123"
            assert cfg.budget_limit_usd == 10.0
            assert cfg.default_models.get("intent_parse") == "claude-haiku-4-5-20251001"
            assert cfg.tavily_api_key == "tvly-test"
        finally:
            if old_key:
                os.environ["ANTHROPIC_API_KEY"] = old_key

    def test_env_overrides_toml(self, tmp_path, monkeypatch):
        """Environment variables override TOML values."""
        toml_file = tmp_path / "llm.toml"
        toml_file.write_text('[providers]\nanthropic_api_key = "toml-key"\n')

        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")

        from llm.config import LLMConfig
        cfg = LLMConfig.from_env(toml_path=toml_file)
        assert cfg.anthropic_api_key == "env-key"

    def test_malformed_toml_is_ignored(self, tmp_path):
        """A broken toml file doesn't crash — falls back to defaults."""
        toml_file = tmp_path / "llm.toml"
        toml_file.write_text("this is not valid TOML {{{{")

        from llm.config import LLMConfig
        import os
        old = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            cfg = LLMConfig.from_env(toml_path=toml_file)
            assert cfg.anthropic_api_key == ""
        finally:
            if old:
                os.environ["ANTHROPIC_API_KEY"] = old


# ---------------------------------------------------------------------------
# Tool System — no-llm mode
# ---------------------------------------------------------------------------

class TestToolRegistryNoLLM:

    def test_registry_has_at_least_7_tools(self):
        from tools.registry import ToolRegistry, _register_builtin_tools

        # Use a fresh registry to avoid import-order issues
        reg = ToolRegistry()
        _register_builtin_tools(reg)
        tools = reg.list_tools()
        # >= 7 because EDA tools (run_erc, read_schematic, search_component) are also registered
        # when synthesizer/ is in PYTHONPATH; they silently skip when not available
        assert len(tools) >= 7, f"Expected >= 7 tools, got {len(tools)}: {tools}"
        expected_core = {
            "query_knowledge", "validate_hir", "download_pdf",
            "extract_datasheet", "web_search", "search_octopart",
            "compile_code",
        }
        assert expected_core.issubset(set(tools)), f"Core tools missing: {expected_core - set(tools)}"

    def test_query_knowledge_works_without_llm(self):
        from tools.tools.query_knowledge import QueryKnowledgeTool, QueryKnowledgeInput

        tool = QueryKnowledgeTool()
        result = _run_async(tool.execute(
            QueryKnowledgeInput(query="BME280"),
            _make_no_llm_context(),
        ))
        assert result.success is True
        assert result.source == "builtin_db"
        assert result.confidence == 0.95
        assert len(result.data) >= 1

    def test_web_search_without_api_key(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        from tools.tools.web_search import WebSearchTool

        tool = WebSearchTool()
        result = _run_async(tool.execute(
            {"query": "BME280 datasheet"},
            _make_no_llm_context(),
        ))
        assert result.success is False
        assert "not configured" in result.error.lower() or "api" in result.error.lower()

    def test_search_octopart_without_api_key(self, monkeypatch):
        monkeypatch.delenv("NEXAR_CLIENT_ID", raising=False)
        monkeypatch.delenv("NEXAR_CLIENT_SECRET", raising=False)

        from tools.tools.search_octopart import SearchOctopartTool

        tool = SearchOctopartTool()
        result = _run_async(tool.execute(
            {"query": "BME280"},
            _make_no_llm_context(),
        ))
        assert result.success is False
        assert "not configured" in result.error.lower() or "nexar" in result.error.lower()

    def test_compile_code_without_source(self):
        from tools.tools.compile_code import CompileCodeTool

        tool = CompileCodeTool()
        result = _run_async(tool.execute(
            {"source_dir": "/tmp/nonexistent_dir_xyz"},
            _make_no_llm_context(),
        ))
        assert result.success is False

    def test_compile_code_no_build_system(self, tmp_path):
        from tools.tools.compile_code import CompileCodeTool

        # Empty directory — no build system
        tool = CompileCodeTool()
        result = _run_async(tool.execute(
            {"source_dir": str(tmp_path)},
            _make_no_llm_context(),
        ))
        assert result.success is False
        assert "no build system" in result.error.lower()

    def test_extract_datasheet_no_llm(self):
        from tools.tools.extract_datasheet import ExtractDatasheetTool

        tool = ExtractDatasheetTool()
        ctx = _make_no_llm_context()
        result = _run_async(tool.execute(
            {"pdf_path": "/tmp/fake.pdf"},
            ctx,
        ))
        # Either "PDF not found" or "LLM disabled" — both are acceptable
        assert result.success is False

    def test_web_search_empty_query(self):
        from tools.tools.web_search import WebSearchTool

        tool = WebSearchTool()
        result = _run_async(tool.execute(
            {"query": ""},
            _make_no_llm_context(),
        ))
        assert result.success is False
        assert "no query" in result.error.lower()

    def test_search_octopart_empty_query(self):
        from tools.tools.search_octopart import SearchOctopartTool

        tool = SearchOctopartTool()
        result = _run_async(tool.execute(
            {"query": ""},
            _make_no_llm_context(),
        ))
        assert result.success is False


# ---------------------------------------------------------------------------
# Pipeline Stages — no-llm mode
# ---------------------------------------------------------------------------

class TestPipelineNoLLM:
    """Each pipeline stage produces valid output without LLM."""

    PROMPT = "ESP32 with BME280 temperature sensor over I2C"

    def test_b1_intent_parser(self):
        from boardsmith_hw.intent_parser import IntentParser

        parser = IntentParser(use_llm=False)
        spec = parser.parse(self.PROMPT)
        assert spec is not None
        # RequirementsSpec has mcu_family (not mcu) and sensing_modalities
        assert spec.mcu_family is not None or len(spec.sensor_mpns) > 0
        assert len(spec.sensing_modalities) > 0 or len(spec.sensor_mpns) > 0

    def test_b2_requirements_normalizer(self):
        from boardsmith_hw.intent_parser import IntentParser
        from boardsmith_hw.requirements_normalizer import normalize

        parser = IntentParser(use_llm=False)
        spec = parser.parse(self.PROMPT)
        reqs = normalize(spec)
        assert reqs is not None
        assert reqs.confidence > 0

    def test_b3_component_selector(self):
        from boardsmith_hw.intent_parser import IntentParser
        from boardsmith_hw.requirements_normalizer import normalize
        from boardsmith_hw.component_selector import ComponentSelector

        parser = IntentParser(use_llm=False)
        spec = parser.parse(self.PROMPT)
        reqs = normalize(spec)
        selector = ComponentSelector(seed=42, use_agent=False)
        selection = selector.select(reqs)
        assert selection.mcu is not None
        assert len(selection.sensors) > 0

    def test_b4_topology_synthesizer(self):
        from boardsmith_hw.intent_parser import IntentParser
        from boardsmith_hw.requirements_normalizer import normalize
        from boardsmith_hw.component_selector import ComponentSelector
        from boardsmith_hw.topology_synthesizer import synthesize_topology

        parser = IntentParser(use_llm=False)
        spec = parser.parse(self.PROMPT)
        reqs = normalize(spec)
        selector = ComponentSelector(seed=42, use_agent=False)
        selection = selector.select(reqs)
        topology = synthesize_topology(selection, use_llm=False)
        assert topology is not None
        assert len(topology.components) > 0

    def test_b5_hir_composer(self):
        from boardsmith_hw.intent_parser import IntentParser
        from boardsmith_hw.requirements_normalizer import normalize
        from boardsmith_hw.component_selector import ComponentSelector
        from boardsmith_hw.topology_synthesizer import synthesize_topology
        from boardsmith_hw.hir_composer import compose_hir

        parser = IntentParser(use_llm=False)
        spec = parser.parse(self.PROMPT)
        reqs = normalize(spec)
        selector = ComponentSelector(seed=42, use_agent=False)
        selection = selector.select(reqs)
        topology = synthesize_topology(selection, use_llm=False)
        hir = compose_hir(topology, track="B", source="test")
        # compose_hir returns a Pydantic HIR object
        assert hasattr(hir, "components")
        assert len(hir.components) > 0

    def test_b6_constraint_refiner(self):
        from boardsmith_hw.intent_parser import IntentParser
        from boardsmith_hw.requirements_normalizer import normalize
        from boardsmith_hw.component_selector import ComponentSelector
        from boardsmith_hw.topology_synthesizer import synthesize_topology
        from boardsmith_hw.hir_composer import compose_hir
        from boardsmith_hw.constraint_refiner import ConstraintRefiner

        parser = IntentParser(use_llm=False)
        spec = parser.parse(self.PROMPT)
        reqs = normalize(spec)
        selector = ComponentSelector(seed=42, use_agent=False)
        selection = selector.select(reqs)
        topology = synthesize_topology(selection, use_llm=False)
        hir = compose_hir(topology, track="B", source="test")
        refiner = ConstraintRefiner(max_iterations=3, use_llm=False)
        refinement = refiner.refine(hir)
        assert refinement.hir is not None
        assert refinement.report is not None

    def test_b7_bom_builder(self):
        from boardsmith_hw.intent_parser import IntentParser
        from boardsmith_hw.requirements_normalizer import normalize
        from boardsmith_hw.component_selector import ComponentSelector
        from boardsmith_hw.topology_synthesizer import synthesize_topology
        from boardsmith_hw.hir_composer import compose_hir
        from boardsmith_hw.constraint_refiner import ConstraintRefiner
        from boardsmith_hw.bom_builder import build_bom, bom_summary

        parser = IntentParser(use_llm=False)
        spec = parser.parse(self.PROMPT)
        reqs = normalize(spec)
        selector = ComponentSelector(seed=42, use_agent=False)
        selection = selector.select(reqs)
        topology = synthesize_topology(selection, use_llm=False)
        hir = compose_hir(topology, track="B", source="test")
        # ConstraintRefiner converts HIR to dict
        refiner = ConstraintRefiner(max_iterations=3, use_llm=False)
        refinement = refiner.refine(hir)
        hir_dict = refinement.hir
        bom = build_bom(hir_dict)
        assert len(bom) > 0
        summary = bom_summary(bom)
        assert summary["line_count"] > 0

    def test_b8_kicad_exporter(self, tmp_path):
        from boardsmith_hw.intent_parser import IntentParser
        from boardsmith_hw.requirements_normalizer import normalize
        from boardsmith_hw.component_selector import ComponentSelector
        from boardsmith_hw.topology_synthesizer import synthesize_topology
        from boardsmith_hw.hir_composer import compose_hir
        from boardsmith_hw.constraint_refiner import ConstraintRefiner
        from boardsmith_hw.kicad_exporter import export_kicad_sch

        parser = IntentParser(use_llm=False)
        spec = parser.parse(self.PROMPT)
        reqs = normalize(spec)
        selector = ComponentSelector(seed=42, use_agent=False)
        selection = selector.select(reqs)
        topology = synthesize_topology(selection, use_llm=False)
        hir = compose_hir(topology, track="B", source="test")
        # ConstraintRefiner converts HIR to dict (needed by export_kicad_sch)
        refiner = ConstraintRefiner(max_iterations=3, use_llm=False)
        refinement = refiner.refine(hir)
        hir_dict = refinement.hir

        sch_path = tmp_path / "test.kicad_sch"
        export_kicad_sch(hir_dict, sch_path, use_llm=False)
        assert sch_path.exists()
        content = sch_path.read_text()
        assert "(kicad_sch" in content

    def test_b9_confidence_engine(self):
        from boardsmith_hw.confidence_engine import ConfidenceEngine

        engine = ConfidenceEngine()
        result = engine.compute(
            intent_confidence=0.8,
            component_confidence=0.9,
            topology_confidence=0.85,
            validation_report=MagicMock(
                valid=True,
                summary={"errors": 0, "warnings": 0},
                diagnostics=[],
            ),
            assumptions=["assumed 3.3V supply"],
            hir_dict={"components": [{"name": "test"}], "bus_contracts": []},
            llm_boosted_stages=[],
        )
        assert result.overall > 0.0
        assert result.overall <= 1.0


# ---------------------------------------------------------------------------
# Full Pipeline — no-llm integration
# ---------------------------------------------------------------------------

class TestFullPipelineNoLLM:

    def test_full_synthesizer_no_llm(self, tmp_path):
        """The complete Synthesizer pipeline runs without LLM."""
        from boardsmith_hw.synthesizer import Synthesizer

        synth = Synthesizer(
            out_dir=tmp_path,
            target="esp32",
            seed=42,
            use_llm=False,
            confidence_threshold=0.1,
        )
        result = synth.run(
            "ESP32 with BME280 temperature sensor over I2C",
            generate_firmware=False,
        )

        assert result.success is True or result.error is None, (
            f"Pipeline failed: {result.error}"
        )
        assert result.confidence > 0.0
        assert "hir.json" in result.artifacts
        assert "bom.json" in result.artifacts
        assert "schematic.kicad_sch" in result.artifacts

        # Verify artifacts exist
        assert (tmp_path / "hir.json").exists()
        assert (tmp_path / "bom.json").exists()
        assert (tmp_path / "schematic.kicad_sch").exists()

    def test_hir_json_is_valid(self, tmp_path):
        """Generated HIR JSON is parseable and has required fields."""
        from boardsmith_hw.synthesizer import Synthesizer

        synth = Synthesizer(
            out_dir=tmp_path, target="esp32", seed=42,
            use_llm=False, confidence_threshold=0.1,
        )
        synth.run("ESP32 with BME280 over I2C", generate_firmware=False)

        hir = json.loads((tmp_path / "hir.json").read_text())
        assert "components" in hir
        assert "bus_contracts" in hir
        assert "metadata" in hir

    def test_bom_json_is_valid(self, tmp_path):
        """Generated BOM JSON is parseable and non-empty."""
        from boardsmith_hw.synthesizer import Synthesizer

        synth = Synthesizer(
            out_dir=tmp_path, target="esp32", seed=42,
            use_llm=False, confidence_threshold=0.1,
        )
        synth.run("ESP32 with BME280 over I2C", generate_firmware=False)

        bom = json.loads((tmp_path / "bom.json").read_text())
        assert isinstance(bom, list)
        assert len(bom) > 0

    def test_schematic_is_valid_kicad(self, tmp_path):
        """Generated .kicad_sch contains valid KiCad format markers."""
        from boardsmith_hw.synthesizer import Synthesizer

        synth = Synthesizer(
            out_dir=tmp_path, target="esp32", seed=42,
            use_llm=False, confidence_threshold=0.1,
        )
        synth.run("ESP32 with BME280 over I2C", generate_firmware=False)

        content = (tmp_path / "schematic.kicad_sch").read_text()
        assert "(kicad_sch" in content
        assert "(lib_symbols" in content


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_no_llm_context():
    """Create a ToolContext suitable for --no-llm testing."""
    from tools.base import ToolContext
    from llm.config import LLMConfig
    from llm.gateway import LLMGateway

    gw = LLMGateway(LLMConfig.no_llm_mode())
    return ToolContext(
        session_id="test-no-llm",
        llm_gateway=gw,
        no_llm=True,
    )
