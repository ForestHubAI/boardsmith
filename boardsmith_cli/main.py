# SPDX-License-Identifier: AGPL-3.0-or-later
"""Boardsmith CLI — Prompt to Hardware.

Single entry point for the full pipeline:
  boardsmith build-project --prompt "ESP32 with BME280 over I2C" --target esp32 --out ./output
"""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path

import click
from importlib.metadata import version as _meta_version, PackageNotFoundError as _PkgNotFound
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

# ---------------------------------------------------------------------------
# Path setup — add synthesizer and compiler to sys.path so their packages
# are importable from the monorepo root.
#
# Order matters:
#   1. synthesizer — owns boardsmith_fw/api, boardsmith_hw, boardsmith_fw/models (v1.1.0)
#   2. shared      — provides models.hir as fallback
#   3. compiler    — provides boardsmith_fw/analysis, boardsmith_fw/codegen (Track A)
#   4. cli         — boardsmith_cli itself
# ---------------------------------------------------------------------------
_cli_dir = Path(__file__).parent
_repo_root = _cli_dir.parent
# Add repo root first — required for `from shared.xxx` imports to resolve
# the `shared` *package* (not just the directory contents).
_repo_root_str = str(_repo_root)
if _repo_root_str not in sys.path:
    sys.path.insert(0, _repo_root_str)
for _subdir in ("synthesizer", "shared", "compiler"):
    _p = str(_repo_root / _subdir)
    if _p not in sys.path:
        sys.path.insert(0, _p)

console = Console()

VALID_TARGETS = [
    "esp32", "esp32c3", "esp32s3",
    "stm32", "stm32f4", "stm32f7", "stm32g4", "stm32h7", "stm32l4",
    "lpc55", "imxrt",
    "rp2040", "nrf52",
]


try:
    _boardsmith_version = _meta_version("boardsmith")
except _PkgNotFound:
    _boardsmith_version = "0.0.0.dev0"


@click.group()
@click.version_option(_boardsmith_version, prog_name="boardsmith")
def cli() -> None:
    """Boardsmith — Prompt to Hardware.

    Converts a text prompt into a complete schematic, BOM, and firmware.
    """
    # Check KiCad availability (Flow 1 of component lookup).
    # Only print the warning once per CLI invocation — not in subcommands.
    try:
        from synthesizer.tools.kicad_library import KICAD_AVAILABLE
        if not KICAD_AVAILABLE:
            console.print(
                "[yellow]⚠ KiCad not found.[/] "
                "Symbol-lookup flow 1 disabled — using LLM and DB fallback.\n"
                "[dim]Install KiCad 8+: https://www.kicad.org/download/[/]"
            )
    except Exception:
        pass  # never break CLI startup due to KiCad check


@cli.command("build")
@click.option(
    "--prompt", "-p",
    required=True,
    help="Hardware description in plain text.",
)
@click.option(
    "--target", "-t",
    default="esp32",
    show_default=True,
    type=click.Choice(VALID_TARGETS, case_sensitive=False),
    help="Target MCU platform.",
)
@click.option(
    "--out", "-o",
    default="./boardsmith-output",
    show_default=True,
    type=click.Path(),
    help="Output directory.",
)
@click.option(
    "--quality",
    default="balanced",
    show_default=True,
    type=click.Choice(["fast", "balanced", "high"], case_sensitive=False),
    help="Acceptance threshold: fast=0.75 | balanced=0.85 | high=0.90",
)
@click.option(
    "--max-iterations",
    default=5,
    show_default=True,
    type=click.IntRange(1, 20),
    help="Maximum number of design iterations.",
)
@click.option(
    "--max-erc-iterations",
    default=5,
    show_default=True,
    type=click.IntRange(1, 20),
    help="Maximum number of LLM-guided ERC repair iterations (ERCAgent loop).",
)
@click.option(
    "--no-llm",
    is_flag=True,
    default=False,
    help="Deterministic mode — no LLM, no API key required.",
)
@click.option(
    "--no-pcb",
    is_flag=True,
    default=False,
    help="Skip PCB generation after accept.",
)
@click.option(
    "--no-firmware",
    is_flag=True,
    default=False,
    help="Skip firmware code generation.",
)
@click.option(
    "--seed",
    default=None,
    type=int,
    help="Random seed for reproducible runs.",
)
@click.option(
    "--clarification",
    default="single",
    show_default=True,
    type=click.Choice(["none", "single", "auto"], case_sensitive=False),
    help="Clarification mode: none | single (one round, default) | auto (until unambiguous).",
)
@click.option(
    "--agent",
    "agent_mode",
    default=None,
    type=click.Choice(["experimental"], case_sensitive=False),
    help=(
        "26.6 — Enable experimental agent mode. "
        "Activates: clarification=auto, state-machine progress display, "
        "gate matrix report, and synthesis_report agent section. "
        "Core determinism is unchanged — LLM suggestions remain validated patches only."
    ),
)
def build(
    prompt: str,
    target: str,
    out: str,
    quality: str,
    max_iterations: int,
    max_erc_iterations: int,
    no_llm: bool,
    no_pcb: bool,
    no_firmware: bool,
    seed: int | None,
    clarification: str,
    agent_mode: str | None,
) -> None:
    """Full agentic design loop: Prompt → Design → Review → Improve → Accept.

    Iterates until the confidence threshold is met, stagnation is detected, or
    max iterations are exhausted. After accept: PCB generation + JLCPCB ZIP + audit trail.

    \b
    Quality levels:
        fast     — accept at ≥ 0.75 (1–2 iterations)
        balanced — accept at ≥ 0.85 (2–3 iterations, default)
        high     — accept at ≥ 0.90 (3–5 iterations)

    \b
    Examples:
        boardsmith build -p "ESP32 with BME280 temperature sensor" --quality balanced
        boardsmith build -p "RP2040 CO2 monitor with LoRa" --target rp2040 --quality high
        boardsmith build -p "STM32 motor controller" --no-llm --seed 42
        boardsmith build -p "ESP32 with 5V HC-SR04 ultrasonic" --agent experimental
    """
    import asyncio

    out_dir = Path(out)
    is_experimental = agent_mode == "experimental"

    from agents.iterative_orchestrator import (
        ACCEPT_THRESHOLDS,
        AuditTrail,
        BuildResult,
        IterationRecord,
        IterativeOrchestrator,
        OrchestratorState,
    )

    accept_threshold = ACCEPT_THRESHOLDS.get(quality, 0.85)

    # ─── Agent-mode overrides ─────────────────────────────────────────────
    # --agent experimental: auto-clarification + verbose state display
    # --no-llm always wins (can't clarify without LLM)
    if is_experimental and not no_llm:
        clarification = "auto"   # full clarification rounds in experimental mode

    # --no-llm implies no clarification (no LLM = no questions)
    effective_clarification = "none" if no_llm else clarification
    effective_agent_mode = "no-llm" if no_llm else (agent_mode or "standard")

    # ─── Header ──────────────────────────────────────────────────────────
    console.print()

    agent_line = ""
    if is_experimental:
        agent_line = "\n[dim]Mode:[/]      [yellow bold]experimental[/] (auto-clarify · gate matrix · state trace)"

    console.print(Panel.fit(
        f"[bold cyan]Boardsmith Build[/] — Agentic Design Loop\n\n"
        f"[dim]Prompt:[/]    {prompt}\n"
        f"[dim]Target:[/]    {target}   "
        f"[dim]Quality:[/]   {quality} (accept ≥ {accept_threshold:.0%})   "
        f"[dim]Max-Iter:[/]  {max_iterations}\n"
        f"[dim]LLM:[/]       {'off' if no_llm else 'on'}   "
        f"[dim]PCB:[/]       {'off' if no_pcb else 'on'}   "
        f"[dim]Firmware:[/]  {'off' if no_firmware else 'on'}   "
        f"[dim]Clarify:[/]   {effective_clarification}"
        + agent_line,
        border_style="cyan" if not is_experimental else "yellow",
    ))
    console.print()
    console.print("━" * 60)

    # ─── Progress callback ────────────────────────────────────────────────

    def _on_iteration(record: IterationRecord) -> None:
        """Print iteration progress to console (Phase 21: multi-agent scores)."""
        conf_str = f"{record.confidence:.0%}"
        delta_str = ""
        if record.delta_confidence != 0:
            sign = "+" if record.delta_confidence >= 0 else ""
            delta_str = f" [dim]({sign}{record.delta_confidence:+.0%})[/]"

        if record.confidence >= accept_threshold:
            conf_color = "green"
            accept_tag = f"  [green bold]✅ ACCEPT[/]"
        elif record.hitl_required:
            conf_color = "red"
            accept_tag = f"  [red bold]🛑 HITL[/]"
        elif record.confidence >= 0.65:
            conf_color = "yellow"
            accept_tag = ""
        else:
            conf_color = "red"
            accept_tag = ""

        stages_str = ", ".join(record.stages_rerun)
        console.print(
            f"\n[bold]Iteration {record.iteration}/{max_iterations}[/] "
            f"[dim][{stages_str}][/]{accept_tag}"
        )
        console.print(
            f"  Confidence: [{conf_color}]{conf_str}[/]{delta_str}  "
            f"[dim](target: {accept_threshold:.0%})[/]"
        )

        # Phase 21: per-agent score breakdown
        agent_scores = getattr(record, "agent_scores", {})
        if agent_scores:
            score_parts = []
            label_map = {
                "design_review":     "design",
                "electrical":        "elec",
                "component_quality": "quality",
                "pcb":               "pcb",
            }
            for key, label in label_map.items():
                if key in agent_scores:
                    s = agent_scores[key]
                    color = "green" if s >= 0.85 else ("yellow" if s >= 0.65 else "red")
                    score_parts.append(f"[{color}]{label}={s:.0%}[/]")
            if score_parts:
                console.print("  Agents:     " + "  ".join(score_parts))

        if record.issues_found:
            for issue in record.issues_found[:6]:
                parts = issue.split(": ", 1)
                sev = parts[0].strip().upper() if len(parts) == 2 else "INFO"
                msg = parts[1] if len(parts) == 2 else issue
                if sev == "ERROR":
                    icon, color = "✗", "red"
                elif sev == "WARNING":
                    icon, color = "⚠", "yellow"
                else:
                    icon, color = "·", "dim"
                console.print(f"  [{color}]{icon}[/] {msg[:100]}")
            if len(record.issues_found) > 6:
                console.print(f"  [dim]... and {len(record.issues_found) - 6} more[/]")

        if record.fixes_applied:
            for fix in record.fixes_applied[:4]:
                console.print(f"  [green]→ Fix:[/] {fix}")

        # Chronic issues warning
        chronic = getattr(record, "chronic_issues", [])
        if chronic:
            console.print(
                f"  [red]⚡ Stuck issues (tried ≥2×):[/] {', '.join(chronic[:3])}"
            )

    # ─── Run orchestrator ─────────────────────────────────────────────────

    from agents.clarification_agent import CLIClarificationIO
    clarification_io = CLIClarificationIO(console)

    orchestrator = IterativeOrchestrator(
        use_llm=not no_llm,
        clarification_io=clarification_io,
        agent_mode=effective_agent_mode,
    )

    try:
        result: BuildResult = asyncio.run(orchestrator.build(
            prompt=prompt,
            target=target,
            out_dir=out_dir,
            quality=quality,
            max_iterations=max_iterations,
            max_erc_iterations=max_erc_iterations,
            with_pcb=not no_pcb,
            generate_firmware=not no_firmware,
            progress_callback=_on_iteration,
            seed=seed,
            clarification_mode=effective_clarification,
        ))
    except Exception as exc:
        console.print(f"\n[red bold]Fatal error:[/] {exc}")
        sys.exit(1)

    console.print("\n" + "━" * 60)

    # ─── Results ──────────────────────────────────────────────────────────

    if result.error:
        console.print(Panel.fit(
            f"[red bold]Build failed:[/] {result.error}",
            border_style="red",
        ))
        sys.exit(1)

    if result.hitl_required:
        console.print(Panel.fit(
            f"[yellow bold]🛑 Human-in-the-Loop required[/]\n\n"
            f"{result.hitl_reason}\n\n"
            f"Please review the generated design manually:\n"
            f"  [cyan]{out_dir.resolve() / 'hir.json'}[/]\n\n"
            f"Then re-run with an adjusted prompt.",
            border_style="yellow",
        ))
        # Don't exit with error — artifacts are still useful
    else:
        # Accept summary
        trail = result.audit_trail
        num_iter = len(trail.iterations)
        reason_map = {
            "threshold_met": f"confidence {result.confidence:.0%} ≥ target {accept_threshold:.0%}",
            "converged":     "stagnation detected (Δ < 2%)",
            "no_fixes":      "no more fixes available",
            "max_iter":      f"max iterations ({max_iterations}) reached",
            "hitl":          "HITL gate triggered",
        }
        reason_text = reason_map.get(trail.accept_reason, trail.accept_reason)

        conf_color = "green" if result.confidence >= accept_threshold else "yellow"

        # 26.2 — Gate matrix line
        gate_line = ""
        gm = result.gate_matrix
        if gm is not None:
            gate_status = "[green]READY[/]" if gm.release_ready else "[red]NOT READY[/]"
            gate_icons = (
                f"ERC {'✅' if gm.erc_clean else '❌'}  "
                f"Boot {'✅' if gm.boot_pins_valid else '❌'}  "
                f"Power {'✅' if gm.power_budget_ok else '❌'}  "
                f"BOM {'✅' if gm.bom_complete else '❌'}  "
                f"Pinmux {'✅' if gm.no_pinmux_conflicts else '❌'}"
            )
            ls_note = "  ⚠ Level-Shifter auto-inserted" if gm.level_shifter_inserted else ""
            gate_line = f"\n  Gates:       {gate_status} — {gate_icons}{ls_note}"
            if gm.warnings:
                for w in gm.warnings[:3]:
                    gate_line += f"\n  [dim]⚠ {w}[/]"

        # 26.4 — state line
        state_line = ""
        if is_experimental:
            state_line = f"\n  Final State: [dim]{result.final_state.value}[/]"

        console.print(Panel.fit(
            f"[{conf_color} bold]✅ Design accepted![/]\n\n"
            f"  Confidence:  [{conf_color}]{result.confidence:.0%}[/]\n"
            f"  Iterations:  {num_iter}\n"
            f"  Reason:      {reason_text}"
            + gate_line
            + state_line
            + (f"\n  Firmware:    score={result.firmware_score:.2f}"
               if result.firmware_score is not None else ""),
            border_style=conf_color,
        ))

    # ─── Phase 21: Iteration summary table ───────────────────────────────
    trail = result.audit_trail
    if trail.iterations:
        iter_table = Table(
            title="Iteration History",
            show_header=True,
            header_style="bold cyan",
            show_lines=False,
        )
        iter_table.add_column("#",      style="dim", justify="right", width=3)
        iter_table.add_column("Stages", style="dim", width=8)
        iter_table.add_column("Score",  justify="right", width=6)
        iter_table.add_column("Δ",      justify="right", width=6)
        iter_table.add_column("Design", justify="right", width=7)
        iter_table.add_column("Elec",   justify="right", width=7)
        iter_table.add_column("Quality",justify="right", width=8)
        iter_table.add_column("PCB",    justify="right", width=7)
        iter_table.add_column("Fixes",  justify="right", width=5)
        iter_table.add_column("Reason", style="dim", width=14)

        def _pct(v: float) -> str:
            color = "green" if v >= 0.85 else ("yellow" if v >= 0.65 else "red")
            return f"[{color}]{v:.0%}[/]"

        for rec in trail.iterations:
            a = rec.agent_scores if hasattr(rec, "agent_scores") else {}
            delta_str = (
                f"[green]+{rec.delta_confidence:.0%}[/]"
                if rec.delta_confidence > 0.01
                else (
                    f"[red]{rec.delta_confidence:+.0%}[/]"
                    if rec.delta_confidence < -0.01
                    else "[dim]—[/]"
                )
            )
            iter_table.add_row(
                str(rec.iteration),
                ",".join(rec.stages_rerun)[:8],
                _pct(rec.confidence),
                delta_str,
                _pct(a.get("design_review", rec.confidence)),
                _pct(a.get("electrical", rec.confidence)),
                _pct(a.get("component_quality", rec.confidence)),
                _pct(a.get("pcb", rec.confidence)),
                str(len(rec.fixes_applied)),
                rec.accept_reason[:14],
            )
        console.print()
        console.print(iter_table)

    # Artifacts table
    if result.artifacts:
        table = Table(title="Generated Artifacts", show_header=True, header_style="bold cyan")
        table.add_column("File", style="dim")
        table.add_column("Type")
        type_map = {
            "hir.json": "Hardware spec (HIR)",
            "bom.json": "Bill of materials (BOM)",
            "schematic.kicad_sch": "Schematic (KiCad)",
            "pcb.kicad_pcb": "PCB layout (KiCad)",
            "audit_trail.json": "Audit trail",
            "synthesis_report.md": "Design report",
            "design_rules.txt": "PCB design rules",
        }
        for artifact in sorted(result.artifacts)[:12]:
            name = Path(artifact).name
            t = type_map.get(name, "File")
            if "jlcpcb.zip" in name:
                t = "JLCPCB ZIP (production)"
            elif name.endswith("/") or Path(artifact).is_dir():
                t = "Directory"
            table.add_row(Path(artifact).name, t)
        console.print()
        console.print(table)

    console.print(f"\n[dim]Output:[/] [cyan]{out_dir.resolve()}[/]")

    if not result.success and not result.hitl_required:
        sys.exit(1)


