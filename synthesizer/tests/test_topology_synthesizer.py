# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Boardsmith topology synthesizer."""
import pytest
from boardsmith_hw.intent_parser import IntentParser
from boardsmith_hw.requirements_normalizer import normalize
from boardsmith_hw.component_selector import ComponentSelector
from boardsmith_hw.topology_synthesizer import synthesize_topology, _comp_id


def _synthesize(prompt: str, seed: int = 42):
    spec = IntentParser(use_llm=False).parse(prompt)
    reqs = normalize(spec)
    selection = ComponentSelector(seed=seed).select(reqs)
    return synthesize_topology(selection)


def test_i2c_bus_created(monkeypatch):
    topo = _synthesize("ESP32 with BME280 temperature sensor over I2C")
    i2c_buses = [b for b in topo.buses if b.bus_type == "I2C"]
    assert len(i2c_buses) >= 1


def test_unique_i2c_addresses():
    topo = _synthesize("Measure temperature and humidity with I2C sensors")
    for bus in topo.buses:
        if bus.bus_type == "I2C":
            addresses = list(bus.slave_addresses.values())
            assert len(addresses) == len(set(addresses)), "I2C addresses must be unique"


def test_mcu_is_master():
    topo = _synthesize("ESP32 with BME280 over I2C")
    if topo.buses:
        bus = topo.buses[0]
        mcu_ids = [_comp_id(c) for c in topo.components if c.category == "mcu"]
        assert bus.master_id in mcu_ids


def test_power_rail_present():
    topo = _synthesize("ESP32 with BME280 over I2C")
    assert len(topo.power_rails) >= 1
    rail = topo.power_rails[0]
    assert 3.0 <= rail.voltage_nominal <= 5.5


def test_component_ids_stable():
    topo1 = _synthesize("ESP32 with BME280 over I2C", seed=42)
    topo2 = _synthesize("ESP32 with BME280 over I2C", seed=42)
    ids1 = sorted(c.mpn for c in topo1.components)
    ids2 = sorted(c.mpn for c in topo2.components)
    assert ids1 == ids2


# --- Passive component tests ---

def test_i2c_pullups_generated():
    """I2C pull-up resistors must be synthesized when an I2C bus exists."""
    topo = _synthesize("ESP32 with BME280 over I2C")
    resistors = [p for p in topo.passives if p.category == "resistor"]
    assert len(resistors) >= 2, "Need at least SDA + SCL pull-up resistors"
    for r in resistors:
        assert r.value == "4.7k"
        assert r.unit == "Ω"
        assert r.package == "0402"


def test_decoupling_caps_per_ic():
    """One 100 nF decoupling cap must be generated per active IC."""
    topo = _synthesize("ESP32 with BME280 and MPU-6050")
    decoupling = [p for p in topo.passives if p.category == "capacitor" and p.value == "100n"]
    # Should have one per active component (MCU + 2 sensors = 3)
    assert len(decoupling) == len(topo.components)


def test_bulk_cap_per_rail():
    """One 10 µF bulk cap must be generated per power rail."""
    topo = _synthesize("ESP32 with BME280 over I2C")
    bulk = [p for p in topo.passives if p.value == "10u"]
    assert len(bulk) == len(topo.power_rails)


def test_passive_nets_reference_power_rail():
    """Pull-up resistor nets must connect to power rail and signal net."""
    topo = _synthesize("ESP32 with BME280 over I2C")
    rail_names = {pr.name for pr in topo.power_rails}
    pullups = [p for p in topo.passives if "pullup" in p.purpose]
    for p in pullups:
        assert any(net in rail_names for net in p.nets), f"Pull-up {p.comp_id} must connect to power rail"


def test_no_passives_without_sensors():
    """With only MCU and no sensors, no I2C bus → no pull-up resistors."""
    spec = IntentParser(use_llm=False).parse("standalone ESP32 MCU")
    reqs = normalize(spec)
    reqs.sensing_modalities = []
    reqs.sensor_mpns = []
    from boardsmith_hw.component_selector import ComponentSelector
    sel = ComponentSelector(seed=42).select(reqs)
    topo = synthesize_topology(sel)
    resistors = [p for p in topo.passives if p.category == "resistor"]
    assert len(resistors) == 0, "No sensors → no I2C bus → no pull-up resistors"


# --- Voltage Regulator tests ---

def test_no_regulator_at_33v():
    """No LDO needed when supply matches MCU VDD (3.3V)."""
    topo = _synthesize("ESP32 with BME280 over I2C")
    topo2 = synthesize_topology(
        __import__("boardsmith_hw.component_selector", fromlist=["ComponentSelector"])
        .ComponentSelector(seed=42)
        .select(__import__("boardsmith_hw.requirements_normalizer", fromlist=["normalize"])
                .normalize(IntentParser(use_llm=False).parse("ESP32 with BME280"))),
        supply_voltage_v=3.3,
    )
    assert len(topo2.voltage_regulators) == 0, "3.3V supply → no LDO needed"


def test_ldo_added_at_5v():
    """AMS1117-3.3 must be synthesized when 5V is the supply."""
    spec = IntentParser(use_llm=False).parse("ESP32 with BME280")
    reqs = normalize(spec)
    sel = ComponentSelector(seed=42).select(reqs)
    topo = synthesize_topology(sel, supply_voltage_v=5.0)
    assert len(topo.voltage_regulators) == 1
    reg = topo.voltage_regulators[0]
    assert reg.input_voltage_nom == 5.0
    assert reg.output_voltage_nom == 3.3
    assert "AMS1117" in reg.mpn or "AP2112" in reg.mpn


