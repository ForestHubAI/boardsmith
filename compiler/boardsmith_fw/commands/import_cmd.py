# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command: import — parse Eagle schematic/netlist/board-schema into internal model."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from boardsmith_fw.parser.eagle_parser import parse_eagle_schematic
from boardsmith_fw.parser.kicad_parser import parse_kicad_schematic
from boardsmith_fw.parser.netlist_parser import parse_eagle_netlist

console = Console()


def run_import(path: Path, out: Path) -> None:
    path = path.resolve()
    out = out.resolve()

    console.print("[bold blue]Schematic Import[/]")
    console.print(f"  Input:  {path}")
    console.print(f"  Output: {out}")

    if not path.exists():
        console.print(f"[red]Error: File not found: {path}[/]")
        raise typer.Exit(1)

    ext = path.suffix.lower()
    if ext == ".sch":
        console.print("[dim]  Parsing Eagle schematic XML...[/]")
        result = parse_eagle_schematic(path)
    elif ext == ".kicad_sch":
        console.print("[dim]  Parsing KiCad schematic...[/]")
        result = parse_kicad_schematic(path)
    elif ext in (".net", ".txt"):
        console.print("[dim]  Parsing Eagle netlist...[/]")
        result = parse_eagle_netlist(path)
    elif ext in (".yaml", ".yml"):
        console.print("[dim]  Parsing Board Schema YAML...[/]")
        _run_board_schema_import(path, out)
        return
    else:
        console.print(
            f"[red]Error: Unsupported format '{ext}'. "
            f"Supported: .sch, .kicad_sch, .net, .txt, .yaml, .yml[/]"
        )
        raise typer.Exit(1)

    out.mkdir(parents=True, exist_ok=True)
    output_file = out / "imported_data.json"

    data = {
        "source": str(path),
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "components": [c.model_dump() for c in result.components],
        "nets": [n.model_dump() for n in result.nets],
        "warnings": result.warnings,
    }
    output_file.write_text(json.dumps(data, indent=2))

    console.print("\n[green]Import successful![/]")
    console.print(f"  Components: {len(result.components)}")
    console.print(f"  Nets:       {len(result.nets)}")
    console.print(f"  Warnings:   {len(result.warnings)}")
    for w in result.warnings:
        console.print(f"  [yellow]  ! {w}[/]")
    console.print(f"  Output:     {output_file}")


def _run_board_schema_import(path: Path, out: Path) -> None:
    """Parse a board schema YAML directly into a HardwareGraph and save it."""
    from boardsmith_fw.analysis.constraint_solver import solve_constraints
    from boardsmith_fw.analysis.hir_builder import build_hir
    from boardsmith_fw.knowledge.resolver import resolve_knowledge
    from boardsmith_fw.parser.board_schema_parser import parse_board_schema

    graph = parse_board_schema(path)
    knowledge = resolve_knowledge(graph)
    hir = build_hir(graph, knowledge)
    hir.constraints = solve_constraints(hir, graph)

    out.mkdir(parents=True, exist_ok=True)

    # Save hardware_graph.json (same format as analyze command)
    graph_file = out / "hardware_graph.json"
    graph_file.write_text(graph.model_dump_json(indent=2))

    # Save HIR
    hir_file = out / "hir.json"
    hir_file.write_text(hir.model_dump_json(indent=2))

    errors = hir.get_errors()
    warnings = hir.get_failing_constraints()

    console.print("\n[green]Board Schema import successful![/]")
    console.print(f"  MCU:        {graph.mcu.type if graph.mcu else 'unknown'}")
    console.print(f"  Components: {len(graph.components)}")
    console.print(f"  Buses:      {len(graph.buses)}")
    console.print(
        f"  Constraints:{len(hir.constraints)} "
        f"([red]{len(errors)} errors[/], "
        f"[yellow]{len(warnings) - len(errors)} warnings[/])"
    )
    console.print(f"  Graph:      {graph_file}")
    console.print(f"  HIR:        {hir_file}")
    if errors:
        console.print("\n[red bold]CONSTRAINT ERRORS:[/]")
        for e in errors:
            console.print(f"  [red]  ✗ {e.description}[/]")
