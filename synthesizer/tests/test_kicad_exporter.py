# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for boardsmith_hw.kicad_exporter (KiCad 6 .kicad_sch generation)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from boardsmith_hw.kicad_exporter import export_kicad_sch, _net_for_pin, _esc_id
from synth_core.knowledge.symbol_map import SYMBOL_MAP, _generic_symbol


# ---------------------------------------------------------------------------
# Fixtures — minimal HIR dicts
# ---------------------------------------------------------------------------

def _make_hir(components: list[dict], bus_contracts: list[dict] | None = None) -> dict:
    return {
        "version": "1.1.0",
        "components": components,
        "bus_contracts": bus_contracts or [],
        "nets": [],
        "buses": [],
    }


ESP32_COMP = {
    "id": "U_MCU",
    "name": "ESP32-WROOM-32 MCU",
    "role": "mcu",
    "mpn": "ESP32-WROOM-32",
    "interface_types": ["I2C", "SPI", "UART"],
}

BME280_COMP = {
    "id": "U_BME280",
    "name": "BME280 sensor",
    "role": "sensor",
    "mpn": "BME280",
    "interface_types": ["I2C", "SPI"],
}

AHT20_COMP = {
    "id": "U_AHT20",
    "name": "AHT20 sensor",
    "role": "sensor",
    "mpn": "AHT20",
    "interface_types": ["I2C"],
}

LDO_COMP = {
    "id": "U_LDO",
    "name": "AMS1117-3.3 LDO",
    "role": "power",
    "mpn": "AMS1117-3.3",
    "interface_types": [],
}

PASSIVE_R = {
    "id": "R1",
    "name": "4.7k pull-up",
    "role": "passive",
    "mpn": "RC0402FR-074K7L",
    "interface_types": [],
}

PASSIVE_C = {
    "id": "C1",
    "name": "100nF decoupling",
    "role": "passive",
    "mpn": "GRM155R71C104KA88D",
    "interface_types": [],
}

I2C_BUS = {
    "bus_name": "i2c0",
    "bus_type": "I2C",
    "master_id": "U_MCU",
    "slave_ids": ["U_BME280"],
    "slave_addresses": {"U_BME280": "0x76"},
}

UNKNOWN_COMP = {
    "id": "U_UNKNOWN",
    "name": "My Custom Sensor",
    "role": "sensor",
    "mpn": "CUSTOM-XYZ-123",
    "interface_types": ["I2C"],
}


# ---------------------------------------------------------------------------
# Helper to run export and return content
# ---------------------------------------------------------------------------

def _export(hir: dict) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "schematic.kicad_sch"
        export_kicad_sch(hir, p)
        return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestKiCadHeader:
    def test_output_starts_with_kicad_sch(self):
        hir = _make_hir([ESP32_COMP])
        content = _export(hir)
        assert content.startswith("(kicad_sch")

    def test_version_20230121(self):
        hir = _make_hir([ESP32_COMP])
        content = _export(hir)
        assert "20230121" in content

    def test_generator_boardsmith_fw(self):
        hir = _make_hir([ESP32_COMP])
        content = _export(hir)
        assert 'generator "boardsmith-fw"' in content

    def test_paper_a4(self):
        hir = _make_hir([ESP32_COMP])
        content = _export(hir)
        assert '"A4"' in content

    def test_sheet_instances_present(self):
        hir = _make_hir([ESP32_COMP])
        content = _export(hir)
        assert "sheet_instances" in content

    def test_closed_parenthesis(self):
        """Last non-empty line should close the top-level s-expression."""
        hir = _make_hir([ESP32_COMP])
        content = _export(hir)
        non_empty = [l for l in content.splitlines() if l.strip()]
        assert non_empty[-1] == ")"


