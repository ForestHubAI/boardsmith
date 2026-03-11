# SPDX-License-Identifier: AGPL-3.0-or-later
"""HIR snapshot regression tests.

Verifies that the HIR structure produced by the Boardsmith pipeline
(Track B) and the compiler pipeline (Track A) matches a set of stable
invariants. Any change that breaks these tests is a potential regression
in the HIR schema or the synthesis logic.

Design principle: tests check *structural invariants*, not volatile fields
(timestamps, UUIDs, created_at). This makes snapshots durable across
legitimate changes while catching accidental regressions.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from boardsmith_hw.synthesizer import Synthesizer

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

FIXTURE_DIR  = Path(__file__).parent.parent / "fixtures"
VIBE_FIXTURE = FIXTURE_DIR / "boardsmith_hw"
VALID_HIR    = VIBE_FIXTURE / "hir_valid_esp32_bme280.json"
GRAPH_JSON   = FIXTURE_DIR  / "hardware_graph_esp32_bme280.json"


# ---------------------------------------------------------------------------
# Shared fixture — Track B synthesis (runs once for the whole module)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def track_b_hir(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Run the full Boardsmith pipeline with a fixed seed and return the HIR dict."""
    out = tmp_path_factory.mktemp("snap_b")
    synth = Synthesizer(
        out_dir=out,
        target="esp32",
        max_iterations=5,
        confidence_threshold=0.30,
        seed=42,
        use_llm=False,
    )
    synth.run("ESP32 with BME280 temperature humidity pressure sensor over I2C")
    hir_path = out / "hir.json"
    assert hir_path.exists(), "Synthesis did not produce hir.json"
    return json.loads(hir_path.read_text())


