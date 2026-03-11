# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the built-in knowledge DB and resolver."""

from pathlib import Path

from boardsmith_fw.analysis.graph_builder import build_hardware_graph
from boardsmith_fw.knowledge.builtin_db import list_builtin_mpns, lookup_builtin
from boardsmith_fw.knowledge.resolver import resolve_knowledge, save_to_cache
from boardsmith_fw.parser.eagle_parser import parse_eagle_schematic

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _build(fixture: str, filename: str):
    path = FIXTURES / fixture / filename
    result = parse_eagle_schematic(path)
    return build_hardware_graph(str(path), result.components, result.nets)


class TestBuiltinDB:
    def test_bme280_lookup(self):
        k = lookup_builtin("BME280")
        assert k is not None
        assert k.name == "BME280"
        assert k.i2c_address == "0x76"
        assert k.interface.value == "I2C"

    def test_bme280_has_registers(self):
        k = lookup_builtin("BME280")
        assert len(k.registers) >= 10
        ctrl_meas = next(r for r in k.registers if r.name == "ctrl_meas")
        assert ctrl_meas.address == "0xF4"

    def test_bme280_has_init_sequence(self):
        k = lookup_builtin("BME280")
        assert len(k.init_sequence) >= 4
        # Soft reset first
        assert k.init_sequence[0].reg_addr == "0xE0"
        assert k.init_sequence[0].value == "0xB6"
        # Normal mode config
        ctrl = next(s for s in k.init_sequence if s.reg_addr == "0xF4")
        assert ctrl.value == "0x27"

    def test_w25q128_lookup(self):
        k = lookup_builtin("W25Q128")
        assert k is not None
        assert k.interface.value == "SPI"
        assert k.manufacturer == "Winbond"

    def test_w25q128_prefix_match(self):
        k = lookup_builtin("W25Q128JVSIQ")
        assert k is not None
        assert k.name == "W25Q128"

    def test_neo_m8n_lookup(self):
        k = lookup_builtin("NEO-M8N")
        assert k is not None
        assert k.interface.value == "UART"

    def test_unknown_returns_none(self):
        k = lookup_builtin("XYZ_UNKNOWN_CHIP_999")
        assert k is None

    def test_list_builtin_mpns(self):
        mpns = list_builtin_mpns()
        assert "BME280" in mpns
        assert "W25Q128" in mpns
        assert "NEO-M8N" in mpns
        assert len(mpns) >= 5


class TestResolver:
    def test_resolve_esp32_bme280(self):
        graph = _build("esp32_bme280_i2c", "esp32_bme280.sch")
        knowledge = resolve_knowledge(graph)

        # Should resolve at least ESP32 and BME280 (not passives)
        assert len(knowledge) >= 2

        bme_k = next((k for k in knowledge if "BME280" in k.name.upper()), None)
        assert bme_k is not None
        assert bme_k.i2c_address == "0x76"
        assert len(bme_k.init_sequence) >= 4

    def test_resolve_multi_bus(self):
        graph = _build("esp32_multi_bus", "esp32_multi_bus.sch")
        knowledge = resolve_knowledge(graph)

        names = {k.name.upper() for k in knowledge}
        assert "BME280" in names
        assert "W25Q128" in names

    def test_resolve_assigns_component_ids(self):
        graph = _build("esp32_bme280_i2c", "esp32_bme280.sch")
        knowledge = resolve_knowledge(graph)

        for k in knowledge:
            assert k.component_id != ""
            # Component ID should exist in graph
            assert any(c.id == k.component_id for c in graph.components)

    def test_passives_excluded(self):
        graph = _build("esp32_bme280_i2c", "esp32_bme280.sch")
        knowledge = resolve_knowledge(graph)

        for k in knowledge:
            # No resistors, capacitors, etc.
            comp = next(c for c in graph.components if c.id == k.component_id)
            assert comp.name[0].upper() not in ("R", "C", "L", "D")

    def test_save_and_load_cache(self, tmp_path):
        k = lookup_builtin("BME280")
        k.component_id = "U2"
        path = save_to_cache(k, tmp_path)
        assert path.exists()

        from boardsmith_fw.knowledge.resolver import _load_from_cache
        loaded = _load_from_cache("BME280", tmp_path)
        assert loaded is not None
        assert loaded.i2c_address == "0x76"
