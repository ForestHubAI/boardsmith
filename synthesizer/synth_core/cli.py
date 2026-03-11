# SPDX-License-Identifier: AGPL-3.0-or-later
"""synth-core CLI — HIR bridge commands + Boardsmith synthesize command."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich import print as rprint

console = Console()


@click.group()
@click.version_option(version="0.6.0", prog_name="boardsmith-fw")
def cli() -> None:
    """boardsmith-fw: Hardware Intermediate Representation compiler and synthesizer."""


# ---------------------------------------------------------------------------
# Compiler: export-hir
# ---------------------------------------------------------------------------

@cli.command("export-hir")
@click.option("--graph", required=True, type=click.Path(exists=True), help="HardwareGraph JSON file")
@click.option("--knowledge-dir", type=click.Path(), default=None, help="Extra knowledge directory")
@click.option("--output", "-o", required=True, type=click.Path(), help="Output HIR JSON path")
@click.option("--include-constraints", is_flag=True, default=True, help="Run solver and embed constraints")
@click.option("--session-id", default=None, help="Session ID for metadata")
def export_hir(graph: str, knowledge_dir: str | None, output: str, include_constraints: bool, session_id: str | None) -> None:
    """Export canonical HIR from a HardwareGraph JSON file."""
    from synth_core.api.compiler import export_hir as _export

    with console.status("Building HIR..."):
        hir_dict = _export(
            graph_path=graph,
            knowledge_dir=knowledge_dir,
            include_constraints=include_constraints,
            session_id=session_id,
        )

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(hir_dict, indent=2))
    console.print(f"[green]HIR written to[/green] {out_path}")


# ---------------------------------------------------------------------------
# Compiler: parse-schematic
# ---------------------------------------------------------------------------

@cli.command("parse-schematic")
@click.option("--input", "-i", "input_path", required=True, type=click.Path(exists=True),
              help="KiCad 6 .kicad_sch schematic file")
@click.option("--output", "-o", required=True, type=click.Path(), help="Output file path (JSON)")
@click.option("--format", "fmt", type=click.Choice(["hir", "graph"]), default="hir",
              help="Output format: 'hir' (full HIR, default) or 'graph' (HardwareGraph JSON)")
@click.option("--knowledge-dir", type=click.Path(), default=None, help="Extra knowledge directory")
@click.option("--include-constraints/--no-constraints", default=True,
              help="Run constraint solver and embed results (HIR format only)")
@click.option("--session-id", default=None, help="Session ID for HIR metadata")
def parse_schematic_cmd(
    input_path: str,
    output: str,
    fmt: str,
    knowledge_dir: str | None,
    include_constraints: bool,
    session_id: str | None,
) -> None:
    """Parse a KiCad 6 .kicad_sch schematic into HIR or HardwareGraph JSON.

    Reads component instances, net labels, and wire connectivity from a
    KiCad 6 S-expression schematic and outputs either a canonical HIR
    (--format hir) or a raw HardwareGraph dict (--format graph).

    Exit codes: 0=success, 1=parse error, 2=tool error
    """
    from synth_core.api.compiler import parse_schematic

    try:
        with console.status(f"Parsing schematic [cyan]{input_path}[/cyan]..."):
            result = parse_schematic(
                schematic_path=input_path,
                output_format=fmt,
                knowledge_dir=knowledge_dir,
                include_constraints=include_constraints,
                session_id=session_id,
            )
    except FileNotFoundError as e:
        console.print(f"[red]File not found:[/red] {e}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Parse error:[/red] {e}")
        sys.exit(2)

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))

    if fmt == "hir":
        n_comp = len(result.get("components", []))
        n_net  = len(result.get("nets", []))
        n_bus  = len(result.get("buses", []))
        console.print(
            f"[green]HIR written to[/green] {out_path} "
            f"({n_comp} components, {n_net} nets, {n_bus} buses)"
        )
    else:
        n_comp = len(result.get("components", []))
        console.print(f"[green]HardwareGraph written to[/green] {out_path} ({n_comp} components)")


# ---------------------------------------------------------------------------
# Compiler: validate-hir
# ---------------------------------------------------------------------------

@cli.command("validate-hir")
@click.option("--hir", required=True, type=click.Path(exists=True), help="HIR JSON file to validate")
@click.option("--diagnostics", type=click.Path(), default=None, help="Output diagnostics JSON path")
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="text")
def validate_hir_cmd(hir: str, diagnostics: str | None, fmt: str) -> None:
    """Validate HIR schema and semantic constraints.

    Exit codes: 0=valid, 1=invalid, 2=tool error
    """
    from synth_core.api.compiler import validate_hir_dict

    try:
        with open(hir) as f:
            hir_dict = json.load(f)
    except Exception as e:
        console.print(f"[red]Failed to parse HIR:[/red] {e}")
        sys.exit(2)

    try:
        report = validate_hir_dict(hir_dict)
    except Exception as e:
        console.print(f"[red]Validation tool error:[/red] {e}")
        sys.exit(2)

    report_dict = report.to_dict()

    if fmt == "json":
        click.echo(json.dumps(report_dict, indent=2))
    else:
        _print_diagnostics_text(report_dict)

    if diagnostics:
        diag_path = Path(diagnostics)
        diag_path.parent.mkdir(parents=True, exist_ok=True)
        diag_path.write_text(json.dumps(report_dict, indent=2))
        if fmt == "text":
            console.print(f"Diagnostics written to [cyan]{diag_path}[/cyan]")

    sys.exit(0 if report.valid else 1)


def _print_diagnostics_text(report: dict) -> None:
    valid = report["valid"]
    s = report["summary"]
    color = "green" if valid else "red"
    status_str = "VALID" if valid else "INVALID"
    console.print(f"\n[bold {color}]{status_str}[/bold {color}] — "
                  f"errors={s['errors']} warnings={s['warnings']} info={s['info']} unknown={s['unknown']}\n")

    for d in report["diagnostics"]:
        sev = d["severity"]
        color_map = {"error": "red", "warning": "yellow", "info": "cyan"}
        c = color_map.get(sev, "white")
        st = d["status"] if d["status"] != "pass_" else "pass"
        console.print(f"  [{c}][{sev.upper()}][/{c}] [{st}] {d['id']}: {d['message']}")
        if d.get("suggested_fixes"):
            for fix in d["suggested_fixes"]:
                console.print(f"         → {fix}")


# ---------------------------------------------------------------------------
# Compiler: generate-from-hir
# ---------------------------------------------------------------------------

@cli.command("generate-from-hir")
@click.option("--hir", required=True, type=click.Path(exists=True), help="HIR JSON file")
@click.option("--target", required=True, type=str, help="Target platform (esp32, stm32f103, ...)")
@click.option("--out", required=True, type=click.Path(), help="Output directory for firmware")
@click.option("--strict/--no-strict", default=True, help="Block generation on error-level constraint failures")
def generate_from_hir_cmd(hir: str, target: str, out: str, strict: bool) -> None:
    """Generate firmware from an HIR JSON file."""
    from synth_core.api.compiler import generate_firmware

    with open(hir) as f:
        hir_dict = json.load(f)

    try:
        with console.status(f"Generating firmware for [bold]{target}[/bold]..."):
            summary = generate_firmware(hir_dict, target=target, out_dir=out, strict=strict)
    except ValueError as e:
        console.print(f"[red]Generation failed:[/red] {e}")
        sys.exit(1)

    console.print(f"[green]Firmware generated[/green] → {summary.out_dir}")
    for f_name in summary.files_written:
        console.print(f"  {f_name}")
    if summary.warnings:
        for w in summary.warnings:
            console.print(f"[yellow]WARN:[/yellow] {w}")


# ---------------------------------------------------------------------------
# Compiler: list-components
# ---------------------------------------------------------------------------

@cli.command("list-components")
@click.option("--format", "fmt", type=click.Choice(["json", "table"]), default="table")
@click.option("--category", default=None, help="Filter by category (mcu, sensor, ...)")
@click.option("--interface", default=None, help="Filter by interface (I2C, SPI, ...)")
@click.option("--max-cost", type=float, default=None, help="Maximum unit cost USD")
@click.option("--include-cache/--no-cache", default=True)
@click.option("--knowledge-dir", type=click.Path(), default=None)
def list_components_cmd(fmt: str, category: str | None, interface: str | None,
                         max_cost: float | None, include_cache: bool,
                         knowledge_dir: str | None) -> None:
    """List components from the knowledge database."""
    from synth_core.api.compiler import list_components

    entries = list_components(
        category=category,
        interface=interface,
        max_cost=max_cost,
        include_cache=include_cache,
        knowledge_dir=knowledge_dir,
    )

    if fmt == "json":
        click.echo(json.dumps(entries, indent=2))
        return

    table = Table(title="Component Catalog", show_lines=True)
    table.add_column("MPN", style="bold cyan")
    table.add_column("Manufacturer")
    table.add_column("Name")
    table.add_column("Category")
    table.add_column("Interfaces")
    table.add_column("I2C Addresses")
    table.add_column("Cost (USD)")

    for e in entries:
        addrs = ", ".join(e.get("known_i2c_addresses", []))
        ifaces = ", ".join(e.get("interface_types", []))
        cost = f"${e.get('unit_cost_usd', 0):.2f}" if e.get("unit_cost_usd") else "-"
        table.add_row(
            e.get("mpn", ""),
            e.get("manufacturer", ""),
            e.get("name", ""),
            e.get("category", ""),
            ifaces,
            addrs or "-",
            cost,
        )

    console.print(table)
    console.print(f"\n[dim]{len(entries)} component(s) found[/dim]")


# ---------------------------------------------------------------------------
# Boardsmith: synthesize (imported from boardsmith_hw)
# ---------------------------------------------------------------------------

@cli.command("synthesize")
@click.option("--prompt", "-p", required=True, type=str, help="Natural language design prompt")
@click.option("--out", "-o", required=True, type=click.Path(), help="Output directory")
@click.option("--target", default="esp32", help="Firmware target platform")
@click.option("--max-iterations", default=5, type=int, help="Max validation loop iterations")
@click.option("--confidence-threshold", default=0.65, type=float, help="Minimum confidence to proceed")
@click.option("--seed", default=None, type=int, help="Random seed for determinism")
@click.option("--generate-firmware/--no-firmware", "gen_fw", default=False,
              help="Call generate-from-hir after valid HIR")
@click.option("--use-llm/--no-llm", default=True,
              help="Use LLM for intent parsing (requires ANTHROPIC_API_KEY)")
def synthesize_cmd(
    prompt: str,
    out: str,
    target: str,
    max_iterations: int,
    confidence_threshold: float,
    seed: int | None,
    gen_fw: bool,
    use_llm: bool,
) -> None:
    """Synthesize hardware design from a natural-language prompt (Boardsmith)."""
    from boardsmith_hw.synthesizer import Synthesizer

    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    synthesizer = Synthesizer(
        out_dir=out_dir,
        target=target,
        max_iterations=max_iterations,
        confidence_threshold=confidence_threshold,
        seed=seed,
        use_llm=use_llm,
    )

    console.print(f"[bold]Boardsmith Synthesizer[/bold] — prompt: [italic]{prompt}[/italic]")
    result = synthesizer.run(prompt, generate_firmware=gen_fw)

    if result.success:
        console.print(f"\n[green bold]Synthesis successful[/green bold] (confidence={result.confidence:.2f})")
    else:
        console.print(f"\n[yellow bold]Synthesis completed with issues[/yellow bold] (confidence={result.confidence:.2f})")

    console.print(f"Output: {out_dir}")
    for fname in result.artifacts:
        console.print(f"  {fname}")

    if result.hitl_required:
        console.print("\n[yellow]Human-in-the-loop review required:[/yellow]")
        for msg in result.hitl_messages:
            console.print(f"  • {msg}")

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    cli()
