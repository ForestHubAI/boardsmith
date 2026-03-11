# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the timing constraints engine."""

from boardsmith_fw.analysis.timing_engine import (
    get_required_delays,
    validate_timing,
)
from boardsmith_fw.models.component_knowledge import (
    ComponentKnowledge,
    InitStep,
    InterfaceType,
    TimingConstraint,
)
from boardsmith_fw.models.hardware_graph import (
    Bus,
    BusType,
    HardwareGraph,
    MCUFamily,
    MCUInfo,
)


def _make_graph(buses=None):
    return HardwareGraph(
        source="test",
        mcu=MCUInfo(component_id="U1", type="ESP32", family=MCUFamily.ESP32),
        components=[],
        nets=[],
        buses=buses or [],
    )


class TestI2CTiming:
    def test_within_limits(self):
        buses = [Bus(
            name="I2C_BUS", type=BusType.I2C, nets=["SDA", "SCL"],
            slave_component_ids=["U2"],
        )]
        graph = _make_graph(buses=buses)
        knowledge = [ComponentKnowledge(
            component_id="U2", name="BME280",
            interface=InterfaceType.I2C,
            timing_constraints=[
                TimingConstraint(
                    parameter="I2C clock frequency", max="3400000", unit="Hz"
                ),
            ],
        )]
        issues = validate_timing(graph, knowledge, i2c_freq=100_000)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_exceeds_max_frequency(self):
        buses = [Bus(
            name="I2C_BUS", type=BusType.I2C, nets=["SDA", "SCL"],
            slave_component_ids=["U2"],
        )]
        graph = _make_graph(buses=buses)
        knowledge = [ComponentKnowledge(
            component_id="U2", name="SLOW_DEVICE",
            interface=InterfaceType.I2C,
            timing_constraints=[
                TimingConstraint(
                    parameter="I2C clock frequency", max="100000", unit="Hz"
                ),
            ],
        )]
        issues = validate_timing(graph, knowledge, i2c_freq=400_000)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 1
        assert "400000" in errors[0].message
        assert "100000" in errors[0].message

    def test_near_limit_warning(self):
        buses = [Bus(
            name="I2C_BUS", type=BusType.I2C, nets=["SDA", "SCL"],
            slave_component_ids=["U2"],
        )]
        graph = _make_graph(buses=buses)
        knowledge = [ComponentKnowledge(
            component_id="U2", name="SENSOR",
            interface=InterfaceType.I2C,
            timing_constraints=[
                TimingConstraint(
                    parameter="I2C clock frequency", max="400000", unit="Hz"
                ),
            ],
        )]
        # 380kHz is >90% of 400kHz
        issues = validate_timing(graph, knowledge, i2c_freq=380_000)
        warnings = [i for i in issues if i.severity == "warning"]
        assert len(warnings) == 1


class TestSPITiming:
    def test_exceeds_spi_max(self):
        buses = [Bus(
            name="SPI_BUS", type=BusType.SPI, nets=["MOSI", "MISO", "SCK"],
            slave_component_ids=["U3"],
        )]
        graph = _make_graph(buses=buses)
        knowledge = [ComponentKnowledge(
            component_id="U3", name="W25Q128",
            interface=InterfaceType.SPI,
            timing_constraints=[
                TimingConstraint(
                    parameter="SPI clock frequency", max="133000000", unit="Hz"
                ),
            ],
        )]
        # 200MHz exceeds 133MHz
        issues = validate_timing(graph, knowledge, spi_freq=200_000_000)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 1

    def test_within_spi_limits(self):
        buses = [Bus(
            name="SPI_BUS", type=BusType.SPI, nets=["MOSI", "MISO", "SCK"],
            slave_component_ids=["U3"],
        )]
        graph = _make_graph(buses=buses)
        knowledge = [ComponentKnowledge(
            component_id="U3", name="W25Q128",
            interface=InterfaceType.SPI,
            timing_constraints=[
                TimingConstraint(
                    parameter="SPI clock frequency", max="133000000", unit="Hz"
                ),
            ],
        )]
        issues = validate_timing(graph, knowledge, spi_freq=40_000_000)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0


class TestRequiredDelays:
    def test_extracts_delays(self):
        knowledge = [ComponentKnowledge(
            component_id="U2", name="BME280",
            init_sequence=[
                InitStep(order=1, reg_addr="0xE0", value="0xB6",
                         description="Soft reset"),
                InitStep(order=2, description="Wait", delay_ms=10),
                InitStep(order=3, reg_addr="0xF4", value="0x27",
                         description="Config"),
            ],
        )]
        delays = get_required_delays(knowledge)
        assert len(delays) == 1
        assert delays[0] == ("U2", "Wait", 10)

    def test_no_delays(self):
        knowledge = [ComponentKnowledge(
            component_id="U2", name="SIMPLE",
            init_sequence=[
                InitStep(order=1, reg_addr="0x00", value="0xFF",
                         description="Write"),
            ],
        )]
        delays = get_required_delays(knowledge)
        assert len(delays) == 0
