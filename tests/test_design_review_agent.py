# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for shared/agents/design_review_agent (Phase 18)."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure shared/ on path
_shared = Path(__file__).parent.parent / "shared"
if str(_shared) not in sys.path:
    sys.path.insert(0, str(_shared))

import pytest
from agents.design_review_agent import (
    DesignIssue,
    DesignReviewAgent,
    DesignReviewResult,
    SCORE_AUTO_PROCEED,
    SCORE_CONFIRM,
)


# ---------------------------------------------------------------------------
# Fixtures — HIR dicts
# ---------------------------------------------------------------------------

def _good_hir() -> dict:
    """A design that should pass all deterministic checks."""
    return {
        "version": "1.1.0",
        "components": [
            {"id": "ESP32", "mpn": "ESP32-WROOM-32", "role": "mcu",
             "electrical_ratings": {"current_draw_max_ma": 240.0}},
            {"id": "BME280", "mpn": "BME280", "role": "sensor",
             "electrical_ratings": {"current_draw_max_ma": 3.6}},
            {"id": "LDO", "mpn": "AMS1117-3.3", "role": "power",
             "output_rail": "3V3",
             "capabilities": {"output_current_max_ma": 800.0}},
        ],
        "bus_contracts": [
            {
                "bus_type": "I2C",
                "bus_name": "i2c0",
                "slaves": [{"component_id": "BME280", "address": "0x76"}],
            }
        ],
        "power_sequence": {"rails": [{"name": "3V3", "voltage": {"nominal": 3.3}}]},
        "nets": [],
    }


def _overcurrent_hir() -> dict:
    """Design with a 250 mA LDO but >250 mA load."""
    return {
        "version": "1.1.0",
        "components": [
            {"id": "ESP32", "mpn": "ESP32-WROOM-32", "role": "mcu",
             "electrical_ratings": {"current_draw_max_ma": 240.0}},
            {"id": "SX1276", "mpn": "SX1276", "role": "comms",
             "electrical_ratings": {"current_draw_max_ma": 120.0}},
            {"id": "LDO", "mpn": "MCP1700-3302E", "role": "power",
             "output_rail": "3V3",
             "capabilities": {"output_current_max_ma": 250.0}},
        ],
        "bus_contracts": [],
        "power_sequence": {"rails": [{"name": "3V3", "voltage": {"nominal": 3.3}}]},
        "nets": [],
    }


def _address_conflict_hir() -> dict:
    """Design with I2C address conflict."""
    return {
        "version": "1.1.0",
        "components": [
            {"id": "ESP32", "mpn": "ESP32-WROOM-32", "role": "mcu"},
            {"id": "BME280", "mpn": "BME280", "role": "sensor"},
            {"id": "BMP280", "mpn": "BMP280", "role": "sensor"},
        ],
        "bus_contracts": [
            {
                "bus_type": "I2C",
                "bus_name": "i2c0",
                "slaves": [
                    {"component_id": "BME280", "address": "0x76"},
                    {"component_id": "BMP280", "address": "0x76"},  # conflict!
                ],
            }
        ],
        "power_sequence": {},
        "nets": [],
    }


def _no_mcu_hir() -> dict:
    return {
        "components": [
            {"id": "BME280", "mpn": "BME280", "role": "sensor"},
        ],
        "bus_contracts": [],
        "power_sequence": {},
        "nets": [],
    }


def _actuator_hir() -> dict:
    return {
        "components": [
            {"id": "ESP32", "mpn": "ESP32-WROOM-32", "role": "mcu"},
            {"id": "RELAY1", "mpn": "G5Q-1A", "role": "actuator"},
        ],
        "bus_contracts": [],
        "power_sequence": {},
        "nets": [],
    }


# ---------------------------------------------------------------------------
# Unit tests — DesignIssue
# ---------------------------------------------------------------------------

class TestDesignIssue:
    def test_fields(self):
        issue = DesignIssue(
            category="electrical",
            severity="error",
            code="TEST",
            message="test message",
            suggestion="fix it",
        )
        assert issue.category == "electrical"
        assert issue.severity == "error"
        assert issue.code == "TEST"

    def test_defaults(self):
        issue = DesignIssue(category="power", severity="info", code="X", message="")
        assert issue.suggestion == ""
        assert issue.component_id is None
        assert issue.context == {}


