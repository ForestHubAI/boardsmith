# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the Hardware Intermediate Representation (HIR)."""

from pathlib import Path

from boardsmith_fw.analysis.constraint_solver import solve_constraints
from boardsmith_fw.analysis.graph_builder import build_hardware_graph
from boardsmith_fw.analysis.hir_builder import build_hir
from boardsmith_fw.knowledge.resolver import resolve_knowledge
from boardsmith_fw.models.hardware_graph import (
    HardwareGraph,
)
from boardsmith_fw.models.hir import (
    HIR,
    Constraint,
    ConstraintSeverity,
    ConstraintStatus,
    I2CSpec,
    InitPhase,
    PowerSequence,
    VoltageLevel,
)
from boardsmith_fw.parser.eagle_parser import parse_eagle_schematic

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# HIR Model tests
# ---------------------------------------------------------------------------


class TestVoltageLevel:
    def test_contains_in_range(self):
        v = VoltageLevel(nominal=3.3, min=3.0, max=3.6)
        assert v.contains(3.3) is True
        assert v.contains(3.0) is True
        assert v.contains(3.6) is True

    def test_contains_out_of_range(self):
        v = VoltageLevel(nominal=3.3, min=3.0, max=3.6)
        assert v.contains(5.0) is False
        assert v.contains(1.8) is False

    def test_contains_default_tolerance(self):
        v = VoltageLevel(nominal=3.3)
        assert v.contains(3.3) is True
        assert v.contains(3.0) is True  # 3.3 * 0.9 = 2.97
        assert v.contains(5.0) is False


class TestHIRModel:
    def test_is_valid_empty(self):
        hir = HIR()
        assert hir.is_valid() is True

    def test_is_valid_with_passing(self):
        hir = HIR(constraints=[
            Constraint(
                id="test.1",
                category="electrical",
                description="test",
                status=ConstraintStatus.PASS,
            ),
        ])
        assert hir.is_valid() is True

    def test_is_valid_with_error(self):
        hir = HIR(constraints=[
            Constraint(
                id="test.1",
                category="electrical",
                description="voltage mismatch",
                severity=ConstraintSeverity.ERROR,
                status=ConstraintStatus.FAIL,
            ),
        ])
        assert hir.is_valid() is False

    def test_is_valid_warning_doesnt_fail(self):
        hir = HIR(constraints=[
            Constraint(
                id="test.1",
                category="electrical",
                description="missing pullup",
                severity=ConstraintSeverity.WARNING,
                status=ConstraintStatus.FAIL,
            ),
        ])
        assert hir.is_valid() is True

    def test_get_errors(self):
        hir = HIR(constraints=[
            Constraint(id="1", category="e", description="ok", status=ConstraintStatus.PASS),
            Constraint(
                id="2", category="e", description="bad",
                severity=ConstraintSeverity.ERROR, status=ConstraintStatus.FAIL,
            ),
            Constraint(
                id="3", category="e", description="warn",
                severity=ConstraintSeverity.WARNING, status=ConstraintStatus.FAIL,
            ),
        ])
        errors = hir.get_errors()
        assert len(errors) == 1
        assert errors[0].id == "2"


class TestPowerSequence:
    def test_startup_order_empty(self):
        ps = PowerSequence()
        assert ps.get_startup_order() == []

    def test_startup_order_linear(self):
        from boardsmith_fw.models.hir import PowerDependency, PowerRail

        ps = PowerSequence(
            rails=[
                PowerRail(name="3V3", voltage=VoltageLevel(nominal=3.3)),
                PowerRail(name="1V8", voltage=VoltageLevel(nominal=1.8)),
            ],
            dependencies=[
                PowerDependency(source="3V3", target="1V8", min_delay_ms=1),
            ],
        )
        order = ps.get_startup_order()
        assert order == ["3V3", "1V8"]


# ---------------------------------------------------------------------------
# HIR Builder tests — from real fixtures
# ---------------------------------------------------------------------------


def _make_esp32_graph():
    path = FIXTURES / "esp32_bme280_i2c" / "esp32_bme280.sch"
    parsed = parse_eagle_schematic(path)
    return build_hardware_graph(str(path), parsed.components, parsed.nets)


def _make_rp2040_graph():
    path = FIXTURES / "rp2040_bme280_i2c" / "rp2040_bme280.sch"
    parsed = parse_eagle_schematic(path)
    return build_hardware_graph(str(path), parsed.components, parsed.nets)


