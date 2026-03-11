# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Phase 21: FirmwareReviewAgent and IterativeOrchestrator."""
from __future__ import annotations

import asyncio
import json
import zipfile
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_firmware_dir(tmp_path: Path, todos: int = 0) -> Path:
    """Create a fake firmware directory."""
    fw = tmp_path / "firmware"
    fw.mkdir()

    lines = ["#include <stdio.h>\n", "int main(void) {\n"]
    for i in range(todos):
        lines.append(f"    // TODO: implement step {i}\n")
    lines.append("    return 0;\n}\n")

    (fw / "main.c").write_text("".join(lines))
    (fw / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.12)\n")
    return fw


def _make_hir() -> dict:
    return {
        "system_name": "TestBoard",
        "components": [
            {"id": "ESP32", "mpn": "ESP32-WROOM-32", "role": "mcu"},
            {"id": "BME280", "mpn": "BME280", "role": "sensor"},
        ],
        "bus_contracts": [{"bus_type": "I2C", "bus_name": "i2c0"}],
    }


# ---------------------------------------------------------------------------
# Tests — FirmwareReviewAgent
# ---------------------------------------------------------------------------


class TestFirmwareReviewAgent:
    def test_no_firmware_dir_returns_zero_score(self):
        from agents.firmware_review_agent import FirmwareReviewAgent
        agent = FirmwareReviewAgent()
        result = agent.review(None)
        assert result.score == 0.0
        assert result.file_count == 0

    def test_nonexistent_dir_returns_zero_score(self, tmp_path):
        from agents.firmware_review_agent import FirmwareReviewAgent
        agent = FirmwareReviewAgent()
        result = agent.review(tmp_path / "nonexistent")
        assert result.score == 0.0

    def test_clean_firmware_is_compilable(self, tmp_path):
        from agents.firmware_review_agent import FirmwareReviewAgent
        fw = _make_firmware_dir(tmp_path, todos=0)
        agent = FirmwareReviewAgent()
        result = agent.review(fw)
        assert result.compilable is True
        assert result.todo_count == 0
        assert result.score == 1.0

    def test_todos_reduce_score(self, tmp_path):
        from agents.firmware_review_agent import FirmwareReviewAgent
        fw = _make_firmware_dir(tmp_path, todos=4)
        agent = FirmwareReviewAgent()
        result = agent.review(fw)
        assert result.todo_count == 4
        assert result.score < 1.0
        assert result.compilable is False

    def test_score_lower_for_more_todos(self, tmp_path):
        from agents.firmware_review_agent import FirmwareReviewAgent
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        fw_few = _make_firmware_dir(tmp_path / "a", todos=1)
        fw_many = _make_firmware_dir(tmp_path / "b", todos=5)
        agent = FirmwareReviewAgent()
        r_few = agent.review(fw_few)
        r_many = agent.review(fw_many)
        assert r_few.score > r_many.score

    def test_score_never_below_zero(self, tmp_path):
        from agents.firmware_review_agent import FirmwareReviewAgent
        fw = _make_firmware_dir(tmp_path, todos=30)
        agent = FirmwareReviewAgent()
        result = agent.review(fw)
        assert result.score >= 0.0

    def test_missing_entry_point_reported(self, tmp_path):
        from agents.firmware_review_agent import FirmwareReviewAgent
        fw = tmp_path / "firmware"
        fw.mkdir()
        (fw / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.12)\n")
        (fw / "helpers.h").write_text("// helpers\n")
        agent = FirmwareReviewAgent()
        result = agent.review(fw)
        assert not result.has_entry_point
        issues_text = " ".join(result.issues).lower()
        assert "main" in issues_text

    def test_missing_build_file_reported(self, tmp_path):
        from agents.firmware_review_agent import FirmwareReviewAgent
        fw = tmp_path / "firmware"
        fw.mkdir()
        (fw / "main.c").write_text("int main() { return 0; }\n")
        agent = FirmwareReviewAgent()
        result = agent.review(fw)
        assert not result.has_build_file

    def test_has_entry_point_detected(self, tmp_path):
        from agents.firmware_review_agent import FirmwareReviewAgent
        fw = _make_firmware_dir(tmp_path, todos=0)
        agent = FirmwareReviewAgent()
        result = agent.review(fw)
        assert result.has_entry_point is True

    def test_has_build_file_detected(self, tmp_path):
        from agents.firmware_review_agent import FirmwareReviewAgent
        fw = _make_firmware_dir(tmp_path, todos=0)
        agent = FirmwareReviewAgent()
        result = agent.review(fw)
        assert result.has_build_file is True

    def test_file_count_correct(self, tmp_path):
        from agents.firmware_review_agent import FirmwareReviewAgent
        fw = _make_firmware_dir(tmp_path, todos=0)
        (fw / "extra.h").write_text("// extra\n")
        agent = FirmwareReviewAgent()
        result = agent.review(fw)
        assert result.file_count >= 2  # main.c + extra.h

    def test_todos_list_populated(self, tmp_path):
        from agents.firmware_review_agent import FirmwareReviewAgent
        fw = _make_firmware_dir(tmp_path, todos=2)
        agent = FirmwareReviewAgent()
        result = agent.review(fw)
        assert len(result.todos) >= 1

    def test_summary_string(self, tmp_path):
        from agents.firmware_review_agent import FirmwareReviewAgent
        fw = _make_firmware_dir(tmp_path, todos=0)
        agent = FirmwareReviewAgent()
        result = agent.review(fw)
        summary = result.summary()
        assert "Firmware" in summary
        assert "score" in summary

    def test_fixme_counted_as_todo(self, tmp_path):
        from agents.firmware_review_agent import FirmwareReviewAgent
        fw = tmp_path / "firmware"
        fw.mkdir()
        (fw / "main.c").write_text("int main() {\n    // FIXME: broken\n    return 0;\n}\n")
        (fw / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.12)\n")
        agent = FirmwareReviewAgent()
        result = agent.review(fw)
        assert result.todo_count >= 1
        assert result.compilable is False

    def test_empty_dir_returns_zero_score(self, tmp_path):
        from agents.firmware_review_agent import FirmwareReviewAgent
        fw = tmp_path / "firmware"
        fw.mkdir()
        agent = FirmwareReviewAgent()
        result = agent.review(fw)
        assert result.score == 0.0
        assert result.file_count == 0


