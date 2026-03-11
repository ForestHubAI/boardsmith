# SPDX-License-Identifier: AGPL-3.0-or-later
"""Boardsmith Synthesizer — main orchestrator for prompt → HIR synthesis."""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

from boardsmith_hw.intent_parser import IntentParser
from boardsmith_hw.requirements_normalizer import normalize
from boardsmith_hw.component_selector import ComponentSelector
from boardsmith_hw.topology_synthesizer import synthesize_topology
from boardsmith_hw.hir_composer import compose_hir
from boardsmith_hw.constraint_refiner import ConstraintRefiner
from boardsmith_hw.bom_builder import build_bom, write_bom, write_bom_csv, bom_summary
from boardsmith_hw.confidence_engine import ConfidenceEngine
from boardsmith_hw.schematic_exporter import export_netlist
from boardsmith_hw.kicad_exporter import export_kicad_sch
from boardsmith_hw.profile_checks import run_profile_checks


@dataclass
class SynthesisResult:
    success: bool
    confidence: float
    artifacts: list[str] = field(default_factory=list)
    hitl_required: bool = False
    hitl_messages: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    error: str | None = None
    erc_passed: bool | None = None
    erc_errors: list[str] = field(default_factory=list)
    erc_note: str = ""
    erc_iterations: int = 0
    erc_fixes: list[str] = field(default_factory=list)
    # PCB pipeline results (populated when generate_pcb=True)
    pcb_path: Path | None = None
    pcb_routed: bool = False
    pcb_router_method: str = ""
    pcb_gerber_dir: Path | None = None
    pcb_production_zip: Path | None = None
    pcb_error: str | None = None
    drc_unconnected_count: int = 0


