# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for constraint report export (JSON and HTML)."""

import json

from boardsmith_fw.analysis.constraint_report import export_html, export_json
from boardsmith_fw.models.hir import (
    HIR,
    BusContract,
    Constraint,
    ConstraintSeverity,
    ConstraintStatus,
    ElectricalSpec,
    I2CSpec,
    InitContract,
    InitPhase,
    InitPhaseSpec,
    RegisterRead,
    RegisterWrite,
    VoltageLevel,
)


def _make_hir_with_constraints() -> HIR:
    """Build a small HIR with pre-populated constraints for report testing."""
    return HIR(
        source="test_fixture.sch",
        bus_contracts=[
            BusContract(
                bus_name="I2C_BUS",
                bus_type="I2C",
                master_id="MCU",
                slave_ids=["SENSOR"],
                i2c=I2CSpec(address="0x76"),
            ),
        ],
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
                        phase=InitPhase.VERIFY,
                        order=1,
                        reads=[RegisterRead(reg_addr="0xD0", expected_value="0x60")],
                    ),
                ],
            ),
        ],
        electrical_specs=[
            ElectricalSpec(
                component_id="MCU",
                io_voltage=VoltageLevel(nominal=3.3),
            ),
            ElectricalSpec(
                component_id="SENSOR",
                supply_voltage=VoltageLevel(nominal=3.3),
            ),
        ],
        constraints=[
            Constraint(
                id="voltage.I2C_BUS.SENSOR_ok",
                category="electrical",
                description="Voltage compatible on I2C_BUS: 3.3V",
                severity=ConstraintSeverity.INFO,
                status=ConstraintStatus.PASS,
                affected_components=["MCU", "SENSOR"],
            ),
            Constraint(
                id="clock.I2C_BUS.ok",
                category="timing",
                description="I2C clock within limit",
                severity=ConstraintSeverity.INFO,
                status=ConstraintStatus.PASS,
            ),
            Constraint(
                id="pullup.I2C_BUS.SDA.missing",
                category="electrical",
                description="No pull-up resistor on SDA",
                severity=ConstraintSeverity.WARNING,
                status=ConstraintStatus.FAIL,
            ),
            Constraint(
                id="rise_time.I2C_BUS.unknown",
                category="signal_integrity",
                description="Cannot calculate rise time: no capacitance data",
                severity=ConstraintSeverity.WARNING,
                status=ConstraintStatus.UNKNOWN,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# JSON export tests
# ---------------------------------------------------------------------------


class TestExportJSON:
    def test_returns_valid_json(self):
        hir = _make_hir_with_constraints()
        result = export_json(hir)
        data = json.loads(result)
        assert isinstance(data, dict)

    def test_has_version(self):
        hir = _make_hir_with_constraints()
        data = json.loads(export_json(hir))
        assert data["boardsmith_fw_version"] == "0.5.0"

    def test_has_generated_at(self):
        hir = _make_hir_with_constraints()
        data = json.loads(export_json(hir))
        assert "generated_at" in data
        assert "T" in data["generated_at"]  # ISO format

    def test_has_source(self):
        hir = _make_hir_with_constraints()
        data = json.loads(export_json(hir))
        assert data["source"] == "test_fixture.sch"

    def test_summary_counts(self):
        hir = _make_hir_with_constraints()
        data = json.loads(export_json(hir))
        summary = data["summary"]
        assert summary["total"] == 4
        assert summary["pass"] == 2
        assert summary["fail"] == 1
        assert summary["unknown"] == 1
        assert summary["errors"] == 0
        assert summary["warnings"] == 1

    def test_valid_when_no_errors(self):
        hir = _make_hir_with_constraints()
        data = json.loads(export_json(hir))
        assert data["summary"]["valid"] is True

    def test_invalid_when_errors(self):
        hir = _make_hir_with_constraints()
        hir.constraints.append(Constraint(
            id="voltage.mismatch",
            category="electrical",
            description="5V vs 3.3V mismatch",
            severity=ConstraintSeverity.ERROR,
            status=ConstraintStatus.FAIL,
        ))
        data = json.loads(export_json(hir))
        assert data["summary"]["valid"] is False
        assert data["summary"]["errors"] == 1

    def test_categories_grouped(self):
        hir = _make_hir_with_constraints()
        data = json.loads(export_json(hir))
        cats = data["categories"]
        assert "electrical" in cats
        assert "timing" in cats
        assert "signal_integrity" in cats
        # Check that each category contains the right constraint IDs
        electrical_ids = [c["id"] for c in cats["electrical"]]
        assert "voltage.I2C_BUS.SENSOR_ok" in electrical_ids
        assert "pullup.I2C_BUS.SDA.missing" in electrical_ids

    def test_hir_metadata(self):
        hir = _make_hir_with_constraints()
        data = json.loads(export_json(hir))
        assert data["bus_contracts"] == 1
        assert data["init_contracts"] == 1
        assert data["electrical_specs"] == 2

    def test_empty_hir(self):
        hir = HIR()
        data = json.loads(export_json(hir))
        assert data["summary"]["total"] == 0
        assert data["summary"]["valid"] is True
        assert data["categories"] == {}

    def test_constraint_entry_fields(self):
        hir = _make_hir_with_constraints()
        data = json.loads(export_json(hir))
        entry = data["categories"]["electrical"][0]
        assert "id" in entry
        assert "description" in entry
        assert "severity" in entry
        assert "status" in entry
        assert "affected_components" in entry


# ---------------------------------------------------------------------------
# HTML export tests
# ---------------------------------------------------------------------------


class TestExportHTML:
    def test_returns_html_string(self):
        hir = _make_hir_with_constraints()
        html = export_html(hir)
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_contains_title(self):
        hir = _make_hir_with_constraints()
        html = export_html(hir)
        assert "boardsmith-fw Constraint Report" in html

    def test_contains_source(self):
        hir = _make_hir_with_constraints()
        html = export_html(hir)
        assert "test_fixture.sch" in html

    def test_shows_valid_status(self):
        hir = _make_hir_with_constraints()
        html = export_html(hir)
        assert "VALID" in html

    def test_shows_invalid_status(self):
        hir = _make_hir_with_constraints()
        hir.constraints.append(Constraint(
            id="error.1",
            category="electrical",
            description="bad",
            severity=ConstraintSeverity.ERROR,
            status=ConstraintStatus.FAIL,
        ))
        html = export_html(hir)
        assert "INVALID" in html

    def test_contains_table(self):
        hir = _make_hir_with_constraints()
        html = export_html(hir)
        assert "<table>" in html
        assert "<thead>" in html
        assert "<tbody>" in html

    def test_constraint_rows_present(self):
        hir = _make_hir_with_constraints()
        html = export_html(hir)
        assert "voltage.I2C_BUS.SENSOR_ok" in html
        assert "pullup.I2C_BUS.SDA.missing" in html

    def test_css_classes(self):
        hir = _make_hir_with_constraints()
        html = export_html(hir)
        assert 'class="pass"' in html
        assert 'class="warn"' in html

    def test_summary_cards(self):
        hir = _make_hir_with_constraints()
        html = export_html(hir)
        assert "2 pass" in html
        assert "0 errors" in html
        assert "1 warnings" in html
        assert "1 unknown" in html

    def test_hir_metadata_in_html(self):
        hir = _make_hir_with_constraints()
        html = export_html(hir)
        assert "1 bus contracts" in html
        assert "1 init contracts" in html
        assert "2 electrical specs" in html

    def test_empty_hir_renders(self):
        hir = HIR()
        html = export_html(hir)
        assert "<!DOCTYPE html>" in html
        assert "VALID" in html
        assert "0 pass" in html

    def test_status_uppercase_in_table(self):
        hir = _make_hir_with_constraints()
        html = export_html(hir)
        assert "PASS" in html
        assert "FAIL" in html


# ---------------------------------------------------------------------------
# Integration — report from real fixture
# ---------------------------------------------------------------------------


class TestReportFromFixture:
    def test_export_json_from_fixture(self):
        from pathlib import Path

        from boardsmith_fw.analysis.constraint_solver import solve_constraints
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

        json_str = export_json(hir)
        data = json.loads(json_str)

        assert data["summary"]["total"] >= 5
        assert data["summary"]["valid"] is True
        assert len(data["categories"]) >= 2

    def test_export_html_from_fixture(self):
        from pathlib import Path

        from boardsmith_fw.analysis.constraint_solver import solve_constraints
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

        html = export_html(hir)
        assert "<!DOCTYPE html>" in html
        assert "VALID" in html
        assert "esp32_bme280" in html
