# SPDX-License-Identifier: AGPL-3.0-or-later
"""B8. Schematic Exporter — optional HIR → netlist/KiCad export (MVP stub)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def export_netlist(hir_dict: dict[str, Any], out_path: Path) -> None:
    """Export HIR as a simple JSON netlist (MVP).

    Full KiCad .kicad_sch export is planned for Phase 3.
    """
    components = [
        {
            "ref": c.get("id"),
            "mpn": c.get("mpn"),
            "name": c.get("name"),
            "role": c.get("role"),
        }
        for c in hir_dict.get("components", [])
    ]

    nets = [
        {
            "name": n.get("name"),
            "pins": n.get("pins", []),
        }
        for n in hir_dict.get("nets", [])
    ]

    netlist = {
        "format": "boardsmith-fw-netlist",
        "version": "1.0",
        "hir_version": hir_dict.get("version", "1.1.0"),
        "components": components,
        "nets": nets,
        "buses": [
            {
                "name": bc.get("bus_name"),
                "type": bc.get("bus_type"),
                "master": bc.get("master_id"),
                "slaves": bc.get("slave_ids", []),
                "pin_assignments": bc.get("pin_assignments", {}),
                "slave_addresses": bc.get("slave_addresses", {}),
            }
            for bc in hir_dict.get("bus_contracts", [])
        ],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(netlist, f, indent=2)
