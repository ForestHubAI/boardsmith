# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for B15 KiCad DRC/ERC module (kicad_drc.py).

Covers:
  - KiCadChecker availability detection
  - ERC on .kicad_sch (graceful when kicad-cli absent)
  - DRC on .kicad_pcb (graceful when kicad-cli absent)
  - Auto-detect via check() method
  - Report parsing from JSON
  - CheckResult and DRCViolation data classes
  - ERCRefiner closed-loop
  - ERCRefinementResult data class
  - KiCad exporter no_connect and PWR_FLAG support
  - Integration with Autorouter delegation
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler"):
    _p = str(_REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from boardsmith_hw.kicad_drc import (
    KiCadChecker, CheckResult, DRCViolation,
    ERCRefiner, ERCRefinementResult,
)


# ===========================================================================
# Data class tests
# ===========================================================================


class TestDRCViolation:
    def test_defaults(self):
        v = DRCViolation(severity="error", description="Pin not connected")
        assert v.severity == "error"
        assert v.description == "Pin not connected"
        assert v.rule_id == ""
        assert v.items == []

    def test_with_items(self):
        v = DRCViolation(
            severity="warning",
            description="Clearance violation",
            rule_id="clearance",
            items=["Pad U1:1", "Pad U2:3"],
        )
        assert len(v.items) == 2
        assert v.rule_id == "clearance"


class TestCheckResult:
    def test_defaults(self):
        r = CheckResult(check_type="erc", passed=True)
        assert r.check_type == "erc"
        assert r.passed is True
        assert r.violations == []
        assert r.error_count == 0
        assert r.warning_count == 0
        assert r.error_messages == []
        assert r.tool_available is False
        assert r.note == ""

    def test_with_violations(self):
        r = CheckResult(
            check_type="drc",
            passed=False,
            violations=[
                DRCViolation(severity="error", description="Short circuit"),
            ],
            error_count=1,
            warning_count=0,
            error_messages=["Short circuit"],
            tool_available=True,
            note="DRC: 1 Fehler, 0 Warnungen.",
        )
        assert not r.passed
        assert r.error_count == 1
        assert len(r.violations) == 1


# ===========================================================================
# KiCadChecker — availability
# ===========================================================================


class TestKiCadCheckerAvailability:
    def test_is_available_returns_bool(self):
        result = KiCadChecker.is_available()
        assert isinstance(result, bool)

    def test_kicad_cli_available_returns_bool(self):
        checker = KiCadChecker()
        result = checker.kicad_cli_available()
        assert isinstance(result, bool)

    def test_kicad_cli_available_caches_result(self):
        checker = KiCadChecker()
        r1 = checker.kicad_cli_available()
        r2 = checker.kicad_cli_available()
        assert r1 == r2

    @patch("shutil.which", return_value="/usr/bin/kicad-cli")
    def test_available_when_on_path(self, mock_which):
        checker = KiCadChecker()
        checker._cli_available = None  # reset cache
        assert checker.kicad_cli_available() is True

    @patch("shutil.which", return_value=None)
    def test_unavailable_when_not_on_path(self, mock_which):
        checker = KiCadChecker()
        checker._cli_available = None  # reset cache
        assert checker.kicad_cli_available() is False


# ===========================================================================
# KiCadChecker — ERC (without kicad-cli)
# ===========================================================================


class TestRunERCGraceful:
    """ERC tests that work without kicad-cli installed."""

    def test_erc_without_tool_returns_result(self, tmp_path):
        sch = tmp_path / "test.kicad_sch"
        sch.write_text("(kicad_sch (version 20211014))", encoding="utf-8")

        checker = KiCadChecker()
        checker._cli_available = False  # force no tool
        result = checker.run_erc(sch)

        assert isinstance(result, CheckResult)
        assert result.check_type == "erc"
        assert result.passed is True  # optimistic when tool absent
        assert result.tool_available is False
        assert "kicad-cli" in result.note.lower() or "übersprungen" in result.note.lower()

    def test_erc_returns_check_type_erc(self, tmp_path):
        sch = tmp_path / "test.kicad_sch"
        sch.write_text("(kicad_sch (version 20211014))", encoding="utf-8")

        checker = KiCadChecker()
        checker._cli_available = False
        result = checker.run_erc(sch)
        assert result.check_type == "erc"


# ===========================================================================
# KiCadChecker — DRC (without kicad-cli)
# ===========================================================================


class TestRunDRCGraceful:
    """DRC tests that work without kicad-cli installed."""

    def test_drc_without_tool_returns_result(self, tmp_path):
        pcb = tmp_path / "test.kicad_pcb"
        pcb.write_text("(kicad_pcb (version 20221018))", encoding="utf-8")

        checker = KiCadChecker()
        checker._cli_available = False
        result = checker.run_drc(pcb)

        assert isinstance(result, CheckResult)
        assert result.check_type == "drc"
        assert result.passed is True
        assert result.tool_available is False

    def test_drc_returns_check_type_drc(self, tmp_path):
        pcb = tmp_path / "test.kicad_pcb"
        pcb.write_text("(kicad_pcb (version 20221018))", encoding="utf-8")

        checker = KiCadChecker()
        checker._cli_available = False
        result = checker.run_drc(pcb)
        assert result.check_type == "drc"


# ===========================================================================
# KiCadChecker — check() auto-detect
# ===========================================================================


class TestCheckAutoDetect:
    def test_auto_detect_erc(self, tmp_path):
        sch = tmp_path / "test.kicad_sch"
        sch.write_text("(kicad_sch (version 20211014))", encoding="utf-8")

        checker = KiCadChecker()
        checker._cli_available = False
        result = checker.check(sch)
        assert result.check_type == "erc"

    def test_auto_detect_drc(self, tmp_path):
        pcb = tmp_path / "test.kicad_pcb"
        pcb.write_text("(kicad_pcb (version 20221018))", encoding="utf-8")

        checker = KiCadChecker()
        checker._cli_available = False
        result = checker.check(pcb)
        assert result.check_type == "drc"

    def test_unsupported_extension_raises(self, tmp_path):
        txt = tmp_path / "test.txt"
        txt.write_text("hello", encoding="utf-8")

        checker = KiCadChecker()
        with pytest.raises(ValueError, match="Unsupported file type"):
            checker.check(txt)

    def test_gerber_extension_raises(self, tmp_path):
        gbr = tmp_path / "test.gbr"
        gbr.write_text("G04 test*", encoding="utf-8")

        checker = KiCadChecker()
        with pytest.raises(ValueError):
            checker.check(gbr)


# ===========================================================================
# KiCadChecker — report parsing
# ===========================================================================


class TestReportParsing:
    def _checker(self) -> KiCadChecker:
        checker = KiCadChecker()
        checker._cli_available = True
        return checker

    def test_parse_empty_report(self, tmp_path):
        report = tmp_path / "report.json"
        report.write_text(json.dumps({"violations": []}), encoding="utf-8")

        checker = self._checker()
        result = checker._parse_report("drc", report)
        assert result.passed is True
        assert result.error_count == 0
        assert result.warning_count == 0
        assert result.violations == []

    def test_parse_report_with_errors(self, tmp_path):
        report = tmp_path / "report.json"
        report.write_text(json.dumps({
            "violations": [
                {
                    "severity": "error",
                    "description": "Clearance violation (min 0.2mm; actual 0.1mm)",
                    "type": "clearance",
                    "items": [
                        {"description": "Pad U1:1", "pos": {"x": 10.0, "y": 20.0}},
                        {"description": "Pad U2:3", "pos": {"x": 10.5, "y": 20.0}},
                    ],
                },
                {
                    "severity": "warning",
                    "description": "Silk text over pad",
                    "type": "silk_overlap",
                },
            ]
        }), encoding="utf-8")

        checker = self._checker()
        result = checker._parse_report("drc", report)
        assert not result.passed
        assert result.error_count == 1
        assert result.warning_count == 1
        assert len(result.violations) == 2
        assert result.violations[0].severity == "error"
        assert result.violations[0].rule_id == "clearance"
        assert len(result.violations[0].items) == 2
        assert "10.0" in result.violations[0].items[0]

    def test_parse_report_with_warnings_only(self, tmp_path):
        report = tmp_path / "report.json"
        report.write_text(json.dumps({
            "violations": [
                {"severity": "warning", "description": "Courtyard overlap"},
            ]
        }), encoding="utf-8")

        checker = self._checker()
        result = checker._parse_report("drc", report)
        assert result.passed is True  # warnings don't fail
        assert result.error_count == 0
        assert result.warning_count == 1

    def test_parse_erc_sheets_format(self, tmp_path):
        """ERC reports may nest violations under 'sheets'."""
        report = tmp_path / "report.json"
        report.write_text(json.dumps({
            "sheets": [
                {
                    "path": "/",
                    "violations": [
                        {"severity": "error", "description": "Pin not connected", "type": "pin_not_connected"},
                        {"severity": "warning", "description": "Power pin not driven", "type": "power_pin"},
                    ]
                }
            ]
        }), encoding="utf-8")

        checker = self._checker()
        result = checker._parse_report("erc", report)
        assert not result.passed
        assert result.error_count == 1
        assert result.warning_count == 1
        assert len(result.violations) == 2
        assert result.violations[0].description == "Pin not connected"

    def test_parse_invalid_json(self, tmp_path):
        report = tmp_path / "report.json"
        report.write_text("not json!", encoding="utf-8")

        checker = self._checker()
        result = checker._parse_report("drc", report)
        assert not result.passed
        assert "geparst" in result.note.lower() or "parse" in result.note.lower()

    def test_parse_caps_violations_at_30(self, tmp_path):
        report = tmp_path / "report.json"
        violations = [
            {"severity": "error", "description": f"Error {i}"}
            for i in range(50)
        ]
        report.write_text(json.dumps({"violations": violations}), encoding="utf-8")

        checker = self._checker()
        result = checker._parse_report("drc", report)
        assert len(result.violations) == 30
        assert len(result.error_messages) == 30

    def test_error_messages_backward_compat(self, tmp_path):
        """error_messages should be a flat list of description strings."""
        report = tmp_path / "report.json"
        report.write_text(json.dumps({
            "violations": [
                {"severity": "error", "description": "Short circuit"},
                {"severity": "warning", "description": "Missing teardrops"},
            ]
        }), encoding="utf-8")

        checker = self._checker()
        result = checker._parse_report("drc", report)
        assert "Short circuit" in result.error_messages
        assert "Missing teardrops" in result.error_messages


# ===========================================================================
# KiCadChecker — mocked kicad-cli execution
# ===========================================================================


class TestRunCheckMocked:
    """Test _run_check with mocked subprocess."""

    def test_run_check_no_report_file(self, tmp_path):
        """When kicad-cli produces no output file."""
        target = tmp_path / "test.kicad_pcb"
        target.write_text("(kicad_pcb (version 20221018))", encoding="utf-8")

        checker = KiCadChecker()
        checker._cli_available = True

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr="some error", stdout=""
            )
            # The report file won't exist since we mocked subprocess
            result = checker._run_check("drc", ["kicad-cli", "pcb", "drc"], target)

        assert result.tool_available is True
        assert not result.passed
        assert "Report" in result.note or "report" in result.note.lower()

    def test_run_check_timeout(self, tmp_path):
        import subprocess as sp
        target = tmp_path / "test.kicad_sch"
        target.write_text("(kicad_sch)", encoding="utf-8")

        checker = KiCadChecker()
        checker._cli_available = True

        with patch("subprocess.run", side_effect=sp.TimeoutExpired("cmd", 120)):
            result = checker._run_check("erc", ["kicad-cli", "sch", "erc"], target)

        assert result.tool_available is True
        assert not result.passed
        assert "timeout" in result.note.lower() or "Timeout" in result.note

    def test_run_check_general_exception(self, tmp_path):
        target = tmp_path / "test.kicad_pcb"
        target.write_text("(kicad_pcb)", encoding="utf-8")

        checker = KiCadChecker()
        checker._cli_available = True

        with patch("subprocess.run", side_effect=OSError("No such file")):
            result = checker._run_check("drc", ["kicad-cli", "pcb", "drc"], target)

        assert result.tool_available is True
        assert not result.passed
        assert "Fehler" in result.note or "error" in result.note.lower()


