# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command: analyze — build HardwareGraph and generate analysis report."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from boardsmith_fw.analysis.analysis_report import generate_analysis_report
from boardsmith_fw.analysis.graph_builder import build_hardware_graph
from boardsmith_fw.models.hardware_graph import Component, Net

console = Console()


def run_analyze(out: Path) -> None:
    out = out.resolve()
    imported_file = out / "imported_data.json"

    console.print("[bold blue]Hardware Analysis[/]")

    if not imported_file.exists():
        console.print(f"[red]Error: imported_data.json not found in {out}. Run 'boardsmith-fw import' first.[/]")
        raise typer.Exit(1)

    imported = json.loads(imported_file.read_text())

    console.print("[dim]  Building hardware graph...[/]")
    components = [Component(**c) for c in imported["components"]]
    nets = [Net(**n) for n in imported["nets"]]
    graph = build_hardware_graph(imported["source"], components, nets)
    graph.metadata.warnings.extend(imported.get("warnings", []))

    # Write hardware_graph.json
    graph_file = out / "hardware_graph.json"
    graph_file.write_text(graph.model_dump_json(indent=2))
    console.print(f"  Written: {graph_file}")

    # Write analysis.md
    report = generate_analysis_report(graph)
    report_file = out / "analysis.md"
    report_file.write_text(report)
    console.print(f"  Written: {report_file}")

    console.print("\n[green]Analysis complete![/]")
    console.print(f"  Components: {graph.metadata.total_components}")
    console.print(f"  Nets:       {graph.metadata.total_nets}")
    console.print(f"  MCU:        {graph.mcu.type if graph.mcu else 'not detected'}")
    console.print(f"  Buses:      {', '.join(graph.metadata.detected_buses) or 'none'}")
    console.print(f"  IRQ lines:  {len(graph.irq_lines)}")
    console.print(f"  Power:      {len(graph.power_domains)} domains")
