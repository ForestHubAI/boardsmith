# SPDX-License-Identifier: AGPL-3.0-or-later
"""Design Review Agent — holistic, agentically-driven hardware design review.

Architecture:
  1. Deterministic phase (no LLM required):
     - HIR constraint validation (electrical correctness)
     - Power budget check (overcurrent / dropout)
     - Component sanity (EOL, missing init contracts)
  2. LLM-boosted ReAct phase (optional, graceful fallback):
     - Cost optimisation opportunities
     - Layout hints
     - Reference design match + gap analysis

Result:
  DesignReviewResult.score = 0.0–1.0
  HITL required when score < 0.65 or unresolved hard errors.

Usage:
    agent = DesignReviewAgent()
    result = await agent.review(hir_dict)
    if result.hitl_required:
        # pause and show result.hitl_reason to user
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Score thresholds
# ---------------------------------------------------------------------------

SCORE_AUTO_PROCEED = 0.85    # pass without human review
SCORE_CONFIRM = 0.65         # needs quick human glance
# below SCORE_CONFIRM → mandatory HITL


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DesignIssue:
    """A single finding from the design review."""

    category: str          # "electrical" | "power" | "component" | "layout" | "cost"
    severity: str          # "error" | "warning" | "info"
    code: str              # e.g. "OVERCURRENT", "MISSING_INIT_CONTRACT"
    message: str
    suggestion: str = ""
    component_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class DesignReviewResult:
    """Complete result from one design review pass."""

    issues: list[DesignIssue] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    score: float = 0.0                 # 0.0–1.0, higher is better
    category_scores: dict[str, float] = field(default_factory=dict)
    reference_match: str | None = None
    reference_match_confidence: float = 0.0
    agent_trace: list[str] = field(default_factory=list)
    hitl_required: bool = False
    hitl_reason: str | None = None
    llm_boosted: bool = False

    # --- Derived convenience ---

    @property
    def errors(self) -> list[DesignIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[DesignIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# DesignReviewAgent
# ---------------------------------------------------------------------------

class DesignReviewAgent:
    """Reviews a hardware design HIR and returns structured feedback.

    Args:
        gateway:          LLMGateway instance (None → deterministic-only mode).
        max_agent_steps:  Max ReAct iterations for the LLM-boosted phase.
    """

    def __init__(
        self,
        gateway: Any | None = None,
        max_agent_steps: int = 8,
    ) -> None:
        self._gateway = gateway
        self._max_steps = max_agent_steps

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def review(self, hir_dict: dict[str, Any], prompt: str = "") -> DesignReviewResult:
        """Synchronous wrapper around review_async."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already inside an event loop — create a new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(asyncio.run, self.review_async(hir_dict, prompt))
                    return future.result()
            return loop.run_until_complete(self.review_async(hir_dict, prompt))
        except RuntimeError:
            return asyncio.run(self.review_async(hir_dict, prompt))

    async def review_async(
        self, hir_dict: dict[str, Any], prompt: str = ""
    ) -> DesignReviewResult:
        """Full async design review."""
        result = DesignReviewResult()

        # --- Phase 1: Deterministic checks (always run, no LLM needed) ---
        self._check_electrical_direct(hir_dict, result)
        await self._check_electrical_with_solver(hir_dict, result)
        self._check_power(hir_dict, result)
        self._check_components(hir_dict, result)

        # --- Reference design match (no LLM needed) ---
        self._match_reference_design(hir_dict, result)

        # --- Phase 2: LLM-boosted ReAct (optional) ---
        gw = self._get_gateway()
        if gw and gw.is_llm_available():
            await self._run_llm_phase(hir_dict, prompt, result, gw)

        # --- Compute final score + HITL gate ---
        self._compute_score(result)
        self._check_hitl(hir_dict, result)

        return result

    # ------------------------------------------------------------------
    # Phase 1a: Electrical checks
    # ------------------------------------------------------------------

    async def _check_electrical_with_solver(
        self, hir_dict: dict[str, Any], result: DesignReviewResult
    ) -> None:
        """Run the constraint solver via ValidateHIRTool (optional, async)."""
        try:
            from tools.tools.validate_hir import ValidateHIRTool
            from tools.base import ToolContext
            from llm.gateway import get_default_gateway
            ctx = ToolContext(
                session_id="design_review_electrical",
                llm_gateway=self._get_gateway() or get_default_gateway(),
            )
            tool = ValidateHIRTool()
            tr = await tool.execute({"hir": hir_dict}, ctx)
            if not tr.success:
                return  # already covered by direct check
            report = tr.data or {}
            for diag in report.get("diagnostics", []):
                code = diag.get("constraint_id", "UNKNOWN_CONSTRAINT")
                # Avoid duplicate issues from the direct check
                if any(i.code == code for i in result.issues):
                    continue
                result.issues.append(DesignIssue(
                    category="electrical",
                    severity="error" if diag.get("status") == "FAIL" else "warning",
                    code=code,
                    message=diag.get("message", ""),
                    suggestion=diag.get("suggestion", ""),
                    context=diag,
                ))
        except Exception as exc:
            log.debug("Solver-based electrical check skipped: %s", exc)

    def _check_electrical_direct(
        self, hir_dict: dict[str, Any], result: DesignReviewResult
    ) -> None:
        """Deterministic electrical checks without the constraint solver."""
        comps = hir_dict.get("components", [])
        bus_contracts = hir_dict.get("bus_contracts", [])

        # I2C address conflict check
        i2c_addrs: dict[str, str] = {}
        for bc in bus_contracts:
            if bc.get("bus_type", "").upper() != "I2C":
                continue
            for slave in bc.get("slaves", []):
                addr = slave.get("address", "")
                cid = slave.get("component_id", "")
                if addr and addr in i2c_addrs:
                    result.issues.append(DesignIssue(
                        category="electrical",
                        severity="error",
                        code="I2C_ADDRESS_CONFLICT",
                        message=f"I2C address {addr} conflict: {i2c_addrs[addr]} and {cid}",
                        suggestion="Use TCA9548A I2C mux or choose components with different addresses",
                        component_id=cid,
                    ))
                elif addr:
                    i2c_addrs[addr] = cid

        # Missing MCU check
        mcu_roles = [c for c in comps if c.get("role", "").lower() == "mcu"]
        if not mcu_roles:
            result.issues.append(DesignIssue(
                category="electrical",
                severity="error",
                code="NO_MCU",
                message="Design has no MCU component",
                suggestion="Add a microcontroller (e.g. ESP32-WROOM-32, RP2040)",
            ))

    # ------------------------------------------------------------------
    # Phase 1b: Power checks
    # ------------------------------------------------------------------

    def _check_power(self, hir_dict: dict[str, Any], result: DesignReviewResult) -> None:
        """Run power budget analysis and add issues."""
        try:
            from boardsmith_hw.power_budget import calculate_power_budget
            budget = calculate_power_budget(hir_dict)
            for rail in budget.rails:
                if not rail.passes:
                    margin = (
                        f"{rail.margin_ma:.0f} mA remaining"
                        if rail.margin_ma is not None else "unknown"
                    )
                    result.issues.append(DesignIssue(
                        category="power",
                        severity="error",
                        code="OVERCURRENT",
                        message=(
                            f"Rail '{rail.rail_name}': "
                            f"{rail.total_load_ma:.0f} mA load × 1.20 > "
                            f"{rail.regulator_max_ma:.0f} mA ({rail.regulator_mpn})"
                        ),
                        suggestion=(
                            f"Reduce load or switch to a higher-current regulator. "
                            f"AMS1117-3.3 supports 800 mA."
                        ),
                    ))
                elif rail.regulator_max_ma and rail.utilisation_pct and rail.utilisation_pct > 70:
                    result.issues.append(DesignIssue(
                        category="power",
                        severity="warning",
                        code="HIGH_POWER_UTILISATION",
                        message=(
                            f"Rail '{rail.rail_name}': "
                            f"{rail.utilisation_pct:.0f}% of {rail.regulator_mpn} used "
                            f"({rail.total_load_ma:.0f}/{rail.regulator_max_ma:.0f} mA)"
                        ),
                        suggestion="Consider a higher-capacity regulator for headroom",
                    ))
        except ImportError:
            log.debug("power_budget module not available — skipping power check")
        except Exception as exc:
            log.debug("Power check failed: %s", exc)

    # ------------------------------------------------------------------
    # Phase 1c: Component checks
    # ------------------------------------------------------------------

    def _check_components(self, hir_dict: dict[str, Any], result: DesignReviewResult) -> None:
        """Check component quality: EOL, missing init contracts, cost outliers."""
        comps = hir_dict.get("components", [])

        try:
            from knowledge.components import find_by_mpn
        except ImportError:
            find_by_mpn = None  # type: ignore[assignment]

        for comp in comps:
            mpn = comp.get("mpn", "")
            cid = comp.get("id", mpn)
            role = comp.get("role", "").lower()

            if role in ("passive", "power", "connector"):
                continue

            # Check EOL status
            status = comp.get("status", "active")
            if status in ("eol", "nrnd", "discontinued"):
                result.issues.append(DesignIssue(
                    category="component",
                    severity="warning",
                    code="EOL_COMPONENT",
                    message=f"{mpn} status is '{status}' — may be hard to source",
                    suggestion="Find an in-production alternative",
                    component_id=cid,
                ))

            # Check init contract (critical ICs should have one)
            if role in ("mcu", "sensor") and find_by_mpn:
                db_entry = find_by_mpn(mpn)
                if db_entry and not db_entry.get("init_contract_coverage", True):
                    result.issues.append(DesignIssue(
                        category="component",
                        severity="info",
                        code="MISSING_INIT_CONTRACT",
                        message=f"{mpn}: no init sequence in knowledge DB",
                        suggestion="Manually verify initialization sequence from datasheet",
                        component_id=cid,
                    ))

        # Total BOM cost estimate
        total_cost = sum(
            float(c.get("unit_cost_usd", 0.0)) for c in comps
        )
        if total_cost > 50.0:
            result.issues.append(DesignIssue(
                category="cost",
                severity="info",
                code="HIGH_BOM_COST",
                message=f"Estimated BOM cost ${total_cost:.2f} is high",
                suggestion="Run find_component_alternatives to identify cost savings",
            ))

    # ------------------------------------------------------------------
    # Reference design matching
    # ------------------------------------------------------------------

    def _match_reference_design(
        self, hir_dict: dict[str, Any], result: DesignReviewResult
    ) -> None:
        try:
            from knowledge.reference_designs import ReferenceDesignLibrary
            lib = ReferenceDesignLibrary()
            best, conf = lib.find_closest(hir_dict)
            if best and conf >= 0.40:
                result.reference_match = best.name
                result.reference_match_confidence = conf
                if best.notes:
                    for note in best.notes[:3]:
                        result.recommendations.append(
                            f"[Reference: {best.name}] {note}"
                        )
        except ImportError:
            pass
        except Exception as exc:
            log.debug("Reference matching failed: %s", exc)

    # ------------------------------------------------------------------
    # Phase 2: LLM ReAct boost
    # ------------------------------------------------------------------

    async def _run_llm_phase(
        self,
        hir_dict: dict[str, Any],
        prompt: str,
        result: DesignReviewResult,
        gateway: Any,
    ) -> None:
        """Run a ReAct loop for advisory checks (cost, layout, alternatives)."""
        from agents.react_loop import run_react_loop
        from llm.types import TaskType
        from tools.base import ToolContext
        from tools.tools.query_knowledge import QueryKnowledgeTool
        from tools.tools.find_component_alternatives import FindComponentAlternativesTool
        from tools.tools.analyze_power_design import AnalyzePowerDesignTool

        ctx = ToolContext(
            session_id="design_review_agent",
            llm_gateway=gateway,
        )

        tools: dict[str, Any] = {
            "query_knowledge": QueryKnowledgeTool(),
            "analyze_power_design": AnalyzePowerDesignTool(),
            "find_component_alternatives": FindComponentAlternativesTool(),
        }

        comps = hir_dict.get("components", [])
        comp_summary = ", ".join(c.get("mpn", "?") for c in comps[:8])
        buses = hir_dict.get("bus_contracts", [])
        bus_summary = ", ".join(
            f"{bc.get('bus_type','?')} ({bc.get('bus_name','?')})" for bc in buses[:4]
        )

        task = (
            f"Review this hardware design for quality issues and improvements:\n"
            f"  Components: {comp_summary}\n"
            f"  Buses: {bus_summary or 'none'}\n"
            f"  User intent: {prompt or 'not specified'}\n\n"
            f"Please:\n"
            f"1) Run analyze_power_design to check the power budget.\n"
            f"2) For each active component (not passives), check if there are cheaper "
            f"   or lower-power alternatives (find_component_alternatives).\n"
            f"3) Identify any layout concerns (RF components, decoupling, etc.).\n"
            f"4) Return a JSON with keys: "
            f"'issues' (list of {{category, severity, code, message, suggestion}}), "
            f"'recommendations' (list of strings)."
        )

        hir_compact = json.dumps(hir_dict, ensure_ascii=False, default=str)
        if len(hir_compact) > 3000:
            hir_compact = hir_compact[:3000] + "...[truncated]"

        full_task = f"{task}\n\nHIR (compact):\n{hir_compact}"

        react_result = await run_react_loop(
            task=full_task,
            tools=tools,
            gateway=gateway,
            context=ctx,
            max_steps=self._max_steps,
            task_type=TaskType.AGENT_REASONING,
        )

        result.agent_trace = [
            f"Step {s.step_num}: {s.action}" for s in react_result.steps
        ]

        if react_result.success and react_result.answer:
            result.llm_boosted = True
            self._parse_agent_answer(react_result.answer, result)

    def _parse_agent_answer(self, answer: str, result: DesignReviewResult) -> None:
        """Extract structured issues and recommendations from the agent's answer."""
        try:
            m = re.search(r"\{[\s\S]+\}", answer)
            if m:
                data = json.loads(m.group())
                for raw_issue in data.get("issues", []):
                    if isinstance(raw_issue, dict):
                        result.issues.append(DesignIssue(
                            category=raw_issue.get("category", "electrical"),
                            severity=raw_issue.get("severity", "info"),
                            code=raw_issue.get("code", "LLM_REVIEW"),
                            message=raw_issue.get("message", ""),
                            suggestion=raw_issue.get("suggestion", ""),
                            component_id=raw_issue.get("component_id"),
                        ))
                for rec in data.get("recommendations", []):
                    if isinstance(rec, str) and rec:
                        result.recommendations.append(rec)
        except (json.JSONDecodeError, ValueError):
            # LLM returned plain text — add as an info recommendation
            if len(answer) > 20:
                result.recommendations.append(f"[LLM] {answer[:300]}")

    # ------------------------------------------------------------------
    # Score + HITL
    # ------------------------------------------------------------------

    def _compute_score(self, result: DesignReviewResult) -> None:
        """Compute 0.0–1.0 score from issues.

        Weights:
          error   → -0.20 per issue (cap at -0.80)
          warning → -0.05 per issue (cap at -0.30)
          info    → no penalty
        Bonus: reference_match_confidence × 0.05
        """
        errors = len(result.errors)
        warnings = len(result.warnings)

        penalty = min(errors * 0.20, 0.80) + min(warnings * 0.05, 0.30)
        bonus = result.reference_match_confidence * 0.05
        score = max(0.0, min(1.0, 1.0 - penalty + bonus))

        result.score = round(score, 3)

        # Per-category scores
        cats = set(i.category for i in result.issues)
        for cat in cats:
            cat_errors = sum(1 for i in result.issues if i.category == cat and i.severity == "error")
            cat_warns = sum(1 for i in result.issues if i.category == cat and i.severity == "warning")
            cat_penalty = min(cat_errors * 0.20, 0.80) + min(cat_warns * 0.05, 0.30)
            result.category_scores[cat] = round(max(0.0, 1.0 - cat_penalty), 3)

    def _check_hitl(self, hir_dict: dict[str, Any], result: DesignReviewResult) -> None:
        """Determine if human review is required."""
        reasons: list[str] = []

        # Low score
        if result.score < SCORE_CONFIRM:
            reasons.append(f"design score {result.score:.2f} < {SCORE_CONFIRM}")

        # Hard errors
        if result.errors:
            reasons.append(f"{len(result.errors)} unresolved error(s)")

        # Safety-critical actuators
        comps = hir_dict.get("components", [])
        for c in comps:
            role = c.get("role", "").lower()
            if role in ("actuator", "motor", "relay", "valve"):
                reasons.append(f"safety-critical component: {c.get('mpn', role)}")
                break

        if reasons:
            result.hitl_required = True
            result.hitl_reason = "; ".join(reasons)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_gateway(self) -> Any:
        if self._gateway:
            return self._gateway
        try:
            from llm.gateway import get_default_gateway
            return get_default_gateway()
        except ImportError:
            return None
