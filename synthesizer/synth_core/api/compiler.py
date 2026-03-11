# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stable API boundary: boardsmith-fw Compiler ↔ Boardsmith.

Boardsmith must only use this module (or the CLI commands) to interact
with Compiler internals. No direct imports of internal modules allowed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from synth_core.hir_bridge.codegen import GenerationSummary, generate_from_hir as _gen
from synth_core.hir_bridge.graph import HardwareGraph
from synth_core.hir_bridge.hir_builder import build_hir as _build
from synth_core.hir_bridge.kicad_parser import KiCadSchematicParser
from synth_core.hir_bridge.validator import DiagnosticsReport, validate_hir as _validate
from synth_core.knowledge.resolver import KnowledgeResolver
from synth_core.models.hir import HIR


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_hir(
    graph_path: str | Path,
    knowledge_dir: str | Path | None = None,
    include_constraints: bool = True,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Build and return HIR dict from a serialized HardwareGraph JSON.

    Args:
        graph_path: path to HardwareGraph JSON file
        knowledge_dir: optional extra knowledge directory
        include_constraints: if True, run solver and embed results
        session_id: optional session identifier for metadata

    Returns:
        HIR as a plain dict (JSON-serializable)
    """
    with open(graph_path) as f:
        graph_data = json.load(f)
    graph = HardwareGraph.from_dict(graph_data)

    extra_dirs = [Path(knowledge_dir)] if knowledge_dir else None
    resolver = KnowledgeResolver(extra_dirs=extra_dirs)

    hir = _build(graph, resolver=resolver, source="schematic", track="A", session_id=session_id)

    if include_constraints:
        from synth_core.hir_bridge.validator import solve_constraints
        constraints = solve_constraints(hir)
        hir.constraints = constraints

    return json.loads(hir.model_dump_json())


def validate_hir_dict(hir_dict: dict[str, Any]) -> DiagnosticsReport:
    """Validate an HIR dict and return a DiagnosticsReport.

    Args:
        hir_dict: HIR as a plain dict (e.g. loaded from JSON)

    Returns:
        DiagnosticsReport with constraint results
    """
    hir = HIR.model_validate(hir_dict)
    return _validate(hir, validate_schema=True)


def generate_firmware(
    hir_dict: dict[str, Any],
    target: str,
    out_dir: str | Path,
    strict: bool = True,
) -> GenerationSummary:
    """Generate firmware from HIR dict.

    Args:
        hir_dict: HIR as a plain dict
        target: firmware target ("esp32", "stm32f103", ...)
        out_dir: output directory path
        strict: if True, raise on error-level constraint failures

    Returns:
        GenerationSummary with list of written files
    """
    hir = HIR.model_validate(hir_dict)
    return _gen(hir, target=target, out_dir=Path(out_dir), strict=strict)


def parse_schematic(
    schematic_path: str | Path,
    output_format: str = "hir",
    knowledge_dir: str | Path | None = None,
    include_constraints: bool = True,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Parse a KiCad 6 .kicad_sch schematic and return HIR or graph dict.

    Args:
        schematic_path: path to .kicad_sch file
        output_format: "hir" (default) or "graph" (raw HardwareGraph JSON)
        knowledge_dir: optional extra knowledge directory
        include_constraints: if True, run solver and embed results (HIR only)
        session_id: optional session identifier for metadata

    Returns:
        HIR dict or HardwareGraph dict (JSON-serializable)
    """
    sch_path = Path(schematic_path)
    parser = KiCadSchematicParser()
    graph = parser.parse(sch_path)

    if output_format == "graph":
        # Serialise HardwareGraph to a plain dict
        def _pin_to_dict(p: Any) -> dict:
            return {
                "name": p.name,
                "number": p.number,
                "function": p.function,
                "electrical_type": p.electrical_type,
            }

        def _comp_to_dict(c: Any) -> dict:
            return {
                "id": c.id,
                "name": c.name,
                "mpn": c.mpn,
                "role": c.role,
                "manufacturer": c.manufacturer,
                "package": c.package,
                "interface_types": c.interface_types,
                "pins": [_pin_to_dict(p) for p in c.pins],
                "properties": c.properties,
            }

        def _net_to_dict(n: Any) -> dict:
            return {
                "name": n.name,
                "pins": [{"component_id": p[0], "pin_name": p[1]} for p in n.pins],
                "is_power": n.is_power,
                "is_bus": n.is_bus,
            }

        def _bus_to_dict(b: Any) -> dict:
            return {
                "name": b.name,
                "type": b.type,
                "master_id": b.master_id,
                "slave_ids": b.slave_ids,
                "net_names": b.net_names,
                "pin_assignments": b.pin_assignments,
            }

        return {
            "source_file": graph.source_file,
            "components": [_comp_to_dict(c) for c in graph.components],
            "nets": [_net_to_dict(n) for n in graph.nets],
            "buses": [_bus_to_dict(b) for b in graph.buses],
        }

    # Default: build HIR from graph
    extra_dirs = [Path(knowledge_dir)] if knowledge_dir else None
    resolver = KnowledgeResolver(extra_dirs=extra_dirs)
    hir = _build(graph, resolver=resolver, source="schematic", track="A", session_id=session_id)

    if include_constraints:
        from synth_core.hir_bridge.validator import solve_constraints
        hir.constraints = solve_constraints(hir)

    return json.loads(hir.model_dump_json())


def list_components(
    category: str | None = None,
    interface: str | None = None,
    voltage_range: tuple[float, float] | None = None,
    max_cost: float | None = None,
    temp_range: tuple[float, float] | None = None,
    include_cache: bool = True,
    knowledge_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return filtered component catalog as a list of plain dicts.

    Args:
        category: filter by role ("mcu", "sensor", ...)
        interface: filter by interface type ("I2C", "SPI", ...)
        voltage_range: (vdd_min, vdd_max) filter
        max_cost: maximum unit cost in USD
        temp_range: (temp_min_c, temp_max_c) filter
        include_cache: include locally cached components
        knowledge_dir: optional extra knowledge directory

    Returns:
        List of component entry dicts
    """
    extra_dirs = [Path(knowledge_dir)] if knowledge_dir else None
    resolver = KnowledgeResolver(extra_dirs=extra_dirs)
    entries = resolver.query(
        category=category,
        interface=interface,
        voltage_range=voltage_range,
        max_cost=max_cost,
        temp_range=temp_range,
        include_cache=include_cache,
    )
    return [dict(e) for e in entries]
