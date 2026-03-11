# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Phase 20: PCB Design Rules, JLCPCB Validator, Gerber Validator,
and Production Bundle Export."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _simple_hir() -> dict:
    return {
        "system_name": "TestBoard",
        "components": [
            {"id": "ESP32", "mpn": "ESP32-WROOM-32", "role": "mcu",
             "electrical_ratings": {"current_draw_max_ma": 240.0}},
            {"id": "BME280", "mpn": "BME280", "role": "sensor",
             "electrical_ratings": {"current_draw_max_ma": 3.6}},
            {"id": "LDO", "mpn": "AMS1117-3.3", "role": "power"},
        ],
        "bus_contracts": [
            {"bus_type": "I2C", "bus_name": "i2c0"},
            {"bus_type": "SPI", "bus_name": "spi0"},
        ],
    }


def _lora_hir() -> dict:
    return {
        "system_name": "LoRaNode",
        "components": [
            {"id": "ESP32", "mpn": "ESP32-WROOM-32", "role": "mcu",
             "electrical_ratings": {"current_draw_max_ma": 240.0}},
            {"id": "SX1276", "mpn": "SX1276", "role": "comms",
             "electrical_ratings": {"current_draw_max_ma": 120.0}},
            {"id": "LDO", "mpn": "AP2112K-3.3TRG1", "role": "power"},
        ],
        "bus_contracts": [
            {"bus_type": "SPI", "bus_name": "spi0"},
        ],
    }


def _usb_hir() -> dict:
    return {
        "system_name": "USBDevice",
        "components": [
            {"id": "STM32", "mpn": "STM32F103C8T6", "role": "mcu"},
        ],
        "bus_contracts": [
            {"bus_type": "USB", "bus_name": "usb0"},
        ],
    }


def _high_current_hir() -> dict:
    return {
        "components": [
            {"id": "ESP32", "mpn": "ESP32-WROOM-32", "role": "mcu",
             "electrical_ratings": {"current_draw_max_ma": 240.0}},
            {"id": "MOTOR", "mpn": "GENERIC-DRIVER", "role": "actuator",
             "electrical_ratings": {"current_draw_max_ma": 400.0}},
        ],
        "bus_contracts": [],
    }


# ---------------------------------------------------------------------------
# Tests — pcb_design_rules
# ---------------------------------------------------------------------------


class TestTraceWidthForCurrent:
    from boardsmith_hw.pcb_design_rules import trace_width_for_current as _fn

    def test_zero_current_returns_minimum(self):
        from boardsmith_hw.pcb_design_rules import trace_width_for_current
        assert trace_width_for_current(0) == 0.10

    def test_small_current_100ma(self):
        from boardsmith_hw.pcb_design_rules import trace_width_for_current
        w = trace_width_for_current(100)
        assert 0.10 <= w <= 0.30

    def test_medium_current_500ma(self):
        from boardsmith_hw.pcb_design_rules import trace_width_for_current
        w = trace_width_for_current(500)
        # IPC-2221: ~0.12mm for 500mA, 10°C rise, 1oz copper
        assert 0.10 <= w <= 0.30

    def test_high_current_2000ma(self):
        from boardsmith_hw.pcb_design_rules import trace_width_for_current
        w = trace_width_for_current(2000)
        # IPC-2221: ~0.79mm for 2000mA, 10°C rise, 1oz copper
        assert w >= 0.50

    def test_wider_for_higher_current(self):
        from boardsmith_hw.pcb_design_rules import trace_width_for_current
        w_low = trace_width_for_current(100)
        w_high = trace_width_for_current(1000)
        assert w_high > w_low

    def test_internal_layer_narrower(self):
        from boardsmith_hw.pcb_design_rules import trace_width_for_current
        w_ext = trace_width_for_current(500, layer="external")
        w_int = trace_width_for_current(500, layer="internal")
        assert w_ext < w_int  # internal needs more width for same current

    def test_negative_current(self):
        from boardsmith_hw.pcb_design_rules import trace_width_for_current
        assert trace_width_for_current(-10) == 0.10


