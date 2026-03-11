# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command: build — compile the generated firmware."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import typer
from rich.console import Console

console = Console()


def _detect_target(project: Path, target: str) -> str:
    """Resolve 'auto' target from generation_meta.json or project structure."""
    if target != "auto":
        return target

    meta_file = project / "generation_meta.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text())
            explanation = meta.get("explanation", "")
            if "STM32" in explanation:
                return "stm32"
            if "RP2040" in explanation or "Pico" in explanation:
                return "rp2040"
        except Exception:
            pass

    # Heuristic: STM32 projects have Inc/ and Src/, ESP-IDF has main/
    if (project / "Src").is_dir() and (project / "Inc").is_dir():
        return "stm32"
    if (project / "main").is_dir():
        return "esp32"

    # Check for Pico SDK markers
    cmake = project / "CMakeLists.txt"
    if cmake.exists():
        try:
            content = cmake.read_text()
            if "pico_sdk_import" in content:
                return "rp2040"
        except Exception:
            pass
    if (project / "src").is_dir() and not (project / "main").is_dir():
        return "rp2040"

    return "esp32"


def run_build(project: Path, target: str = "auto") -> None:
    project = project.resolve()

    console.print("[bold blue]Firmware Build[/]")
    console.print(f"  Project: {project}")

    if not project.exists():
        console.print(f"[red]Error: Project directory not found: {project}[/]")
        raise typer.Exit(1)

    if not (project / "CMakeLists.txt").exists():
        console.print(f"[red]Error: CMakeLists.txt not found in {project}[/]")
        raise typer.Exit(1)

    resolved = _detect_target(project, target)
    console.print(f"  Target:  {resolved}")

    if resolved == "stm32":
        _build_stm32(project)
    elif resolved == "rp2040":
        _build_rp2040(project)
    else:
        _build_esp32(project)


def _build_esp32(project: Path) -> None:
    idf_path = os.environ.get("IDF_PATH")
    if not idf_path:
        console.print(
            "[red]Error: IDF_PATH not set.\n"
            "  Install ESP-IDF: https://docs.espressif.com/projects/esp-idf/en/latest/esp32/get-started/\n"
            "  Then run: . $HOME/esp/esp-idf/export.sh[/]"
        )
        raise typer.Exit(1)

    console.print(f"[dim]  IDF_PATH: {idf_path}[/]")

    try:
        console.print("[dim]  Setting target to ESP32...[/]")
        subprocess.run(["idf.py", "set-target", "esp32"], cwd=project, check=True)

        console.print("[dim]  Building...[/]")
        subprocess.run(["idf.py", "build"], cwd=project, check=True)

        console.print("\n[green]Build successful![/]")
        console.print(f"  Binary: {project / 'build' / 'eagle_firmware.bin'}")
    except subprocess.CalledProcessError:
        console.print("\n[red]Build failed. Check errors above.[/]")
        raise typer.Exit(1)


def _build_stm32(project: Path) -> None:
    build_dir = project / "build"
    build_dir.mkdir(exist_ok=True)

    try:
        console.print("[dim]  Configuring CMake (arm-none-eabi-gcc)...[/]")
        subprocess.run(
            [
                "cmake",
                "-DCMAKE_C_COMPILER=arm-none-eabi-gcc",
                "-DCMAKE_SYSTEM_NAME=Generic",
                "-DCMAKE_SYSTEM_PROCESSOR=arm",
                "..",
            ],
            cwd=build_dir,
            check=True,
        )

        console.print("[dim]  Building...[/]")
        subprocess.run(["cmake", "--build", "."], cwd=build_dir, check=True)

        console.print("\n[green]Build successful![/]")
        console.print(f"  Output: {build_dir}")
    except FileNotFoundError:
        console.print(
            "[red]Error: arm-none-eabi-gcc or cmake not found.\n"
            "  Install ARM toolchain: sudo apt install gcc-arm-none-eabi cmake\n"
            "  Or download from: https://developer.arm.com/downloads/-/gnu-rm[/]"
        )
        raise typer.Exit(1)
    except subprocess.CalledProcessError:
        console.print("\n[red]Build failed. Check errors above.[/]")
        raise typer.Exit(1)


def _build_rp2040(project: Path) -> None:
    pico_sdk = os.environ.get("PICO_SDK_PATH")
    if not pico_sdk:
        console.print(
            "[red]Error: PICO_SDK_PATH not set.\n"
            "  Install Pico SDK: git clone https://github.com/raspberrypi/pico-sdk.git\n"
            "  Then: export PICO_SDK_PATH=/path/to/pico-sdk[/]"
        )
        raise typer.Exit(1)

    console.print(f"[dim]  PICO_SDK_PATH: {pico_sdk}[/]")

    build_dir = project / "build"
    build_dir.mkdir(exist_ok=True)

    try:
        console.print("[dim]  Configuring CMake (Pico SDK)...[/]")
        subprocess.run(["cmake", ".."], cwd=build_dir, check=True)

        console.print("[dim]  Building...[/]")
        subprocess.run(["cmake", "--build", "."], cwd=build_dir, check=True)

        console.print("\n[green]Build successful![/]")
        console.print(f"  UF2:  {build_dir / 'eagle_firmware.uf2'}")
        console.print(f"  ELF:  {build_dir / 'eagle_firmware.elf'}")
    except FileNotFoundError:
        console.print(
            "[red]Error: cmake or arm-none-eabi-gcc not found.\n"
            "  Install: sudo apt install cmake gcc-arm-none-eabi\n"
            "  Or download from: https://developer.arm.com/downloads/-/gnu-rm[/]"
        )
        raise typer.Exit(1)
    except subprocess.CalledProcessError:
        console.print("\n[red]Build failed. Check errors above.[/]")
        raise typer.Exit(1)