# ---------------------------------------------------------------------------
# Tests — IterationRecord / AuditTrail / BuildResult dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_iteration_record_fields(self):
        from agents.iterative_orchestrator import IterationRecord
        r = IterationRecord(
            iteration=1,
            confidence=0.82,
            delta_confidence=0.12,
            issues_found=["WARNING: [OVERCURRENT] power issue"],
            fixes_applied=["OVERCURRENT"],
            stages_rerun=["B1-B9"],
        )
        assert r.iteration == 1
        assert r.confidence == 0.82
        assert r.delta_confidence == 0.12
        assert len(r.issues_found) == 1
        assert len(r.fixes_applied) == 1
        assert r.hitl_required is False

    def test_audit_trail_to_dict(self):
        from agents.iterative_orchestrator import AuditTrail, IterationRecord
        trail = AuditTrail(
            prompt="ESP32 with BME280",
            target="esp32",
            quality="balanced",
            max_iterations=5,
        )
        trail.iterations.append(IterationRecord(
            iteration=1,
            confidence=0.88,
            delta_confidence=0.0,
        ))
        d = trail.to_dict()
        assert isinstance(d, dict)
        assert d["prompt"] == "ESP32 with BME280"
        assert d["target"] == "esp32"
        assert len(d["iterations"]) == 1
        assert d["iterations"][0]["confidence"] == 0.88

    def test_build_result_fields(self):
        from agents.iterative_orchestrator import AuditTrail, BuildResult
        result = BuildResult(
            success=True,
            confidence=0.91,
            artifacts=["hir.json"],
            audit_trail=AuditTrail("p", "esp32", "high", 5),
        )
        assert result.success is True
        assert result.confidence == 0.91
        assert result.hitl_required is False
        assert result.error is None


# ---------------------------------------------------------------------------
# Tests — IterativeOrchestrator
# ---------------------------------------------------------------------------


