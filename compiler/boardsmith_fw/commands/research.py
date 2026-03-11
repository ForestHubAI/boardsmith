# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command: research — search datasheets, cache PDFs, extract knowledge."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import typer
from rich.console import Console

from boardsmith_fw.models.component_knowledge import ComponentKnowledge, InterfaceType
from boardsmith_fw.models.hardware_graph import Component, HardwareGraph
from boardsmith_fw.research.datasheet_pipeline import (
    download_datasheet,
    extract_from_datasheet,
    search_datasheet,
)

console = Console()


def run_research(component: str | None, cache_dir: Path, out: Path) -> None:
    out = out.resolve()
    cache_dir = cache_dir.resolve()
    graph_file = out / "hardware_graph.json"

    console.print("[bold blue]Datasheet Research Agent[/]")

    if not graph_file.exists():
        console.print(f"[red]Error: hardware_graph.json not found in {out}. Run 'boardsmith-fw analyze' first.[/]")
        raise typer.Exit(1)

    graph = HardwareGraph.model_validate_json(graph_file.read_text())

    if component:
        targets = [c for c in graph.components if c.id == component]
        if not targets:
            console.print(f"[red]Error: Component '{component}' not found in graph.[/]")
            raise typer.Exit(1)
    else:
        targets = [c for c in graph.components if c.name[0].upper() not in ("R", "C", "L")]

    console.print(f"  Researching {len(targets)} component(s)...")

    knowledge_dir = out / "component_knowledge"
    datasheet_dir = cache_dir / "datasheets"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    datasheet_dir.mkdir(parents=True, exist_ok=True)

    asyncio.run(_research_all(targets, knowledge_dir, datasheet_dir))


async def _research_all(
    targets: list[Component], knowledge_dir: Path, datasheet_dir: Path
) -> None:
    success = 0

    for comp in targets:
        console.print(f"\n[dim]  [{comp.name}] {comp.value or comp.mpn or 'unknown'}[/]")

        kn = ComponentKnowledge(
            component_id=comp.id,
            name=comp.value or comp.mpn or comp.name,
            manufacturer=comp.manufacturer,
            mpn=comp.mpn or comp.value or "",
        )

        try:
            console.print("[dim]    Searching for datasheet...[/]")
            url = await search_datasheet(kn.mpn, kn.manufacturer)

            if url:
                kn.datasheet_url = url
                console.print(f"[dim]    Found: {url}[/]")

                console.print("[dim]    Downloading...[/]")
                local = await download_datasheet(url, datasheet_dir, kn.mpn)
                if local:
                    kn.datasheet_local_path = str(local)
                    console.print(f"[dim]    Cached: {local}[/]")

                    console.print("[dim]    Extracting component info...[/]")
                    extracted = extract_from_datasheet(local, kn.mpn)
                    if extracted:
                        _apply_extracted(kn, extracted)
            else:
                console.print("[yellow]    No datasheet found online.[/]")
                kn.notes.append("Datasheet not found via automated search")

            if kn.interface == InterfaceType.OTHER:
                kn.interface = _infer_interface(comp)

            safe = re.sub(r"[^a-zA-Z0-9_-]", "_", kn.mpn or comp.name)[:64]
            kn_file = knowledge_dir / f"{safe}.json"
            kn_file.write_text(kn.model_dump_json(indent=2))
            console.print(f"[green]    Saved: {kn_file}[/]")
            success += 1

        except Exception as exc:
            console.print(f"[yellow]    Error: {exc}[/]")
            kn.notes.append(f"Research error: {exc}")
            safe = re.sub(r"[^a-zA-Z0-9_-]", "_", kn.mpn or comp.name)[:64]
            kn_file = knowledge_dir / f"{safe}.json"
            kn_file.write_text(kn.model_dump_json(indent=2))

    console.print(f"\n[green]Research complete: {success}/{len(targets)} components processed.[/]")


def _apply_extracted(kn: ComponentKnowledge, data: dict) -> None:
    from boardsmith_fw.models.component_knowledge import (
        ExtractedSections,
        PinInfo,
        RegisterInfo,
        TimingConstraint,
    )

    if data.get("description"):
        kn.description = data["description"]
    if data.get("interface") and data["interface"] != "OTHER":
        kn.interface = InterfaceType(data["interface"])
    if data.get("i2c_address"):
        kn.i2c_address = data["i2c_address"]
    if data.get("pins"):
        kn.pins = [PinInfo(**p) for p in data["pins"]]
    if data.get("registers"):
        kn.registers = [RegisterInfo(**r) for r in data["registers"]]
    if data.get("timing_constraints"):
        kn.timing_constraints = [TimingConstraint(**t) for t in data["timing_constraints"]]
    if data.get("extracted_sections"):
        kn.extracted_sections = ExtractedSections(**data["extracted_sections"])


def _infer_interface(comp: Component) -> InterfaceType:
    names = {p.name.upper() for p in comp.pins}
    if {"SDA", "SCL"} & names:
        return InterfaceType.I2C
    if {"MOSI", "MISO", "SCK"} & names:
        return InterfaceType.SPI
    if {"TX", "RX"} & names:
        return InterfaceType.UART
    return InterfaceType.OTHER
