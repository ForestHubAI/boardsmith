# SPDX-License-Identifier: AGPL-3.0-or-later
"""ModifyOrchestrator — Phase 09: Brownfield Modify.

Synchronous 7-phase flow for `boardsmith modify`:
  1. Read schematic (ReadSchematicTool)
  2. LLM plan-only call (gateway.complete_sync → JSON)
  3. Display plan + prompt for confirmation
  4. (User confirms or aborts)
  5. Apply patches via WriteSchematicPatchTool
  6. Run ERCAgent
  7. Output result + HIR out-of-sync warning

All imports from boardsmith_hw, tools, and llm are lazy (inside method bodies)
so that `BOARDSMITH_NO_LLM=1 python -c 'from agents.modify_orchestrator import
ModifyOrchestrator'` exits 0.

Usage::

    from pathlib import Path
    from agents.modify_orchestrator import ModifyOrchestrator

    # gateway is an LLMGateway instance
    orch = ModifyOrchestrator(gateway=gateway, max_iterations=5)
    result = orch.run(
        sch_path=Path("board.kicad_sch"),
        instruction="add a 100nF decoupling cap on VCC",
        yes=False,  # prompt user for confirmation
    )
    if result.success:
        print("Done!")
    elif result.aborted:
        print("User aborted — no changes made.")
"""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional


# ---------------------------------------------------------------------------
# System prompt for LLM plan generation
# ---------------------------------------------------------------------------

_PLAN_SYSTEM = (
    "You are a KiCad schematic modification planner.\n"
    "Given a schematic summary and a user instruction, produce ONLY a JSON object "
    "with two keys:\n"
    "  'add': list of {lib_id, reference, value, footprint, mpn} dicts to add\n"
    "  'modify': list of {symbol_uuid, property_name, new_value, description} dicts to modify\n"
    "Both lists may be empty. Use exact KiCad library IDs (e.g. 'Device:R', 'Device:C').\n"
    "Return ONLY the JSON object, no prose, no markdown fences."
)


# ---------------------------------------------------------------------------
# ModifyResult dataclass
# ---------------------------------------------------------------------------


@dataclass
class ModifyResult:
    """Result from ModifyOrchestrator.run()."""

    success: bool
    aborted: bool = False
    backup_path: Optional[str] = None
    applied_ops: Optional[List[str]] = None
    failed_ops: Optional[List[str]] = None
    erc_clean: Optional[bool] = None
    erc_violations: Optional[List[dict]] = None
    erc_skipped: bool = False


# ---------------------------------------------------------------------------
# ModifyOrchestrator
# ---------------------------------------------------------------------------