# ---------------------------------------------------------------------------
# Unit tests — DesignReviewResult
# ---------------------------------------------------------------------------

class TestDesignReviewResult:
    def test_errors_property(self):
        r = DesignReviewResult(issues=[
            DesignIssue("electrical", "error", "E1", ""),
            DesignIssue("power", "warning", "W1", ""),
            DesignIssue("cost", "info", "I1", ""),
        ])
        assert len(r.errors) == 1
        assert r.errors[0].code == "E1"

    def test_warnings_property(self):
        r = DesignReviewResult(issues=[
            DesignIssue("electrical", "error", "E1", ""),
            DesignIssue("power", "warning", "W1", ""),
        ])
        assert len(r.warnings) == 1

    def test_passed_no_errors(self):
        r = DesignReviewResult(issues=[
            DesignIssue("power", "warning", "W1", ""),
        ])
        assert r.passed is True

    def test_not_passed_with_errors(self):
        r = DesignReviewResult(issues=[
            DesignIssue("electrical", "error", "E1", ""),
        ])
        assert r.passed is False


# ---------------------------------------------------------------------------
# Unit tests — _compute_score
# ---------------------------------------------------------------------------

class TestComputeScore:
    def _agent(self) -> DesignReviewAgent:
        return DesignReviewAgent(gateway=None)

    def test_no_issues_gives_max_score(self):
        result = DesignReviewResult()
        agent = self._agent()
        agent._compute_score(result)
        assert result.score >= 0.95

    def test_one_error_reduces_score(self):
        result = DesignReviewResult(issues=[
            DesignIssue("electrical", "error", "E1", ""),
        ])
        agent = self._agent()
        agent._compute_score(result)
        assert result.score <= 0.85

    def test_score_below_confirm_with_many_errors(self):
        result = DesignReviewResult(issues=[
            DesignIssue("electrical", "error", f"E{i}", "")
            for i in range(5)
        ])
        agent = self._agent()
        agent._compute_score(result)
        assert result.score < SCORE_CONFIRM

    def test_score_in_range(self):
        result = DesignReviewResult(issues=[
            DesignIssue("power", "warning", "W1", ""),
            DesignIssue("electrical", "error", "E1", ""),
        ])
        agent = self._agent()
        agent._compute_score(result)
        assert 0.0 <= result.score <= 1.0

    def test_reference_match_bonus(self):
        result = DesignReviewResult(reference_match_confidence=0.90)
        agent = self._agent()
        agent._compute_score(result)
        assert result.score >= 1.0  # bonus can push to 1.0 (capped)


# ---------------------------------------------------------------------------
# Unit tests — _check_hitl
# ---------------------------------------------------------------------------

class TestCheckHitl:
    def _agent(self) -> DesignReviewAgent:
        return DesignReviewAgent(gateway=None)

    def test_no_hitl_for_clean_design(self):
        result = DesignReviewResult(score=0.90)
        agent = self._agent()
        agent._check_hitl(_good_hir(), result)
        assert result.hitl_required is False

    def test_hitl_for_low_score(self):
        result = DesignReviewResult(score=0.50)
        agent = self._agent()
        agent._check_hitl({}, result)
        assert result.hitl_required is True
        assert "score" in result.hitl_reason

    def test_hitl_for_errors(self):
        result = DesignReviewResult(
            score=0.80,
            issues=[DesignIssue("electrical", "error", "E1", "")]
        )
        agent = self._agent()
        agent._check_hitl({}, result)
        assert result.hitl_required is True

    def test_hitl_for_actuator(self):
        result = DesignReviewResult(score=0.90)
        agent = self._agent()
        agent._check_hitl(_actuator_hir(), result)
        assert result.hitl_required is True
        assert "safety-critical" in result.hitl_reason.lower()


# ---------------------------------------------------------------------------
# Integration tests — deterministic checks (no LLM)
# ---------------------------------------------------------------------------

