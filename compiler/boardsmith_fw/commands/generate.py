# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command: generate — produce firmware from hardware graph + knowledge."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console

from boardsmith_fw.codegen.llm_wrapper import GenerationRequest, generate_firmware
from boardsmith_fw.knowledge.resolver import resolve_knowledge
from boardsmith_fw.models.component_knowledge import ComponentKnowledge
from boardsmith_fw.models.hardware_graph import HardwareGraph

console = Console()


def run_generate(
    description: str,
    lang: str,
    target: str,
    out: Path,
    model: str,
    rtos: bool = False,
    platformio: bool = False,
    ci: bool = False,
) -> None:
    out = out.resolve()
    graph_file = Path("hardware_graph.json").resolve()
    knowledge_dir = Path("component_knowledge").resolve()

    console.print("[bold blue]Firmware Code Generation[/]")
    console.print(f"  Description: {description}")
    console.print(f"  Language:    {lang}")
    console.print(f"  Target:      {target}")
    if rtos:
        console.print("  Architecture: FreeRTOS task-per-bus")
    if platformio:
        console.print("  PlatformIO:  enabled")
    if ci:
        console.print("  CI/CD:       GitHub Actions")
    console.print(f"  Output:      {out}")

    if not graph_file.exists():
        console.print(
            "[red]Error: hardware_graph.json not found. "
            "Run 'boardsmith-fw analyze' first.[/]"
        )
        raise typer.Exit(1)

    graph = HardwareGraph.model_validate_json(graph_file.read_text())

    # 1. Auto-resolve knowledge from built-in DB + cache
    knowledge = resolve_knowledge(graph)
    builtin_count = sum(
        1 for k in knowledge if "Minimal knowledge" not in " ".join(k.notes)
    )
    minimal_count = len(knowledge) - builtin_count
    console.print(
        f"[dim]  Auto-resolved: {builtin_count} built-in, "
        f"{minimal_count} minimal[/]"
    )

    # 2. Merge with manually-researched knowledge
    if knowledge_dir.exists():
        for f in sorted(knowledge_dir.glob("*.json")):
            try:
                ck = ComponentKnowledge.model_validate_json(f.read_text())
                knowledge = [
                    k for k in knowledge if k.component_id != ck.component_id
                ]
                knowledge.append(ck)
            except Exception:
                pass
        console.print(f"[dim]  Total knowledge: {len(knowledge)} component(s)[/]")

    # 3. Build HIR (Hardware Intermediate Representation)
    from boardsmith_fw.analysis.hir_builder import build_hir

    hir = build_hir(graph, knowledge)
    console.print(
        f"[dim]  HIR: {len(hir.bus_contracts)} bus contracts, "
        f"{len(hir.init_contracts)} init contracts, "
        f"{len(hir.electrical_specs)} electrical specs[/]"
    )

    # 4. Run constraint solver on HIR
    from boardsmith_fw.analysis.constraint_solver import solve_constraints

    hir.constraints = solve_constraints(hir, graph)
    errors = hir.get_errors()
    warnings = [
        c for c in hir.constraints
        if c.status.value == "fail" and c.severity.value == "warning"
    ]
    passing = [c for c in hir.constraints if c.status.value == "pass"]
    unknown = [c for c in hir.constraints if c.status.value == "unknown"]

    if errors:
        for e in errors:
            console.print(f"[red]  CONSTRAINT FAIL: {e.description}[/]")
    if warnings:
        for w in warnings:
            console.print(f"[yellow]  CONSTRAINT WARN: {w.description}[/]")
    if unknown:
        console.print(f"[dim]  Constraints: {len(unknown)} unknown (missing data)[/]")
    console.print(
        f"[dim]  Constraints: {len(passing)} pass, "
        f"{len(errors)} errors, {len(warnings)} warnings[/]"
    )

    # 5. HIR-driven code generation (contract-driven drivers)
    from boardsmith_fw.codegen.hir_codegen import generate_from_hir

    hir_result = generate_from_hir(hir, target=target)
    hir_file_paths = {f.path for f in hir_result.files}
    if hir_result.files:
        console.print(
            f"[dim]  HIR codegen: {len(hir_result.files)} contract-driven "
            f"files generated[/]"
        )
    for w in hir_result.warnings:
        console.print(f"[yellow]  HIR: {w}[/]")

    # 6. Incremental regeneration check
    from boardsmith_fw.codegen.fingerprint import (
        compute_component_fingerprints,
        compute_graph_fingerprint,
        diff_fingerprints,
        load_state,
    )

    new_graph_fp = compute_graph_fingerprint(graph)
    new_comp_fps = compute_component_fingerprints(graph, knowledge)
    old_state = load_state(out)

    if old_state.get("graph_fingerprint") == new_graph_fp:
        console.print("[dim]  No schematic changes detected (same fingerprint)[/]")
    elif old_state.get("component_fingerprints"):
        added, changed, removed = diff_fingerprints(
            old_state["component_fingerprints"], new_comp_fps
        )
        if added:
            console.print(f"[dim]  New components: {', '.join(added)}[/]")
        if changed:
            console.print(f"[dim]  Changed components: {', '.join(changed)}[/]")
        if removed:
            console.print(f"[dim]  Removed components: {', '.join(removed)}[/]")

    # 7. LLM-assisted generation
    lang_norm = "cpp" if lang == "cpp" else "c"
    console.print("[dim]  Generating firmware (LLM)...[/]")

    req = GenerationRequest(
        graph=graph,
        knowledge=knowledge,
        description=description,
        lang=lang_norm,
        target=target,
        model=model,
        rtos=rtos,
    )
    result = asyncio.run(generate_firmware(req))

    # Merge: HIR-generated files take priority over LLM-generated
    # (contract-driven drivers are more reliable than LLM guesses)
    llm_only = [f for f in result.files if f.path not in hir_file_paths]
    from boardsmith_fw.codegen.llm_wrapper import GeneratedFile as LLMFile

    merged_files = [
        LLMFile(path=f.path, content=f.content) for f in hir_result.files
    ] + llm_only
    result.files = merged_files
    console.print(
        f"[dim]  Merged: {len(hir_result.files)} HIR + "
        f"{len(llm_only)} LLM files[/]"
    )

    # 8. PlatformIO integration
    if platformio:
        from boardsmith_fw.codegen.platformio import generate_platformio_ini

        pio = generate_platformio_ini(graph, target=target, lang=lang_norm)
        result.files.append(pio)

    # 9. CI/CD pipeline
    if ci:
        from boardsmith_fw.codegen.ci_templates import generate_github_actions

        ci_file = generate_github_actions(graph, target=target)
        result.files.append(ci_file)

    out.mkdir(parents=True, exist_ok=True)
    generated_files: dict[str, str] = {}
    for gf in result.files:
        fpath = out / gf.path
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(gf.content)
        console.print(f"  Written: {fpath}")
        generated_files[gf.path] = gf.path

    # Save state for incremental regen
    from boardsmith_fw.codegen.fingerprint import save_state

    save_state(out, new_graph_fp, new_comp_fps, generated_files)

    meta = {
        "description": description,
        "lang": lang_norm,
        "target": target,
        "model": model,
        "rtos": rtos,
        "platformio": platformio,
        "ci": ci,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "file_count": len(result.files),
        "explanation": result.explanation,
    }
    (out / "generation_meta.json").write_text(json.dumps(meta, indent=2))

    # Phase 24.4: Firmware syntax validation (no compiler required)
    from boardsmith_fw.codegen.firmware_validator import validate_codegen_result
    from boardsmith_fw.codegen.hir_codegen import HIRCodegenResult, GeneratedFile as HirFile

    # Build a lightweight result from all files for the validator
    _all_hir = HIRCodegenResult(
        files=[HirFile(path=gf.path, content=gf.content) for gf in result.files],
    )
    val_result = validate_codegen_result(_all_hir)
    if val_result.errors:
        console.print(
            f"[red]  Firmware validation: {len(val_result.errors)} error(s)[/]"
        )
        for issue in val_result.errors:
            console.print(f"[red]    {issue}[/]")
    if val_result.warnings:
        for issue in val_result.warnings:
            console.print(f"[yellow]  FW-WARN: {issue}[/]")
    if val_result.valid and not val_result.warnings:
        console.print(
            f"[green]  Firmware validation passed "
            f"({len(_all_hir.files)} files)[/]"
        )

    console.print("\n[green]Generation complete![/]")
    console.print(f"  Files: {len(result.files)}")
    console.print(f"  Output: {out}")
    if result.explanation:
        console.print(f"[dim]\n  {result.explanation}[/]")


def _run_timing_validation(
    graph: HardwareGraph, knowledge: list[ComponentKnowledge]
) -> None:
    """Run timing validation and print issues."""
    from boardsmith_fw.analysis.timing_engine import validate_timing

    issues = validate_timing(graph, knowledge)
    for issue in issues:
        if issue.severity == "error":
            console.print(f"[red]  TIMING: {issue.message}[/]")
        elif issue.severity == "warning":
            console.print(f"[yellow]  TIMING: {issue.message}[/]")


def _run_conflict_check(
    graph: HardwareGraph, knowledge: list[ComponentKnowledge]
) -> None:
    """Run conflict detection and print issues."""
    from boardsmith_fw.analysis.conflict_detector import detect_conflicts

    conflicts = detect_conflicts(graph, knowledge)
    for conflict in conflicts:
        if conflict.severity == "error":
            console.print(f"[red]  CONFLICT: {conflict.message}[/]")
        elif conflict.severity == "warning":
            console.print(f"[yellow]  CONFLICT: {conflict.message}[/]")