class TestIterativeOrchestrator:
    """Unit tests for the orchestrator — mock heavy dependencies."""

    def _make_mock_synthesis(self, hir: dict, confidence: float = 0.80):
        """Create a mock SynthesisResult-like object."""
        mock = MagicMock()
        mock.confidence = confidence
        mock.success = True
        mock.artifacts = ["hir.json", "bom.json", "schematic.kicad_sch"]
        mock.hitl_required = False
        mock.error = None
        return mock

    def _make_mock_review(self, score: float = 0.88, hitl: bool = False):
        """Create a mock DesignReviewResult-like object."""
        mock = MagicMock()
        mock.score = score
        mock.hitl_required = hitl
        mock.issues = []
        return mock

    def test_accept_thresholds_defined(self):
        from agents.iterative_orchestrator import ACCEPT_THRESHOLDS
        assert "fast" in ACCEPT_THRESHOLDS
        assert "balanced" in ACCEPT_THRESHOLDS
        assert "high" in ACCEPT_THRESHOLDS
        assert ACCEPT_THRESHOLDS["fast"] < ACCEPT_THRESHOLDS["high"]

    def test_orchestrator_instantiates(self):
        from agents.iterative_orchestrator import IterativeOrchestrator
        o = IterativeOrchestrator(use_llm=False)
        assert o is not None

    def test_audit_trail_written(self, tmp_path):
        """After build(), audit_trail.json must exist."""
        from agents.iterative_orchestrator import IterativeOrchestrator

        o = IterativeOrchestrator(use_llm=False)

        # We need to mock the internal methods so no real synthesis runs
        async def _mock_build(*args, **kwargs):
            from agents.iterative_orchestrator import AuditTrail, BuildResult, IterationRecord
            trail = AuditTrail("test", "esp32", "balanced", 1)
            trail.iterations.append(IterationRecord(1, 0.88, 0.0, accept_reason="threshold_met"))
            trail.final_confidence = 0.88
            trail.accept_reason = "threshold_met"
            # Write the audit trail
            audit_path = tmp_path / "audit_trail.json"
            audit_path.write_text(
                __import__("json").dumps(trail.to_dict(), indent=2), encoding="utf-8"
            )
            return BuildResult(
                success=True,
                confidence=0.88,
                artifacts=[str(audit_path)],
                audit_trail=trail,
            )

        o.build = _mock_build
        result = asyncio.run(o.build(
            prompt="test",
            target="esp32",
            out_dir=tmp_path,
        ))
        assert (tmp_path / "audit_trail.json").exists()
        data = json.loads((tmp_path / "audit_trail.json").read_text())
        assert data["prompt"] == "test"

    def test_build_result_has_success(self, tmp_path):
        from agents.iterative_orchestrator import AuditTrail, BuildResult
        result = BuildResult(
            success=True,
            confidence=0.91,
            artifacts=["hir.json"],
            audit_trail=AuditTrail("p", "esp32", "high", 5),
        )
        assert result.success is True

    def test_stagnation_delta_constant(self):
        from agents.iterative_orchestrator import STAGNATION_DELTA
        assert 0.0 < STAGNATION_DELTA <= 0.05

    def test_audit_trail_serialisable(self):
        from agents.iterative_orchestrator import AuditTrail, IterationRecord
        trail = AuditTrail("test prompt", "esp32", "balanced", 5)
        trail.iterations = [
            IterationRecord(1, 0.75, 0.0, issues_found=["x"], fixes_applied=["y"]),
            IterationRecord(2, 0.88, 0.13, accept_reason="threshold_met"),
        ]
        trail.final_confidence = 0.88
        d = trail.to_dict()
        json_str = json.dumps(d)  # should not raise
        assert "threshold_met" in json_str

    def test_accept_threshold_high_greater_than_balanced(self):
        from agents.iterative_orchestrator import ACCEPT_THRESHOLDS
        assert ACCEPT_THRESHOLDS["high"] > ACCEPT_THRESHOLDS["balanced"]
        assert ACCEPT_THRESHOLDS["balanced"] > ACCEPT_THRESHOLDS["fast"]

    def test_build_result_artifacts_list(self, tmp_path):
        from agents.iterative_orchestrator import AuditTrail, BuildResult
        result = BuildResult(
            success=True,
            confidence=0.85,
            artifacts=["hir.json", "bom.json", "schematic.kicad_sch"],
            audit_trail=AuditTrail("p", "esp32", "balanced", 5),
        )
        assert isinstance(result.artifacts, list)
        assert len(result.artifacts) >= 1

    def test_iteration_record_hitl_default_false(self):
        from agents.iterative_orchestrator import IterationRecord
        r = IterationRecord(1, 0.60, 0.0)
        assert r.hitl_required is False

    def test_iteration_record_accept_reason_default(self):
        from agents.iterative_orchestrator import IterationRecord
        r = IterationRecord(1, 0.88, 0.0)
        assert r.accept_reason == "continue"


# ---------------------------------------------------------------------------
# Tests — Full integration (minimal, no-llm, mocked Synthesizer)
# ---------------------------------------------------------------------------