@pytest.fixture(scope="module")
def track_b_bom(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Run synthesis and return the BOM dict."""
    out = tmp_path_factory.mktemp("snap_b_bom")
    synth = Synthesizer(
        out_dir=out,
        target="esp32",
        max_iterations=5,
        confidence_threshold=0.30,
        seed=42,
        use_llm=False,
    )
    synth.run("ESP32 with BME280 temperature humidity pressure sensor over I2C")
    bom_path = out / "bom.json"
    assert bom_path.exists(), "Synthesis did not produce bom.json"
    return json.loads(bom_path.read_text())


@pytest.fixture(scope="module")
def track_a_hir() -> dict:
    """Export HIR from the Track A fixture graph and return the dict."""
    from synth_core.api.compiler import export_hir
    return export_hir(graph_path=GRAPH_JSON, include_constraints=True)


# ---------------------------------------------------------------------------
# Track B HIR — Top-level schema
# ---------------------------------------------------------------------------

class TestTrackBSchema:
    def test_hir_version_is_1_1_0(self, track_b_hir):
        assert track_b_hir["version"] == "1.1.0"

    def test_source_is_prompt(self, track_b_hir):
        assert track_b_hir["source"] == "prompt"

    def test_metadata_track_is_b(self, track_b_hir):
        assert track_b_hir["metadata"]["track"] == "B"

    def test_metadata_has_confidence(self, track_b_hir):
        conf = track_b_hir["metadata"]["confidence"]
        assert 0.0 <= conf["overall"] <= 1.0

    def test_metadata_has_assumptions_list(self, track_b_hir):
        assert isinstance(track_b_hir["metadata"].get("assumptions", []), list)

    def test_top_level_fields_present(self, track_b_hir):
        required = {"version", "source", "components", "bus_contracts",
                    "electrical_specs", "power_sequence", "bom", "metadata"}
        assert required.issubset(track_b_hir.keys())


# ---------------------------------------------------------------------------
# Track B HIR — Components
# ---------------------------------------------------------------------------

class TestTrackBComponents:
    def _comps(self, hir: dict) -> list[dict]:
        return hir["components"]

    def _mpns(self, hir: dict) -> set[str]:
        return {c["mpn"] for c in self._comps(hir)}

    def test_has_esp32_mcu(self, track_b_hir):
        assert "ESP32-WROOM-32" in self._mpns(track_b_hir)

    def test_has_bme280_sensor(self, track_b_hir):
        assert "BME280" in self._mpns(track_b_hir)

    def test_has_i2c_pull_up_resistors(self, track_b_hir):
        # I2C pull-up: RC0402FR-074K7L (4.7kΩ)
        assert "RC0402FR-074K7L" in self._mpns(track_b_hir)

    def test_has_decoupling_capacitors(self, track_b_hir):
        assert "GRM155R71C104KA88D" in self._mpns(track_b_hir)

    def test_has_bulk_capacitors(self, track_b_hir):
        assert "GRM188R61A106KE69D" in self._mpns(track_b_hir)

    def test_mcu_has_role_mcu(self, track_b_hir):
        mcu = next(c for c in self._comps(track_b_hir) if c["mpn"] == "ESP32-WROOM-32")
        assert mcu["role"] == "mcu"

    def test_sensor_has_role_sensor(self, track_b_hir):
        sensor = next(c for c in self._comps(track_b_hir) if c["mpn"] == "BME280")
        assert sensor["role"] == "sensor"

    def test_passive_has_role_passive(self, track_b_hir):
        passives = [c for c in self._comps(track_b_hir) if c["role"] == "passive"]
        assert len(passives) >= 3  # 2 pull-ups + at least 1 decoupling cap

    def test_all_components_have_mpn(self, track_b_hir):
        assert all(c.get("mpn") for c in self._comps(track_b_hir))

    def test_all_components_have_id(self, track_b_hir):
        ids = [c.get("id") for c in self._comps(track_b_hir)]
        assert all(ids)
        assert len(ids) == len(set(ids)), "Duplicate component IDs"

    def test_at_least_five_components(self, track_b_hir):
        # MCU + sensor + 2 pull-ups + decoupling caps
        assert len(self._comps(track_b_hir)) >= 5


# ---------------------------------------------------------------------------
# Track B HIR — Bus contracts
# ---------------------------------------------------------------------------

class TestTrackBBusContracts:
    def _buses(self, hir: dict) -> list[dict]:
        return hir.get("bus_contracts", [])

    def test_has_at_least_one_bus(self, track_b_hir):
        assert len(self._buses(track_b_hir)) >= 1

    def test_i2c_bus_present(self, track_b_hir):
        types = {bc["bus_type"] for bc in self._buses(track_b_hir)}
        assert "I2C" in types

    def test_i2c_master_is_esp32(self, track_b_hir):
        i2c = next(bc for bc in self._buses(track_b_hir) if bc["bus_type"] == "I2C")
        assert "ESP32" in i2c["master_id"].upper() or "MCU" in i2c["master_id"].upper()

    def test_bme280_is_i2c_slave(self, track_b_hir):
        i2c = next(bc for bc in self._buses(track_b_hir) if bc["bus_type"] == "I2C")
        slave_ids = i2c.get("slave_ids", [])
        slave_mpns = {
            c["mpn"] for c in track_b_hir["components"]
            if c["id"] in slave_ids
        }
        assert "BME280" in slave_mpns

    def test_bme280_has_i2c_address(self, track_b_hir):
        i2c = next(bc for bc in self._buses(track_b_hir) if bc["bus_type"] == "I2C")
        slave_addrs = i2c.get("slave_addresses", {})
        addrs = set(slave_addrs.values())
        # BME280 default addresses: 0x76 or 0x77
        assert any(addr in addrs for addr in ("0x76", "0x77"))

    def test_i2c_has_pin_assignments(self, track_b_hir):
        i2c = next(bc for bc in self._buses(track_b_hir) if bc["bus_type"] == "I2C")
        pins = i2c.get("pin_assignments", {})
        assert "SDA" in pins or "sda" in {k.lower() for k in pins}

    def test_bus_contract_has_bus_name(self, track_b_hir):
        for bc in self._buses(track_b_hir):
            assert bc.get("bus_name"), f"Bus contract missing bus_name: {bc}"


# ---------------------------------------------------------------------------
# Track B HIR — Power sequence
# ---------------------------------------------------------------------------

class TestTrackBPowerSequence:
    def _power_seq(self, hir: dict) -> dict:
        return hir.get("power_sequence", {})

    def test_power_sequence_present(self, track_b_hir):
        assert "power_sequence" in track_b_hir

    def test_has_power_rails(self, track_b_hir):
        rails = self._power_seq(track_b_hir).get("rails", [])
        assert len(rails) >= 1

    def test_3v3_rail_present(self, track_b_hir):
        rails = self._power_seq(track_b_hir).get("rails", [])
        names = {r["name"].lower() for r in rails}
        assert any("3v3" in n or "vdd" in n or "3.3" in n for n in names)

    def test_rails_have_voltage(self, track_b_hir):
        rails = self._power_seq(track_b_hir).get("rails", [])
        for rail in rails:
            assert "voltage" in rail, f"Rail {rail.get('name')} missing voltage"


# ---------------------------------------------------------------------------
# Track B HIR — BOM
# ---------------------------------------------------------------------------

class TestTrackBBom:
    def _bom(self, hir: dict) -> list[dict]:
        return hir.get("bom", [])

    def test_bom_not_empty(self, track_b_hir):
        assert len(self._bom(track_b_hir)) >= 2

    def test_bom_contains_esp32(self, track_b_hir):
        mpns = {e["mpn"] for e in self._bom(track_b_hir)}
        assert "ESP32-WROOM-32" in mpns

    def test_bom_contains_bme280(self, track_b_hir):
        mpns = {e["mpn"] for e in self._bom(track_b_hir)}
        assert "BME280" in mpns

    def test_bom_contains_passive_mpns(self, track_b_hir):
        mpns = {e["mpn"] for e in self._bom(track_b_hir)}
        # At least one passive MPN must be present
        passive_mpns = {"RC0402FR-074K7L", "GRM155R71C104KA88D", "GRM188R61A106KE69D"}
        assert mpns & passive_mpns, f"No passive MPNs in BOM: {mpns}"

    def test_bom_line_ids_unique(self, track_b_hir):
        ids = [e["line_id"] for e in self._bom(track_b_hir)]
        assert len(ids) == len(set(ids)), "Duplicate BOM line IDs"

    def test_bom_entries_have_qty(self, track_b_hir):
        for entry in self._bom(track_b_hir):
            assert entry.get("qty", 0) >= 1, f"Zero qty: {entry.get('line_id')}"

    def test_bom_entries_have_component_id(self, track_b_hir):
        comp_ids = {c["id"] for c in track_b_hir["components"]}
        for entry in self._bom(track_b_hir):
            assert entry.get("component_id") in comp_ids, \
                f"BOM entry {entry.get('line_id')} references unknown component"


# ---------------------------------------------------------------------------
# Track B — Electrical specs
# ---------------------------------------------------------------------------

class TestTrackBElecSpecs:
    def test_electrical_specs_not_empty(self, track_b_hir):
        assert len(track_b_hir.get("electrical_specs", [])) >= 1

    def test_mcu_has_electrical_spec(self, track_b_hir):
        mcu = next(c for c in track_b_hir["components"] if c["mpn"] == "ESP32-WROOM-32")
        specs = track_b_hir.get("electrical_specs", [])
        assert any(s["component_id"] == mcu["id"] for s in specs)


# ---------------------------------------------------------------------------
# Track A HIR — from hardware graph fixture
# ---------------------------------------------------------------------------

class TestTrackASnapshot:
    def test_hir_version_1_1_0(self, track_a_hir):
        assert track_a_hir["version"] == "1.1.0"

    def test_source_is_schematic(self, track_a_hir):
        assert track_a_hir["source"] == "schematic"

    def test_track_is_a(self, track_a_hir):
        assert track_a_hir["metadata"]["track"] == "A"

    def test_has_two_components(self, track_a_hir):
        assert len(track_a_hir["components"]) == 2

    def test_components_have_esp32_and_bme280(self, track_a_hir):
        mpns = {c["mpn"] for c in track_a_hir["components"]}
        assert "ESP32-WROOM-32" in mpns
        assert "BME280" in mpns

    def test_has_i2c_bus_contract(self, track_a_hir):
        bus_types = {bc["bus_type"] for bc in track_a_hir.get("bus_contracts", [])}
        assert "I2C" in bus_types

    def test_constraints_present(self, track_a_hir):
        assert isinstance(track_a_hir.get("constraints", []), list)

    def test_valid_fixture_produces_no_error_constraints(self, track_a_hir):
        errors = [
            c for c in track_a_hir.get("constraints", [])
            if c.get("severity") == "error" and c.get("status") == "fail"
        ]
        assert len(errors) == 0, f"Unexpected errors: {errors}"


# ---------------------------------------------------------------------------
# HIR schema stability — field-level checks
# ---------------------------------------------------------------------------

class TestHIRSchemaStability:
    """Verify that all HIR model fields are still present and correctly typed."""

    def test_component_fields_stable(self, track_b_hir):
        for comp in track_b_hir["components"]:
            assert "id" in comp
            assert "name" in comp
            assert "role" in comp
            assert "mpn" in comp
            assert "interface_types" in comp
            assert isinstance(comp["interface_types"], list)

    def test_bus_contract_fields_stable(self, track_b_hir):
        for bc in track_b_hir.get("bus_contracts", []):
            assert "bus_name" in bc
            assert "bus_type" in bc
            assert "master_id" in bc
            assert "slave_ids" in bc
            assert isinstance(bc["slave_ids"], list)

    def test_bom_entry_fields_stable(self, track_b_hir):
        for entry in track_b_hir.get("bom", []):
            assert "line_id" in entry
            assert "component_id" in entry
            assert "mpn" in entry
            assert "qty" in entry

    def test_power_rail_fields_stable(self, track_b_hir):
        for rail in track_b_hir.get("power_sequence", {}).get("rails", []):
            assert "name" in rail
            assert "voltage" in rail
            assert "nominal" in rail["voltage"]

    def test_electrical_spec_fields_stable(self, track_b_hir):
        for spec in track_b_hir.get("electrical_specs", []):
            assert "component_id" in spec

    def test_metadata_fields_stable(self, track_b_hir):
        meta = track_b_hir["metadata"]
        assert "created_at" in meta
        assert "track" in meta
        assert "confidence" in meta
        conf = meta["confidence"]
        assert "overall" in conf