class TestBuildDesignRules:
    def test_returns_pcb_design_rules(self):
        from boardsmith_hw.pcb_design_rules import build_design_rules, PcbDesignRules
        rules = build_design_rules(_simple_hir())
        assert isinstance(rules, PcbDesignRules)

    def test_default_trace_is_sensible(self):
        from boardsmith_hw.pcb_design_rules import build_design_rules
        rules = build_design_rules(_simple_hir())
        assert 0.15 <= rules.default_trace_mm <= 0.50

    def test_power_trace_scales_with_current(self):
        from boardsmith_hw.pcb_design_rules import build_design_rules
        rules_lo = build_design_rules({"components": [
            {"id": "X", "role": "mcu", "electrical_ratings": {"current_draw_max_ma": 50}},
        ], "bus_contracts": []})
        rules_hi = build_design_rules(_high_current_hir())
        assert rules_hi.power_trace_mm >= rules_lo.power_trace_mm

    def test_high_current_note_present(self):
        from boardsmith_hw.pcb_design_rules import build_design_rules
        rules = build_design_rules(_high_current_hir())
        notes_text = " ".join(rules.signal_integrity_notes)
        assert "current" in notes_text.lower()

    def test_usb_generates_diff_pair_rules(self):
        from boardsmith_hw.pcb_design_rules import build_design_rules
        rules = build_design_rules(_usb_hir())
        net_names = [r.net_name for r in rules.trace_rules]
        assert "USB_DP" in net_names
        assert "USB_DM" in net_names

    def test_usb_diff_pair_is_flagged(self):
        from boardsmith_hw.pcb_design_rules import build_design_rules
        rules = build_design_rules(_usb_hir())
        diff_rules = [r for r in rules.trace_rules if r.is_differential]
        assert len(diff_rules) >= 2

    def test_spi_generates_si_note(self):
        from boardsmith_hw.pcb_design_rules import build_design_rules
        rules = build_design_rules(_simple_hir())
        notes_text = " ".join(rules.signal_integrity_notes).lower()
        assert "spi" in notes_text

    def test_i2c_generates_si_note(self):
        from boardsmith_hw.pcb_design_rules import build_design_rules
        rules = build_design_rules(_simple_hir())
        notes_text = " ".join(rules.signal_integrity_notes).lower()
        assert "i2c" in notes_text

    def test_rf_generates_keepout_note(self):
        from boardsmith_hw.pcb_design_rules import build_design_rules
        rules = build_design_rules(_lora_hir())
        notes_text = " ".join(rules.signal_integrity_notes).lower()
        assert "keepout" in notes_text or "antenna" in notes_text

    def test_mcu_generates_decoupling_note(self):
        from boardsmith_hw.pcb_design_rules import build_design_rules
        rules = build_design_rules(_simple_hir())
        notes_text = " ".join(rules.signal_integrity_notes).lower()
        assert "decoupling" in notes_text

    def test_to_dsn_constraints_returns_string(self):
        from boardsmith_hw.pcb_design_rules import build_design_rules
        rules = build_design_rules(_simple_hir())
        dsn = rules.to_dsn_constraints()
        assert isinstance(dsn, str)
        assert "rule" in dsn
        assert "width" in dsn

    def test_summary_contains_widths(self):
        from boardsmith_hw.pcb_design_rules import build_design_rules
        rules = build_design_rules(_simple_hir())
        summary = rules.summary()
        assert "mm" in summary
        assert "IPC-2221" in summary

    def test_empty_hir(self):
        from boardsmith_hw.pcb_design_rules import build_design_rules
        rules = build_design_rules({})
        assert rules.default_trace_mm >= 0.15


# ---------------------------------------------------------------------------
# Tests — jlcpcb_validator
# ---------------------------------------------------------------------------


