# SPDX-License-Identifier: AGPL-3.0-or-later
"""B14. PCB Pipeline — HIR → .kicad_pcb → Gerbers → Production ZIP.

Orchestrates the full PCB generation flow:

    HIR dict
      │
      ├─→ FootprintMapper      → footprint strings + physical sizes
      │
      ├─→ PcbDesignRules       → IPC-2221 trace widths, SI notes
      │
      ├─→ PcbLayoutEngine      → .kicad_pcb (component placement + nets + pads)
      │
      ├─→ Autorouter           → trace routing (FreeRouting / kicad-cli / stub)
      │
      ├─→ Gerber export        → gerbers/ directory
      │
      ├─→ GerberValidator      → layer completeness check
      │
      ├─→ JLCPCBValidator      → BOM parts availability
      │
      └─→ PcbProductionExporter → <project>-jlcpcb.zip

All steps gracefully degrade: if kicad-cli / FreeRouting is not installed,
the pipeline still produces a valid (unrouted) .kicad_pcb and stub Gerbers.
`use_llm=False` always works without API keys.

Output files:
  <out_dir>/
    pcb.kicad_pcb          ← KiCad 6 PCB (always produced)
    gerbers/               ← Gerber + drill files (*.gbr, *.drl)
    <project>-jlcpcb.zip   ← JLCPCB-ready production bundle
    design_rules.txt        ← IPC-2221 design rule summary
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PcbResult:
    """Result of the PCB pipeline.

    Attributes:
        pcb_path:       Path to the generated .kicad_pcb file (None on fatal error).
        gerber_dir:     Path to the Gerber output directory.
        production_zip: Path to the JLCPCB-ready production ZIP (None if failed).
        routed:         True if traces were auto-routed (requires FreeRouting).
        real_gerbers:   True if kicad-cli was used for real Gerbers (vs stubs).
        drc_errors:     List of DRC error messages (empty if DRC not run).
        footprints:     {comp_id: kicad_footprint_string} resolved mapping.
        llm_boosted:    True if LLM was used in layout planning.
        router_method:  "freerouting" | "kicad_cli_drc" | "stub"
        design_rules_summary: Human-readable IPC-2221 design rules text.
        jlcpcb_summary: Human-readable JLCPCB availability summary.
        error:          Non-None if a fatal error occurred.
        manufacturing_packages: ManufacturingPackage objects produced by
                                export_manufacturing (empty if not requested).
    """

    pcb_path: Path | None
    gerber_dir: Path | None
    routed: bool
    real_gerbers: bool = False
    drc_errors: list[str] = field(default_factory=list)
    footprints: dict[str, str] = field(default_factory=dict)
    llm_boosted: bool = False
    router_method: str = "stub"
    production_zip: Path | None = None
    design_rules_summary: str = ""
    jlcpcb_summary: str = ""
    jlcpcb_drc_summary: str = ""   # Phase 25.5: JLCPCB DRC result summary
    error: str | None = None
    manufacturing_packages: list[Any] = field(default_factory=list)


# ---------------------------------------------------------------------------
# PcbPipeline
# ---------------------------------------------------------------------------


class PcbPipeline:
    """Generates a PCB from an HIR dict.

    Usage::

        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(hir_dict, out_dir=Path("./output"))
        if result.pcb_path:
            print(f"PCB: {result.pcb_path}")
            print(f"Gerbers: {result.gerber_dir}")
        if result.routed:
            print("PCB is fully routed")
        else:
            print(f"Unrouted — {result.router_method}")
    """

    def __init__(self, use_llm: bool = True) -> None:
        self._use_llm = use_llm

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        hir_dict: dict[str, Any],
        out_dir: Path,
        project_base: str = "pcb",
        export_manufacturing: list[str] | None = None,
    ) -> PcbResult:
        """Run the full PCB pipeline.

        Args:
            hir_dict:             HIR as a plain dict (from hir.json or synthesizer output).
            out_dir:              Output directory. Will be created if it doesn't exist.
            project_base:         Base name for the PCB file (should match schematic base name
                                  so KiCad sees them as one project).
            export_manufacturing: Optional list of fab service names to package after Gerber
                                  export (e.g. ["jlcpcb", "seeed"]). Packages are written
                                  to out_dir/manufacturing/{service}/. Requires no extra
                                  dependencies — uses Python stdlib only.

        Returns:
            PcbResult with paths to generated files and status information.
        """
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        pcb_path  = out_dir / f"{project_base}.kicad_pcb"
        gerber_dir = out_dir / "gerbers"

        # ------------------------------------------------------------------
        # Step 1: Footprint resolution
        # ------------------------------------------------------------------
        try:
            from boardsmith_hw.footprint_mapper import FootprintMapper
            mapper = FootprintMapper(use_llm=self._use_llm)
            footprints = mapper.resolve_all(hir_dict)
            log.debug("PCB pipeline: resolved %d footprints", len(footprints))
        except Exception as exc:
            log.exception("Footprint mapping failed")
            return PcbResult(
                pcb_path=None, gerber_dir=None, routed=False,
                error=f"Footprint mapping failed: {exc}",
            )

        # ------------------------------------------------------------------
        # Step 2: PCB layout + .kicad_pcb generation
        # ------------------------------------------------------------------
        try:
            from boardsmith_hw.pcb_layout_engine import PcbLayoutEngine
            from boardsmith_hw.autorouter import Autorouter
            routing_avail = Autorouter.freerouting_available()
            engine = PcbLayoutEngine(
                use_llm=self._use_llm,
                routing_available=routing_avail,
            )
            pcb_text = engine.build(hir_dict, footprints)
            pcb_path.write_text(pcb_text, encoding="utf-8")
            log.info("PCB layout written to %s", pcb_path)
        except Exception as exc:
            log.exception("PCB layout generation failed")
            return PcbResult(
                pcb_path=None, gerber_dir=None, routed=False,
                error=f"PCB layout failed: {exc}",
            )

        # Did LLM help with placement?
        llm_boosted = self._use_llm

        # ------------------------------------------------------------------
        # Step 3: Autorouting
        # ------------------------------------------------------------------
        try:
            from boardsmith_hw.autorouter import Autorouter
            router = Autorouter()
            router_result = router.route(pcb_path, hir_dict)
            log.info("Router: method=%s routed=%s drc_errors=%d note=%s",
                     router_result.method, router_result.routed,
                     len(router_result.drc_errors), router_result.note)
        except Exception as exc:
            log.warning("Autorouter raised an exception: %s", exc)
            from boardsmith_hw.autorouter import RouterResult
            router_result = RouterResult(
                routed=False, method="stub", pcb_path=pcb_path,
                note=f"Autorouter exception: {exc}",
            )

        # ------------------------------------------------------------------
        # Step 3b: DRC auto-fix loop (errors → patch PCB → re-check)
        # ------------------------------------------------------------------
        try:
            from boardsmith_hw.pcb_drc_autofix import run_drc_fix_loop
            fix_result = run_drc_fix_loop(pcb_path, max_iterations=3)
            if fix_result.fixes_applied:
                log.info(
                    "DRC auto-fix: applied %d fix(es): %s",
                    len(fix_result.fixes_applied),
                    ", ".join(fix_result.fixes_applied),
                )
                # Merge any remaining unfixable violations into router_result
                router_result.drc_errors.extend(fix_result.remaining)
        except Exception as exc:
            log.debug("DRC auto-fix skipped: %s", exc)

        # ------------------------------------------------------------------
        # Step 3c: Post-routing DRC (Phase 23.6)
        # ------------------------------------------------------------------
        try:
            from boardsmith_hw.pcb_drc_autofix import PcbDrcAutoFix
            post_fixer = PcbDrcAutoFix()
            post_result = post_fixer.post_routing_check(pcb_path)
            if post_result.fixes_applied:
                log.info(
                    "Post-routing DRC: applied %d fix(es): %s",
                    len(post_result.fixes_applied),
                    ", ".join(post_result.fixes_applied),
                )
            if post_result.remaining:
                router_result.drc_errors.extend(post_result.remaining)
        except Exception as exc:
            log.debug("Post-routing DRC skipped: %s", exc)

        # ------------------------------------------------------------------
        # Step 3d: Routing validation (Phase 23.1)
        # ------------------------------------------------------------------
        try:
            from boardsmith_hw.autorouter import Autorouter
            validator = Autorouter()
            routing_issues = validator.validate_routing(pcb_path)
            if routing_issues:
                for issue in routing_issues:
                    log.info("Routing validation: %s", issue)
                router_result.drc_errors.extend(routing_issues)
        except Exception as exc:
            log.debug("Routing validation skipped: %s", exc)

        # ------------------------------------------------------------------
        # Step 4: Gerber export
        # ------------------------------------------------------------------
        real_gerbers = False
        try:
            from boardsmith_hw.autorouter import Autorouter
            router = Autorouter()
            real_gerbers = router.export_gerbers(pcb_path, gerber_dir)
        except Exception as exc:
            log.warning("Gerber export failed: %s — writing stubs", exc)
            from boardsmith_hw.autorouter import _write_stub_gerbers
            _write_stub_gerbers(gerber_dir, pcb_path.stem)

        # ------------------------------------------------------------------
        # Step 4b: Gerber validation (Phase 23.7)
        # ------------------------------------------------------------------
        try:
            from boardsmith_hw.gerber_validator import GerberValidator
            gerber_v = GerberValidator()
            gerber_report = gerber_v.validate(gerber_dir)
            if not gerber_report.valid:
                for issue in gerber_report.issues:
                    log.warning("Gerber validation: %s", issue)
                    router_result.drc_errors.append(f"Gerber: {issue}")
            for warn in gerber_report.warnings:
                log.info("Gerber: %s", warn)
            if gerber_report.stub_gerbers:
                log.info("Gerber: stub output — install kicad-cli for real Gerbers")
        except Exception as exc:
            log.debug("Gerber validation skipped: %s", exc)

        # ------------------------------------------------------------------
        # Build footprint summary dict
        # ------------------------------------------------------------------
        fp_summary = {
            comp_id: fp_info.kicad_footprint
            for comp_id, fp_info in footprints.items()
        }

        result = PcbResult(
            pcb_path=pcb_path,
            gerber_dir=gerber_dir,
            routed=router_result.routed,
            real_gerbers=real_gerbers,
            drc_errors=router_result.drc_errors,
            footprints=fp_summary,
            llm_boosted=llm_boosted,
            router_method=router_result.method,
        )

        # ------------------------------------------------------------------
        # Step 4c: JLCPCB DRC — board size, track width, via geometry
        # Phase 25.5: Always run JLCPCB DRC on the generated PCB
        # ------------------------------------------------------------------
        if pcb_path and pcb_path.exists():
            try:
                from boardsmith_hw.jlcpcb_drc import JLCPCBDRCChecker
                drc_checker = JLCPCBDRCChecker()
                drc_result = drc_checker.check(pcb_path)
                result.jlcpcb_drc_summary = drc_result.summary()
                if drc_result.errors:
                    for err in drc_result.errors:
                        log.warning("JLCPCB DRC error: %s", err.message)
                if drc_result.warnings:
                    for warn in drc_result.warnings:
                        log.info("JLCPCB DRC warning: %s", warn.message)
                log.info(
                    "JLCPCB DRC: %d error(s), %d warning(s) on %s×%smm board",
                    len(drc_result.errors), len(drc_result.warnings),
                    f"{drc_result.board_width_mm:.1f}", f"{drc_result.board_height_mm:.1f}",
                )
            except Exception as exc:
                log.warning("JLCPCB DRC failed: %s", exc)

        # ------------------------------------------------------------------
        # Step 5: Design rules + JLCPCB validation + production ZIP
        # ------------------------------------------------------------------
        try:
            from boardsmith_hw.pcb_design_rules import build_design_rules
            rules = build_design_rules(hir_dict)
            result.design_rules_summary = rules.summary()
            # Write design rules to file for reference
            dr_path = out_dir / "design_rules.txt"
            dr_path.write_text(rules.summary(), encoding="utf-8")
        except Exception as exc:
            log.warning("Design rules analysis failed: %s", exc)

        try:
            from boardsmith_hw.pcb_production import PcbProductionExporter
            exporter = PcbProductionExporter()
            system_name = hir_dict.get("system_name", "boardsmith")
            project_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(system_name))
            bundle = exporter.export(result, hir_dict, out_dir, project_name)
            result.production_zip = bundle.zip_path
            if bundle.jlcpcb_report:
                result.jlcpcb_summary = bundle.jlcpcb_report.summary()
            if bundle.errors:
                for err in bundle.errors:
                    log.warning("Production export: %s", err)
            log.info("Production bundle: %s", bundle.zip_path)
        except Exception as exc:
            log.warning("Production bundle export failed: %s", exc)

        # ------------------------------------------------------------------
        # Step 6: Manufacturing export
        # Phase 25.5: JLCPCB package is generated by default.
        # Pass export_manufacturing=[] explicitly to skip entirely.
        # ------------------------------------------------------------------
        services = list(export_manufacturing) if export_manufacturing is not None else ["jlcpcb"]
        if services:
            try:
                from boardsmith_hw.manufacturing_exporter import ManufacturingExporter
                mfg_exporter = ManufacturingExporter()
                for service in services:
                    mfg_dir = out_dir / "manufacturing" / service
                    pkg = mfg_exporter.export(
                        service=service,
                        pcb_result=result,
                        hir_dict=hir_dict,
                        out_dir=mfg_dir,
                    )
                    result.manufacturing_packages.append(pkg)
                    log.info(
                        "Manufacturing package for %s: gerbers=%s bom=%s cpl=%s lcsc=%.0f%%",
                        service, pkg.gerber_zip, pkg.bom_csv, pkg.cpl_csv,
                        pkg.lcsc_coverage_pct,
                    )
            except Exception as exc:
                log.warning("Manufacturing export failed: %s", exc)

        return result
