# SPDX-License-Identifier: AGPL-3.0-or-later
"""VerifyComponentsTool — cross-checks HIR components against placed schematic symbols."""
from __future__ import annotations

from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Helper functions — module-level, no heavy imports
# ---------------------------------------------------------------------------

def _find_graph_comp(hir_comp: Any, graph: Any) -> Any | None:
    """Find GraphComponent matching HIR Component by normalized MPN."""
    target = hir_comp.mpn.upper().replace("-", "").replace("_", "")
    for gc in graph.components:
        candidate = gc.mpn.upper().replace("-", "").replace("_", "")
        if candidate == target or target in candidate or candidate in target:
            return gc
    return None


def _role_str(role: Any) -> str:
    """Normalize a role value (str enum or plain str) to lowercase string."""
    # ComponentRole is a str enum — str(ComponentRole.mcu) gives "ComponentRole.mcu",
    # but .value gives "mcu". Direct equality comparison works; use .value if available.
    if hasattr(role, "value"):
        return str(role.value).lower()
    return str(role).lower()


def _check_placement(hir: Any, graph: Any) -> list[dict]:
    """Check that every HIR component has a matching GraphComponent in the schematic."""
    violations: list[dict] = []
    for hir_comp in hir.components:
        if _find_graph_comp(hir_comp, graph) is None:
            violations.append({
                "type": "missing_component",
                "severity": "error",
                "message": (
                    f"HIR component '{hir_comp.name}' (MPN: {hir_comp.mpn}) "
                    "not found in schematic"
                ),
                "ref": hir_comp.id,
            })
    return violations


def _check_decoupling(hir: Any, graph: Any) -> list[dict]:
    """Check for 100nF decoupling caps when MCU/sensor/comms are present."""
    _ROLES_NEEDING_DECOUPLING = {"mcu", "sensor", "comms"}
    _CAP_PATTERNS = ("100n", "0.1u", "100nf")

    needs_decoupling = any(
        _role_str(c.role) in _ROLES_NEEDING_DECOUPLING for c in hir.components
    )
    if not needs_decoupling:
        return []

    def _has_cap_value(gc: Any) -> bool:
        for text in (gc.name.lower(), gc.mpn.lower()):
            if any(pat in text for pat in _CAP_PATTERNS):
                return True
        return False

    cap_count = sum(
        1 for gc in graph.components
        if gc.role == "passive" and _has_cap_value(gc)
    )
    if cap_count == 0:
        return [{
            "type": "missing_decoupling_cap",
            "severity": "warning",
            "message": "No 100nF decoupling capacitors found in schematic",
        }]
    return []


def _check_i2c_pullup(hir: Any, graph: Any) -> list[dict]:
    """Check for I2C pull-up resistors when an I2C BusContract exists."""
    _PULLUP_PATTERNS = ("4.7k", "4k7", "10k", "47k")

    has_i2c = any(
        bc.bus_type.upper() == "I2C" for bc in hir.bus_contracts
    )
    if not has_i2c:
        return []

    def _has_pullup_value(gc: Any) -> bool:
        for text in (gc.name.lower(), gc.mpn.lower()):
            if any(pat in text for pat in _PULLUP_PATTERNS):
                return True
        return False

    pullup_count = sum(
        1 for gc in graph.components
        if gc.role == "passive" and _has_pullup_value(gc)
    )
    if pullup_count == 0:
        return [{
            "type": "missing_i2c_pullup",
            "severity": "warning",
            "message": "I2C bus present but no 4.7k\u03a9 or 10k\u03a9 pull-up resistors found",
        }]
    return []


# ---------------------------------------------------------------------------
# Tool class
# ---------------------------------------------------------------------------

class VerifyComponentsTool:
    """Cross-check HIR components against placed schematic symbols.

    Checks:
    - Placement: every HIR component has a matching schematic symbol (by MPN)
    - Decoupling caps: at least one 100nF capacitor present for MCU/sensor/comms
    - I2C pull-ups: pull-up resistors present when I2C bus contract exists

    Note: Decoupling cap check is count-based (not proximity-based). Proximity
    analysis requires PCB-level coordinates and is out of scope at schematic level.
    """

    name = "verify_components"
    description = (
        "Cross-check HIR components against placed schematic symbols. "
        "Returns violations for missing ICs, missing decoupling caps, "
        "and missing I2C pull-up resistors."
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
        "required": ["hir_path", "sch_path"],
    }

    async def execute(self, input: Any, context: Any) -> Any:
        from tools.base import ToolResult
        from synth_core.hir_bridge.kicad_parser import KiCadSchematicParser
        from models.hir import HIR
        import json

        hir_path = Path(input["hir_path"])
        if not hir_path.exists():
            return ToolResult(
                success=False,
                data={"violations": []},
                source="verify_components",
                confidence=0.0,
                error=f"hir.json not found: {hir_path}",
            )

        hir = HIR.model_validate(json.loads(hir_path.read_text()))
        graph = KiCadSchematicParser().parse(Path(input["sch_path"]))

        violations = (
            _check_placement(hir, graph)
            + _check_decoupling(hir, graph)
            + _check_i2c_pullup(hir, graph)
        )

        return ToolResult(
            success=True,
            data={
                "violations": violations,
                "violation_count": len(violations),
                "checks_run": ["placement", "decoupling", "i2c_pullup"],
            },
            source="verify_components",
            confidence=1.0,
            metadata={"component_count": len(hir.components)},
        )