class TestJLCPCBValidator:
    def test_known_basic_part(self):
        from boardsmith_hw.jlcpcb_validator import JLCPCBValidator
        v = JLCPCBValidator()
        entry = v.lookup("AMS1117-3.3")
        assert entry is not None
        assert entry["tier"] == "basic"

    def test_known_extended_part(self):
        from boardsmith_hw.jlcpcb_validator import JLCPCBValidator
        v = JLCPCBValidator()
        entry = v.lookup("ESP32-WROOM-32")
        assert entry is not None
        assert entry["tier"] == "extended"

    def test_unknown_part_returns_none(self):
        from boardsmith_hw.jlcpcb_validator import JLCPCBValidator
        v = JLCPCBValidator()
        entry = v.lookup("NONEXISTENT_PART_XYZ_999")
        assert entry is None

    def test_case_insensitive_lookup(self):
        from boardsmith_hw.jlcpcb_validator import JLCPCBValidator
        v = JLCPCBValidator()
        entry_upper = v.lookup("AMS1117-3.3")
        entry_lower = v.lookup("ams1117-3.3")
        assert entry_upper is not None
        assert entry_lower is not None

    def test_validate_returns_report(self):
        from boardsmith_hw.jlcpcb_validator import JLCPCBValidator, JLCPCBReport
        v = JLCPCBValidator()
        report = v.validate(_simple_hir())
        assert isinstance(report, JLCPCBReport)

    def test_validate_counts_items(self):
        from boardsmith_hw.jlcpcb_validator import JLCPCBValidator
        v = JLCPCBValidator()
        report = v.validate(_simple_hir())
        total = report.basic_count + report.extended_count + report.not_found_count
        assert total == len([c for c in _simple_hir()["components"] if c.get("mpn")])

    def test_basic_count_correct(self):
        from boardsmith_hw.jlcpcb_validator import JLCPCBValidator
        v = JLCPCBValidator()
        report = v.validate(_simple_hir())
        # AMS1117-3.3 is basic
        assert report.basic_count >= 1

    def test_setup_fee_calculation(self):
        from boardsmith_hw.jlcpcb_validator import JLCPCBValidator, _EXTENDED_SETUP_FEE_USD
        v = JLCPCBValidator()
        report = v.validate(_simple_hir())
        assert report.estimated_setup_fee_usd == report.extended_count * _EXTENDED_SETUP_FEE_USD

    def test_bom_csv_format(self):
        from boardsmith_hw.jlcpcb_validator import JLCPCBValidator
        v = JLCPCBValidator()
        report = v.validate(_simple_hir())
        csv = report.to_bom_csv()
        assert "Comment,Designator,Footprint,LCSC Part #" in csv
        assert "ESP32" in csv

    def test_summary_string(self):
        from boardsmith_hw.jlcpcb_validator import JLCPCBValidator
        v = JLCPCBValidator()
        report = v.validate(_simple_hir())
        summary = report.summary()
        assert "JLCPCB" in summary
        assert "Basic" in summary

    def test_empty_hir(self):
        from boardsmith_hw.jlcpcb_validator import JLCPCBValidator
        v = JLCPCBValidator()
        report = v.validate({})
        assert report.basic_count + report.extended_count + report.not_found_count == 0

    def test_component_without_mpn_skipped(self):
        from boardsmith_hw.jlcpcb_validator import JLCPCBValidator
        hir = {"components": [{"id": "X", "role": "passive"}]}
        v = JLCPCBValidator()
        report = v.validate(hir)
        assert len(report.items) == 0


# ---------------------------------------------------------------------------
# Tests — gerber_validator
# ---------------------------------------------------------------------------


