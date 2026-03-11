# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Phase 21 — Voller Agentischer Loop.

Covers:
  - ElectricalReviewAgent     — voltage conflicts, I2C loading, SPI clock, decap, power-seq
  - ComponentQualityAgent     — JLCPCB availability, EOL, package, BOM cost
  - PCBReviewAgent            — DRC, board density, SPI traces, manufacturing spec, copper fill
  - IterationMemory           — issue tracking, fix recording, oscillation prevention
  - IterativeOrchestrator     — multi-agent integration (agent_scores, chronic_issues)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("shared", "synthesizer", "compiler"):
    _p = str(_REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Shared HIR fixtures
# ---------------------------------------------------------------------------

def _base_hir(**kwargs) -> dict:
    """Minimal HIR with one MCU and one I2C sensor."""
    hir = {
        "version": "1.1.0",
        "source": "test",
        "components": [
            {
                "id": "U1", "mpn": "ESP32-WROOM-32", "name": "ESP32-WROOM-32",
                "role": "mcu", "interface_types": ["I2C", "SPI"],
                "pins": [], "manufacturer": "Espressif",
                "provenance": {"source_type": "builtin_db", "confidence": 0.95},
            },
            {
                "id": "U2", "mpn": "BME280", "name": "BME280",
                "role": "sensor", "interface_types": ["I2C"],
                "pins": [], "manufacturer": "Bosch",
                "provenance": {"source_type": "builtin_db", "confidence": 0.95},
            },
        ],
        "bus_contracts": [
            {
                "bus_name": "I2C0", "bus_type": "I2C",
                "master_id": "U1", "slave_ids": ["U2"],
                "configured_clock_hz": 400_000,
                "slave_addresses": {"U2": 118},
                "pin_assignments": {"SDA": "IO21", "SCL": "IO22"},
                "provenance": {"source_type": "builtin_db", "confidence": 0.95},
            },
        ],
        "constraints": [],
        "nets": [],
        "buses": [],
        "electrical_specs": [],
        "init_contracts": [],
        "bom": [],
        "power_sequence": {"rails": [], "dependencies": []},
        "metadata": {"created_at": "2026-03-01T00:00:00Z", "track": "B",
                     "confidence": {"overall": 0.85, "explanations": []}},
    }
    hir.update(kwargs)
    return hir


def _hir_with_spi() -> dict:
    hir = _base_hir()
    hir["bus_contracts"] = [
        {
            "bus_name": "SPI0", "bus_type": "SPI",
            "master_id": "U1", "slave_ids": ["U2"],
            "configured_clock_hz": 8_000_000,
            "slave_addresses": {},
            "pin_assignments": {"MOSI": "IO23", "MISO": "IO19", "SCLK": "IO18", "CS": "IO5"},
            "provenance": {"source_type": "builtin_db", "confidence": 0.95},
        },
    ]
    return hir


def _hir_with_decap() -> dict:
    hir = _base_hir()
    hir["components"].append({
        "id": "C1", "mpn": "CC0402KRX7R9BB104",
        "name": "100nF bypass capacitor", "role": "passive",
        "interface_types": [], "pins": [],
        "provenance": {"source_type": "builtin_db", "confidence": 0.9},
    })
    return hir


# ===========================================================================
# ElectricalReviewAgent
# ===========================================================================

class TestElectricalReviewAgent:
    def _agent(self):
        from agents.electrical_review_agent import ElectricalReviewAgent
        return ElectricalReviewAgent()

    def test_returns_result_with_score(self):
        result = self._agent().review(_base_hir())
        assert 0.0 <= result.score <= 1.0

    def test_clean_hir_has_high_score(self):
        result = self._agent().review(_base_hir())
        assert result.score >= 0.70, f"Expected clean HIR score ≥ 0.70, got {result.score}"

    def test_checks_run_list_populated(self):
        result = self._agent().review(_base_hir())
        assert len(result.checks_run) >= 3

    def test_voltage_conflict_detected_for_5v_ic(self):
        hir = _base_hir()
        hir["components"].append({
            "id": "U3", "mpn": "74HC595", "name": "74HC595 Shift Register",
            "role": "comms", "interface_types": [],
            "pins": [], "provenance": {"source_type": "builtin_db", "confidence": 0.9},
        })
        result = self._agent().review(hir)
        codes = [i.code for i in result.issues]
        assert "VOLTAGE_LEVEL_CONFLICT" in codes

    def test_i2c_overload_detected(self):
        hir = _base_hir()
        slave_ids = [f"U{i}" for i in range(2, 12)]
        hir["components"].extend([
            {"id": uid, "mpn": "BMP280", "name": f"Sensor {uid}",
             "role": "sensor", "interface_types": ["I2C"], "pins": [],
             "provenance": {"source_type": "builtin_db", "confidence": 0.9}}
            for uid in slave_ids
        ])
        hir["bus_contracts"][0]["slave_ids"] = slave_ids
        result = self._agent().review(hir)
        codes = [i.code for i in result.issues]
        assert "I2C_OVERLOADED" in codes

    def test_i2c_4_slaves_no_error(self):
        hir = _base_hir()
        slave_ids = [f"U{i}" for i in range(2, 6)]
        hir["components"].extend([
            {"id": uid, "mpn": "BMP280", "name": f"Sensor {uid}",
             "role": "sensor", "interface_types": ["I2C"], "pins": [],
             "provenance": {"source_type": "builtin_db", "confidence": 0.9}}
            for uid in slave_ids
        ])
        hir["bus_contracts"][0]["slave_ids"] = slave_ids
        result = self._agent().review(hir)
        codes = [i.code for i in result.issues]
        assert "I2C_OVERLOADED" not in codes

    def test_spi_clock_too_high_detected(self):
        hir = _hir_with_spi()
        hir["bus_contracts"][0]["configured_clock_hz"] = 80_000_000
        hir["bus_contracts"][0]["slave_ids"] = ["U2", "U3"]
        result = self._agent().review(hir)
        codes = [i.code for i in result.issues]
        assert "SPI_CLOCK_TOO_HIGH" in codes

    def test_safe_spi_clock_no_warning(self):
        hir = _hir_with_spi()
        hir["bus_contracts"][0]["configured_clock_hz"] = 1_000_000
        result = self._agent().review(hir)
        codes = [i.code for i in result.issues]
        assert "SPI_CLOCK_TOO_HIGH" not in codes

    def test_missing_decoupling_detected(self):
        result = self._agent().review(_base_hir())
        codes = [i.code for i in result.issues]
        assert "MISSING_DECOUPLING" in codes

    def test_present_decoupling_no_warning(self):
        result = self._agent().review(_hir_with_decap())
        codes = [i.code for i in result.issues]
        assert "MISSING_DECOUPLING" not in codes

    def test_power_cycle_detected(self):
        hir = _base_hir()
        hir["power_sequence"] = {
            "rails": ["3V3", "5V"],
            "dependencies": [
                {"rail": "3V3", "after": "5V"},
                {"rail": "5V", "after": "3V3"},   # cycle!
            ],
        }
        result = self._agent().review(hir)
        codes = [i.code for i in result.issues]
        assert "POWER_SEQ_CYCLE" in codes

    def test_score_decreases_with_errors(self):
        hir_clean = _hir_with_decap()
        hir_bad   = _base_hir()
        r_clean = self._agent().review(hir_clean)
        r_bad   = self._agent().review(hir_bad)
        # Bad HIR (missing decap) should score worse or equal to clean
        assert r_bad.score <= r_clean.score + 0.01


# ===========================================================================
# ComponentQualityAgent
# ===========================================================================

class TestComponentQualityAgent:
    def _agent(self):
        from agents.component_quality_agent import ComponentQualityAgent
        return ComponentQualityAgent()

    def test_returns_result_with_score(self):
        result = self._agent().review(_base_hir())
        assert 0.0 <= result.score <= 1.0

    def test_estimated_bom_usd_positive(self):
        result = self._agent().review(_base_hir())
        assert result.estimated_bom_usd >= 0.0

    def test_checks_run_list_populated(self):
        result = self._agent().review(_base_hir())
        assert len(result.checks_run) >= 3

    def test_known_basic_parts_increase_count(self):
        result = self._agent().review(_hir_with_decap())
        assert result.jlcpcb_basic_count >= 1

    def test_eol_marker_in_mpn_triggers_warning(self):
        hir = _base_hir()
        hir["components"].append({
            "id": "U3", "mpn": "OBSOLETE-SENSOR-EOL",
            "name": "Some EOL sensor", "role": "sensor",
            "interface_types": [], "pins": [],
            "provenance": {"source_type": "builtin_db", "confidence": 0.9},
        })
        result = self._agent().review(hir)
        codes = [i.code for i in result.issues]
        assert "EOL_COMPONENT" in codes

    def test_eol_marker_in_description_triggers_warning(self):
        hir = _base_hir()
        hir["components"].append({
            "id": "U4", "mpn": "MYSENSOR", "name": "Discontinued sensor",
            "description": "not recommended for new designs",
            "role": "sensor", "interface_types": [], "pins": [],
            "provenance": {"source_type": "builtin_db", "confidence": 0.9},
        })
        result = self._agent().review(hir)
        codes = [i.code for i in result.issues]
        assert "EOL_COMPONENT" in codes

    def test_bga_package_triggers_warning(self):
        hir = _base_hir()
        hir["components"].append({
            "id": "U5", "mpn": "SOME-BGA-CHIP", "name": "BGA part",
            "role": "mcu", "package": "BGA144",
            "interface_types": [], "pins": [],
            "provenance": {"source_type": "builtin_db", "confidence": 0.9},
        })
        result = self._agent().review(hir)
        codes = [i.code for i in result.issues]
        assert "MACHINE_ONLY_PACKAGE" in codes

    def test_soic_package_no_warning(self):
        hir = _base_hir()
        hir["components"][0]["package"] = "SOIC-8"
        result = self._agent().review(hir)
        codes = [i.code for i in result.issues]
        assert "MACHINE_ONLY_PACKAGE" not in codes

    def test_high_bom_cost_warns(self):
        hir = _base_hir()
        # Add many expensive sensors to push cost > $50
        for i in range(20):
            hir["components"].append({
                "id": f"U{i+10}", "mpn": f"EXPENSIVE-{i}", "name": "Specialty IC",
                "role": "comms", "interface_types": [], "pins": [],
                "provenance": {"source_type": "builtin_db", "confidence": 0.9},
            })
        result = self._agent().review(hir)
        codes = [i.code for i in result.issues]
        assert "BOM_COST_ELEVATED" in codes or "BOM_COST_HIGH" in codes

    def test_empty_components_score_is_1(self):
        hir = _base_hir()
        hir["components"] = []
        result = self._agent().review(hir)
        assert result.score == 1.0
        assert result.estimated_bom_usd == 0.0


# ===========================================================================
# PCBReviewAgent
# ===========================================================================

class TestPCBReviewAgent:
    def _agent(self):
        from agents.pcb_review_agent import PCBReviewAgent
        return PCBReviewAgent()

    def test_returns_result_without_pcb_result(self):
        result = self._agent().review(_base_hir(), pcb_result=None)
        assert 0.0 <= result.score <= 1.0

    def test_checks_run_populated(self):
        result = self._agent().review(_base_hir())
        assert len(result.checks_run) >= 3

    def test_no_drc_errors_without_pcb_result(self):
        result = self._agent().review(_base_hir())
        assert result.drc_error_count == 0

    def test_drc_errors_from_pcb_result(self):
        class FakePcbResult:
            drc_errors = ["error: clearance violation", "error: track too narrow"]
            pcb_path = None

        result = self._agent().review(_base_hir(), pcb_result=FakePcbResult())
        assert result.drc_error_count == 2
        codes = [i.code for i in result.issues]
        assert "DRC_ERRORS" in codes

    def test_score_penalised_by_drc_errors(self):
        class FakePcbResult:
            drc_errors = ["error: clearance"] * 5
            pcb_path = None

        result = self._agent().review(_base_hir(), pcb_result=FakePcbResult())
        assert result.score < 0.85

    def test_spi_high_clock_multi_slave_warning(self):
        hir = _hir_with_spi()
        hir["bus_contracts"][0]["configured_clock_hz"] = 50_000_000
        hir["bus_contracts"][0]["slave_ids"] = ["U2", "U3"]
        result = self._agent().review(hir)
        codes = [i.code for i in result.issues]
        assert "SPI_STUB_LENGTH" in codes

    def test_spi_single_slave_no_stub_warning(self):
        hir = _hir_with_spi()
        hir["bus_contracts"][0]["configured_clock_hz"] = 50_000_000
        result = self._agent().review(hir)
        codes = [i.code for i in result.issues]
        assert "SPI_STUB_LENGTH" not in codes

    def test_narrow_trace_detected_from_pcb_file(self, tmp_path):
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text(
            "(kicad_pcb\n  (segment (net 1) (width 0.05))\n)",
            encoding="utf-8",
        )

        class FakePcbResult:
            drc_errors: list = []
            pcb_path = str(pcb)

        result = self._agent().review(_base_hir(), pcb_result=FakePcbResult())
        codes = [i.code for i in result.issues]
        assert "TRACE_BELOW_SPEC" in codes

    def test_compliant_trace_no_error(self, tmp_path):
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text(
            "(kicad_pcb\n  (segment (net 1) (width 0.25))\n)",
            encoding="utf-8",
        )

        class FakePcbResult:
            drc_errors: list = []
            pcb_path = str(pcb)

        result = self._agent().review(_base_hir(), pcb_result=FakePcbResult())
        codes = [i.code for i in result.issues]
        assert "TRACE_BELOW_SPEC" not in codes

    def test_no_copper_fill_warning(self, tmp_path):
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb (version 20221018))", encoding="utf-8")

        class FakePcbResult:
            drc_errors: list = []
            pcb_path = str(pcb)

        result = self._agent().review(_base_hir(), pcb_result=FakePcbResult())
        codes = [i.code for i in result.issues]
        assert "NO_COPPER_FILL" in codes

    def test_copper_fill_present_no_warning(self, tmp_path):
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text(
            '(kicad_pcb\n  (zone (net 1) (net_name "GND"))\n)',
            encoding="utf-8",
        )

        class FakePcbResult:
            drc_errors: list = []
            pcb_path = str(pcb)

        result = self._agent().review(_base_hir(), pcb_result=FakePcbResult())
        codes = [i.code for i in result.issues]
        assert "NO_COPPER_FILL" not in codes


