# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the deterministic graph builder."""

from pathlib import Path

import pytest

from boardsmith_fw.analysis.graph_builder import build_hardware_graph
from boardsmith_fw.models.hardware_graph import MCUFamily
from boardsmith_fw.parser.eagle_parser import parse_eagle_schematic

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _build(fixture_name: str, sch_name: str):
    path = FIXTURES / fixture_name / sch_name
    result = parse_eagle_schematic(path)
    return build_hardware_graph(str(path), result.components, result.nets)


class TestEsp32Graph:
    @pytest.fixture
    def graph(self):
        return _build("esp32_bme280_i2c", "esp32_bme280.sch")

    def test_mcu_detected(self, graph):
        assert graph.mcu is not None
        assert graph.mcu.family == MCUFamily.ESP32
        assert "ESP32" in graph.mcu.type

    def test_i2c_bus_detected(self, graph):
        assert len(graph.buses) >= 1
        i2c = next(b for b in graph.buses if b.type.value == "I2C")
        assert i2c.name == "I2C_BUS"

    def test_i2c_master_is_mcu(self, graph):
        i2c = next(b for b in graph.buses if b.type.value == "I2C")
        assert i2c.master_component_id == "U1"

    def test_i2c_slave_is_bme280(self, graph):
        i2c = next(b for b in graph.buses if b.type.value == "I2C")
        assert "U2" in i2c.slave_component_ids

    def test_passives_not_in_slaves(self, graph):
        i2c = next(b for b in graph.buses if b.type.value == "I2C")
        for sid in i2c.slave_component_ids:
            assert sid[0] != "R"
            assert sid[0] != "C"

    def test_power_domains(self, graph):
        names = {pd.name for pd in graph.power_domains}
        assert "3V3" in names
        assert "GND" in names

    def test_power_voltages(self, graph):
        pd_3v3 = next(p for p in graph.power_domains if p.name == "3V3")
        assert pd_3v3.voltage == "3.3V"

    def test_pin_mapping_sda(self, graph):
        i2c = next(b for b in graph.buses if b.type.value == "I2C")
        sda_map = next(pm for pm in i2c.pin_mapping if pm.signal == "SDA")
        assert sda_map.gpio == "21"
        assert "GPIO21" in sda_map.mcu_pin_name

    def test_pin_mapping_scl(self, graph):
        i2c = next(b for b in graph.buses if b.type.value == "I2C")
        scl_map = next(pm for pm in i2c.pin_mapping if pm.signal == "SCL")
        assert scl_map.gpio == "22"

    def test_metadata(self, graph):
        assert graph.metadata.total_components == 5
        assert graph.metadata.total_nets == 4
        assert len(graph.metadata.detected_buses) >= 1


class TestStm32Graph:
    @pytest.fixture
    def graph(self):
        return _build("stm32f4_bme280_i2c", "stm32f4_bme280.sch")

    def test_mcu_detected(self, graph):
        assert graph.mcu is not None
        assert graph.mcu.family == MCUFamily.STM32

    def test_i2c_bus_detected(self, graph):
        i2c = next(b for b in graph.buses if b.type.value == "I2C")
        assert i2c.master_component_id == "U1"
        assert "U2" in i2c.slave_component_ids

    def test_stm32_pin_mapping(self, graph):
        i2c = next(b for b in graph.buses if b.type.value == "I2C")
        sda_map = next(pm for pm in i2c.pin_mapping if pm.signal == "SDA")
        assert sda_map.gpio == "PB7"
        scl_map = next(pm for pm in i2c.pin_mapping if pm.signal == "SCL")
        assert scl_map.gpio == "PB6"


class TestMultiBusGraph:
    """Test multi-bus fixture: ESP32 + I2C (BME280) + SPI (W25Q128) + UART (NEO-M8N)."""

    @pytest.fixture
    def graph(self):
        return _build("esp32_multi_bus", "esp32_multi_bus.sch")

    def test_mcu_detected(self, graph):
        assert graph.mcu is not None
        assert graph.mcu.family == MCUFamily.ESP32

    def test_three_buses_detected(self, graph):
        bus_types = {b.type.value for b in graph.buses}
        assert "I2C" in bus_types
        assert "SPI" in bus_types
        assert "UART" in bus_types

    def test_i2c_bus(self, graph):
        i2c = next(b for b in graph.buses if b.type.value == "I2C")
        assert i2c.master_component_id == "U1"
        assert "U2" in i2c.slave_component_ids

    def test_spi_bus(self, graph):
        spi = next(b for b in graph.buses if b.type.value == "SPI")
        assert spi.master_component_id == "U1"
        assert "U3" in spi.slave_component_ids

    def test_uart_bus(self, graph):
        uart = next(b for b in graph.buses if b.type.value == "UART")
        assert uart.master_component_id == "U1"
        assert "U4" in uart.slave_component_ids

    def test_i2c_pin_mapping(self, graph):
        i2c = next(b for b in graph.buses if b.type.value == "I2C")
        sda_map = next(pm for pm in i2c.pin_mapping if pm.signal == "SDA")
        assert sda_map.gpio == "21"
        scl_map = next(pm for pm in i2c.pin_mapping if pm.signal == "SCL")
        assert scl_map.gpio == "22"

    def test_spi_pin_mapping(self, graph):
        spi = next(b for b in graph.buses if b.type.value == "SPI")
        mosi_map = next(pm for pm in spi.pin_mapping if pm.signal == "MOSI")
        assert mosi_map.gpio == "23"
        miso_map = next(pm for pm in spi.pin_mapping if pm.signal == "MISO")
        assert miso_map.gpio == "19"
        sck_map = next(pm for pm in spi.pin_mapping if pm.signal == "SCK")
        assert sck_map.gpio == "18"

    def test_uart_pin_mapping(self, graph):
        uart = next(b for b in graph.buses if b.type.value == "UART")
        tx_map = next(pm for pm in uart.pin_mapping if pm.signal == "TX")
        assert tx_map.gpio == "17"
        rx_map = next(pm for pm in uart.pin_mapping if pm.signal == "RX")
        assert rx_map.gpio == "16"

    def test_passives_excluded(self, graph):
        for bus in graph.buses:
            for sid in bus.slave_component_ids:
                assert sid[0] not in ("R", "C", "L")

    def test_no_unconnected_irq(self, graph):
        # GPIO4/INT pin exists on ESP32 but no INT net connects it to a source
        # IRQ lines require both source and target components on the same net
        for irq in graph.irq_lines:
            assert irq.target_component_id == "U1"

    def test_power_domains(self, graph):
        names = {pd.name for pd in graph.power_domains}
        assert "3V3" in names
        assert "GND" in names

    def test_metadata(self, graph):
        assert graph.metadata.total_components == 6  # U1, U2, U3, U4, R1, R2
        assert len(graph.metadata.detected_buses) >= 3
