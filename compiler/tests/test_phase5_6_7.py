# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Phase 5.6 (per-slave I2C address tracking) and 5.7 (electrical ratings)."""

from boardsmith_fw.analysis.constraint_solver import solve_constraints
from boardsmith_fw.models.component_knowledge import ComponentKnowledge, ElectricalRatings, InterfaceType
from boardsmith_fw.models.hardware_graph import HardwareGraph
from boardsmith_fw.models.hir import (
    HIR,
    BusContract,
    ConstraintSeverity,
    ConstraintStatus,
    ElectricalSpec,
    I2CSpec,
    VoltageLevel,
)


def _empty_graph():
    return HardwareGraph(source="test")


# ===========================================================================
# 5.6: Per-Slave I2C Address Tracking
# ===========================================================================


class TestPerSlaveI2CAddresses:
    """C2 now uses per-slave address map from BusContract.slave_addresses."""

    def test_unique_addresses_pass(self):
        """Two slaves with different addresses should PASS."""
        hir = HIR(
            bus_contracts=[
                BusContract(
                    bus_name="I2C",
                    bus_type="I2C",
                    master_id="MCU",
                    slave_ids=["SENS_A", "SENS_B"],
                    i2c=I2CSpec(address="0x76"),
                    slave_addresses={"SENS_A": "0x76", "SENS_B": "0x48"},
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        addr_constraints = [c for c in hir.constraints if "i2c_addr" in c.id]
        conflicts = [c for c in addr_constraints if c.status == ConstraintStatus.FAIL]
        assert len(conflicts) == 0

        passes = [c for c in addr_constraints if c.status == ConstraintStatus.PASS]
        assert len(passes) == 2  # one per address

    def test_duplicate_addresses_fail(self):
        """Two slaves with the same address should FAIL with ERROR."""
        hir = HIR(
            bus_contracts=[
                BusContract(
                    bus_name="I2C",
                    bus_type="I2C",
                    master_id="MCU",
                    slave_ids=["SENS_A", "SENS_B"],
                    i2c=I2CSpec(address="0x76"),
                    slave_addresses={"SENS_A": "0x76", "SENS_B": "0x76"},
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        addr_constraints = [c for c in hir.constraints if "i2c_addr" in c.id]
        conflicts = [c for c in addr_constraints if c.status == ConstraintStatus.FAIL]
        assert len(conflicts) == 1
        assert conflicts[0].severity == ConstraintSeverity.ERROR
        assert "0x76" in conflicts[0].description
        assert "SENS_A" in conflicts[0].description or "SENS_B" in conflicts[0].description

    def test_conflict_message_names_both_slaves(self):
        """Conflict description should mention both slaves."""
        hir = HIR(
            bus_contracts=[
                BusContract(
                    bus_name="I2C",
                    bus_type="I2C",
                    master_id="MCU",
                    slave_ids=["SENS_A", "SENS_B"],
                    i2c=I2CSpec(address="0x76"),
                    slave_addresses={"SENS_A": "0x76", "SENS_B": "0x76"},
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        conflict = next(c for c in hir.constraints if c.status == ConstraintStatus.FAIL and "i2c_addr" in c.id)
        assert "SENS_A" in conflict.description
        assert "SENS_B" in conflict.description

    def test_unknown_slave_address_reported(self):
        """A slave without a known address should appear as UNKNOWN."""
        hir = HIR(
            bus_contracts=[
                BusContract(
                    bus_name="I2C",
                    bus_type="I2C",
                    master_id="MCU",
                    slave_ids=["SENS_A", "MYSTERY"],
                    i2c=I2CSpec(address="0x76"),
                    slave_addresses={"SENS_A": "0x76"},  # MYSTERY not in map
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        unknowns = [
            c for c in hir.constraints
            if "i2c_addr" in c.id and c.status == ConstraintStatus.UNKNOWN
        ]
        assert len(unknowns) == 1
        assert "MYSTERY" in unknowns[0].description

    def test_three_slaves_two_conflicts(self):
        """Three slaves where two share the same address → one conflict constraint."""
        hir = HIR(
            bus_contracts=[
                BusContract(
                    bus_name="I2C",
                    bus_type="I2C",
                    master_id="MCU",
                    slave_ids=["A", "B", "C"],
                    i2c=I2CSpec(address="0x76"),
                    slave_addresses={"A": "0x76", "B": "0x76", "C": "0x48"},
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        addr_constraints = [c for c in hir.constraints if "i2c_addr" in c.id]
        conflicts = [c for c in addr_constraints if c.status == ConstraintStatus.FAIL]
        passes = [c for c in addr_constraints if c.status == ConstraintStatus.PASS]

        assert len(conflicts) == 1  # only 0x76 is a conflict
        assert len(passes) == 1    # 0x48 is fine

    def test_empty_slave_addresses_falls_back_to_bus_address(self):
        """If slave_addresses is empty, fall back to bus-level i2c.address."""
        hir = HIR(
            bus_contracts=[
                BusContract(
                    bus_name="I2C",
                    bus_type="I2C",
                    master_id="MCU",
                    slave_ids=["SENS"],
                    i2c=I2CSpec(address="0x76"),
                    slave_addresses={},  # empty
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        addr_constraints = [c for c in hir.constraints if "i2c_addr" in c.id]
        assert len(addr_constraints) == 1
        assert addr_constraints[0].status == ConstraintStatus.PASS
        assert "no per-slave data" in addr_constraints[0].description

    def test_no_conflict_does_not_invalidate_hir(self):
        """Unique addresses should not make the HIR invalid."""
        hir = HIR(
            bus_contracts=[
                BusContract(
                    bus_name="I2C",
                    bus_type="I2C",
                    master_id="MCU",
                    slave_ids=["A", "B"],
                    i2c=I2CSpec(address="0x76"),
                    slave_addresses={"A": "0x76", "B": "0x48"},
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())
        assert hir.is_valid()

    def test_conflict_invalidates_hir(self):
        """Address conflict (ERROR severity) should invalidate the HIR."""
        hir = HIR(
            bus_contracts=[
                BusContract(
                    bus_name="I2C",
                    bus_type="I2C",
                    master_id="MCU",
                    slave_ids=["A", "B"],
                    i2c=I2CSpec(address="0x76"),
                    slave_addresses={"A": "0x76", "B": "0x76"},
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())
        assert not hir.is_valid()

    def test_hir_builder_populates_slave_addresses(self):
        """HIR builder should populate slave_addresses from ComponentKnowledge."""
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

        i2c_bus = next((bc for bc in hir.bus_contracts if bc.i2c), None)
        assert i2c_bus is not None
        # BME280 has i2c_address = "0x76" in builtin KB, so slave_addresses should be populated
        assert len(i2c_bus.slave_addresses) >= 1
        assert "0x76" in i2c_bus.slave_addresses.values()


# ===========================================================================
# 5.7: Electrical Ratings in ComponentKnowledge
# ===========================================================================


class TestElectricalRatingsModel:
    """ElectricalRatings model and ComponentKnowledge integration."""

    def test_electrical_ratings_optional(self):
        """ComponentKnowledge works without electrical_ratings."""
        kn = ComponentKnowledge(
            component_id="U1",
            name="TEST",
            interface=InterfaceType.I2C,
        )
        assert kn.electrical_ratings is None

    def test_electrical_ratings_fields(self):
        er = ElectricalRatings(
            vdd_min=1.71,
            vdd_max=3.6,
            vdd_abs_max=4.25,
            current_supply_ma=0.34,
            current_supply_max_ma=1.8,
            temp_min_c=-40.0,
            temp_max_c=85.0,
            is_5v_tolerant=False,
        )
        assert er.vdd_min == 1.71
        assert er.vdd_max == 3.6
        assert er.vdd_abs_max == 4.25
        assert er.temp_min_c == -40.0
        assert er.temp_max_c == 85.0
        assert er.is_5v_tolerant is False

    def test_bme280_has_electrical_ratings(self):
        """BME280 builtin entry should now include electrical_ratings."""
        from boardsmith_fw.knowledge.builtin_db import lookup_builtin

        k = lookup_builtin("BME280")
        assert k is not None
        assert k.electrical_ratings is not None
        er = k.electrical_ratings
        assert er.vdd_min == 1.71
        assert er.vdd_max == 3.6
        assert er.vdd_abs_max == 4.25
        assert er.temp_max_c == 85.0

    def test_w25q128_has_electrical_ratings(self):
        """W25Q128 builtin entry should include electrical_ratings."""
        from boardsmith_fw.knowledge.builtin_db import lookup_builtin

        k = lookup_builtin("W25Q128JV")
        assert k is not None
        assert k.electrical_ratings is not None
        er = k.electrical_ratings
        assert er.vdd_min == 2.7
        assert er.vdd_max == 3.6
        assert er.vdd_abs_max == 4.6


class TestElectricalSpecFromRatings:
    """HIR builder populates ElectricalSpec from electrical_ratings."""

    def test_electrical_ratings_populates_abs_max(self):
        """If component has electrical_ratings, ElectricalSpec.abs_max_voltage is set."""
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

        # At least some spec should have abs_max set (from BME280 ratings)
        specs_with_abs_max = [e for e in hir.electrical_specs if e.abs_max_voltage is not None]
        assert len(specs_with_abs_max) >= 1

    def test_supply_voltage_nominal_preserved_from_power_domain(self):
        """Actual operating voltage from power domain should be kept as nominal."""
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

        # Supply voltage nominals should be actual operating voltages (3.3V), not midpoints
        for spec in hir.electrical_specs:
            if spec.supply_voltage is not None:
                assert spec.supply_voltage.nominal > 0.0
                # Should not be the midpoint of BME280 range (2.655V)
                assert abs(spec.supply_voltage.nominal - 2.655) > 0.01


class TestAbsoluteMaxConstraint:
    """C11: absolute maximum voltage check."""

    def test_within_abs_max_passes(self):
        """Supply voltage within abs_max → PASS."""
        hir = HIR(
            electrical_specs=[
                ElectricalSpec(
                    component_id="U1",
                    supply_voltage=VoltageLevel(nominal=3.3, min=1.71, max=3.6),
                    abs_max_voltage=4.25,
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        abs_constraints = [c for c in hir.constraints if "abs_max" in c.id]
        assert len(abs_constraints) == 1
        assert abs_constraints[0].status == ConstraintStatus.PASS
        assert "margin" in abs_constraints[0].description

    def test_exceeds_abs_max_fails(self):
        """Supply voltage above abs_max → FAIL with ERROR."""
        hir = HIR(
            electrical_specs=[
                ElectricalSpec(
                    component_id="U1",
                    supply_voltage=VoltageLevel(nominal=5.0, min=1.71, max=5.0),
                    abs_max_voltage=4.25,
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        abs_constraints = [c for c in hir.constraints if "abs_max" in c.id]
        assert len(abs_constraints) == 1
        assert abs_constraints[0].status == ConstraintStatus.FAIL
        assert abs_constraints[0].severity == ConstraintSeverity.ERROR
        assert "damage" in abs_constraints[0].description.lower()

    def test_exceeds_rated_max_warns(self):
        """Supply voltage above rated max but below abs_max → WARNING."""
        hir = HIR(
            electrical_specs=[
                ElectricalSpec(
                    component_id="U1",
                    supply_voltage=VoltageLevel(nominal=4.0, min=1.71, max=3.6),
                    abs_max_voltage=4.25,
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        abs_constraints = [c for c in hir.constraints if "abs_max" in c.id]
        assert len(abs_constraints) == 1
        assert abs_constraints[0].status == ConstraintStatus.FAIL
        assert abs_constraints[0].severity == ConstraintSeverity.WARNING
        assert "over_rated" in abs_constraints[0].id

    def test_no_abs_max_no_constraint(self):
        """If abs_max_voltage is None, no abs_max constraint generated."""
        hir = HIR(
            electrical_specs=[
                ElectricalSpec(
                    component_id="U1",
                    supply_voltage=VoltageLevel(nominal=3.3),
                    # no abs_max_voltage set
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        abs_constraints = [c for c in hir.constraints if "abs_max" in c.id]
        assert len(abs_constraints) == 0

    def test_no_supply_voltage_no_constraint(self):
        """If supply_voltage is None, no abs_max constraint even if abs_max set."""
        hir = HIR(
            electrical_specs=[
                ElectricalSpec(
                    component_id="U1",
                    abs_max_voltage=4.25,
                    # no supply_voltage
                ),
            ],
        )
        hir.constraints = solve_constraints(hir, _empty_graph())

        abs_constraints = [c for c in hir.constraints if "abs_max" in c.id]
        assert len(abs_constraints) == 0

    def test_abs_max_from_fixture(self):
        """Fixture should produce abs_max constraints for components with ratings."""
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

        # BME280 has electrical_ratings, so abs_max constraints should exist
        abs_constraints = [c for c in hir.constraints if "abs_max" in c.id]
        assert len(abs_constraints) >= 1

    def test_fixture_no_errors_after_5_7(self):
        """Valid fixture should still be error-free after 5.7 improvements."""
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

        errors = hir.get_errors()
        assert len(errors) == 0, f"Unexpected errors: {[e.description for e in errors]}"