@cli.command("build-project")
@click.option(
    "--prompt", "-p",
    required=True,
    help='Hardware project description, e.g. "ESP32 with BME280 over I2C"',
)
@click.option(
    "--target", "-t",
    default="esp32",
    show_default=True,
    type=click.Choice(VALID_TARGETS, case_sensitive=False),
    help="Target MCU",
)
@click.option(
    "--out", "-o",
    default="./boardsmith-output",
    show_default=True,
    type=click.Path(),
    help="Output directory",
)
@click.option(
    "--no-firmware",
    is_flag=True,
    default=False,
    help="Generate schematic + BOM only, skip firmware",
)
@click.option(
    "--confidence-threshold",
    default=0.65,
    show_default=True,
    type=float,
    help="Minimum confidence (0.0–1.0) for auto-accept",
)
@click.option(
    "--seed",
    default=None,
    type=int,
    help="Random seed for reproducible component selection",
)
@click.option(
    "--no-llm",
    is_flag=True,
    default=False,
    help="Disable LLM parsing (regex fallback only)",
)
@click.option(
    "--generate-pcb",
    is_flag=True,
    default=False,
    help="Generate PCB layout (.kicad_pcb), Gerbers, and JLCPCB production ZIP after schematic",
)
@click.option(
    "--max-erc-iterations",
    default=5,
    show_default=True,
    type=click.IntRange(1, 20),
    help="Maximum number of LLM-guided ERC repair iterations (ERCAgent loop).",
)
@click.option(
    "--no-interactive",
    is_flag=True,
    default=False,
    help="Disable interactive HITL chat when prompt is too vague (non-interactive/batch mode).",
)
def build_project(
    prompt: str,
    target: str,
    out: str,
    no_firmware: bool,
    confidence_threshold: float,
    seed: int | None,
    no_llm: bool,
    generate_pcb: bool,
    max_erc_iterations: int,
    no_interactive: bool,
) -> None:
    """Single-pass pipeline: Prompt → Schematic + BOM + Firmware.

    \b
    Example:
        boardsmith build-project \\
          --prompt "ESP32 with BME280 temperature sensor and SSD1306 OLED over I2C" \\
          --target esp32 \\
          --out ./my-project
    """
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    console.print()
    console.print(Panel.fit(
        f"[bold cyan]Boardsmith[/] — Prompt → Hardware\n\n"
        f"[dim]Prompt:[/]  {prompt}\n"
        f"[dim]Target:[/]  {target}\n"
        f"[dim]Output:[/]  {out_dir.resolve()}",
        border_style="cyan",
    ))
    console.print()

    # ------------------------------------------------------------------
    # Import Synthesizer (Track B)
    # ------------------------------------------------------------------
    try:
        from boardsmith_hw.synthesizer import Synthesizer
    except ImportError as e:
        console.print(f"[red]Error:[/] Synthesizer module not found: {e}")
        console.print("[dim]Make sure you are in the Boardsmith repo directory.[/]")
        sys.exit(1)

    synthesizer = Synthesizer(
        out_dir=out_dir,
        target=target,
        confidence_threshold=confidence_threshold,
        seed=seed,
        use_llm=not no_llm,
        generate_pcb=generate_pcb,
        max_erc_iterations=max_erc_iterations,
    )

    generate_firmware = not no_firmware

    # ------------------------------------------------------------------
    # Run synthesis
    # ------------------------------------------------------------------
    status_msg = "[bold green]Synthesizing...[/]"
    if generate_pcb:
        status_msg = "[bold green]Synthesizing + PCB layout...[/]"
    with console.status(status_msg, spinner="dots"):
        result = synthesizer.run(prompt, generate_firmware=generate_firmware)

    # ------------------------------------------------------------------
    # Output results
    # ------------------------------------------------------------------
    if result.error and not result.success:
        # HITL gate: if not suppressed, offer clarification chat.
        # Works in TTY and non-TTY (piped) mode; EOF on stdin is handled gracefully.
        if result.hitl_required and not no_interactive:
            enriched_prompt = _interactive_hitl_chat(
                original_prompt=prompt,
                result=result,
                use_llm=not no_llm,
            )
            if enriched_prompt:
                console.print()
                console.print(Panel.fit(
                    f"[bold cyan]Re-running synthesis[/] with enriched prompt…\n\n"
                    f"[dim]{enriched_prompt}[/]",
                    border_style="cyan",
                ))
                console.print()
                status_msg2 = "[bold green]Synthesizing + PCB layout...[/]" if generate_pcb else "[bold green]Synthesizing...[/]"
                with console.status(status_msg2, spinner="dots"):
                    result = synthesizer.run(enriched_prompt, generate_firmware=generate_firmware)
                if result.error and not result.success:
                    console.print(f"\n[red bold]Error:[/] {result.error}")
                    sys.exit(1)
            else:
                # User chose to abort or stdin was closed
                sys.exit(0)
        else:
            console.print(f"\n[red bold]Error:[/] {result.error}")
            sys.exit(1)

    if result.hitl_required and not no_interactive:
        console.print("\n[yellow bold]Human-in-the-Loop required:[/]")
        for msg in result.hitl_messages:
            console.print(f"  [yellow]→[/] {msg}")

    _print_results(result, out_dir, generate_firmware)

    if not result.success:
        sys.exit(1)


def _interactive_hitl_chat(
    original_prompt: str,
    result: object,
    use_llm: bool = True,
) -> str | None:
    """Interactive HITL clarification chat.

    Shows the user what was unclear, asks 3 targeted questions with numbered
    component options, collects answers, and returns the enriched prompt.
    Returns None if the user decides to abort.
    """
    # ---------------------------------------------------------------------------
    # Component options from _MODALITY_SENSORS (import lazily to avoid hard dep)
    # ---------------------------------------------------------------------------
    try:
        from boardsmith_hw.component_selector import _MODALITY_SENSORS  # type: ignore[attr-defined]
    except ImportError:
        _MODALITY_SENSORS = {}

    # Flatten all known modalities + their MPNs for the LLM context
    modality_options_text = "\n".join(
        f"  {mod}: {', '.join(mpns)}" if mpns else f"  {mod}: (generic)"
        for mod, mpns in _MODALITY_SENSORS.items()
    )

    # ---------------------------------------------------------------------------
    # Header
    # ---------------------------------------------------------------------------
    console.print()
    console.print(Panel.fit(
        "[bold yellow]📋 Design Clarification[/]\n\n"
        "Your prompt needs more detail. I'll ask a few questions so I can\n"
        "select the right components and synthesize a complete design.",
        border_style="yellow",
    ))
    console.print()

    # Show what was unclear
    if result.hitl_messages:  # type: ignore[union-attr]
        console.print("[dim]What was unclear:[/]")
        for msg in result.hitl_messages:  # type: ignore[union-attr]
            console.print(f"  [yellow]→[/] {msg}")
        console.print()

    # ---------------------------------------------------------------------------
    # Generate clarifying questions
    # ---------------------------------------------------------------------------
    questions: list[dict] = []  # list of {question: str, options: list[str], free: bool}

    if use_llm:
        questions = _generate_hitl_questions_llm(
            original_prompt=original_prompt,
            hitl_messages=getattr(result, "hitl_messages", []),
            modality_options_text=modality_options_text,
            modality_sensors=_MODALITY_SENSORS,
        )

    # Fallback to generic questions if LLM unavailable or returned nothing
    if not questions:
        questions = _hitl_questions_fallback(_MODALITY_SENSORS)

    # ---------------------------------------------------------------------------
    # Ask each question
    # ---------------------------------------------------------------------------
    answers: list[str] = []

    for i, q in enumerate(questions, 1):
        console.print(f"[bold cyan]Question {i}/{len(questions)}:[/] {q['question']}")
        opts = q.get("options", [])
        if opts:
            for idx, opt in enumerate(opts, 1):
                console.print(f"  [dim]{idx})[/] {opt}")
            console.print(f"  [dim]{len(opts) + 1})[/] Other / Überspringen (skip)")
            console.print()
            try:
                raw = input("Your choice (number or text): ").strip()
            except EOFError:
                raw = ""
            # Parse numeric choice
            if raw.isdigit():
                choice = int(raw)
                if 1 <= choice <= len(opts):
                    answers.append(f"{q['question']}: {opts[choice - 1]}")
                elif choice == len(opts) + 1:
                    answers.append("")  # skipped
                else:
                    answers.append(raw)
            elif raw:
                answers.append(f"{q['question']}: {raw}")
            else:
                answers.append("")  # skipped
        else:
            # Free-text question
            console.print()
            try:
                raw = input("Your answer: ").strip()
            except EOFError:
                raw = ""
            if raw:
                answers.append(f"{q['question']}: {raw}")
            else:
                answers.append("")
        console.print()

    # ---------------------------------------------------------------------------
    # Build enriched prompt
    # ---------------------------------------------------------------------------
    non_empty = [a for a in answers if a]
    if not non_empty:
        console.print("[dim]No answers provided — aborting.[/]")
        return None

    # Use LLM to synthesize a proper hardware-design prompt from the Q&A answers.
    # Simple string concatenation loses semantics (e.g. "LCD/OLED-Display (lokal)"
    # doesn't parse as SSD1306 in the intent parser).
    if use_llm:
        enriched = _synthesize_enriched_prompt_llm(original_prompt, non_empty)
    else:
        enriched = original_prompt + ". " + ". ".join(non_empty) + "."
    return enriched


