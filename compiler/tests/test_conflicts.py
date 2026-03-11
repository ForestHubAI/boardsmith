# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the bus conflict detector."""

from boardsmith_fw.analysis.conflict_detector import detect_conflicts
from boardsmith_fw.models.component_knowledge import ComponentKnowledge, InterfaceType
from boardsmith_fw.models.hardware_graph import (
    Bus,
    BusPinMapping,
    BusType,
    Component,
    HardwareGraph,
    MCUFamily,
    MCUInfo,
    Net,
    NetPin,
)


def _make_graph(buses=None, components=None, nets=None, power_domains=None):
    return HardwareGraph(
        source="test",
        mcu=MCUInfo(component_id="U1", type="ESP32", family=MCUFamily.ESP32),
        components=components or [],
        nets=nets or [],
        buses=buses or [],
        power_domains=power_domains or [],
    )


class TestI2CCollision:
    def test_no_collision(self):
        buses = [Bus(
            name="I2C_BUS", type=BusType.I2C, nets=["SDA", "SCL"],
            master_component_id="U1", slave_component_ids=["U2", "U3"],
        )]
        graph = _make_graph(buses=buses)
        knowledge = [
            ComponentKnowledge(component_id="U2", name="BME280", interface=InterfaceType.I2C, i2c_address="0x76"),
            ComponentKnowledge(component_id="U3", name="BMP388", interface=InterfaceType.I2C, i2c_address="0x77"),
        ]
        conflicts = detect_conflicts(graph, knowledge)
        collisions = [c for c in conflicts if c.category == "i2c_collision"]
        assert len(collisions) == 0

    def test_collision_detected(self):
        buses = [Bus(
            name="I2C_BUS", type=BusType.I2C, nets=["SDA", "SCL"],
            master_component_id="U1", slave_component_ids=["U2", "U3"],
        )]
        graph = _make_graph(buses=buses)
        knowledge = [
            ComponentKnowledge(component_id="U2", name="BME280_1", interface=InterfaceType.I2C, i2c_address="0x76"),
            ComponentKnowledge(component_id="U3", name="BME280_2", interface=InterfaceType.I2C, i2c_address="0x76"),
        ]
        conflicts = detect_conflicts(graph, knowledge)
        collisions = [c for c in conflicts if c.category == "i2c_collision"]
        assert len(collisions) == 1
        assert "0X76" in collisions[0].message.upper()
        assert collisions[0].severity == "error"


class TestPinConflict:
    def test_no_conflict(self):
        buses = [
            Bus(name="I2C_BUS", type=BusType.I2C, nets=["SDA", "SCL"],
                pin_mapping=[
                    BusPinMapping(signal="SDA", net="SDA", mcu_pin_name="GPIO21", gpio="21"),
                    BusPinMapping(signal="SCL", net="SCL", mcu_pin_name="GPIO22", gpio="22"),
                ]),
            Bus(name="SPI_BUS", type=BusType.SPI, nets=["MOSI", "MISO", "SCK"],
                pin_mapping=[
                    BusPinMapping(signal="MOSI", net="MOSI", mcu_pin_name="GPIO23", gpio="23"),
                    BusPinMapping(signal="MISO", net="MISO", mcu_pin_name="GPIO19", gpio="19"),
                    BusPinMapping(signal="SCK", net="SCK", mcu_pin_name="GPIO18", gpio="18"),
                ]),
        ]
        graph = _make_graph(buses=buses)
        conflicts = detect_conflicts(graph)
        pin_conflicts = [c for c in conflicts if c.category == "pin_conflict"]
        assert len(pin_conflicts) == 0

    def test_conflict_detected(self):
        buses = [
            Bus(name="I2C_BUS", type=BusType.I2C, nets=["SDA", "SCL"],
                pin_mapping=[
                    BusPinMapping(signal="SDA", net="SDA", mcu_pin_name="GPIO21", gpio="21"),
                ]),
            Bus(name="SPI_BUS", type=BusType.SPI, nets=["MOSI"],
                pin_mapping=[
                    BusPinMapping(signal="MOSI", net="MOSI", mcu_pin_name="GPIO21", gpio="21"),
                ]),
        ]
        graph = _make_graph(buses=buses)
        conflicts = detect_conflicts(graph)
        pin_conflicts = [c for c in conflicts if c.category == "pin_conflict"]
        assert len(pin_conflicts) == 1
        assert "21" in pin_conflicts[0].message


class TestMissingPullups:
    def test_pullup_present(self):
        components = [
            Component(id="U1", name="U1", value="ESP32"),
            Component(id="U2", name="U2", value="BME280"),
            Component(id="R1", name="R1", value="4.7k"),
        ]
        nets = [
            Net(name="SDA", pins=[
                NetPin(component_id="U1", pin_name="SDA"),
                NetPin(component_id="U2", pin_name="SDA"),
                NetPin(component_id="R1", pin_name="1"),
            ]),
        ]
        buses = [Bus(name="I2C_BUS", type=BusType.I2C, nets=["SDA", "SCL"])]
        graph = _make_graph(buses=buses, components=components, nets=nets)
        conflicts = detect_conflicts(graph)
        pullups = [c for c in conflicts if c.category == "missing_pullup"]
        # SDA has a resistor, so no warning for SDA.
        # SCL net doesn't exist in nets list, so it's skipped
        assert not any("SDA" in c.message for c in pullups)

    def test_pullup_missing(self):
        components = [
            Component(id="U1", name="U1", value="ESP32"),
            Component(id="U2", name="U2", value="BME280"),
        ]
        nets = [
            Net(name="SDA", pins=[
                NetPin(component_id="U1", pin_name="SDA"),
                NetPin(component_id="U2", pin_name="SDA"),
            ]),
        ]
        buses = [Bus(name="I2C_BUS", type=BusType.I2C, nets=["SDA"])]
        graph = _make_graph(buses=buses, components=components, nets=nets)
        conflicts = detect_conflicts(graph)
        pullups = [c for c in conflicts if c.category == "missing_pullup"]
        assert len(pullups) == 1
        assert "SDA" in pullups[0].message
        assert pullups[0].severity == "warning"
