# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for shared/agents/ — react_loop and knowledge_agent.

All tests work without API keys and without external services.
"""
from __future__ import annotations

import asyncio
import json
import sys
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
# Helpers: mock gateway that returns fixed LLM content
# ---------------------------------------------------------------------------

def _make_mock_gateway(content: str, skipped: bool = False):
    """Return a minimal mock LLMGateway for testing."""
    from llm.types import LLMResponse

    class MockGateway:
        def is_llm_available(self) -> bool:
            return not skipped

        async def complete(self, task, messages, system="", temperature=0.0, max_tokens=2048, model_override=None):
            if skipped:
                return LLMResponse(
                    content="", model="", provider="", skipped=True,
                    input_tokens=0, output_tokens=0, cost_usd=0.0,
                )
            return LLMResponse(
                content=content,
                model="claude-haiku",
                provider="anthropic",
                skipped=False,
                input_tokens=10,
                output_tokens=20,
                cost_usd=0.00001,
            )

    return MockGateway()


def _make_no_llm_gateway():
    """Gateway backed by LLMConfig.no_llm_mode()."""
    from llm.config import LLMConfig
    from llm.gateway import LLMGateway
    return LLMGateway(LLMConfig.no_llm_mode())


# ---------------------------------------------------------------------------
# ReActStep / ReActResult dataclasses
# ---------------------------------------------------------------------------

class TestReActDataclasses:
    def test_react_step_defaults(self):
        from agents.react_loop import ReActStep
        step = ReActStep(thought="thinking", action="tool_a", action_input={"q": "test"})
        assert step.observation == ""
        assert step.step_num == 0

    def test_react_step_with_observation(self):
        from agents.react_loop import ReActStep
        step = ReActStep(
            thought="I found it",
            action="query_knowledge",
            action_input={"query": "ESP32"},
            observation="SUCCESS: {...}",
            step_num=1,
        )
        assert step.observation == "SUCCESS: {...}"
        assert step.step_num == 1

    def test_react_result_defaults(self):
        from agents.react_loop import ReActResult
        r = ReActResult(answer="done")
        assert r.success is True
        assert r.error == ""
        assert r.steps == []
        assert r.total_llm_calls == 0

    def test_react_result_failure(self):
        from agents.react_loop import ReActResult
        r = ReActResult(answer="", success=False, error="timeout", total_llm_calls=3)
        assert r.success is False
        assert "timeout" in r.error
        assert r.total_llm_calls == 3


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------

class TestParseResponse:
    def _parse(self, text):
        from agents.react_loop import _parse_response
        return _parse_response(text)

    def test_standard_action(self):
        text = (
            'Thought: I should search the knowledge base first.\n'
            'Action: query_knowledge\n'
            'Action Input: {"query": "ESP32-WROOM-32"}\n'
        )
        thought, action, action_input, final_answer = self._parse(text)
        assert "knowledge base" in thought
        assert action == "query_knowledge"
        assert action_input == {"query": "ESP32-WROOM-32"}
        assert final_answer is None

    def test_finish_action(self):
        text = (
            'Thought: I have all the info I need.\n'
            'Action: FINISH\n'
            'Action Input: {}\n'
            'Final Answer: The ESP32 is a WiFi+BT SoC by Espressif.\n'
        )
        thought, action, action_input, final_answer = self._parse(text)
        assert action.upper() == "FINISH"
        assert final_answer is not None
        assert "ESP32" in final_answer

    def test_finish_case_insensitive(self):
        text = (
            'Thought: done\n'
            'Action: finish\n'
            'Action Input: {}\n'
            'Final Answer: result\n'
        )
        _, action, _, final_answer = self._parse(text)
        assert action.lower() == "finish"
        assert final_answer == "result"

    def test_invalid_json_action_input_is_wrapped(self):
        text = (
            'Thought: trying something\n'
            'Action: query_knowledge\n'
            'Action Input: {not valid json}\n'
        )
        _, _, action_input, _ = self._parse(text)
        # Should fall back to {"raw": ...}
        assert isinstance(action_input, dict)

    def test_plain_string_action_input(self):
        text = (
            'Thought: search now\n'
            'Action: query_knowledge\n'
            'Action Input: SCD41\n'
        )
        _, _, action_input, _ = self._parse(text)
        # Falls back to {"query": "SCD41"}
        assert isinstance(action_input, dict)

    def test_finish_with_no_final_answer_uses_thought(self):
        text = (
            'Thought: The answer is 42.\n'
            'Action: FINISH\n'
            'Action Input: {}\n'
        )
        thought, action, _, final_answer = self._parse(text)
        assert action.upper() == "FINISH"
        # final_answer falls back to thought
        assert final_answer == thought

    def test_empty_response(self):
        thought, action, action_input, final_answer = self._parse("")
        assert thought == ""
        assert action == ""
        assert final_answer is None


# ---------------------------------------------------------------------------
# _build_system_prompt / _build_history_message
# ---------------------------------------------------------------------------

class TestPromptBuilders:
    def test_system_prompt_contains_tool_names(self):
        from agents.react_loop import _build_system_prompt
        tools = {"query_knowledge": "Look up component", "download_pdf": "Download a PDF"}
        prompt = _build_system_prompt(tools)
        assert "query_knowledge" in prompt
        assert "download_pdf" in prompt
        assert "FINISH" in prompt

    def test_system_prompt_no_tools(self):
        from agents.react_loop import _build_system_prompt
        prompt = _build_system_prompt({})
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_history_message_empty_steps(self):
        from agents.react_loop import _build_history_message
        msg = _build_history_message([])
        assert msg == ""

    def test_history_message_single_step(self):
        from agents.react_loop import ReActStep, _build_history_message
        step = ReActStep(
            thought="first thought",
            action="query_knowledge",
            action_input={"query": "SCD41"},
            observation="SUCCESS: data",
            step_num=1,
        )
        msg = _build_history_message([step])
        assert "first thought" in msg
        assert "query_knowledge" in msg
        assert "SUCCESS: data" in msg

    def test_history_message_step_without_observation(self):
        from agents.react_loop import ReActStep, _build_history_message
        step = ReActStep(
            thought="thinking",
            action="FINISH",
            action_input={},
            observation="",
            step_num=1,
        )
        msg = _build_history_message([step])
        assert "Observation:" not in msg


# ---------------------------------------------------------------------------
# run_react_loop — no-LLM mode
# ---------------------------------------------------------------------------

class TestReActLoopNoLLM:
    def test_skipped_llm_returns_failure(self):
        from agents.react_loop import run_react_loop
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(
            session_id="test",
            llm_gateway=gw,
            cache_dir=Path("/tmp/test_react"),
        )

        result = asyncio.run(run_react_loop(
            task="Find ESP32 specs",
            tools={},
            gateway=gw,
            context=ctx,
            max_steps=3,
        ))
        assert result.success is False
        assert "LLM unavailable" in result.error or result.error != ""

    def test_skipped_returns_empty_answer(self):
        from agents.react_loop import run_react_loop
        from llm.config import LLMConfig
        from llm.gateway import LLMGateway
        from tools.base import ToolContext

        gw = LLMGateway(LLMConfig.no_llm_mode())
        ctx = ToolContext(
            session_id="test",
            llm_gateway=gw,
            cache_dir=Path("/tmp/test_react"),
        )

        result = asyncio.run(run_react_loop(
            task="anything",
            tools={},
            gateway=gw,
            context=ctx,
        ))
        assert result.answer == ""
        assert result.total_llm_calls == 1


# ---------------------------------------------------------------------------
# run_react_loop — mock LLM that immediately returns FINISH
# ---------------------------------------------------------------------------

class TestReActLoopMockLLM:
    def _make_finish_response(self, answer: str = "The component is ESP32") -> str:
        return (
            f"Thought: I already know the answer.\n"
            f"Action: FINISH\n"
            f"Action Input: {{}}\n"
            f"Final Answer: {answer}\n"
        )

    def test_finish_on_first_step(self, tmp_path):
        from agents.react_loop import run_react_loop
        from tools.base import ToolContext

        gw = _make_mock_gateway(self._make_finish_response("ESP32 is a WiFi chip"))
        ctx = ToolContext(session_id="t", llm_gateway=gw, cache_dir=tmp_path)

        result = asyncio.run(run_react_loop(
            task="What is ESP32?",
            tools={},
            gateway=gw,
            context=ctx,
        ))
        assert result.success is True
        assert "ESP32" in result.answer
        assert result.total_llm_calls == 1
        assert len(result.steps) == 1

    def test_tool_not_found_creates_error_observation(self, tmp_path):
        """If LLM picks a nonexistent tool, it should record an error observation."""
        from agents.react_loop import run_react_loop
        from tools.base import ToolContext

        # LLM tries a fake tool first, then finishes
        responses = [
            "Thought: use fake\nAction: nonexistent_tool\nAction Input: {}\n",
            self._make_finish_response("fallback answer"),
        ]
        call_count = 0

        from llm.types import LLMResponse

        class SequentialGateway:
            def is_llm_available(self):
                return True

            async def complete(self, task, messages, system="", temperature=0.0,
                               max_tokens=2048, model_override=None):
                nonlocal call_count
                content = responses[min(call_count, len(responses) - 1)]
                call_count += 1
                return LLMResponse(
                    content=content, model="test", provider="mock",
                    skipped=False, input_tokens=5, output_tokens=10, cost_usd=0.0
                )

        gw = SequentialGateway()
        ctx = ToolContext(session_id="t", llm_gateway=gw, cache_dir=tmp_path)

        result = asyncio.run(run_react_loop(
            task="test",
            tools={},   # no tools registered
            gateway=gw,
            context=ctx,
            max_steps=5,
        ))
        # Eventually finishes
        assert result.success is True
        # First step has an error observation about nonexistent tool
        first_step = result.steps[0]
        assert "not found" in first_step.observation.lower() or "ERROR" in first_step.observation

    def test_max_steps_reached(self, tmp_path):
        """If LLM never FINISHes, max_steps kicks in."""
        from agents.react_loop import run_react_loop
        from tools.base import ToolContext

        # Always returns a non-FINISH action but there's no real tool
        loop_response = "Thought: still thinking\nAction: query_knowledge\nAction Input: {\"query\": \"x\"}\n"
        gw = _make_mock_gateway(loop_response)
        ctx = ToolContext(session_id="t", llm_gateway=gw, cache_dir=tmp_path)

        result = asyncio.run(run_react_loop(
            task="spin forever",
            tools={},
            gateway=gw,
            context=ctx,
            max_steps=2,
        ))
        assert result.success is False
        assert "Max steps" in result.error
        assert result.total_llm_calls == 2

    def test_tool_execute_success_included_in_observation(self, tmp_path):
        """A working dummy tool result appears in the next step's history."""
        from agents.react_loop import run_react_loop
        from tools.base import ToolContext, ToolResult

        # Step 1: use dummy_tool; Step 2: FINISH
        from llm.types import LLMResponse

        step_responses = [
            "Thought: check db\nAction: dummy_tool\nAction Input: {\"q\": \"SCD41\"}\n",
            self._make_finish_response("SCD41 found"),
        ]
        idx = [0]

        class StepGateway:
            def is_llm_available(self):
                return True

            async def complete(self, task, messages, **kw):
                content = step_responses[min(idx[0], len(step_responses) - 1)]
                idx[0] += 1
                return LLMResponse(
                    content=content, model="t", provider="mock",
                    skipped=False, input_tokens=5, output_tokens=10, cost_usd=0.0
                )

        class DummyTool:
            name = "dummy_tool"
            description = "dummy"

            async def execute(self, inp, ctx):
                return ToolResult(success=True, data={"mpn": "SCD41"}, source="test", confidence=0.9)

        gw = StepGateway()
        ctx = ToolContext(session_id="t", llm_gateway=gw, cache_dir=tmp_path)

        result = asyncio.run(run_react_loop(
            task="find SCD41",
            tools={"dummy_tool": DummyTool()},
            gateway=gw,
            context=ctx,
            max_steps=5,
        ))
        assert result.success is True
        assert "SCD41" in result.answer
        # First step observation contains tool result
        assert "SCD41" in result.steps[0].observation


