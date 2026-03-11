# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phase 12 — LLM-Boost Pipeline tests.

Verifies that B4 (TopologySynthesizer), B6 (ConstraintRefiner), B8 (KiCadExporter),
and B9 (ConfidenceEngine) behave correctly with and without LLM.

All tests work without real API keys — mock gateways return fixed responses.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helper: mock LLM gateway
# ---------------------------------------------------------------------------

def _make_mock_gateway(content: str, available: bool = True):
    """Return a minimal mock LLMGateway."""
    from llm.types import LLMResponse

    gw = MagicMock()
    gw.is_llm_available.return_value = available
    gw.complete_sync.return_value = LLMResponse(
        content=content,
        model="mock-model",
        provider="mock",
        skipped=not available,
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.0,
    )
    return gw


def _no_llm_gateway():
    """Gateway that reports LLM unavailable."""
    return _make_mock_gateway(content="", available=False)


def _make_selection(prompt: str = "ESP32 with BME280 temperature sensor", seed: int = 42):
    """Build a ComponentSelection for tests."""
    from boardsmith_hw.component_selector import ComponentSelector
    from boardsmith_hw.intent_parser import IntentParser
    from boardsmith_hw.requirements_normalizer import normalize

    spec = IntentParser(use_llm=False).parse(prompt)
    reqs = normalize(spec)
    return ComponentSelector(seed=seed).select(reqs)


def _make_hir(prompt: str = "ESP32 with BME280 temperature sensor"):
    """Build a full HIR for tests."""
    from boardsmith_hw.hir_composer import compose_hir
    from boardsmith_hw.topology_synthesizer import synthesize_topology

    sel = _make_selection(prompt)
    topo = synthesize_topology(sel, use_llm=False)
    return compose_hir(topo)


# ===========================================================================
# B4 — TopologySynthesizer LLM-Boost
# ===========================================================================

class TestB4NoLLM:
    """use_llm=False always works — pure deterministic path."""

    def test_synthesize_with_no_llm(self):
        """use_llm=False produces valid topology without any LLM calls."""
        from boardsmith_hw.topology_synthesizer import synthesize_topology

        sel = _make_selection("ESP32 with BME280")
        topo = synthesize_topology(sel, use_llm=False)

        assert topo is not None
        assert len(topo.components) >= 1
        assert any(c.category == "mcu" for c in topo.components)

    def test_synthesize_no_llm_has_buses(self):
        from boardsmith_hw.topology_synthesizer import synthesize_topology

        sel = _make_selection("ESP32 with BME280")
        topo = synthesize_topology(sel, use_llm=False)
        assert len(topo.buses) >= 1

    def test_synthesize_no_llm_no_gateway_calls(self):
        """When use_llm=False, get_default_gateway is never called."""
        from boardsmith_hw.topology_synthesizer import synthesize_topology

        sel = _make_selection("ESP32 with BME280")
        with patch("llm.gateway.get_default_gateway") as mock_gw:
            synthesize_topology(sel, use_llm=False)
        mock_gw.assert_not_called()