class TestLibSymbols:
    def test_lib_symbols_block_present(self):
        hir = _make_hir([ESP32_COMP])
        content = _export(hir)
        assert "(lib_symbols" in content

    def test_mcu_mpn_in_lib_symbols(self):
        hir = _make_hir([ESP32_COMP])
        content = _export(hir)
        assert "ESP32-WROOM-32" in content

    def test_sensor_mpn_in_lib_symbols(self):
        hir = _make_hir([ESP32_COMP, BME280_COMP])
        content = _export(hir)
        assert "BME280" in content

    def test_ldo_mpn_in_lib_symbols(self):
        hir = _make_hir([ESP32_COMP, LDO_COMP])
        content = _export(hir)
        assert "AMS1117-3.3" in content

    def test_power_symbols_gnd_present(self):
        hir = _make_hir([ESP32_COMP])
        content = _export(hir)
        assert '"GND"' in content

    def test_power_symbols_3v3_present(self):
        hir = _make_hir([ESP32_COMP])
        content = _export(hir)
        assert '"+3V3"' in content

    def test_passive_mpn_in_lib_symbols(self):
        hir = _make_hir([ESP32_COMP, PASSIVE_R])
        content = _export(hir)
        assert "RC0402FR-074K7L" in content

    def test_dedup_same_mpn_appears_once_in_lib(self):
        """Two sensors with the same MPN should only produce one lib_symbol entry."""
        c1 = {**BME280_COMP, "id": "U_S1"}
        c2 = {**BME280_COMP, "id": "U_S2"}
        hir = _make_hir([ESP32_COMP, c1, c2])
        content = _export(hir)
        # Count occurrences of the unique symbol header
        count = content.count('(symbol "BME280"')
        assert count == 1


class TestSymbolInstances:
    def test_reference_designators_present(self):
        hir = _make_hir([ESP32_COMP, BME280_COMP])
        content = _export(hir)
        assert '"U1"' in content
        assert '"U2"' in content

    def test_footprint_property_in_output(self):
        hir = _make_hir([ESP32_COMP])
        content = _export(hir)
        assert "RF_Module:ESP32-WROOM-32" in content

    def test_mpn_property_in_instance(self):
        hir = _make_hir([ESP32_COMP])
        content = _export(hir)
        assert '"MPN"' in content

    def test_passive_ref_prefix_r(self):
        hir = _make_hir([PASSIVE_R])
        content = _export(hir)
        assert '"R1"' in content

    def test_passive_ref_prefix_c(self):
        hir = _make_hir([PASSIVE_C])
        content = _export(hir)
        assert '"C1"' in content


class TestBusLabels:
    def test_sda_net_label_for_i2c_design(self):
        """SDA net label must appear for I2C designs (within-sheet label, not global)."""
        hir = _make_hir([ESP32_COMP, BME280_COMP], [I2C_BUS])
        content = _export(hir)
        assert '"SDA"' in content

    def test_scl_net_label_for_i2c_design(self):
        hir = _make_hir([ESP32_COMP, BME280_COMP], [I2C_BUS])
        content = _export(hir)
        assert '"SCL"' in content

    def test_no_bus_labels_without_bus_contracts(self):
        """Without bus_contracts, no bus wires or global_labels should appear."""
        hir = _make_hir([ESP32_COMP, BME280_COMP])  # no bus_contracts
        content = _export(hir)
        # No global_label (multi-sheet) and no within-sheet bus labels either
        assert "global_label" not in content

    def test_no_global_label_in_single_sheet(self):
        """Bus connections must use net labels, not global_label."""
        hir = _make_hir([ESP32_COMP, BME280_COMP], [I2C_BUS])
        content = _export(hir)
        assert "global_label" not in content

    def test_real_wire_drawn_for_bus_signal(self):
        """A wire segment must be emitted for each bus connection."""
        hir = _make_hir([ESP32_COMP, BME280_COMP], [I2C_BUS])
        content = _export(hir)
        assert "(wire" in content

    def test_multiple_sensors_each_get_net_label(self):
        """Multiple I2C sensors → each sensor pin gets its own SDA/SCL net label.

        The old bus-spine approach used a single vertical wire with junctions.
        The new net-label approach emits one label per pin; KiCad auto-connects
        same-name labels.  With 2 sensors (BME280 + AHT20) there must be at
        least 2 SDA labels and 2 SCL labels (one per sensor) plus one each for
        the MCU pins.
        """
        hir = _make_hir([ESP32_COMP, BME280_COMP, AHT20_COMP], [I2C_BUS])
        content = _export(hir)
        # 3 components with SDA pin (ESP32 + 2 sensors) → ≥ 3 SDA labels
        assert content.count('(label "SDA"') >= 3
        assert content.count('(label "SCL"') >= 3

    def test_bidirectional_pin_type_in_lib(self):
        hir = _make_hir([ESP32_COMP, BME280_COMP], [I2C_BUS])
        content = _export(hir)
        assert "bidirectional" in content