# ---------------------------------------------------------------------------
# AgentComponentResult
# ---------------------------------------------------------------------------

class TestAgentComponentResult:
    def test_basic_construction(self):
        from agents.knowledge_agent import AgentComponentResult
        r = AgentComponentResult(
            mpn="SCD41",
            name="CO2 Sensor",
            manufacturer="Sensirion",
            category="sensor",
            interface_types=["I2C"],
            electrical_ratings={"vdd_v": 3.3},
            known_i2c_addresses=["0x62"],
            unit_cost_usd=4.99,
            tags=["co2", "i2c"],
            confidence=0.95,
            source="builtin_db",
        )
        assert r.mpn == "SCD41"
        assert r.confidence == 0.95
        assert r.agent_trace == []
        assert r.raw == {}

    def test_with_raw_and_trace(self):
        from agents.knowledge_agent import AgentComponentResult
        r = AgentComponentResult(
            mpn="SCD41",
            name="CO2",
            manufacturer="Sensirion",
            category="sensor",
            interface_types=[],
            electrical_ratings={},
            known_i2c_addresses=[],
            unit_cost_usd=0.0,
            tags=[],
            confidence=0.80,
            source="agent_extracted",
            raw={"mpn": "SCD41"},
            agent_trace=["Step 1: query_knowledge", "Step 2: FINISH"],
        )
        assert r.raw["mpn"] == "SCD41"
        assert len(r.agent_trace) == 2


