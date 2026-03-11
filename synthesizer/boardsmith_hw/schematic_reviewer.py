# SPDX-License-Identifier: AGPL-3.0-or-later
"""B13. Schematic Review Loop — .kicad_sch → HIR → Diff → Auto-Fix.

Implements the closed-loop feedback pipeline for Phase 13:

    HIR → KiCad Export → KiCad Re-Parse → HIR' → Diff → Auto-Fix → Loop
                                                    ↑
                                              SchematicReviewer

Entry point for the `boardsmith review --schematic` CLI command.

Algorithm:
  1. Parse .kicad_sch → HardwareGraph  (KiCadSchematicParser)
  2. HardwareGraph → HIR object         (build_hir)
  3. Validate HIR                        (Track A constraint solver)
  4. Round-trip diff vs original HIR    (optional — if original_hir provided)
  5. Auto-fix via ConstraintRefiner     (max_iterations, LLM-boost optional)
  6. Return ReviewResult

Invariants:
  - Never modifies the original HIR dict passed in.
  - Graceful error: parse/build failures return ReviewResult(valid=False, error=...)
  - Deterministic fallback: use_llm=False always works without API keys.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DiffSummary:
    """Round-trip diff: original HIR vs re-parsed HIR from schematic.

    Captures what changed when round-tripping through .kicad_sch export/import.
    Expected result for a lossless round-trip: has_diff=False (all fields empty).
    Typical losses: pin-level details not stored in .kicad_sch (OK by design).
    """

    components_added: list[str] = field(default_factory=list)
    """Component IDs present in re-parsed HIR but not in original."""

    components_removed: list[str] = field(default_factory=list)
    """Component IDs present in original HIR but not in re-parsed."""

    components_changed: list[str] = field(default_factory=list)
    """Component IDs present in both, but MPN or role differs."""

    buses_added: list[str] = field(default_factory=list)
    """Bus names present in re-parsed HIR but not in original."""

    buses_removed: list[str] = field(default_factory=list)
    """Bus names present in original HIR but not in re-parsed."""

    has_diff: bool = False
    """True if any difference was detected."""


@dataclass
class ReviewResult:
    """Full result of a schematic review pass.

    Attributes:
        valid:          Final validation status after auto-fix loop.
        iterations:     Number of auto-fix iterations performed.
        errors_before:  Error-level constraint failures in initial parse.
        errors_after:   Error-level failures after auto-fix loop.
        resolved:       Constraint IDs fixed by the refiner.
        unresolvable:   Constraint IDs that could not be fixed.
        diff:           Round-trip diff vs original HIR (empty if not provided).
        hir_dict:       Final HIR dict after all fixes (ready for downstream use).
        llm_boosted:    True if LLM was used in the auto-fix loop.
        error:          Non-None if a fatal error occurred (parse failure etc.).
    """

    valid: bool
    iterations: int
    errors_before: int
    errors_after: int
    resolved: list[str] = field(default_factory=list)
    unresolvable: list[str] = field(default_factory=list)
    diff: DiffSummary = field(default_factory=DiffSummary)
    hir_dict: dict[str, Any] = field(default_factory=dict)
    llm_boosted: bool = False
    error: str | None = None


# ---------------------------------------------------------------------------
# SchematicReviewer
# ---------------------------------------------------------------------------


class SchematicReviewer:
    """Closed-loop schematic review: parse → validate → diff → auto-fix.

    Usage::

        reviewer = SchematicReviewer(max_iterations=3, use_llm=False)
        result = reviewer.review(
            schematic_path=Path("output/schematic.kicad_sch"),
            original_hir=hir_dict,   # optional, enables round-trip diff
        )
        if result.valid:
            print("Schematic passes all constraints")
        else:
            print(f"Unresolvable errors: {result.unresolvable}")
    """

    def __init__(
        self,
        max_iterations: int = 3,
        use_llm: bool = True,
    ) -> None:
        self.max_iterations = max_iterations
        self._use_llm = use_llm

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def review(
        self,
        schematic_path: Path,
        original_hir: dict[str, Any] | None = None,
    ) -> ReviewResult:
        """Review a .kicad_sch file.

        Args:
            schematic_path: Path to the KiCad 6 .kicad_sch file.
            original_hir:   Optional original HIR dict to compute a
                            round-trip diff against the re-parsed result.

        Returns:
            ReviewResult with validation status, diff, and auto-fix output.
        """
        schematic_path = Path(schematic_path)
        if not schematic_path.exists():
            return ReviewResult(
                valid=False,
                iterations=0,
                errors_before=0,
                errors_after=0,
                error=f"Schematic file not found: {schematic_path}",
            )

        # --- Step 1: Parse .kicad_sch → HIR ---
        try:
            hir = self._parse_and_build_hir(schematic_path)
        except Exception as exc:
            log.exception("Failed to parse schematic: %s", schematic_path)
            return ReviewResult(
                valid=False,
                iterations=0,
                errors_before=0,
                errors_after=0,
                error=f"Parse error: {exc}",
            )

        # --- Step 2: Convert to dict ---
        hir_dict: dict[str, Any] = json.loads(hir.model_dump_json())

        # --- Step 3: Initial validation ---
        from synth_core.api.compiler import validate_hir_dict

        initial_report = validate_hir_dict(hir_dict)
        errors_before = sum(
            1
            for d in initial_report.constraints
            if d.severity.value == "error" and d.status.value == "fail"
        )
        log.debug(
            "Phase13 initial validation: %d error(s) before auto-fix",
            errors_before,
        )

        # --- Step 4: Round-trip diff ---
        diff = DiffSummary()
        if original_hir is not None:
            diff = self._diff_hir(original_hir, hir_dict)
            if diff.has_diff:
                log.info(
                    "Phase13 round-trip diff: +%d/-%d components, +%d/-%d buses",
                    len(diff.components_added),
                    len(diff.components_removed),
                    len(diff.buses_added),
                    len(diff.buses_removed),
                )

        # --- Step 5: Auto-fix via ConstraintRefiner ---
        from boardsmith_hw.constraint_refiner import ConstraintRefiner

        refiner = ConstraintRefiner(
            max_iterations=self.max_iterations,
            use_llm=self._use_llm,
        )
        refinement = refiner.refine(hir)

        errors_after = sum(
            1
            for d in refinement.report.constraints
            if d.severity.value == "error" and d.status.value == "fail"
        )
        log.info(
            "Phase13 review complete: valid=%s, iterations=%d, "
            "errors %d→%d, resolved=%d, unresolvable=%d",
            refinement.report.valid,
            refinement.iterations,
            errors_before,
            errors_after,
            len(refinement.resolved),
            len(refinement.unresolvable),
        )

        return ReviewResult(
            valid=refinement.report.valid,
            iterations=refinement.iterations,
            errors_before=errors_before,
            errors_after=errors_after,
            resolved=refinement.resolved,
            unresolvable=refinement.unresolvable,
            diff=diff,
            hir_dict=refinement.hir,
            llm_boosted=refinement.llm_boosted,
        )

    def review_text(
        self,
        schematic_text: str,
        original_hir: dict[str, Any] | None = None,
        source_name: str = "<text>",
    ) -> ReviewResult:
        """Review KiCad schematic content from a string (useful for tests).

        Writes the text to a temp file, then calls review().
        """
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".kicad_sch",
            delete=False,
            encoding="utf-8",
        ) as fh:
            fh.write(schematic_text)
            tmp_path = Path(fh.name)

        try:
            return self.review(tmp_path, original_hir=original_hir)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_and_build_hir(self, path: Path):
        """Parse .kicad_sch → HardwareGraph → HIR."""
        from synth_core.hir_bridge.kicad_parser import parse_kicad_schematic
        from synth_core.hir_bridge.hir_builder import build_hir

        graph = parse_kicad_schematic(path)
        hir = build_hir(graph, source=str(path), track="A")
        return hir

    def _diff_hir(
        self,
        original: dict[str, Any],
        reparsed: dict[str, Any],
    ) -> DiffSummary:
        """Compute round-trip diff between original and re-parsed HIR.

        Compares component IDs (MPN + role) and bus_contract names.
        Pin-level differences are intentionally ignored: the .kicad_sch
        format does not preserve all HIR pin metadata, so pin-level
        loss is expected and not treated as a diff.
        """
        orig_comps: dict[str, dict] = {
            c["id"]: c for c in original.get("components", [])
        }
        repr_comps: dict[str, dict] = {
            c["id"]: c for c in reparsed.get("components", [])
        }

        orig_ids = set(orig_comps)
        repr_ids = set(repr_comps)

        removed = sorted(orig_ids - repr_ids)
        added = sorted(repr_ids - orig_ids)

        changed: list[str] = []
        for cid in sorted(orig_ids & repr_ids):
            oc = orig_comps[cid]
            rc = repr_comps[cid]
            if oc.get("mpn") != rc.get("mpn") or oc.get("role") != rc.get("role"):
                changed.append(cid)

        orig_buses: dict[str, dict] = {
            bc["bus_name"]: bc
            for bc in original.get("bus_contracts", [])
        }
        repr_buses: dict[str, dict] = {
            bc["bus_name"]: bc
            for bc in reparsed.get("bus_contracts", [])
        }
        orig_bus_names = set(orig_buses)
        repr_bus_names = set(repr_buses)
        buses_removed = sorted(orig_bus_names - repr_bus_names)
        buses_added = sorted(repr_bus_names - orig_bus_names)

        has_diff = bool(removed or added or changed or buses_removed or buses_added)

        return DiffSummary(
            components_added=added,
            components_removed=removed,
            components_changed=changed,
            buses_added=buses_added,
            buses_removed=buses_removed,
            has_diff=has_diff,
        )