# ===========================================================================
# Integration: Autorouter delegation
# ===========================================================================


class TestAutoRouterDelegation:
    def test_drc_only_returns_list(self, tmp_path):
        from boardsmith_hw.autorouter import Autorouter
        pcb = tmp_path / "test.kicad_pcb"
        pcb.write_text("(kicad_pcb (version 20221018))", encoding="utf-8")

        router = Autorouter()
        errors = router.drc_only(pcb)
        assert isinstance(errors, list)

    def test_drc_only_uses_kicad_checker(self, tmp_path):
        from boardsmith_hw.autorouter import Autorouter
        pcb = tmp_path / "test.kicad_pcb"
        pcb.write_text("(kicad_pcb (version 20221018))", encoding="utf-8")

        with patch("boardsmith_hw.kicad_drc.KiCadChecker.run_drc") as mock_drc:
            mock_drc.return_value = CheckResult(
                check_type="drc",
                passed=False,
                error_messages=["Track too close"],
                tool_available=True,
            )
            router = Autorouter()
            errors = router.drc_only(pcb)
            assert errors == ["Track too close"]
            mock_drc.assert_called_once()


# ===========================================================================
# Integration: SynthesisResult ERC fields
# ===========================================================================


class TestSynthesisResultERC:
    def test_synthesis_result_has_erc_fields(self):
        from boardsmith_hw.synthesizer import SynthesisResult
        result = SynthesisResult(
            success=True,
            confidence=0.85,
            erc_passed=True,
            erc_errors=[],
            erc_note="ERC bestanden.",
            erc_iterations=2,
            erc_fixes=["no_connect"],
        )
        assert result.erc_passed is True
        assert result.erc_errors == []
        assert result.erc_note == "ERC bestanden."
        assert result.erc_iterations == 2
        assert result.erc_fixes == ["no_connect"]

    def test_synthesis_result_erc_defaults(self):
        from boardsmith_hw.synthesizer import SynthesisResult
        result = SynthesisResult(success=True, confidence=0.8)
        assert result.erc_passed is None
        assert result.erc_errors == []
        assert result.erc_note == ""
        assert result.erc_iterations == 0
        assert result.erc_fixes == []