class TestHIRBuilder:
    def test_builds_from_esp32_fixture(self):
        graph = _make_esp32_graph()
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)

        assert len(hir.bus_contracts) >= 1
        assert len(hir.electrical_specs) >= 1

    def test_bus_contract_has_i2c_spec(self):
        graph = _make_esp32_graph()
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)

        i2c_contracts = [bc for bc in hir.bus_contracts if bc.i2c is not None]
        assert len(i2c_contracts) >= 1
        assert i2c_contracts[0].i2c.address == "0x76"

    def test_bus_contract_has_pin_assignments(self):
        graph = _make_esp32_graph()
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)

        i2c = next(bc for bc in hir.bus_contracts if bc.i2c)
        assert "SDA" in i2c.pin_assignments or "SCL" in i2c.pin_assignments

    def test_init_contract_for_bme280(self):
        graph = _make_esp32_graph()
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)

        assert len(hir.init_contracts) >= 1
        bme_init = hir.init_contracts[0]
        assert len(bme_init.phases) >= 1

        # Should have classified phases
        phase_types = {p.phase for p in bme_init.phases}
        assert InitPhase.RESET in phase_types or InitPhase.CONFIGURE in phase_types

    def test_init_contract_has_register_writes(self):
        graph = _make_esp32_graph()
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)

        bme_init = hir.init_contracts[0]
        total_writes = sum(len(p.writes) for p in bme_init.phases)
        assert total_writes >= 3  # BME280 has at least reset + config + enable

    def test_electrical_spec_has_voltage(self):
        graph = _make_esp32_graph()
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)

        # At least one component should have a supply voltage inferred
        with_voltage = [e for e in hir.electrical_specs if e.supply_voltage is not None]
        assert len(with_voltage) >= 1

    def test_power_sequence_built(self):
        graph = _make_esp32_graph()
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)

        assert hir.power_sequence is not None
        # Should have at least one rail if power domains exist
        if graph.power_domains:
            assert len(hir.power_sequence.rails) >= 1

    def test_rp2040_builds_hir(self):
        graph = _make_rp2040_graph()
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)

        assert len(hir.bus_contracts) >= 1
        i2c = next((bc for bc in hir.bus_contracts if bc.i2c), None)
        assert i2c is not None


# ---------------------------------------------------------------------------
# Constraint solver tests
# ---------------------------------------------------------------------------


class TestConstraintSolver:
    def test_esp32_fixture_produces_constraints(self):
        graph = _make_esp32_graph()
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)
        hir.constraints = solve_constraints(hir, graph)

        assert len(hir.constraints) >= 1

    def test_no_hard_errors_on_valid_fixture(self):
        graph = _make_esp32_graph()
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)
        hir.constraints = solve_constraints(hir, graph)

        errors = hir.get_errors()
        # A well-designed fixture should not have hard errors
        # (warnings are ok for missing data)
        assert len(errors) == 0, f"Unexpected errors: {[e.description for e in errors]}"

    def test_clock_feasibility_check(self):
        graph = _make_esp32_graph()
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)
        hir.constraints = solve_constraints(hir, graph)

        clock_constraints = [c for c in hir.constraints if c.category == "timing"]
        assert len(clock_constraints) >= 1

    def test_pullup_check(self):
        graph = _make_esp32_graph()
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)
        hir.constraints = solve_constraints(hir, graph)

        pullup_constraints = [c for c in hir.constraints if "pullup" in c.id]
        assert len(pullup_constraints) >= 1

    def test_init_ordering_check(self):
        graph = _make_esp32_graph()
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)
        hir.constraints = solve_constraints(hir, graph)

        init_constraints = [c for c in hir.constraints if "init_order" in c.id]
        assert len(init_constraints) >= 1
        # BME280 init should be properly ordered
        assert all(c.status == ConstraintStatus.PASS for c in init_constraints)


class TestConstraintSolverEdgeCases:
    def test_voltage_mismatch_detected(self):
        """Manually construct a graph with voltage mismatch."""
        from boardsmith_fw.models.hir import BusContract, ElectricalSpec

        hir = HIR(
            electrical_specs=[
                ElectricalSpec(
                    component_id="U1",
                    io_voltage=VoltageLevel(nominal=5.0, min=4.5, max=5.5),
                ),
                ElectricalSpec(
                    component_id="U2",
                    supply_voltage=VoltageLevel(nominal=3.3, min=3.0, max=3.6),
                    is_5v_tolerant=False,
                ),
            ],
            bus_contracts=[
                BusContract(
                    bus_name="I2C_BUS",
                    bus_type="I2C",
                    master_id="U1",
                    slave_ids=["U2"],
                    i2c=I2CSpec(address="0x76"),
                ),
            ],
        )
        graph = HardwareGraph(source="test")
        hir.constraints = solve_constraints(hir, graph)

        voltage_errors = [
            c for c in hir.constraints
            if c.category == "electrical" and c.status == ConstraintStatus.FAIL
        ]
        assert len(voltage_errors) >= 1
        desc = voltage_errors[0].description.lower()
        assert "mismatch" in desc or "level shifter" in desc

    def test_pin_conflict_detected(self):
        from boardsmith_fw.models.hir import BusContract

        hir = HIR(
            bus_contracts=[
                BusContract(
                    bus_name="I2C",
                    bus_type="I2C",
                    master_id="U1",
                    pin_assignments={"SDA": "21", "SCL": "22"},
                ),
                BusContract(
                    bus_name="SPI",
                    bus_type="SPI",
                    master_id="U1",
                    pin_assignments={"MOSI": "21"},  # conflicts with SDA!
                ),
            ],
        )
        graph = HardwareGraph(source="test")
        hir.constraints = solve_constraints(hir, graph)

        pin_errors = [
            c for c in hir.constraints
            if "pin" in c.id and c.status == ConstraintStatus.FAIL
        ]
        assert len(pin_errors) >= 1
        assert "21" in pin_errors[0].description
