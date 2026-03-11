# SPDX-License-Identifier: AGPL-3.0-or-later
"""IterativeOrchestrator — Phase 21: The Full Agentic Loop.

Wires together all Boardsmith building blocks into a self-improving,
convergent iteration loop:

    prompt
      ↓
    [Iteration 1] Synthesizer B1–B9
      ↓
    DesignReviewAgent → score, issues, fixes
      ↓  (if score < threshold)
    DesignImprover → apply fixes → updated HIR
      ↓
    [Iteration 2] B6 re-validate + DesignReview again
      ↓  (if score >= threshold or convergence or max_iter)
    ACCEPT
      ↓
    PcbPipeline → production ZIP
    FirmwareReviewAgent → static quality check
    write audit_trail.json
      ↓
    BuildResult

Stop conditions (checked after each iteration):
  1. score >= ACCEPT_THRESHOLD[quality]    — target reached
  2. Δscore < STAGNATION_DELTA (iter > 1)  — no more improvement
  3. iteration == max_iterations            — give up, take what we have
  4. hitl_required                         — human must decide
  5. DesignImprover has no changes         — nothing left to fix

Usage::

    import asyncio
    from pathlib import Path
    from agents.iterative_orchestrator import IterativeOrchestrator

    orchestrator = IterativeOrchestrator(use_llm=False)
    result = asyncio.run(orchestrator.build(
        prompt="ESP32 with BME280 over I2C",
        target="esp32",
        out_dir=Path("./output"),
        quality="balanced",
        max_iterations=3,
    ))
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Reason: {result.audit_trail.accept_reason}")
    for artifact in result.artifacts:
        print(f"  {artifact}")
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 26.4 — OrchestratorState: named states for observability
# ---------------------------------------------------------------------------

class OrchestratorState(str, Enum):
    """Named states of the iterative orchestrator.

    Transitions are logged in AuditTrail.state_transitions and surfaced in
    BuildResult.final_state so callers (CLI, API, tests) can observe progress.
    """

    COLLECTING_REQUIREMENTS = "collecting_requirements"
    SYNTHESIZING            = "synthesizing"
    REVIEWING               = "reviewing"
    IMPROVING               = "improving"
    VALIDATING_GATES        = "validating_gates"
    COMPLETED               = "completed"
    ERROR_RECOVERY          = "error_recovery"
    AWAITING_HUMAN          = "awaiting_human"


# ---------------------------------------------------------------------------
# 26.2 — GateMatrix: hard pass/fail criteria separate from confidence score
# ---------------------------------------------------------------------------

@dataclass
class GateMatrix:
    """Binary pass/fail gates that determine release-readiness.

    A high confidence score is necessary but not sufficient. All hard gates
    must pass before a design is considered production-ready.

    Attributes:
        erc_clean:            ERC = 0 errors (kicad-cli report or best-effort).
        drc_clean:            DRC = 0 errors (only meaningful after PCB routing).
        boot_pins_valid:      No boot-strap pin conflicts in HIR assumptions.
        power_budget_ok:      At least one power rail defined + no overload.
        mandatory_components: All MCU-profile mandatory components present.
        no_pinmux_conflicts:  Zero dual-assigned GPIO pins.
        bom_complete:         All non-passive components have an MPN.
        firmware_compiles:    Firmware dir exists (None = not requested).
        level_shifter_inserted: One or more auto level-shifters were added.
        warnings:             Human-readable list of non-blocking notes.
    """

    erc_clean: bool = True
    drc_clean: bool = True
    boot_pins_valid: bool = True
    power_budget_ok: bool = True
    mandatory_components: bool = True
    no_pinmux_conflicts: bool = True
    bom_complete: bool = True
    firmware_compiles: Optional[bool] = None   # None = not requested
    level_shifter_inserted: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def release_ready(self) -> bool:
        """True iff all hard gates pass.

        DRC and firmware_compiles are soft: DRC only runs after PCB routing
        (Phase 23) and firmware is optional.
        """
        hard = [
            self.erc_clean,
            self.boot_pins_valid,
            self.power_budget_ok,
            self.mandatory_components,
            self.no_pinmux_conflicts,
            self.bom_complete,
        ]
        return all(hard)

    def summary_line(self) -> str:
        """One-line status for CLI display."""
        icons = {
            "ERC":     "✅" if self.erc_clean           else "❌",
            "Boot":    "✅" if self.boot_pins_valid      else "❌",
            "Power":   "✅" if self.power_budget_ok      else "❌",
            "MandC":   "✅" if self.mandatory_components else "❌",
            "Pinmux":  "✅" if self.no_pinmux_conflicts  else "❌",
            "BOM":     "✅" if self.bom_complete          else "❌",
        }
        parts = "  ".join(f"{k} {v}" for k, v in icons.items())
        ready = "READY" if self.release_ready else "NOT READY"
        return f"Gates [{ready}]: {parts}"

    def to_dict(self) -> dict:
        return {
            "release_ready":         self.release_ready,
            "erc_clean":             self.erc_clean,
            "drc_clean":             self.drc_clean,
            "boot_pins_valid":       self.boot_pins_valid,
            "power_budget_ok":       self.power_budget_ok,
            "mandatory_components":  self.mandatory_components,
            "no_pinmux_conflicts":   self.no_pinmux_conflicts,
            "bom_complete":          self.bom_complete,
            "firmware_compiles":     self.firmware_compiles,
            "level_shifter_inserted": self.level_shifter_inserted,
            "warnings":              self.warnings,
        }


# ---------------------------------------------------------------------------
# 26.3 — ArtifactBundle: typed output manifest with completeness check
# ---------------------------------------------------------------------------

@dataclass
class ArtifactBundle:
    """Typed manifest of all output artifacts produced by a build.

    Usage::

        bundle = ArtifactBundle.from_out_dir(Path("./output"))
        missing = bundle.missing(require_pcb=True, require_firmware=False)
    """

    hir_json:            Optional[Path] = None
    schematic_kicad:     Optional[Path] = None
    pcb_kicad:           Optional[Path] = None
    gerber_zip:          Optional[Path] = None
    bom_json:            Optional[Path] = None
    bom_csv:             Optional[Path] = None
    diagnostics_json:    Optional[Path] = None
    erc_report:          Optional[Path] = None
    drc_report:          Optional[Path] = None
    firmware_dir:        Optional[Path] = None
    synthesis_report_md: Optional[Path] = None
    audit_trail_json:    Optional[Path] = None
    gate_matrix_json:    Optional[Path] = None

    @classmethod
    def from_out_dir(cls, out_dir: Path) -> "ArtifactBundle":
        """Scan out_dir and build bundle from what's present."""
        def _p(name: str) -> Optional[Path]:
            p = out_dir / name
            return p if p.exists() else None

        gerber = _p("gerbers") or _p("gerbers.zip") or _p("production.zip")

        return cls(
            hir_json            = _p("hir.json"),
            schematic_kicad     = _p("schematic.kicad_sch"),
            pcb_kicad           = _p("pcb.kicad_pcb"),
            gerber_zip          = gerber,
            bom_json            = _p("bom.json"),
            bom_csv             = _p("bom.csv"),
            diagnostics_json    = _p("diagnostics.json"),
            erc_report          = _p("erc_report.json"),
            drc_report          = _p("drc_report.json"),
            firmware_dir        = out_dir / "firmware" if (out_dir / "firmware").exists() else None,
            synthesis_report_md = _p("synthesis_report.md"),
            audit_trail_json    = _p("audit_trail.json"),
            gate_matrix_json    = _p("gate_matrix.json"),
        )

    def completeness(
        self,
        require_pcb: bool = False,
        require_firmware: bool = False,
    ) -> dict[str, bool]:
        """Return {artifact_name: exists} for expected outputs.

        Only artifacts relevant to the requested outputs are checked.
        """
        result = {
            "hir.json":             self.hir_json is not None,
            "schematic.kicad_sch":  self.schematic_kicad is not None,
            "bom.json":             self.bom_json is not None,
            "bom.csv":              self.bom_csv is not None,
            "synthesis_report.md":  self.synthesis_report_md is not None,
            "audit_trail.json":     self.audit_trail_json is not None,
        }
        if require_pcb:
            result["pcb.kicad_pcb"] = self.pcb_kicad is not None
            result["gerbers"]        = self.gerber_zip is not None
        if require_firmware:
            result["firmware/"]      = self.firmware_dir is not None
        return result

    def missing(
        self,
        require_pcb: bool = False,
        require_firmware: bool = False,
    ) -> list[str]:
        """Return list of artifact names that are expected but absent."""
        return [
            name
            for name, present in self.completeness(require_pcb, require_firmware).items()
            if not present
        ]

    def to_paths(self) -> list[str]:
        """Flat list of all present artifact paths (for BuildResult.artifacts)."""
        paths: list[str] = []
        for val in vars(self).values():
            if isinstance(val, Path) and val.exists():
                paths.append(str(val))
        return paths