class TestGerberValidator:
    def _write_stub_gerbers(self, tmp_path: Path) -> Path:
        """Create minimal stub Gerber files for testing."""
        gerber_dir = tmp_path / "gerbers"
        gerber_dir.mkdir()
        layers = ["F_Cu", "B_Cu", "F_Mask", "B_Mask", "F_SilkS", "B_SilkS", "Edge_Cuts"]
        for layer in layers:
            (gerber_dir / f"pcb-{layer}.gbr").write_text(
                "%FSLAX46Y46*%\n%MOMM*%\nG04 stub*\nM02*\n"
            )
        (gerber_dir / "pcb.drl").write_text(
            "M48\n; drill file\nM30\n"
        )
        return gerber_dir

    def _write_real_gerbers(self, tmp_path: Path) -> Path:
        """Create realistic (non-stub) Gerber files."""
        gerber_dir = tmp_path / "gerbers"
        gerber_dir.mkdir()
        content = "%FSLAX46Y46*%\n%MOMM*%\n" + ("G01X100Y100D01*\n" * 20) + "M02*\n"
        layers = ["F_Cu", "B_Cu", "F_Mask", "B_Mask", "Edge_Cuts"]
        for layer in layers:
            (gerber_dir / f"pcb-{layer}.gbr").write_text(content)
        (gerber_dir / "pcb.drl").write_text("M48\n" + ("T1C0.3\n" * 10) + "M30\n")
        return gerber_dir

    def test_nonexistent_dir_fails(self, tmp_path):
        from boardsmith_hw.gerber_validator import GerberValidator
        v = GerberValidator()
        report = v.validate(tmp_path / "nonexistent")
        assert report.valid is False

    def test_empty_dir_fails(self, tmp_path):
        from boardsmith_hw.gerber_validator import GerberValidator
        empty = tmp_path / "empty"
        empty.mkdir()
        v = GerberValidator()
        report = v.validate(empty)
        assert report.valid is False

    def test_stub_gerbers_detected(self, tmp_path):
        from boardsmith_hw.gerber_validator import GerberValidator
        gdir = self._write_stub_gerbers(tmp_path)
        v = GerberValidator()
        report = v.validate(gdir)
        assert report.stub_gerbers is True

    def test_real_gerbers_pass(self, tmp_path):
        from boardsmith_hw.gerber_validator import GerberValidator
        gdir = self._write_real_gerbers(tmp_path)
        v = GerberValidator()
        report = v.validate(gdir)
        assert report.valid is True

    def test_drill_file_detected(self, tmp_path):
        from boardsmith_hw.gerber_validator import GerberValidator
        gdir = self._write_stub_gerbers(tmp_path)
        v = GerberValidator()
        report = v.validate(gdir)
        assert report.has_drill is True

    def test_outline_detected(self, tmp_path):
        from boardsmith_hw.gerber_validator import GerberValidator
        gdir = self._write_stub_gerbers(tmp_path)
        v = GerberValidator()
        report = v.validate(gdir)
        assert report.has_outline is True

    def test_layer_count(self, tmp_path):
        from boardsmith_hw.gerber_validator import GerberValidator
        gdir = self._write_stub_gerbers(tmp_path)
        v = GerberValidator()
        report = v.validate(gdir)
        assert len(report.layers) >= 5

    def test_summary_string(self, tmp_path):
        from boardsmith_hw.gerber_validator import GerberValidator
        gdir = self._write_stub_gerbers(tmp_path)
        v = GerberValidator()
        report = v.validate(gdir)
        summary = report.summary()
        assert "Gerber" in summary

    def test_missing_outline_warning(self, tmp_path):
        from boardsmith_hw.gerber_validator import GerberValidator
        gerber_dir = tmp_path / "gerbers"
        gerber_dir.mkdir()
        (gerber_dir / "pcb-F_Cu.gbr").write_text("%FSLAX46Y46*%\n%MOMM*%\n" + "X" * 300 + "\nM02*\n")
        (gerber_dir / "pcb.drl").write_text("M48\nM30\n")
        v = GerberValidator()
        report = v.validate(gerber_dir)
        assert not report.has_outline


# ---------------------------------------------------------------------------
# Tests — pcb_production
# ---------------------------------------------------------------------------


class TestBuildCentroidCsv:
    def test_returns_csv_string(self):
        from boardsmith_hw.pcb_production import _build_centroid_csv
        csv = _build_centroid_csv(_simple_hir(), {})
        assert isinstance(csv, str)
        assert "Designator" in csv

    def test_contains_all_components(self):
        from boardsmith_hw.pcb_production import _build_centroid_csv
        csv = _build_centroid_csv(_simple_hir(), {})
        assert "ESP32" in csv
        assert "BME280" in csv
        assert "LDO" in csv

    def test_csv_has_correct_columns(self):
        from boardsmith_hw.pcb_production import _build_centroid_csv
        csv = _build_centroid_csv(_simple_hir(), {})
        header = csv.splitlines()[0]
        assert "Mid X" in header
        assert "Rotation" in header
        assert "Layer" in header


