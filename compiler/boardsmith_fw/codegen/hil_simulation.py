# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hardware-in-the-Loop Simulation — QEMU/Renode integration.

Generates simulation configurations for running firmware in emulated
hardware environments without physical boards.

Supports:
  - QEMU: ESP32, STM32 (Cortex-M), RP2040 (Cortex-M0+)
  - Renode: ESP32, STM32, nRF52 with peripheral models
  - Test harness: automated firmware verification in simulation

Usage:
    from boardsmith_fw.codegen.hil_simulation import generate_hil
    result = generate_hil(target="esp32", firmware_elf="build/app.elf")
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class HILSimulationResult:
    files: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class HILConfig:
    firmware_elf: str = "build/firmware.elf"
    timeout_s: int = 10
    uart_log: bool = True
    gdb_port: int = 3333
    peripherals: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_hil(
    target: str = "esp32",
    config: HILConfig | None = None,
) -> HILSimulationResult:
    """Generate HIL simulation configuration for the given target."""
    if config is None:
        config = HILConfig()

    result = HILSimulationResult()

    if target in ("esp32", "esp32c3"):
        _gen_esp32_hil(target, config, result)
    elif target == "stm32":
        _gen_stm32_hil(config, result)
    elif target == "rp2040":
        _gen_rp2040_hil(config, result)
    elif target == "nrf52":
        _gen_nrf52_hil(config, result)
    else:
        result.warnings.append(f"Unknown target '{target}', defaulting to esp32")
        _gen_esp32_hil("esp32", config, result)

    # Common: test runner script
    result.files.append(("hil/run_tests.py", _gen_test_runner(target, config)))
    result.files.append(("hil/conftest.py", _gen_conftest(target, config)))
    result.files.append(("hil/README.md", _gen_hil_readme(target)))

    return result


# ---------------------------------------------------------------------------
# ESP32 — QEMU + Renode
# ---------------------------------------------------------------------------


def _gen_esp32_hil(
    target: str,
    config: HILConfig,
    result: HILSimulationResult,
) -> None:
    arch = "riscv32" if target == "esp32c3" else "xtensa"
    qemu_machine = "esp32c3" if target == "esp32c3" else "esp32"

    # QEMU launch script
    qemu_script = f"""\
#!/bin/bash
# boardsmith-fw HIL — QEMU {target} simulation
set -e

FIRMWARE="${{1:-{config.firmware_elf}}}"
TIMEOUT={config.timeout_s}

echo "=== boardsmith-fw HIL: QEMU {target} ==="
echo "Firmware: $FIRMWARE"
echo "Timeout:  ${{TIMEOUT}}s"

# Launch QEMU with {target}
qemu-system-{arch} \\
    -machine {qemu_machine} \\
    -nographic \\
    -no-reboot \\
    -drive file=$FIRMWARE,if=mtd,format=raw \\
    -serial mon:stdio \\
    {f'-gdb tcp::{config.gdb_port} -S' if config.gdb_port else ''} \\
    -d guest_errors \\
    | timeout $TIMEOUT tee hil/uart_output.log

echo "=== Simulation complete ==="
"""
    result.files.append(("hil/qemu_run.sh", qemu_script))

    # Renode platform file
    renode_repl = f"""\
// boardsmith-fw HIL — Renode {target} platform
// Auto-generated — do not edit

using "platforms/cpus/{qemu_machine}.repl"

// UART0 — serial output
uart0: UART.ESP32_UART @ sysbus 0x60000000
    -> cpu@0

// I2C0 — sensor bus
i2c0: I2C.ESP32_I2C @ sysbus 0x60013000
"""

    for periph in config.peripherals:
        if periph.upper() == "BME280":
            renode_repl += """\

// BME280 temperature/pressure/humidity sensor
bme280: Sensors.BME280 @ i2c0 0x76
    temperature: 22.5
    pressure: 1013.25
    humidity: 45.0
"""
        elif periph.upper() == "SSD1306":
            renode_repl += """\

// SSD1306 OLED display (128x64)
ssd1306: Video.SSD1306 @ i2c0 0x3C
"""

    result.files.append(("hil/platform.repl", renode_repl))

    # Renode script
    renode_resc = f"""\
# boardsmith-fw HIL — Renode {target} script
# Run with: renode hil/simulation.resc

mach create "{target}"
machine LoadPlatformDescription @hil/platform.repl

sysbus LoadELF @{config.firmware_elf}

# UART logging
showAnalyzer uart0
logFile @hil/renode_uart.log

# Emulate for {config.timeout_s} seconds then quit
emulation RunFor "{config.timeout_s}"
quit
"""
    result.files.append(("hil/simulation.resc", renode_resc))


