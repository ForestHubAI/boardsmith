# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression tests for 5 synthesis bugs fixed in quick task 9.

Bugs:
  BUG1 - NXP keyword 'nxp' overriding 'i.mx' mapping to lpc55
  BUG2 - Crystal frequency ignores prompt for STM32F7 (always 8MHz)
  BUG3 - CAN transceiver modality missing (no TCAN1042VDRQ1 for CAN-FD prompts)
  BUG4 - Battery charger modality missing (no TP4056 for Li-Ion charge prompts)
  BUG5 - 1.8V voltage domain not synthesized when prompt mentions 1.8V

All tests run under BOARDSMITH_NO_LLM=1.
"""
from __future__ import annotations

import os
os.environ.setdefault("BOARDSMITH_NO_LLM", "1")

from knowledge import db as _kdb  # noqa: E402
_kdb.rebuild()

from boardsmith_hw.intent_parser import IntentParser  # noqa: E402
from boardsmith_hw.requirements_normalizer import normalize  # noqa: E402
from boardsmith_hw.component_selector import ComponentSelector  # noqa: E402
from boardsmith_hw.topology_synthesizer import synthesize_topology  # noqa: E402


def _parse(prompt: str):
    return IntentParser(use_llm=False).parse(prompt)


def _select(prompt: str):
    spec = _parse(prompt)
    reqs = normalize(spec)
    return ComponentSelector(seed=42, use_agent=False).select(reqs)


def _synthesize(prompt: str, supply_voltage_v: float = 12.0):
    sel = _select(prompt)
    return synthesize_topology(sel, supply_voltage_v=supply_voltage_v, raw_prompt=prompt)


# ---------------------------------------------------------------------------
# BUG1 — NXP keyword override: 'nxp' must not map NXP i.MX prompts to lpc55
# ---------------------------------------------------------------------------

def test_nxp_imxrt_not_lpc55():
    """NXP i.MX RT1062 prompt must map to family 'imxrt', not 'lpc55' (BUG1)."""
    spec = _parse("NXP i.MX RT1062 mit 600 MHz Cortex-M7 Industrie-Gateway")
    assert spec.mcu_family == "imxrt", (
        f"Expected 'imxrt', got '{spec.mcu_family}' — "
        f"'nxp' keyword must not override 'i.mx'"
    )


def test_lpc_keyword_maps_to_lpc55():
    """'lpc' keyword must still map to lpc55 family (regression guard for BUG1 fix)."""
    spec = _parse("NXP LPC55S69 microcontroller board")
    assert spec.mcu_family == "lpc55", (
        f"Expected 'lpc55', got '{spec.mcu_family}'"
    )


# ---------------------------------------------------------------------------
# BUG2 — Crystal frequency: STM32F7 + '12MHz Crystal' in prompt must use 12 MHz
# ---------------------------------------------------------------------------

def test_crystal_12mhz_from_prompt():
    """STM32F746 + '12MHz Crystal' in prompt must synthesize 12 MHz crystal, not 8 MHz (BUG2)."""
    topo = _synthesize(
        "STM32F746 Board mit externem 12MHz Crystal, WM8731 Codec, getrennten Analog/Digital Supplies",
        supply_voltage_v=5.0,
    )
    crystals = [p for p in topo.passives if p.category == "crystal"]
    assert len(crystals) >= 1, "STM32F7 must synthesize at least one crystal oscillator"
    crystal = crystals[0]
    assert "12" in crystal.value, (
        f"Expected crystal value to contain '12', got '{crystal.value}' — "
        f"prompt-specified 12MHz must override 8MHz default"
    )


def test_crystal_default_8mhz_without_prompt():
    """STM32F746 without MHz hint in prompt must default to 8 MHz crystal (BUG2 regression)."""
    topo = _synthesize(
        "STM32F746 Board mit I2C Sensor",
        supply_voltage_v=5.0,
    )
    crystals = [p for p in topo.passives if p.category == "crystal"]
    assert len(crystals) >= 1, "STM32F7 must synthesize at least one crystal oscillator"
    crystal = crystals[0]
    assert "8" in crystal.value, (
        f"Expected 8MHz default crystal, got '{crystal.value}'"
    )


# ---------------------------------------------------------------------------
# BUG3 — CAN transceiver modality: CAN-FD prompt must select TCAN1042VDRQ1
# ---------------------------------------------------------------------------

def test_can_transceiver_modality_intent():
    """'CAN-FD transceiver' in prompt must set 'can' sensing modality (BUG3)."""
    spec = _parse("STM32F746 Board mit USB Device und CAN-FD transceiver, inklusive 120Ω Terminierung")
    assert "can" in spec.sensing_modalities, (
        f"Expected 'can' in sensing_modalities, got: {spec.sensing_modalities}"
    )


def test_can_transceiver_selects_tcan1042():
    """'can' sensing modality must select TCAN1042VDRQ1 component (BUG3)."""
    sel = _select("STM32F746 Board mit CAN-FD transceiver")
    mpns = [s.mpn for s in sel.sensors]
    assert "TCAN1042VDRQ1" in mpns, (
        f"Expected TCAN1042VDRQ1 in selected sensors, got: {mpns}"
    )


# ---------------------------------------------------------------------------
# BUG4 — Battery charger modality: Li-Ion charge prompt must select TP4056
# ---------------------------------------------------------------------------

def test_battery_charger_modality_intent():
    """'Li-Ion Ladefunktion' in prompt must set 'battery_charger' sensing modality (BUG4)."""
    spec = _parse("ESP32-S3 Board mit Li-Ion Ladefunktion (USB-C), Power-Path Management")
    assert "battery_charger" in spec.sensing_modalities, (
        f"Expected 'battery_charger' in sensing_modalities, got: {spec.sensing_modalities}"
    )


def test_battery_charger_selects_tp4056():
    """'battery_charger' sensing modality must select TP4056 component (BUG4)."""
    sel = _select("ESP32 Board mit battery charger und USB Eingang")
    mpns = [s.mpn for s in sel.sensors]
    assert "TP4056" in mpns, (
        f"Expected TP4056 in selected sensors, got: {mpns}"
    )


# ---------------------------------------------------------------------------
# BUG5 — 1.8V domain: prompt mentioning 1.8V must add MCP1700-1802E LDO
# ---------------------------------------------------------------------------

def test_1v8_domain_added():
    """Prompt with '1.8V' must add MCP1700-1802E LDO with output_rail='1V8_REG' (BUG5)."""
    topo = _synthesize(
        "ESP32 Board mit 3 verschiedenen Spannungsdomänen (5V, 3.3V, 1.8V), Level Shiftern",
        supply_voltage_v=12.0,
    )
    reg_rails = [r.output_rail for r in topo.voltage_regulators]
    reg_mpns = [r.mpn for r in topo.voltage_regulators]
    assert "1V8_REG" in reg_rails, (
        f"Expected '1V8_REG' in voltage_regulator output rails, got: {reg_rails}"
    )
    assert any("MCP1700" in mpn for mpn in reg_mpns), (
        f"Expected MCP1700-1802E in voltage_regulators, got: {reg_mpns}"
    )


def test_1v8_not_added_without_mention():
    """Prompt without '1.8V' must NOT add 1V8_REG rail (BUG5 regression guard)."""
    topo = _synthesize(
        "ESP32 Board mit 5V und 3.3V Versorgung, I2C Sensor",
        supply_voltage_v=12.0,
    )
    reg_rails = [r.output_rail for r in topo.voltage_regulators]
    assert "1V8_REG" not in reg_rails, (
        f"Expected no '1V8_REG' without 1.8V prompt, got: {reg_rails}"
    )


# ---------------------------------------------------------------------------
# BUG6 — Fuel gauge modality: 'Fuel Gauge' in prompt must select MAX17043
# ---------------------------------------------------------------------------

def test_fuel_gauge_modality_intent():
    """'Fuel Gauge' in prompt must set 'fuel_gauge' sensing modality (BUG6)."""
    spec = _parse(
        "ESP32-S3 Board mit Li-Ion Ladefunktion (USB-C), Power-Path Management, "
        "Fuel Gauge und Deep-Sleep Stromoptimierung."
    )
    assert "fuel_gauge" in spec.sensing_modalities, (
        f"Expected 'fuel_gauge' in sensing_modalities, got: {spec.sensing_modalities}"
    )


def test_fuel_gauge_selects_max17043():
    """'fuel_gauge' sensing modality must select MAX17043 component (BUG6)."""
    sel = _select(
        "ESP32 Board mit battery charger, fuel gauge und Deep-Sleep Modus"
    )
    mpns = [s.mpn for s in sel.sensors]
    assert "MAX17043" in mpns, (
        f"Expected MAX17043 in selected sensors, got: {mpns}"
    )


def test_fuel_gauge_and_charger_coexist():
    """Both TP4056 (charger) and MAX17043 (fuel gauge) must appear together (BUG6)."""
    sel = _select(
        "ESP32-S3 Board mit Li-Ion Ladefunktion (USB-C), "
        "Fuel Gauge und Deep-Sleep Stromoptimierung."
    )
    mpns = [s.mpn for s in sel.sensors]
    assert "TP4056" in mpns, f"Expected TP4056 in sensors, got: {mpns}"
    assert "MAX17043" in mpns, f"Expected MAX17043 in sensors, got: {mpns}"


def test_fuel_gauge_keywords_max17043_mpn():
    """'max17043' MPN in prompt must trigger fuel_gauge modality (BUG6)."""
    spec = _parse("ESP32 Battery Board mit max17043 Fuel Gauge IC")
    assert "fuel_gauge" in spec.sensing_modalities, (
        f"Expected 'fuel_gauge' in sensing_modalities, got: {spec.sensing_modalities}"
    )
