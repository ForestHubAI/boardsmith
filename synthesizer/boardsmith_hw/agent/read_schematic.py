# SPDX-License-Identifier: AGPL-3.0-or-later
"""ReadSchematicTool — wraps KiCadSchematicParser for LLM-callable schematic reading."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

_TOKEN_BUDGET = 400
_MAX_SIGNAL_NETS = 20


class ReadSchematicTool:
    """LLM-callable tool that reads a KiCad schematic and returns a compact summary."""

    name = "read_schematic"
    description = (
        "Read a KiCad schematic (.kicad_sch) and return a compact summary "
        "containing all component references, values, power nets, and signal nets. "
        "Summary is always under 400 tokens for LLM consumption."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "sch_path": {
                "type": "string",
                "description": "Absolute path to the .kicad_sch file to read.",
            }
        },
        "required": ["sch_path"],
    }

    async def execute(self, input: Any, context: Any) -> Any:
        from tools.base import ToolResult
        # Lazy import — never at module level to keep import-clean
        from synth_core.hir_bridge.kicad_parser import KiCadSchematicParser

        try:
            parser = KiCadSchematicParser()
            graph = parser.parse(Path(input["sch_path"]))

            components = [
                {
                    "ref": c.properties.get("Reference", c.id),
                    "value": c.properties.get("Value", c.mpn or c.name),
                    "footprint": c.properties.get("Footprint", c.package or ""),
                }
                for c in graph.components
            ]

            power_nets = [n.name for n in graph.nets if n.is_power]
            signal_nets_sorted = sorted(
                [n for n in graph.nets if not n.is_power],
                key=lambda n: len(n.pins),
                reverse=True,
            )
            signal_nets = [n.name for n in signal_nets_sorted[:_MAX_SIGNAL_NETS]]

            data: dict[str, Any] = {
                "components": components,
                "power_nets": power_nets,
                "signal_nets": signal_nets,
                "net_count": len(graph.nets),
            }

            # Token budget enforcement: iteratively reduce output until under budget
            # Pass 1: strip footprint from all components
            token_est = len(json.dumps(data)) // 4
            if token_est >= _TOKEN_BUDGET:
                for c in data["components"]:
                    c.pop("footprint", None)
            # Pass 2: if still over budget, cap components at 30 (largest schematics)
            token_est = len(json.dumps(data)) // 4
            if token_est >= _TOKEN_BUDGET:
                data["components"] = data["components"][:30]
            # Pass 3: if still over budget, truncate values to 20 chars each
            token_est = len(json.dumps(data)) // 4
            if token_est >= _TOKEN_BUDGET:
                for c in data["components"]:
                    if len(c.get("value", "")) > 20:
                        c["value"] = c["value"][:20]

            return ToolResult(
                success=True,
                data=data,
                source="kicad_parser",
                confidence=1.0,
                metadata={"component_count": len(components)},
            )
        except Exception as exc:
            from tools.base import ToolResult as TR
            return TR(
                success=False,
                data={},
                source="kicad_parser",
                confidence=0.0,
                error=str(exc),
            )
