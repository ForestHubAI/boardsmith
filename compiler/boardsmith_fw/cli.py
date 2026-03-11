# SPDX-License-Identifier: AGPL-3.0-or-later
"""boardsmith-fw CLI — Hardware-Aware Firmware Compiler.

Compiles Eagle/KiCad schematics into validated ESP32/STM32/RP2040 firmware
via a Hardware Intermediate Representation (HIR) with constraint solving.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="boardsmith-fw",
    help="Hardware-aware firmware compiler: Eagle/KiCad schematics → ESP32/STM32/RP2040 firmware.",
    add_completion=False,
)


@app.command(name="import")
def import_cmd(
    path: Path = typer.Argument(..., help="Path to schematic (.sch, .kicad_sch) or netlist (.net/.txt)"),
    out: Path = typer.Option(".", "--out", help="Output directory"),
) -> None:
    """Parse Eagle/KiCad schematic or netlist into internal model."""
    from boardsmith_fw.commands.import_cmd import run_import

    run_import(path, out)


@app.command()
def analyze(
    out: Path = typer.Option(".", "--out", help="Output directory"),
) -> None:
    """Generate hardware_graph.json and analysis.md from imported data."""
    from boardsmith_fw.commands.analyze import run_analyze

    run_analyze(out)


@app.command()
def research(
    component: Optional[str] = typer.Option(None, "--component", help="Research a specific component only"),
    cache_dir: Path = typer.Option(".cache", "--cache-dir", help="Cache directory for datasheets"),
    out: Path = typer.Option(".", "--out", help="Output directory"),
) -> None:
    """Search datasheets, cache PDFs, extract component knowledge."""
    from boardsmith_fw.commands.research import run_research

    run_research(component, cache_dir, out)


@app.command()
def generate(
    description: str = typer.Option(..., "--description", help="Firmware function description"),
    lang: str = typer.Option("c", "--lang", help="Output language: c or cpp"),
    target: str = typer.Option("auto", "--target", help="Target MCU: auto, esp32, stm32, or rp2040"),
    out: Path = typer.Option("generated_firmware", "--out", help="Output directory"),
    model: str = typer.Option("gpt-4o", "--model", help="LLM model to use"),
    rtos: bool = typer.Option(False, "--rtos", help="Use FreeRTOS task-per-bus architecture"),
    platformio: bool = typer.Option(False, "--platformio", help="Generate platformio.ini"),
    ci: bool = typer.Option(False, "--ci", help="Generate GitHub Actions CI workflow"),
) -> None:
    """Generate firmware project from hardware graph + knowledge."""
    from boardsmith_fw.commands.generate import run_generate

    run_generate(
        description, lang, target, out, model,
        rtos=rtos, platformio=platformio, ci=ci,
    )


@app.command()
def build(
    project: Path = typer.Option("generated_firmware", "--project", help="Path to generated project"),
    target: str = typer.Option("auto", "--target", help="Target MCU: auto, esp32, stm32, or rp2040"),
) -> None:
    """Build the generated firmware project."""
    from boardsmith_fw.commands.build import run_build

    run_build(project, target)


@app.command()
def flash(
    project: Path = typer.Option("generated_firmware", "--project", help="Path to generated project"),
    target: str = typer.Option("auto", "--target", help="Target MCU: auto, esp32, stm32, or rp2040"),
    port: str = typer.Option("auto", "--port", help="Serial port (auto-detect if 'auto')"),
) -> None:
    """Flash firmware to the target MCU."""
    from boardsmith_fw.commands.flash import run_flash

    run_flash(project, target, port)


@app.command()
def monitor(
    port: str = typer.Option("auto", "--port", help="Serial port (auto-detect if 'auto')"),
    baud: int = typer.Option(115200, "--baud", help="Baud rate"),
) -> None:
    """Open serial monitor (miniterm) to the target device."""
    from boardsmith_fw.commands.flash import run_monitor

    run_monitor(port, baud)


@app.command()
def verify(
    project: Path = typer.Option("generated_firmware", "--project", help="Path to generated project"),
    target: str = typer.Option("auto", "--target", help="Target MCU: auto, esp32, stm32, or rp2040"),
    no_docker: bool = typer.Option(False, "--no-docker", help="Skip Docker, use local toolchain only"),
) -> None:
    """Verify that generated firmware compiles (Docker or local)."""
    from boardsmith_fw.commands.verify import run_verify

    run_verify(project, target, docker=not no_docker)


@app.command()
def extract(
    pdf: Path = typer.Argument(..., help="Path to datasheet PDF"),
    model: str = typer.Option("gpt-4o", "--model", help="LLM model for extraction"),
    max_pages: int = typer.Option(40, "--max-pages", help="Max PDF pages to process"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save to local cache"),
    out_json: Optional[Path] = typer.Option(
        None, "--out", help="Write extracted knowledge JSON to file",
    ),
) -> None:
    """Extract component knowledge from a datasheet PDF using LLM."""
    import asyncio

    from rich.console import Console

    from boardsmith_fw.knowledge.extractor import (
        extract_from_pdf,
        save_extracted_knowledge,
    )

    console = Console()

    if not pdf.exists():
        console.print(f"[red]File not found: {pdf}[/]")
        raise typer.Exit(1)

    console.print(f"[bold]Extracting from:[/] {pdf}")
    console.print(f"[dim]Model: {model}, max pages: {max_pages}[/]")

    result = asyncio.run(extract_from_pdf(pdf, model=model, max_pages=max_pages))

    if result.sections_found:
        console.print(
            f"[green]Sections found:[/] {', '.join(result.sections_found)}"
        )
    else:
        console.print("[yellow]Warning: no datasheet sections identified[/]")

    for err in result.errors:
        console.print(f"[red]{err}[/]")

    if result.knowledge:
        k = result.knowledge
        console.print(f"\n[green bold]Extracted: {k.name}[/] ({k.manufacturer})")
        console.print(f"  Category:    {k.category}")
        console.print(f"  Interface:   {k.interface.value}")
        if k.i2c_address:
            console.print(f"  I2C Address: {k.i2c_address}")
        console.print(f"  Registers:   {len(k.registers)}")
        console.print(f"  Init Steps:  {len(k.init_sequence)}")
        console.print(f"  Timing:      {len(k.timing_constraints)}")
        console.print(f"  Notes:       {len(k.notes)}")

        if save:
            path = save_extracted_knowledge(k)
            console.print(f"\n[green]Saved to:[/] {path}")

        if out_json:
            out_json.write_text(k.model_dump_json(indent=2))
            console.print(f"[green]JSON written to:[/] {out_json}")
    else:
        console.print("[red]Extraction failed — no knowledge produced.[/]")
        raise typer.Exit(1)


@app.command()
def init() -> None:
    """Generate a default .boardsmith-fw.yaml config file."""
    from rich.console import Console

    from boardsmith_fw.config import generate_default_config

    console = Console()
    path = Path(".boardsmith-fw.yaml")
    if path.exists():
        console.print("[yellow].boardsmith-fw.yaml already exists. Not overwriting.[/]")
        raise typer.Exit(1)
    path.write_text(generate_default_config())
    console.print(f"[green]Created {path}[/]")


@app.command()
def knowledge(
    mpn: Optional[str] = typer.Argument(None, help="Look up a specific MPN"),
) -> None:
    """List built-in component knowledge or look up a specific MPN."""
    from rich.console import Console

    from boardsmith_fw.knowledge.builtin_db import list_builtin_mpns, lookup_builtin

    console = Console()
    if mpn:
        k = lookup_builtin(mpn)
        if k:
            console.print(f"[green]Found: {k.name}[/] ({k.manufacturer})")
            console.print(f"  Interface: {k.interface.value}")
            if k.i2c_address:
                console.print(f"  I2C Address: {k.i2c_address}")
            console.print(f"  Registers: {len(k.registers)}")
            console.print(f"  Init Steps: {len(k.init_sequence)}")
            for step in k.init_sequence:
                desc = f"  {step.order}. {step.description}"
                if step.reg_addr and step.value:
                    desc += f" [{step.reg_addr} = {step.value}]"
                if step.delay_ms:
                    desc += f" (wait {step.delay_ms}ms)"
                console.print(f"[dim]{desc}[/]")
        else:
            console.print(f"[yellow]No built-in knowledge for '{mpn}'[/]")
    else:
        mpns = list_builtin_mpns()
        console.print(f"[bold]Built-in knowledge: {len(mpns)} MPN(s)[/]")
        for m in mpns:
            console.print(f"  - {m}")


@app.command()
def report(
    out: Path = typer.Option(".", "--out", help="Working directory with hardware_graph.json"),
    fmt: str = typer.Option("json", "--format", help="Output format: json or html"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write report to file (stdout if omitted)"),
) -> None:
    """Export constraint validation report (JSON or HTML)."""
    import json as json_mod

    from rich.console import Console

    from boardsmith_fw.analysis.constraint_report import export_html, export_json
    from boardsmith_fw.analysis.constraint_solver import solve_constraints
    from boardsmith_fw.analysis.hir_builder import build_hir
    from boardsmith_fw.knowledge.resolver import resolve_knowledge

    console = Console()

    graph_path = out / "hardware_graph.json"
    if not graph_path.exists():
        console.print(f"[red]Not found: {graph_path}[/]  (run 'boardsmith-fw analyze' first)")
        raise typer.Exit(1)

    graph_data = json_mod.loads(graph_path.read_text())
    from boardsmith_fw.models.hardware_graph import HardwareGraph

    graph = HardwareGraph(**graph_data)
    knowledge = resolve_knowledge(graph)
    hir = build_hir(graph, knowledge)
    hir.constraints = solve_constraints(hir, graph)

    if fmt == "html":
        result = export_html(hir)
    else:
        result = export_json(hir)

    if output:
        output.write_text(result)
        console.print(f"[green]Report written to:[/] {output}")
    else:
        console.print(result)

    summary = hir.constraints
    errors = hir.get_errors()
    warnings = hir.get_failing_constraints()
    console.print(
        f"\n[bold]{len(summary)} constraints:[/] "
        f"[red]{len(errors)} errors[/], "
        f"[yellow]{len(warnings) - len(errors)} warnings[/]"
    )
    if errors:
        console.print("[red bold]INVALID[/]")
    else:
        console.print("[green bold]VALID[/]")


@app.command()
def board(
    schema: Path = typer.Argument(..., help="Path to board schema YAML file"),
    out: Path = typer.Option(".", "--out", help="Output directory"),
    constraints: bool = typer.Option(True, "--constraints/--no-constraints", help="Run constraint solver"),
) -> None:
    """Parse a board schema YAML and produce a validated HardwareGraph + HIR."""
    from boardsmith_fw.commands.import_cmd import _run_board_schema_import

    if not schema.exists():
        from rich.console import Console
        Console().print(f"[red]Not found: {schema}[/]")
        raise typer.Exit(1)

    _run_board_schema_import(schema, out)


@app.command()
def intent(
    intent_file: Path = typer.Argument(..., help="Path to intent YAML file"),
    target: str = typer.Option("auto", "--target", help="Target MCU: auto, esp32, stm32, rp2040"),
    out: Path = typer.Option("generated_firmware", "--out", help="Output directory"),
) -> None:
    """Compile a firmware intent YAML into C application loop code."""
    from rich.console import Console

    from boardsmith_fw.codegen.intent_codegen import compile_intent_from_file

    console = Console()

    if not intent_file.exists():
        console.print(f"[red]Not found: {intent_file}[/]")
        raise typer.Exit(1)

    console.print("[bold blue]Intent Compiler[/]")
    console.print(f"  Input:  {intent_file}")
    console.print(f"  Target: {target}")

    result = compile_intent_from_file(intent_file, target=target)

    out.mkdir(parents=True, exist_ok=True)
    for filename, content in result.files:
        dest = out / filename
        dest.write_text(content)
        console.print(f"  [green]→[/] {dest}")

    for w in result.warnings:
        console.print(f"  [yellow]! {w}[/]")

    console.print(f"\n[green]Intent compiled:[/] {len(result.files)} file(s)")


@app.command()
def safety(
    target: str = typer.Option("esp32", "--target", help="Target MCU: esp32, stm32, rp2040"),
    out: Path = typer.Option("generated_firmware", "--out", help="Output directory"),
    wdt_timeout: int = typer.Option(5000, "--wdt-timeout", help="Watchdog timeout in ms"),
    stack_min: int = typer.Option(256, "--stack-min", help="Minimum free stack bytes"),
    heap_low: int = typer.Option(4096, "--heap-low", help="Heap low watermark bytes"),
) -> None:
    """Generate IEC 61508 safety templates (watchdog, stack, heap monitoring)."""
    from rich.console import Console

    from boardsmith_fw.codegen.safety_codegen import (
        HeapConfig,
        SafetyConfig,
        StackConfig,
        WatchdogConfig,
        generate_safety,
    )

    console = Console()

    cfg = SafetyConfig(
        watchdog=WatchdogConfig(timeout_ms=wdt_timeout),
        stack=StackConfig(min_free_bytes=stack_min),
        heap=HeapConfig(low_watermark_bytes=heap_low),
    )

    console.print("[bold blue]Safety Template Generator[/]")
    console.print(f"  Target:       {target}")
    console.print(f"  WDT timeout:  {wdt_timeout}ms")
    console.print(f"  Stack min:    {stack_min} bytes")
    console.print(f"  Heap low:     {heap_low} bytes")

    result = generate_safety(target=target, config=cfg)

    out.mkdir(parents=True, exist_ok=True)
    for filename, content in result.files:
        dest = out / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        console.print(f"  [green]→[/] {dest}")

    for w in result.warnings:
        console.print(f"  [yellow]! {w}[/]")

    console.print(f"\n[green]Safety templates generated:[/] {len(result.files)} file(s)")


@app.command()
def ota(
    target: str = typer.Option("esp32", "--target", help="Target MCU: esp32, stm32, rp2040"),
    out: Path = typer.Option("generated_firmware", "--out", help="Output directory"),
    server_url: str = typer.Option("https://firmware.example.com/ota", "--server", help="OTA server URL"),
    version: str = typer.Option("1.0.0", "--version", help="Firmware version string"),
) -> None:
    """Generate OTA update scaffolding (dual-bank, flash write, reboot)."""
    from rich.console import Console

    from boardsmith_fw.codegen.ota_codegen import OTAConfig, generate_ota

    console = Console()

    cfg = OTAConfig(server_url=server_url, firmware_version=version)

    console.print("[bold blue]OTA Scaffolding Generator[/]")
    console.print(f"  Target:  {target}")
    console.print(f"  Version: {version}")
    if target == "esp32":
        console.print(f"  Server:  {server_url}")

    result = generate_ota(target=target, config=cfg)

    out.mkdir(parents=True, exist_ok=True)
    for filename, content in result.files:
        dest = out / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        console.print(f"  [green]→[/] {dest}")

    for w in result.warnings:
        console.print(f"  [yellow]! {w}[/]")

    console.print(f"\n[green]OTA scaffolding generated:[/] {len(result.files)} file(s)")


@app.command()
def topology(
    topo_file: Path = typer.Argument(..., help="Path to topology YAML file"),
    out: Path = typer.Option("generated_firmware", "--out", help="Output directory"),
) -> None:
    """Generate multi-board communication code from a topology YAML."""
    from rich.console import Console

    from boardsmith_fw.codegen.topology_codegen import generate_topology, parse_topology_file

    console = Console()

    if not topo_file.exists():
        console.print(f"[red]Not found: {topo_file}[/]")
        raise typer.Exit(1)

    console.print("[bold blue]Topology Compiler[/]")
    console.print(f"  Input: {topo_file}")

    topo = parse_topology_file(topo_file)
    console.print(f"  System: {topo.system_name}")
    console.print(f"  Nodes:  {len(topo.nodes)}")
    console.print(f"  Links:  {len(topo.links)}")

    result = generate_topology(topo)

    out.mkdir(parents=True, exist_ok=True)
    for filename, content in result.files:
        dest = out / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        console.print(f"  [green]→[/] {dest}")

    for w in result.warnings:
        console.print(f"  [yellow]! {w}[/]")

    console.print(f"\n[green]Topology compiled:[/] {len(result.files)} file(s)")


@app.command(name="docker-build")
def docker_build(
    target: str = typer.Option("esp32", "--target", help="Target MCU: esp32, esp32c3, stm32, rp2040, nrf52"),
    out: Path = typer.Option("generated_firmware", "--out", help="Output directory"),
    project_name: str = typer.Option("firmware", "--name", help="Project name"),
) -> None:
    """Generate Docker build configuration for cloud compile verification."""
    from rich.console import Console

    from boardsmith_fw.codegen.docker_build import generate_docker_build

    console = Console()

    console.print("[bold blue]Docker Build Generator[/]")
    console.print(f"  Target:  {target}")
    console.print(f"  Project: {project_name}")

    result = generate_docker_build(target=target, project_name=project_name)

    out.mkdir(parents=True, exist_ok=True)
    for filename, content in result.files:
        dest = out / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        console.print(f"  [green]→[/] {dest}")

    for w in result.warnings:
        console.print(f"  [yellow]! {w}[/]")

    console.print(f"\n[green]Docker build config generated:[/] {len(result.files)} file(s)")


@app.command(name="vscode-extension")
def vscode_extension(
    out: Path = typer.Option("boardsmith-fw-vscode", "--out", help="Output directory for VS Code extension"),
    name: str = typer.Option("boardsmith-fw", "--name", help="Extension name"),
    publisher: str = typer.Option("boardsmith-fw", "--publisher", help="Publisher name"),
) -> None:
    """Generate a VS Code extension for constraint visualization and diagnostics."""
    from rich.console import Console

    from boardsmith_fw.codegen.vscode_extension import generate_vscode_extension

    console = Console()

    console.print("[bold blue]VS Code Extension Generator[/]")
    console.print(f"  Name:      {name}")
    console.print(f"  Publisher: {publisher}")

    result = generate_vscode_extension(
        extension_name=name, publisher=publisher,
    )

    out.mkdir(parents=True, exist_ok=True)
    for filename, content in result.files:
        dest = out / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        console.print(f"  [green]→[/] {dest}")

    for w in result.warnings:
        console.print(f"  [yellow]! {w}[/]")

    console.print(f"\n[green]VS Code extension generated:[/] {len(result.files)} file(s)")
    console.print(f"[dim]Next: cd {out} && npm install && npm run compile[/]")


@app.command()
def hil(
    target: str = typer.Option("esp32", "--target", help="Target MCU: esp32, esp32c3, stm32, rp2040, nrf52"),
    out: Path = typer.Option(".", "--out", help="Output directory"),
    firmware: str = typer.Option("build/firmware.elf", "--firmware", help="Path to firmware ELF"),
    timeout: int = typer.Option(10, "--timeout", help="Simulation timeout in seconds"),
    peripherals: Optional[str] = typer.Option(
        None, "--peripherals",
        help="Comma-separated peripherals (e.g. BME280,SSD1306)",
    ),
) -> None:
    """Generate Hardware-in-the-Loop simulation configs (QEMU/Renode)."""
    from rich.console import Console

    from boardsmith_fw.codegen.hil_simulation import HILConfig, generate_hil

    console = Console()

    periph_list = [p.strip() for p in peripherals.split(",")] if peripherals else []

    cfg = HILConfig(
        firmware_elf=firmware,
        timeout_s=timeout,
        peripherals=periph_list,
    )

    console.print("[bold blue]HIL Simulation Generator[/]")
    console.print(f"  Target:      {target}")
    console.print(f"  Firmware:    {firmware}")
    console.print(f"  Timeout:     {timeout}s")
    if periph_list:
        console.print(f"  Peripherals: {', '.join(periph_list)}")

    result = generate_hil(target=target, config=cfg)

    out.mkdir(parents=True, exist_ok=True)
    for filename, content in result.files:
        dest = out / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        console.print(f"  [green]→[/] {dest}")

    for w in result.warnings:
        console.print(f"  [yellow]! {w}[/]")

    console.print(f"\n[green]HIL configs generated:[/] {len(result.files)} file(s)")


if __name__ == "__main__":
    app()
