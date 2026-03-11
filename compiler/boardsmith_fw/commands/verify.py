# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command: verify — compile-verify generated firmware in Docker containers.

This implements Produktprinzip #2: "Compilebarkeit ist Pflicht."

Supports:
  - ESP32 (ESP-IDF via espressif/idf container)
  - STM32 (arm-none-eabi-gcc)
  - RP2040 (Pico SDK)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console

console = Console()


@dataclass
class VerifyResult:
    target: str
    success: bool
    output: str
    errors: list[str]


def run_verify(
    project: Path,
    target: str = "auto",
    docker: bool = True,
) -> VerifyResult:
    """Verify that generated firmware compiles successfully."""
    project = project.resolve()

    console.print("[bold blue]Compile Verification[/]")
    console.print(f"  Project: {project}")

    if not project.exists():
        console.print(f"[red]Error: Project directory not found: {project}[/]")
        raise typer.Exit(1)

    resolved = _detect_target(project, target)
    console.print(f"  Target:  {resolved}")

    if docker and _has_docker():
        console.print("  Mode:    Docker container")
        result = _verify_docker(project, resolved)
    else:
        if docker:
            console.print("[yellow]  Docker not available, falling back to local toolchain[/]")
        console.print("  Mode:    Local toolchain")
        result = _verify_local(project, resolved)

    if result.success:
        console.print("\n[green]Compilation successful![/]")
    else:
        console.print("\n[red]Compilation FAILED[/]")
        for err in result.errors:
            console.print(f"[red]  {err}[/]")

    return result


def _has_docker() -> bool:
    """Check if Docker is available."""
    try:
        r = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _detect_target(project: Path, target: str) -> str:
    if target != "auto":
        return target

    meta_file = project / "generation_meta.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text())
            t = meta.get("target", "")
            if t in ("esp32", "stm32", "rp2040"):
                return t
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


# ---------------------------------------------------------------------------
# Docker-based verification
# ---------------------------------------------------------------------------

_DOCKER_IMAGES = {
    "esp32": "espressif/idf:latest",
    "stm32": "gcc-arm-none-eabi:latest",
    "rp2040": "gcc-arm-none-eabi:latest",
}

_DOCKER_SCRIPTS = {
    "esp32": (
        "cd /project && "
        ". $IDF_PATH/export.sh && "
        "idf.py set-target esp32 && "
        "idf.py build 2>&1"
    ),
    "stm32": (
        "cd /project && "
        "mkdir -p build && cd build && "
        "cmake -DCMAKE_C_COMPILER=arm-none-eabi-gcc "
        "-DCMAKE_SYSTEM_NAME=Generic -DCMAKE_SYSTEM_PROCESSOR=arm .. && "
        "cmake --build . 2>&1"
    ),
    "rp2040": (
        "cd /project && "
        "mkdir -p build && cd build && "
        "cmake .. && "
        "cmake --build . 2>&1"
    ),
}


def _verify_docker(project: Path, target: str) -> VerifyResult:
    image = _DOCKER_IMAGES.get(target, _DOCKER_IMAGES["esp32"])

    # For ESP-IDF, use the official container
    if target == "esp32":
        image = "espressif/idf:latest"
        script = _DOCKER_SCRIPTS["esp32"]
    elif target == "rp2040":
        # Use a custom build script with Pico SDK
        script = _DOCKER_SCRIPTS["rp2040"]
    else:
        script = _DOCKER_SCRIPTS.get(target, _DOCKER_SCRIPTS["esp32"])

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{project}:/project",
        image,
        "bash", "-c", script,
    ]

    console.print(f"[dim]  Image: {image}[/]")
    console.print("[dim]  Compiling...[/]")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        errors = _extract_errors(result.stderr + result.stdout)

        return VerifyResult(
            target=target,
            success=result.returncode == 0,
            output=result.stdout[-2000:] if result.stdout else "",
            errors=errors,
        )
    except subprocess.TimeoutExpired:
        return VerifyResult(
            target=target,
            success=False,
            output="",
            errors=["Compilation timed out (300s)"],
        )
    except FileNotFoundError:
        return VerifyResult(
            target=target,
            success=False,
            output="",
            errors=["Docker not found"],
        )


# ---------------------------------------------------------------------------
# Local toolchain verification (fallback)
# ---------------------------------------------------------------------------

def _verify_local(project: Path, target: str) -> VerifyResult:
    """Try to compile with locally installed toolchain."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Copy project to temp dir to avoid polluting the original
        tmp_project = Path(tmpdir) / "project"
        shutil.copytree(project, tmp_project)

        if target == "esp32":
            return _verify_local_esp32(tmp_project)
        if target == "stm32":
            return _verify_local_cmake(tmp_project, target)
        if target == "rp2040":
            return _verify_local_cmake(tmp_project, target)

        return VerifyResult(
            target=target,
            success=False,
            output="",
            errors=[f"Unknown target: {target}"],
        )


def _verify_local_esp32(project: Path) -> VerifyResult:
    import os
    if not os.environ.get("IDF_PATH"):
        return VerifyResult(
            target="esp32",
            success=False,
            output="",
            errors=["IDF_PATH not set. Cannot verify locally."],
        )

    try:
        r = subprocess.run(
            ["idf.py", "build"],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return VerifyResult(
            target="esp32",
            success=r.returncode == 0,
            output=r.stdout[-2000:] if r.stdout else "",
            errors=_extract_errors(r.stderr + r.stdout),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return VerifyResult(
            target="esp32",
            success=False,
            output="",
            errors=[str(e)],
        )


def _verify_local_cmake(project: Path, target: str) -> VerifyResult:
    build_dir = project / "build"
    build_dir.mkdir(exist_ok=True)

    try:
        # Configure
        cmake_cmd = ["cmake", ".."]
        if target == "stm32":
            cmake_cmd = [
                "cmake",
                "-DCMAKE_C_COMPILER=arm-none-eabi-gcc",
                "-DCMAKE_SYSTEM_NAME=Generic",
                "-DCMAKE_SYSTEM_PROCESSOR=arm",
                "..",
            ]

        r1 = subprocess.run(
            cmake_cmd,
            cwd=build_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if r1.returncode != 0:
            return VerifyResult(
                target=target,
                success=False,
                output=r1.stdout[-2000:] if r1.stdout else "",
                errors=_extract_errors(r1.stderr + r1.stdout),
            )

        # Build
        r2 = subprocess.run(
            ["cmake", "--build", "."],
            cwd=build_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return VerifyResult(
            target=target,
            success=r2.returncode == 0,
            output=r2.stdout[-2000:] if r2.stdout else "",
            errors=_extract_errors(r2.stderr + r2.stdout),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return VerifyResult(
            target=target,
            success=False,
            output="",
            errors=[str(e)],
        )


# ---------------------------------------------------------------------------
# Error extraction
# ---------------------------------------------------------------------------

def _extract_errors(output: str) -> list[str]:
    """Extract compilation error lines from build output."""
    errors: list[str] = []
    for line in output.splitlines():
        line_lower = line.lower()
        if "error:" in line_lower or "fatal error:" in line_lower:
            cleaned = line.strip()
            if cleaned and len(cleaned) < 500:
                errors.append(cleaned)
    return errors[:20]  # cap at 20 errors