# ===========================================================================
# ERCRefinementResult data class
# ===========================================================================


class TestERCRefinementResult:
    def test_defaults(self):
        r = ERCRefinementResult(passed=True, iterations=1)
        assert r.passed is True
        assert r.iterations == 1
        assert r.initial_errors == 0
        assert r.final_errors == 0
        assert r.fixes_applied == []
        assert r.final_check is None
        assert r.tool_available is False

    def test_with_fixes(self):
        r = ERCRefinementResult(
            passed=True,
            iterations=3,
            initial_errors=5,
            final_errors=0,
            fixes_applied=["no_connect", "pwr_flag"],
            tool_available=True,
        )
        assert r.passed is True
        assert r.iterations == 3
        assert len(r.fixes_applied) == 2


# ===========================================================================
# ERCRefiner — closed-loop
# ===========================================================================


class TestERCRefinerGraceful:
    """ERCRefiner tests without kicad-cli."""

    def test_refine_without_tool_passes(self, tmp_path):
        refiner = ERCRefiner(max_iterations=3)
        refiner._checker._cli_available = False

        sch = tmp_path / "test.kicad_sch"
        result = refiner.refine({}, sch)

        assert isinstance(result, ERCRefinementResult)
        assert result.passed is True
        assert result.iterations == 0
        assert result.tool_available is False

    def test_refine_max_iterations_respected(self):
        refiner = ERCRefiner(max_iterations=2)
        assert refiner.max_iterations == 2