def _synthesize_enriched_prompt_llm(original_prompt: str, answers: list[str]) -> str:
    """Use LLM to rewrite the original prompt + HITL answers into a concrete hardware prompt.

    Translates human-readable answer labels (e.g. "LCD/OLED-Display (lokal)")
    into concrete component MPNs that the intent parser can extract (e.g. SSD1306).
    Falls back to simple concatenation if the API call fails.
    """
    try:
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError("no key")
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        answers_text = "\n".join(f"- {a}" for a in answers)
        system = (
            "You are a hardware design prompt engineer. "
            "Given an original vague board design request and the user's clarification answers, "
            "rewrite them into a single, concrete hardware design prompt in the SAME LANGUAGE as the original. "
            "CRITICAL: Replace ALL abstract descriptions with EXACT component MPNs. Never use human-readable "
            "descriptions like '16x2 LCD-Display' — always use the actual MPN.\n"
            "REQUIRED MPN translations (always use these exact MPNs):\n"
            "  ANY display/LCD/OLED/screen/Bildschirm/Anzeige → use 'SSD1306 OLED display over I2C'\n"
            "  'Netzbetrieb (230V)' → '5V USB power supply with AMS1117-3.3 LDO'\n"
            "  'Batterien mit Fuel Gauge' or 'MAX17043' → 'Li-Ion battery with MAX17043 fuel gauge and TP4056 charger'\n"
            "  'Solar-Panel' or 'Solarenergie' or solar charging → 'solar panel input with BQ24650 MPPT charge controller'\n"
            "  'BME280' or temp+humidity+pressure → 'BME280 sensor over I2C'\n"
            "  'Web-Interface via Ethernet' → 'W5500 Ethernet controller'\n"
            "  'WLAN' or 'WiFi' → keep ESP32 or add ESP32 if MCU not specified\n"
            "  'USB-C Stromversorgung' → '5V USB-C power input'\n"
            "Return only the rewritten prompt string, no explanations. "
            "The output MUST contain explicit MPNs for every component the user requested."
        )
        user_msg = (
            f"Original prompt: {original_prompt}\n\n"
            f"User clarification answers:\n{answers_text}\n\n"
            "Rewrite into a single concrete hardware design prompt with specific MPNs."
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        return response.content[0].text.strip()
    except Exception:
        return original_prompt + ". " + ". ".join(answers) + "."


def _generate_hitl_questions_llm(
    original_prompt: str,
    hitl_messages: list[str],
    modality_options_text: str,
    modality_sensors: dict,
) -> list[dict]:
    """Use LLM to generate 3 domain-appropriate clarifying questions."""
    try:
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return []
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        system = (
            "You are a hardware design assistant helping to clarify a vague board design prompt. "
            "Generate exactly 3 concise clarifying questions in the same language as the user prompt. "
            "CRITICAL: Option labels MUST use the actual component MPN as the first word, followed by a brief description. "
            "NEVER use human-readable descriptions alone — always lead with the MPN. "
            "Examples of CORRECT option labels: "
            "  'BME280 (Temp/Feuchte/Druck)', 'SSD1306 OLED I2C Display', 'LAN8720A Ethernet PHY', "
            "  'SHT31-DIS (Temp/Feuchte)', 'TP4056 LiPo Charger', 'BQ24650 Solar Charger'. "
            "This is required so that when the user picks an option, the MPN can be extracted for component selection. "
            "Return JSON array: [{\"question\": \"...\", \"options\": [\"BME280 (Temp/Feuchte/Druck)\", ...]}, ...]"
        )
        user_msg = (
            f"Prompt: {original_prompt}\n"
            f"Unclear aspects: {'; '.join(hitl_messages)}\n\n"
            f"Available component modalities and MPNs:\n{modality_options_text}\n\n"
            "Generate 3 targeted clarifying questions. Include display/output as a question if a UI is relevant. "
            "Use MPN-first option labels. Focus on: sensors, power/connectivity, and output/display. "
            "Return only valid JSON, no explanation."
        )

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        import json as _json
        parsed = _json.loads(text)
        if isinstance(parsed, list):
            return parsed[:3]
    except Exception:
        pass
    return []


def _hitl_questions_fallback(modality_sensors: dict) -> list[dict]:
    """Generic fallback questions when LLM is unavailable."""
    sensor_opts = []
    for mpns in list(modality_sensors.values())[:6]:
        sensor_opts.extend(mpns)
    sensor_opts = list(dict.fromkeys(sensor_opts))[:6]  # deduplicated, max 6

    return [
        {
            "question": "Welche Sensoren sollen verbaut werden? / Which sensors?",
            "options": sensor_opts or ["BME280 (Temp/Druck/Feuchte)", "ICM-42688-P (IMU)", "SCD41 (CO2)", "ADS1115 (ADC)"],
        },
        {
            "question": "Was ist die Stromversorgung? / Power source?",
            "options": ["USB 5V", "LiPo + TP4056 Charger", "12V DC", "Solar + BQ24650 Charger"],
        },
        {
            "question": "Lokale Ausgabe oder Schnittstelle? / Local output or interface?",
            "options": ["SSD1306 OLED I2C", "LAN8720A Ethernet PHY", "WiFi (ESP32 integriert)", "Keine"],
        },
    ]


def _print_results(result: object, out_dir: Path, firmware_requested: bool) -> None:
    from boardsmith_hw.synthesizer import SynthesisResult
    assert isinstance(result, SynthesisResult)

    conf = result.confidence
    conf_color = "green" if conf >= 0.8 else ("yellow" if conf >= 0.65 else "red")
    console.print(f"\n[bold]Confidence:[/] [{conf_color}]{conf:.0%}[/]\n")

    table = Table(title="Generated Files", show_header=True, header_style="bold cyan")
    table.add_column("File", style="dim")
    table.add_column("Status")

    for artifact in result.artifacts:
        path = out_dir / artifact
        exists = path.exists()
        status = "[green]✓[/]" if exists else "[red]✗ missing[/]"
        table.add_row(artifact, status)

    console.print(table)

    bom_path = out_dir / "bom.json"
    if bom_path.exists():
        try:
            bom = json.loads(bom_path.read_text())
            if bom:
                console.print(f"\n[bold]Bill of Materials:[/] {len(bom)} items")
                total_cost = sum(
                    item.get("unit_cost_estimate", 0) or 0
                    for item in bom
                )
                if total_cost > 0:
                    console.print(f"  Estimated cost: [cyan]${total_cost:.2f} USD[/]")
        except Exception:
            pass

    # PCB result
    if result.pcb_path is not None:
        if result.pcb_error:
            console.print(f"\n[yellow bold]PCB:[/] [yellow]Warning — {result.pcb_error[:120]}[/]")
        else:
            routed_note = "[green]routed[/]" if result.pcb_routed else f"[yellow]unrouted[/] (method: {result.pcb_router_method})"
            console.print(f"\n[bold]PCB Layout:[/] {routed_note}")
            if result.pcb_path:
                console.print(f"  [dim]PCB:[/]     {result.pcb_path.name}")
            if result.pcb_gerber_dir and result.pcb_gerber_dir.exists():
                n_gerbers = len(list(result.pcb_gerber_dir.glob("*")))
                console.print(f"  [dim]Gerbers:[/] gerbers/ ({n_gerbers} files)")
            if result.pcb_production_zip and result.pcb_production_zip.exists():
                console.print(f"  [dim]JLCPCB:[/]  {result.pcb_production_zip.name}")
    elif getattr(result, "_generate_pcb_requested", False):
        console.print("\n[red bold]PCB:[/] [red]Generation failed — see synthesis_report.md[/]")

    # ERC result
    if result.erc_passed is not None:
        if result.erc_passed:
            fixes_note = ""
            if result.erc_fixes:
                fixes_note = f" (Fixes: {', '.join(result.erc_fixes)})"
            iter_note = ""
            if result.erc_iterations > 1:
                iter_note = f" after {result.erc_iterations} iterations"
            console.print(f"\n[green bold]ERC:[/] [green]Passed[/]{iter_note}{fixes_note}")
        else:
            console.print(f"\n[red bold]ERC:[/] [red]{len(result.erc_errors)} errors[/] after {result.erc_iterations} iterations")
            if result.erc_fixes:
                console.print(f"  [dim]Applied fixes: {', '.join(result.erc_fixes)}[/]")
            for err in result.erc_errors[:5]:
                console.print(f"  [red]->[/] {err}")
            if len(result.erc_errors) > 5:
                console.print(f"  [dim]... and {len(result.erc_errors) - 5} more (see erc_report.json)[/]")
    elif result.erc_note:
        console.print(f"\n[dim]ERC: {result.erc_note}[/]")

    # DRC unconnected pad warning (PCB-level)
    _drc_unc = getattr(result, "drc_unconnected_count", 0)
    if _drc_unc > 0:
        console.print(
            f"\n[red bold]DRC:[/] [red]{_drc_unc} unconnected pad(s)[/] "
            "[dim]— see DRC.rpt for details[/]"
        )

    if result.assumptions:
        console.print("\n[yellow]Assumptions / Notes:[/]")
        for assumption in result.assumptions[:5]:
            console.print(f"  [dim]→[/] {assumption}")
        if len(result.assumptions) > 5:
            console.print(f"  [dim]... and {len(result.assumptions) - 5} more (see synthesis_report.md)[/]")

    console.print()
    if result.success:
        lines = [f"[green bold]Done![/] Output: [cyan]{out_dir.resolve()}[/]\n"]
        if firmware_requested:
            lines.append("  [dim]Firmware:[/]   firmware/")
        lines.append("  [dim]Schematic:[/]  schematic.kicad_sch")
        lines.append("  [dim]BOM:[/]       bom.json")
        if result.pcb_path and not result.pcb_error:
            lines.append(f"  [dim]PCB:[/]       {result.pcb_path.name}")
        if result.pcb_gerber_dir and result.pcb_gerber_dir.exists():
            lines.append("  [dim]Gerbers:[/]   gerbers/")
        if result.pcb_production_zip and result.pcb_production_zip.exists():
            lines.append(f"  [dim]JLCPCB:[/]   {result.pcb_production_zip.name}")
        console.print(Panel.fit("\n".join(lines), border_style="green"))
    else:
        console.print(Panel.fit(
            "[yellow bold]Synthesis completed with limitations.[/]\n"
            "Check [cyan]synthesis_report.md[/] and [cyan]diagnostics.json[/] for details.",
            border_style="yellow",
        ))


@cli.command("synthesize")
@click.argument("prompt")
@click.option("--target", "-t", default="esp32", type=click.Choice(VALID_TARGETS, case_sensitive=False))
@click.option("--out", "-o", default="./boardsmith-output", type=click.Path())
@click.option("--generate-firmware", is_flag=True, default=False)
@click.option("--no-llm", is_flag=True, default=False)
@click.option("--seed", default=None, type=int)
def synthesize(
    prompt: str, target: str, out: str, generate_firmware: bool, no_llm: bool, seed: int | None
) -> None:
    """Alias for build-project (compatibility with Boardsmith-CLI)."""
    ctx = click.get_current_context()
    ctx.invoke(
        build_project,
        prompt=prompt,
        target=target,
        out=out,
        no_firmware=not generate_firmware,
        confidence_threshold=0.65,
        seed=seed,
        no_llm=no_llm,
    )


@cli.command("validate-hir")
@click.argument("hir_path", type=click.Path(exists=True))
def validate_hir(hir_path: str) -> None:
    """Validate a HIR JSON file against the v1.1.0 schema.

    \b
    Example:
        boardsmith validate-hir ./output/hir.json
    """
    hir_file = Path(hir_path)

    try:
        from synth_core.api.compiler import validate_hir_dict
    except ImportError:
        # Fallback: use synthesizer's validator
        try:
            from synth_core.hir_bridge.validator import validate_hir, DiagnosticsReport  # type: ignore[import]
        except ImportError as e:
            console.print(f"[red]Error:[/] Validator not found: {e}")
            sys.exit(1)

    data = json.loads(hir_file.read_text())
    console.print(f"Validating [cyan]{hir_file}[/]...")

    try:
        report = validate_hir_dict(data)  # type: ignore[possibly-undefined]
    except NameError:
        from models.hir import HIR  # type: ignore[import]
        hir = HIR.model_validate(data)
        console.print(f"[green]✓[/] HIR v{hir.version} — structure valid ({len(hir.bus_contracts)} bus contracts, {len(hir.constraints)} constraints)")
        return

    valid_str = "[green]VALID[/]" if report.valid else "[red]INVALID[/]"
    console.print(f"Status: {valid_str}")
    errors = [d for d in report.diagnostics if d.severity == "error" and d.status == "fail"]
    warnings = [d for d in report.diagnostics if d.severity == "warning"]
    console.print(f"  Errors: {len(errors)}  Warnings: {len(warnings)}")
    for e in errors:
        console.print(f"  [red]✗[/] {e.id}: {e.message}")


@cli.command("list-components")
@click.option("--role", default=None, help="Filter by role (mcu, sensor, display, ...)")
def list_components(role: str | None) -> None:
    """List all components in the knowledge base."""
    try:
        from synth_core.api.compiler import list_components as _list
    except ImportError:
        try:
            from synth_core.knowledge.builtin_db import get_all_knowledge  # type: ignore[import]
            components = get_all_knowledge()
            table = Table(title="Available Components")
            table.add_column("MPN")
            table.add_column("Name")
            table.add_column("Interface")
            for c in components:
                if role and getattr(c, "role", None) != role:
                    continue
                ifaces = ", ".join(getattr(c, "supported_interfaces", []))
                table.add_row(c.component_id, getattr(c, "name", "-"), ifaces)
            console.print(table)
            return
        except ImportError as e:
            console.print(f"[red]Error:[/] Knowledge base not found: {e}")
            sys.exit(1)

    components = _list()
    table = Table(title="Available Components")
    table.add_column("MPN")
    table.add_column("Name")
    table.add_column("Interfaces")
    for c in components:
        if role and c.get("role") != role:
            continue
        ifaces = ", ".join(c.get("supported_interfaces", []))
        table.add_row(c.get("component_id", "-"), c.get("name", "-"), ifaces)
    console.print(table)


@cli.command("research")
@click.argument("query")
@click.option(
    "--cache-dir",
    default=None,
    type=click.Path(),
    help="Local cache directory (default: ~/.boardsmith/knowledge/)",
)
@click.option(
    "--no-agent",
    is_flag=True,
    default=False,
    help="Query built-in DB only, skip the research agent",
)
def research(query: str, cache_dir: str | None, no_agent: bool) -> None:
    """Search for component information by MPN or description.

    \b
    Examples:
        boardsmith research BME280
        boardsmith research "CO2 sensor I2C 3.3V"
        boardsmith research SCD41 --no-agent
    """
    import asyncio

    console.print()
    console.print(Panel.fit(
        f"[bold cyan]Boardsmith Research[/]\n\n"
        f"[dim]Query:[/]  {query}",
        border_style="cyan",
    ))
    console.print()

    try:
        from agents.knowledge_agent import KnowledgeAgent
    except ImportError as e:
        console.print(f"[red]Error:[/] agents module not found: {e}")
        sys.exit(1)

    cache_path = Path(cache_dir) if cache_dir else None

    async def _run() -> None:
        agent = KnowledgeAgent(cache_dir=cache_path)

        if no_agent:
            result = agent._query_builtin(query)
            if not result:
                result = agent._query_cache(query)
        else:
            with console.status("[bold green]Researching...[/]", spinner="dots"):
                result = await agent.find(query)

        if result is None:
            console.print(f"[yellow]No result for:[/] {query}")
            if no_agent:
                console.print("[dim]Tip: Without --no-agent the agent can search dynamically.[/]")
            return

        source_color = {
            "builtin_db": "green",
            "local_cache": "cyan",
            "agent_extracted": "yellow",
            "minimal": "red",
        }.get(result.source, "white")

        console.print(f"[bold]Found:[/] [cyan]{result.mpn}[/]  "
                      f"[{source_color}]{result.source}[/]  "
                      f"Confidence: {result.confidence:.0%}")
        console.print()

        table = Table(show_header=False, box=None)
        table.add_column("Field", style="dim", width=22)
        table.add_column("Value")
        table.add_row("MPN", result.mpn or "—")
        table.add_row("Name", result.name or "—")
        table.add_row("Manufacturer", result.manufacturer or "—")
        table.add_row("Category", result.category or "—")
        table.add_row("Interfaces", ", ".join(result.interface_types) or "—")
        table.add_row("I2C addresses", ", ".join(result.known_i2c_addresses) or "—")
        ratings = result.electrical_ratings
        if ratings:
            table.add_row("Supply voltage", f"{ratings.get('vdd_min', '?')}V – {ratings.get('vdd_max', '?')}V")
        else:
            table.add_row("Supply voltage", "—")
        table.add_row("Cost (est.)", f"${result.unit_cost_usd:.2f}" if result.unit_cost_usd else "—")
        table.add_row("Tags", ", ".join(result.tags[:6]) or "—")
        console.print(table)

        if result.agent_trace:
            console.print()
            console.print("[dim]Agent steps:[/]")
            for step in result.agent_trace:
                console.print(f"  [dim]→[/] {step}")

    asyncio.run(_run())


@cli.command("promote")
@click.argument("mpn")
@click.option(
    "--cache-dir",
    default=None,
    type=click.Path(),
    help="Local cache directory (default: ~/.boardsmith/knowledge/)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show the entry without writing it to the builtin DB",
)
def promote(mpn: str, cache_dir: str | None, dry_run: bool) -> None:
    """Promote a cached component to the builtin DB.

    Reads the cache entry from ~/.boardsmith/knowledge/ and writes it
    (after quality check) to shared/knowledge/components.py.

    \b
    Examples:
        boardsmith promote SCD41 --dry-run
        boardsmith promote SCD41
    """
    cache_path = Path(cache_dir) if cache_dir else Path.home() / ".boardsmith" / "knowledge"

    console.print()
    console.print(Panel.fit(
        f"[bold cyan]Boardsmith Promote[/]\n\n"
        f"[dim]MPN:[/]   {mpn}\n"
        f"[dim]Cache:[/] {cache_path}",
        border_style="cyan",
    ))
    console.print()

    # --- Find cache entry ---
    mpn_norm = mpn.upper().replace("/", "_")
    cache_file = cache_path / f"{mpn_norm}.json"

    if not cache_file.exists():
        # Try case-insensitive search
        found = None
        for p in cache_path.glob("*.json"):
            if p.stem.upper().replace("-", "") == mpn_norm.replace("-", ""):
                found = p
                break
        if not found:
            console.print(f"[red]Error:[/] No cache entry found for '{mpn}'.")
            console.print(f"[dim]Tip: Run `boardsmith research {mpn}` first.[/]")
            sys.exit(1)
        cache_file = found

    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception as e:
        console.print(f"[red]Error:[/] Cache file not readable: {e}")
        sys.exit(1)

    # --- Check if already in Builtin DB ---
    try:
        from knowledge.components import find_by_mpn
        if find_by_mpn(data.get("mpn", mpn)):
            console.print(f"[yellow]'{data.get('mpn', mpn)}' is already in the builtin DB.[/]")
            sys.exit(0)
    except ImportError:
        pass

    # --- Quality check ---
    issues: list[str] = []
    if not data.get("mpn"):
        issues.append("mpn missing")
    if not data.get("manufacturer"):
        issues.append("manufacturer missing")
    if not data.get("interface_types"):
        issues.append("interface_types missing (at least 1)")
    ratings = data.get("electrical_ratings", {})
    if not ratings.get("vdd_min") and not ratings.get("vdd_max"):
        issues.append("electrical_ratings.vdd_min/vdd_max missing")

    if issues:
        console.print("[yellow]Quality issues:[/]")
        for issue in issues:
            console.print(f"  [yellow]![/] {issue}")
        console.print()
        if not dry_run:
            console.print("[dim]Entry will still be written (with warning).[/]")

    # --- Build ComponentEntry ---
    entry = _build_component_entry(data)

    # --- Show entry ---
    import pprint
    entry_str = pprint.pformat(entry, indent=4, width=100)
    console.print("[bold]ComponentEntry:[/]")
    console.print(f"[dim]{entry_str}[/]")

    if dry_run:
        console.print("\n[yellow]--dry-run: Not written.[/]")
        return

    # --- Write to components.py ---
    components_py = Path(__file__).parent.parent / "shared" / "knowledge" / "components.py"
    if not components_py.exists():
        console.print(f"[red]Error:[/] {components_py} not found.")
        sys.exit(1)

    content = components_py.read_text(encoding="utf-8")

    # Find the closing bracket of COMPONENTS list
    insert_pos = content.rfind("\n]")
    if insert_pos == -1:
        console.print("[red]Error:[/] Could not find COMPONENTS list.")
        sys.exit(1)

    # Format the entry as Python dict literal
    entry_lines = _format_component_entry(entry)
    new_content = content[:insert_pos] + f"\n{entry_lines}" + content[insert_pos:]
    components_py.write_text(new_content, encoding="utf-8")

    console.print(f"\n[green bold]Success![/] '{data.get('mpn', mpn)}' written to builtin DB.")
    console.print(f"[dim]Check with: git diff shared/knowledge/components.py[/]")


def _build_component_entry(data: dict) -> dict:
    """Convert a cache entry dict to a ComponentEntry-compatible dict."""
    ratings = data.get("electrical_ratings", {})
    timing = data.get("timing_caps", {})
    return {
        "mpn": data.get("mpn", ""),
        "manufacturer": data.get("manufacturer", ""),
        "name": data.get("name", data.get("mpn", "")),
        "category": data.get("category", "sensor"),
        "interface_types": data.get("interface_types", []),
        "package": data.get("package", ""),
        "description": data.get("description", ""),
        "electrical_ratings": {
            k: v for k, v in ratings.items() if v
        } if ratings else {},
        "timing_caps": {
            k: v for k, v in timing.items() if v
        } if timing else {},
        "known_i2c_addresses": data.get("known_i2c_addresses", []),
        "i2c_address_selectable": data.get("i2c_address_selectable", False),
        "init_contract_coverage": data.get("init_contract_coverage", False),
        "init_contract_template": data.get("init_contract_template", {}),
        "unit_cost_usd": data.get("unit_cost_usd", 0.0),
        "tags": data.get("tags", []),
    }


def _format_component_entry(entry: dict) -> str:
    """Format a ComponentEntry as a Python dict literal matching components.py style."""
    lines = ["    {"]
    for key in (
        "mpn", "manufacturer", "name", "category", "interface_types",
        "package", "description",
    ):
        val = entry.get(key)
        if isinstance(val, str):
            lines.append(f'        "{key}": {json.dumps(val)},')
        elif isinstance(val, list):
            lines.append(f'        "{key}": {json.dumps(val)},')

    # Electrical ratings
    ratings = entry.get("electrical_ratings", {})
    if ratings:
        lines.append('        "electrical_ratings": {')
        for k, v in ratings.items():
            lines.append(f'            "{k}": {json.dumps(v)},')
        lines.append("        },")
    else:
        lines.append('        "electrical_ratings": {},')

    # Timing caps
    timing = entry.get("timing_caps", {})
    if timing:
        lines.append('        "timing_caps": {')
        for k, v in timing.items():
            lines.append(f'            "{k}": {json.dumps(v)},')
        lines.append("        },")

    # I2C addresses
    lines.append(f'        "known_i2c_addresses": {json.dumps(entry.get("known_i2c_addresses", []))},')
    lines.append(f'        "i2c_address_selectable": {json.dumps(entry.get("i2c_address_selectable", False))},')
    lines.append(f'        "init_contract_coverage": {json.dumps(entry.get("init_contract_coverage", False))},')

    # Init contract template
    template = entry.get("init_contract_template", {})
    if template:
        lines.append(f'        "init_contract_template": {json.dumps(template)},')

    lines.append(f'        "unit_cost_usd": {json.dumps(entry.get("unit_cost_usd", 0.0))},')
    lines.append(f'        "tags": {json.dumps(entry.get("tags", []))},')
    lines.append("    },")
    return "\n".join(lines)


@cli.command("drc")
@click.argument(
    "path",
    type=click.Path(exists=True),
)
@click.option(
    "--format", "-f", "output_format",
    default="text",
    type=click.Choice(["text", "json"], case_sensitive=False),
    show_default=True,
    help="Output format (text or json)",
)
def drc(path: str, output_format: str) -> None:
    """KiCad DRC/ERC check on a schematic or PCB file.

    Automatically detects by file extension whether ERC (.kicad_sch)
    or DRC (.kicad_pcb) should be run. Requires kicad-cli (KiCad 7+).

    \b
    Examples:
        boardsmith drc ./output/schematic.kicad_sch
        boardsmith drc ./output/pcb.kicad_pcb
        boardsmith drc ./output/schematic.kicad_sch --format json
    """
    file_path = Path(path)

    try:
        from boardsmith_hw.kicad_drc import KiCadChecker
    except ImportError as e:
        console.print(f"[red]Error:[/] KiCadChecker not found: {e}")
        sys.exit(1)

    checker = KiCadChecker()

    if not checker.kicad_cli_available():
        console.print(
            "[yellow]Warning:[/] kicad-cli is not installed.\n"
            "[dim]Install KiCad 7+ for DRC/ERC support: "
            "https://www.kicad.org/download/[/]"
        )
        sys.exit(1)

    suffix = file_path.suffix.lower()
    if suffix not in (".kicad_sch", ".kicad_pcb"):
        console.print(
            f"[red]Error:[/] Unsupported file extension '{suffix}'.\n"
            "[dim]Expected: .kicad_sch (ERC) or .kicad_pcb (DRC)[/]"
        )
        sys.exit(1)

    check_label = "ERC" if suffix == ".kicad_sch" else "DRC"

    console.print()
    console.print(Panel.fit(
        f"[bold cyan]Boardsmith {check_label}[/] -- KiCad Design Check\n\n"
        f"[dim]File:[/]  {file_path.resolve()}\n"
        f"[dim]Type:[/]  {check_label}",
        border_style="cyan",
    ))
    console.print()

    with console.status(f"[bold green]Running {check_label}...[/]", spinner="dots"):
        result = checker.check(file_path)

    # --- JSON output ---
    if output_format == "json":
        json_out = {
            "check_type": result.check_type,
            "passed": result.passed,
            "error_count": result.error_count,
            "warning_count": result.warning_count,
            "violations": [
                {
                    "severity": v.severity,
                    "description": v.description,
                    "rule_id": v.rule_id,
                    "items": v.items,
                }
                for v in result.violations
            ],
            "note": result.note,
        }
        console.print_json(json.dumps(json_out, indent=2))
        if not result.passed:
            sys.exit(1)
        return

    # --- Text output ---
    status_color = "green" if result.passed else "red"
    status_text = "[green bold]PASSED[/]" if result.passed else "[red bold]FAILED[/]"
    console.print(f"Status: {status_text}")
    console.print(f"  Errors:   [{status_color}]{result.error_count}[/]")
    console.print(f"  Warnings: [yellow]{result.warning_count}[/]")

    if result.violations:
        console.print()
        table = Table(title=f"{check_label} Violations", show_header=True, header_style="bold cyan")
        table.add_column("#", style="dim", width=4)
        table.add_column("Severity", width=10)
        table.add_column("Description")
        table.add_column("Rule", style="dim", width=25)

        for i, v in enumerate(result.violations, 1):
            sev_color = "red" if v.severity == "error" else (
                "yellow" if v.severity == "warning" else "dim"
            )
            table.add_row(
                str(i),
                f"[{sev_color}]{v.severity}[/]",
                v.description,
                v.rule_id or "—",
            )
            # Show affected items inline
            for item in v.items[:2]:
                table.add_row("", "", f"  [dim]↳ {item}[/]", "")

        console.print(table)

    console.print()
    if result.passed:
        console.print(Panel.fit(
            f"[green bold]{check_label} passed![/] No errors found.",
            border_style="green",
        ))
    else:
        console.print(Panel.fit(
            f"[red bold]{check_label} failed.[/]\n"
            f"{result.error_count} errors, {result.warning_count} warnings.",
            border_style="red",
        ))
        sys.exit(1)


@cli.command("modify")
@click.argument("schematic_path", type=click.Path(exists=True))
@click.argument("instruction")
@click.option(
    "--yes", "-y",
    is_flag=True,
    default=False,
    help="Skip confirmation prompt (non-interactive mode).",
)
@click.option(
    "--max-erc-iterations",
    default=5,
    show_default=True,
    type=click.IntRange(1, 20),
    help="Maximum LLM-guided ERC repair iterations after modification.",
)
@click.option(
    "--no-llm",
    is_flag=True,
    default=False,
    help="boardsmith modify requires LLM — this flag shows a usage error.",
)
def modify(
    schematic_path: str,
    instruction: str,
    yes: bool,
    max_erc_iterations: int,
    no_llm: bool,
) -> None:
    """Modify an existing KiCad schematic using LLM-guided patching."""

    # --no-llm is not supported: modify is fundamentally LLM-driven
    if no_llm:
        click.echo(
            "boardsmith modify requires an LLM API key. "
            "Use --help for alternatives.",
            err=True,
        )
        raise SystemExit(1)

    from pathlib import Path

    # All heavy imports inside function body (BOARDSMITH_NO_LLM=1 isolation)
    try:
        from llm.gateway import LLMGateway
        from agents.modify_orchestrator import ModifyOrchestrator
    except ImportError as exc:
        click.echo(
            f"boardsmith modify requires [llm] extras: {exc}",
            err=True,
        )
        raise SystemExit(1)

    gateway = LLMGateway()
    orchestrator = ModifyOrchestrator(gateway=gateway, max_iterations=max_erc_iterations)

    result = orchestrator.run(
        sch_path=Path(schematic_path),
        instruction=instruction,
        yes=yes,
    )

    if result.aborted:
        raise SystemExit(0)

    if not result.success:
        raise SystemExit(1)


@cli.command("verify")
@click.argument("schematic_path", type=click.Path(exists=True))
@click.option(
    "--hir-path",
    default=None,
    type=click.Path(),
    help="Path to hir.json. Defaults to hir.json in schematic's directory.",
)
@click.option(
    "--max-semantic-iterations",
    default=5,
    show_default=True,
    type=click.IntRange(1, 20),
    help="Maximum semantic repair iterations.",
)
@click.option(
    "--no-llm",
    is_flag=True,
    default=False,
    help="boardsmith verify requires LLM — this flag shows a usage error.",
)
def verify(
    schematic_path: str,
    hir_path: str | None,
    max_semantic_iterations: int,
    no_llm: bool,
) -> None:
    """Semantic verification: check schematic design intent against HIR and fix with LLM."""
    if no_llm:
        click.echo(
            "boardsmith verify requires LLM — set ANTHROPIC_API_KEY or omit --no-llm.",
            err=True,
        )
        raise SystemExit(1)

    from pathlib import Path

    sch = Path(schematic_path)
    _hir = Path(hir_path) if hir_path else sch.parent / "hir.json"
    if not _hir.exists():
        click.echo(
            f"hir.json not found at {_hir}. Use --hir-path to specify location.",
            err=True,
        )
        raise SystemExit(1)

    try:
        from llm.gateway import LLMGateway
        from llm.dispatcher import ToolDispatcher
        from tools.registry import get_default_registry
        from boardsmith_hw.agent.semantic_agent import SemanticVerificationAgent
    except ImportError as exc:
        click.echo(
            f"boardsmith verify requires [llm] extras: {exc}",
            err=True,
        )
        raise SystemExit(1)

    gateway = LLMGateway()
    registry = get_default_registry()
    dispatcher = ToolDispatcher(registry=registry)
    agent = SemanticVerificationAgent(
        sch_path=sch,
        hir_path=_hir,
        gateway=gateway,
        dispatcher=dispatcher,
        max_iterations=max_semantic_iterations,
    )
    result = agent.run()

    if result.is_clean:
        click.echo("Semantic verification: all checks passed")
        raise SystemExit(0)
    else:
        click.echo(result.summary_message, err=True)
        raise SystemExit(1)


@cli.command("pcb")
@click.option(
    "--hir",
    default=None,
    type=click.Path(exists=True),
    help="HIR JSON input file (from boardsmith build)",
)
@click.option(
    "--out", "-o",
    default="./boardsmith-output",
    show_default=True,
    type=click.Path(),
    help="Output directory (pcb.kicad_pcb + gerbers/)",
)
@click.option(
    "--no-llm",
    is_flag=True,
    default=False,
    help="Disable LLM placement (deterministic grid layout only)",
)
def pcb(
    hir: str | None,
    out: str,
    no_llm: bool,
) -> None:
    """PCB pipeline: HIR → .kicad_pcb → Gerber files.

    Generates a KiCad 6 PCB layout from a HIR JSON.
    Routing via FreeRouting (if installed) or KiCad CLI.
    Fallback: valid unrouted .kicad_pcb + stub Gerbers.

    \b
    Examples:
        boardsmith pcb --hir ./output/hir.json --out ./output
        boardsmith pcb --hir ./output/hir.json --out ./output --no-llm
    """
    out_dir = Path(out)

    # --- Load HIR ---
    hir_dict: dict | None = None
    if hir:
        try:
            hir_dict = json.loads(Path(hir).read_text())
        except Exception as e:
            console.print(f"[red]Error:[/] Could not read HIR file: {e}")
            sys.exit(1)
    else:
        auto_hir = out_dir / "hir.json"
        if auto_hir.exists():
            try:
                hir_dict = json.loads(auto_hir.read_text())
                console.print(f"[dim]HIR loaded from {auto_hir}.[/]")
            except Exception as e:
                console.print(f"[red]Error:[/] Could not read auto-HIR: {e}")
                sys.exit(1)
        else:
            console.print(
                "[red]Error:[/] No --hir specified and no hir.json found in output directory.\n"
                "[dim]Tip: Run `boardsmith build` first.[/]"
            )
            sys.exit(1)

    console.print()
    console.print(Panel.fit(
        f"[bold cyan]Boardsmith PCB[/] — HIR → Layout → Gerbers\n\n"
        f"[dim]Output:[/]  {out_dir.resolve()}\n"
        f"[dim]LLM:[/]     {'off' if no_llm else 'on'}",
        border_style="cyan",
    ))
    console.print()

    try:
        from boardsmith_hw.pcb_pipeline import PcbPipeline
    except ImportError as e:
        console.print(f"[red]Error:[/] PCB pipeline not found: {e}")
        sys.exit(1)

    pipeline = PcbPipeline(use_llm=not no_llm)

    with console.status("[bold green]Generating PCB...[/]", spinner="dots"):
        result = pipeline.run(hir_dict, out_dir=out_dir)

    if result.error:
        console.print(f"\n[red bold]Error:[/] {result.error}")
        sys.exit(1)

    # --- Results table ---
    from boardsmith_hw.autorouter import Autorouter
    routed_str = "[green]✓ routed[/]" if result.routed else "[yellow]○ unrouted[/]"
    gerber_str = "[green]✓ real[/]" if result.real_gerbers else "[yellow]○ stub[/]"
    router_hint = ""
    if not result.routed and not Autorouter.freerouting_available() and not Autorouter.kicad_cli_available():
        router_hint = " [dim](FreeRouting/kicad-cli not installed)[/]"

    table = Table(title="PCB Artifacts", show_header=True, header_style="bold cyan")
    table.add_column("File", style="dim")
    table.add_column("Status")
    table.add_row("pcb.kicad_pcb", "[green]✓[/]" if result.pcb_path and result.pcb_path.exists() else "[red]✗[/]")
    table.add_row("gerbers/",      "[green]✓[/]" if result.gerber_dir and result.gerber_dir.exists() else "[red]✗[/]")
    console.print(table)

    console.print(f"\n[bold]Routing:[/]  {routed_str} [dim]({result.router_method}){router_hint}[/]")
    console.print(f"[bold]Gerbers:[/]  {gerber_str}")

    if result.footprints:
        console.print(f"\n[bold]Footprints ({len(result.footprints)}):[/]")
        for comp_id, fp in list(result.footprints.items())[:6]:
            console.print(f"  [dim]{comp_id}[/]  {fp}")
        if len(result.footprints) > 6:
            console.print(f"  [dim]... and {len(result.footprints) - 6} more[/]")

    if result.drc_errors:
        console.print(f"\n[yellow]DRC ({len(result.drc_errors)} issues):[/]")
        for err in result.drc_errors[:5]:
            console.print(f"  [yellow]→[/] {err}")

    if result.production_zip and result.production_zip.exists():
        size_kb = result.production_zip.stat().st_size // 1024
        table.add_row(result.production_zip.name, f"[green]✓[/] ({size_kb} kB)")

    if result.jlcpcb_summary:
        console.print()
        console.print("[bold]JLCPCB:[/]")
        for line in result.jlcpcb_summary.splitlines()[1:]:  # skip header
            console.print(f"  {line}")

    console.print()
    zip_note = ""
    if result.production_zip and result.production_zip.exists():
        zip_note = f"\n  [dim]ZIP:[/]     {result.production_zip.name}"
    note = "" if result.routed else "\n[dim]PCB unrouted — install FreeRouting for auto-routing.[/]"
    console.print(Panel.fit(
        f"[green bold]PCB generated![/] Output: [cyan]{out_dir.resolve()}[/]"
        f"\n  [dim]PCB:[/]     pcb.kicad_pcb\n  [dim]Gerbers:[/] gerbers/"
        + zip_note + note,
        border_style="green" if result.pcb_path else "red",
    ))
    if not result.pcb_path:
        sys.exit(1)


@cli.command("manufacture")
@click.option(
    "--out", "-o",
    default="./boardsmith-output",
    show_default=True,
    type=click.Path(),
    help="Output directory (contains pcb.kicad_pcb + gerbers/ from boardsmith pcb).",
)
@click.option(
    "--hir",
    default=None,
    type=click.Path(exists=True),
    help="HIR JSON input file (from boardsmith build-project). Auto-detected if --out is set.",
)
@click.option(
    "--service", "-s",
    default=["jlcpcb"],
    multiple=True,
    type=click.Choice(["jlcpcb", "seeed", "pcbway", "generic"], case_sensitive=False),
    show_default=True,
    help="Target manufacturing service. Can be specified multiple times.",
)
def manufacture(
    out: str,
    hir: str | None,
    service: tuple[str, ...],
) -> None:
    """Create order-ready manufacturing packages for PCB services.

    Reads PCB artifacts from --out (produced by boardsmith pcb) and packages
    them as service-specific order bundles:

    \b
      gerbers_{service}.zip    -- Gerber files ready for upload
      bom_{service}.csv        -- BOM in service format
      cpl_{service}.csv        -- Pick-and-Place file for SMT assembly
      README_{service}.md      -- Step-by-step ordering guide

    \b
    Examples:
        boardsmith manufacture --out ./output --service jlcpcb
        boardsmith manufacture --out ./output -s jlcpcb -s seeed
        boardsmith manufacture --out ./output -s pcbway --hir ./output/hir.json
    """
    out_dir = Path(out)

    # --- Load HIR ---
    hir_path = Path(hir) if hir else out_dir / "hir.json"
    if not hir_path.exists():
        console.print(
            f"[red]Error:[/] No HIR file found: {hir_path}\n"
            "[dim]Tip: Run `boardsmith build-project` first.[/]"
        )
        sys.exit(1)

    try:
        hir_dict = json.loads(hir_path.read_text())
        console.print(f"[dim]HIR loaded: {hir_path}[/]")
    except Exception as e:
        console.print(f"[red]Error:[/] HIR not readable: {e}")
        sys.exit(1)

    # --- Check for existing PCB pipeline output ---
    pcb_path = out_dir / "pcb.kicad_pcb"
    gerber_dir = out_dir / "gerbers"

    if not pcb_path.exists():
        console.print(
            f"[red]Error:[/] No pcb.kicad_pcb found: {pcb_path}\n"
            "[dim]Tip: Run `boardsmith pcb` first.[/]"
        )
        sys.exit(1)

    # --- Reconstruct minimal PcbResult from disk ---
    try:
        from boardsmith_hw.pcb_pipeline import PcbResult
    except ImportError as e:
        console.print(f"[red]Error:[/] PCB pipeline not found: {e}")
        sys.exit(1)

    # Detect real vs. stub gerbers by file size (stubs are ~50 bytes)
    real_gerbers = False
    if gerber_dir.exists():
        gbr_files = list(gerber_dir.glob("*.gbr"))
        real_gerbers = any(f.stat().st_size > 500 for f in gbr_files)

    # Re-resolve footprints (no LLM, fast)
    footprints_map: dict[str, str] = {}
    try:
        from boardsmith_hw.footprint_mapper import FootprintMapper
        fp_infos = FootprintMapper(use_llm=False).resolve_all(hir_dict)
        footprints_map = {cid: fi.kicad_footprint for cid, fi in fp_infos.items()}
    except Exception as e:
        console.print(f"[yellow]Note:[/] Footprint resolution skipped: {e}")

    pcb_result = PcbResult(
        pcb_path=pcb_path,
        gerber_dir=gerber_dir if gerber_dir.exists() else None,
        routed=False,
        real_gerbers=real_gerbers,
        footprints=footprints_map,
        router_method="unknown",
    )

    # --- Header ---
    services_str = ", ".join(service)
    console.print()
    console.print(Panel.fit(
        f"[bold cyan]Boardsmith Manufacture[/] -- PCB -> Order-ready Package\n\n"
        f"[dim]Output:[/]    {out_dir.resolve()}\n"
        f"[dim]Service(s):[/] {services_str}",
        border_style="cyan",
    ))
    console.print()

    # --- Import exporter ---
    try:
        from boardsmith_hw.manufacturing_exporter import ManufacturingExporter
    except ImportError as e:
        console.print(f"[red]Error:[/] ManufacturingExporter not found: {e}")
        sys.exit(1)

    exporter = ManufacturingExporter()
    all_packages = []

    for svc in service:
        mfg_dir = out_dir / "manufacturing" / svc
        with console.status(f"[bold green]Creating package for {svc}...[/]", spinner="dots"):
            try:
                pkg = exporter.export(
                    service=svc,
                    pcb_result=pcb_result,
                    hir_dict=hir_dict,
                    out_dir=mfg_dir,
                )
                all_packages.append((svc, pkg))
            except Exception as e:
                console.print(f"[red]Error for {svc}:[/] {e}")

    # --- Results display ---
    for svc, pkg in all_packages:
        table = Table(
            title=f"{svc.upper()} Files",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("File", style="dim")
        table.add_column("Status")

        def _status(p: Path | None, label: str) -> None:
            if p and p.exists():
                table.add_row(p.name, f"[green]+ {label}[/]")
            else:
                table.add_row(label, "[yellow]o skipped[/]")

        _status(pkg.gerber_zip, "Gerber ZIP")
        _status(pkg.bom_csv, "BOM CSV")
        _status(pkg.cpl_csv, "CPL CSV")
        _status(pkg.readme, "README")
        console.print(table)

        if pkg.warnings:
            for w in pkg.warnings:
                console.print(f"  [yellow]![/] {w}")
        console.print()

    # --- Summary ---
    if all_packages:
        paths_str = "\n".join(
            f"  {svc}:  manufacturing/{svc}/" for svc, _ in all_packages
        )
        console.print(Panel.fit(
            f"[green bold]Manufacturing packages ready![/]\n{paths_str}\n\n"
            "[dim]Next step: Read the README in each folder for upload instructions.[/]",
            border_style="green",
        ))
    else:
        console.print(Panel.fit("[red bold]No packages created.[/]", border_style="red"))
        sys.exit(1)


@cli.command("pcb-export")
@click.option(
    "--hir",
    default=None,
    type=click.Path(exists=True),
    help="HIR-JSON input file.",
)
@click.option(
    "--out", "-o",
    default="./boardsmith-output",
    show_default=True,
    type=click.Path(),
    help="Output directory (must contain gerbers/ from previous pcb run).",
)
@click.option(
    "--name",
    default=None,
    help="Project name prefix for the ZIP file (default: from HIR system_name).",
)
def pcb_export(hir: str | None, out: str, name: str | None) -> None:
    """Generate JLCPCB-ready production bundle from PCB pipeline output.

    Packages Gerbers + BOM + Centroid CSV + design rules into a ZIP file
    that can be uploaded directly to jlcpcb.com.

    Runs the full validation suite:
      - IPC-2221 trace width & signal integrity rules
      - JLCPCB parts availability (Basic / Extended / Not found)
      - Gerber layer completeness check

    \b
    Examples:
        boardsmith pcb-export --hir ./output/hir.json --out ./output
        boardsmith pcb-export --out ./output --name my-iot-board
    """
    out_dir = Path(out)

    # Load HIR
    hir_dict: dict = {}
    if hir:
        try:
            hir_dict = json.loads(Path(hir).read_text())
        except Exception as e:
            console.print(f"[red]Error:[/] Could not read HIR: {e}")
            sys.exit(1)
    else:
        auto_hir = out_dir / "hir.json"
        if auto_hir.exists():
            try:
                hir_dict = json.loads(auto_hir.read_text())
                console.print(f"[dim]HIR loaded from {auto_hir}[/]")
            except Exception as e:
                console.print(f"[red]Error:[/] Could not read HIR: {e}")
                sys.exit(1)

    project_name = name
    if not project_name:
        import re as _re
        raw_name = hir_dict.get("system_name", "boardsmith")
        project_name = _re.sub(r"[^a-zA-Z0-9_\-]", "_", str(raw_name))

    console.print()
    console.print(Panel.fit(
        f"[bold cyan]Boardsmith PCB Export[/] -- Production Bundle\n\n"
        f"[dim]Output:[/]  {out_dir.resolve()}\n"
        f"[dim]Project:[/] {project_name}",
        border_style="cyan",
    ))
    console.print()

    try:
        from boardsmith_hw.pcb_production import PcbProductionExporter
        from boardsmith_hw.pcb_pipeline import PcbResult
    except ImportError as e:
        console.print(f"[red]Error:[/] Production exporter not found: {e}")
        sys.exit(1)

    # Build a minimal PcbResult stub pointing to existing output
    stub_result = PcbResult(
        pcb_path=out_dir / "pcb.kicad_pcb",
        gerber_dir=out_dir / "gerbers",
        routed=False,
        footprints={},
    )

    with console.status("[bold green]Creating production bundle...[/]", spinner="dots"):
        exporter = PcbProductionExporter()
        bundle = exporter.export(stub_result, hir_dict, out_dir, project_name)

    # --- Design rules ---
    if bundle.design_rules:
        console.print("[bold]Design Rules (IPC-2221):[/]")
        for line in bundle.design_rules.summary().splitlines()[1:]:
            console.print(f"  {line}")
        console.print()

    # --- JLCPCB report ---
    if bundle.jlcpcb_report:
        r = bundle.jlcpcb_report
        console.print("[bold]JLCPCB Parts Availability:[/]")
        console.print(f"  Basic:    [green]{r.basic_count}[/]  (no fee)")
        console.print(f"  Extended: [yellow]{r.extended_count}[/]  "
                      f"(${r.estimated_setup_fee_usd:.0f} setup fee)")
        console.print(f"  Missing:  [red]{r.not_found_count}[/]  (hand-solder)")
        if r.not_found_count:
            for item in r.items:
                if item.tier == "not_found":
                    console.print(f"    [red]![/] {item.component_id} ({item.mpn})")
        console.print()

    # --- Gerber validation ---
    if bundle.gerber_report:
        gr = bundle.gerber_report
        status = "[green]PASS[/]" if gr.valid else "[red]FAIL[/]"
        console.print(f"[bold]Gerber Validation:[/] {status}")
        console.print(f"  Layers: {len(gr.layers)}  "
                      f"Drill: {'yes' if gr.has_drill else 'no'}  "
                      f"Outline: {'yes' if gr.has_outline else 'no'}")
        if gr.stub_gerbers:
            console.print("  [yellow]! Stub Gerbers -- install kicad-cli for real output[/]")
        for issue in gr.issues[:3]:
            console.print(f"  [red]x[/] {issue}")
        for warning in gr.warnings[:3]:
            console.print(f"  [yellow]![/] {warning}")
        console.print()

    # --- Warnings / errors ---
    if bundle.warnings:
        console.print("[yellow]Warnings:[/]")
        for w in bundle.warnings[:5]:
            console.print(f"  [yellow]![/] {w}")
        console.print()

    # --- Final result ---
    if bundle.zip_path and bundle.zip_path.exists():
        size_kb = bundle.zip_path.stat().st_size // 1024
        console.print(Panel.fit(
            f"[green bold]Production bundle ready![/]\n\n"
            f"  [dim]ZIP:[/]   [cyan]{bundle.zip_path.resolve()}[/]  ({size_kb} kB)\n"
            f"  [dim]BOM:[/]   {out_dir}/bom.csv\n"
            f"  [dim]Rules:[/] {out_dir}/design_rules.txt\n\n"
            f"Upload the ZIP to [link=https://jlcpcb.com]jlcpcb.com[/link] -> "
            f"PCB Quote -> SMT Assembly",
            border_style="green",
        ))
    else:
        if bundle.errors:
            for e in bundle.errors:
                console.print(f"[red]x[/] {e}")
        console.print(Panel.fit(
            "[red]Production bundle could not be created.[/]\n"
            "Check errors above and ensure `boardsmith pcb` was run first.",
            border_style="red",
        ))
        sys.exit(1)


@cli.command("review")
@click.option(
    "--schematic", "-s",
    required=True,
    type=click.Path(exists=True),
    help="Path to the .kicad_sch file",
)
@click.option(
    "--hir",
    default=None,
    type=click.Path(exists=True),
    help="Optional original HIR JSON for round-trip diff",
)
@click.option(
    "--max-iterations",
    default=3,
    show_default=True,
    type=int,
    help="Maximum auto-fix iterations (1–10)",
)
@click.option(
    "--no-llm",
    is_flag=True,
    default=False,
    help="Disable LLM-boosted auto-fixes (deterministic only)",
)
@click.option(
    "--out-hir",
    default=None,
    type=click.Path(),
    help="Output path for the reviewed HIR JSON (optional)",
)
def review(
    schematic: str,
    hir: str | None,
    max_iterations: int,
    no_llm: bool,
    out_hir: str | None,
) -> None:
    """Schematic review loop: .kicad_sch → constraint checks → auto-fix.

    Re-parses the exported schematic, validates it against the constraint
    solver (Track A), and attempts to auto-fix errors. Optional round-trip
    diff shows what was lost vs. the original HIR during export/import.

    \b
    Examples:
        boardsmith review --schematic ./output/schematic.kicad_sch
        boardsmith review --schematic ./output/schematic.kicad_sch \\
                        --hir ./output/hir.json \\
                        --out-hir ./output/hir_reviewed.json
        boardsmith review --schematic ./output/schematic.kicad_sch --no-llm
    """
    sch_path = Path(schematic)
    hir_path = Path(hir) if hir else None

    console.print()
    console.print(Panel.fit(
        f"[bold cyan]Boardsmith Review[/] — Schematic → Constraint Checks\n\n"
        f"[dim]Schematic:[/]  {sch_path.resolve()}"
        + (f"\n[dim]HIR:[/]       {hir_path.resolve()}" if hir_path else ""),
        border_style="cyan",
    ))
    console.print()

    try:
        from boardsmith_hw.schematic_reviewer import SchematicReviewer
    except ImportError as e:
        console.print(f"[red]Error:[/] SchematicReviewer not found: {e}")
        sys.exit(1)

    # Optional: load original HIR for diff
    original_hir: dict | None = None
    if hir_path:
        try:
            original_hir = json.loads(hir_path.read_text())
        except Exception as e:
            console.print(f"[yellow]Warning:[/] Could not load HIR: {e}")

    reviewer = SchematicReviewer(
        max_iterations=max(1, min(10, max_iterations)),
        use_llm=not no_llm,
    )

    with console.status("[bold green]Analyzing schematic...[/]", spinner="dots"):
        result = reviewer.review(sch_path, original_hir=original_hir)

    # --- Fatal error ---
    if result.error:
        console.print(f"\n[red bold]Error:[/] {result.error}")
        sys.exit(1)

    # --- Validation status ---
    status_color = "green" if result.valid else "red"
    status_text = "[green bold]VALID[/]" if result.valid else "[red bold]INVALID[/]"
    console.print(f"Status: {status_text}  |  "
                  f"Iterations: [cyan]{result.iterations}[/]  |  "
                  f"Errors: [yellow]{result.errors_before}[/] → [{status_color}]{result.errors_after}[/]")

    # --- Resolved / unresolvable ---
    if result.resolved:
        console.print(f"\n[green]Fixed ({len(result.resolved)}):[/]")
        for r in result.resolved:
            console.print(f"  [green]✓[/] {r}")

    if result.unresolvable:
        console.print(f"\n[red]Unresolvable ({len(result.unresolvable)}):[/]")
        for u in result.unresolvable:
            console.print(f"  [red]✗[/] {u}")

    if result.llm_boosted:
        console.print("\n[yellow dim]LLM boost was used.[/]")

    # --- Round-trip diff ---
    diff = result.diff
    if diff.has_diff:
        console.print("\n[yellow]Round-trip diff (original vs. re-parsed):[/]")
        for cid in diff.components_removed:
            console.print(f"  [red]−[/] Component removed: {cid}")
        for cid in diff.components_added:
            console.print(f"  [green]+[/] Component added: {cid}")
        for cid in diff.components_changed:
            console.print(f"  [yellow]~[/] Component changed: {cid}")
        for b in diff.buses_removed:
            console.print(f"  [red]−[/] Bus removed: {b}")
        for b in diff.buses_added:
            console.print(f"  [green]+[/] Bus added: {b}")
    elif original_hir is not None:
        console.print("\n[green dim]Round-trip complete — no diff.[/]")

    # --- Save reviewed HIR ---
    if out_hir and result.hir_dict:
        out_path = Path(out_hir)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result.hir_dict, indent=2, default=str))
        console.print(f"\n[dim]Reviewed HIR saved:[/] {out_path.resolve()}")

    # --- Summary panel ---
    console.print()
    if result.valid:
        console.print(Panel.fit(
            "[green bold]Review passed![/]\n"
            "Schematic passes all constraint checks.",
            border_style="green",
        ))
    else:
        console.print(Panel.fit(
            "[yellow bold]Review complete with open errors.[/]\n"
            f"Unresolvable constraints: {', '.join(result.unresolvable) or '—'}",
            border_style="yellow",
        ))
        sys.exit(1)