# ===========================================================================
# IterationMemory
# ===========================================================================

class TestIterationMemory:
    def _mem(self):
        from agents.iteration_memory import IterationMemory
        return IterationMemory()

    def test_record_and_retrieve_issues(self):
        mem = self._mem()
        mem.record_issues(1, ["OVERCURRENT", "MISSING_INIT"])
        assert len(mem.persistent_issues(min_iterations=1)) == 2

    def test_resolved_when_not_seen_again(self):
        mem = self._mem()
        mem.record_issues(1, ["OVERCURRENT", "MISSING_INIT"])
        mem.record_issues(2, ["MISSING_INIT"])  # OVERCURRENT not seen
        resolved = [h.code for h in mem.resolved_issues()]
        assert "OVERCURRENT" in resolved

    def test_persistent_issue_min_iterations(self):
        mem = self._mem()
        mem.record_issues(1, ["CODE_A"])
        mem.record_issues(2, ["CODE_A"])
        persistent = mem.persistent_issues(min_iterations=2)
        assert any(h.code == "CODE_A" for h in persistent)

    def test_single_occurrence_not_persistent_for_min2(self):
        mem = self._mem()
        mem.record_issues(1, ["CODE_B"])
        persistent = mem.persistent_issues(min_iterations=2)
        assert not any(h.code == "CODE_B" for h in persistent)

    def test_record_fixes_tracked(self):
        mem = self._mem()
        mem.record_issues(1, ["OVERCURRENT"])
        mem.record_fixes(1, ["OVERCURRENT"])
        assert "OVERCURRENT" in mem.already_fixed_codes()

    def test_already_fixed_codes_initially_empty(self):
        mem = self._mem()
        assert len(mem.already_fixed_codes()) == 0

    def test_chronic_issues_detected(self):
        mem = self._mem()
        mem.record_issues(1, ["STUCK"])
        mem.record_fixes(1, ["STUCK"])
        mem.record_issues(2, ["STUCK"])
        mem.record_fixes(2, ["STUCK"])
        chronic = mem.chronic_issue_codes(min_fix_attempts=2)
        assert "STUCK" in chronic

    def test_not_chronic_after_one_fix(self):
        mem = self._mem()
        mem.record_issues(1, ["FIXABLE"])
        mem.record_fixes(1, ["FIXABLE"])
        chronic = mem.chronic_issue_codes(min_fix_attempts=2)
        assert "FIXABLE" not in chronic

    def test_summary_is_json_serializable(self):
        import json
        mem = self._mem()
        mem.record_issues(1, ["A", "B"])
        mem.record_fixes(1, ["A"])
        summary = mem.summary(current_iteration=1)
        dumped = json.dumps(summary)
        assert "A" in dumped
        assert "total_unique_issues" in dumped

    def test_times_seen_increments(self):
        mem = self._mem()
        mem.record_issues(1, ["CODE_X"])
        mem.record_issues(2, ["CODE_X"])
        mem.record_issues(3, ["CODE_X"])
        h = mem._history.get("CODE_X")
        assert h is not None
        assert h.times_seen == 3