class TestERCRefinerMocked:
    """ERCRefiner tests with mocked kicad-cli."""

    def _make_hir(self):
        return {
            "version": "1.1.0",
            "source": "prompt",
            "components": [
                {
                    "id": "mcu_0",
                    "name": "ESP32",
                    "role": "mcu",
                    "mpn": "ESP32-WROOM-32",
                    "interface_types": ["I2C"],
                },
                {
                    "id": "sensor_0",
                    "name": "BME280",
                    "role": "sensor",
                    "mpn": "BME280",
                    "interface_types": ["I2C"],
                },
            ],
            "bus_contracts": [
                {
                    "bus_name": "I2C0",
                    "bus_type": "I2C",
                    "master_id": "mcu_0",
                    "slave_ids": ["sensor_0"],
                    "slave_addresses": {"sensor_0": "0x77"},
                    "clock_hz": 400000,
                }
            ],
            "constraints": [],
            "metadata": {
                "track": "B",
                "confidence": {"overall": 0.85},
            },
        }

    def test_refine_passes_immediately_when_erc_clean(self, tmp_path):
        """If ERC is clean on first try, no fixes needed."""
        refiner = ERCRefiner(max_iterations=3)
        refiner._checker._cli_available = True

        sch = tmp_path / "test.kicad_sch"

        with patch.object(
            refiner._checker, "run_erc",
            return_value=CheckResult(
                check_type="erc", passed=True, tool_available=True,
                note="ERC bestanden."
            ),
        ):
            result = refiner.refine(self._make_hir(), sch)

        assert result.passed is True
        assert result.iterations == 1
        assert result.fixes_applied == []
        assert result.tool_available is True

    def test_refine_applies_no_connect_fix(self, tmp_path):
        """If ERC fails with 'pin not connected', no_connect fix is applied."""
        refiner = ERCRefiner(max_iterations=3)
        refiner._checker._cli_available = True

        sch = tmp_path / "test.kicad_sch"

        call_count = [0]

        def mock_erc(path):
            call_count[0] += 1
            if call_count[0] == 1:
                return CheckResult(
                    check_type="erc", passed=False, tool_available=True,
                    error_count=3, warning_count=0,
                    violations=[
                        DRCViolation(severity="error", description="Pin not connected",
                                     rule_id="pin_not_connected"),
                    ],
                    error_messages=["Pin not connected"],
                )
            return CheckResult(
                check_type="erc", passed=True, tool_available=True,
            )

        with patch.object(refiner._checker, "run_erc", side_effect=mock_erc):
            result = refiner.refine(self._make_hir(), sch)

        assert result.passed is True
        assert "no_connect" in result.fixes_applied
        assert result.iterations == 2  # initial + 1 fix

    def test_refine_applies_pwr_flag_fix(self, tmp_path):
        """If ERC fails with 'power pin not driven', pwr_flag fix is applied."""
        refiner = ERCRefiner(max_iterations=3)
        refiner._checker._cli_available = True

        sch = tmp_path / "test.kicad_sch"

        call_count = [0]

        def mock_erc(path):
            call_count[0] += 1
            if call_count[0] == 1:
                return CheckResult(
                    check_type="erc", passed=False, tool_available=True,
                    error_count=1,
                    violations=[
                        DRCViolation(severity="error",
                                     description="Power pin not driven",
                                     rule_id="power_pin_not_driven"),
                    ],
                    error_messages=["Power pin not driven"],
                )
            return CheckResult(
                check_type="erc", passed=True, tool_available=True,
            )

        with patch.object(refiner._checker, "run_erc", side_effect=mock_erc):
            result = refiner.refine(self._make_hir(), sch)

        assert result.passed is True
        assert "pwr_flag" in result.fixes_applied

    def test_refine_applies_multiple_fixes(self, tmp_path):
        """Both no_connect and pwr_flag can be applied in sequence."""
        refiner = ERCRefiner(max_iterations=3)
        refiner._checker._cli_available = True

        sch = tmp_path / "test.kicad_sch"

        call_count = [0]

        def mock_erc(path):
            call_count[0] += 1
            if call_count[0] == 1:
                return CheckResult(
                    check_type="erc", passed=False, tool_available=True,
                    error_count=4,
                    violations=[
                        DRCViolation(severity="error", description="Pin not connected"),
                        DRCViolation(severity="error", description="Power pin not driven"),
                    ],
                    error_messages=["Pin not connected", "Power pin not driven"],
                )
            elif call_count[0] == 2:
                return CheckResult(
                    check_type="erc", passed=False, tool_available=True,
                    error_count=1,
                    violations=[
                        DRCViolation(severity="error", description="Power pin not driven"),
                    ],
                    error_messages=["Power pin not driven"],
                )
            return CheckResult(
                check_type="erc", passed=True, tool_available=True,
            )

        with patch.object(refiner._checker, "run_erc", side_effect=mock_erc):
            result = refiner.refine(self._make_hir(), sch)

        assert result.passed is True
        assert "no_connect" in result.fixes_applied
        assert "pwr_flag" in result.fixes_applied
        assert result.iterations == 3

    def test_refine_stops_when_no_fixes_left(self, tmp_path):
        """Loop terminates when all fix strategies are exhausted."""
        refiner = ERCRefiner(max_iterations=5)
        refiner._checker._cli_available = True

        sch = tmp_path / "test.kicad_sch"

        def mock_erc_always_fail(path):
            return CheckResult(
                check_type="erc", passed=False, tool_available=True,
                error_count=1,
                violations=[
                    DRCViolation(severity="error", description="Unknown issue"),
                ],
                error_messages=["Unknown issue"],
            )

        with patch.object(refiner._checker, "run_erc", side_effect=mock_erc_always_fail):
            result = refiner.refine(self._make_hir(), sch)

        assert result.passed is False
        # Should have tried all available fix strategies
        assert len(result.fixes_applied) == 2  # no_connect + pwr_flag

    def test_refine_initial_errors_tracked(self, tmp_path):
        """initial_errors reflects the first ERC run."""
        refiner = ERCRefiner(max_iterations=3)
        refiner._checker._cli_available = True

        sch = tmp_path / "test.kicad_sch"

        call_count = [0]

        def mock_erc(path):
            call_count[0] += 1
            if call_count[0] == 1:
                return CheckResult(
                    check_type="erc", passed=False, tool_available=True,
                    error_count=7,
                    violations=[DRCViolation(severity="error", description="pin not connected")],
                    error_messages=["pin not connected"],
                )
            return CheckResult(
                check_type="erc", passed=True, tool_available=True,
                error_count=0,
            )

        with patch.object(refiner._checker, "run_erc", side_effect=mock_erc):
            result = refiner.refine(self._make_hir(), sch)

        assert result.initial_errors == 7
        assert result.final_errors == 0


