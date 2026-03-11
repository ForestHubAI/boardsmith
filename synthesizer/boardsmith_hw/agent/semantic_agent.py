# SPDX-License-Identifier: AGPL-3.0-or-later
"""SemanticVerificationAgent — bounded LLM tool-use loop for semantic repair.

Import-safe with BOARDSMITH_NO_LLM=1: no anthropic import at module level.
All LLM-dependent code is inside SemanticVerificationAgent._run_loop() which
is only reachable when use_llm=True.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # ToolDispatcher and gateway imports happen inside methods


# ---------------------------------------------------------------------------
# Tool definition constants — plain dicts, no anthropic import needed
# ---------------------------------------------------------------------------

VERIFY_COMPONENTS_TOOL_DEF = {
    "name": "verify_components",
    "description": (
        "Verify that all HIR components are present in the schematic. "
        "Returns violations list."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hir_path": {"type": "string", "description": "Absolute path to HIR JSON file"},
            "sch_path": {"type": "string", "description": "Absolute path to .kicad_sch file"},
        },
        "required": ["hir_path", "sch_path"],
    },
}

VERIFY_CONNECTIVITY_TOOL_DEF = {
    "name": "verify_connectivity",
    "description": (
        "Verify that all HIR bus/net connections exist in the schematic. "
        "Returns violations list."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hir_path": {"type": "string", "description": "Absolute path to HIR JSON file"},
            "sch_path": {"type": "string", "description": "Absolute path to .kicad_sch file"},
        },
        "required": ["hir_path", "sch_path"],
    },
}

VERIFY_BOOTABILITY_TOOL_DEF = {
    "name": "verify_bootability",
    "description": (
        "Verify that reset circuits, clock sources, and boot configuration pins "
        "are correctly wired. Returns violations list."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hir_path": {"type": "string", "description": "Absolute path to HIR JSON file"},
            "sch_path": {"type": "string", "description": "Absolute path to .kicad_sch file"},
        },
        "required": ["hir_path", "sch_path"],
    },
}

VERIFY_POWER_TOOL_DEF = {
    "name": "verify_power",
    "description": (
        "Verify power rails: regulators present, decoupling caps, power sequencing. "
        "Returns violations list."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hir_path": {"type": "string", "description": "Absolute path to HIR JSON file"},
            "sch_path": {"type": "string", "description": "Absolute path to .kicad_sch file"},
        },
        "required": ["hir_path", "sch_path"],
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

VERIFY_BOM_TOOL_DEF = {
    "name": "verify_bom",
    "description": (
        "Cross-check HIR components against bom.csv. "
        "Returns violations for missing rows or MPN mismatches."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hir_path": {"type": "string", "description": "Absolute path to hir.json"},
        },
        "required": ["hir_path"],
    },
}

VERIFY_PCB_BASIC_TOOL_DEF = {
    "name": "verify_pcb_basic",
    "description": (
        "Check that every schematic symbol has a corresponding PCB footprint. "
        "Returns violations for missing footprints."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hir_path": {"type": "string", "description": "Absolute path to hir.json"},
            "sch_path": {"type": "string", "description": "Absolute path to .kicad_sch"},
        },
        "required": ["hir_path", "sch_path"],
    },
}

# System prompt for the LLM
_AGENT_SYSTEM = (
    "You are a semantic design repair agent for KiCad schematics.\n"
    "You will receive semantic violation reports (missing components, missing bus nets,\n"
    "missing reset circuits, power integrity issues) and must call write_schematic_patch\n"
    "to fix them. Fix one violation per tool call. Then call the relevant verify_* tools\n"
    "to check if the fix worked. Never delete components. Prefer adding missing elements\n"
    "over modifying existing ones."
)


# ---------------------------------------------------------------------------
# _violation_fingerprint
# ---------------------------------------------------------------------------


def _violation_fingerprint(violations: list[dict]) -> str:
    """Return a deterministic sha256 fingerprint of error-severity violations.

    Warnings are excluded intentionally — they do not change between iterations
    due to LLM reasoning patterns, which would cause false stall detection.

    The result is order-independent: violations are sorted before hashing.
    Sort key uses `type` field (not `rule_id`).
    """
    errors_only = [v for v in violations if v.get("severity") == "error"]
    sorted_errors = sorted(
        errors_only,
        key=lambda v: (v.get("type", ""), v.get("message", "")),
    )
    serialized = json.dumps(
        [(v.get("type", ""), v.get("message", "")) for v in sorted_errors]
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


# ---------------------------------------------------------------------------
# SemanticAgentResult
# ---------------------------------------------------------------------------


@dataclass
class SemanticAgentResult:
    """Result returned by SemanticVerificationAgent.run()."""

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
            return "Semantic agent stalled: same violations in 2 consecutive iterations"
        if self.is_clean:
            return "Semantic agent: all violations resolved"
        msgs = " ".join(
            f"[{v.get('message', '?')}]" for v in self.violations
        )
        return f"Semantic agent: {len(self.violations)} violations remain: {msgs}"


# ---------------------------------------------------------------------------
# SemanticVerificationAgent
# ---------------------------------------------------------------------------


class SemanticVerificationAgent:
    """Bounded tool-use loop that drives LLM-guided semantic repair.

    The loop:
    1. Calls 6 verify_* tools via ToolDispatcher to get initial violations.
    2. If no violations → returns clean result immediately.
    3. Builds messages, then iterates up to max_iterations:
       a. Checks fingerprint for stall (same error-set twice in a row).
       b. Emits progress to stderr.
       c. Calls _request_fix() to ask LLM to apply one fix.
       d. Re-runs all 6 verify tools to get updated violations.
       e. If clean → returns.
    4. On cap hit → returns cap_hit=True with remaining violations.
    5. On any exception → returns cap_hit=True with exception message in violations.

    SemanticVerificationAgent.run() is synchronous — no asyncio.run() inside.
    Any async operations (ToolDispatcher.dispatch) are wrapped in concurrent.futures.
    """

    def __init__(
        self,
        sch_path: Path,
        hir_path: Path,
        gateway,       # LLMGateway — lazy import type
        dispatcher,    # ToolDispatcher — lazy import type
        max_iterations: int = 5,
    ) -> None:
        self._sch_path = sch_path
        self._hir_path = hir_path
        self._gateway = gateway
        self._dispatcher = dispatcher
        self._max_iterations = max_iterations

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> SemanticAgentResult:
        """Run the semantic repair loop synchronously.

        Returns a SemanticAgentResult — never raises.
        """
        iteration = 0
        try:
            violations = self._run_verification_via_tools()
            if not violations:
                return SemanticAgentResult(
                    violations=[],
                    iterations_used=0,
                    sch_path=self._sch_path,
                )

            messages: list[dict] = [
                {
                    "role": "user",
                    "content": f"Semantic violations found: {json.dumps(violations)}. Fix them.",
                }
            ]
            prev_fingerprint: str | None = None

            while iteration < self._max_iterations:
                iteration += 1
                fp = _violation_fingerprint(violations)
                if fp == prev_fingerprint:
                    # Violations unchanged — structural issues that require re-synthesis.
                    # Only log in verbose/debug mode to avoid alarming users.
                    import os
                    if os.environ.get("BOARDSMITH_VERBOSE"):
                        print(
                            "Semantic agent stalled: same violations in 2 consecutive iterations",
                            file=sys.stderr,
                        )
                    return SemanticAgentResult(
                        violations=violations,
                        iterations_used=iteration,
                        stalled=True,
                        sch_path=self._sch_path,
                    )
                prev_fingerprint = fp

                error_count = len(
                    [v for v in violations if v.get("severity") == "error"]
                )
                import os as _os
                if _os.environ.get("BOARDSMITH_VERBOSE"):
                    print(
                        f"Semantic iteration {iteration}/{self._max_iterations}: "
                        f"{error_count} errors remain",
                        file=sys.stderr,
                    )

                messages = self._request_fix(violations, messages)
                violations = self._run_verification_via_tools()

                if not violations:
                    return SemanticAgentResult(
                        violations=[],
                        iterations_used=iteration,
                        sch_path=self._sch_path,
                    )

            # Cap hit
            return SemanticAgentResult(
                violations=violations,
                iterations_used=iteration,
                cap_hit=True,
                sch_path=self._sch_path,
            )

        except Exception as e:
            return SemanticAgentResult(
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
            session_id="semantic-agent",
            llm_gateway=self._gateway,
            no_llm=False,
        )

    def _run_verification_via_tools(self) -> list[dict]:
        """Synchronously call all 6 verify_* tools via the ToolDispatcher.

        Dispatches verify_components, verify_connectivity, verify_bootability,
        verify_power, verify_bom, and verify_pcb_basic concurrently, then
        aggregates all violations.

        Returns the combined violations list from all 6 tool results, or [] if empty.
        """
        import asyncio
        import concurrent.futures

        from llm.types import ToolCall

        tool_inputs = {
            "hir_path": str(self._hir_path),
            "sch_path": str(self._sch_path),
        }

        tool_calls = [
            ToolCall(id=f"verif-{name}", name=name, input=tool_inputs)
            for name in [
                "verify_components",
                "verify_connectivity",
                "verify_bootability",
                "verify_power",
                "verify_bom",        # Phase 12
                "verify_pcb_basic",  # Phase 12
            ]
        ]

        ctx = self._make_context()

        # Use lambda factory so except-clause gets a fresh coroutine (avoids
        # "cannot reuse already awaited coroutine" when RuntimeError originates
        # from inside the coroutine rather than from the event loop machinery).
        def _make_dispatch():
            return self._dispatcher.dispatch(tool_calls, ctx)

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

        # Aggregate violations from all 4 result blocks
        all_violations: list[dict] = []
        for block in (result_blocks or []):
            try:
                content = block.get("content", "{}")
                data = json.loads(content) if isinstance(content, str) else content
                all_violations.extend(data.get("violations", []))
            except (json.JSONDecodeError, AttributeError):
                pass
        return all_violations

    def _request_fix(self, violations: list[dict], messages: list[dict]) -> list[dict]:
        """Ask the LLM to fix one violation and apply via ToolDispatcher.

        Returns the updated messages list (appends assistant response + tool_result).
        All LLM imports are lazy inside this method — import-clean under BOARDSMITH_NO_LLM=1.
        """
        import asyncio
        import concurrent.futures

        # Build Anthropic-format tool definitions
        tools = [
            VERIFY_COMPONENTS_TOOL_DEF,
            VERIFY_CONNECTIVITY_TOOL_DEF,
            VERIFY_BOOTABILITY_TOOL_DEF,
            VERIFY_POWER_TOOL_DEF,
            VERIFY_BOM_TOOL_DEF,       # Phase 12
            VERIFY_PCB_BASIC_TOOL_DEF, # Phase 12
            WRITE_PATCH_TOOL_DEF,
        ]

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

        # Use factory to avoid "cannot reuse already awaited coroutine" on RuntimeError.
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