class ModifyOrchestrator:
    """Synchronous orchestrator for `boardsmith modify` flow.

    Parameters
    ----------
    gateway:
        An ``LLMGateway`` instance. Must support ``complete_sync()``.
    max_iterations:
        Maximum ERC repair iterations passed to ERCAgent.
    """

    def __init__(self, gateway: Any, max_iterations: int = 5) -> None:
        self._gateway = gateway
        self._max_iterations = max_iterations

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        sch_path: Path,
        instruction: str,
        yes: bool = False,
    ) -> ModifyResult:
        """Execute the full 7-phase modify flow.

        Never raises — all exceptions are caught and returned as
        ``ModifyResult(success=False)``.
        """
        import click

        try:
            # Phase 1: Read schematic
            summary = self._read_schematic(sch_path)

            # Phase 2: LLM plan-only call
            plan = self._generate_plan(summary, instruction)

            # Phase 2b: Empty plan check
            if not plan.get("add") and not plan.get("modify"):
                click.echo("Nothing to modify.")
                return ModifyResult(success=False)

            # Phase 3: Display + confirm
            confirmed = self._display_and_confirm(sch_path, plan, yes)
            if not confirmed:
                return ModifyResult(success=False, aborted=True)

            # Phase 4: Convert plan to operations
            ops = self._plan_to_operations(plan)

            # Phase 5: Apply patches via WriteSchematicPatchTool
            write_result = self._apply_operations(sch_path, ops)
            bak = write_result.data.get("backup") if write_result.data else None

            if not write_result.success:
                click.echo(f"Write failed: {write_result.error}", err=True)
                if bak:
                    click.echo(f"Backup preserved at: {bak}", err=True)
                return ModifyResult(success=False, backup_path=bak)

            # Print backup path to stdout on success
            if bak:
                click.echo(f"Backup: {bak}")

            # Partial failures in operations
            if write_result.data and write_result.data.get("errors"):
                errs = write_result.data["errors"]
                applied = write_result.data.get("applied", [])
                total = len(applied) + len(errs)
                click.echo(f"⚠ {len(errs)} of {total} operations failed:", err=True)
                for e in errs:
                    click.echo(f"  {e}", err=True)

            # Phase 6: Run ERC agent
            erc_result = self._run_erc_agent(sch_path)

            # Phase 7: Output ERC result + HIR warning
            erc_clean: Optional[bool] = None
            erc_violations: List[dict] = []
            erc_skipped = False

            if self._is_kicad_cli_missing(erc_result):
                click.echo("⚠ Modifications applied, ERC skipped (kicad-cli not available)")
                erc_skipped = True
                erc_clean = None
                erc_violations = []
            elif erc_result.is_clean:
                click.echo("✓ Modifications applied, ERC clean")
                erc_clean = True
                erc_violations = []
            else:
                msgs = " ".join(
                    f"[{v.get('message', '?')}]" for v in erc_result.violations
                )
                click.echo(
                    f"⚠ Modifications applied, {len(erc_result.violations)} "
                    f"ERC violation(s) remain: {msgs}"
                )
                erc_clean = False
                erc_violations = list(erc_result.violations)

            # Always emit HIR warning
            click.echo("")
            click.echo(
                f"⚠ HIR out of sync: Run `boardsmith build --from-schematic {sch_path}`"
                " to regenerate BOM and firmware."
            )

            applied_ops = write_result.data.get("applied") if write_result.data else None
            failed_ops = write_result.data.get("errors") if write_result.data else None

            return ModifyResult(
                success=True,
                backup_path=bak,
                applied_ops=applied_ops,
                failed_ops=failed_ops,
                erc_clean=erc_clean,
                erc_violations=erc_violations,
                erc_skipped=erc_skipped,
            )

        except RuntimeError as exc:
            import click as _click
            _click.echo(f"Error: {exc}", err=True)
            return ModifyResult(success=False)
        except Exception as exc:  # noqa: BLE001
            import click as _click
            _click.echo(f"Unexpected error: {exc}", err=True)
            return ModifyResult(success=False)

    # ------------------------------------------------------------------
    # Phase helpers
    # ------------------------------------------------------------------

    def _read_schematic(self, sch_path: Path) -> dict:
        """Phase 1: Read schematic via ReadSchematicTool (lazy import)."""
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool  # noqa: PLC0415
        from tools.base import ToolContext  # noqa: PLC0415

        tool = ReadSchematicTool()
        ctx = ToolContext(session_id="modify-read", llm_gateway=self._gateway, no_llm=False)
        result = asyncio.run(tool.execute({"sch_path": str(sch_path)}, ctx))
        if not result.success:
            raise RuntimeError(f"Could not read schematic: {result.error}")
        return result.data

    def _generate_plan(self, summary: dict, instruction: str) -> dict:
        """Phase 2: LLM text call to produce a JSON plan (lazy import of types)."""
        from llm.types import Message, TaskType  # noqa: PLC0415

        prompt = (
            f"Schematic summary:\n{json.dumps(summary, indent=2)}\n\n"
            f"Instruction: {instruction}"
        )
        response = self._gateway.complete_sync(
            task=TaskType.AGENT_REASONING,
            messages=[Message(role="user", content=prompt)],
            system=_PLAN_SYSTEM,
            max_tokens=2048,
        )

        if response.skipped or not response.content.strip():
            raise RuntimeError("LLM plan generation failed or returned empty response")

        # Strip markdown fences (pitfall 1 from research)
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("```", 2)[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.rsplit("```", 1)[0].strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"LLM returned non-JSON plan: {exc}") from exc

    def _format_plan(self, sch_path: Path, plan: dict) -> str:
        """Return human-readable plan string; omits empty sections."""
        lines = [f"Modification plan for {sch_path.name}:"]

        if plan.get("add"):
            parts = [
                f"{op.get('reference', '?')} ({op.get('value', op.get('lib_id', '?'))})"
                for op in plan["add"]
            ]
            lines.append(f"  Adding:    {', '.join(parts)}")

        if plan.get("modify"):
            parts = [
                op.get("description", op.get("property_name", "?"))
                for op in plan["modify"]
            ]
            lines.append(f"  Modifying: {', '.join(parts)}")

        return "\n".join(lines)

    def _display_and_confirm(self, sch_path: Path, plan: dict, yes: bool) -> bool:
        """Phase 3: Display plan and prompt user for confirmation.

        Returns True if confirmed, False if aborted.
        """
        import click  # noqa: PLC0415

        plan_text = self._format_plan(sch_path, plan)
        click.echo(plan_text)

        if yes:
            click.echo("Applying...")
            return True

        # Block on stdin
        user_input = click.prompt(
            "\nApply modifications? [y/N]",
            default="",
            show_default=False,
        ).strip().lower()

        if user_input in ("y", "yes"):
            return True

        click.echo("Aborted — no changes made.")
        return False

    def _plan_to_operations(self, plan: dict) -> list:
        """Convert plan JSON to WriteSchematicPatchTool operation dicts."""
        ops = []
        for item in plan.get("add", []):
            ops.append({"op": "ADD_SYMBOL", **item})
        for item in plan.get("modify", []):
            ops.append({"op": "MODIFY_PROPERTY", **item})
        return ops

    def _apply_operations(self, sch_path: Path, ops: list) -> Any:
        """Phase 5: Apply patches via WriteSchematicPatchTool (lazy import)."""
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool  # noqa: PLC0415
        from tools.base import ToolContext  # noqa: PLC0415

        tool = WriteSchematicPatchTool()
        ctx = ToolContext(session_id="modify-write", llm_gateway=self._gateway, no_llm=False)
        result = asyncio.run(tool.execute({"path": str(sch_path), "operations": ops}, ctx))
        return result

    def _run_erc_agent(self, sch_path: Path) -> Any:
        """Phase 6: Run ERCAgent synchronously (lazy import)."""
        from boardsmith_hw.agent.erc_agent import ERCAgent  # noqa: PLC0415
        from llm.dispatcher import ToolDispatcher  # noqa: PLC0415
        from tools.registry import get_default_registry  # noqa: PLC0415

        registry = get_default_registry()
        dispatcher = ToolDispatcher(registry)
        agent = ERCAgent(
            sch_path=sch_path,
            gateway=self._gateway,
            dispatcher=dispatcher,
            max_iterations=self._max_iterations,
        )
        return agent.run()  # synchronous, never raises

    def _is_kicad_cli_missing(self, result: Any) -> bool:
        """Heuristic: detect kicad-cli-not-found errors in ERC result.

        Returns True if the ERC result looks like kicad-cli was unavailable
        rather than a real ERC violation.
        """
        if not result.cap_hit:
            return False
        violations = result.violations if result.violations else []
        if len(violations) != 1:
            return False
        msg = violations[0].get("message", "").lower()
        return "not found" in msg or "kicad-cli" in msg or "not available" in msg