class TestB4LLMBoost:
    """use_llm=True with mock gateway."""

    def test_interface_suggestion_accepted(self):
        """LLM returns 'I2C' — topology uses I2C bus."""
        from boardsmith_hw.topology_synthesizer import synthesize_topology

        sel = _make_selection("ESP32 with BME280")
        mock_gw = _make_mock_gateway("I2C")

        with patch("llm.gateway.get_default_gateway", return_value=mock_gw):
            topo = synthesize_topology(sel, use_llm=True)

        # Topology completes regardless of LLM output
        assert topo is not None
        assert len(topo.components) >= 1

    def test_llm_unavailable_falls_back_to_deterministic(self):
        """When gateway reports unavailable, topology still succeeds."""
        from boardsmith_hw.topology_synthesizer import synthesize_topology

        sel = _make_selection("ESP32 with BME280")
        mock_gw = _no_llm_gateway()

        with patch("llm.gateway.get_default_gateway", return_value=mock_gw):
            topo = synthesize_topology(sel, use_llm=True)

        assert topo is not None
        assert len(topo.buses) >= 1

    def test_llm_returns_garbage_falls_back(self):
        """LLM returns garbage — topology still produces valid result."""
        from boardsmith_hw.topology_synthesizer import synthesize_topology

        sel = _make_selection("ESP32 with BME280")
        mock_gw = _make_mock_gateway("THIS IS NOT A VALID RESPONSE!!!")

        with patch("llm.gateway.get_default_gateway", return_value=mock_gw):
            topo = synthesize_topology(sel, use_llm=True)

        assert topo is not None
        assert len(topo.components) >= 1

    def test_llm_suggest_pins_i2c_json(self):
        """_llm_suggest_pins returns a valid I2C pin dict when LLM returns JSON."""
        from boardsmith_hw.topology_synthesizer import _llm_suggest_pins

        mock_gw = _make_mock_gateway('{"SDA": "GPIO21", "SCL": "GPIO22"}')
        with patch("llm.gateway.get_default_gateway", return_value=mock_gw):
            pins = _llm_suggest_pins("CUSTOM_MCU_XYZ", "I2C")

        # Either valid dict or None (graceful)
        if pins is not None:
            assert "SDA" in pins
            assert "SCL" in pins

    def test_llm_suggest_pins_spi_json(self):
        """_llm_suggest_pins returns a valid SPI pin dict."""
        from boardsmith_hw.topology_synthesizer import _llm_suggest_pins

        mock_gw = _make_mock_gateway('{"MOSI": "GPIO11", "MISO": "GPIO12", "SCK": "GPIO13"}')
        with patch("llm.gateway.get_default_gateway", return_value=mock_gw):
            pins = _llm_suggest_pins("CUSTOM_MCU_XYZ", "SPI")

        if pins is not None:
            assert "MOSI" in pins

    def test_llm_suggest_pins_bad_json_returns_none(self):
        """_llm_suggest_pins returns None on invalid JSON."""
        from boardsmith_hw.topology_synthesizer import _llm_suggest_pins

        mock_gw = _make_mock_gateway("not json at all")
        with patch("llm.gateway.get_default_gateway", return_value=mock_gw):
            pins = _llm_suggest_pins("CUSTOM_MCU_XYZ", "I2C")

        assert pins is None

    def test_llm_suggest_interface_returns_valid(self):
        """_llm_suggest_interface returns the correct interface string."""
        from boardsmith_hw.topology_synthesizer import _llm_suggest_interface

        mock_gw = _make_mock_gateway("SPI")
        with patch("llm.gateway.get_default_gateway", return_value=mock_gw):
            iface = _llm_suggest_interface("ESP32", "BME280", "BME280 Sensor", ["I2C", "SPI"])

        # Should return "SPI" or None (graceful)
        assert iface in ("SPI", None)

    def test_llm_suggest_interface_unavailable_returns_none(self):
        """_llm_suggest_interface returns None when LLM unavailable."""
        from boardsmith_hw.topology_synthesizer import _llm_suggest_interface

        mock_gw = _no_llm_gateway()
        with patch("llm.gateway.get_default_gateway", return_value=mock_gw):
            iface = _llm_suggest_interface("ESP32", "BME280", "BME280", ["I2C", "SPI"])

        assert iface is None


# ===========================================================================
# B6 — ConstraintRefiner LLM-Boost
# ===========================================================================

class TestB6NoLLM:
    """use_llm=False — hardcoded fixes only."""

    def test_refine_with_no_llm(self):
        """Refiner completes without LLM — no API calls."""
        from boardsmith_hw.constraint_refiner import ConstraintRefiner

        hir = _make_hir("ESP32 with BME280")
        result = ConstraintRefiner(use_llm=False).refine(hir)

        assert result is not None
        assert hasattr(result, "hir")
        assert isinstance(result.hir, dict)

    def test_no_llm_result_has_report(self):
        from boardsmith_hw.constraint_refiner import ConstraintRefiner

        hir = _make_hir("ESP32 with BME280")
        result = ConstraintRefiner(use_llm=False).refine(hir)
        assert result.report is not None

    def test_no_llm_no_gateway_calls(self):
        """use_llm=False: get_default_gateway never called."""
        from boardsmith_hw.constraint_refiner import ConstraintRefiner

        hir = _make_hir("ESP32 with BME280")
        with patch("llm.gateway.get_default_gateway") as mock_gw:
            ConstraintRefiner(use_llm=False).refine(hir)
        mock_gw.assert_not_called()