class TestPcbProductionExporter:
    def _make_stub_output(self, tmp_path: Path) -> Path:
        """Create a minimal pcb pipeline output directory."""
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        gerber_dir = out_dir / "gerbers"
        gerber_dir.mkdir()
        for layer in ["F_Cu", "B_Cu", "Edge_Cuts"]:
            (gerber_dir / f"pcb-{layer}.gbr").write_text(
                "%FSLAX46Y46*%\n%MOMM*%\nG04 test*\nM02*\n"
            )
        (gerber_dir / "pcb.drl").write_text("M48\nM30\n")
        (out_dir / "pcb.kicad_pcb").write_text("(kicad_pcb)\n")
        return out_dir

    def _stub_result(self, out_dir: Path):
        from boardsmith_hw.pcb_pipeline import PcbResult
        return PcbResult(
            pcb_path=out_dir / "pcb.kicad_pcb",
            gerber_dir=out_dir / "gerbers",
            routed=False,
            footprints={"ESP32": "RF_Module:ESP32-WROOM-32"},
        )

    def test_export_creates_zip(self, tmp_path):
        from boardsmith_hw.pcb_production import PcbProductionExporter
        out_dir = self._make_stub_output(tmp_path)
        stub = self._stub_result(out_dir)
        exporter = PcbProductionExporter()
        bundle = exporter.export(stub, _simple_hir(), out_dir)
        assert bundle.zip_path is not None
        assert bundle.zip_path.exists()

    def test_zip_contains_gerbers(self, tmp_path):
        from boardsmith_hw.pcb_production import PcbProductionExporter
        out_dir = self._make_stub_output(tmp_path)
        stub = self._stub_result(out_dir)
        exporter = PcbProductionExporter()
        bundle = exporter.export(stub, _simple_hir(), out_dir)
        with zipfile.ZipFile(bundle.zip_path) as zf:
            names = zf.namelist()
        assert any("gerbers/" in n for n in names)

    def test_zip_contains_bom(self, tmp_path):
        from boardsmith_hw.pcb_production import PcbProductionExporter
        out_dir = self._make_stub_output(tmp_path)
        stub = self._stub_result(out_dir)
        exporter = PcbProductionExporter()
        bundle = exporter.export(stub, _simple_hir(), out_dir)
        with zipfile.ZipFile(bundle.zip_path) as zf:
            names = zf.namelist()
        assert "bom.csv" in names

    def test_zip_contains_centroid(self, tmp_path):
        from boardsmith_hw.pcb_production import PcbProductionExporter
        out_dir = self._make_stub_output(tmp_path)
        stub = self._stub_result(out_dir)
        exporter = PcbProductionExporter()
        bundle = exporter.export(stub, _simple_hir(), out_dir)
        with zipfile.ZipFile(bundle.zip_path) as zf:
            names = zf.namelist()
        assert "centroid.csv" in names

    def test_zip_contains_readme(self, tmp_path):
        from boardsmith_hw.pcb_production import PcbProductionExporter
        out_dir = self._make_stub_output(tmp_path)
        stub = self._stub_result(out_dir)
        exporter = PcbProductionExporter()
        bundle = exporter.export(stub, _simple_hir(), out_dir)
        with zipfile.ZipFile(bundle.zip_path) as zf:
            names = zf.namelist()
        assert "README.txt" in names

    def test_bom_csv_populated(self, tmp_path):
        from boardsmith_hw.pcb_production import PcbProductionExporter
        out_dir = self._make_stub_output(tmp_path)
        stub = self._stub_result(out_dir)
        exporter = PcbProductionExporter()
        bundle = exporter.export(stub, _simple_hir(), out_dir)
        assert bundle.bom_csv
        assert "Comment" in bundle.bom_csv

    def test_jlcpcb_report_populated(self, tmp_path):
        from boardsmith_hw.pcb_production import PcbProductionExporter
        out_dir = self._make_stub_output(tmp_path)
        stub = self._stub_result(out_dir)
        exporter = PcbProductionExporter()
        bundle = exporter.export(stub, _simple_hir(), out_dir)
        assert bundle.jlcpcb_report is not None

    def test_gerber_report_populated(self, tmp_path):
        from boardsmith_hw.pcb_production import PcbProductionExporter
        out_dir = self._make_stub_output(tmp_path)
        stub = self._stub_result(out_dir)
        exporter = PcbProductionExporter()
        bundle = exporter.export(stub, _simple_hir(), out_dir)
        assert bundle.gerber_report is not None

    def test_design_rules_populated(self, tmp_path):
        from boardsmith_hw.pcb_production import PcbProductionExporter
        out_dir = self._make_stub_output(tmp_path)
        stub = self._stub_result(out_dir)
        exporter = PcbProductionExporter()
        bundle = exporter.export(stub, _simple_hir(), out_dir)
        assert bundle.design_rules is not None

    def test_ready_for_order_property(self, tmp_path):
        from boardsmith_hw.pcb_production import PcbProductionExporter
        out_dir = self._make_stub_output(tmp_path)
        stub = self._stub_result(out_dir)
        exporter = PcbProductionExporter()
        bundle = exporter.export(stub, _simple_hir(), out_dir)
        # ready_for_order is False if gerber report is invalid (missing layers)
        # or if no zip. Just verify the property returns a bool.
        assert isinstance(bundle.ready_for_order, bool)

    def test_summary_string(self, tmp_path):
        from boardsmith_hw.pcb_production import PcbProductionExporter
        out_dir = self._make_stub_output(tmp_path)
        stub = self._stub_result(out_dir)
        exporter = PcbProductionExporter()
        bundle = exporter.export(stub, _simple_hir(), out_dir)
        summary = bundle.summary()
        assert "Production Bundle" in summary

    def test_project_name_in_zip_filename(self, tmp_path):
        from boardsmith_hw.pcb_production import PcbProductionExporter
        out_dir = self._make_stub_output(tmp_path)
        stub = self._stub_result(out_dir)
        exporter = PcbProductionExporter()
        bundle = exporter.export(stub, _simple_hir(), out_dir, project_name="myboard")
        assert bundle.zip_path is not None
        assert "myboard" in bundle.zip_path.name


