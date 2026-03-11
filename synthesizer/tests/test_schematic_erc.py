# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for boardsmith_hw.schematic_erc (Phase 16 ERC validation)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from boardsmith_hw.schematic_erc import SchematicERC, ERCResult, ERCIssue
from boardsmith_hw.kicad_exporter import export_kicad_sch


# ---------------------------------------------------------------------------
# Fixtures — minimal HIR dicts (same pattern as test_kicad_exporter.py)
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
    "id": "ESP32_WROOM_32",
    "name": "ESP32-WROOM-32 MCU",
    "role": "mcu",
    "mpn": "ESP32-WROOM-32",
    "interface_types": ["I2C", "SPI", "UART"],
}

BME280_COMP = {
    "id": "BME280",
    "name": "BME280 sensor",
    "role": "sensor",
    "mpn": "BME280",
    "interface_types": ["I2C", "SPI"],
}

I2C_BUS = {
    "bus_name": "i2c0",
    "bus_type": "I2C",
    "master_id": "ESP32_WROOM_32",
    "slave_ids": ["BME280"],
    "slave_addresses": {"BME280": "0x76"},
}


def _export_to_text(hir: dict) -> str:
    """Export HIR to .kicad_sch text (in-memory via temp file)."""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "schematic.kicad_sch"
        export_kicad_sch(hir, p, use_llm=False)
        return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# ERCResult property tests
# ---------------------------------------------------------------------------

class TestERCResult:
    def test_passed_when_no_issues(self):
        result = ERCResult()
        assert result.passed is True

    def test_passed_false_when_errors(self):
        result = ERCResult(issues=[ERCIssue("error", "TEST", "msg")])
        assert result.passed is False

    def test_passed_true_with_only_warnings(self):
        """Warnings alone do not fail ERC."""
        result = ERCResult(issues=[ERCIssue("warning", "TEST", "msg")])
        assert result.passed is True

    def test_errors_property_filters_by_severity(self):
        result = ERCResult(issues=[
            ERCIssue("error",   "E1", "e"),
            ERCIssue("warning", "W1", "w"),
            ERCIssue("info",    "I1", "i"),
        ])
        assert len(result.errors) == 1
        assert result.errors[0].code == "E1"

    def test_warnings_property_filters_by_severity(self):
        result = ERCResult(issues=[
            ERCIssue("error",   "E1", "e"),
            ERCIssue("warning", "W1", "w"),
        ])
        assert len(result.warnings) == 1
        assert result.warnings[0].code == "W1"


# ---------------------------------------------------------------------------
# Basic ERC checks
# ---------------------------------------------------------------------------

class TestERCBasic:
    def test_empty_schematic_returns_no_components_error(self):
        """An empty .kicad_sch (no components) must produce NO_COMPONENTS error."""
        empty_sch = '(kicad_sch (version 20230121) (generator "test")\n  (uuid "abc")\n)'
        erc = SchematicERC()
        result = erc.check_text(empty_sch)
        codes = [i.code for i in result.issues]
        assert "NO_COMPONENTS" in codes

    def test_valid_i2c_design_passes_erc(self):
        """A complete I2C design (ESP32 + BME280) must pass ERC."""
        hir = _make_hir([ESP32_COMP, BME280_COMP], [I2C_BUS])
        sch_text = _export_to_text(hir)
        erc = SchematicERC()
        result = erc.check_text(sch_text, hir_dict=hir)
        assert result.component_count >= 2
        assert result.passed, (
            f"ERC failed with errors: {[e.message for e in result.errors]}"
        )

    def test_erc_without_hir_still_parses(self):
        """ERC without HIR dict must not crash and must set component_count."""
        hir = _make_hir([ESP32_COMP, BME280_COMP], [I2C_BUS])
        sch_text = _export_to_text(hir)
        erc = SchematicERC()
        result = erc.check_text(sch_text)
        assert result.component_count >= 1


# ---------------------------------------------------------------------------
# Bus net checks
# ---------------------------------------------------------------------------

class TestERCBusNets:
    def test_i2c_design_has_sda_and_scl_nets(self):
        """Exported I2C design must have SDA and SCL in the parsed net list."""
        hir = _make_hir([ESP32_COMP, BME280_COMP], [I2C_BUS])
        sch_text = _export_to_text(hir)
        erc = SchematicERC()
        result = erc.check_text(sch_text, hir_dict=hir)
        # No MISSING_NET errors expected
        missing_net_errors = [i for i in result.errors if i.code == "MISSING_NET"]
        assert not missing_net_errors, (
            f"Unexpected MISSING_NET: {[e.message for e in missing_net_errors]}"
        )

    def test_schematic_without_sda_triggers_missing_net(self):
        """A schematic lacking SDA net must trigger MISSING_NET error."""
        # Build a schematic without any bus wiring (no bus_contracts)
        hir_no_bus = _make_hir([ESP32_COMP, BME280_COMP])
        sch_text = _export_to_text(hir_no_bus)

        # But check against a HIR that expects an I2C bus
        hir_with_bus = _make_hir([ESP32_COMP, BME280_COMP], [I2C_BUS])
        erc = SchematicERC()
        result = erc.check_text(sch_text, hir_dict=hir_with_bus)

        codes = [i.code for i in result.issues]
        assert "MISSING_NET" in codes


# ---------------------------------------------------------------------------
# Component checks
# ---------------------------------------------------------------------------

class TestERCComponents:
    def test_all_hir_components_found(self):
        """Round-trip: all HIR components must appear in schematic."""
        hir = _make_hir([ESP32_COMP, BME280_COMP], [I2C_BUS])
        sch_text = _export_to_text(hir)
        erc = SchematicERC()
        result = erc.check_text(sch_text, hir_dict=hir)
        missing = [i for i in result.issues if i.code == "MISSING_COMPONENT"]
        assert not missing, f"Components missing: {[m.message for m in missing]}"

    def test_missing_component_triggers_warning(self):
        """HIR component not in schematic must produce MISSING_COMPONENT warning."""
        hir_export = _make_hir([ESP32_COMP])
        sch_text = _export_to_text(hir_export)

        # Check against HIR that includes BME280 (not in schematic)
        hir_check = _make_hir([ESP32_COMP, BME280_COMP])
        erc = SchematicERC()
        result = erc.check_text(sch_text, hir_dict=hir_check)
        codes = [i.code for i in result.issues]
        assert "MISSING_COMPONENT" in codes

    def test_component_count_matches(self):
        """Parsed component count must equal or exceed HIR component count."""
        hir = _make_hir([ESP32_COMP, BME280_COMP], [I2C_BUS])
        sch_text = _export_to_text(hir)
        erc = SchematicERC()
        result = erc.check_text(sch_text, hir_dict=hir)
        assert result.component_count >= 2


# ---------------------------------------------------------------------------
# File-based check
# ---------------------------------------------------------------------------

class TestERCFileInput:
    def test_check_file(self, tmp_path):
        """erc.check(path) must work identically to check_text()."""
        hir = _make_hir([ESP32_COMP, BME280_COMP], [I2C_BUS])
        sch_path = tmp_path / "schematic.kicad_sch"
        export_kicad_sch(hir, sch_path, use_llm=False)

        erc = SchematicERC()
        result = erc.check(sch_path, hir_dict=hir)
        assert result.component_count >= 2
        assert result.passed
