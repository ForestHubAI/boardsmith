# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the KiCad .kicad_sch parser."""

from pathlib import Path

from boardsmith_fw.parser.kicad_parser import parse_kicad_schematic

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class TestKicadParser:
    def test_parse_fixture(self):
        path = FIXTURES / "kicad_bme280_i2c" / "esp32_bme280.kicad_sch"
        result = parse_kicad_schematic(path)
        assert len(result.warnings) == 0
        assert len(result.components) >= 2  # At least U1 (ESP32) and U2 (BME280)

    def test_component_references(self):
        path = FIXTURES / "kicad_bme280_i2c" / "esp32_bme280.kicad_sch"
        result = parse_kicad_schematic(path)
        refs = {c.name for c in result.components}
        assert "U1" in refs
        assert "U2" in refs

    def test_component_values(self):
        path = FIXTURES / "kicad_bme280_i2c" / "esp32_bme280.kicad_sch"
        result = parse_kicad_schematic(path)
        u1 = next(c for c in result.components if c.name == "U1")
        assert "ESP32" in u1.value.upper()
        u2 = next(c for c in result.components if c.name == "U2")
        assert "BME280" in u2.value.upper()

    def test_component_pins(self):
        path = FIXTURES / "kicad_bme280_i2c" / "esp32_bme280.kicad_sch"
        result = parse_kicad_schematic(path)
        u1 = next(c for c in result.components if c.name == "U1")
        assert len(u1.pins) >= 2  # At least SDA and SCL pins

    def test_mpn_property(self):
        path = FIXTURES / "kicad_bme280_i2c" / "esp32_bme280.kicad_sch"
        result = parse_kicad_schematic(path)
        u2 = next(c for c in result.components if c.name == "U2")
        assert u2.mpn == "BME280"

    def test_manufacturer_property(self):
        path = FIXTURES / "kicad_bme280_i2c" / "esp32_bme280.kicad_sch"
        result = parse_kicad_schematic(path)
        u2 = next(c for c in result.components if c.name == "U2")
        assert u2.manufacturer == "Bosch Sensortec"

    def test_net_labels(self):
        path = FIXTURES / "kicad_bme280_i2c" / "esp32_bme280.kicad_sch"
        result = parse_kicad_schematic(path)
        net_names = {n.name for n in result.nets}
        assert "SDA" in net_names
        assert "SCL" in net_names

    def test_passives_parsed(self):
        path = FIXTURES / "kicad_bme280_i2c" / "esp32_bme280.kicad_sch"
        result = parse_kicad_schematic(path)
        refs = {c.name for c in result.components}
        assert "R1" in refs
        assert "R2" in refs

    def test_nonexistent_file(self):
        result = parse_kicad_schematic(Path("/nonexistent/file.kicad_sch"))
        assert len(result.components) == 0
        assert len(result.warnings) > 0

    def test_invalid_file(self, tmp_path):
        bad = tmp_path / "bad.kicad_sch"
        bad.write_text("this is not a valid kicad file")
        result = parse_kicad_schematic(bad)
        assert len(result.warnings) > 0