# ---------------------------------------------------------------------------
# STM32 — QEMU (Cortex-M) + Renode
# ---------------------------------------------------------------------------


def _gen_stm32_hil(
    config: HILConfig,
    result: HILSimulationResult,
) -> None:
    # QEMU launch script for STM32F4
    qemu_script = f"""\
#!/bin/bash
# boardsmith-fw HIL — QEMU STM32 (Cortex-M4) simulation
set -e

FIRMWARE="${{1:-{config.firmware_elf}}}"
TIMEOUT={config.timeout_s}

echo "=== boardsmith-fw HIL: QEMU STM32 ==="
echo "Firmware: $FIRMWARE"

qemu-system-arm \\
    -machine netduinoplus2 \\
    -cpu cortex-m4 \\
    -nographic \\
    -no-reboot \\
    -kernel $FIRMWARE \\
    -serial mon:stdio \\
    {f'-gdb tcp::{config.gdb_port}' if config.gdb_port else ''} \\
    -d guest_errors \\
    | timeout $TIMEOUT tee hil/uart_output.log

echo "=== Simulation complete ==="
"""
    result.files.append(("hil/qemu_run.sh", qemu_script))

    # Renode platform for STM32F407
    renode_repl = """\
// boardsmith-fw HIL — Renode STM32F407 platform

using "platforms/cpus/stm32f4.repl"

// Override UART for logging
usart2: UART.STM32_UART @ sysbus 0x40004400
    -> nvic@38

// I2C1 — sensor bus
i2c1: I2C.STM32F4_I2C @ sysbus 0x40005400
    -> nvic@31
"""

    for periph in config.peripherals:
        if periph.upper() == "BME280":
            renode_repl += """\

bme280: Sensors.BME280 @ i2c1 0x76
    temperature: 22.5
    pressure: 1013.25
    humidity: 45.0
"""

    result.files.append(("hil/platform.repl", renode_repl))

    renode_resc = f"""\
# boardsmith-fw HIL — Renode STM32F407 script

mach create "stm32"
machine LoadPlatformDescription @hil/platform.repl

sysbus LoadELF @{config.firmware_elf}

showAnalyzer usart2
logFile @hil/renode_uart.log

emulation RunFor "{config.timeout_s}"
quit
"""
    result.files.append(("hil/simulation.resc", renode_resc))


# ---------------------------------------------------------------------------
# RP2040 — QEMU (Cortex-M0+) + Renode
# ---------------------------------------------------------------------------


def _gen_rp2040_hil(
    config: HILConfig,
    result: HILSimulationResult,
) -> None:
    qemu_script = f"""\
#!/bin/bash
# boardsmith-fw HIL — QEMU RP2040 (Cortex-M0+) simulation
set -e

FIRMWARE="${{1:-{config.firmware_elf}}}"
TIMEOUT={config.timeout_s}

echo "=== boardsmith-fw HIL: QEMU RP2040 ==="
echo "Firmware: $FIRMWARE"

qemu-system-arm \\
    -machine raspi-pico \\
    -cpu cortex-m0 \\
    -nographic \\
    -no-reboot \\
    -kernel $FIRMWARE \\
    -serial mon:stdio \\
    {f'-gdb tcp::{config.gdb_port}' if config.gdb_port else ''} \\
    -d guest_errors \\
    | timeout $TIMEOUT tee hil/uart_output.log

echo "=== Simulation complete ==="
"""
    result.files.append(("hil/qemu_run.sh", qemu_script))

    renode_repl = """\
// boardsmith-fw HIL — Renode RP2040 platform

using "platforms/cpus/rp2040.repl"

uart0: UART.PL011 @ sysbus 0x40034000
    -> nvic@20

i2c0: I2C.RP2040_I2C @ sysbus 0x40044000
"""

    for periph in config.peripherals:
        if periph.upper() == "BME280":
            renode_repl += """\

bme280: Sensors.BME280 @ i2c0 0x76
    temperature: 22.5
    pressure: 1013.25
    humidity: 45.0
"""

    result.files.append(("hil/platform.repl", renode_repl))

    renode_resc = f"""\
# boardsmith-fw HIL — Renode RP2040 script

mach create "rp2040"
machine LoadPlatformDescription @hil/platform.repl

sysbus LoadELF @{config.firmware_elf}

showAnalyzer uart0
logFile @hil/renode_uart.log

emulation RunFor "{config.timeout_s}"
quit
"""
    result.files.append(("hil/simulation.resc", renode_resc))


