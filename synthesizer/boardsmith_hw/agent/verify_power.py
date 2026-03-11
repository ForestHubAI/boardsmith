# SPDX-License-Identifier: AGPL-3.0-or-later
"""VerifyPowerTool — power supply integrity semantic verification.

Checks: unconnected power-in pins, voltage regulator presence, bulk capacitor.
Runs without LLM — BOARDSMITH_NO_LLM=1 safe.
All heavy imports are lazy (inside execute() body only).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Bulk capacitor value patterns (KiCad shorthand and standard notation)
# ---------------------------------------------------------------------------

_BULK_CAP_PATTERNS = (
    "10uf", "10µf", "10u",
    "47uf", "47µf", "47u",
    "100uf", "100µf", "100u",
)


# ---------------------------------------------------------------------------
# Rule check functions
# ---------------------------------------------------------------------------

def _check_power_pin_connectivity(graph: Any) -> list[dict]:
    """Find power_in pins not connected to any net.

    Builds a connected_pins set from all net.pins entries and reports
    any power_in pin whose (comp_id, pin_name) is absent from it.
    """
    connected_pins: set[tuple[str, str]] = {
        (comp_id, pin_name)
        for net in graph.nets
        for comp_id, pin_name in net.pins
    }

    violations: list[dict] = []
    for comp in graph.components:
        for pin in comp.pins:
            if pin.electrical_type == "power_in":
                if (comp.id, pin.name) not in connected_pins:
                    violations.append(
                        {
                            "type": "unconnected_power_pin",
                            "severity": "error",
                            "message": (
                                f"Power-in pin '{pin.name}' of {comp.id} "
                                f"is not connected to any net"
                            ),
                            "ref": comp.id,
                        }
                    )
    return violations


def _check_voltage_regulator(hir: Any, graph: Any) -> list[dict]:
    """Warn when MCU/sensor is present in HIR but no power component in schematic."""
    needs_regulation = any(c.role in ("mcu", "sensor") for c in hir.components)
    has_regulator = any(gc.role == "power" for gc in graph.components)

    if needs_regulation and not has_regulator:
        return [
            {
                "type": "missing_voltage_regulator",
                "severity": "warning",
                "message": (
                    "MCU/sensor components present but no voltage regulator "
                    "found in schematic"
                ),
            }
        ]
    return []


def _check_bulk_cap(graph: Any) -> list[dict]:
    """Warn when a power regulator is present but no bulk capacitor (10uF+) is found."""
    has_regulator = any(gc.role == "power" for gc in graph.components)
    if not has_regulator:
        return []

    for gc in graph.components:
        combined = (gc.name + gc.mpn).lower()
        for pat in _BULK_CAP_PATTERNS:
            if pat in combined:
                return []

    return [
        {
            "type": "missing_bulk_cap",
            "severity": "warning",
            "message": (
                "Voltage regulator present but no bulk capacitor (10uF+) found"
            ),
        }
    ]


# ---------------------------------------------------------------------------
# Tool class
# ---------------------------------------------------------------------------

class VerifyPowerTool:
    """LLM-callable tool that checks power supply integrity in a schematic.

    Verifies: unconnected power-in pins, voltage regulator presence, bulk cap.
    All imports inside execute() — BOARDSMITH_NO_LLM=1 safe.
    """

    name = "verify_power"
    description = (
        "Verify power supply integrity: unconnected power-in pins (error), "
        "missing voltage regulator when MCU/sensor present (warning), "
        "missing bulk capacitor when regulator present (warning)."
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
                "description": "Absolute path to .kicad_sch file",
            },
        },
        "required": ["hir_path", "sch_path"],
    }

    async def execute(self, input: Any, context: Any) -> Any:  # noqa: A002
        from tools.base import ToolResult  # lazy — BOARDSMITH_NO_LLM=1 safe
        from synth_core.hir_bridge.kicad_parser import KiCadSchematicParser
        from models.hir import HIR
        import json

        hir_path = Path(input["hir_path"])
        if not hir_path.exists():
            return ToolResult(
                success=False,
                data={"violations": []},
                source="verify_power",
                confidence=0.0,
                error=f"hir.json not found: {hir_path}",
            )

        hir = HIR.model_validate(json.loads(hir_path.read_text()))
        graph = KiCadSchematicParser().parse(Path(input["sch_path"]))

        violations = (
            _check_power_pin_connectivity(graph)
            + _check_voltage_regulator(hir, graph)
            + _check_bulk_cap(graph)
        )

        return ToolResult(
            success=True,
            data={
                "violations": violations,
                "violation_count": len(violations),
                "checks_run": ["power_pins", "voltage_regulator", "bulk_cap"],
            },
            source="verify_power",
            confidence=1.0,
            metadata={"net_count": len(graph.nets)},
        )
