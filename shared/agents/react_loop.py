# SPDX-License-Identifier: AGPL-3.0-or-later
"""Generic ReAct (Reasoning + Acting) agent loop.

Each step:
  1. THINK  — LLM reasons about what to do next
  2. ACT    — execute a tool
  3. OBSERVE — feed result back to LLM
  4. Repeat until FINISH or max_steps reached.

Format the LLM receives:
  Thought: <reasoning>
  Action: <tool_name>  (or "FINISH")
  Action Input: <JSON>

  When done:
  Thought: <reasoning>
  Action: FINISH
  Final Answer: <answer>
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class ReActStep:
    """One iteration of the Thought → Act → Observe loop."""

    thought: str
    action: str               # tool name or "FINISH"
    action_input: Any         # parsed JSON or raw string
    observation: str = ""     # tool output (filled after execution)
    step_num: int = 0


@dataclass
class ReActResult:
    """Final result from a ReAct run."""

    answer: str
    steps: list[ReActStep] = field(default_factory=list)
    success: bool = True
    error: str = ""
    total_llm_calls: int = 0


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

_SYSTEM_TEMPLATE = """\
You are a hardware research agent. Your task is to answer the user's question \
by using the available tools step by step.

Available tools:
{tool_descriptions}

Respond in EXACTLY this format:

Thought: <your reasoning>
Action: <tool_name or FINISH>
Action Input: <JSON object with tool parameters>

When you have enough information to answer:
Thought: <final reasoning>
Action: FINISH
Final Answer: <your complete answer>

Rules:
- Always use valid JSON for Action Input.
- Only use tool names from the available list.
- Never skip Thought.
- Be concise in observations; focus on what matters for the task.
"""

_OBSERVATION_PREFIX = "Observation: "


def _build_system_prompt(tools: dict[str, str]) -> str:
    tool_desc = "\n".join(
        f"  - {name}: {desc}"
        for name, desc in tools.items()
    )
    return _SYSTEM_TEMPLATE.format(tool_descriptions=tool_desc)


def _build_history_message(steps: list[ReActStep]) -> str:
    """Build the accumulated conversation so far."""
    lines: list[str] = []
    for step in steps:
        lines.append(f"Thought: {step.thought}")
        lines.append(f"Action: {step.action}")
        lines.append(f"Action Input: {json.dumps(step.action_input, ensure_ascii=False)}")
        if step.observation:
            lines.append(f"{_OBSERVATION_PREFIX}{step.observation}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_response(text: str) -> tuple[str, str, Any, str | None]:
    """Parse an LLM response into (thought, action, action_input, final_answer).

    Returns final_answer as non-None only when Action: FINISH.
    """
    thought = ""
    action = ""
    action_input: Any = {}
    final_answer: str | None = None

    # Extract Thought
    m = re.search(r"Thought:\s*(.+?)(?=\nAction:|\Z)", text, re.DOTALL | re.IGNORECASE)
    if m:
        thought = m.group(1).strip()

    # Extract Action
    m = re.search(r"Action:\s*(\S+)", text, re.IGNORECASE)
    if m:
        action = m.group(1).strip()

    # Extract Action Input (JSON block)
    m = re.search(r"Action Input:\s*(\{[\s\S]*?\})", text, re.IGNORECASE)
    if m:
        try:
            action_input = json.loads(m.group(1))
        except json.JSONDecodeError:
            action_input = {"raw": m.group(1)}
    else:
        # Try a plain string input
        m = re.search(r"Action Input:\s*(.+?)(?=\nThought:|\nObservation:|\Z)", text, re.DOTALL | re.IGNORECASE)
        if m:
            raw = m.group(1).strip().strip('"\'')
            action_input = {"query": raw}

    # Extract Final Answer (only when FINISH)
    if action.upper() == "FINISH":
        m = re.search(r"Final Answer:\s*([\s\S]+)", text, re.IGNORECASE)
        if m:
            final_answer = m.group(1).strip()
        else:
            final_answer = thought  # fallback

    return thought, action, action_input, final_answer


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def run_react_loop(
    task: str,
    tools: dict[str, Any],       # name → Tool instance (has .execute() and .description)
    gateway: Any,                  # LLMGateway
    context: Any,                  # ToolContext
    max_steps: int = 10,
    task_type: str = "agent_reasoning",
) -> ReActResult:
    """Run the ReAct loop until FINISH or max_steps.

    Args:
        task: Natural language task description.
        tools: Dict of tool_name → Tool instance.
        gateway: LLMGateway instance.
        context: ToolContext instance.
        max_steps: Hard limit on iterations.
        task_type: LLM TaskType for routing.

    Returns:
        ReActResult with answer and full step trace.
    """
    from llm.types import Message, TaskType

    tool_descriptions = {name: t.description for name, t in tools.items()}
    system = _build_system_prompt(tool_descriptions)

    steps: list[ReActStep] = []
    llm_calls = 0

    for step_num in range(1, max_steps + 1):
        # Build user message: task + accumulated history
        history = _build_history_message(steps)
        user_msg = f"Task: {task}\n\n{history}".strip()

        from llm.types import Message
        response = await gateway.complete(
            task=task_type,
            messages=[Message(role="user", content=user_msg)],
            system=system,
            temperature=0.0,
            max_tokens=2048,
        )
        llm_calls += 1

        if response.skipped or not response.content:
            return ReActResult(
                answer="",
                steps=steps,
                success=False,
                error="LLM unavailable or skipped",
                total_llm_calls=llm_calls,
            )

        thought, action, action_input, final_answer = _parse_response(response.content)

        log.debug(
            "[ReAct step %d] thought=%r action=%s input=%s",
            step_num, thought[:80], action, str(action_input)[:60],
        )

        if action.upper() == "FINISH":
            step = ReActStep(
                thought=thought,
                action="FINISH",
                action_input=action_input,
                observation="",
                step_num=step_num,
            )
            steps.append(step)
            return ReActResult(
                answer=final_answer or "",
                steps=steps,
                success=True,
                total_llm_calls=llm_calls,
            )

        # Execute tool
        tool = tools.get(action)
        if tool is None:
            observation = f"ERROR: Tool '{action}' not found. Use one of: {list(tools.keys())}"
        else:
            try:
                # Build tool-specific input object if the tool uses a dataclass
                tool_result = await tool.execute(action_input, context)
                if tool_result.success:
                    data_str = json.dumps(tool_result.data, ensure_ascii=False, default=str)
                    if len(data_str) > 2000:
                        data_str = data_str[:2000] + "...[truncated]"
                    observation = (
                        f"SUCCESS (source={tool_result.source}, "
                        f"confidence={tool_result.confidence:.2f}): {data_str}"
                    )
                else:
                    observation = f"FAILED: {tool_result.error}"
            except Exception as e:
                observation = f"ERROR executing {action}: {e}"
                log.warning("Tool %s failed: %s", action, e)

        step = ReActStep(
            thought=thought,
            action=action,
            action_input=action_input,
            observation=observation,
            step_num=step_num,
        )
        steps.append(step)

    # Max steps reached
    last_thought = steps[-1].thought if steps else "Max steps reached"
    return ReActResult(
        answer=last_thought,
        steps=steps,
        success=False,
        error=f"Max steps ({max_steps}) reached without FINISH",
        total_llm_calls=llm_calls,
    )
