# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for shared/llm/ — LLMGateway, Config, CostTracker, Router, Types.

All tests work without any API keys (use --no-llm / no-op mode).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

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
# TaskType + Message + LLMResponse
# ---------------------------------------------------------------------------

class TestTypes:
    def test_task_type_values(self):
        from llm.types import TaskType
        assert TaskType.INTENT_PARSE == "intent_parse"
        assert TaskType.COMPONENT_SUGGEST == "component_suggest"
        assert TaskType.TOPOLOGY_SUGGEST == "topology_suggest"
        assert TaskType.CONSTRAINT_FIX == "constraint_fix"
        assert TaskType.LAYOUT_PLAN == "layout_plan"
        assert TaskType.CODE_GEN == "code_gen"
        assert TaskType.DATASHEET_EXTRACT == "datasheet_extract"
        assert TaskType.AGENT_REASONING == "agent_reasoning"

    def test_message_creation(self):
        from llm.types import Message
        m = Message(role="user", content="hello")
        assert m.role == "user"
        assert m.content == "hello"

    def test_llm_response_total_tokens(self):
        from llm.types import LLMResponse
        r = LLMResponse(
            content="hi", model="claude", provider="anthropic",
            input_tokens=100, output_tokens=50,
        )
        assert r.total_tokens == 150

    def test_llm_response_skipped_default_false(self):
        from llm.types import LLMResponse
        r = LLMResponse(content="x", model="m", provider="p")
        assert r.skipped is False

    def test_llm_response_skipped_true(self):
        from llm.types import LLMResponse
        r = LLMResponse(content="", model="", provider="", skipped=True)
        assert r.skipped is True
        assert r.total_tokens == 0

    def test_cost_summary_creation(self):
        from llm.types import CostSummary
        s = CostSummary(total_usd=0.05, total_tokens=1000, total_calls=3)
        assert s.total_usd == 0.05
        assert s.total_tokens == 1000
        assert s.total_calls == 3
        assert s.calls_by_task == {}


# ---------------------------------------------------------------------------
# LLMConfig
# ---------------------------------------------------------------------------

class TestLLMConfig:
    def test_no_llm_mode_factory(self):
        from llm.config import LLMConfig
        cfg = LLMConfig.no_llm_mode()
        assert cfg.no_llm is True
        assert cfg.anthropic_api_key == ""

    def test_from_env_no_keys_set(self):
        from llm.config import LLMConfig
        env = {k: v for k, v in os.environ.items()
               if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY",
                             "BOARDSMITH_NO_LLM", "BOARDSMITH_BUDGET_USD")}
        # Temporarily clear relevant keys
        saved = {k: os.environ.pop(k, None)
                 for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY",
                            "BOARDSMITH_NO_LLM", "BOARDSMITH_BUDGET_USD")}
        try:
            cfg = LLMConfig.from_env()
            assert cfg.no_llm is False
            assert cfg.budget_limit_usd is None
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_from_env_no_llm_flag(self):
        from llm.config import LLMConfig
        os.environ["BOARDSMITH_NO_LLM"] = "true"
        try:
            cfg = LLMConfig.from_env()
            assert cfg.no_llm is True
        finally:
            del os.environ["BOARDSMITH_NO_LLM"]

    def test_from_env_no_llm_numeric(self):
        from llm.config import LLMConfig
        os.environ["BOARDSMITH_NO_LLM"] = "1"
        try:
            assert LLMConfig.from_env().no_llm is True
        finally:
            del os.environ["BOARDSMITH_NO_LLM"]

    def test_from_env_budget(self):
        from llm.config import LLMConfig
        os.environ["BOARDSMITH_BUDGET_USD"] = "2.50"
        try:
            cfg = LLMConfig.from_env()
            assert cfg.budget_limit_usd == pytest.approx(2.50)
        finally:
            del os.environ["BOARDSMITH_BUDGET_USD"]

    def test_from_env_bad_budget_ignored(self):
        from llm.config import LLMConfig
        os.environ["BOARDSMITH_BUDGET_USD"] = "not_a_number"
        try:
            cfg = LLMConfig.from_env()
            assert cfg.budget_limit_usd is None
        finally:
            del os.environ["BOARDSMITH_BUDGET_USD"]

    def test_has_anthropic_true(self):
        from llm.config import LLMConfig
        cfg = LLMConfig(anthropic_api_key="sk-ant-test")
        assert cfg.has_anthropic() is True

    def test_has_anthropic_false(self):
        from llm.config import LLMConfig
        cfg = LLMConfig(anthropic_api_key="")
        assert cfg.has_anthropic() is False

    def test_has_openai(self):
        from llm.config import LLMConfig
        assert LLMConfig(openai_api_key="sk-test").has_openai() is True
        assert LLMConfig(openai_api_key="").has_openai() is False

    def test_has_ollama_default_true(self):
        from llm.config import LLMConfig
        cfg = LLMConfig()
        assert cfg.has_ollama() is True   # default URL is set

    def test_from_toml_basic(self, tmp_path):
        """Config loads from a TOML file."""
        from llm.config import LLMConfig
        toml_file = tmp_path / "llm.toml"
        toml_file.write_text(
            '[llm]\nanthopic_api_key = ""\nno_llm = true\nbudget_limit_usd = 0.5\n',
            encoding="utf-8",
        )
        cfg = LLMConfig.from_toml(toml_file)
        # budget_limit_usd should be read from TOML
        assert cfg.budget_limit_usd == pytest.approx(0.5)

    def test_env_overrides_toml(self, tmp_path):
        """Env var wins over TOML file value."""
        from llm.config import LLMConfig
        toml_file = tmp_path / "llm.toml"
        toml_file.write_text("[llm]\nno_llm = false\n", encoding="utf-8")
        os.environ["BOARDSMITH_NO_LLM"] = "true"
        try:
            cfg = LLMConfig.from_env(config_path=toml_file)
            assert cfg.no_llm is True
        finally:
            del os.environ["BOARDSMITH_NO_LLM"]

    def test_toml_models_section(self, tmp_path):
        """[llm.models] section is loaded into default_models."""
        from llm.config import LLMConfig
        toml_file = tmp_path / "llm.toml"
        toml_file.write_text(
            '[llm.models]\nintent_parse = "claude-haiku-4-5-20251001"\n',
            encoding="utf-8",
        )
        cfg = LLMConfig.from_env(config_path=toml_file)
        assert cfg.default_models.get("intent_parse") == "claude-haiku-4-5-20251001"

    def test_missing_toml_file_ignored(self, tmp_path):
        """Missing TOML file → defaults used, no error."""
        from llm.config import LLMConfig
        cfg = LLMConfig.from_env(config_path=tmp_path / "nonexistent.toml")
        assert cfg.no_llm is False


