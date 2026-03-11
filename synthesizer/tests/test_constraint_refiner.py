# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Boardsmith constraint refiner (I2C conflict resolution, I2C-Mux)."""
from __future__ import annotations

import pytest
from boardsmith_hw.intent_parser import IntentParser
from boardsmith_hw.requirements_normalizer import normalize
from boardsmith_hw.component_selector import ComponentSelector, SelectedComponent
from boardsmith_hw.topology_synthesizer import synthesize_topology
from boardsmith_hw.hir_composer import compose_hir
from boardsmith_hw.constraint_refiner import ConstraintRefiner
from synth_core.api.compiler import list_components


def _make_conflicting_topology():
    """Build a topology with two VL53L0X sensors (same fixed address 0x29)."""
    spec = IntentParser(use_llm=False).parse("ESP32")
    req = normalize(spec)
    sel = ComponentSelector(seed=42).select(req)
    vl_raw = next(c for c in list_components() if c.get("mpn") == "VL53L0X")
    sc1 = SelectedComponent(
        mpn="VL53L0X", manufacturer="ST", name="VL53L0X Unit1", category="sensor",
        interface_types=["I2C"], role="distance", known_i2c_addresses=["0x29"],
        init_contract_coverage=True, unit_cost_usd=4.5, score=0.9, raw=vl_raw,
    )
    sc2 = SelectedComponent(
        mpn="VL53L0X-2", manufacturer="ST", name="VL53L0X Unit2", category="sensor",
        interface_types=["I2C"], role="distance", known_i2c_addresses=["0x29"],
        init_contract_coverage=True, unit_cost_usd=4.5, score=0.9,
        raw=dict(vl_raw, mpn="VL53L0X-2", known_i2c_addresses=["0x29"]),
    )
    sel.sensors = [sc1, sc2]
    topo = synthesize_topology(sel)
    return compose_hir(topo)


def _refine(hir, max_iterations: int = 3) -> dict:
    return ConstraintRefiner(max_iterations=max_iterations).refine(hir).hir


# --- Alternate-address resolution (existing logic) ---

def test_i2c_conflict_resolved_by_alternate_address():
    """BME280 (0x76/0x77) + AHT20 (0x38): no conflict, both should pass without mux."""
    spec = IntentParser(use_llm=False).parse("ESP32 with BME280 and AHT20")
    req = normalize(spec)
    sel = ComponentSelector(seed=42).select(req)
    topo = synthesize_topology(sel)
    hir = compose_hir(topo)
    result = ConstraintRefiner(max_iterations=3).refine(hir)
    conflict_fails = [c for c in result.report.constraints
                      if "conflict" in c.id and c.status.value == "fail"]
    assert len(conflict_fails) == 0, "BME280+AHT20 should have no I2C conflict"


# --- TCA9548A I2C-Mux insertion ---

def test_mux_inserted_for_unresolvable_conflict():
    """Two VL53L0X (fixed 0x29) → TCA9548A must be auto-inserted."""
    hir_dict = _refine(_make_conflicting_topology())
    mux = [c for c in hir_dict.get("components", []) if c.get("mpn") == "TCA9548A"]
    assert len(mux) == 1, "TCA9548A must be inserted as a component"


def test_mux_in_bom():
    """TCA9548A must appear in the BOM after mux insertion."""
    hir_dict = _refine(_make_conflicting_topology())
    bom_mpns = [e.get("mpn") for e in hir_dict.get("bom", [])]
    assert "TCA9548A" in bom_mpns


def test_mux_sub_buses_created():
    """Each conflicting slave must get its own sub-bus routed through the mux."""
    hir_dict = _refine(_make_conflicting_topology())
    sub_buses = [b for b in hir_dict.get("buses", []) if "mux_ch" in b.get("name", "")]
    assert len(sub_buses) == 2, "Two conflicting slaves → two sub-buses"


def test_mux_sub_bus_master_is_tca9548a():
    """Sub-buses must have TCA9548A as master, not the MCU."""
    hir_dict = _refine(_make_conflicting_topology())
    sub_buses = [b for b in hir_dict.get("buses", []) if "mux_ch" in b.get("name", "")]
    for bus in sub_buses:
        assert bus.get("master_component_id") == "TCA9548A_MUX1"


def test_mux_sub_bus_addresses_preserved():
    """Original I2C addresses (0x29) must be preserved in the sub-bus contracts."""
    hir_dict = _refine(_make_conflicting_topology())
    sub_bus_contracts = [
        bc for bc in hir_dict.get("bus_contracts", [])
        if "mux_ch" in bc.get("bus_name", "")
    ]
    for bc in sub_bus_contracts:
        for addr in bc.get("slave_addresses", {}).values():
            assert addr == "0x29", f"Expected 0x29 in sub-bus, got {addr}"


def test_conflicting_slaves_removed_from_main_bus():
    """After mux insertion, only TCA9548A should be slave on the main bus."""
    hir_dict = _refine(_make_conflicting_topology())
    main_bc = next(
        (bc for bc in hir_dict.get("bus_contracts", []) if bc.get("bus_name") == "i2c0"),
        {},
    )
    addrs = main_bc.get("slave_addresses", {})
    assert "TCA9548A_MUX1" in addrs, "TCA9548A must be slave on main bus"
    assert "VL53L0X" not in addrs, "VL53L0X must be moved to sub-bus"
    assert "VL53L0X_2" not in addrs, "VL53L0X_2 must be moved to sub-bus"


def test_conflict_marked_as_resolved():
    """i2c_addr.i2c0.conflict must appear in the resolved list."""
    hir = _make_conflicting_topology()
    result = ConstraintRefiner(max_iterations=3).refine(hir)
    assert "i2c_addr.i2c0.conflict" in result.resolved