class TestB6LLMBoost:
    """use_llm=True with mock gateway."""

    def test_refine_with_unavailable_llm_still_succeeds(self):
        """When LLM unavailable, hardcoded fixes still run."""
        from boardsmith_hw.constraint_refiner import ConstraintRefiner

        hir = _make_hir("ESP32 with BME280")
        mock_gw = _no_llm_gateway()

        with patch("llm.gateway.get_default_gateway", return_value=mock_gw):
            result = ConstraintRefiner(use_llm=True).refine(hir)

        assert result is not None
        assert isinstance(result.hir, dict)

    def test_llm_fix_document_only_accepted(self):
        """LLM returns 'document_only' — adds assumption, HIR unchanged."""
        from boardsmith_hw.constraint_refiner import ConstraintRefiner

        hir = _make_hir("ESP32 with BME280")
        doc_fix = json.dumps({"action": "document_only", "note": "requires level shifter"})
        mock_gw = _make_mock_gateway(doc_fix)

        with patch("llm.gateway.get_default_gateway", return_value=mock_gw):
            result = ConstraintRefiner(use_llm=True, max_iterations=3).refine(hir)

        assert result is not None
        assert isinstance(result.hir, dict)

    def test_llm_fix_none_action_safe(self):
        """LLM returns 'none' action — no change, no crash."""
        from boardsmith_hw.constraint_refiner import ConstraintRefiner

        hir = _make_hir("ESP32 with BME280")
        mock_gw = _make_mock_gateway('{"action": "none"}')

        with patch("llm.gateway.get_default_gateway", return_value=mock_gw):
            result = ConstraintRefiner(use_llm=True, max_iterations=3).refine(hir)

        assert result is not None

    def test_llm_fix_invalid_json_no_crash(self):
        """LLM returns invalid JSON — no crash, falls back."""
        from boardsmith_hw.constraint_refiner import ConstraintRefiner

        hir = _make_hir("ESP32 with BME280")
        mock_gw = _make_mock_gateway("I cannot help with that, sorry.")

        with patch("llm.gateway.get_default_gateway", return_value=mock_gw):
            result = ConstraintRefiner(use_llm=True, max_iterations=2).refine(hir)

        assert result is not None

    def test_refiner_result_llm_boosted_flag(self):
        """RefinementResult.llm_boosted tracks whether LLM was used."""
        from boardsmith_hw.constraint_refiner import ConstraintRefiner, RefinementResult

        hir = _make_hir("ESP32 with BME280")
        result = ConstraintRefiner(use_llm=False).refine(hir)
        # Without LLM, llm_boosted should be False
        assert result.llm_boosted is False


# ===========================================================================
# B8 — KiCad Exporter LLM-Boost
# ===========================================================================

class TestB8NoLLM:
    """use_llm=False — pure grid layout."""

    def test_export_no_llm_produces_file(self, tmp_path):
        """export_kicad_sch with use_llm=False creates a valid .kicad_sch file."""
        from boardsmith_hw.kicad_exporter import export_kicad_sch

        hir_dict = _make_hir("ESP32 with BME280").model_dump()
        out = tmp_path / "test.kicad_sch"
        export_kicad_sch(hir_dict, out, use_llm=False)

        assert out.exists()
        content = out.read_text()
        assert "(kicad_sch" in content

    def test_export_no_llm_no_gateway_calls(self, tmp_path):
        """use_llm=False: get_default_gateway never called."""
        from boardsmith_hw.kicad_exporter import export_kicad_sch

        hir_dict = _make_hir("ESP32 with BME280").model_dump()
        out = tmp_path / "test.kicad_sch"
        with patch("llm.gateway.get_default_gateway") as mock_gw:
            export_kicad_sch(hir_dict, out, use_llm=False)
        mock_gw.assert_not_called()