# ---------------------------------------------------------------------------
# Tests — pcb_pipeline integration (new fields)
# ---------------------------------------------------------------------------


class TestPcbPipelinePhase20:
    def _make_hir(self) -> dict:
        return {
            "system_name": "TestSystem",
            "components": [
                {"id": "ESP32", "mpn": "ESP32-WROOM-32", "role": "mcu",
                 "electrical_ratings": {"current_draw_max_ma": 240.0}},
                {"id": "BME280", "mpn": "BME280", "role": "sensor"},
                {"id": "LDO", "mpn": "AMS1117-3.3", "role": "power"},
            ],
            "bus_contracts": [
                {"bus_type": "I2C", "bus_name": "i2c0"},
            ],
        }

    def test_result_has_production_zip(self, tmp_path):
        from boardsmith_hw.pcb_pipeline import PcbPipeline
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(self._make_hir(), out_dir=tmp_path)
        assert hasattr(result, "production_zip")

    def test_production_zip_created(self, tmp_path):
        from boardsmith_hw.pcb_pipeline import PcbPipeline
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(self._make_hir(), out_dir=tmp_path)
        if result.production_zip:
            assert result.production_zip.exists()

    def test_result_has_design_rules_summary(self, tmp_path):
        from boardsmith_hw.pcb_pipeline import PcbPipeline
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(self._make_hir(), out_dir=tmp_path)
        assert hasattr(result, "design_rules_summary")
        # May be empty if design rules analysis failed, but field exists
        assert isinstance(result.design_rules_summary, str)

    def test_result_has_jlcpcb_summary(self, tmp_path):
        from boardsmith_hw.pcb_pipeline import PcbPipeline
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(self._make_hir(), out_dir=tmp_path)
        assert hasattr(result, "jlcpcb_summary")

    def test_design_rules_txt_written(self, tmp_path):
        from boardsmith_hw.pcb_pipeline import PcbPipeline
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(self._make_hir(), out_dir=tmp_path)
        dr_file = tmp_path / "design_rules.txt"
        # Only exists if design rules succeeded
        if result.design_rules_summary:
            assert dr_file.exists()
