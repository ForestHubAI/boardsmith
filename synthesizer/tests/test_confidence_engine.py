# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Boardsmith confidence engine."""
import pytest
from synth_core.hir_bridge.validator import DiagnosticsReport
from boardsmith_hw.confidence_engine import ConfidenceEngine, ConfidenceResult


def _empty_report() -> DiagnosticsReport:
    return DiagnosticsReport(constraints=[])


def test_high_confidence_auto_proceed():
    engine = ConfidenceEngine()
    result = engine.compute(
        intent_confidence=0.95,
        component_confidence=0.92,
        topology_confidence=0.90,
        validation_report=_empty_report(),
        assumptions=[],
    )
    assert result.overall >= ConfidenceResult.AUTO_PROCEED_THRESHOLD
    assert not result.hitl_required


def test_low_confidence_triggers_hitl():
    engine = ConfidenceEngine()
    result = engine.compute(
        intent_confidence=0.3,
        component_confidence=0.4,
        topology_confidence=0.5,
        validation_report=_empty_report(),
        assumptions=["Unresolved issue 1", "Unresolved issue 2"],
    )
    assert result.hitl_required
    assert len(result.hitl_messages) >= 1


def test_error_constraints_reduce_electrical_confidence():
    from synth_core.models.hir import Constraint, ConstraintCategory, Severity, ConstraintStatus, Provenance, SourceType
    prov = Provenance(source_type=SourceType.inference, confidence=1.0)
    err = Constraint(
        id="test.err",
        category=ConstraintCategory.electrical,
        description="Test error",
        severity=Severity.error,
        status=ConstraintStatus.fail,
        provenance=prov,
    )
    report = DiagnosticsReport(constraints=[err])
    engine = ConfidenceEngine()
    result = engine.compute(
        intent_confidence=0.9,
        component_confidence=0.9,
        topology_confidence=0.9,
        validation_report=report,
        assumptions=[],
    )
    assert result.subscores["electrical"] == 0.0
    assert result.hitl_required


def test_subscores_present():
    engine = ConfidenceEngine()
    result = engine.compute(0.8, 0.8, 0.8, _empty_report(), [])
    assert "intent" in result.subscores
    assert "components" in result.subscores
    assert "topology" in result.subscores
    assert "electrical" in result.subscores


def test_overall_bounded():
    engine = ConfidenceEngine()
    result = engine.compute(1.0, 1.0, 1.0, _empty_report(), [])
    assert 0.0 <= result.overall <= 1.0