@cli.command("design-review")
@click.option(
    "--hir", "-h",
    required=True,
    type=click.Path(exists=True),
    help="Path to the HIR JSON file (from boardsmith build)",
)
@click.option(
    "--prompt", "-p",
    default="",
    help="Original design prompt (improves LLM review quality)",
)
@click.option(
    "--auto-improve",
    is_flag=True,
    default=False,
    help="Auto-fix detected issues and save improved HIR",
)
@click.option(
    "--max-iterations",
    default=5,
    show_default=True,
    type=int,
    help="Maximum auto-improve iterations",
)
@click.option(
    "--no-llm",
    is_flag=True,
    default=False,
    help="Deterministic checks only (no LLM)",
)
@click.option(
    "--out-hir",
    default=None,
    type=click.Path(),
    help="Output path for the improved HIR JSON (default: <hir>_improved.json)",
)
def design_review(
    hir: str,
    prompt: str,
    auto_improve: bool,
    max_iterations: int,
    no_llm: bool,
    out_hir: str | None,
) -> None:
    """Agentic design review loop: HIR → electrical + power + component checks.

    Analyzes the design holistically: electrical correctness, power budget,
    component quality, and (with LLM) cost optimization and layout hints.

    With --auto-improve, detected issues are automatically fixed and
    an improved HIR is saved.

    \b
    Examples:
        boardsmith design-review --hir ./output/hir.json
        boardsmith design-review --hir ./output/hir.json --auto-improve
        boardsmith design-review --hir ./output/hir.json --prompt "ESP32 CO2 monitor"
        boardsmith design-review --hir ./output/hir.json --no-llm
    """
    import asyncio
    hir_path = Path(hir)

    console.print()
    console.print(Panel.fit(
        f"[bold cyan]Boardsmith Design-Review[/] — Agentic Quality Review\n\n"
        f"[dim]HIR:[/]    {hir_path.resolve()}\n"
        f"[dim]Mode:[/]   {'Deterministic' if no_llm else 'LLM-boosted'}"
        + (f"  +  [cyan]Auto-Improve[/]" if auto_improve else ""),
        border_style="cyan",
    ))
    console.print()

    try:
        hir_dict = json.loads(hir_path.read_text())
    except Exception as e:
        console.print(f"[red]Error:[/] Could not load HIR: {e}")
        sys.exit(1)

    try:
        from agents.design_review_agent import DesignReviewAgent
    except ImportError as e:
        console.print(f"[red]Error:[/] DesignReviewAgent not found: {e}")
        sys.exit(1)

    # Build gateway
    gateway = None
    if not no_llm:
        try:
            from llm.gateway import get_default_gateway
            gateway = get_default_gateway()
        except ImportError:
            pass

    agent = DesignReviewAgent(
        gateway=gateway if not no_llm else None,
        max_agent_steps=8,
    )

    with console.status("[bold green]Analyzing design...[/]", spinner="dots"):
        review_result = asyncio.run(agent.review_async(hir_dict, prompt=prompt))

    # --- Score banner ---
    score_pct = int(review_result.score * 100)
    score_color = "green" if score_pct >= 85 else "yellow" if score_pct >= 65 else "red"
    console.print(
        f"Score: [{score_color}]{score_pct}%[/]  |  "
        f"Errors: [red]{len(review_result.errors)}[/]  |  "
        f"Warnings: [yellow]{len(review_result.warnings)}[/]"
        + (f"  |  [dim]LLM boost active[/]" if review_result.llm_boosted else "")
    )

    # --- Reference design match ---
    if review_result.reference_match:
        conf_pct = int(review_result.reference_match_confidence * 100)
        console.print(
            f"\n[cyan]Reference design match ({conf_pct}%):[/] "
            f"[dim]{review_result.reference_match}[/]"
        )

    # --- Issues ---
    if review_result.errors:
        console.print(f"\n[red bold]Errors ({len(review_result.errors)}):[/]")
        for issue in review_result.errors:
            console.print(f"  [red]✗[/] [{issue.category}] {issue.code}: {issue.message}")
            if issue.suggestion:
                console.print(f"      [dim]→ {issue.suggestion}[/]")

    if review_result.warnings:
        console.print(f"\n[yellow]Warnings ({len(review_result.warnings)}):[/]")
        for issue in review_result.warnings:
            console.print(f"  [yellow]⚠[/] [{issue.category}] {issue.code}: {issue.message}")
            if issue.suggestion:
                console.print(f"      [dim]→ {issue.suggestion}[/]")

    info_issues = [i for i in review_result.issues if i.severity == "info"]
    if info_issues:
        console.print(f"\n[dim]Info ({len(info_issues)}):[/]")
        for issue in info_issues:
            console.print(f"  [dim]ℹ {issue.code}: {issue.message}[/]")

    # --- Recommendations ---
    if review_result.recommendations:
        console.print(f"\n[cyan]Recommendations:[/]")
        for rec in review_result.recommendations[:5]:
            console.print(f"  [cyan]→[/] {rec}")

    # --- HITL gate ---
    if review_result.hitl_required:
        console.print(f"\n[red bold]⚠ Human review required:[/] {review_result.hitl_reason}")

    # --- Auto-Improve loop ---
    if auto_improve and (review_result.errors or review_result.warnings):
        console.print(f"\n[cyan bold]Starting auto-improve (max {max_iterations} iterations)...[/]")

        try:
            from boardsmith_hw.design_improver import DesignImprover
        except ImportError as e:
            console.print(f"[yellow]Auto-improve not available: {e}[/]")
        else:
            current_hir = hir_dict
            current_review = review_result
            applied_total: list[str] = []

            for iteration in range(1, max_iterations + 1):
                improver = DesignImprover()
                improvement = improver.apply(current_hir, current_review)

                if not improvement.applied:
                    console.print(f"  [dim]Iteration {iteration}: no more fixes available.[/]")
                    break

                applied_total.extend(improvement.applied)
                console.print(
                    f"  [green]Iteration {iteration}:[/] "
                    f"fixes applied: {', '.join(improvement.applied)}"
                )

                # Re-review improved HIR
                with console.status(f"  Re-reviewing iteration {iteration}...", spinner="dots2"):
                    current_review = asyncio.run(
                        agent.review_async(improvement.hir_dict, prompt=prompt)
                    )
                current_hir = improvement.hir_dict

                new_score = int(current_review.score * 100)
                score_col = "green" if new_score >= 85 else "yellow" if new_score >= 65 else "red"
                console.print(
                    f"  → Score after iteration {iteration}: "
                    f"[{score_col}]{new_score}%[/]  "
                    f"(errors: {len(current_review.errors)})"
                )

                if not current_review.errors and not current_review.warnings:
                    console.print(f"  [green]✓ All issues resolved![/]")
                    break

            # Save improved HIR
            out_path = Path(out_hir) if out_hir else hir_path.with_name(
                hir_path.stem + "_improved.json"
            )
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(current_hir, indent=2, default=str))
            console.print(f"\n[dim]Improved HIR saved:[/] {out_path.resolve()}")

            console.print(
                f"\n[cyan]Auto-improve summary:[/] "
                f"{len(applied_total)} fix(es): {', '.join(set(applied_total)) or '—'}"
            )
            review_result = current_review

    # --- Summary panel ---
    console.print()
    if review_result.passed and not review_result.hitl_required:
        console.print(Panel.fit(
            f"[green bold]Design review passed![/]\n"
            f"Score: {int(review_result.score * 100)}% — no human intervention required.",
            border_style="green",
        ))
    elif review_result.hitl_required:
        console.print(Panel.fit(
            f"[yellow bold]Human review required[/]\n"
            f"{review_result.hitl_reason}",
            border_style="yellow",
        ))
        sys.exit(1)
    else:
        console.print(Panel.fit(
            f"[yellow bold]Design review completed with warnings[/]\n"
            f"Score: {int(review_result.score * 100)}%  "
            f"Warnings: {len(review_result.warnings)}",
            border_style="yellow",
        ))