def test_ldo_creates_input_and_output_rails():
    """5V supply → two power rails: VIN_5V + 3V3_REG."""
    spec = IntentParser(use_llm=False).parse("ESP32 with BME280")
    reqs = normalize(spec)
    sel = ComponentSelector(seed=42).select(reqs)
    topo = synthesize_topology(sel, supply_voltage_v=5.0)
    rail_names = {r.name for r in topo.power_rails}
    assert "VIN_5V" in rail_names
    assert any("REG" in n for n in rail_names), "Regulated output rail expected"


def test_ldo_bypass_caps_synthesized():
    """LDO must produce input + output bypass caps."""
    spec = IntentParser(use_llm=False).parse("ESP32 with BME280")
    reqs = normalize(spec)
    sel = ComponentSelector(seed=42).select(reqs)
    topo = synthesize_topology(sel, supply_voltage_v=5.0)
    ldo_caps = [p for p in topo.passives if "ldo" in p.purpose]
    # Expect at least: 1 input cap + 2 output caps (bulk + noise)
    assert len(ldo_caps) >= 3, f"Expected ≥3 LDO bypass caps, got {len(ldo_caps)}"


def test_ldo_in_hir_bom():
    """LDO must appear as a power component in HIR BOM."""
    from boardsmith_hw.hir_composer import compose_hir
    spec = IntentParser(use_llm=False).parse("ESP32 with BME280")
    reqs = normalize(spec)
    sel = ComponentSelector(seed=42).select(reqs)
    topo = synthesize_topology(sel, supply_voltage_v=5.0)
    hir = compose_hir(topo)
    ldo_bom = [e for e in hir.bom if e.line_id.startswith("V")]
    assert len(ldo_bom) == 1
    assert "AMS1117" in ldo_bom[0].mpn or "AP2112" in ldo_bom[0].mpn


def test_ldo_power_dependency_in_hir():
    """HIR power sequence must contain VIN→3V3_REG dependency."""
    from boardsmith_hw.hir_composer import compose_hir
    spec = IntentParser(use_llm=False).parse("ESP32 with BME280")
    reqs = normalize(spec)
    sel = ComponentSelector(seed=42).select(reqs)
    topo = synthesize_topology(sel, supply_voltage_v=5.0)
    hir = compose_hir(topo)
    deps = hir.power_sequence.dependencies
    assert len(deps) >= 1
    assert any("VIN" in d.source for d in deps)


# ---------------------------------------------------------------------------
# Battery charger circuit (TP4056)
# ---------------------------------------------------------------------------

def _make_tp4056_selection():
    """Build a minimal ComponentSelection with TP4056 as a sensor component."""
    from boardsmith_hw.component_selector import ComponentSelection, SelectedComponent
    mcu = SelectedComponent(
        mpn="ESP32-WROOM-32",
        manufacturer="Espressif",
        name="ESP32 WROOM-32",
        category="mcu",
        interface_types=["I2C", "SPI", "UART"],
        role="mcu",
        known_i2c_addresses=[],
        init_contract_coverage=True,
        unit_cost_usd=3.50,
        score=0.95,
        raw={"mpn": "ESP32-WROOM-32", "category": "mcu", "interface_types": ["I2C", "SPI"]},
    )
    tp4056 = SelectedComponent(
        mpn="TP4056",
        manufacturer="NanJing Top Power ASIC",
        name="TP4056 Li-Ion Charger",
        category="battery_charger",
        interface_types=[],
        role="battery_charger",
        known_i2c_addresses=[],
        init_contract_coverage=False,
        unit_cost_usd=0.20,
        score=0.90,
        raw={"mpn": "TP4056", "category": "battery_charger"},
    )
    return ComponentSelection(mcu=mcu, sensors=[tp4056])


class TestBatteryChargerCircuit:
    """Tests for _synthesize_battery_charger_circuit() TP4056 support circuit."""

    def test_tp4056_adds_r_prog(self):
        """TP4056 in components → R_PROG passive with correct value and nets."""
        sel = _make_tp4056_selection()
        topo = synthesize_topology(sel)
        prog_resistors = [
            p for p in topo.passives if p.purpose == "tp4056_prog_resistor"
        ]
        assert len(prog_resistors) >= 1, "Expected at least one R_PROG passive"
        r = prog_resistors[0]
        assert r.value == "2k"
        assert r.nets == ["TP4056_PROG", "GND"]

    def test_tp4056_adds_jst_connector(self):
        """TP4056 in components → JST-PH battery connector (B2B-PH-K-S) in all_components."""
        sel = _make_tp4056_selection()
        topo = synthesize_topology(sel)
        mpns = [c.mpn for c in topo.components]
        assert "B2B-PH-K-S" in mpns, f"Expected B2B-PH-K-S in components, got: {mpns}"

    def test_tp4056_adds_vcc_assumption(self):
        """TP4056 circuit adds 5V_VBUS assumption note."""
        sel = _make_tp4056_selection()
        topo = synthesize_topology(sel)
        assert any(
            "5V_VBUS" in a for a in topo.assumptions
        ), f"Expected 5V_VBUS in assumptions, got: {topo.assumptions}"

    def test_no_tp4056_no_circuit(self):
        """Without TP4056, no R_PROG passive and no JST connector added."""
        sel = _make_tp4056_selection()
        sel.sensors = []  # Remove TP4056
        topo = synthesize_topology(sel)
        prog_resistors = [p for p in topo.passives if p.purpose == "tp4056_prog_resistor"]
        mpns = [c.mpn for c in topo.components]
        assert len(prog_resistors) == 0, "No TP4056 → no R_PROG"
        assert "B2B-PH-K-S" not in mpns, "No TP4056 → no JST connector"
