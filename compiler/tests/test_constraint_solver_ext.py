# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for constraint solver extensions: C9 (rise-time) and C10 (init phase coverage)."""

from boardsmith_fw.analysis.constraint_solver import solve_constraints
from boardsmith_fw.models.hardware_graph import HardwareGraph
from boardsmith_fw.models.hir import (
    HIR,
    BusContract,
    ConstraintSeverity,
    ConstraintStatus,
    ElectricalSpec,
    I2CSpec,
    InitContract,
    InitPhase,
    InitPhaseSpec,
    RegisterRead,
    RegisterWrite,
)


def _empty_graph():
    return HardwareGraph(source="test")


# ---------------------------------------------------------------------------
# C9: I2C rise-time checks
# ---------------------------------------------------------------------------


class TestI2CRiseTime:
    def test_explicit_rise_time_within_limit(self):
        """If I2CSpec has explicit t_rise_ns within limit, PASS."""
        hir = HIR(
            bus_contracts=[
                BusContract(
                    bus_name="I2C",
                    bus_type="I2C",
                    master_id="MCU",
                    slave_ids=["SENSOR"],
                    configured_clock_hz=100_000,
                    i2c=I2CSpec(address="0x76", t_rise_ns=500),
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        rise = [c for c in hir.constraints if "rise_time" in c.id]
        assert len(rise) == 1
        assert rise[0].status == ConstraintStatus.PASS
        assert "margin" in rise[0].description.lower()

    def test_explicit_rise_time_exceeds_limit(self):
        """If t_rise_ns exceeds the mode limit, FAIL."""
        hir = HIR(
            bus_contracts=[
                BusContract(
                    bus_name="I2C",
                    bus_type="I2C",
                    master_id="MCU",
                    slave_ids=["SENSOR"],
                    configured_clock_hz=400_000,  # fast-mode → 300ns max
                    i2c=I2CSpec(address="0x76", t_rise_ns=500),
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        rise = [c for c in hir.constraints if "rise_time" in c.id]
        assert len(rise) == 1
        assert rise[0].status == ConstraintStatus.FAIL
        assert rise[0].severity == ConstraintSeverity.ERROR
        assert "fast" in rise[0].description.lower()

    def test_calculated_rise_time_passes(self):
        """Rise time calculated from R=4700 and small capacitance should pass."""
        hir = HIR(
            bus_contracts=[
                BusContract(
                    bus_name="I2C",
                    bus_type="I2C",
                    master_id="MCU",
                    slave_ids=["SENSOR"],
                    configured_clock_hz=100_000,
                    i2c=I2CSpec(address="0x76", pullup_ohm_min=4000, pullup_ohm_max=5000),
                ),
            ],
            electrical_specs=[
                ElectricalSpec(component_id="MCU", input_capacitance_pf=5.0),
                ElectricalSpec(component_id="SENSOR", input_capacitance_pf=5.0),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        rise = [c for c in hir.constraints if "rise_time" in c.id]
        assert len(rise) == 1
        # R_mid=4500, C_total=5+5+10=20pF => t_rise = 0.8473*4500*20e-12 = ~76ns
        # standard-mode limit = 1000ns → should pass easily
        assert rise[0].status == ConstraintStatus.PASS

    def test_calculated_rise_time_exceeds_fast_mode(self):
        """High capacitance + large pullup should fail at fast-mode."""
        hir = HIR(
            bus_contracts=[
                BusContract(
                    bus_name="I2C",
                    bus_type="I2C",
                    master_id="MCU",
                    slave_ids=["SENSOR"],
                    configured_clock_hz=400_000,  # fast-mode → 300ns max
                    i2c=I2CSpec(
                        address="0x76",
                        pullup_ohm_min=8000,
                        pullup_ohm_max=12000,
                    ),
                ),
            ],
            electrical_specs=[
                ElectricalSpec(component_id="MCU", input_capacitance_pf=10.0),
                ElectricalSpec(component_id="SENSOR", input_capacitance_pf=30.0),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        rise = [c for c in hir.constraints if "rise_time" in c.id]
        assert len(rise) == 1
        # R_mid=10000, C_total=10+30+10=50pF => t_rise = 0.8473*10000*50e-12 = ~424ns
        # fast-mode limit = 300ns → should FAIL
        assert rise[0].status == ConstraintStatus.FAIL
        assert "reduce pullup" in rise[0].description.lower()

    def test_no_capacitance_data_unknown(self):
        """If no pin capacitance data and no explicit t_rise, result is UNKNOWN."""
        hir = HIR(
            bus_contracts=[
                BusContract(
                    bus_name="I2C",
                    bus_type="I2C",
                    master_id="MCU",
                    slave_ids=["SENSOR"],
                    configured_clock_hz=100_000,
                    i2c=I2CSpec(address="0x76"),
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        rise = [c for c in hir.constraints if "rise_time" in c.id]
        assert len(rise) == 1
        assert rise[0].status == ConstraintStatus.UNKNOWN

    def test_fast_plus_mode_limit(self):
        """Clock > 400kHz uses fast_plus limit of 120ns."""
        hir = HIR(
            bus_contracts=[
                BusContract(
                    bus_name="I2C",
                    bus_type="I2C",
                    master_id="MCU",
                    slave_ids=["SENSOR"],
                    configured_clock_hz=1_000_000,  # fast_plus → 120ns max
                    i2c=I2CSpec(address="0x76", t_rise_ns=100),
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        rise = [c for c in hir.constraints if "rise_time" in c.id]
        assert len(rise) == 1
        assert rise[0].status == ConstraintStatus.PASS
        assert "fast_plus" in rise[0].description

    def test_tight_margin_warning(self):
        """Rise time > 80% of limit should PASS but with WARNING severity."""
        hir = HIR(
            bus_contracts=[
                BusContract(
                    bus_name="I2C",
                    bus_type="I2C",
                    master_id="MCU",
                    slave_ids=["SENSOR"],
                    configured_clock_hz=100_000,
                    # Need R and C to produce ~850ns (85% of 1000ns)
                    # t = 0.8473 * R * C → R=10000, C=90pF+10=100pF → 0.8473*10000*100e-12=847ns
                    i2c=I2CSpec(
                        address="0x76",
                        pullup_ohm_min=9000,
                        pullup_ohm_max=11000,
                    ),
                ),
            ],
            electrical_specs=[
                ElectricalSpec(component_id="MCU", input_capacitance_pf=45.0),
                ElectricalSpec(component_id="SENSOR", input_capacitance_pf=45.0),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        rise = [c for c in hir.constraints if "rise_time" in c.id]
        assert len(rise) == 1
        assert rise[0].status == ConstraintStatus.PASS
        assert rise[0].severity == ConstraintSeverity.WARNING  # tight margin

    def test_non_i2c_bus_skipped(self):
        """SPI buses should not generate rise-time constraints."""
        from boardsmith_fw.models.hir import SPISpec

        hir = HIR(
            bus_contracts=[
                BusContract(
                    bus_name="SPI",
                    bus_type="SPI",
                    master_id="MCU",
                    slave_ids=["FLASH"],
                    configured_clock_hz=10_000_000,
                    spi=SPISpec(),
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        rise = [c for c in hir.constraints if "rise_time" in c.id]
        assert len(rise) == 0


# ---------------------------------------------------------------------------
# C10: Init phase coverage checks
# ---------------------------------------------------------------------------


class TestInitPhaseCoverage:
    def test_complete_init_passes(self):
        """Init with RESET phase, writes, and reads should PASS."""
        hir = HIR(
            init_contracts=[
                InitContract(
                    component_id="SENSOR",
                    component_name="BME280",
                    phases=[
                        InitPhaseSpec(
                            phase=InitPhase.RESET,
                            order=0,
                            writes=[RegisterWrite(reg_addr="0xE0", value="0xB6", description="soft reset")],
                        ),
                        InitPhaseSpec(
                            phase=InitPhase.VERIFY,
                            order=1,
                            reads=[RegisterRead(reg_addr="0xD0", expected_value="0x60", description="chip ID")],
                        ),
                        InitPhaseSpec(
                            phase=InitPhase.CONFIGURE,
                            order=2,
                            writes=[RegisterWrite(reg_addr="0xF4", value="0x27", description="ctrl_meas")],
                        ),
                    ],
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        cov = [c for c in hir.constraints if "init_coverage" in c.id]
        assert len(cov) == 1
        assert cov[0].status == ConstraintStatus.PASS
        assert "3 phases" in cov[0].description

    def test_empty_phases_warns(self):
        """Init with no phases should warn."""
        hir = HIR(
            init_contracts=[
                InitContract(
                    component_id="SENSOR",
                    component_name="BME280",
                    phases=[],
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        cov = [c for c in hir.constraints if "init_coverage" in c.id]
        assert len(cov) == 1
        assert cov[0].status == ConstraintStatus.FAIL
        assert "no init phases" in cov[0].description.lower()

    def test_no_writes_warns(self):
        """Init with only reads and no writes should flag missing config."""
        hir = HIR(
            init_contracts=[
                InitContract(
                    component_id="SENSOR",
                    component_name="BME280",
                    phases=[
                        InitPhaseSpec(
                            phase=InitPhase.VERIFY,
                            order=0,
                            reads=[RegisterRead(reg_addr="0xD0", description="chip ID")],
                        ),
                    ],
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        cov = [c for c in hir.constraints if "init_coverage" in c.id]
        assert len(cov) == 1
        assert cov[0].status == ConstraintStatus.FAIL
        assert "no register writes" in cov[0].description.lower()

    def test_no_reset_phase_warns(self):
        """Init with writes but no RESET phase should flag stale state risk."""
        hir = HIR(
            init_contracts=[
                InitContract(
                    component_id="SENSOR",
                    component_name="BME280",
                    phases=[
                        InitPhaseSpec(
                            phase=InitPhase.CONFIGURE,
                            order=0,
                            writes=[RegisterWrite(reg_addr="0xF4", value="0x27")],
                            reads=[RegisterRead(reg_addr="0xD0", expected_value="0x60")],
                        ),
                    ],
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        cov = [c for c in hir.constraints if "init_coverage" in c.id]
        assert len(cov) == 1
        assert cov[0].status == ConstraintStatus.FAIL
        assert "reset" in cov[0].description.lower()

    def test_no_reads_warns(self):
        """Init with writes but no reads should flag missing verification."""
        hir = HIR(
            init_contracts=[
                InitContract(
                    component_id="SENSOR",
                    component_name="BME280",
                    phases=[
                        InitPhaseSpec(
                            phase=InitPhase.RESET,
                            order=0,
                            writes=[RegisterWrite(reg_addr="0xE0", value="0xB6")],
                        ),
                        InitPhaseSpec(
                            phase=InitPhase.CONFIGURE,
                            order=1,
                            writes=[RegisterWrite(reg_addr="0xF4", value="0x27")],
                        ),
                    ],
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        cov = [c for c in hir.constraints if "init_coverage" in c.id]
        assert len(cov) == 1
        assert cov[0].status == ConstraintStatus.FAIL
        assert "no register reads" in cov[0].description.lower() or "no chip id" in cov[0].description.lower()

    def test_multiple_issues_combined(self):
        """Init with writes but no RESET and no reads should list both issues."""
        hir = HIR(
            init_contracts=[
                InitContract(
                    component_id="SENSOR",
                    component_name="BME280",
                    phases=[
                        InitPhaseSpec(
                            phase=InitPhase.CONFIGURE,
                            order=0,
                            writes=[RegisterWrite(reg_addr="0xF4", value="0x27")],
                        ),
                    ],
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        cov = [c for c in hir.constraints if "init_coverage" in c.id]
        assert len(cov) == 1
        assert cov[0].status == ConstraintStatus.FAIL
        desc = cov[0].description.lower()
        assert "reset" in desc
        assert "read" in desc

    def test_no_init_contracts_no_coverage_checks(self):
        """If there are no init contracts, no coverage constraints."""
        hir = HIR()
        hir.constraints = solve_constraints(hir, _empty_graph())

        cov = [c for c in hir.constraints if "init_coverage" in c.id]
        assert len(cov) == 0


# ---------------------------------------------------------------------------
# Integration with real fixtures
# ---------------------------------------------------------------------------


class TestNewConstraintsWithFixture:
    def _make_esp32_hir(self):
        from pathlib import Path

        from boardsmith_fw.analysis.graph_builder import build_hardware_graph
        from boardsmith_fw.analysis.hir_builder import build_hir
        from boardsmith_fw.knowledge.resolver import resolve_knowledge
        from boardsmith_fw.parser.eagle_parser import parse_eagle_schematic

        fixtures = Path(__file__).parent.parent / "fixtures"
        path = fixtures / "esp32_bme280_i2c" / "esp32_bme280.sch"
        parsed = parse_eagle_schematic(path)
        graph = build_hardware_graph(str(path), parsed.components, parsed.nets)
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)
        hir.constraints = solve_constraints(hir, graph)
        return hir

    def test_rise_time_constraint_present(self):
        hir = self._make_esp32_hir()
        rise = [c for c in hir.constraints if "rise_time" in c.id]
        assert len(rise) >= 1

    def test_init_coverage_constraint_present(self):
        hir = self._make_esp32_hir()
        cov = [c for c in hir.constraints if "init_coverage" in c.id]
        assert len(cov) >= 1

    def test_no_hard_errors_with_new_checks(self):
        """Valid fixture should still pass with the new checks."""
        hir = self._make_esp32_hir()
        errors = hir.get_errors()
        assert len(errors) == 0, f"Unexpected errors: {[e.description for e in errors]}"