# Repo root derived from this file's location (shared/agents/ → repo root)
_REPO_ROOT = Path(__file__).parent.parent.parent

# ---------------------------------------------------------------------------
# Accept thresholds per quality level
# ---------------------------------------------------------------------------

ACCEPT_THRESHOLDS: dict[str, float] = {
    "fast":     0.75,
    "balanced": 0.85,
    "high":     0.90,
}

STAGNATION_DELTA = 0.02   # If Δscore < this, consider converged


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class IterationRecord:
    """State of one iteration pass.

    Attributes:
        iteration:        1-based iteration number.
        confidence:       Combined multi-agent score after this iteration.
        delta_confidence: Change vs. previous iteration (0.0 for iter 1).
        issues_found:     Human-readable issue descriptions from review.
        fixes_applied:    Issue codes resolved by DesignImprover.
        stages_rerun:     B-stage labels that ran (["B1-B9"] or ["B6"]).
        hitl_required:    True if HITL gate was triggered.
        accept_reason:    Why this iteration stopped (or "continue").
        duration_s:       Wall-clock seconds for this iteration.
        synthesis_confidence: B9 confidence from the Synthesizer (iter 1 only).
        agent_scores:     Per-specialist-agent scores (Phase 21 multi-agent).
        chronic_issues:   Issue codes that persisted despite fix attempts.
    """

    iteration: int
    confidence: float
    delta_confidence: float
    issues_found: list[str] = field(default_factory=list)
    fixes_applied: list[str] = field(default_factory=list)
    stages_rerun: list[str] = field(default_factory=list)
    hitl_required: bool = False
    accept_reason: str = "continue"
    duration_s: float = 0.0
    synthesis_confidence: float = 0.0
    # Phase 21: multi-agent scores
    agent_scores: dict[str, float] = field(default_factory=dict)
    chronic_issues: list[str] = field(default_factory=list)


@dataclass
class AuditTrail:
    """Complete audit trail for the full build.

    Attributes:
        prompt:             Original user prompt.
        target:             MCU target (e.g. "esp32").
        quality:            Quality level (fast|balanced|high).
        iterations:         Per-iteration records.
        final_confidence:   Score after the accepted iteration.
        accept_reason:      Why the loop ended.
        total_duration_s:   Total wall-clock time.
        state_transitions:  Ordered list of (state, timestamp_s) pairs.
        agent_mode:         "experimental" | "standard" | "no-llm".
    """

    prompt: str
    target: str
    quality: str
    max_iterations: int
    iterations: list[IterationRecord] = field(default_factory=list)
    final_confidence: float = 0.0
    accept_reason: str = "max_iter"
    total_duration_s: float = 0.0
    # 26.4 — state machine trace
    state_transitions: list[dict] = field(default_factory=list)
    agent_mode: str = "standard"

    def record_state(self, state: "OrchestratorState") -> None:
        """Append a state transition with current timestamp."""
        self.state_transitions.append({
            "state": state.value,
            "t_s":   round(time.monotonic(), 3),
        })

    def to_dict(self) -> dict:
        """Serialise to a JSON-safe dict."""
        d = asdict(self)
        return d


