# SPDX-License-Identifier: AGPL-3.0-or-later
"""TDD tests for RunERCTool — boardsmith_hw/agent/run_erc.py.

RED phase: tests written before implementation.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
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
# Stubs for kicad_drc types (allow tests to run without kicad-cli)
# ---------------------------------------------------------------------------

@dataclass
class StubDRCViolation:
    severity: str
    description: str
    rule_id: str = ""
    items: list[str] = field(default_factory=list)


@dataclass
class StubCheckResult:
    check_type: str
    passed: bool
    violations: list = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    error_messages: list = field(default_factory=list)
    tool_available: bool = True
    note: str = ""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRunERCToolAttributes:
    def test_name_is_run_erc(self):
        from boardsmith_hw.agent.run_erc import RunERCTool
        t = RunERCTool()
        assert t.name == "run_erc"

    def test_description_is_non_empty(self):
        from boardsmith_hw.agent.run_erc import RunERCTool
        t = RunERCTool()
        assert len(t.description) > 10

    def test_fixable_rule_ids_contains_pin_not_connected(self):
        from boardsmith_hw.agent.run_erc import _FIXABLE_RULE_IDS
        assert "pin_not_connected" in _FIXABLE_RULE_IDS

    def test_fixable_rule_ids_contains_power_pin_not_driven(self):
        from boardsmith_hw.agent.run_erc import _FIXABLE_RULE_IDS
        assert "power_pin_not_driven" in _FIXABLE_RULE_IDS

    def test_fixable_rule_ids_contains_pin_unconnected(self):
        from boardsmith_hw.agent.run_erc import _FIXABLE_RULE_IDS
        assert "pin_unconnected" in _FIXABLE_RULE_IDS

    def test_fixable_rule_ids_contains_missing_power_flag(self):
        from boardsmith_hw.agent.run_erc import _FIXABLE_RULE_IDS
        assert "missing_power_flag" in _FIXABLE_RULE_IDS


class TestFormatViolations:
    def test_format_pin_not_connected(self):
        from boardsmith_hw.agent.run_erc import _format_violations
        v = StubDRCViolation(
            severity="error",
            description="Pin not connected",
            rule_id="pin_not_connected",
            items=["R1.pin1", "R1.pin2", "R2.pin1", "R2.pin2"],  # 4 items — should be capped at 3
        )
        result_stub = StubCheckResult(
            check_type="erc", passed=False, violations=[v]
        )
        formatted = _format_violations(result_stub)
        assert len(formatted) == 1
        f = formatted[0]
        assert f["message"] == "Pin not connected"
        assert f["severity"] == "error"
        assert f["fixable"] is True
        assert f["rule_id"] == "pin_not_connected"
        assert len(f["items"]) == 3  # capped at 3

    def test_format_power_pin_not_driven(self):
        from boardsmith_hw.agent.run_erc import _format_violations
        v = StubDRCViolation(
            severity="error",
            description="Power pin not driven",
            rule_id="power_pin_not_driven",
        )
        result_stub = StubCheckResult(check_type="erc", passed=False, violations=[v])
        formatted = _format_violations(result_stub)
        assert formatted[0]["fixable"] is True

    def test_format_unknown_rule_id_not_fixable(self):
        from boardsmith_hw.agent.run_erc import _format_violations
        v = StubDRCViolation(
            severity="warning",
            description="Some unknown issue",
            rule_id="some_unknown_rule",
        )
        result_stub = StubCheckResult(check_type="erc", passed=True, violations=[v])
        formatted = _format_violations(result_stub)
        assert formatted[0]["fixable"] is False

    def test_format_empty_violations(self):
        from boardsmith_hw.agent.run_erc import _format_violations
        result_stub = StubCheckResult(check_type="erc", passed=True, violations=[])
        formatted = _format_violations(result_stub)
        assert formatted == []


class TestRunERCToolExecute:
    def test_execute_returns_tool_result_success(self):
        from boardsmith_hw.agent.run_erc import RunERCTool

        clean_result = StubCheckResult(
            check_type="erc",
            passed=True,
            violations=[],
            error_count=0,
            tool_available=True,
        )
        tool = RunERCTool()
        with patch("boardsmith_hw.kicad_drc.KiCadChecker") as MockChecker:
            instance = MockChecker.return_value
            instance.run_erc.return_value = clean_result
            result = run(tool.execute({"sch_path": "test.kicad_sch"}, make_ctx()))

        assert result.success is True
        assert isinstance(result.data["violations"], list)
        assert result.data["error_count"] == 0
        assert result.source == "kicad_cli_erc"

    def test_execute_confidence_zero_when_tool_unavailable(self):
        from boardsmith_hw.agent.run_erc import RunERCTool

        unavailable_result = StubCheckResult(
            check_type="erc",
            passed=True,
            violations=[],
            error_count=0,
            tool_available=False,
            note="kicad-cli not installed",
        )
        tool = RunERCTool()
        with patch("boardsmith_hw.kicad_drc.KiCadChecker") as MockChecker:
            instance = MockChecker.return_value
            instance.run_erc.return_value = unavailable_result
            result = run(tool.execute({"sch_path": "test.kicad_sch"}, make_ctx()))

        assert result.confidence == 0.0

    def test_execute_violations_always_a_list(self):
        from boardsmith_hw.agent.run_erc import RunERCTool

        result_with_violations = StubCheckResult(
            check_type="erc",
            passed=False,
            violations=[
                StubDRCViolation("error", "Pin X not connected", "pin_not_connected", ["U1.1"]),
            ],
            error_count=1,
            tool_available=True,
        )
        tool = RunERCTool()
        with patch("boardsmith_hw.kicad_drc.KiCadChecker") as MockChecker:
            instance = MockChecker.return_value
            instance.run_erc.return_value = result_with_violations
            result = run(tool.execute({"sch_path": "test.kicad_sch"}, make_ctx()))

        assert isinstance(result.data["violations"], list)
        assert len(result.data["violations"]) == 1
        assert result.data["violations"][0]["fixable"] is True

    def test_no_llm_imports_at_module_level(self):
        """Confirm no anthropic/openai imports at module level."""
        import importlib, sys
        # Remove cached module if present
        for mod in list(sys.modules.keys()):
            if "boardsmith_hw.agent" in mod:
                del sys.modules[mod]

        import boardsmith_hw.agent.run_erc as m
        import inspect
        src = inspect.getsource(m)
        # Top-level imports are at col 0
        top_level_lines = [l for l in src.splitlines() if l.startswith("import ") or l.startswith("from ")]
        for line in top_level_lines:
            assert "anthropic" not in line, f"anthropic imported at top level: {line}"
            assert "openai" not in line, f"openai imported at top level: {line}"


class TestAgentPackageInit:
    def test_init_has_no_imports(self):
        """boardsmith_hw/agent/__init__.py must have no import statements."""
        init_path = Path(__file__).parent.parent / "boardsmith_hw" / "agent" / "__init__.py"
        content = init_path.read_text()
        lines = [l for l in content.splitlines() if l.startswith("import ") or l.startswith("from ")]
        assert lines == [], f"Unexpected imports in __init__.py: {lines}"
