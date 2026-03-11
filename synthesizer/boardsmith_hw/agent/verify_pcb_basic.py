# SPDX-License-Identifier: AGPL-3.0-or-later
"""VerifyPcbBasicTool — check every schematic ref-des has a PCB footprint."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _check_pcb_footprints(sch_refs: set, pcb_refs: set) -> list[dict]:
    violations = []
    for ref in sorted(sch_refs - pcb_refs):
        violations.append({
            "type": "missing_pcb_footprint",
            "severity": "warning",
            "message": f"Schematic component '{ref}' has no footprint in PCB layout",
            "ref": ref,
        })
    return violations


class VerifyPcbBasicTool:
    """Check that every schematic symbol reference designator has a
    corresponding footprint in the PCB layout.

    Returns violations for missing footprints.
    Power symbols (#PWR, #FLG, etc.) are filtered out — they never appear in PCB.

    If no .kicad_pcb file exists in the schematic's directory, the check is
    skipped and the result is marked with skipped=True (PCB may not be generated yet).
    """

    name = "verify_pcb_basic"
    description = (
        "Check that every schematic symbol reference designator has a "
        "corresponding footprint in the PCB layout. "
        "Returns violations for missing footprints."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "hir_path": {
                "type": "string",
                "description": "Absolute path to hir.json",
            },
            "sch_path": {
                "type": "string",
                "description": "Absolute path to .kicad_sch",
            },
        },
        "required": ["sch_path"],
    }

    async def execute(self, input: Any, context: Any) -> Any:
        import re
        from tools.base import ToolResult
        from synth_core.hir_bridge.kicad_parser import KiCadSchematicParser

        sch_path = Path(input["sch_path"])
        out_dir = sch_path.parent

        pcb_candidates = sorted(out_dir.glob("*.kicad_pcb"))
        if not pcb_candidates:
            return ToolResult(
                success=True,
                data={
                    "violations": [],
                    "violation_count": 0,
                    "checks_run": ["pcb_footprint_coverage"],
                    "skipped": True,
                    "skip_reason": "no .kicad_pcb found",
                },
                source="verify_pcb_basic",
                confidence=1.0,
            )

        # Prefer PCB file whose stem matches the schematic stem; otherwise take first
        pcb_path = pcb_candidates[0]
        for candidate in pcb_candidates:
            if candidate.stem == sch_path.stem:
                pcb_path = candidate
                break

        pcb_text = pcb_path.read_text(encoding="utf-8")
        pcb_refs = set(re.findall(r'\(property\s+"Reference"\s+"([^"]+)"', pcb_text))

        graph = KiCadSchematicParser().parse(sch_path)
        # Filter out power/flag symbols (#PWR, #FLG) — they have no PCB footprint
        sch_refs = {gc.id for gc in graph.components if not gc.id.startswith("#")}

        violations = _check_pcb_footprints(sch_refs, pcb_refs)

        return ToolResult(
            success=True,
            data={
                "violations": violations,
                "violation_count": len(violations),
                "checks_run": ["pcb_footprint_coverage"],
                "pcb_ref_count": len(pcb_refs),
                "sch_ref_count": len(sch_refs),
            },
            source="verify_pcb_basic",
            confidence=1.0,
            metadata={"pcb_file": pcb_path.name},
        )