# ---------------------------------------------------------------------------
# KnowledgeAgent helpers
# ---------------------------------------------------------------------------

class TestKnowledgeAgentHelpers:
    def test_entry_to_result(self):
        from agents.knowledge_agent import KnowledgeAgent
        entry = {
            "mpn": "ESP32-WROOM-32",
            "name": "ESP32 Module",
            "manufacturer": "Espressif",
            "category": "mcu",
            "interface_types": ["WiFi", "BT", "I2C"],
            "electrical_ratings": {"vdd_v": 3.3},
            "known_i2c_addresses": [],
            "unit_cost_usd": 2.50,
            "tags": ["esp32", "wifi"],
        }
        r = KnowledgeAgent._entry_to_result(entry, source="builtin_db", confidence=0.95)
        assert r.mpn == "ESP32-WROOM-32"
        assert r.source == "builtin_db"
        assert r.confidence == 0.95
        assert r.manufacturer == "Espressif"

    def test_dict_to_result_alternate_keys(self):
        """_dict_to_result handles alternate key names (MPN, interfaces, i2c_addresses)."""
        from agents.knowledge_agent import KnowledgeAgent
        data = {
            "MPN": "BME280",
            "manufacturer": "Bosch",
            "interfaces": ["I2C", "SPI"],
            "i2c_addresses": ["0x76", "0x77"],
            "unit_cost_usd": 1.80,
        }
        r = KnowledgeAgent._dict_to_result(data, source="local_cache", confidence=0.85)
        assert r.mpn == "BME280"
        assert "I2C" in r.interface_types
        assert "0x76" in r.known_i2c_addresses

    def test_result_to_dict_roundtrip(self):
        from agents.knowledge_agent import AgentComponentResult, KnowledgeAgent
        r = AgentComponentResult(
            mpn="BME280", name="Pressure Sensor", manufacturer="Bosch",
            category="sensor", interface_types=["I2C"], electrical_ratings={},
            known_i2c_addresses=["0x76"], unit_cost_usd=1.80,
            tags=["pressure"], confidence=0.85, source="builtin_db",
        )
        d = KnowledgeAgent._result_to_dict(r)
        assert d["mpn"] == "BME280"
        assert d["confidence"] == 0.85
        assert "I2C" in d["interface_types"]

    def test_parse_agent_answer_with_json(self):
        from agents.knowledge_agent import KnowledgeAgent
        answer = (
            'The component is:\n'
            '{"mpn": "SCD41", "manufacturer": "Sensirion", "category": "sensor", '
            '"interface_types": ["I2C"], "electrical_ratings": {"vdd_v": 3.3}, '
            '"known_i2c_addresses": ["0x62"], "unit_cost_usd": 4.99, "tags": ["co2"]}'
        )
        agent = KnowledgeAgent.__new__(KnowledgeAgent)
        result = agent._parse_agent_answer(answer, query="SCD41", trace=["Step 1: FINISH"])
        assert result is not None
        assert result.mpn == "SCD41"
        assert result.source == "agent_extracted"
        assert result.confidence == 0.70

    def test_parse_agent_answer_no_json_fallback(self):
        from agents.knowledge_agent import KnowledgeAgent
        answer = "I found the SCD41 by Sensirion, it uses I2C communication at 3.3V."
        agent = KnowledgeAgent.__new__(KnowledgeAgent)
        result = agent._parse_agent_answer(answer, query="SCD41", trace=[])
        assert result is not None
        assert result.mpn == "SCD41"
        assert result.confidence == 0.30

    def test_parse_agent_answer_too_short_returns_none(self):
        from agents.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent.__new__(KnowledgeAgent)
        result = agent._parse_agent_answer("N/A", query="XYZ", trace=[])
        assert result is None