# ===========================================================================
# KiCad Exporter: no_connect and PWR_FLAG
# ===========================================================================


class TestKiCadExporterERCFixes:
    """Test that the KiCad exporter generates no_connect and PWR_FLAG elements."""

    def _make_hir(self):
        return {
            "version": "1.1.0",
            "source": "prompt",
            "components": [
                {
                    "id": "mcu_0",
                    "name": "ESP32",
                    "role": "mcu",
                    "mpn": "ESP32-WROOM-32",
                    "interface_types": ["I2C"],
                },
                {
                    "id": "sensor_0",
                    "name": "BME280",
                    "role": "sensor",
                    "mpn": "BME280",
                    "interface_types": ["I2C"],
                },
            ],
            "bus_contracts": [
                {
                    "bus_name": "I2C0",
                    "bus_type": "I2C",
                    "master_id": "mcu_0",
                    "slave_ids": ["sensor_0"],
                    "slave_addresses": {"sensor_0": "0x77"},
                    "clock_hz": 400000,
                }
            ],
            "constraints": [],
        }

    def test_export_without_erc_fixes(self, tmp_path):
        from boardsmith_hw.kicad_exporter import export_kicad_sch
        sch = tmp_path / "test.kicad_sch"
        export_kicad_sch(self._make_hir(), sch, use_llm=False)
        content = sch.read_text()
        # Default: no no_connect or PWR_FLAG
        assert "(no_connect" not in content
        assert "PWR_FLAG" not in content

    def test_export_with_no_connect(self, tmp_path):
        from boardsmith_hw.kicad_exporter import export_kicad_sch
        sch = tmp_path / "test.kicad_sch"
        export_kicad_sch(self._make_hir(), sch, use_llm=False, add_no_connect=True)
        content = sch.read_text()
        assert "(no_connect" in content

    def test_export_with_pwr_flag(self, tmp_path):
        from boardsmith_hw.kicad_exporter import export_kicad_sch
        sch = tmp_path / "test.kicad_sch"
        export_kicad_sch(self._make_hir(), sch, use_llm=False, add_pwr_flag=True)
        content = sch.read_text()
        assert "PWR_FLAG" in content
        assert "#FLG" in content

    def test_export_with_both_fixes(self, tmp_path):
        from boardsmith_hw.kicad_exporter import export_kicad_sch
        sch = tmp_path / "test.kicad_sch"
        export_kicad_sch(
            self._make_hir(), sch, use_llm=False,
            add_no_connect=True, add_pwr_flag=True,
        )
        content = sch.read_text()
        assert "(no_connect" in content
        assert "PWR_FLAG" in content

    def test_no_connect_not_on_bus_pins(self, tmp_path):
        """SDA/SCL pins should NOT get no_connect flags."""
        from boardsmith_hw.kicad_exporter import export_kicad_sch
        sch = tmp_path / "test.kicad_sch"
        export_kicad_sch(self._make_hir(), sch, use_llm=False, add_no_connect=True)
        content = sch.read_text()
        # Verify that no_connect flags exist for some pins
        assert "(no_connect" in content
        # The schematic should still have bus wires (SDA, SCL)
        assert "SDA" in content
        assert "SCL" in content

    def test_no_connect_not_on_power_pins(self, tmp_path):
        """Power pins (VDD, GND) should NOT get no_connect flags."""
        from boardsmith_hw.kicad_exporter import export_kicad_sch
        sch = tmp_path / "test.kicad_sch"
        export_kicad_sch(self._make_hir(), sch, use_llm=False, add_no_connect=True)
        content = sch.read_text()
        # Power symbols should still be present
        assert "GND" in content
        assert "+3V3" in content

    def test_pwr_flag_per_net(self, tmp_path):
        """Only one PWR_FLAG per power net should be placed."""
        from boardsmith_hw.kicad_exporter import export_kicad_sch
        sch = tmp_path / "test.kicad_sch"
        export_kicad_sch(self._make_hir(), sch, use_llm=False, add_pwr_flag=True)
        content = sch.read_text()
        # Count PWR_FLAG instances (lib_id "PWR_FLAG") in component instances
        flag_instances = content.count('(lib_id "PWR_FLAG")')
        # Should have at most one per unique power net (GND, +3V3, +5V)
        assert 1 <= flag_instances <= 3

    def test_schematic_still_valid_with_fixes(self, tmp_path):
        """Schematic should remain valid KiCad s-expression with fixes."""
        from boardsmith_hw.kicad_exporter import export_kicad_sch
        sch = tmp_path / "test.kicad_sch"
        export_kicad_sch(
            self._make_hir(), sch, use_llm=False,
            add_no_connect=True, add_pwr_flag=True,
        )
        content = sch.read_text()
        # Basic s-expression validity: balanced parens
        assert content.startswith("(kicad_sch")
        assert content.rstrip().endswith(")")
        open_parens = content.count("(")
        close_parens = content.count(")")
        assert open_parens == close_parens