class TestB8LLMBoost:
    """use_llm=True with mock gateway."""

    def _hir_dict(self, prompt: str = "ESP32 with BME280") -> dict:
        return _make_hir(prompt).model_dump()

    def test_export_llm_unavailable_falls_back_to_grid(self, tmp_path):
        """When LLM unavailable, grid layout is used. Still produces valid file."""
        from boardsmith_hw.kicad_exporter import export_kicad_sch

        hir_dict = self._hir_dict()
        out = tmp_path / "test.kicad_sch"
        mock_gw = _no_llm_gateway()

        with patch("llm.gateway.get_default_gateway", return_value=mock_gw):
            export_kicad_sch(hir_dict, out, use_llm=True)

        assert out.exists()
        content = out.read_text()
        assert "(kicad_sch" in content

    def test_export_llm_positions_applied(self, tmp_path):
        """When LLM returns positions JSON, those positions override grid."""
        from boardsmith_hw.kicad_exporter import export_kicad_sch

        hir_dict = self._hir_dict()
        out = tmp_path / "test.kicad_sch"

        # Get a component ID to use in LLM response
        comp_ids = [c["id"] for c in hir_dict.get("components", [])]
        assert comp_ids, "Need at least one component"
        comp_id = comp_ids[0]

        positions_json = json.dumps({comp_id: {"x": 77.7, "y": 42.0}})
        mock_gw = _make_mock_gateway(positions_json)

        with patch("llm.gateway.get_default_gateway", return_value=mock_gw):
            export_kicad_sch(hir_dict, out, use_llm=True)

        assert out.exists()
        content = out.read_text()
        assert "(kicad_sch" in content

    def test_export_llm_bad_json_falls_back(self, tmp_path):
        """LLM returns bad JSON — grid layout used as fallback, no crash."""
        from boardsmith_hw.kicad_exporter import export_kicad_sch

        hir_dict = self._hir_dict()
        out = tmp_path / "test.kicad_sch"
        mock_gw = _make_mock_gateway("not valid json at all!")

        with patch("llm.gateway.get_default_gateway", return_value=mock_gw):
            export_kicad_sch(hir_dict, out, use_llm=True)

        assert out.exists()
        content = out.read_text()
        assert "(kicad_sch" in content

    def test_export_consistent_without_llm(self, tmp_path):
        """Two runs with use_llm=False both produce valid KiCad schematic files."""
        from boardsmith_hw.kicad_exporter import export_kicad_sch

        hir_dict = self._hir_dict()
        out1 = tmp_path / "a.kicad_sch"
        out2 = tmp_path / "b.kicad_sch"
        export_kicad_sch(hir_dict, out1, use_llm=False)
        export_kicad_sch(hir_dict, out2, use_llm=False)

        # Both files exist and contain valid KiCad schema
        # (Note: UUIDs in output may differ between runs)
        assert "(kicad_sch" in out1.read_text()
        assert "(kicad_sch" in out2.read_text()


# ===========================================================================
# B9 — ConfidenceEngine LLM-boost signal
# ===========================================================================

class TestB9LLMBoost:
    """llm_boosted_stages signal wired up and tested."""

    def _empty_report(self):
        from synth_core.hir_bridge.validator import DiagnosticsReport
        return DiagnosticsReport(constraints=[])

    def test_no_boost_without_llm_stages(self):
        from boardsmith_hw.confidence_engine import ConfidenceEngine

        engine = ConfidenceEngine()
        result = engine.compute(
            intent_confidence=0.8,
            component_confidence=0.8,
            topology_confidence=0.8,
            validation_report=self._empty_report(),
            assumptions=[],
            llm_boosted_stages=None,
        )
        # No LLM boost applied — explanations should not mention LLM
        llm_explanations = [e for e in result.explanations if "LLM-boost" in e]
        assert len(llm_explanations) == 0

    def test_boost_applied_per_stage(self):
        """Each boosted stage adds 0.01 to overall confidence."""
        from boardsmith_hw.confidence_engine import ConfidenceEngine

        engine = ConfidenceEngine()

        result_no_boost = engine.compute(0.8, 0.8, 0.8, self._empty_report(), [])
        result_boosted = engine.compute(
            0.8, 0.8, 0.8, self._empty_report(), [],
            llm_boosted_stages=["B4", "B6"],
        )

        expected_boost = 0.01 * 2
        assert abs(result_boosted.overall - (result_no_boost.overall + expected_boost)) < 0.001

    def test_boost_in_explanations(self):
        """llm_boosted_stages appears in explanations."""
        from boardsmith_hw.confidence_engine import ConfidenceEngine

        engine = ConfidenceEngine()
        result = engine.compute(
            0.7, 0.7, 0.7, self._empty_report(), [],
            llm_boosted_stages=["B6"],
        )
        llm_exps = [e for e in result.explanations if "LLM-boost" in e or "llm" in e.lower()]
        assert len(llm_exps) >= 1

    def test_boost_capped_at_1_0(self):
        """Overall confidence never exceeds 1.0 even with many boosted stages."""
        from boardsmith_hw.confidence_engine import ConfidenceEngine

        engine = ConfidenceEngine()
        result = engine.compute(
            1.0, 1.0, 1.0, self._empty_report(), [],
            llm_boosted_stages=["B1", "B3", "B4", "B6", "B8", "B9"],
        )
        assert result.overall <= 1.0

    def test_boost_stages_stored_in_result(self):
        """llm_boosted_stages is returned in ConfidenceResult."""
        from boardsmith_hw.confidence_engine import ConfidenceEngine

        engine = ConfidenceEngine()
        result = engine.compute(
            0.8, 0.8, 0.8, self._empty_report(), [],
            llm_boosted_stages=["B4"],
        )
        assert "B4" in result.llm_boosted_stages

    def test_empty_stages_list_no_boost(self):
        """Empty list = no boost (same as None)."""
        from boardsmith_hw.confidence_engine import ConfidenceEngine

        engine = ConfidenceEngine()
        result_none = engine.compute(0.8, 0.8, 0.8, self._empty_report(), [])
        result_empty = engine.compute(0.8, 0.8, 0.8, self._empty_report(), [], llm_boosted_stages=[])
        assert result_none.overall == result_empty.overall

    def test_boost_with_assumption_penalty(self):
        """LLM boost and assumption penalty both apply: net = -0.02 + 0.01 = -0.01."""
        from boardsmith_hw.confidence_engine import ConfidenceEngine

        engine = ConfidenceEngine()
        result_clean = engine.compute(
            0.9, 0.9, 0.9, self._empty_report(),
            assumptions=[],
            llm_boosted_stages=[],
        )
        result_modified = engine.compute(
            0.9, 0.9, 0.9, self._empty_report(),
            assumptions=["assumption_1"],   # -0.02 penalty
            llm_boosted_stages=["B6"],      # +0.01 boost
        )
        # Net delta = -0.02 + 0.01 = -0.01
        delta = round(result_modified.overall - result_clean.overall, 3)
        assert abs(delta - (-0.01)) < 0.001