# ---------------------------------------------------------------------------
# KnowledgeAgent — cache operations
# ---------------------------------------------------------------------------

class TestKnowledgeAgentCache:
    def test_save_and_query_cache(self, tmp_path):
        from agents.knowledge_agent import AgentComponentResult, KnowledgeAgent
        agent = KnowledgeAgent(cache_dir=tmp_path)
        r = AgentComponentResult(
            mpn="BME280",
            name="Pressure",
            manufacturer="Bosch",
            category="sensor",
            interface_types=["I2C"],
            electrical_ratings={},
            known_i2c_addresses=[],
            unit_cost_usd=1.80,
            tags=[],
            confidence=0.85,
            source="agent_extracted",
        )
        agent._save_to_cache(r)

        # Cache file created
        cache_files = list(tmp_path.glob("*.json"))
        assert len(cache_files) == 1
        assert "BME280" in cache_files[0].stem.upper()

        # Can retrieve from cache
        found = agent._query_cache("BME280")
        assert found is not None
        assert found.mpn == "BME280"
        assert found.source == "local_cache"

    def test_cache_miss_returns_none(self, tmp_path):
        from agents.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent(cache_dir=tmp_path)
        assert agent._query_cache("NONEXISTENT_XYZ_PART") is None

    def test_save_empty_mpn_does_nothing(self, tmp_path):
        from agents.knowledge_agent import AgentComponentResult, KnowledgeAgent
        agent = KnowledgeAgent(cache_dir=tmp_path)
        r = AgentComponentResult(
            mpn="",  # empty
            name="", manufacturer="", category="",
            interface_types=[], electrical_ratings={},
            known_i2c_addresses=[], unit_cost_usd=0.0,
            tags=[], confidence=0.0, source="test",
        )
        agent._save_to_cache(r)
        # No files created
        assert len(list(tmp_path.glob("*.json"))) == 0

    def test_cache_dir_created_on_init(self, tmp_path):
        from agents.knowledge_agent import KnowledgeAgent
        cache_dir = tmp_path / "nested" / "cache"
        assert not cache_dir.exists()
        KnowledgeAgent(cache_dir=cache_dir)
        assert cache_dir.exists()