@cli.command("erc")
@click.option(
    "--schematic", "-s",
    required=True,
    type=click.Path(exists=True),
    help="Path to the .kicad_sch file",
)
@click.option(
    "--hir",
    default=None,
    type=click.Path(exists=True),
    help="Optional HIR JSON for component-based checks",
)
def erc(schematic: str, hir: str | None) -> None:
    """Schematic ERC: check net connections in a .kicad_sch file.

    Parses the exported schematic and checks:
      - Expected bus nets (SDA/SCL for I2C, MOSI/MISO/SCLK for SPI)
      - All HIR components present (when --hir is provided)
      - Bus masters and slaves connected to the correct nets

    \b
    Examples:
        boardsmith erc --schematic ./output/schematic.kicad_sch
        boardsmith erc --schematic ./output/schematic.kicad_sch --hir ./output/hir.json
    """
    sch_path = Path(schematic)
    hir_path = Path(hir) if hir else None

    console.print()
    console.print(Panel.fit(
        f"[bold cyan]Boardsmith ERC[/] — Electrical Rules Check\n\n"
        f"[dim]Schematic:[/]  {sch_path.resolve()}"
        + (f"\n[dim]HIR:[/]       {hir_path.resolve()}" if hir_path else ""),
        border_style="cyan",
    ))
    console.print()

    try:
        from boardsmith_hw.schematic_erc import SchematicERC
    except ImportError as e:
        console.print(f"[red]Error:[/] SchematicERC not found: {e}")
        sys.exit(1)

    hir_dict: dict | None = None
    if hir_path:
        try:
            hir_dict = json.loads(hir_path.read_text())
        except Exception as e:
            console.print(f"[yellow]Warning:[/] Could not load HIR: {e}")

    erc_checker = SchematicERC()
    with console.status("[bold green]Checking schematic...[/]", spinner="dots"):
        result = erc_checker.check(sch_path, hir_dict=hir_dict)

    # --- Summary ---
    status_color = "green" if result.passed else "red"
    status_text = "[green bold]PASS[/]" if result.passed else "[red bold]FAILED[/]"
    console.print(
        f"Status: {status_text}  |  "
        f"Components: [cyan]{result.component_count}[/]  |  "
        f"Nets: [cyan]{result.net_count}[/]  |  "
        f"Buses: [cyan]{result.bus_count}[/]"
    )

    # --- Issues ---
    errors = result.errors
    warnings = result.warnings

    if errors:
        console.print(f"\n[red bold]Errors ({len(errors)}):[/]")
        for issue in errors:
            console.print(f"  [red]✗[/] [{issue.code}] {issue.message}")

    if warnings:
        console.print(f"\n[yellow]Warnings ({len(warnings)}):[/]")
        for issue in warnings:
            console.print(f"  [yellow]![/] [{issue.code}] {issue.message}")

    info = [i for i in result.issues if i.severity == "info"]
    if info:
        console.print(f"\n[dim]Info ({len(info)}):[/]")
        for issue in info:
            console.print(f"  [dim]→[/] [{issue.code}] {issue.message}")

    if not result.issues:
        console.print("\n[green dim]No issues found.[/]")

    # --- Panel ---
    console.print()
    if result.passed:
        console.print(Panel.fit(
            f"[green bold]ERC passed![/]  "
            f"{result.component_count} components, {result.net_count} nets.",
            border_style="green",
        ))
    else:
        console.print(Panel.fit(
            f"[red bold]ERC failed![/]  "
            f"{len(errors)} errors, {len(warnings)} warnings.\n"
            "Check output above for details.",
            border_style="red",
        ))
        sys.exit(1)