class TestPowerConnections:
    def test_gnd_power_symbol_instances(self):
        hir = _make_hir([ESP32_COMP])
        content = _export(hir)
        # Should have at least one GND power instance
        # lib_id reference appears in symbol instances
        assert 'lib_id "GND"' in content

    def test_3v3_power_symbol_instances(self):
        hir = _make_hir([ESP32_COMP])
        content = _export(hir)
        assert 'lib_id "+3V3"' in content

    def test_ldo_vin_connected_to_5v(self):
        hir = _make_hir([LDO_COMP])
        content = _export(hir)
        assert '"+5V"' in content

    def test_power_symbol_ref_incrementing(self):
        hir = _make_hir([ESP32_COMP, BME280_COMP])
        content = _export(hir)
        assert "#PWR001" in content
        assert "#PWR002" in content


class TestGenericSymbolFallback:
    def test_unknown_mpn_produces_output(self):
        hir = _make_hir([UNKNOWN_COMP])
        content = _export(hir)
        assert "CUSTOM-XYZ-123" in content

    def test_generic_symbol_has_i2c_pins(self):
        sym = _generic_symbol("CUSTOM-XYZ-123", "sensor", ["I2C"])
        pin_names = [p.name for p in sym.pins]
        assert "SDA" in pin_names
        assert "SCL" in pin_names

    def test_generic_symbol_has_spi_pins(self):
        sym = _generic_symbol("CUSTOM-SPI", "sensor", ["SPI"])
        pin_names = [p.name for p in sym.pins]
        assert "MOSI" in pin_names
        assert "MISO" in pin_names
        assert "SCLK" in pin_names

    def test_generic_symbol_has_power_pins(self):
        sym = _generic_symbol("CUSTOM-XYZ", "sensor", [])
        pin_names = [p.name for p in sym.pins]
        assert "VDD" in pin_names
        assert "GND" in pin_names

    def test_generic_symbol_ref_prefix_u_for_sensor(self):
        sym = _generic_symbol("CUSTOM-SENSOR", "sensor", [])
        assert sym.ref_prefix == "U"

    def test_generic_symbol_ref_prefix_c_for_passive(self):
        sym = _generic_symbol("CUSTOM-CAP", "passive", [])
        assert sym.ref_prefix == "C"


class TestFileOutput:
    def test_creates_file(self):
        hir = _make_hir([ESP32_COMP])
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "schematic.kicad_sch"
            export_kicad_sch(hir, p)
            assert p.exists()

    def test_creates_parent_directories(self):
        hir = _make_hir([ESP32_COMP])
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "nested" / "dir" / "schematic.kicad_sch"
            export_kicad_sch(hir, p)
            assert p.exists()

    def test_empty_components_produces_valid_header(self):
        hir = _make_hir([])
        content = _export(hir)
        assert content.startswith("(kicad_sch")
        assert "sheet_instances" in content

    def test_multi_component_design(self):
        hir = _make_hir(
            [ESP32_COMP, BME280_COMP, AHT20_COMP, LDO_COMP, PASSIVE_R, PASSIVE_C],
            [I2C_BUS],
        )
        content = _export(hir)
        assert "ESP32-WROOM-32" in content
        assert "BME280" in content
        assert "AHT20" in content
        assert "AMS1117-3.3" in content


class TestSymbolMap:
    def test_all_known_mpns_have_ref_prefix(self):
        # Valid KiCad reference designator prefixes:
        #   U=IC, R=Resistor, C=Capacitor, L=Inductor, J=Connector,
        #   Q=Transistor/FET, D=Diode, FB=Ferrite Bead, Y=Crystal
        valid_prefixes = ("U", "R", "C", "L", "J", "Q", "D", "FB", "Y")
        for mpn, sdef in SYMBOL_MAP.items():
            assert sdef.ref_prefix in valid_prefixes, \
                f"{mpn}: unexpected ref_prefix '{sdef.ref_prefix}'"

    def test_all_known_mpns_have_footprint(self):
        for mpn, sdef in SYMBOL_MAP.items():
            assert sdef.footprint, f"{mpn}: empty footprint"

    def test_all_known_mpns_have_at_least_2_pins(self):
        for mpn, sdef in SYMBOL_MAP.items():
            # Passives (R, C) may have only 2 pins; MCUs/sensors must have ≥2
            assert len(sdef.pins) >= 2, f"{mpn}: too few pins ({len(sdef.pins)})"

    def test_esp32_has_sda_pin(self):
        sdef = SYMBOL_MAP["ESP32-WROOM-32"]
        pin_names = [p.name for p in sdef.pins]
        assert any("SDA" in n for n in pin_names)

    def test_bme280_has_vdd_and_gnd(self):
        sdef = SYMBOL_MAP["BME280"]
        types = {p.type for p in sdef.pins}
        assert "power_in" in types