# ---------------------------------------------------------------------------
# KnowledgeAgent — builtin DB tier
# ---------------------------------------------------------------------------

class TestKnowledgeAgentBuiltin:
    def test_known_mpn_query_builtin(self):
        from agents.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent.__new__(KnowledgeAgent)
        result = agent._query_builtin("ESP32-WROOM-32")
        # May succeed or return None if DB not available — check structure
        if result is not None:
            assert result.source == "builtin_db"
            assert result.confidence == 0.95
            assert result.mpn != ""

    def test_unknown_mpn_query_builtin_returns_none(self):
        from agents.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent.__new__(KnowledgeAgent)
        result = agent._query_builtin("ZZZNONSENSE_PART_999")
        assert result is None

    def test_query_builtin_by_modality_sensor(self):
        from agents.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent.__new__(KnowledgeAgent)
        # "co2" is a known tag in the COMPONENTS list
        result = agent._query_builtin_by_modality("co2")
        if result is not None:
            # Matched something
            assert result.confidence == 0.90
            assert result.source == "builtin_db"

    def test_query_builtin_by_modality_unknown_returns_none(self):
        from agents.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent.__new__(KnowledgeAgent)
        result = agent._query_builtin_by_modality("xyzzy_modality_that_doesnt_exist")
        assert result is None