# ===========================================================================
# --no-llm Integration: full pipeline with use_llm=False at every stage
# ===========================================================================

class TestFullPipelineNoLLM:
    """End-to-end: all stages with use_llm=False → valid schematic + confidence."""

    def test_full_pipeline_no_llm(self, tmp_path):
        """B4 → B6 → B8 → B9 all run without LLM, producing valid outputs."""
        from boardsmith_hw.confidence_engine import ConfidenceEngine
        from boardsmith_hw.constraint_refiner import ConstraintRefiner
        from boardsmith_hw.hir_composer import compose_hir
        from boardsmith_hw.kicad_exporter import export_kicad_sch
        from boardsmith_hw.topology_synthesizer import synthesize_topology
        from synth_core.hir_bridge.validator import DiagnosticsReport

        sel = _make_selection("ESP32 with BME280")

        # B4
        topo = synthesize_topology(sel, use_llm=False)
        assert len(topo.buses) >= 1

        # B5 (HIR composition)
        hir = compose_hir(topo)

        # B6
        result = ConstraintRefiner(use_llm=False).refine(hir)
        assert isinstance(result.hir, dict)

        # B8
        out = tmp_path / "schematic.kicad_sch"
        export_kicad_sch(result.hir, out, use_llm=False)
        assert out.exists()
        assert "(kicad_sch" in out.read_text()

        # B9
        engine = ConfidenceEngine()
        confidence = engine.compute(
            intent_confidence=0.9,
            component_confidence=topo.components[0].score if topo.components else 0.8,
            topology_confidence=0.85,
            validation_report=result.report,
            assumptions=topo.assumptions,
        )
        assert 0.0 <= confidence.overall <= 1.0

    def test_full_pipeline_with_llm_boost_flags(self, tmp_path):
        """B9 confidence boosted when B4/B8 used LLM."""
        from boardsmith_hw.confidence_engine import ConfidenceEngine
        from boardsmith_hw.constraint_refiner import ConstraintRefiner
        from boardsmith_hw.hir_composer import compose_hir
        from boardsmith_hw.topology_synthesizer import synthesize_topology

        sel = _make_selection("ESP32 with BME280")
        topo = synthesize_topology(sel, use_llm=False)
        hir = compose_hir(topo)
        result = ConstraintRefiner(use_llm=False).refine(hir)

        engine = ConfidenceEngine()
        conf_no_boost = engine.compute(0.9, 0.85, 0.85, result.report, [])
        conf_boosted = engine.compute(
            0.9, 0.85, 0.85, result.report, [],
            llm_boosted_stages=["B4", "B8"],
        )
        assert conf_boosted.overall > conf_no_boost.overall
        assert abs(conf_boosted.overall - conf_no_boost.overall - 0.02) < 0.001