# ===========================================================================
# IterativeOrchestrator — Phase 21 multi-agent integration
# ===========================================================================

class TestIterativeOrchestratorPhase21:
    """Integration tests: IterationRecord carries agent_scores + chronic_issues."""

    def _orchestrator(self):
        from agents.iterative_orchestrator import IterativeOrchestrator
        return IterativeOrchestrator(use_llm=False)

    def test_iteration_record_has_agent_scores_field(self):
        from agents.iterative_orchestrator import IterationRecord
        rec = IterationRecord(iteration=1, confidence=0.8, delta_confidence=0.0)
        assert hasattr(rec, "agent_scores")
        assert isinstance(rec.agent_scores, dict)

    def test_iteration_record_has_chronic_issues_field(self):
        from agents.iterative_orchestrator import IterationRecord
        rec = IterationRecord(iteration=1, confidence=0.8, delta_confidence=0.0)
        assert hasattr(rec, "chronic_issues")
        assert isinstance(rec.chronic_issues, list)

    def test_orchestrator_has_multi_agent_review_method(self):
        orch = self._orchestrator()
        assert hasattr(orch, "_run_multi_agent_review")

    def test_orchestrator_has_memory_attribute(self):
        orch = self._orchestrator()
        assert hasattr(orch, "_memory")

    def test_call_electrical_agent_returns_tuple(self):
        orch = self._orchestrator()
        score, issues = orch._call_electrical_agent(_base_hir())
        assert 0.0 <= score <= 1.0
        assert isinstance(issues, list)

    def test_call_quality_agent_returns_tuple(self):
        orch = self._orchestrator()
        score, issues = orch._call_quality_agent(_base_hir())
        assert 0.0 <= score <= 1.0
        assert isinstance(issues, list)

    def test_call_pcb_agent_returns_tuple(self):
        orch = self._orchestrator()
        score, issues = orch._call_pcb_agent(_base_hir())
        assert 0.0 <= score <= 1.0
        assert isinstance(issues, list)

    def test_multi_agent_review_returns_review_and_scores(self):
        import asyncio
        orch = self._orchestrator()
        review, agent_scores = asyncio.run(
            orch._run_multi_agent_review(_base_hir(), "test prompt")
        )
        assert "combined" in agent_scores
        assert "electrical" in agent_scores
        assert "component_quality" in agent_scores
        assert "pcb" in agent_scores
        assert 0.0 <= agent_scores["combined"] <= 1.0

    def test_combined_score_is_weighted_average(self):
        import asyncio
        orch = self._orchestrator()
        _, scores = asyncio.run(
            orch._run_multi_agent_review(_base_hir(), "test")
        )
        combined = scores["combined"]
        expected = (
            0.35 * scores["design_review"]
            + 0.25 * scores["electrical"]
            + 0.20 * scores["component_quality"]
            + 0.20 * scores["pcb"]
        )
        assert abs(combined - round(expected, 3)) < 0.01

    def test_memory_initialised_in_build(self):
        """IterationMemory is created at the start of build()."""
        import asyncio
        orch = self._orchestrator()
        # Just call build with a trivial prompt and max_iterations=1
        # We only care that _memory is set by the end
        try:
            asyncio.run(orch.build(
                prompt="ESP32 with BME280 over I2C",
                target="esp32",
                out_dir=Path("/tmp/boardsmith_test_21"),
                quality="fast",
                max_iterations=1,
                with_pcb=False,
                generate_firmware=False,
            ))
        except Exception:
            pass  # synthesis may fail in test env — memory still set
        assert orch._memory is not None
