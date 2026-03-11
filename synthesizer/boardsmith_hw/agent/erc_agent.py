# SPDX-License-Identifier: AGPL-3.0-or-later
"""ERCAgent — bounded LLM tool-use loop for ERC repair.

Import-safe with BOARDSMITH_NO_LLM=1: no anthropic import at module level.
All LLM-dependent code is inside ERCAgent._run_loop() which is only reachable
when use_llm=True.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # ToolDispatcher and gateway imports happen inside _run_loop


# ---------------------------------------------------------------------------
# Tool definition constants — plain dicts, no anthropic import needed
# ---------------------------------------------------------------------------

RUN_ERC_TOOL_DEF = {
    "name": "run_erc",
    "description": "Run KiCad ERC on the schematic. Returns violations list.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sch_path": {"type": "string", "description": "Absolute path to .kicad_sch file"},
        },
        "required": ["sch_path"],
    },
}

WRITE_PATCH_TOOL_DEF = {
    "name": "write_schematic_patch",
    "description": "Apply ADD or MODIFY operations to the schematic. Creates .bak before writing.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sch_path": {"type": "string"},
            "operations": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of {op: ADD|MODIFY, ...} patch operations",
            },
        },
        "required": ["sch_path", "operations"],
    },
}

# System prompt for the LLM
_AGENT_SYSTEM = (
    "You are an ERC repair agent for KiCad schematics.\n"
    "You will receive ERC violation reports and must call write_schematic_patch to fix them.\n"
    "Fix one violation per tool call. Prefer adding PWR_FLAG symbols for power net issues.\n"
    "For unconnected pins, add no_connect markers. Never delete components.\n"
    "After each fix, run_erc will be called automatically to check progress."
)


# ---------------------------------------------------------------------------
# _violation_fingerprint
# ---------------------------------------------------------------------------

def _violation_fingerprint(violations: list[dict]) -> str:
    """Return a deterministic sha256 fingerprint of error-severity violations.

    Warnings are excluded intentionally — they do not change between iterations
    due to LLM reasoning patterns, which would cause false stall detection.

    The result is order-independent: violations are sorted before hashing.
    """
    errors_only = [v for v in violations if v.get("severity") == "error"]
    sorted_errors = sorted(
        errors_only,
        key=lambda v: (v.get("rule_id", ""), v.get("message", "")),
    )
    serialized = json.dumps(
        [(v.get("rule_id", ""), v.get("message", "")) for v in sorted_errors]
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


# ---------------------------------------------------------------------------
# ERCAgentResult
# ---------------------------------------------------------------------------

@dataclass
class ERCAgentResult:
    """Result returned by ERCAgent.run()."""

    violations: list[dict]
    iterations_used: int
    stalled: bool = False
    cap_hit: bool = False
    sch_path: Path | None = None

    @property
    def is_clean(self) -> bool:
        """True when no violations remain."""
        return len(self.violations) == 0

    @property
    def summary_message(self) -> str:
        """Human-readable summary of the agent run."""
        if self.stalled:
            return "ERC agent stalled: same violations in 2 consecutive iterations"
        if self.is_clean:
            return "ERC agent: all violations resolved"
        msgs = " ".join(
            f"[{v.get('message', '?')}]" for v in self.violations
        )
        return f"ERC agent: {len(self.violations)} ERC violations remain: {msgs}"


# ---------------------------------------------------------------------------
# ERCAgent
# ---------------------------------------------------------------------------

class ERCAgent:
    """Bounded tool-use loop that drives LLM-guided ERC repair.

    The loop:
    1. Calls run_erc via ToolDispatcher to get initial violations.
    2. If no violations → returns clean result immediately.
    3. Builds messages, then iterates up to max_iterations:
       a. Checks fingerprint for stall (same error-set twice in a row).
       b. Emits progress to stderr.
       c. Calls _request_fix() to ask LLM to apply one fix.
       d. Re-runs ERC to get updated violations.
       e. If clean → returns.
    4. On cap hit → returns cap_hit=True with remaining violations.
    5. On any exception → returns cap_hit=True with exception message in violations.

    ERCAgent.run() is synchronous — no asyncio.run() inside. Any async operations
    (ToolDispatcher.dispatch) are wrapped in concurrent.futures if needed.
    """

    def __init__(
        self,
        sch_path: Path,
        gateway,          # LLMGateway — lazy import type
        dispatcher,       # ToolDispatcher — lazy import type
        max_iterations: int = 5,
    ) -> None:
        self._sch_path = sch_path
        self._gateway = gateway
        self._dispatcher = dispatcher
        self._max_iterations = max_iterations

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> ERCAgentResult:
        """Run the ERC repair loop synchronously.

        Returns an ERCAgentResult — never raises.
        """
        iteration = 0
        try:
            violations = self._run_erc_via_tool()
            if not violations:
                return ERCAgentResult(
                    violations=[],
                    iterations_used=0,
                    sch_path=self._sch_path,
                )

            messages: list[dict] = [
                {
                    "role": "user",
                    "content": f"ERC violations found: {json.dumps(violations)}. Fix them.",
                }
            ]
            prev_fingerprint: str | None = None

            while iteration < self._max_iterations:
                iteration += 1
                fp = _violation_fingerprint(violations)
                if fp == prev_fingerprint:
                    print(
                        "ERC agent stalled: same violations in 2 consecutive iterations",
                        file=sys.stderr,
                    )
                    return ERCAgentResult(
                        violations=violations,
                        iterations_used=iteration,
                        stalled=True,
                        sch_path=self._sch_path,
                    )
                prev_fingerprint = fp

                error_count = len(
                    [v for v in violations if v.get("severity") == "error"]
                )
                print(
                    f"ERC iteration {iteration}/{self._max_iterations}: "
                    f"{error_count} errors remain",
                    file=sys.stderr,
                )

                messages = self._request_fix(violations, messages)
                violations = self._run_erc_via_tool()

                if not violations:
                    return ERCAgentResult(
                        violations=[],
                        iterations_used=iteration,
                        sch_path=self._sch_path,
                    )

            # Cap hit
            return ERCAgentResult(
                violations=violations,
                iterations_used=iteration,
                cap_hit=True,
                sch_path=self._sch_path,
            )

        except Exception as e:
            return ERCAgentResult(
                violations=[{"message": str(e), "severity": "error"}],
                iterations_used=iteration,
                cap_hit=True,
                sch_path=self._sch_path,
            )

    # ------------------------------------------------------------------
    # Internal helpers (overridable in tests)
    # ------------------------------------------------------------------

    def _make_context(self):
        """Create a ToolContext for dispatching tool calls.

        Lazy import to stay BOARDSMITH_NO_LLM=1 safe.
        """
        from tools.base import ToolContext
        return ToolContext(
            session_id="erc-agent",
            llm_gateway=self._gateway,
            no_llm=False,
        )

    def _run_erc_via_tool(self) -> list[dict]:
        """Synchronously call run_erc via the ToolDispatcher.

        Returns the violations list from the tool result, or [] if key missing.
        """
        import asyncio
        import concurrent.futures

        from llm.types import ToolCall

        tc = ToolCall(
            id="erc-check",
            name="run_erc",
            input={"sch_path": str(self._sch_path)},
        )

        ctx = self._make_context()

        _tc = tc  # capture for factory closure

        def _make_dispatch():
            return self._dispatcher.dispatch([_tc], ctx)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, _make_dispatch())
                    result_blocks = future.result(timeout=60)
            else:
                result_blocks = loop.run_until_complete(_make_dispatch())
        except RuntimeError:
            result_blocks = asyncio.run(_make_dispatch())

        if not result_blocks:
            return []

        # Parse violations from the first tool_result block
        try:
            content = result_blocks[0].get("content", "{}")
            data = json.loads(content) if isinstance(content, str) else content
            return data.get("violations", [])
        except (json.JSONDecodeError, AttributeError, IndexError):
            return []

    def _request_fix(self, violations: list[dict], messages: list[dict]) -> list[dict]:
        """Ask the LLM to fix one violation and apply via ToolDispatcher.

        Returns the updated messages list (appends assistant response + tool_result).
        All LLM imports are lazy inside this method — import-clean under BOARDSMITH_NO_LLM=1.
        """
        import asyncio
        import concurrent.futures

        # Build Anthropic-format tool definitions
        tools = [RUN_ERC_TOOL_DEF, WRITE_PATCH_TOOL_DEF]

        # complete_with_tools_sync() is a sync wrapper on LLMGateway
        response = self._gateway.complete_with_tools_sync(
            tools=tools,
            messages=messages,
            system=_AGENT_SYSTEM,
        )

        # Append assistant's raw_content to messages for next turn
        assistant_msg: dict = {
            "role": "assistant",
            "content": response.raw_content if response.raw_content else [],
        }
        updated_messages = messages + [assistant_msg]

        if not response.tool_calls:
            return updated_messages

        # Dispatch each tool call synchronously
        ctx = self._make_context()

        _tool_calls = response.tool_calls

        def _make_dispatch_all():
            return self._dispatcher.dispatch(_tool_calls, ctx)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, _make_dispatch_all())
                    tool_result_blocks = future.result(timeout=60)
            else:
                tool_result_blocks = loop.run_until_complete(_make_dispatch_all())
        except RuntimeError:
            tool_result_blocks = asyncio.run(_make_dispatch_all())

        # Append tool results as user message
        tool_result_msg: dict = {
            "role": "user",
            "content": tool_result_blocks,
        }
        return updated_messages + [tool_result_msg]
