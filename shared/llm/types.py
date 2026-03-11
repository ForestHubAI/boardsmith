# SPDX-License-Identifier: AGPL-3.0-or-later
"""Core types for the LLM abstraction layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskType(str, Enum):
    """Semantic task types — used by the router to pick the right provider."""

    INTENT_PARSE = "intent_parse"           # NL → RequirementsSpec
    COMPONENT_SUGGEST = "component_suggest" # Context → Component Recommendations
    TOPOLOGY_SUGGEST = "topology_suggest"   # Requirements → Bus/Pin Topology
    CONSTRAINT_FIX = "constraint_fix"       # FAIL constraint → Fix suggestion
    LAYOUT_PLAN = "layout_plan"             # Components → Schematic Layout
    CODE_GEN = "code_gen"                   # HIR/Graph → Firmware code
    DATASHEET_EXTRACT = "datasheet_extract" # PDF text → Structured ComponentKnowledge
    AGENT_REASONING = "agent_reasoning"     # ReAct loop step
    CLARIFICATION = "clarification"         # Prompt → Clarification questions


@dataclass
class Message:
    """A single message in a conversation."""

    role: str     # "user", "assistant", or "system"
    content: str


@dataclass
class LLMResponse:
    """Response from any LLM provider."""

    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    skipped: bool = False   # True when --no-llm mode is active or all providers failed

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class CostEntry:
    """A single tracked LLM call."""

    task: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


@dataclass
class CostSummary:
    """Aggregated cost summary for a session."""

    total_usd: float
    total_tokens: int
    total_calls: int
    calls_by_task: dict[str, int] = field(default_factory=dict)
    calls_by_provider: dict[str, int] = field(default_factory=dict)
    cost_by_provider: dict[str, float] = field(default_factory=dict)


@dataclass
class ToolCall:
    """A single tool invocation requested by the LLM."""

    id: str          # tool_use_id from Anthropic API — must be echoed back in tool_result
    name: str        # tool name — routed by ToolDispatcher
    input: dict[str, Any]  # arguments from LLM


@dataclass
class ToolCallResponse:
    """Response from complete_with_tools() when stop_reason == 'tool_use'."""

    tool_calls: list["ToolCall"]
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    raw_content: list[Any] = field(default_factory=list)  # SDK objects — pass directly to next API call
    stop_reason: str = "tool_use"