class Synthesizer:
    """Orchestrates full Boardsmith synthesis pipeline."""

    def __init__(
        self,
        out_dir: Path,
        target: str = "esp32",
        max_iterations: int = 5,
        confidence_threshold: float = 0.65,
        seed: int | None = None,
        use_llm: bool = True,
        component_challenge_agent: Any = None,
        generate_pcb: bool = False,
        max_erc_iterations: int = 5,
        max_semantic_iterations: int = 5,
    ) -> None:
        self.out_dir = out_dir
        self.target = target
        self.max_iterations = max_iterations
        self.confidence_threshold = confidence_threshold
        self.seed = seed
        self._session_id = str(uuid.uuid4())
        self._use_llm = use_llm
        self._component_challenge_agent = component_challenge_agent
        self._generate_pcb = generate_pcb
        self._max_erc_iterations = max_erc_iterations
        self._max_semantic_iterations = max_semantic_iterations

        self._intent_parser = IntentParser(use_llm=use_llm)
        self._component_selector = ComponentSelector(seed=seed, use_agent=use_llm)
        self._constraint_refiner = ConstraintRefiner(max_iterations=max_iterations, use_llm=use_llm)
        self._confidence_engine = ConfidenceEngine()

    def run(self, prompt: str, generate_firmware: bool = False, generate_pcb: bool | None = None) -> SynthesisResult:
        """Execute the full synthesis pipeline."""
        artifacts: list[str] = []

        try:
            # --- B1: Intent Parsing ---
            spec = self._intent_parser.parse(prompt)

            # Override MCU family with --target when it's a recognized family.
            # The target flag is user-specified and more authoritative than LLM
            # guesses.  Keep the LLM-selected family only when it is a
            # sub-variant of the target (e.g. "stm32h7" for target "stm32",
            # "esp32s3" for target "esp32") — in that case the LLM resolved a
            # more specific variant which we want to preserve.  If the LLM
            # chose a completely different family (e.g. "arduino" when target
            # is "stm32"), override with the target to avoid selecting the
            # wrong MCU and producing voltage mismatches or unsupported buses.
            from .component_selector import _MCU_FAMILY_MPNS

            if self.target in _MCU_FAMILY_MPNS:
                # Guard: mcu_family may be a list (dual-MCU prompts) or None
                _raw_family = spec.mcu_family
                if isinstance(_raw_family, list):
                    _raw_family = _raw_family[0] if _raw_family else ""
                _llm_family = (_raw_family or "").lower()
                if not _llm_family.startswith(self.target.lower()):
                    spec.mcu_family = self.target

            # --- B2: Requirements Normalization ---
            reqs = normalize(spec)
            intent_conf = sum(spec.confidence_per_field.values()) / max(1, len(spec.confidence_per_field))

            # Check confidence threshold early
            if reqs.confidence < self.confidence_threshold and reqs.unresolved:
                return SynthesisResult(
                    success=False,
                    confidence=reqs.confidence,
                    hitl_required=True,
                    hitl_messages=[
                        f"Intent confidence {reqs.confidence:.2f} below threshold",
                        *[f"Unresolved: {u}" for u in reqs.unresolved],
                    ],
                    assumptions=reqs.unresolved,
                    error="Insufficient requirements clarity — please clarify prompt",
                )

            # --- B3: Component Selection ---
            selection = self._component_selector.select(reqs)
            if selection.mcu is None:
                return SynthesisResult(
                    success=False,
                    confidence=0.0,
                    error="No MCU found in knowledge base",
                )

            # --- B3.5: Component Challenge (optional, interactive) ---
            if self._component_challenge_agent is not None:
                selection = self._component_challenge_agent.challenge(selection, reqs)

            # --- B4: Topology Synthesis ---
            # Pass intended supply voltage so regulator is auto-added when needed
            supply_v = reqs.raw.supply_voltage
            topology = synthesize_topology(
                selection, supply_voltage_v=supply_v, use_llm=self._use_llm,
                raw_prompt=getattr(reqs.raw, "raw_prompt", ""),
            )

            # --- B5: HIR Composition ---
            hir = compose_hir(
                topology,
                track="B",
                source="prompt",
                session_id=self._session_id,
                overall_confidence=selection.confidence * reqs.confidence,
            )

            # --- B6: Constraint Refinement Loop ---
            refinement = self._constraint_refiner.refine(hir)
            final_hir_dict = refinement.hir
            final_report = refinement.report

            # --- B7: MCU Profile Checks (Checks 12–18) ---
            mcu_mpn = selection.mcu.mpn if selection.mcu else ""
            assigned_pins: dict[str, str] = {}
            for bus in topology.buses:
                assigned_pins.update(bus.pin_assignments)
            component_mpns = [c.mpn for c in selection.sensors]
            profile_report = run_profile_checks(
                mcu_mpn=mcu_mpn,
                target_sdk=self._target_to_sdk(self.target),
                assigned_pins=assigned_pins,
                component_mpns=component_mpns,
            )
            # Merge profile check results into assumptions
            profile_assumptions: list[str] = []
            for chk in profile_report.checks:
                if chk.status == "fail":
                    profile_assumptions.append(f"[{chk.check_id}] {chk.message}")
            # Store profile report in HIR metadata
            final_hir_dict.setdefault("metadata", {})["profile_checks"] = {
                "errors": profile_report.errors,
                "warnings": profile_report.warnings,
                "checks": [
                    {"id": c.check_id, "severity": c.severity,
                     "status": c.status, "message": c.message}
                    for c in profile_report.checks
                ],
            }

            # --- B9: Confidence Computation ---
            # Only penalised assumptions go to the confidence engine.
            # Informational notes (profile-derived, deterministic) are displayed
            # in the report but do NOT reduce confidence.
            all_assumptions = list(topology.assumptions)
            for u in reqs.unresolved:
                if u not in all_assumptions:
                    all_assumptions.append(u)
            all_assumptions.extend(profile_assumptions)

            # Notes are shown alongside assumptions in the report
            all_notes = list(getattr(topology, "notes", []))

            # Collect LLM-boosted stages for confidence bonus
            llm_stages: list[str] = []
            if refinement.llm_boosted:
                llm_stages.append("B6")

            # Compute driver quality subscore from profile checks
            driver_quality = self._compute_driver_quality(component_mpns, self._target_to_sdk(self.target))

            conf_result = self._confidence_engine.compute(
                intent_confidence=intent_conf,
                component_confidence=selection.confidence,
                topology_confidence=0.85 if not topology.assumptions else 0.70,
                validation_report=final_report,
                assumptions=all_assumptions,
                hir_dict=final_hir_dict,
                llm_boosted_stages=llm_stages,
                profile_errors=profile_report.errors,
                profile_warnings=profile_report.warnings,
                driver_quality=driver_quality,
            )

            # Update HIR metadata with final confidence
            if "metadata" in final_hir_dict:
                final_hir_dict["metadata"]["confidence"] = {
                    "overall": conf_result.overall,
                    "subscores": conf_result.subscores,
                    "explanations": conf_result.explanations,
                }
                # Merge penalised assumptions + informational notes for the report
                final_hir_dict["metadata"]["assumptions"] = all_assumptions + all_notes

            # --- Write artifacts ---
            # hir.json
            hir_path = self.out_dir / "hir.json"
            hir_path.write_text(json.dumps(final_hir_dict, indent=2, default=str))
            artifacts.append("hir.json")

            # bom.json + bom.csv
            bom = build_bom(final_hir_dict)
            bom_path = self.out_dir / "bom.json"
            write_bom(bom, bom_path)
            artifacts.append("bom.json")
            bom_csv_path = self.out_dir / "bom.csv"
            write_bom_csv(bom, bom_csv_path)
            artifacts.append("bom.csv")

            # diagnostics.json
            diag_dict = final_report.to_dict()
            diag_path = self.out_dir / "diagnostics.json"
            diag_path.write_text(json.dumps(diag_dict, indent=2))
            artifacts.append("diagnostics.json")

            # netlist.json (legacy JSON netlist)
            netlist_path = self.out_dir / "netlist.json"
            export_netlist(final_hir_dict, netlist_path)
            artifacts.append("netlist.json")

            # KiCad schematic + closed-loop ERC — unified project name
            sys_name = final_hir_dict.get("system_name", "boardsmith")
            project_base = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(sys_name)).strip("_") or "boardsmith"
            kicad_path = self.out_dir / f"{project_base}.kicad_sch"
            erc_passed: bool | None = None
            erc_errors: list[str] = []
            erc_note = ""
            erc_iterations = 0
            erc_fixes: list[str] = []
            try:
                # --- B8.1: ERC Refinement Loop ---
                # Export → ERC → fix (no_connect, PWR_FLAG) → re-export → re-check
                from boardsmith_hw.kicad_drc import ERCRefiner
                refiner = ERCRefiner(max_iterations=3, use_llm=self._use_llm)
                erc_ref = refiner.refine(final_hir_dict, kicad_path)
                artifacts.append(kicad_path.name)

                erc_passed = erc_ref.passed
                erc_iterations = erc_ref.iterations
                erc_fixes = list(erc_ref.fixes_applied)
                if erc_ref.final_check:
                    erc_errors = list(erc_ref.final_check.error_messages)
                    erc_note = erc_ref.final_check.note

                if erc_ref.tool_available:
                    # Write ERC report
                    erc_report_path = self.out_dir / "erc_report.json"
                    final_check = erc_ref.final_check
                    erc_report_path.write_text(json.dumps({
                        "check_type": "erc",
                        "passed": erc_ref.passed,
                        "iterations": erc_ref.iterations,
                        "initial_errors": erc_ref.initial_errors,
                        "final_errors": erc_ref.final_errors,
                        "fixes_applied": erc_ref.fixes_applied,
                        "error_count": final_check.error_count if final_check else 0,
                        "warning_count": final_check.warning_count if final_check else 0,
                        "violations": [
                            {
                                "severity": v.severity,
                                "description": v.description,
                                "rule_id": v.rule_id,
                                "items": v.items,
                            }
                            for v in (final_check.violations if final_check else [])
                        ],
                    }, indent=2))
                    artifacts.append("erc_report.json")

                    # --- B8.2: ERC Agent Loop (LLM-guided repair) ---
                    # Activates only when: ERC has errors AND kicad-cli available AND LLM enabled
                    if not erc_ref.passed and erc_ref.tool_available and self._use_llm:
                        try:
                            from boardsmith_hw.agent.erc_agent import ERCAgent
                            from llm.gateway import LLMGateway
                            from llm.dispatcher import ToolDispatcher
                            from tools.registry import get_default_registry
                            _registry = get_default_registry()
                            _gateway = LLMGateway()
                            _dispatcher = ToolDispatcher(registry=_registry)
                            _agent = ERCAgent(
                                sch_path=kicad_path,
                                gateway=_gateway,
                                dispatcher=_dispatcher,
                                max_iterations=self._max_erc_iterations,
                            )
                            _agent_result = _agent.run()
                            if _agent_result.is_clean:
                                erc_passed = True
                                erc_errors = []
                                log.info(
                                    "ERC agent: all violations resolved in %d iteration(s)",
                                    _agent_result.iterations_used,
                                )
                            else:
                                log.warning("ERC agent incomplete: %s", _agent_result.summary_message)
                        except ImportError as _agent_import_err:
                            # Phase 7 not yet executed or BOARDSMITH_NO_LLM=1 guard
                            log.debug("ERCAgent unavailable (import error): %s", _agent_import_err)
                        except Exception as _agent_err:
                            log.warning("ERCAgent failed unexpectedly: %s", _agent_err)

                    # --- B8.3: Semantic Verification (rule-based, no LLM) ---
                    # Runs always when kicad_path.exists() — not gated on LLM credentials
                    # Guard is kicad_path.exists() only (already in outer block)
                    _all_verif_violations: list = []  # initialised here so B8.4 can always read it
                    try:
                        from boardsmith_hw.agent.verify_components import VerifyComponentsTool as _VCT
                        from boardsmith_hw.agent.verify_connectivity import VerifyConnectivityTool as _VCONNT
                        from boardsmith_hw.agent.verify_bootability import VerifyBootabilityTool as _VBT
                        from boardsmith_hw.agent.verify_power import VerifyPowerTool as _VPT
                        from boardsmith_hw.agent.verify_bom import VerifyBomTool as _VBOMT
                        from boardsmith_hw.agent.verify_pcb_basic import VerifyPcbBasicTool as _VPCBT
                        import asyncio as _asyncio
                        _verif_hir_path = str(self.out_dir / "hir.json")
                        _verif_sch_path = str(kicad_path)
                        _verif_input = {"hir_path": _verif_hir_path, "sch_path": _verif_sch_path}
                        _verif_tools = [_VCT(), _VCONNT(), _VBT(), _VPT(), _VBOMT(), _VPCBT()]
                        for _vtool in _verif_tools:
                            _vtool_result = _asyncio.run(
                                _vtool.execute(_verif_input, None)
                            )
                            if _vtool_result.success and _vtool_result.data:
                                _all_verif_violations.extend(
                                    _vtool_result.data.get("violations", [])
                                )
                        if _all_verif_violations:
                            log.debug(
                                "Semantic verification: %d violation(s) — %s",
                                len(_all_verif_violations),
                                "; ".join(
                                    v.get("message", "")
                                    for v in _all_verif_violations[:5]
                                ),
                            )
                        else:
                            log.info("Semantic verification: all checks passed")
                    except ImportError as _verif_import_err:
                        log.debug("Semantic verification unavailable: %s", _verif_import_err)
                    except Exception as _verif_err:
                        log.warning("Semantic verification failed: %s", _verif_err)

                    # --- B8.4: Semantic Verification Agent (LLM-guided repair) ---
                    # Activates only when: semantic violations found AND LLM enabled AND hir.json exists
                    _sem_hir_path = self.out_dir / "hir.json"
                    if self._use_llm and _all_verif_violations and _sem_hir_path.exists():
                        try:
                            from boardsmith_hw.agent.semantic_agent import SemanticVerificationAgent
                            from llm.gateway import LLMGateway
                            from llm.dispatcher import ToolDispatcher
                            from tools.registry import get_default_registry
                            _sem_agent = SemanticVerificationAgent(
                                sch_path=kicad_path,
                                hir_path=_sem_hir_path,
                                gateway=LLMGateway(),
                                dispatcher=ToolDispatcher(registry=get_default_registry()),
                                max_iterations=self._max_semantic_iterations,
                            )
                            _sem_result = _sem_agent.run()
                            if _sem_result.is_clean:
                                log.info(
                                    "Semantic agent: all violations resolved in %d iteration(s)",
                                    _sem_result.iterations_used,
                                )
                            else:
                                log.debug(
                                    "Semantic agent incomplete: %s",
                                    _sem_result.summary_message,
                                )
                        except ImportError as _sem_import_err:
                            log.debug(
                                "SemanticVerificationAgent unavailable: %s",
                                _sem_import_err,
                            )
                        except Exception as _sem_err:
                            log.warning(
                                "SemanticVerificationAgent failed: %s", _sem_err
                            )

                    if not erc_ref.passed:
                        log.warning(
                            "ERC: %d error(s) after %d iteration(s)",
                            erc_ref.final_errors, erc_ref.iterations,
                        )
                    elif erc_ref.fixes_applied:
                        log.info(
                            "ERC passed after fixes: %s",
                            ", ".join(erc_ref.fixes_applied),
                        )
            except Exception as _kicad_err:
                # Fallback: export without ERC loop
                try:
                    export_kicad_sch(final_hir_dict, kicad_path, use_llm=self._use_llm)
                    artifacts.append(kicad_path.name)
                except Exception:
                    pass
                all_assumptions.append(f"KiCad export/ERC warning: {_kicad_err}")

            # Create a stable 'schematic.kicad_sch' alias so tests and
            # downstream tools can always find the schematic under a
            # predictable name regardless of system_name.
            _alias = self.out_dir / "schematic.kicad_sch"
            if kicad_path.exists() and not _alias.exists():
                try:
                    _alias.symlink_to(kicad_path.name)
                except OSError:
                    import shutil
                    shutil.copy2(kicad_path, _alias)

            # synthesis_report.md
            report_path = self.out_dir / "synthesis_report.md"
            report_path.write_text(
                self._build_report_md(prompt, final_hir_dict, diag_dict, conf_result, bom, refinement)
            )
            artifacts.append("synthesis_report.md")

            # --- ERC.rpt — persistent human-readable report via kicad-cli ---
            try:
                from boardsmith_hw.kicad_drc import KiCadChecker
                _checker = KiCadChecker()
                erc_rpt_path = self.out_dir / "ERC.rpt"
                # Remove stale report so old results don't persist
                if erc_rpt_path.exists():
                    erc_rpt_path.unlink()
                if _checker.export_erc_rpt(kicad_path, erc_rpt_path):
                    artifacts.append("ERC.rpt")
            except Exception:
                pass  # ERC.rpt is best-effort; never blocks synthesis

            # Optional: PCB layout + Gerbers
            pcb_path: Path | None = None
            pcb_routed = False
            pcb_router_method = ""
            pcb_gerber_dir: Path | None = None
            pcb_production_zip: Path | None = None
            pcb_error: str | None = None
            _drc_unconnected: int = 0
            _do_pcb = generate_pcb if generate_pcb is not None else self._generate_pcb
            if _do_pcb:
                (
                    pcb_path,
                    pcb_routed,
                    pcb_router_method,
                    pcb_gerber_dir,
                    pcb_production_zip,
                    pcb_error,
                ) = self._run_pcb_pipeline(final_hir_dict, artifacts,
                                           project_base=project_base)
                if pcb_error:
                    all_assumptions.append(f"PCB pipeline warning: {pcb_error}")
                # --- DRC.rpt — persistent human-readable DRC report ---
                elif pcb_path and pcb_path.exists():
                    try:
                        from boardsmith_hw.kicad_drc import KiCadChecker
                        _pcb_checker = KiCadChecker()
                        drc_rpt_path = self.out_dir / "DRC.rpt"
                        # Remove stale report so old results don't persist
                        if drc_rpt_path.exists():
                            drc_rpt_path.unlink()
                        if _pcb_checker.export_drc_rpt(pcb_path, drc_rpt_path):
                            artifacts.append("DRC.rpt")
                            # Parse unconnected pad count from DRC.rpt
                            _drc_unconnected = KiCadChecker.count_unconnected_from_rpt(drc_rpt_path)
                    except Exception:
                        pass  # DRC.rpt is best-effort

                # Update erc_report.json with drc_unconnected_count (best-effort)
                erc_report_path = self.out_dir / "erc_report.json"
                if erc_report_path.exists():
                    try:
                        _erc_data = json.loads(erc_report_path.read_text(encoding="utf-8"))
                        _erc_data["drc_unconnected_count"] = _drc_unconnected
                        erc_report_path.write_text(json.dumps(_erc_data, indent=2))
                    except Exception:
                        pass  # erc_report.json update is best-effort

            # Optional: generate firmware
            if generate_firmware and final_report.valid:
                from synth_core.api.compiler import generate_firmware as _gen_fw
                fw_dir = self.out_dir / "firmware"
                try:
                    summary = _gen_fw(final_hir_dict, target=self.target, out_dir=fw_dir, strict=False)
                    for fname in summary.files_written:
                        artifacts.append(f"firmware/{fname}")
                except Exception as e:
                    all_assumptions.append(f"Firmware generation failed: {e}")

            success = final_report.valid and conf_result.overall >= self.confidence_threshold

            # Merge all penalised assumptions + informational notes for report
            report_assumptions = all_assumptions + all_notes

            return SynthesisResult(
                success=success,
                confidence=conf_result.overall,
                artifacts=artifacts,
                hitl_required=conf_result.hitl_required,
                hitl_messages=conf_result.hitl_messages,
                assumptions=report_assumptions,
                erc_passed=erc_passed,
                erc_errors=erc_errors,
                erc_note=erc_note,
                erc_iterations=erc_iterations,
                erc_fixes=erc_fixes,
                pcb_path=pcb_path,
                pcb_routed=pcb_routed,
                pcb_router_method=pcb_router_method,
                pcb_gerber_dir=pcb_gerber_dir,
                pcb_production_zip=pcb_production_zip,
                pcb_error=pcb_error,
                drc_unconnected_count=_drc_unconnected,
            )

        except Exception as e:
            import traceback
            return SynthesisResult(
                success=False,
                confidence=0.0,
                error=f"Synthesis failed: {e}\n{traceback.format_exc()}",
            )

    @staticmethod
    def _target_to_sdk(target: str) -> str:
        """Map target platform to SDK identifier for profile checks."""
        mapping = {
            "esp32": "esp-idf", "esp32c3": "esp-idf", "esp32s3": "esp-idf",
            "stm32": "stm32hal", "stm32f4": "stm32hal", "stm32f7": "stm32hal",
            "stm32g4": "stm32hal", "stm32h7": "stm32hal", "stm32l4": "stm32hal",
            "lpc55": "nxp-sdk", "imxrt": "nxp-sdk",
            "rp2040": "pico-sdk", "nrf52": "zephyr",
        }
        return mapping.get(target.lower(), "esp-idf")

    @staticmethod
    def _compute_driver_quality(component_mpns: list[str], target_sdk: str) -> float | None:
        """Compute average driver quality score for components with software profiles."""
        try:
            from shared.knowledge.software_profiles import get as get_sw_profile
        except ImportError:
            return None

        scores: list[float] = []
        target_map = {"esp-idf": "esp32", "stm32hal": "stm32", "pico-sdk": "rp2040", "zephyr": "nrf52"}
        target_key = target_map.get(target_sdk, target_sdk)

        for mpn in component_mpns:
            sw_profile = get_sw_profile(mpn)
            if sw_profile is None:
                continue
            drivers = sw_profile.get_drivers_for_target(target_key)
            if drivers:
                best = max(drivers, key=lambda d: d.computed_quality)
                scores.append(best.computed_quality)
            # else: no driver for this target — skip (unknown, not bad)

        return sum(scores) / len(scores) if scores else None

    def _run_pcb_pipeline(
        self,
        hir_dict: dict[str, Any],
        artifacts: list[str],
        project_base: str = "boardsmith",
    ) -> tuple[Path | None, bool, str, Path | None, Path | None, str | None]:
        """Run PCB layout + Gerber pipeline. Returns (pcb_path, routed, method, gerber_dir, zip, error)."""
        try:
            from boardsmith_hw.pcb_pipeline import PcbPipeline
            pipeline = PcbPipeline(use_llm=self._use_llm)
            pcb_result = pipeline.run(
                hir_dict,
                out_dir=self.out_dir,
                project_base=project_base,
                export_manufacturing=["jlcpcb"],
            )
            if pcb_result.error:
                return None, False, "stub", None, None, pcb_result.error
            # Register artifacts
            if pcb_result.pcb_path and pcb_result.pcb_path.exists():
                artifacts.append(pcb_result.pcb_path.name)
            if pcb_result.gerber_dir and pcb_result.gerber_dir.exists():
                artifacts.append("gerbers/")
            if pcb_result.production_zip and pcb_result.production_zip.exists():
                artifacts.append(pcb_result.production_zip.name)
            if (self.out_dir / "design_rules.txt").exists():
                artifacts.append("design_rules.txt")
            return (
                pcb_result.pcb_path,
                pcb_result.routed,
                pcb_result.router_method,
                pcb_result.gerber_dir,
                pcb_result.production_zip,
                None,
            )
        except Exception as exc:
            import traceback
            return None, False, "stub", None, None, f"PCB pipeline failed: {exc}\n{traceback.format_exc()}"

    def _build_report_md(
        self,
        prompt: str,
        hir_dict: dict[str, Any],
        diag_dict: dict[str, Any],
        conf_result: Any,
        bom: list[dict[str, Any]],
        refinement: Any,
    ) -> str:
        from boardsmith_hw.bom_builder import bom_summary

        lines = [
            "# Boardsmith Synthesis Report",
            "",
            f"**Session:** `{self._session_id}`",
            f"**Prompt:** `{prompt}`",
            f"**Target:** `{self.target}`",
            "",
            "## Confidence",
            "",
            f"- **Overall:** {conf_result.overall:.2f}",
        ]
        for k, v in conf_result.subscores.items():
            lines.append(f"- {k.capitalize()}: {v:.2f}")
        if conf_result.explanations:
            lines.extend(["", "**Notes:**"])
            for e in conf_result.explanations:
                lines.append(f"- {e}")

        lines += ["", "## Components", ""]
        for c in hir_dict.get("components", []):
            lines.append(f"- **{c.get('name')}** ({c.get('mpn')}) — role: {c.get('role')}")

        lines += ["", "## Buses", ""]
        for bc in hir_dict.get("bus_contracts", []):
            addr_str = ", ".join(f"{sid}@{addr}" for sid, addr in bc.get("slave_addresses", {}).items())
            lines.append(f"- **{bc.get('bus_name')}** ({bc.get('bus_type')}): master={bc.get('master_id')}, slaves={bc.get('slave_ids')}, addresses=[{addr_str}]")

        summary = bom_summary(bom)
        lines += [
            "",
            "## Bill of Materials",
            "",
            f"- Lines: {summary['line_count']}",
            f"- Estimated cost: ${summary['total_cost_estimate_usd']:.2f} USD",
            "",
            "| # | MPN | Description | Qty | Unit Cost |",
            "|---|-----|-------------|-----|-----------|",
        ]
        for item in summary["items"]:
            cost = f"${item['unit_cost']:.2f}" if item["unit_cost"] else "-"
            lines.append(f"| - | {item['mpn']} | {item['description']} | {item['qty']} | {cost} |")

        lines += ["", "## Validation Summary", ""]
        s = diag_dict.get("summary", {})
        valid_str = "VALID" if diag_dict.get("valid") else "INVALID"
        lines.append(f"**Status:** {valid_str}")
        lines.append(f"- Errors: {s.get('errors', 0)}")
        lines.append(f"- Warnings: {s.get('warnings', 0)}")
        lines.append(f"- Info: {s.get('info', 0)}")
        lines.append(f"- Unknown: {s.get('unknown', 0)}")
        lines.append(f"- Refinement iterations: {refinement.iterations}")

        if refinement.resolved:
            lines += ["", "**Auto-resolved constraints:**"]
            for r in refinement.resolved:
                lines.append(f"- {r}")
        if refinement.unresolvable:
            lines += ["", "**Unresolvable constraints (require review):**"]
            for r in refinement.unresolvable:
                lines.append(f"- {r}")

        diags = diag_dict.get("diagnostics", [])
        errors_diags = [d for d in diags if d.get("severity") == "error" and d.get("status") == "fail"]
        if errors_diags:
            lines += ["", "### Errors", ""]
            for d in errors_diags:
                lines.append(f"- **{d['id']}**: {d['message']}")
                for fix in d.get("suggested_fixes", []):
                    lines.append(f"  → {fix}")

        meta = hir_dict.get("metadata", {})
        assumptions = meta.get("assumptions", [])
        if assumptions:
            lines += ["", "## Assumptions", ""]
            for a in assumptions:
                lines.append(f"- {a}")

        lines += ["", "---", "*Generated by boardsmith-fw Boardsmith Synthesizer*", ""]
        return "\n".join(lines)