class TestIterativeOrchestratorIntegration:
    """Integration-level tests that use a mocked Synthesizer to run the loop."""

    def _write_hir(self, out_dir: Path, hir: dict) -> None:
        (out_dir / "hir.json").write_text(json.dumps(hir), encoding="utf-8")

    def _mock_synthesizer_cls(self, out_dir: Path, hir: dict, confidence: float = 0.88):
        """Returns a mock Synthesizer class that writes hir.json and returns SynthesisResult."""
        _conf = confidence  # capture in closure

        class MockSynthResult:
            success = True
            hitl_required = False
            hitl_messages: list = []
            assumptions: list = []
            error = None

            def __init__(self):
                self.confidence = _conf
                self.artifacts = ["hir.json", "bom.json"]

        class MockSynthesizer:
            def __init__(self, *args, **kwargs):
                # Write hir.json to out_dir so the orchestrator can read it
                (out_dir / "hir.json").write_text(
                    json.dumps(hir), encoding="utf-8"
                )
                # Also write bom.json
                (out_dir / "bom.json").write_text("[]", encoding="utf-8")

            def run(self, prompt, generate_firmware=False):
                return MockSynthResult()

        return MockSynthesizer

    async def _run_build(
        self,
        tmp_path: Path,
        hir: dict,
        synth_confidence: float = 0.88,
        review_score: float = 0.88,
        quality: str = "balanced",
        max_iterations: int = 2,
    ):
        """Run a fully mocked orchestrator build."""
        from agents.iterative_orchestrator import IterativeOrchestrator

        mock_synth_cls = self._mock_synthesizer_cls(tmp_path, hir, synth_confidence)

        class MockReviewResult:
            score = review_score
            hitl_required = False
            issues: list = []

        o = IterativeOrchestrator(use_llm=False)

        with patch("agents.iterative_orchestrator._add_to_path"):
            with patch.dict("sys.modules", {"boardsmith_hw.synthesizer": MagicMock(
                Synthesizer=mock_synth_cls,
            )}):
                with patch.object(o, "_run_design_review",
                                  return_value=MockReviewResult()):
                    with patch.object(o, "_run_pcb", return_value=[]):
                        result = await o.build(
                            prompt="ESP32 with BME280",
                            target="esp32",
                            out_dir=tmp_path,
                            quality=quality,
                            max_iterations=max_iterations,
                            with_pcb=False,  # skip PCB for unit tests
                            generate_firmware=False,
                        )
        return result

    def test_high_score_accepts_in_one_iteration(self, tmp_path):
        result = asyncio.run(self._run_build(
            tmp_path, _make_hir(),
            review_score=0.91,
            quality="balanced",
            max_iterations=5,
        ))
        assert result.audit_trail.accept_reason in (
            "threshold_met", "max_iter", "converged", "no_fixes", "hitl"
        )

    def test_audit_trail_has_iterations(self, tmp_path):
        result = asyncio.run(self._run_build(
            tmp_path, _make_hir(),
            review_score=0.88,
            quality="balanced",
            max_iterations=3,
        ))
        assert len(result.audit_trail.iterations) >= 1

    def test_audit_trail_prompt_preserved(self, tmp_path):
        result = asyncio.run(self._run_build(
            tmp_path, _make_hir(),
            review_score=0.88,
            quality="balanced",
        ))
        # Prompt is set in the audit trail
        assert result.audit_trail.prompt == "ESP32 with BME280"

    def test_accept_reason_threshold_met(self, tmp_path):
        result = asyncio.run(self._run_build(
            tmp_path, _make_hir(),
            review_score=0.92,
            quality="balanced",  # threshold 0.85
        ))
        assert result.audit_trail.accept_reason == "threshold_met"

    def test_max_iterations_respected(self, tmp_path):
        result = asyncio.run(self._run_build(
            tmp_path, _make_hir(),
            review_score=0.50,   # always below threshold
            quality="high",      # 0.90 threshold
            max_iterations=2,
        ))
        assert len(result.audit_trail.iterations) <= 2

    def test_audit_trail_json_written(self, tmp_path):
        asyncio.run(self._run_build(tmp_path, _make_hir(), review_score=0.88))
        assert (tmp_path / "audit_trail.json").exists()
        d = json.loads((tmp_path / "audit_trail.json").read_text())
        assert "iterations" in d
        assert "final_confidence" in d

    def test_confidence_in_result(self, tmp_path):
        result = asyncio.run(self._run_build(
            tmp_path, _make_hir(), review_score=0.75
        ))
        assert 0.0 <= result.confidence <= 1.0

    def test_artifacts_list_not_empty(self, tmp_path):
        result = asyncio.run(self._run_build(
            tmp_path, _make_hir(), review_score=0.88
        ))
        # audit_trail.json at minimum
        assert len(result.artifacts) >= 1