# ---------------------------------------------------------------------------
# CostTracker + estimate_cost
# ---------------------------------------------------------------------------

class TestCostTracker:
    def test_estimate_cost_haiku(self):
        from llm.cost_tracker import estimate_cost
        # claude-haiku: $0.80/1M input, $4.00/1M output
        cost = estimate_cost("claude-haiku-4-5-20251001", 1_000_000, 0)
        assert cost == pytest.approx(0.80)

    def test_estimate_cost_sonnet_output(self):
        from llm.cost_tracker import estimate_cost
        cost = estimate_cost("claude-sonnet-4-5", 0, 1_000_000)
        assert cost == pytest.approx(15.00)

    def test_estimate_cost_unknown_model(self):
        from llm.cost_tracker import estimate_cost
        cost = estimate_cost("unknown-model-xyz", 1_000_000, 0)
        assert cost > 0   # uses default fallback

    def test_estimate_cost_ollama_free(self):
        from llm.cost_tracker import estimate_cost
        cost = estimate_cost("ollama", 100_000, 100_000)
        assert cost == pytest.approx(0.0)

    def test_tracker_log_and_total(self):
        from llm.cost_tracker import CostTracker
        t = CostTracker()
        t.log("intent_parse", "anthropic", "claude-haiku-4-5-20251001", 1000, 200)
        assert t.total_tokens() == 1200
        assert t.total_usd() > 0

    def test_tracker_empty(self):
        from llm.cost_tracker import CostTracker
        t = CostTracker()
        assert t.total_usd() == 0.0
        assert t.total_tokens() == 0
        assert t.is_over_budget(0.01) is False

    def test_tracker_over_budget(self):
        from llm.cost_tracker import CostTracker
        t = CostTracker()
        t.log("test", "anthropic", "gpt-4o", 100_000, 100_000)
        assert t.is_over_budget(0.001) is True

    def test_tracker_summary_structure(self):
        from llm.cost_tracker import CostTracker
        t = CostTracker()
        t.log("intent_parse", "anthropic", "claude-haiku-4-5-20251001", 500, 100)
        t.log("code_gen", "openai", "gpt-4o", 800, 200)
        s = t.get_summary()
        assert s.total_calls == 2
        assert "intent_parse" in s.calls_by_task
        assert "code_gen" in s.calls_by_task
        assert "anthropic" in s.calls_by_provider
        assert "openai" in s.calls_by_provider

    def test_format_summary_no_calls(self):
        from llm.cost_tracker import CostTracker
        t = CostTracker()
        fmt = t.format_summary()
        assert "keine" in fmt.lower() or "0" in fmt

    def test_format_summary_with_calls(self):
        from llm.cost_tracker import CostTracker
        t = CostTracker()
        t.log("test", "anthropic", "claude-haiku-4-5-20251001", 100, 50)
        fmt = t.format_summary()
        assert "anthropic" in fmt
        assert "1" in fmt  # 1 call


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class TestRouter:
    def test_chain_for_intent_parse(self):
        from llm.router import get_provider_chain
        from llm.types import TaskType
        chain = get_provider_chain(TaskType.INTENT_PARSE)
        assert len(chain) >= 2
        providers = [p for p, _ in chain]
        assert "anthropic" in providers

    def test_chain_for_code_gen_prefers_openai(self):
        from llm.router import get_provider_chain
        from llm.types import TaskType
        chain = get_provider_chain(TaskType.CODE_GEN)
        # CODE_GEN should prefer GPT-4o (first entry)
        assert chain[0][0] == "openai"

    def test_chain_for_agent_reasoning_has_ollama(self):
        from llm.router import get_provider_chain
        from llm.types import TaskType
        chain = get_provider_chain(TaskType.AGENT_REASONING)
        providers = [p for p, _ in chain]
        assert "ollama" in providers

    def test_unknown_task_returns_default(self):
        from llm.router import get_provider_chain
        chain = get_provider_chain("some_unknown_task")
        assert len(chain) >= 1

    def test_all_task_types_have_chain(self):
        from llm.router import get_provider_chain
        from llm.types import TaskType
        for task in TaskType:
            chain = get_provider_chain(task)
            assert len(chain) >= 1, f"No chain for {task}"