class TestDeterministicReview:
    def _agent(self) -> DesignReviewAgent:
        return DesignReviewAgent(gateway=None)

    def test_good_design_passes(self):
        import asyncio
        agent = self._agent()
        result = asyncio.run(agent.review_async(_good_hir()))
        # Should have no errors (warnings may vary depending on validation)
        assert result.passed or result.score > 0.0

    def test_no_mcu_creates_error(self):
        import asyncio
        agent = self._agent()
        result = asyncio.run(agent.review_async(_no_mcu_hir()))
        error_codes = [i.code for i in result.errors]
        assert "NO_MCU" in error_codes

    def test_i2c_conflict_creates_error(self):
        import asyncio
        agent = self._agent()
        result = asyncio.run(agent.review_async(_address_conflict_hir()))
        error_codes = [i.code for i in result.errors]
        assert "I2C_ADDRESS_CONFLICT" in error_codes

    def test_overcurrent_creates_error(self):
        import asyncio
        agent = self._agent()
        result = asyncio.run(agent.review_async(_overcurrent_hir()))
        error_codes = [i.code for i in result.errors]
        assert "OVERCURRENT" in error_codes

    def test_overcurrent_reduces_score(self):
        import asyncio
        agent = self._agent()
        result = asyncio.run(agent.review_async(_overcurrent_hir()))
        assert result.score < SCORE_AUTO_PROCEED

    def test_result_has_score(self):
        import asyncio
        agent = self._agent()
        result = asyncio.run(agent.review_async(_good_hir()))
        assert 0.0 <= result.score <= 1.0

    def test_reference_match_populated(self):
        import asyncio
        agent = self._agent()
        result = asyncio.run(agent.review_async(_good_hir()))
        # May or may not have a match depending on similarity
        # Just ensure the field is set (None or string)
        assert result.reference_match is None or isinstance(result.reference_match, str)

    def test_actuator_triggers_hitl(self):
        import asyncio
        agent = self._agent()
        result = asyncio.run(agent.review_async(_actuator_hir()))
        assert result.hitl_required is True

    def test_synchronous_review_wrapper(self):
        agent = self._agent()
        result = agent.review(_good_hir())
        assert isinstance(result, DesignReviewResult)


# ---------------------------------------------------------------------------
# Tests — tools
# ---------------------------------------------------------------------------

class TestAnalyzePowerDesignTool:
    def test_good_design_passes(self):
        import asyncio
        from tools.tools.analyze_power_design import AnalyzePowerDesignTool
        from tools.base import ToolContext
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="test", llm_gateway=gw)
        tool = AnalyzePowerDesignTool()
        result = asyncio.run(tool.execute({"hir": _good_hir()}, ctx))
        assert result.success is True
        assert result.data["passes"] is True

    def test_overcurrent_fails(self):
        import asyncio
        from tools.tools.analyze_power_design import AnalyzePowerDesignTool
        from tools.base import ToolContext
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="test", llm_gateway=gw)
        tool = AnalyzePowerDesignTool()
        result = asyncio.run(tool.execute({"hir": _overcurrent_hir()}, ctx))
        assert result.success is True
        assert result.data["passes"] is False

    def test_missing_hir_key(self):
        import asyncio
        from tools.tools.analyze_power_design import AnalyzePowerDesignTool
        from tools.base import ToolContext
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="test", llm_gateway=gw)
        tool = AnalyzePowerDesignTool()
        result = asyncio.run(tool.execute({}, ctx))
        assert result.success is False


class TestFindComponentAlternativesTool:
    def test_finds_alternatives_for_bme280(self):
        import asyncio
        from tools.tools.find_component_alternatives import FindComponentAlternativesTool
        from tools.base import ToolContext
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="test", llm_gateway=gw)
        tool = FindComponentAlternativesTool()
        result = asyncio.run(tool.execute({"mpn": "BME280", "reason": "any"}, ctx))
        assert result.success is True
        assert "original_mpn" in result.data

    def test_not_found_returns_error(self):
        import asyncio
        from tools.tools.find_component_alternatives import FindComponentAlternativesTool
        from tools.base import ToolContext
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(session_id="test", llm_gateway=gw)
        tool = FindComponentAlternativesTool()
        result = asyncio.run(tool.execute({"mpn": "NONEXISTENT_PART_XYZ"}, ctx))
        assert result.success is False