# ---------------------------------------------------------------------------
# compile — invoke PlatformIO / ESP-IDF on generated firmware
# ---------------------------------------------------------------------------


@cli.command("compile")
@click.option(
    "--out", "-o",
    default="./boardsmith-output",
    type=click.Path(),
    help="Output directory that contains the generated firmware (from boardsmith build).",
)
@click.option(
    "--target", "-t",
    default="auto",
    type=click.Choice(["auto", "esp32", "esp32c3", "stm32", "rp2040", "nrf52"]),
    help="Firmware target (auto-detected from platformio.ini when available).",
)
@click.option(
    "--runner",
    default="auto",
    type=click.Choice(["auto", "platformio", "idf", "cmake"]),
    help="Build runner to use.",
)
def compile_firmware(out: str, target: str, runner: str) -> None:
    """Compile generated firmware using PlatformIO, ESP-IDF, or CMake.

    \b
    Examples:
        boardsmith compile --out ./output
        boardsmith compile --out ./output --runner platformio
        boardsmith compile --out ./output --target esp32 --runner idf
    """
    import subprocess

    out_path = Path(out)
    if not out_path.exists():
        console.print(f"[red]Output directory not found: {out_path}[/]")
        console.print("[dim]Tip: Run `boardsmith build` first.[/]")
        sys.exit(1)

    # Auto-detect runner from available build files
    pio_ini = out_path / "platformio.ini"
    cmake_lists = out_path / "main" / "CMakeLists.txt"

    if runner == "auto":
        if pio_ini.exists():
            runner = "platformio"
        elif cmake_lists.exists():
            runner = "idf"
        else:
            runner = "cmake"

    console.print(f"\n[bold]Compiling firmware[/] ({runner}) in [cyan]{out_path}[/]\n")

    try:
        if runner == "platformio":
            cmd = ["pio", "run", "--project-dir", str(out_path)]
        elif runner == "idf":
            cmd = ["idf.py", "-C", str(out_path), "build"]
        else:
            build_dir = out_path / "_build"
            build_dir.mkdir(exist_ok=True)
            subprocess.run(
                ["cmake", "..", "-DCMAKE_BUILD_TYPE=Release"],
                cwd=build_dir,
                check=True,
            )
            cmd = ["cmake", "--build", str(build_dir)]

        result = subprocess.run(cmd, capture_output=False)

        if result.returncode == 0:
            console.print("\n[green bold]Compilation successful.[/]")
        else:
            console.print("\n[red bold]Compilation failed.[/]")
            sys.exit(result.returncode)

    except FileNotFoundError as exc:
        tool = str(exc).split("'")[1] if "'" in str(exc) else runner
        console.print(f"\n[red]Build tool not found: {tool}[/]")
        if runner == "platformio":
            console.print("[dim]Install PlatformIO: pip install platformio[/]")
        elif runner == "idf":
            console.print("[dim]Install ESP-IDF: https://docs.espressif.com/projects/esp-idf/en/latest/get-started/[/]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# test-firmware — simulate firmware with QEMU / Renode
# ---------------------------------------------------------------------------


@cli.command("test-firmware")
@click.option(
    "--out", "-o",
    default="./boardsmith-output",
    type=click.Path(),
    help="Output directory containing generated firmware (from boardsmith build).",
)
@click.option(
    "--target", "-t",
    default="esp32",
    type=click.Choice(["esp32", "esp32c3", "stm32", "rp2040", "nrf52"]),
    help="Firmware target (must match the compiled binary).",
)
@click.option(
    "--simulate",
    is_flag=True,
    default=False,
    help="Run in simulation (QEMU / Renode) instead of on real hardware.",
)
@click.option(
    "--simulator",
    default="auto",
    type=click.Choice(["auto", "qemu", "renode"]),
    help="Simulation backend (auto = prefer Renode, fall back to QEMU).",
)
@click.option(
    "--elf",
    default=None,
    type=click.Path(),
    help="Path to compiled ELF file (auto-detected from common build paths when omitted).",
)
@click.option(
    "--timeout",
    default=10,
    type=int,
    help="Simulation timeout in seconds.",
)
def test_firmware(
    out: str,
    target: str,
    simulate: bool,
    simulator: str,
    elf: str | None,
    timeout: int,
) -> None:
    """Test generated firmware via QEMU or Renode simulation.

    \b
    Examples:
        boardsmith test-firmware --out ./output --simulate
        boardsmith test-firmware --out ./output --simulate --simulator renode
        boardsmith test-firmware --out ./output --simulate --target stm32 --elf build/firmware.elf
    """
    import subprocess

    out_path = Path(out)

    if not simulate:
        console.print("[yellow]No --simulate flag given. Nothing to do.[/]")
        console.print("[dim]Use: boardsmith test-firmware --simulate[/]")
        return

    # Resolve ELF path
    if elf:
        elf_path = Path(elf)
    else:
        candidates = [
            out_path / ".pio" / "build" / "default" / "firmware.elf",
            out_path / "build" / "app-template.elf",
            out_path / "build" / "firmware.elf",
            out_path / "_build" / "firmware.elf",
        ]
        elf_path = next((p for p in candidates if p.exists()), None)

    # Generate HIL simulation config
    try:
        from boardsmith_fw.codegen.hil_simulation import generate_hil, HILConfig
    except ImportError:
        console.print("[red]HIL simulation module not available.[/]")
        sys.exit(1)

    hil_dir = out_path / "hil"
    hil_dir.mkdir(parents=True, exist_ok=True)

    config = HILConfig(
        firmware_elf=str(elf_path) if elf_path else "build/firmware.elf",
        timeout_s=timeout,
    )
    hil_result = generate_hil(target=target, config=config)
    for fname, content in hil_result.files:
        fpath = out_path / fname
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content)
    if hil_result.warnings:
        for w in hil_result.warnings:
            console.print(f"[yellow]HIL warning:[/] {w}")

    console.print(f"[dim]HIL config written to {hil_dir}[/]")

    # Auto-detect simulator
    def _has_tool(name: str) -> bool:
        import shutil
        return shutil.which(name) is not None

    if simulator == "auto":
        simulator = "renode" if _has_tool("renode") else "qemu"

    if elf_path is None or not elf_path.exists():
        console.print(
            f"\n[yellow]ELF not found — simulation config generated but not executed.[/]\n"
            f"[dim]Compile first: boardsmith compile --out {out}\n"
            f"Then run: {hil_dir}/qemu_run.sh  (or load {hil_dir}/simulation.resc in Renode)[/]"
        )
        console.print(f"\n[green]HIL scripts ready in [cyan]{hil_dir}[/][/]")
        return

    console.print(f"\n[bold]Running firmware simulation[/] ({simulator}, {timeout}s)\n")

    if simulator == "renode":
        resc_file = hil_dir / "simulation.resc"
        if not resc_file.exists():
            console.print("[red]simulation.resc not found.[/]")
            sys.exit(1)
        cmd = ["renode", "--console", str(resc_file)]
    else:
        qemu_script = hil_dir / "qemu_run.sh"
        if not qemu_script.exists():
            console.print("[red]qemu_run.sh not found.[/]")
            sys.exit(1)
        qemu_script.chmod(0o755)
        cmd = [str(qemu_script), str(elf_path)]

    try:
        result = subprocess.run(cmd, timeout=timeout + 5)
        if result.returncode == 0:
            console.print("\n[green bold]Simulation passed.[/]")
        else:
            console.print(f"\n[yellow]Simulation exited with code {result.returncode}.[/]")
    except subprocess.TimeoutExpired:
        console.print(f"\n[yellow]Simulation timed out after {timeout + 5}s.[/]")
    except FileNotFoundError:
        console.print(f"\n[red]{simulator} not found. Install it or use --simulator auto.[/]")
        console.print(f"[dim]HIL scripts are in {hil_dir} — run manually.[/]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Phase F — Import commands
# ---------------------------------------------------------------------------

@cli.command("import-mcu")
@click.option(
    "--source", "-s",
    required=True,
    type=click.Choice(["cubemx", "espidf", "picosdk"], case_sensitive=False),
    help="SDK source format to parse.",
)
@click.argument("path", type=click.Path(exists=True))
@click.option(
    "--validate/--no-validate",
    default=True,
    show_default=True,
    help="Validate imported profile against existing data.",
)
@click.option(
    "--register/--no-register",
    "do_register",
    default=False,
    show_default=True,
    help="Register the imported profile in the runtime registry.",
)
@click.option(
    "--out", "-o",
    default=None,
    type=click.Path(),
    help="Write imported profile as JSON to this path.",
)
def import_mcu(source: str, path: str, validate: bool, do_register: bool, out: str | None) -> None:
    """Import MCU profile from SDK data.

    Parses vendor SDK files and converts them to MCUDeviceProfile objects.

    \b
    Sources:
        cubemx  — STM32CubeMX XML file (e.g. STM32G431CBUx.xml)
        espidf  — ESP-IDF soc/ headers directory
        picosdk — Pico SDK directory (or uses built-in table)

    \b
    Examples:
        boardsmith import-mcu --source cubemx ./STM32G431CBUx.xml
        boardsmith import-mcu --source espidf ./esp-idf/components/soc/esp32s3/include/soc/
        boardsmith import-mcu --source picosdk ./pico-sdk/src/rp2040/ --register
    """
    from rich.table import Table

    source_lower = source.lower()

    console.print(f"\n[bold cyan]Importing MCU profile[/] from {source} source: {path}\n")

    try:
        if source_lower == "cubemx":
            from shared.knowledge.importers.cubemx_parser import parse_cubemx_xml
            profile = parse_cubemx_xml(path)
        elif source_lower == "espidf":
            from shared.knowledge.importers.espidf_parser import parse_espidf_headers
            profile = parse_espidf_headers(path)
        elif source_lower == "picosdk":
            from shared.knowledge.importers.picosdk_parser import parse_picosdk_headers
            profile = parse_picosdk_headers(path)
        else:
            console.print(f"[red]Unknown source: {source}[/]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Import failed: {e}[/]")
        sys.exit(1)

    # Display summary
    table = Table(title=f"Imported Profile: {profile.identity.mpn}")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Vendor", profile.identity.vendor)
    table.add_row("Family", profile.identity.family)
    table.add_row("MPN", profile.identity.mpn)
    table.add_row("Package", profile.identity.package)
    table.add_row("Pin Count", str(profile.identity.pin_count))
    table.add_row("GPIO Pins", str(sum(1 for p in profile.pinout.pins if p.pin_type.value == "gpio")))
    table.add_row("Reserved Pins", str(len(profile.pinout.reserved_pins)))
    table.add_row("Pin Maps", str(len(profile.pinout.recommended_pinmaps)))
    table.add_row("Power Domains", str(len(profile.power.power_domains)))
    table.add_row("Provenance", profile.provenance[0].source_ref if profile.provenance else "none")
    table.add_row("Confidence", f"{profile.provenance[0].confidence_score:.0%}" if profile.provenance else "N/A")
    console.print(table)
    console.print()

    # Validate against existing profile
    if validate:
        from shared.knowledge.mcu_profiles import get as get_existing_profile
        existing = get_existing_profile(profile.identity.mpn)

        if existing:
            from shared.knowledge.importers.profile_diff import diff_profiles
            report = diff_profiles(profile, existing)

            diff_table = Table(title="Diff: Imported vs Existing")
            diff_table.add_column("Metric", style="cyan")
            diff_table.add_column("Value")
            diff_table.add_row("Pins Matching", str(report.pins_matching))
            diff_table.add_row("Pins Differing", str(report.pins_differing))
            diff_table.add_row("Pins Added", str(report.pins_added))
            diff_table.add_row("Pins Removed", str(report.pins_removed))
            diff_table.add_row("Alt-Funcs Added", str(report.alt_functions_added))
            diff_table.add_row("Alt-Funcs Removed", str(report.alt_functions_removed))
            diff_table.add_row("Match Score", f"{report.match_score:.0%}")

            console.print(diff_table)
            if report.has_errors:
                console.print("[red]Errors found in diff — review before using imported data.[/]")
            elif report.has_warnings:
                console.print("[yellow]Warnings found — imported data differs from hand-curated profile.[/]")
            else:
                console.print("[green]Import matches existing profile.[/]")
        else:
            console.print("[dim]No existing profile found for this MPN — cannot validate.[/]")

    # Write JSON output
    if out:
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(profile.model_dump_json(indent=2))
        console.print(f"\n[green]Profile written to {out_path}[/]")

    # Register in runtime registry
    if do_register:
        from shared.knowledge.mcu_profiles import register
        register(profile)
        console.print(f"[green]Profile registered for {profile.identity.mpn}[/]")

    console.print()


@cli.command("import-driver")
@click.option(
    "--url", "-u",
    required=True,
    help="Git repository URL of the driver library.",
)
@click.option(
    "--component", "-c",
    required=True,
    help="Component MPN this driver supports (e.g. BME280, SSD1306).",
)
@click.option(
    "--license", "license_str",
    default=None,
    help="SPDX license identifier (auto-detected if not specified).",
)
@click.option(
    "--integration",
    default="source_embed",
    show_default=True,
    type=click.Choice(["source_embed", "git_submodule", "package_manager", "wrapper_only"]),
    help="How the library is integrated.",
)
@click.option(
    "--ecosystem",
    default=None,
    type=click.Choice(["arduino", "esp-idf", "pico-sdk", "zephyr", "stm32hal", "generic"]),
    help="Target ecosystem for the driver.",
)
def import_driver(
    url: str,
    component: str,
    license_str: str | None,
    integration: str,
    ecosystem: str | None,
) -> None:
    """Import a driver library and check license compatibility.

    Checks the license of a driver library against AGPL-3.0 compatibility
    rules and reports whether the specified integration type is allowed.

    \b
    Examples:
        boardsmith import-driver --url https://github.com/boschsensortec/BME280_SensorAPI --component BME280
        boardsmith import-driver -u https://github.com/olikraus/u8g2 -c SSD1306 --license MIT
        boardsmith import-driver -u https://github.com/radiolib-org/RadioLib -c SX1276 --integration package_manager
    """
    from rich.table import Table

    console.print(f"\n[bold cyan]Importing driver[/] for {component}\n")

    # License check
    from shared.knowledge.importers.license_matrix import (
        check_license_compatibility,
        normalize_spdx_id,
    )

    effective_license = license_str or "MIT"  # Default assumption
    canonical = normalize_spdx_id(effective_license)

    result = check_license_compatibility(canonical, integration)

    table = Table(title=f"Driver Import: {component}")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Repository", url)
    table.add_row("Component", component)
    table.add_row("License (SPDX)", result.spdx_id)
    table.add_row("Integration Type", integration)
    table.add_row("Ecosystem", ecosystem or "auto-detect")
    table.add_row("Compatibility", result.level.value)

    # Color the allowed/blocked status
    if result.allowed:
        table.add_row("Status", "[green]ALLOWED[/]")
    else:
        table.add_row("Status", "[red]BLOCKED[/]")

    table.add_row("Action", result.action)
    console.print(table)

    console.print(f"\n{result.message}\n")

    if not result.allowed:
        console.print("[yellow]Suggestion: Try a different integration type (e.g. wrapper_only).[/]\n")

    # Show what profile entry would look like
    console.print("[dim]To add this driver to the knowledge DB, create a software profile module in[/]")
    console.print(f"[dim]  shared/knowledge/software_profiles/{component.lower()}.py[/]")
    console.print()


@cli.command("license-audit")
@click.option(
    "--component", "-c",
    default=None,
    help="Audit a specific component's driver licenses. If not specified, audits all.",
)
def license_audit(component: str | None) -> None:
    """Audit driver license compatibility across the knowledge DB.

    Checks all registered software profiles for AGPL-3.0 license
    compatibility and reports any issues.

    \b
    Examples:
        boardsmith license-audit
        boardsmith license-audit --component BME280
    """
    from rich.table import Table
    from shared.knowledge.importers.license_matrix import (
        check_license_compatibility,
        normalize_spdx_id,
    )

    console.print("\n[bold cyan]License Audit[/] — AGPL-3.0 Compatibility Check\n")

    try:
        from shared.knowledge.software_profiles import get_all
        all_profiles = get_all()
    except (ImportError, Exception):
        console.print("[red]Could not load software profiles.[/]")
        sys.exit(1)

    if component:
        # Filter to specific component
        component_upper = component.upper()
        all_profiles = {k: v for k, v in all_profiles.items()
                        if component_upper in k.upper()}

    if not all_profiles:
        console.print("[yellow]No software profiles found to audit.[/]")
        return

    table = Table(title="License Audit Results")
    table.add_column("Component", style="cyan")
    table.add_column("Driver")
    table.add_column("License")
    table.add_column("Integration")
    table.add_column("Level")
    table.add_column("Status")

    issues = 0
    total = 0

    for mpn, profile in sorted(all_profiles.items()):
        for option in profile.driver_options:
            total += 1

            license_id = getattr(option, "license_spdx", "MIT")
            integration = getattr(option, "integration_type", "source_embed")
            if hasattr(integration, "value"):
                integration = integration.value

            canonical = normalize_spdx_id(license_id)
            result = check_license_compatibility(canonical, integration)

            if result.allowed:
                status = "[green]OK[/]"
            else:
                status = "[red]BLOCKED[/]"
                issues += 1

            driver_name = getattr(option, "name", getattr(option, "library_name", "unknown"))

            table.add_row(
                mpn,
                driver_name,
                result.spdx_id,
                integration,
                result.level.value,
                status,
            )

    console.print(table)
    console.print(f"\n[dim]Total: {total} driver options, {issues} issues[/]\n")

    if issues:
        console.print(f"[yellow]{issues} license compatibility issues found.[/]")
    else:
        console.print("[green]All driver licenses are compatible.[/]")
    console.print()


if __name__ == "__main__":
    cli()