# ---------------------------------------------------------------------------
# LLMGateway — no-llm mode (no API keys needed)
# ---------------------------------------------------------------------------

class TestLLMGatewayNoLLM:
    def _make_gateway(self):
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        return LLMGateway(LLMConfig.no_llm_mode())

    def test_complete_sync_returns_skipped(self):
        from llm.types import Message, TaskType
        gw = self._make_gateway()
        resp = gw.complete_sync(
            task=TaskType.INTENT_PARSE,
            messages=[Message(role="user", content="test")],
        )
        assert resp.skipped is True
        assert resp.content == ""

    def test_is_llm_available_false(self):
        gw = self._make_gateway()
        assert gw.is_llm_available() is False

    def test_cost_summary_empty_in_no_llm(self):
        gw = self._make_gateway()
        s = gw.get_cost_summary()
        assert s.total_calls == 0
        assert s.total_usd == 0.0

    def test_format_cost_summary(self):
        gw = self._make_gateway()
        fmt = gw.format_cost_summary()
        assert isinstance(fmt, str)

    def test_budget_exceeded_skips(self):
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from llm.types import Message, TaskType
        # No-llm mode + budget — should still skip (no_llm takes priority)
        cfg = LLMConfig(no_llm=True, budget_limit_usd=0.00)
        gw = LLMGateway(cfg)
        resp = gw.complete_sync(
            task=TaskType.INTENT_PARSE,
            messages=[Message(role="user", content="test")],
        )
        assert resp.skipped is True

    def test_complete_sync_with_string_task(self):
        from llm.types import Message
        gw = self._make_gateway()
        resp = gw.complete_sync(
            task="intent_parse",
            messages=[Message(role="user", content="ping")],
        )
        assert resp.skipped is True


class TestLLMGatewayDefaultSingleton:
    def test_get_default_gateway_returns_instance(self):
        from llm.gateway import LLMGateway, get_default_gateway, reset_default_gateway
        reset_default_gateway(None)
        gw = get_default_gateway()
        assert isinstance(gw, LLMGateway)

    def test_reset_creates_new_instance(self):
        from llm.config import LLMConfig
        from llm.gateway import get_default_gateway, reset_default_gateway
        gw1 = get_default_gateway()
        reset_default_gateway(LLMConfig.no_llm_mode())
        gw2 = get_default_gateway()
        assert gw1 is not gw2
        assert gw2.config.no_llm is True

    def teardown_method(self, _):
        # Restore to env-based default
        from llm.gateway import reset_default_gateway
        reset_default_gateway(None)


class TestLLMGatewayBudgetEnforcement:
    def test_budget_exceeded_returns_skipped(self):
        """Gateway skips calls once budget is exceeded."""
        from llm.config import LLMConfig
        from llm.cost_tracker import CostTracker
        from llm.gateway import LLMGateway
        from llm.types import Message, TaskType
        # Budget of $0.001 — already exceeded by a single tracked call
        cfg = LLMConfig(no_llm=False, budget_limit_usd=0.000001)
        gw = LLMGateway(cfg)
        # Manually log a call to exhaust budget
        gw._tracker.log("test", "anthropic", "claude-sonnet-4-5", 1000, 500)
        resp = gw.complete_sync(
            task=TaskType.INTENT_PARSE,
            messages=[Message(role="user", content="hi")],
        )
        assert resp.skipped is True
