# SPDX-License-Identifier: AGPL-3.0-or-later
"""B7. BOM Builder — generates/validates Bill of Materials from HIR."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def build_bom(hir_dict: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract and return BOM entries from HIR dict (already embedded by hir_composer)."""
    return hir_dict.get("bom", [])


def write_bom(bom: list[dict[str, Any]], out_path: Path) -> None:
    """Write BOM to JSON file."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(bom, f, indent=2)


def write_bom_csv(bom: list[dict[str, Any]], out_path: Path) -> None:
    """Write BOM to a CSV file with columns: Qty, MPN, Description, Manufacturer, UnitCost, Currency."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["Qty", "MPN", "Description", "Manufacturer", "UnitCost_USD", "ComponentID"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in bom:
            writer.writerow({
                "Qty": entry.get("qty", 1),
                "MPN": entry.get("mpn", ""),
                "Description": entry.get("description", ""),
                "Manufacturer": entry.get("manufacturer", ""),
                "UnitCost_USD": entry.get("unit_cost_estimate", ""),
                "ComponentID": entry.get("component_id", ""),
            })


def bom_summary(bom: list[dict[str, Any]]) -> dict[str, Any]:
    """Return summary statistics for a BOM."""
    total_cost = sum(
        (e.get("unit_cost_estimate") or 0) * (e.get("qty") or 1)
        for e in bom
    )
    return {
        "line_count": len(bom),
        "total_cost_estimate_usd": round(total_cost, 2),
        "currency": "USD",
        "items": [
            {
                "mpn": e.get("mpn", ""),
                "description": e.get("description", ""),
                "qty": e.get("qty", 1),
                "unit_cost": e.get("unit_cost_estimate"),
            }
            for e in bom
        ],
    }
