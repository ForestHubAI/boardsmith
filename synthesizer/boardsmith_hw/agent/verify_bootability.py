# SPDX-License-Identifier: AGPL-3.0-or-later
"""VerifyBootabilityTool — MCU boot-readiness semantic verification.

Checks: reset circuit, SWD/UART programming interface, crystal/oscillator.
Runs without LLM — BOARDSMITH_NO_LLM=1 safe.
All heavy imports are lazy (inside execute() body only).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# MCU family detection helpers — pure string logic, no heavy imports
# ---------------------------------------------------------------------------

_ESP_PATTERNS = ("ESP32", "ESP8266")
_STM_PATTERNS = ("STM32",)
_AVR_PATTERNS = ("ATMEGA", "ATTINY")
_RP_PATTERNS = ("RP2040",)

_RESET_KEYWORDS = ("NRST", "RESET", "RST", "EN")


def _detect_mcu_family(mpn: str) -> str:
    """Return MCU family string: 'esp', 'stm32', 'avr', 'rp2040', or 'generic'."""
    upper = mpn.upper()
    for pat in _ESP_PATTERNS:
        if pat in upper:
            return "esp"
    for pat in _STM_PATTERNS:
        if pat in upper:
            return "stm32"
    for pat in _AVR_PATTERNS:
        if pat in upper:
            return "avr"
    for pat in _RP_PATTERNS:
        if pat in upper:
            return "rp2040"
    return "generic"


# ---------------------------------------------------------------------------
# Rule check functions
# ---------------------------------------------------------------------------

def _check_reset(mcu_comp: Any, graph: Any) -> list[dict]:
    """Check for reset circuit net (NRST/RESET/RST/EN)."""
    net_names_upper = [net.name.upper() for net in graph.nets]
    for keyword in _RESET_KEYWORDS:
        if any(keyword in name for name in net_names_upper):
            return []
    return [
        {
            "type": "missing_reset_circuit",
            "severity": "warning",
            "message": (
                f"No reset net (NRST/RESET/RST/EN) found for MCU {mcu_comp.id}"
            ),
            "ref": mcu_comp.id,
        }
    ]


def _check_programming_interface(mcu_comp: Any, graph: Any, family: str) -> list[dict]:
    """Check for programming/debug interface nets."""
    net_names_upper = [net.name.upper() for net in graph.nets]

    if family == "stm32":
        has_swdio = any("SWDIO" in name for name in net_names_upper)
        has_swdclk = any("SWDCLK" in name for name in net_names_upper)
        if not (has_swdio and has_swdclk):
            return [
                {
                    "type": "missing_programming_interface",
                    "severity": "warning",
                    "message": (
                        "STM32 SWD interface: missing SWDIO and/or SWDCLK nets"
                    ),
                    "ref": mcu_comp.id,
                }
            ]
        return []

    if family == "esp":
        has_uart = any(
            kw in name for name in net_names_upper for kw in ("TX", "RX")
        )
        has_swd = any(
            kw in name for name in net_names_upper for kw in ("SWDIO", "SWDCLK")
        )
        if not (has_uart or has_swd):
            return [
                {
                    "type": "missing_programming_interface",
                    "severity": "warning",
                    "message": (
                        f"ESP MCU {mcu_comp.id}: no UART (TX/RX) or SWD interface nets found"
                    ),
                    "ref": mcu_comp.id,
                }
            ]
        return []

    # Generic / AVR / RP2040: check for any connector (J prefix) or TX/RX net
    has_connector = any(
        gc.id.upper().startswith("J") for gc in graph.components
    )
    has_uart = any(
        any(kw in name for kw in ("TX", "RX")) for name in net_names_upper
    )
    if not (has_connector or has_uart):
        return [
            {
                "type": "missing_programming_interface",
                "severity": "warning",
                "message": (
                    f"MCU {mcu_comp.id}: no programming connector (J*) or UART (TX/RX) nets found"
                ),
                "ref": mcu_comp.id,
            }
        ]
    return []


def _check_clock(mcu_comp: Any, graph: Any, family: str) -> list[dict]:
    """Check for crystal/oscillator (skipped for ESP which has internal oscillator)."""
    if family == "esp":
        # ESP32/ESP8266 have internal oscillator — crystal check is not applicable
        return []

    # For STM32, AVR, RP2040, and generic MCUs, check for crystal load caps or MHz component
    for gc in graph.components:
        combined = (gc.name + gc.mpn).lower()
        # pF-value load caps (crystal load capacitors: 12pF, 18pF, 22pF)
        if "pf" in combined or "µf" in combined:
            return []
        # MHz-valued crystal
        if "mhz" in combined:
            return []
        # KiCad shorthand: 12p, 18p, 22p (picofarad without F suffix)
        import re
        if re.search(r"\d+p\b", combined):
            return []

    return [
        {
            "type": "missing_crystal_load_caps",
            "severity": "warning",
            "message": (
                f"No crystal or load capacitors found for MCU {mcu_comp.id}"
            ),
            "ref": mcu_comp.id,
        }
    ]


# ---------------------------------------------------------------------------
# Tool class
# ---------------------------------------------------------------------------

class VerifyBootabilityTool:
    """LLM-callable tool that checks MCU boot-readiness in a schematic.

    Verifies: reset circuit, programming interface (SWD/UART), clock source.
    ESP32 is exempt from crystal check (has internal oscillator).
    Returns empty violations when no MCU is present in HIR.
    All imports inside execute() — BOARDSMITH_NO_LLM=1 safe.
    """

    name = "verify_bootability"
    description = (
        "Verify MCU boot-readiness: reset circuit, programming interface (SWD/UART), "
        "and clock source. ESP32 skips crystal check (internal oscillator). "
        "Returns empty violations when no MCU is present in the HIR."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "hir_path": {
                "type": "string",
                "description": "Absolute path to hir.json",
            },
            "sch_path": {
                "type": "string",
                "description": "Absolute path to .kicad_sch file",
            },
        },
        "required": ["hir_path", "sch_path"],
    }

    async def execute(self, input: Any, context: Any) -> Any:  # noqa: A002
        from tools.base import ToolResult  # lazy — BOARDSMITH_NO_LLM=1 safe
        from synth_core.hir_bridge.kicad_parser import KiCadSchematicParser
        from models.hir import HIR
        import json

        hir_path = Path(input["hir_path"])
        if not hir_path.exists():
            return ToolResult(
                success=False,
                data={"violations": []},
                source="verify_bootability",
                confidence=0.0,
                error=f"hir.json not found: {hir_path}",
            )

        hir = HIR.model_validate(json.loads(hir_path.read_text()))
        mcu_comps = [c for c in hir.components if c.role == "mcu"]

        if not mcu_comps:
            return ToolResult(
                success=True,
                data={"violations": [], "violation_count": 0, "checks_run": []},
                source="verify_bootability",
                confidence=1.0,
            )

        graph = KiCadSchematicParser().parse(Path(input["sch_path"]))

        violations: list[dict] = []
        for mcu in mcu_comps:
            family = _detect_mcu_family(mcu.mpn)
            violations += _check_reset(mcu, graph)
            violations += _check_programming_interface(mcu, graph, family)
            violations += _check_clock(mcu, graph, family)

        return ToolResult(
            success=True,
            data={
                "violations": violations,
                "violation_count": len(violations),
                "checks_run": ["reset", "programming_interface", "clock"],
            },
            source="verify_bootability",
            confidence=1.0,
            metadata={"mcu_count": len(mcu_comps)},
        )
