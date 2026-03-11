# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for HIR validator — Track A oracle."""
import json
import pytest
from pathlib import Path

from synth_core.models.hir import HIR
from synth_core.hir_bridge.validator import validate_hir, solve_constraints, DiagnosticsReport

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "boardsmith_hw"


def _load_hir(name: str) -> HIR:
    with open(FIXTURE_DIR / name) as f:
        return HIR.model_validate(json.load(f))


def test_valid_hir_passes():
    hir = _load_hir("hir_valid_esp32_bme280.json")
    report = validate_hir(hir)
    assert report.valid, f"Expected valid but got errors: {[c.description for c in report.constraints if c.severity.value == 'error']}"


def test_i2c_address_conflict_detected():
    hir = _load_hir("hir_invalid_i2c_addr_conflict.json")
    constraints = solve_constraints(hir)
    conflict_errs = [c for c in constraints if "conflict" in c.id and c.severity.value == "error"]
    assert len(conflict_errs) >= 1, "Expected at least one I2C address conflict error"


def test_i2c_address_conflict_has_fixes():
    hir = _load_hir("hir_invalid_i2c_addr_conflict.json")
    constraints = solve_constraints(hir)
    conflict_errs = [c for c in constraints if "conflict" in c.id and c.severity.value == "error"]
    assert conflict_errs[0].suggested_fixes, "Conflict constraint should include suggested fixes"


def test_voltage_mismatch_detected():
    hir = _load_hir("hir_invalid_voltage_mismatch.json")
    constraints = solve_constraints(hir)
    voltage_errs = [c for c in constraints if "voltage.level" in c.id and c.severity.value == "error"]
    assert len(voltage_errs) >= 1, "Expected voltage mismatch error"


def test_diagnostics_report_structure():
    hir = _load_hir("hir_invalid_i2c_addr_conflict.json")
    report = validate_hir(hir)
    d = report.to_dict()
    assert "tool" in d
    assert "valid" in d
    assert "summary" in d
    assert "diagnostics" in d
    assert d["summary"]["errors"] >= 1


def test_valid_hir_exit_code_0():
    """Simulate CLI: valid HIR → exit code 0 (report.valid = True)."""
    hir = _load_hir("hir_valid_esp32_bme280.json")
    report = validate_hir(hir)
    assert report.valid


def test_invalid_hir_exit_code_1():
    """Simulate CLI: invalid HIR → exit code 1 (report.valid = False)."""
    hir = _load_hir("hir_invalid_i2c_addr_conflict.json")
    report = validate_hir(hir)
    assert not report.valid