# ---------------------------------------------------------------------------
# nRF52 — Renode (native Zephyr support)
# ---------------------------------------------------------------------------


def _gen_nrf52_hil(
    config: HILConfig,
    result: HILSimulationResult,
) -> None:
    # nRF52 is best supported by Renode (no good QEMU machine)
    result.warnings.append(
        "nRF52 HIL uses Renode only (QEMU support limited for nRF52)"
    )

    qemu_script = f"""\
#!/bin/bash
# boardsmith-fw HIL — nRF52 simulation (Renode)
# Note: nRF52 is best supported by Renode, not QEMU
set -e

FIRMWARE="${{1:-{config.firmware_elf}}}"
TIMEOUT={config.timeout_s}

echo "=== boardsmith-fw HIL: Renode nRF52840 ==="
echo "Firmware: $FIRMWARE"

renode --disable-xwt --console \\
    -e "include @hil/simulation.resc" \\
    2>&1 | timeout $TIMEOUT tee hil/uart_output.log

echo "=== Simulation complete ==="
"""
    result.files.append(("hil/qemu_run.sh", qemu_script))

    renode_repl = """\
// boardsmith-fw HIL — Renode nRF52840 platform

using "platforms/cpus/nrf52840.repl"

// UART0 — Zephyr console
uart0: UART.nRF52840_UART @ sysbus 0x40002000
    -> nvic@2

// TWI0 (I2C) — sensor bus
twi0: I2C.nRF52840_TWI @ sysbus 0x40003000
    -> nvic@3
"""

    for periph in config.peripherals:
        if periph.upper() == "BME280":
            renode_repl += """\

bme280: Sensors.BME280 @ twi0 0x76
    temperature: 22.5
    pressure: 1013.25
    humidity: 45.0
"""

    result.files.append(("hil/platform.repl", renode_repl))

    renode_resc = f"""\
# boardsmith-fw HIL — Renode nRF52840 script (Zephyr)

mach create "nrf52840"
machine LoadPlatformDescription @hil/platform.repl

sysbus LoadELF @{config.firmware_elf}

showAnalyzer uart0
logFile @hil/renode_uart.log

emulation RunFor "{config.timeout_s}"
quit
"""
    result.files.append(("hil/simulation.resc", renode_resc))


# ---------------------------------------------------------------------------
# Test Runner — pytest-based HIL test harness
# ---------------------------------------------------------------------------


def _gen_test_runner(target: str, config: HILConfig) -> str:
    return f"""\
#!/usr/bin/env python3
\"\"\"boardsmith-fw HIL Test Runner — automated firmware verification in simulation.

Runs firmware in QEMU/Renode and validates UART output against expected patterns.

Usage:
    python hil/run_tests.py [--firmware build/firmware.elf] [--timeout 10]
\"\"\"

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path


def run_simulation(
    firmware: str = "{config.firmware_elf}",
    timeout: int = {config.timeout_s},
    target: str = "{target}",
) -> str:
    \"\"\"Run firmware in simulation and capture UART output.\"\"\"
    script = Path(__file__).parent / "qemu_run.sh"
    if not script.exists():
        print(f"ERROR: {{script}} not found", file=sys.stderr)
        sys.exit(1)

    try:
        result = subprocess.run(
            ["bash", str(script), firmware],
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        print(f"WARN: Simulation timed out after {{timeout}}s")
        # Read captured output so far
        log = Path(__file__).parent / "uart_output.log"
        if log.exists():
            return log.read_text()
        return ""


def check_boot(output: str) -> bool:
    \"\"\"Verify firmware boots successfully.\"\"\"
    boot_patterns = [
        r"app_main",
        r"init.*done",
        r"starting",
        r"ready",
        r"boot.*complete",
    ]
    for pattern in boot_patterns:
        if re.search(pattern, output, re.IGNORECASE):
            return True
    return False


def check_no_crash(output: str) -> bool:
    \"\"\"Verify no crash/panic in output.\"\"\"
    crash_patterns = [
        r"panic",
        r"abort",
        r"fault",
        r"stack overflow",
        r"guru meditation",
        r"hardfault",
        r"bus error",
    ]
    for pattern in crash_patterns:
        if re.search(pattern, output, re.IGNORECASE):
            return False
    return True


def check_i2c_init(output: str) -> bool:
    \"\"\"Verify I2C bus initialization.\"\"\"
    return bool(re.search(r"i2c.*init|I2C.*config", output, re.IGNORECASE))


def check_sensor_read(output: str) -> bool:
    \"\"\"Verify sensor data is being read.\"\"\"
    return bool(re.search(
        r"temp|humidity|pressure|sensor.*read",
        output,
        re.IGNORECASE,
    ))


def main() -> None:
    parser = argparse.ArgumentParser(description="boardsmith-fw HIL test runner")
    parser.add_argument(
        "--firmware", default="{config.firmware_elf}",
        help="Path to firmware ELF",
    )
    parser.add_argument(
        "--timeout", type=int, default={config.timeout_s},
        help="Simulation timeout (seconds)",
    )
    args = parser.parse_args()

    print(f"\\n=== boardsmith-fw HIL Tests ({target}) ===\\n")

    output = run_simulation(args.firmware, args.timeout)
    if not output.strip():
        print("ERROR: No UART output captured")
        sys.exit(1)

    tests = [
        ("Boot check", check_boot),
        ("No crash/panic", check_no_crash),
        ("I2C initialization", check_i2c_init),
        ("Sensor data read", check_sensor_read),
    ]

    passed = 0
    failed = 0

    for name, check_fn in tests:
        result = check_fn(output)
        status = "PASS" if result else "FAIL"
        symbol = "+" if result else "-"
        print(f"  [{{symbol}}] {{name}}: {{status}}")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\\n  Results: {{passed}} passed, {{failed}} failed\\n")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
"""