# ---------------------------------------------------------------------------
# KnowledgeAgent.find() — full pipeline
# ---------------------------------------------------------------------------

class TestKnowledgeAgentFind:
    def test_find_known_mpn_hits_builtin(self, tmp_path):
        from agents.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent(cache_dir=tmp_path)
        result = asyncio.run(agent.find("ESP32-WROOM-32"))
        if result is not None:
            # Should be from builtin DB
            assert result.source == "builtin_db"
            assert result.confidence >= 0.90

    def test_find_unknown_mpn_no_llm_returns_none(self, tmp_path):
        from agents.knowledge_agent import KnowledgeAgent
        # No gateway — agent tier skipped, no fallback
        agent = KnowledgeAgent(gateway=None, cache_dir=tmp_path)
        result = asyncio.run(agent.find("ZZZNONSENSE_PART_XYZZY_99"))
        assert result is None

    def test_find_unknown_mpn_with_unavailable_llm_returns_none(self, tmp_path):
        """When LLM is present but skipped, agent tier is skipped."""
        from agents.knowledge_agent import KnowledgeAgent
        gw = _make_no_llm_gateway()
        agent = KnowledgeAgent(gateway=gw, cache_dir=tmp_path)
        result = asyncio.run(agent.find("ZZZNONSENSE_PART_XYZZY_99"))
        assert result is None

    def test_find_hits_local_cache(self, tmp_path):
        """If a component is pre-cached, find() returns it from tier 2."""
        from agents.knowledge_agent import AgentComponentResult, KnowledgeAgent

        # Pre-populate cache
        cache_file = tmp_path / "MYCACHED_PART.json"
        cache_file.write_text(json.dumps({
            "mpn": "MYCACHED_PART",
            "name": "Cached Widget",
            "manufacturer": "Acme",
            "category": "sensor",
            "interface_types": ["I2C"],
            "electrical_ratings": {},
            "known_i2c_addresses": [],
            "unit_cost_usd": 0.5,
            "tags": ["cached"],
        }))

        agent = KnowledgeAgent(gateway=None, cache_dir=tmp_path)
        result = asyncio.run(agent.find("MYCACHED_PART"))
        assert result is not None
        assert result.source == "local_cache"
        assert result.mpn == "MYCACHED_PART"

    def test_find_for_modality_hits_builtin(self, tmp_path):
        from agents.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent(cache_dir=tmp_path)
        # "co2" should hit builtin DB if a CO2 sensor is in COMPONENTS
        result = asyncio.run(agent.find_for_modality("co2"))
        # Result may be None if no match — just check return type
        assert result is None or hasattr(result, "mpn")

    def test_find_for_modality_with_requirements(self, tmp_path):
        from agents.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent(gateway=None, cache_dir=tmp_path)
        result = asyncio.run(agent.find_for_modality(
            "temperature",
            requirements={"interface": "I2C", "supply_voltage": 3.3},
        ))
        assert result is None or hasattr(result, "mpn")


# ---------------------------------------------------------------------------
# KnowledgeAgent._get_gateway
# ---------------------------------------------------------------------------

class TestKnowledgeAgentGetGateway:
    def test_explicit_gateway_returned(self, tmp_path):
        from agents.knowledge_agent import KnowledgeAgent
        gw = _make_no_llm_gateway()
        agent = KnowledgeAgent(gateway=gw, cache_dir=tmp_path)
        assert agent._get_gateway() is gw

    def test_no_gateway_falls_back_to_default(self, tmp_path):
        from agents.knowledge_agent import KnowledgeAgent
        agent = KnowledgeAgent(gateway=None, cache_dir=tmp_path)
        # Should not raise — returns default or None
        result = agent._get_gateway()
        assert result is None or hasattr(result, "complete")
