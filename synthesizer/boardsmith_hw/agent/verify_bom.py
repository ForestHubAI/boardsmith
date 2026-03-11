# SPDX-License-Identifier: AGPL-3.0-or-later
"""VerifyBomTool — cross-check HIR components against bom.csv."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _norm_mpn(s: str) -> str:
    return s.upper().replace("-", "").replace("_", "")


def _check_bom_coverage(hir: Any, bom_by_id: dict) -> list[dict]:
    violations = []
    for comp in hir.components:
        row = bom_by_id.get(comp.id)
        if row is None:
            violations.append({
                "type": "missing_bom_row",
                "severity": "error",
                "message": f"HIR component '{comp.id}' (MPN: {comp.mpn}) not found in bom.csv",
                "ref": comp.id,
            })
        else:
            csv_mpn = row.get("MPN", "").strip()
            if csv_mpn and comp.mpn:
                if _norm_mpn(csv_mpn) != _norm_mpn(comp.mpn):
                    violations.append({
                        "type": "mpn_mismatch",
                        "severity": "warning",
                        "message": (
                            f"Component '{comp.id}': HIR MPN '{comp.mpn}' "
                            f"does not match bom.csv MPN '{csv_mpn}'"
                        ),
                        "ref": comp.id,
                    })
    return violations


class VerifyBomTool:
    """Cross-check HIR components against bom.csv.

    Checks:
    - Coverage: every HIR component has a row in bom.csv (matched by ComponentID)
    - MPN match: when bom.csv row has a non-empty MPN, it must match the HIR MPN
      (normalized: upper-case, strip hyphens/underscores)

    bom.csv is auto-detected from hir_path parent directory.
    """

    name = "verify_bom"
    description = (
        "Cross-check HIR components against bom.csv. "
        "Returns violations for missing rows or MPN mismatches."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "hir_path": {
                "type": "string",
                "description": "Absolute path to hir.json",
            },
        },
        "required": ["hir_path"],
    }

    async def execute(self, input: Any, context: Any) -> Any:
        from tools.base import ToolResult
        from models.hir import HIR
        import csv
        import json

        hir_path = Path(input["hir_path"])
        if not hir_path.exists():
            return ToolResult(
                success=False,
                data={"violations": []},
                source="verify_bom",
                confidence=0.0,
                error=f"hir.json not found: {hir_path}",
            )

        bom_path = hir_path.parent / "bom.csv"
        if not bom_path.exists():
            return ToolResult(
                success=False,
                data={"violations": [], "error": "bom.csv not found"},
                source="verify_bom",
                confidence=0.0,
                error=f"bom.csv not found: {bom_path}",
            )

        hir = HIR.model_validate(json.loads(hir_path.read_text()))

        bom_by_id: dict[str, dict] = {}
        with open(bom_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                cid = row.get("ComponentID", "").strip()
                if cid:
                    bom_by_id[cid] = row

        violations = _check_bom_coverage(hir, bom_by_id)

        return ToolResult(
            success=True,
            data={
                "violations": violations,
                "violation_count": len(violations),
                "checks_run": ["bom_coverage", "mpn_match"],
            },
            source="verify_bom",
            confidence=1.0,
            metadata={
                "component_count": len(hir.components),
                "bom_row_count": len(bom_by_id),
            },
        )
