# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the Eagle .sch XML parser."""

from pathlib import Path

import pytest

from boardsmith_fw.parser.eagle_parser import parse_eagle_schematic

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestEsp32Bme280:
    """Test parsing the ESP32 + BME280 I2C fixture."""

    @pytest.fixture
    def result(self):
        return parse_eagle_schematic(FIXTURES / "esp32_bme280_i2c" / "esp32_bme280.sch")

    def test_component_count(self, result):
        assert len(result.components) == 5  # U1, U2, R1, R2, C1

    def test_net_count(self, result):
        assert len(result.nets) == 4  # SDA, SCL, 3V3, GND

    def test_no_warnings(self, result):
        assert len(result.warnings) == 0

    def test_esp32_component(self, result):
        u1 = next(c for c in result.components if c.id == "U1")
        assert u1.value == "ESP32-WROOM-32"
        assert u1.library == "esp32"
        assert u1.manufacturer == "Espressif"
        assert u1.mpn == "ESP32-WROOM-32"

    def test_bme280_component(self, result):
        u2 = next(c for c in result.components if c.id == "U2")
        assert u2.value == "BME280"
        assert u2.manufacturer == "Bosch"

    def test_passive_components(self, result):
        r1 = next(c for c in result.components if c.id == "R1")
        assert r1.value == "4.7k"
        assert r1.package == "0402"

    def test_sda_net(self, result):
        sda = next(n for n in result.nets if n.name == "SDA")
        comp_ids = {p.component_id for p in sda.pins}
        assert "U1" in comp_ids
        assert "U2" in comp_ids
        assert "R1" in comp_ids

    def test_scl_net(self, result):
        scl = next(n for n in result.nets if n.name == "SCL")
        comp_ids = {p.component_id for p in scl.pins}
        assert "U1" in comp_ids
        assert "U2" in comp_ids

    def test_power_nets(self, result):
        net_names = {n.name for n in result.nets}
        assert "3V3" in net_names
        assert "GND" in net_names

    def test_pin_directions(self, result):
        u1 = next(c for c in result.components if c.id == "U1")
        sda_pin = next(p for p in u1.pins if "SDA" in p.name)
        assert sda_pin.direction.value in ("bidirectional", "io")

    def test_pin_net_assignment(self, result):
        u1 = next(c for c in result.components if c.id == "U1")
        sda_pin = next(p for p in u1.pins if "SDA" in p.name)
        assert sda_pin.net == "SDA"


class TestStm32Bme280:
    """Test parsing the STM32F4 + BME280 I2C fixture."""

    @pytest.fixture
    def result(self):
        return parse_eagle_schematic(FIXTURES / "stm32f4_bme280_i2c" / "stm32f4_bme280.sch")

    def test_component_count(self, result):
        assert len(result.components) == 5

    def test_stm32_component(self, result):
        u1 = next(c for c in result.components if c.id == "U1")
        assert "STM32" in u1.value
        assert u1.manufacturer == "STMicroelectronics"

    def test_sda_net_has_stm32_pin(self, result):
        sda = next(n for n in result.nets if n.name == "SDA")
        comp_ids = {p.component_id for p in sda.pins}
        assert "U1" in comp_ids
        assert "U2" in comp_ids


class TestInvalidFiles:
    def test_nonexistent_file(self):
        with pytest.raises(Exception):
            parse_eagle_schematic(Path("/nonexistent.sch"))

    def test_invalid_xml(self, tmp_path):
        f = tmp_path / "bad.sch"
        f.write_text("<notaneagle/>")
        with pytest.raises(ValueError, match="Not a valid Eagle file"):
            parse_eagle_schematic(f)