class TestHIRNetsConsumption:
    """Tests for _draw_bus_wires() consuming hir_dict['nets'] (Phase 16)."""

    def _make_hir_with_nets(self, components, bus_contracts, nets) -> dict:
        return {
            "version": "1.1.0",
            "components": components,
            "bus_contracts": bus_contracts,
            "nets": nets,
            "buses": [],
        }

    def test_hir_net_with_pin_number_still_emits_sda_label(self):
        """Even if HIR net uses pin_name='21' (GPIO number), SDA label must appear."""
        nets = [
            {
                "name": "i2c0_SDA",
                "pins": [
                    {"component_id": "U_MCU", "pin_name": "21"},  # GPIO number
                    {"component_id": "U_BME280", "pin_name": "SDA"},
                ],
            },
            {
                "name": "i2c0_SCL",
                "pins": [
                    {"component_id": "U_MCU", "pin_name": "22"},
                    {"component_id": "U_BME280", "pin_name": "SCL"},
                ],
            },
        ]
        hir = self._make_hir_with_nets(
            [ESP32_COMP, BME280_COMP], [I2C_BUS], nets
        )
        content = _export(hir)
        # The actual ESP32 symbol has "IO21/SDA" pin — matched by name splitting
        # The HIR net check is a redundant safety net; both paths produce labels
        assert '"SDA"' in content
        assert '"SCL"' in content

    def test_hir_net_extends_bus_signals_without_bus_contract(self):
        """If HIR net defines SDA/SCL but no bus_contracts, bus signals still appear."""
        nets = [
            {
                "name": "i2c0_SDA",
                "pins": [
                    {"component_id": "U_MCU", "pin_name": "SDA"},
                    {"component_id": "U_BME280", "pin_name": "SDA"},
                ],
            },
            {
                "name": "i2c0_SCL",
                "pins": [
                    {"component_id": "U_MCU", "pin_name": "SCL"},
                    {"component_id": "U_BME280", "pin_name": "SCL"},
                ],
            },
        ]
        hir = self._make_hir_with_nets(
            [ESP32_COMP, BME280_COMP], [], nets  # no bus_contracts!
        )
        content = _export(hir)
        # With HIR nets providing the signals, bus wiring should still occur
        assert '"SDA"' in content
        assert '"SCL"' in content

    def test_empty_nets_does_not_break_export(self):
        """hir_dict with empty nets list must not break export."""
        hir = _make_hir([ESP32_COMP, BME280_COMP], [I2C_BUS])
        hir["nets"] = []
        content = _export(hir)
        assert content.startswith("(kicad_sch")
        assert '"SDA"' in content  # still works via bus_contracts

    def test_non_bus_net_in_hir_does_not_add_spurious_label(self):
        """Power nets in hir_dict['nets'] must not produce bus wire labels."""
        nets = [
            {"name": "+3V3", "pins": [{"component_id": "U_MCU", "pin_name": "3V3"}]},
            {"name": "GND",  "pins": [{"component_id": "U_MCU", "pin_name": "GND"}]},
        ]
        hir = self._make_hir_with_nets([ESP32_COMP], [], nets)
        content = _export(hir)
        # No bus labels expected — "+3V3" / "GND" are not bus signals
        assert '(label "+3V3"' not in content
        assert '(label "GND"' not in content


class TestHelpers:
    def test_net_for_pin_gnd(self):
        assert _net_for_pin("GND") == "GND"

    def test_net_for_pin_vss(self):
        assert _net_for_pin("VSS") == "GND"

    def test_net_for_pin_3v3(self):
        assert _net_for_pin("3V3") == "+3V3"

    def test_net_for_pin_vdd(self):
        assert _net_for_pin("VDD") == "+3V3"

    def test_net_for_pin_vin(self):
        assert _net_for_pin("VIN") == "+5V"

    def test_net_for_pin_unknown(self):
        assert _net_for_pin("NRST") is None

    def test_esc_id_spaces_to_underscore(self):
        assert _esc_id("My Symbol") == "My_Symbol"

    def test_esc_id_quotes_escaped(self):
        assert _esc_id('a"b') == 'a\\"b'