# ---------------------------------------------------------------------------
# conftest.py — pytest fixtures for HIL tests
# ---------------------------------------------------------------------------


def _gen_conftest(target: str, config: HILConfig) -> str:
    return f"""\
\"\"\"Pytest fixtures for boardsmith-fw HIL tests.\"\"\"

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def simulation_output():
    \"\"\"Run simulation once and share output across tests.\"\"\"
    script = Path(__file__).parent / "qemu_run.sh"
    if not script.exists():
        pytest.skip("HIL scripts not generated")

    try:
        result = subprocess.run(
            ["bash", str(script), "{config.firmware_elf}"],
            capture_output=True,
            text=True,
            timeout={config.timeout_s} + 5,
        )
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pytest.skip("Simulation environment not available")


@pytest.fixture
def target():
    \"\"\"Current simulation target.\"\"\"
    return "{target}"
"""


# ---------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------


def _gen_hil_readme(target: str) -> str:
    lines = [
        "# Hardware-in-the-Loop Simulation",
        "",
        f"Target: **{target}**",
        "",
        "## Prerequisites",
        "",
    ]

    if target in ("esp32", "esp32c3"):
        lines += [
            "### QEMU (ESP32)",
            "```bash",
            "# Install QEMU with ESP32 support",
            "git clone https://github.com/espressif/qemu.git",
            "cd qemu && ./configure --target-list=xtensa-softmmu && make",
            "```",
            "",
        ]
    elif target in ("stm32", "rp2040"):
        lines += [
            "### QEMU (ARM)",
            "```bash",
            "sudo apt install qemu-system-arm",
            "```",
            "",
        ]

    lines += [
        "### Renode",
        "```bash",
        "# Install Renode",
        "wget https://github.com/renode/renode/releases/latest -O renode.deb",
        "sudo dpkg -i renode.deb",
        "```",
        "",
        "## Running",
        "",
        "### Quick simulation",
        "```bash",
        "bash hil/qemu_run.sh build/firmware.elf",
        "```",
        "",
        "### Renode simulation",
        "```bash",
        "renode hil/simulation.resc",
        "```",
        "",
        "### Automated tests",
        "```bash",
        "python hil/run_tests.py --firmware build/firmware.elf",
        "```",
        "",
        "### Pytest integration",
        "```bash",
        "pytest hil/ -v",
        "```",
        "",
        "## Files",
        "",
        "| File | Description |",
        "|------|-------------|",
        "| `qemu_run.sh` | QEMU launch script |",
        "| `platform.repl` | Renode platform definition |",
        "| `simulation.resc` | Renode simulation script |",
        "| `run_tests.py` | Automated test runner |",
        "| `conftest.py` | Pytest fixtures |",
        "",
    ]

    return "\n".join(lines)