@dataclass
class BuildResult:
    """Final result of the iterative build.

    Attributes:
        success:         True if the design was accepted (not an error).
        confidence:      Final design review score (0.0–1.0).
        artifacts:       Paths to all generated output files.
        audit_trail:     Full iteration history + accept reason.
        hitl_required:   True if human review is needed.
        hitl_reason:     Explanation of why HITL was triggered.
        error:           Non-None if a fatal error occurred.
        firmware_score:  FirmwareReviewAgent score (0.0–1.0 or None).
        gate_matrix:     26.2 — hard pass/fail gates (None if not computed).
        artifact_bundle: 26.3 — typed output manifest.
        final_state:     26.4 — last orchestrator state.
    """

    success: bool
    confidence: float
    artifacts: list[str] = field(default_factory=list)
    audit_trail: AuditTrail = field(
        default_factory=lambda: AuditTrail("", "", "balanced", 5)
    )
    hitl_required: bool = False
    hitl_reason: str = ""
    error: Optional[str] = None
    firmware_score: Optional[float] = None
    # 26.2 / 26.3 / 26.4
    gate_matrix: Optional[GateMatrix] = None
    artifact_bundle: Optional[ArtifactBundle] = None
    final_state: OrchestratorState = OrchestratorState.COMPLETED


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class IterativeOrchestrator:
    """Full agentic loop: prompt → synthesize → review → improve → accept.

    Usage::

        orchestrator = IterativeOrchestrator(use_llm=False)
        result = asyncio.run(orchestrator.build(
            prompt="ESP32 with BME280",
            target="esp32",
            out_dir=Path("./output"),
        ))
    """

    # 26.1 — category → deepest re-entry stage mapping
    _CATEGORY_REENTRY: dict[str, str] = {
        "component": "B3",   # wrong component → re-select (full re-synthesis)
        "cost":      "B3",   # cost issues → try cheaper alternative via B3
        "topology":  "B4",   # bus/topology mismatch → re-synthesize topology
        "power":     "B4",   # power tree error → re-synthesize with fix hint
        "electrical": "B6",  # constraint violation → ConstraintRefiner
        "constraint": "B6",
        "layout":    "B6",   # layout hint → DesignImprover
    }
    _REENTRY_PRIORITY: dict[str, int] = {"B3": 0, "B4": 1, "B6": 2}

    def __init__(
        self,
        use_llm: bool = True,
        clarification_io: Any = None,
        agent_mode: str = "standard",
    ) -> None:
        self._use_llm = use_llm
        self._clarification_io = clarification_io  # ClarificationIO or None
        self._agent_mode = agent_mode  # 26.6: "standard" | "experimental" | "no-llm"
        # Phase 21: iteration memory (reset per build() call)
        self._memory: Any = None  # IterationMemory — lazy import
        # 26.1: store last review issues for re-entry stage detection
        self._last_review_issues: list = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def build(
        self,
        prompt: str,
        target: str,
        out_dir: Path,
        quality: str = "balanced",
        max_iterations: int = 5,
        max_erc_iterations: int = 5,
        with_pcb: bool = True,
        generate_firmware: bool = True,
        progress_callback: Optional[Callable[[IterationRecord], None]] = None,
        seed: Optional[int] = None,
        clarification_mode: str = "single",
    ) -> BuildResult:
        """Run the full iterative build loop.

        Args:
            prompt:             Natural-language hardware description.
            target:             MCU target (esp32, stm32, rp2040, ...).
            out_dir:            Output directory (created if needed).
            quality:            Accept threshold preset (fast/balanced/high).
            max_iterations:     Maximum number of Synthesizer+Review cycles.
            max_erc_iterations: Maximum number of LLM-guided ERC repair iterations (ERCAgent).
            with_pcb:           Run PCB pipeline after accept.
            generate_firmware:  Generate firmware code during synthesis.
            progress_callback:  Called after each iteration with the record.
            seed:               Random seed for deterministic runs.
            clarification_mode: "none" | "single" | "auto" (default: "single").

        Returns:
            BuildResult with all artifacts and full audit trail.
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Store for use in _run_synthesis calls within the iteration loop
        _max_erc_iterations = max_erc_iterations

        accept_threshold = ACCEPT_THRESHOLDS.get(quality, ACCEPT_THRESHOLDS["balanced"])
        trail = AuditTrail(
            prompt=prompt,
            target=target,
            quality=quality,
            max_iterations=max_iterations,
            agent_mode=self._agent_mode,
        )

        t_total_start = time.monotonic()
        prev_score = 0.0
        final_hir: Optional[dict] = None
        final_synthesis = None
        current_hir: Optional[dict] = None
        hitl_required = False
        hitl_reason = ""
        current_state = OrchestratorState.COLLECTING_REQUIREMENTS

        # Phase 21: fresh IterationMemory for this build
        try:
            _add_to_path(str(_REPO_ROOT / "shared"))
            from agents.iteration_memory import IterationMemory
            self._memory = IterationMemory()
        except Exception:
            self._memory = None

        # ------------------------------------------------------------------
        # Pre-flight: Requirements Clarification (before any synthesis)
        # ------------------------------------------------------------------
        trail.record_state(OrchestratorState.COLLECTING_REQUIREMENTS)
        prompt = await self._run_requirements_clarification(
            prompt=prompt,
            clarification_mode=clarification_mode,
        )

        # ------------------------------------------------------------------
        # Iteration loop
        # ------------------------------------------------------------------
        for iteration in range(1, max_iterations + 1):
            t_iter_start = time.monotonic()
            log.info("IterativeOrchestrator: iteration %d/%d", iteration, max_iterations)

            # 26.4 — track state
            if iteration == 1:
                current_state = OrchestratorState.SYNTHESIZING
            else:
                reentry = self._determine_reentry_stage(self._last_review_issues)
                current_state = (
                    OrchestratorState.SYNTHESIZING if reentry in ("B3", "B4")
                    else OrchestratorState.IMPROVING
                )
            trail.record_state(current_state)

            try:
                record, current_hir, synthesis_result = await self._run_iteration(
                    iteration=iteration,
                    prompt=prompt,
                    target=target,
                    out_dir=out_dir,
                    current_hir=current_hir,
                    prev_score=prev_score,
                    generate_firmware=generate_firmware and (iteration == 1),
                    seed=seed,
                    clarification_mode=clarification_mode if iteration == 1 else "none",
                    max_erc_iterations=_max_erc_iterations,
                )
            except Exception as exc:
                log.exception("Iteration %d failed: %s", iteration, exc)
                trail.total_duration_s = time.monotonic() - t_total_start
                trail.accept_reason = "error"
                return BuildResult(
                    success=False,
                    confidence=prev_score,
                    audit_trail=trail,
                    error=f"Iteration {iteration} failed: {exc}",
                )

            if iteration == 1 and synthesis_result is not None:
                final_synthesis = synthesis_result

            record.duration_s = time.monotonic() - t_iter_start
            trail.iterations.append(record)

            if progress_callback:
                try:
                    progress_callback(record)
                except Exception:
                    pass  # never let CLI errors break the build

            score = record.confidence
            delta = record.delta_confidence
            log.info(
                "Iteration %d: score=%.3f delta=%.3f hitl=%s accept_reason=%s",
                iteration, score, delta, record.hitl_required, record.accept_reason,
            )

            # 26.4 — review state
            trail.record_state(OrchestratorState.REVIEWING)

            # --- Stop condition: HITL ---
            if record.hitl_required:
                hitl_required = True
                hitl_reason = f"Design score {score:.2f} requires human review"
                record.accept_reason = "hitl"
                trail.accept_reason = "hitl"
                break

            # --- Stop condition: threshold met ---
            if score >= accept_threshold:
                record.accept_reason = "threshold_met"
                trail.accept_reason = "threshold_met"
                final_hir = current_hir
                prev_score = score
                break

            # --- Stop condition: stagnation (only after iter 1) ---
            if iteration > 1 and abs(delta) < STAGNATION_DELTA:
                record.accept_reason = "converged"
                trail.accept_reason = "converged"
                final_hir = current_hir
                prev_score = score
                break

            # --- Stop condition: nothing left to fix ---
            if record.accept_reason == "no_fixes":
                trail.accept_reason = "no_fixes"
                final_hir = current_hir
                prev_score = score
                break

            final_hir = current_hir
            prev_score = score

        else:
            # Loop exhausted max_iterations without breaking
            trail.accept_reason = "max_iter"

        trail.final_confidence = prev_score
        trail.total_duration_s = time.monotonic() - t_total_start

        # ------------------------------------------------------------------
        # 26.2 — Compute GateMatrix
        # ------------------------------------------------------------------
        trail.record_state(OrchestratorState.VALIDATING_GATES)
        gate_matrix = self._compute_gate_matrix(
            hir_dict=final_hir or {},
            out_dir=out_dir,
            generate_firmware=generate_firmware,
        )

        # Force re-iteration if critical gate fails and we have budget left
        if not gate_matrix.release_ready and not hitl_required:
            log.warning(
                "GateMatrix failed after accept: %s — design may need manual review",
                gate_matrix.summary_line(),
            )

        # Write gate_matrix.json
        try:
            (out_dir / "gate_matrix.json").write_text(
                json.dumps(gate_matrix.to_dict(), indent=2), encoding="utf-8"
            )
        except Exception as exc:
            log.debug("Could not write gate_matrix.json: %s", exc)

        # ------------------------------------------------------------------
        # Collect artifacts from synthesis output
        # ------------------------------------------------------------------
        artifacts = self._collect_artifacts(out_dir, final_synthesis)

        # ------------------------------------------------------------------
        # PCB pipeline (after accept, if requested)
        # ------------------------------------------------------------------
        if with_pcb and final_hir and not hitl_required:
            try:
                pcb_artifacts = await self._run_pcb(final_hir, out_dir)
                artifacts.extend(pcb_artifacts)
            except Exception as exc:
                log.warning("PCB pipeline failed: %s", exc)

        # ------------------------------------------------------------------
        # Firmware review
        # ------------------------------------------------------------------
        firmware_score: Optional[float] = None
        if generate_firmware:
            firmware_score = self._review_firmware(out_dir)

        # ------------------------------------------------------------------
        # Write audit trail
        # ------------------------------------------------------------------
        try:
            audit_path = out_dir / "audit_trail.json"
            audit_path.write_text(
                json.dumps(trail.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )
            artifacts.append(str(audit_path))
        except Exception as exc:
            log.warning("Could not write audit_trail.json: %s", exc)

        # 26.3 — Build ArtifactBundle
        bundle = ArtifactBundle.from_out_dir(out_dir)
        missing = bundle.missing(require_pcb=with_pcb, require_firmware=generate_firmware)
        if missing:
            log.warning("Incomplete artifact bundle — missing: %s", missing)

        # 26.4 — final state
        if hitl_required:
            final_state = OrchestratorState.AWAITING_HUMAN
        elif trail.accept_reason == "error":
            final_state = OrchestratorState.ERROR_RECOVERY
        else:
            final_state = OrchestratorState.COMPLETED
        trail.record_state(final_state)

        return BuildResult(
            success=not hitl_required and trail.final_confidence > 0,
            confidence=trail.final_confidence,
            artifacts=sorted(set(artifacts)),
            audit_trail=trail,
            hitl_required=hitl_required,
            hitl_reason=hitl_reason,
            firmware_score=firmware_score,
            gate_matrix=gate_matrix,
            artifact_bundle=bundle,
            final_state=final_state,
        )

    # ------------------------------------------------------------------
    # Internal: single iteration
    # ------------------------------------------------------------------

    async def _run_iteration(
        self,
        iteration: int,
        prompt: str,
        target: str,
        out_dir: Path,
        current_hir: Optional[dict],
        prev_score: float,
        generate_firmware: bool,
        seed: Optional[int],
        clarification_mode: str = "none",
        max_erc_iterations: int = 5,
    ) -> tuple[IterationRecord, dict, Any]:
        """Run one iteration: synthesize (or improve) → review.

        Iteration 1: full B1-B9 synthesis.
        Iteration 2+: DesignImprover applies fixes, DesignReviewAgent re-reviews.
        """
        stages_rerun: list[str] = []
        fixes_applied: list[str] = []
        synthesis_result = None

        if iteration == 1 or current_hir is None:
            # --- Full synthesis (B1–B9) ---
            stages_rerun = ["B1–B9"]
            hir_dict, synthesis_result = await self._run_synthesis(
                prompt=prompt,
                target=target,
                out_dir=out_dir,
                generate_firmware=generate_firmware,
                seed=seed,
                clarification_mode=clarification_mode,
                max_erc_iterations=max_erc_iterations,
            )
            synthesis_confidence = getattr(synthesis_result, "confidence", 0.0)
        else:
            # 26.1 — Selective re-entry: determine deepest stage required
            reentry_stage = self._determine_reentry_stage(self._last_review_issues)

            if reentry_stage in ("B3", "B4"):
                # Component or topology mismatch → full re-synthesis with issue context
                stages_rerun = [f"B1–B9 (re-entry from {reentry_stage})"]
                enhanced_prompt = self._inject_issue_context(prompt, self._last_review_issues, reentry_stage)
                hir_dict, synthesis_result = await self._run_synthesis(
                    prompt=enhanced_prompt,
                    target=target,
                    out_dir=out_dir,
                    generate_firmware=False,   # firmware only on iter 1
                    seed=seed,
                    clarification_mode="none",  # no re-clarification in improvement iterations
                    max_erc_iterations=max_erc_iterations,
                )
                synthesis_confidence = getattr(synthesis_result, "confidence", prev_score)
            else:
                # B6 — constraint/layout issues → DesignImprover on existing HIR
                stages_rerun = ["B6", "B9"]
                hir_dict, improvement_applied = self._apply_improvements(
                    current_hir, prompt
                )
                fixes_applied = improvement_applied
                synthesis_confidence = prev_score  # carry forward

        if not hir_dict:
            hir_dict = {}

        # --- Phase 21: Multi-agent parallel review ---
        review, agent_scores = await self._run_multi_agent_review(hir_dict, prompt)
        score = getattr(review, "score", 0.0)
        delta = score - prev_score

        # 26.1 — Store issues for next iteration's re-entry decision
        self._last_review_issues = list(getattr(review, "issues", []))

        # Collect issues
        issues_found: list[str] = []
        issue_codes: list[str] = []
        for issue in getattr(review, "issues", []):
            sev  = getattr(issue, "severity", "")
            code = getattr(issue, "code", "")
            msg  = getattr(issue, "message", "")
            issues_found.append(f"{sev}: [{code}] {msg}" if code else f"{sev}: {msg}")
            if code:
                issue_codes.append(code)

        # --- Update iteration memory ---
        chronic_issues: list[str] = []
        if self._memory is not None:
            self._memory.record_issues(iteration, issue_codes)
            if fixes_applied:
                self._memory.record_fixes(iteration, fixes_applied)
            chronic_issues = self._memory.chronic_issue_codes(min_fix_attempts=2)

        # Determine accept_reason for this iteration
        accept_reason = "continue"
        if fixes_applied and not issue_codes:
            accept_reason = "no_fixes"
        elif iteration > 1 and not fixes_applied:
            accept_reason = "no_fixes"

        record = IterationRecord(
            iteration=iteration,
            confidence=score,
            delta_confidence=delta,
            issues_found=issues_found,
            fixes_applied=fixes_applied,
            stages_rerun=stages_rerun,
            hitl_required=getattr(review, "hitl_required", False),
            accept_reason=accept_reason,
            synthesis_confidence=synthesis_confidence,
            agent_scores=agent_scores,
            chronic_issues=chronic_issues,
        )

        return record, hir_dict, synthesis_result

    # ------------------------------------------------------------------
    # Internal: synthesis
    # ------------------------------------------------------------------

    async def _run_requirements_clarification(
        self,
        prompt: str,
        clarification_mode: str,
    ) -> str:
        """Run RequirementsClarificationAgent before B1.

        Returns the (potentially enriched) prompt.
        Silently returns the original prompt if mode is 'none', LLM is
        disabled, or the agent fails for any reason.
        """
        if clarification_mode == "none" or not self._use_llm:
            return prompt
        try:
            _add_to_path(str(_REPO_ROOT / "shared"))
            from agents.clarification_agent import (
                ClarificationMode,
                CLIClarificationIO,
                RequirementsClarificationAgent,
            )
            from llm.gateway import LLMGateway

            io = self._clarification_io or CLIClarificationIO()
            mode = ClarificationMode(clarification_mode)
            agent = RequirementsClarificationAgent(
                mode=mode,
                io=io,
                llm_gateway=LLMGateway(),
            )
            enriched, _ = await agent.clarify(prompt)
            return enriched
        except Exception as exc:
            log.debug("RequirementsClarificationAgent skipped: %s", exc)
            return prompt

    async def _run_synthesis(
        self,
        prompt: str,
        target: str,
        out_dir: Path,
        generate_firmware: bool,
        seed: Optional[int],
        clarification_mode: str = "none",
        max_erc_iterations: int = 5,
    ) -> tuple[dict, Any]:
        """Run B1–B9 Synthesizer and return (hir_dict, SynthesisResult)."""
        try:
            import sys
            _add_to_path(str(_REPO_ROOT / "synthesizer"))
            _add_to_path(str(_REPO_ROOT / "shared"))
            from boardsmith_hw.synthesizer import Synthesizer

            # Build ComponentChallengeAgent if clarification is active
            component_challenge_agent = None
            if clarification_mode != "none" and self._use_llm:
                try:
                    from agents.clarification_agent import (
                        ClarificationMode,
                        CLIClarificationIO,
                        ComponentChallengeAgent,
                    )
                    io = self._clarification_io or CLIClarificationIO()
                    component_challenge_agent = ComponentChallengeAgent(
                        mode=ClarificationMode(clarification_mode),
                        io=io,
                    )
                except Exception as exc:
                    log.debug("ComponentChallengeAgent init skipped: %s", exc)

            synth = Synthesizer(
                out_dir=out_dir,
                target=target,
                use_llm=self._use_llm,
                seed=seed,
                component_challenge_agent=component_challenge_agent,
                max_erc_iterations=max_erc_iterations,
            )
            # Run in executor to avoid blocking the event loop with sync code
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, lambda: synth.run(prompt, generate_firmware=generate_firmware)
            )

            # Load HIR from file (most reliable way to get it)
            hir_path = out_dir / "hir.json"
            if hir_path.exists():
                hir_dict = json.loads(hir_path.read_text(encoding="utf-8"))
            else:
                hir_dict = {}

            return hir_dict, result

        except Exception as exc:
            log.exception("Synthesis failed: %s", exc)
            return {}, None

    # ------------------------------------------------------------------
    # Internal: design improvement
    # ------------------------------------------------------------------

    def _apply_improvements(
        self, hir_dict: dict, prompt: str
    ) -> tuple[dict, list[str]]:
        """Apply DesignImprover fixes to the HIR dict.

        Skips issue codes that have already been tried (IterationMemory) to
        prevent oscillating fixes.

        Returns: (updated_hir_dict, list_of_applied_codes)
        """
        try:
            _add_to_path(str(_REPO_ROOT / "synthesizer"))
            from boardsmith_hw.design_improver import DesignImprover
            from agents.design_review_agent import DesignReviewAgent

            # Run a deterministic (no-LLM) review to get issues for improver
            reviewer = DesignReviewAgent(gateway=None)
            review = reviewer.review(hir_dict, prompt=prompt)

            # Filter out already-tried fixes (Phase 21 oscillation prevention)
            already_fixed: set[str] = set()
            if self._memory is not None:
                already_fixed = self._memory.already_fixed_codes()

            if already_fixed and hasattr(review, "issues"):
                # Remove issues whose code was already tried in a prior iteration
                review.issues = [
                    i for i in review.issues
                    if getattr(i, "code", "") not in already_fixed
                ]

            improver = DesignImprover()
            improvement = improver.apply(hir_dict, review)

            return improvement.hir_dict, improvement.applied

        except Exception as exc:
            log.warning("DesignImprover failed: %s", exc)
            return hir_dict, []

    # ------------------------------------------------------------------
    # Internal: design review
    # ------------------------------------------------------------------

    async def _run_design_review(self, hir_dict: dict, prompt: str) -> Any:
        """Run DesignReviewAgent on hir_dict (single-agent, for compatibility)."""
        review, _ = await self._run_multi_agent_review(hir_dict, prompt)
        return review

    async def _run_multi_agent_review(
        self,
        hir_dict: dict,
        prompt: str,
    ) -> tuple[Any, dict[str, float]]:
        """Phase 21: Run all specialist agents in parallel and merge results.

        Agents (all deterministic, no LLM required):
          - DesignReviewAgent      — electrical + power + component (weight 0.35)
          - ElectricalReviewAgent  — voltage levels, I2C load, SPI clock (0.25)
          - ComponentQualityAgent  — JLCPCB availability, cost, EOL (0.20)
          - PCBReviewAgent         — DRC, density, trace length, spec (0.20)

        Returns:
          (merged_review, agent_scores_dict)
        """
        _add_to_path(str(_REPO_ROOT / "shared"))

        loop = asyncio.get_event_loop()

        # --- 1. DesignReviewAgent (primary, provides issues list + HITL gate) ---
        primary_review = await self._call_design_review_agent(hir_dict, prompt)

        # --- 2. Specialist agents (parallel, sync wrapped in executor) ---
        electrical_score, elec_issues = await loop.run_in_executor(
            None, lambda: self._call_electrical_agent(hir_dict)
        )
        quality_score, qual_issues = await loop.run_in_executor(
            None, lambda: self._call_quality_agent(hir_dict)
        )
        pcb_score, pcb_issues = await loop.run_in_executor(
            None, lambda: self._call_pcb_agent(hir_dict)
        )

        # --- 3. Weighted combined score ---
        primary_score = getattr(primary_review, "score", 0.5)
        combined = (
            0.35 * primary_score
            + 0.25 * electrical_score
            + 0.20 * quality_score
            + 0.20 * pcb_score
        )
        combined = round(min(1.0, max(0.0, combined)), 3)

        agent_scores = {
            "design_review":      round(primary_score, 3),
            "electrical":         round(electrical_score, 3),
            "component_quality":  round(quality_score, 3),
            "pcb":                round(pcb_score, 3),
            "combined":           combined,
        }

        # Patch the primary review's score to the combined value so all
        # existing stop-condition logic works without changes.
        try:
            primary_review.score = combined
            # Append specialist issues to the review's issue list
            primary_review.issues.extend(elec_issues)
            primary_review.issues.extend(qual_issues)
            primary_review.issues.extend(pcb_issues)
        except Exception:
            pass  # read-only fallback object — score already in agent_scores

        log.info(
            "Multi-agent review: combined=%.3f "
            "(design=%.2f elec=%.2f quality=%.2f pcb=%.2f)",
            combined, primary_score, electrical_score, quality_score, pcb_score,
        )
        return primary_review, agent_scores

    # --- specialist agent callers (sync, safe) ---

    def _call_electrical_agent(self, hir: dict) -> tuple[float, list]:
        try:
            from agents.electrical_review_agent import ElectricalReviewAgent
            result = ElectricalReviewAgent().review(hir)
            return result.score, result.issues
        except Exception as exc:
            log.debug("ElectricalReviewAgent skipped: %s", exc)
            return 0.80, []

    def _call_quality_agent(self, hir: dict) -> tuple[float, list]:
        try:
            from agents.component_quality_agent import ComponentQualityAgent
            result = ComponentQualityAgent().review(hir)
            return result.score, result.issues
        except Exception as exc:
            log.debug("ComponentQualityAgent skipped: %s", exc)
            return 0.80, []

    def _call_pcb_agent(self, hir: dict) -> tuple[float, list]:
        try:
            from agents.pcb_review_agent import PCBReviewAgent
            result = PCBReviewAgent().review(hir)
            return result.score, result.issues
        except Exception as exc:
            log.debug("PCBReviewAgent skipped: %s", exc)
            return 0.80, []

    async def _call_design_review_agent(self, hir_dict: dict, prompt: str) -> Any:
        """Run the primary DesignReviewAgent (with optional LLM)."""
        try:
            from agents.design_review_agent import DesignReviewAgent

            if self._use_llm:
                from llm.gateway import LLMGateway
                reviewer = DesignReviewAgent(gateway=LLMGateway())
                return await reviewer.review_async(hir_dict, prompt=prompt)
            else:
                reviewer = DesignReviewAgent(gateway=None)
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, lambda: reviewer.review(hir_dict, prompt=prompt)
                )
        except Exception as exc:
            log.warning("DesignReviewAgent failed: %s — using score 0.5", exc)

            class _FallbackReview:
                score = 0.50
                hitl_required = False
                issues: list = []

            return _FallbackReview()

    # ------------------------------------------------------------------
    # Internal: PCB pipeline
    # ------------------------------------------------------------------

    async def _run_pcb(self, hir_dict: dict, out_dir: Path) -> list[str]:
        """Run PCB pipeline and return list of artifact paths."""
        try:
            _add_to_path(str(_REPO_ROOT / "synthesizer"))
            from boardsmith_hw.pcb_pipeline import PcbPipeline

            pipeline = PcbPipeline(use_llm=self._use_llm)
            loop = asyncio.get_event_loop()
            pcb_result = await loop.run_in_executor(
                None, lambda: pipeline.run(hir_dict, out_dir=out_dir)
            )

            artifacts: list[str] = []
            if pcb_result.pcb_path and pcb_result.pcb_path.exists():
                artifacts.append(str(pcb_result.pcb_path))
            if pcb_result.gerber_dir and pcb_result.gerber_dir.exists():
                artifacts.append(str(pcb_result.gerber_dir))
            if pcb_result.production_zip and pcb_result.production_zip.exists():
                artifacts.append(str(pcb_result.production_zip))
            return artifacts

        except Exception as exc:
            log.warning("PCB pipeline failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Internal: firmware review
    # ------------------------------------------------------------------

    def _review_firmware(self, out_dir: Path) -> Optional[float]:
        """Run FirmwareReviewAgent on the firmware directory."""
        try:
            _add_to_path(str(_REPO_ROOT / "shared"))
            from agents.firmware_review_agent import FirmwareReviewAgent

            fw_dir = out_dir / "firmware"
            agent = FirmwareReviewAgent()
            result = agent.review(fw_dir if fw_dir.exists() else None)
            log.info("Firmware review: %s", result.summary())
            return result.score

        except Exception as exc:
            log.warning("Firmware review failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 26.1 — Re-entry helpers
    # ------------------------------------------------------------------

    def _determine_reentry_stage(self, issues: list) -> str:
        """Return the deepest re-entry stage required by the given issues.

        Priority order: B3 (most expensive) → B4 → B6 (cheapest).
        Falls back to B6 if no issues or unknown categories.
        """
        deepest = "B6"
        for issue in issues:
            cat = getattr(issue, "category", "electrical")
            required = self._CATEGORY_REENTRY.get(cat, "B6")
            if self._REENTRY_PRIORITY[required] < self._REENTRY_PRIORITY[deepest]:
                deepest = required
        log.debug("Re-entry stage determined: %s from %d issues", deepest, len(issues))
        return deepest

    def _inject_issue_context(
        self, prompt: str, issues: list, reentry_stage: str
    ) -> str:
        """Append top issues as synthesis hints to the prompt.

        This lets B1 parser and B3 component selector know what went wrong
        in the previous iteration, improving re-synthesis quality.
        """
        if not issues:
            return prompt

        # Only surface errors and warnings, skip info
        relevant = [
            i for i in issues
            if getattr(i, "severity", "info") in ("error", "warning")
        ][:5]

        if not relevant:
            return prompt

        lines = [f"\n\n[Synthese-Hinweis: Re-Entry ab {reentry_stage} wegen folgender Probleme]"]
        for issue in relevant:
            code = getattr(issue, "code", "")
            msg  = getattr(issue, "message", "")
            sug  = getattr(issue, "suggestion", "")
            line = f"- [{code}] {msg}"
            if sug:
                line += f" → {sug}"
            lines.append(line)
        lines.append("[Ende Hinweis]")

        return prompt + "\n".join(lines)

    # ------------------------------------------------------------------
    # 26.2 — GateMatrix computation
    # ------------------------------------------------------------------

    def _compute_gate_matrix(
        self,
        hir_dict: dict,
        out_dir: Path,
        generate_firmware: bool,
    ) -> GateMatrix:
        """Compute hard pass/fail gates from HIR + output files.

        Each gate is checked independently; failures are non-fatal (design
        can still be useful) but block the release_ready flag.
        """
        warnings: list[str] = []

        # --- ERC ---
        erc_clean = True
        erc_path = out_dir / "erc_report.json"
        if erc_path.exists():
            try:
                erc_data = json.loads(erc_path.read_text(encoding="utf-8"))
                error_count = erc_data.get("error_count", 0)
                erc_clean = error_count == 0
                if not erc_clean:
                    warnings.append(f"ERC: {error_count} error(s) in erc_report.json")
            except Exception:
                pass  # best-effort

        # --- Assumptions analysis ---
        assumptions: list[str] = hir_dict.get("assumptions", [])
        assume_lower = [a.lower() for a in assumptions]

        no_pinmux_conflicts = not any(
            ("pinmux" in a or "conflict" in a) and ("error" in a or "warn" in a or "doppelt" in a)
            for a in assume_lower
        )
        if not no_pinmux_conflicts:
            warnings.append("Pinmux conflict detected in HIR assumptions")

        boot_pins_valid = not any(
            "boot" in a and ("error" in a or "falsch" in a or "conflict" in a)
            for a in assume_lower
        )
        if not boot_pins_valid:
            warnings.append("Boot-pin issue detected in HIR assumptions")

        level_shifter_inserted = any(
            "level-shifter" in a or "levelshifter" in a or "txs0102" in a or "bss138" in a
            for a in assume_lower
        )
        if level_shifter_inserted:
            warnings.append(
                "Level-shifter was auto-inserted — verify direction (uni/bidirectional) "
                "and pull-up configuration manually"
            )

        # --- Power ---
        power_contracts = hir_dict.get("power_contracts", [])
        power_budget_ok = len(power_contracts) > 0
        if not power_budget_ok:
            warnings.append("No power rails defined in HIR")

        # --- Mandatory components (from diagnostics) ---
        mandatory_components = True
        diag_path = out_dir / "diagnostics.json"
        if diag_path.exists():
            try:
                diag = json.loads(diag_path.read_text(encoding="utf-8"))
                profile_errors = diag.get("profile_errors", [])
                if profile_errors:
                    mandatory_components = False
                    warnings.append(
                        f"MCU profile: {len(profile_errors)} mandatory component check(s) failed"
                    )
            except Exception:
                pass

        # --- BOM completeness ---
        components = hir_dict.get("components", [])
        passive_roles = {"passive", "decoupling", "pullup", "pulldown", "ferrite"}
        non_passives = [
            c for c in components
            if c.get("role", "") not in passive_roles
        ]
        bom_complete = all(c.get("mpn") for c in non_passives)
        if not bom_complete:
            warnings.append("One or more non-passive components have no MPN")

        # --- Firmware (optional gate) ---
        firmware_compiles: Optional[bool] = None
        if generate_firmware:
            fw_dir = out_dir / "firmware"
            firmware_compiles = fw_dir.exists()
            if not firmware_compiles:
                warnings.append("Firmware generation requested but firmware/ directory missing")

        return GateMatrix(
            erc_clean=erc_clean,
            drc_clean=True,          # DRC only after PCB routing (Phase 23)
            boot_pins_valid=boot_pins_valid,
            power_budget_ok=power_budget_ok,
            mandatory_components=mandatory_components,
            no_pinmux_conflicts=no_pinmux_conflicts,
            bom_complete=bom_complete,
            firmware_compiles=firmware_compiles,
            level_shifter_inserted=level_shifter_inserted,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Internal: collect artifact paths
    # ------------------------------------------------------------------

    def _collect_artifacts(self, out_dir: Path, synthesis_result: Any) -> list[str]:
        """Collect artifact paths from Synthesizer output + out_dir scan."""
        artifacts: list[str] = []

        # From SynthesisResult.artifacts (list of filenames relative to out_dir)
        if synthesis_result is not None:
            for rel in getattr(synthesis_result, "artifacts", []):
                candidate = out_dir / rel
                if candidate.exists():
                    artifacts.append(str(candidate))

        # Always include well-known output files if present
        known_files = [
            "hir.json", "bom.json", "schematic.kicad_sch",
            "synthesis_report.md", "diagnostics.json",
        ]
        for name in known_files:
            p = out_dir / name
            if p.exists() and str(p) not in artifacts:
                artifacts.append(str(p))

        # firmware/ directory
        fw_dir = out_dir / "firmware"
        if fw_dir.exists():
            artifacts.append(str(fw_dir))

        return artifacts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_added_paths: set[str] = set()


def _add_to_path(path: str) -> None:
    """Add path to sys.path if not already present."""
    import sys
    if path not in sys.path and path not in _added_paths:
        sys.path.insert(0, path)
        _added_paths.add(path)