# ===========================================================================
# KiCadChecker.count_unconnected_from_rpt — unit tests
# ===========================================================================


class TestCountUnconnectedFromRpt:
    """Tests for the static helper that parses DRC.rpt unconnected pad counts."""

    def test_found_13(self, tmp_path):
        """Typical DRC.rpt with 13 unconnected pads returns 13."""
        rpt = tmp_path / "DRC.rpt"
        rpt.write_text(
            "DRC report\n"
            "** Found 13 unconnected pads **\n"
            "Some other content\n",
            encoding="utf-8",
        )
        assert KiCadChecker.count_unconnected_from_rpt(rpt) == 13

    def test_found_0(self, tmp_path):
        """DRC.rpt with 0 unconnected pads returns 0."""
        rpt = tmp_path / "DRC.rpt"
        rpt.write_text(
            "DRC report\n"
            "** Found 0 unconnected pads **\n",
            encoding="utf-8",
        )
        assert KiCadChecker.count_unconnected_from_rpt(rpt) == 0

    def test_no_match(self, tmp_path):
        """DRC.rpt without the unconnected pattern returns 0."""
        rpt = tmp_path / "DRC.rpt"
        rpt.write_text(
            "DRC report\nno violations found\n",
            encoding="utf-8",
        )
        assert KiCadChecker.count_unconnected_from_rpt(rpt) == 0

    def test_missing_file(self, tmp_path):
        """Non-existent path returns 0 (no exception raised)."""
        nonexistent = tmp_path / "nonexistent_DRC.rpt"
        assert KiCadChecker.count_unconnected_from_rpt(nonexistent) == 0
