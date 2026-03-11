# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for RunERCTool."""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler"):
    _p = str(REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

FIXTURES = Path(__file__).parent / "fixtures"


def _make_mock_context():
    ctx = MagicMock()
    ctx.no_llm = False
    return ctx


def _run(coro):
    return asyncio.run(coro)


def _make_check_result(violations=None, tool_available=True):
    """Build a CheckResult from boardsmith_hw.kicad_drc."""
    from boardsmith_hw.kicad_drc import CheckResult, DRCViolation
    viols = violations or []
    return CheckResult(
        check_type="erc",
        passed=not any(v.severity == "error" for v in viols),
        violations=viols,
        error_count=sum(1 for v in viols if v.severity == "error"),
        warning_count=sum(1 for v in viols if v.severity == "warning"),
        error_messages=[v.description for v in viols],
        tool_available=tool_available,
    )


class TestRunERCToolStructuredOutput:
    def test_returns_violations_list(self):
        from boardsmith_hw.agent.run_erc import RunERCTool
        from boardsmith_hw.kicad_drc import DRCViolation
        tool = RunERCTool()
        violation = DRCViolation(
            severity="error",
            description="Pin unconnected",
            rule_id="pin_not_connected",
            items=["Pin PA1 of U1 @ (100, 50)"],
        )
        mock_result = _make_check_result([violation])
        with patch("boardsmith_hw.kicad_drc.KiCadChecker.run_erc", return_value=mock_result):
            result = _run(tool.execute({"sch_path": "fake.kicad_sch"}, _make_mock_context()))
        assert result.success is True
        assert "violations" in result.data
        assert isinstance(result.data["violations"], list)
        assert len(result.data["violations"]) == 1

    def test_violation_has_required_keys(self):
        from boardsmith_hw.agent.run_erc import RunERCTool
        from boardsmith_hw.kicad_drc import DRCViolation
        tool = RunERCTool()
        violation = DRCViolation(severity="error", description="Pin unconnected",
                                 rule_id="pin_not_connected")
        mock_result = _make_check_result([violation])
        with patch("boardsmith_hw.kicad_drc.KiCadChecker.run_erc", return_value=mock_result):
            result = _run(tool.execute({"sch_path": "fake.kicad_sch"}, _make_mock_context()))
        v = result.data["violations"][0]
        for key in ("message", "severity", "fixable"):
            assert key in v, f"Missing key: {key}"

    def test_no_raw_kicad_text_in_output(self):
        from boardsmith_hw.agent.run_erc import RunERCTool
        from boardsmith_hw.kicad_drc import DRCViolation
        tool = RunERCTool()
        violation = DRCViolation(severity="error", description="Pin unconnected",
                                 rule_id="pin_not_connected")
        mock_result = _make_check_result([violation])
        with patch("boardsmith_hw.kicad_drc.KiCadChecker.run_erc", return_value=mock_result):
            result = _run(tool.execute({"sch_path": "fake.kicad_sch"}, _make_mock_context()))
        output_str = json.dumps(result.data)
        assert "(kicad_sch" not in output_str
        assert "kicad-cli" not in output_str

    def test_clean_erc_returns_empty_violations(self):
        from boardsmith_hw.agent.run_erc import RunERCTool
        tool = RunERCTool()
        mock_result = _make_check_result([])
        with patch("boardsmith_hw.kicad_drc.KiCadChecker.run_erc", return_value=mock_result):
            result = _run(tool.execute({"sch_path": "fake.kicad_sch"}, _make_mock_context()))
        assert result.success is True
        assert result.data["violations"] == []
        assert result.data["error_count"] == 0

    def test_tool_unavailable_gives_zero_confidence(self):
        from boardsmith_hw.agent.run_erc import RunERCTool
        tool = RunERCTool()
        mock_result = _make_check_result([], tool_available=False)
        with patch("boardsmith_hw.kicad_drc.KiCadChecker.run_erc", return_value=mock_result):
            result = _run(tool.execute({"sch_path": "fake.kicad_sch"}, _make_mock_context()))
        assert result.confidence == 0.0


class TestRunERCToolFixableClassification:
    def _run_with_rule(self, rule_id: str):
        from boardsmith_hw.agent.run_erc import RunERCTool
        from boardsmith_hw.kicad_drc import DRCViolation
        tool = RunERCTool()
        violation = DRCViolation(severity="error", description="Test", rule_id=rule_id)
        mock_result = _make_check_result([violation])
        with patch("boardsmith_hw.kicad_drc.KiCadChecker.run_erc", return_value=mock_result):
            result = _run(tool.execute({"sch_path": "fake.kicad_sch"}, _make_mock_context()))
        return result.data["violations"][0]["fixable"]

    def test_pin_not_connected_is_fixable(self):
        assert self._run_with_rule("pin_not_connected") is True

    def test_pin_unconnected_is_fixable(self):
        assert self._run_with_rule("pin_unconnected") is True

    def test_power_pin_not_driven_is_fixable(self):
        assert self._run_with_rule("power_pin_not_driven") is True

    def test_missing_power_flag_is_fixable(self):
        assert self._run_with_rule("missing_power_flag") is True

    def test_unknown_rule_is_not_fixable(self):
        assert self._run_with_rule("net_conflict") is False

    def test_items_capped_at_3(self):
        from boardsmith_hw.agent.run_erc import RunERCTool
        from boardsmith_hw.kicad_drc import DRCViolation
        tool = RunERCTool()
        violation = DRCViolation(
            severity="error", description="Test", rule_id="pin_not_connected",
            items=["item1", "item2", "item3", "item4", "item5"],
        )
        mock_result = _make_check_result([violation])
        with patch("boardsmith_hw.kicad_drc.KiCadChecker.run_erc", return_value=mock_result):
            result = _run(tool.execute({"sch_path": "fake.kicad_sch"}, _make_mock_context()))
        assert len(result.data["violations"][0]["items"]) <= 3


class TestRunERCToolKiCadVersionFixtures:
    """Test _parse_report() against real fixture JSON for each KiCad version."""

    def _parse_fixture(self, fixture_name: str):
        from boardsmith_hw.kicad_drc import KiCadChecker
        fixture_path = FIXTURES / fixture_name
        checker = KiCadChecker()
        return checker._parse_report("erc", fixture_path)

    def test_kicad7_fixture_parses(self):
        result = self._parse_fixture("erc_kicad7.json")
        assert result.check_type == "erc"
        assert isinstance(result.violations, list)
        assert len(result.violations) == 1
        assert result.violations[0].rule_id == "pin_not_connected"

    def test_kicad8_fixture_parses(self):
        result = self._parse_fixture("erc_kicad8.json")
        assert result.check_type == "erc"
        assert isinstance(result.violations, list)
        assert len(result.violations) == 1
        assert result.violations[0].rule_id == "power_pin_not_driven"

    def test_kicad9_fixture_parses(self):
        result = self._parse_fixture("erc_kicad9.json")
        assert result.check_type == "erc"
        assert isinstance(result.violations, list)
        # rule_id must be non-empty — defensive parsing handles both "type" and "rule_id"
        assert result.violations[0].rule_id != ""

    def test_clean_fixture_passes(self):
        result = self._parse_fixture("erc_clean.json")
        assert result.passed is True
        assert result.violations == []

    def test_violations_fixture_has_3_violations(self):
        result = self._parse_fixture("erc_with_violations.json")
        assert len(result.violations) == 3
