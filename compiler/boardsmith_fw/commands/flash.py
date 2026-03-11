# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command: flash — flash firmware to target MCU."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import typer
from rich.console import Console

console = Console()


def _detect_target(project: Path, target: str) -> str:
    """Resolve target from generation_meta.json or project structure."""
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

    cmake = project / "CMakeLists.txt"
    if cmake.exists():
        try:
            content = cmake.read_text()
            if "pico_sdk_import" in content:
                return "rp2040"
        except Exception:
            pass

    if (project / "Src").is_dir() and (project / "Inc").is_dir():
        return "stm32"
    return "esp32"


def run_flash(
    project: Path,
    target: str = "auto",
    port: str = "auto",
) -> None:
    """Flash firmware to the target MCU."""
    project = project.resolve()

    console.print("[bold blue]Firmware Flash[/]")
    console.print(f"  Project: {project}")

    resolved = _detect_target(project, target)
    console.print(f"  Target:  {resolved}")

    if resolved == "esp32":
        _flash_esp32(project, port)
    elif resolved == "stm32":
        _flash_stm32(project)
    elif resolved == "rp2040":
        _flash_rp2040(project)
    else:
        console.print(f"[red]Unknown target: {resolved}[/]")
        raise typer.Exit(1)


def _flash_esp32(project: Path, port: str) -> None:
    cmd = ["esptool.py", "--chip", "esp32"]
    if port != "auto":
        cmd += ["--port", port]
    cmd += [
        "write_flash",
        "-z",
        "0x1000",
        str(project / "build" / "eagle_firmware.bin"),
    ]

    console.print(f"[dim]  Command: {' '.join(cmd)}[/]")
    try:
        subprocess.run(cmd, check=True)
        console.print("\n[green]Flash successful![/]")
    except FileNotFoundError:
        console.print(
            "[red]Error: esptool.py not found.\n"
            "  Install: pip install esptool[/]"
        )
        raise typer.Exit(1)
    except subprocess.CalledProcessError:
        console.print("\n[red]Flash failed.[/]")
        raise typer.Exit(1)


def _flash_stm32(project: Path) -> None:
    elf = project / "build" / "eagle_firmware.elf"
    if not elf.exists():
        console.print(f"[red]Error: {elf} not found. Build first.[/]")
        raise typer.Exit(1)

    cmd = ["st-flash", "write", str(elf), "0x08000000"]
    console.print(f"[dim]  Command: {' '.join(cmd)}[/]")
    try:
        subprocess.run(cmd, check=True)
        console.print("\n[green]Flash successful![/]")
    except FileNotFoundError:
        console.print(
            "[red]Error: st-flash not found.\n"
            "  Install: sudo apt install stlink-tools\n"
            "  Or: https://github.com/stlink-org/stlink[/]"
        )
        raise typer.Exit(1)
    except subprocess.CalledProcessError:
        console.print("\n[red]Flash failed.[/]")
        raise typer.Exit(1)


def _flash_rp2040(project: Path) -> None:
    uf2 = project / "build" / "eagle_firmware.uf2"
    if not uf2.exists():
        console.print(f"[red]Error: {uf2} not found. Build first.[/]")
        raise typer.Exit(1)

    console.print("[dim]  Using picotool for flashing...[/]")
    cmd = ["picotool", "load", "-f", str(uf2)]
    console.print(f"[dim]  Command: {' '.join(cmd)}[/]")
    try:
        subprocess.run(cmd, check=True)
        subprocess.run(["picotool", "reboot"], check=True)
        console.print("\n[green]Flash successful! Device rebooting.[/]")
    except FileNotFoundError:
        console.print(
            "[yellow]picotool not found. Trying USB mass storage copy...[/]"
        )
        _flash_rp2040_copy(uf2)
    except subprocess.CalledProcessError:
        console.print("\n[red]Flash failed.[/]")
        raise typer.Exit(1)


def _flash_rp2040_copy(uf2: Path) -> None:
    """Fallback: copy UF2 to mounted Pico drive."""
    import shutil

    pico_mount = Path("/media") / "RPI-RP2"
    if not pico_mount.exists():
        # Try common mount points
        for base in [Path("/media"), Path("/mnt"), Path("/run/media")]:
            if not base.exists():
                continue
            for d in base.iterdir():
                if d.is_dir():
                    rpi = d / "RPI-RP2"
                    if rpi.exists():
                        pico_mount = rpi
                        break
            for d in base.iterdir():
                if d.name == "RPI-RP2":
                    pico_mount = d
                    break

    if not pico_mount.exists():
        console.print(
            "[red]Error: RP2040 not found in BOOTSEL mode.\n"
            "  1. Hold BOOTSEL button\n"
            "  2. Connect USB\n"
            "  3. Release BOOTSEL\n"
            "  4. The RPI-RP2 drive should appear[/]"
        )
        raise typer.Exit(1)

    console.print(f"[dim]  Copying {uf2.name} to {pico_mount}[/]")
    shutil.copy2(uf2, pico_mount / uf2.name)
    console.print("\n[green]Flash successful! Device will reboot automatically.[/]")


def run_monitor(port: str = "auto", baud: int = 115200) -> None:
    """Open serial monitor to the target device."""
    console.print("[bold blue]Serial Monitor[/]")
    console.print(f"  Baud: {baud}")

    if port == "auto":
        port = _detect_port()

    console.print(f"  Port: {port}")
    console.print("[dim]  Press Ctrl+C to exit[/]")

    try:
        subprocess.run(
            ["python3", "-m", "serial.tools.miniterm", port, str(baud)],
            check=True,
        )
    except FileNotFoundError:
        console.print(
            "[red]Error: pyserial not found.\n"
            "  Install: pip install pyserial[/]"
        )
        raise typer.Exit(1)
    except subprocess.CalledProcessError:
        pass
    except KeyboardInterrupt:
        console.print("\n[dim]Monitor closed.[/]")


def _detect_port() -> str:
    """Try to auto-detect serial port."""
    import glob

    patterns = [
        "/dev/ttyUSB*",
        "/dev/ttyACM*",
        "/dev/cu.usbserial*",
        "/dev/cu.usbmodem*",
    ]
    for pattern in patterns:
        ports = sorted(glob.glob(pattern))
        if ports:
            return ports[0]
    return "/dev/ttyUSB0"
