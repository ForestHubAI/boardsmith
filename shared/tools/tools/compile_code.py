# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool: compile_code — compile firmware and report errors/warnings."""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..base import ToolContext, ToolResult

log = logging.getLogger(__name__)

_TIMEOUT_S = 120


@dataclass
class CompileCodeInput:
    source_dir: str             # Path to firmware source directory
    target: str = "esp32"       # MCU target
    toolchain: str = "auto"     # "auto", "platformio", "esp-idf", "cmake"


class CompileCodeTool:
    """Compiles firmware code and reports success/failure with error details.

    Detects the build system automatically:
      1. **PlatformIO** — ``platformio.ini`` present → ``pio run``
      2. **ESP-IDF** — ``sdkconfig`` or ``main/`` present → ``idf.py build``
      3. **CMake** — ``CMakeLists.txt`` present → ``cmake --build``

    Gracefully degrades when the required toolchain is not installed.
    """

    name = "compile_code"
    description = (
        "Compile firmware code for a target MCU and report success/failure "
        "with error details. Supports PlatformIO, ESP-IDF, and CMake. "
        'Input: {"source_dir": "/path/to/firmware", "target": "esp32"}'
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "source_dir": {"type": "string", "description": "Path to firmware source directory"},
            "target": {"type": "string", "description": "Target MCU (e.g. esp32, stm32)", "default": "esp32"},
            "toolchain": {"type": "string", "description": "Toolchain: auto, platformio, esp-idf, cmake", "default": "auto"},
        },
        "required": ["source_dir"],
    }

    async def execute(self, input: Any, context: ToolContext) -> ToolResult:
        # Accept dict or dataclass
        if isinstance(input, dict):
            source_dir = input.get("source_dir", "")
            target = input.get("target", "esp32")
            toolchain = input.get("toolchain", "auto")
        else:
            source_dir = getattr(input, "source_dir", "")
            target = getattr(input, "target", "esp32")
            toolchain = getattr(input, "toolchain", "auto")

        if not source_dir:
            return ToolResult(
                success=False, data=None, source="compile_code",
                confidence=0.0, error="No source_dir provided",
            )

        src = Path(source_dir)
        if not src.is_dir():
            return ToolResult(
                success=False, data=None, source="compile_code",
                confidence=0.0, error=f"Directory not found: {src}",
            )

        # Detect build system
        if toolchain == "auto":
            toolchain = self._detect_toolchain(src)

        if not toolchain:
            return ToolResult(
                success=False, data=None, source="compile_code",
                confidence=0.0,
                error=(
                    f"No build system detected in {src}. "
                    "Expected platformio.ini, CMakeLists.txt, or ESP-IDF project."
                ),
            )

        # Build command
        cmd = self._build_command(toolchain, src, target)
        if not cmd:
            return ToolResult(
                success=False, data=None, source="compile_code",
                confidence=0.0,
                error=f"Toolchain '{toolchain}' not found on PATH",
            )

        # Run compilation
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(src),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                data={"compiled": False, "output": f"Timeout after {_TIMEOUT_S}s"},
                source="compile_code",
                confidence=1.0, error=f"Compilation timed out (>{_TIMEOUT_S}s)",
            )
        except FileNotFoundError:
            return ToolResult(
                success=False, data=None, source="compile_code",
                confidence=0.0,
                error=f"Toolchain command not found: {cmd[0]}",
            )

        stdout = stdout_b.decode(errors="replace")
        stderr = stderr_b.decode(errors="replace")
        combined = stdout + "\n" + stderr

        errors = self._extract_errors(combined)
        warnings = self._extract_warnings(combined)
        compiled = proc.returncode == 0

        return ToolResult(
            success=compiled,
            data={
                "compiled": compiled,
                "return_code": proc.returncode,
                "errors": errors,
                "warnings": warnings,
                "error_count": len(errors),
                "warning_count": len(warnings),
                "output": combined[-3000:],  # last 3 KB of output
            },
            source=f"compile_code:{toolchain}",
            confidence=1.0,
            metadata={"toolchain": toolchain, "target": target, "source_dir": str(src)},
        )

    # ------------------------------------------------------------------
    # Detection & command building
    # ------------------------------------------------------------------

    def _detect_toolchain(self, src: Path) -> str:
        if (src / "platformio.ini").exists():
            return "platformio"
        if (src / "sdkconfig").exists() or (src / "main").is_dir():
            return "esp-idf"
        if (src / "CMakeLists.txt").exists():
            return "cmake"
        return ""

    def _build_command(self, toolchain: str, src: Path, target: str) -> list[str] | None:
        if toolchain == "platformio":
            if not shutil.which("pio"):
                return None
            cmd = ["pio", "run"]
            if target:
                cmd.extend(["-e", target])
            return cmd

        if toolchain == "esp-idf":
            if not shutil.which("idf.py"):
                return None
            return ["idf.py", "build"]

        if toolchain == "cmake":
            if not shutil.which("cmake"):
                return None
            build_dir = src / "build"
            if not build_dir.exists():
                # Configure first, then build
                return ["cmake", "-S", ".", "-B", "build", "--build", "build"]
            return ["cmake", "--build", "build"]

        return None

    # ------------------------------------------------------------------
    # Output parsing
    # ------------------------------------------------------------------

    def _extract_errors(self, output: str) -> list[str]:
        errors: list[str] = []
        for line in output.splitlines():
            if re.search(r"\berror[:\s]", line, re.IGNORECASE):
                clean = line.strip()
                if clean and len(clean) < 500:
                    errors.append(clean)
        return errors[:50]

    def _extract_warnings(self, output: str) -> list[str]:
        warnings: list[str] = []
        for line in output.splitlines():
            if re.search(r"\bwarning[:\s]", line, re.IGNORECASE):
                clean = line.strip()
                if clean and len(clean) < 500:
                    warnings.append(clean)
        return warnings[:50]
