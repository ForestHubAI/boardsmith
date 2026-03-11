# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for JLCPCBDRCChecker — Phase 25.4.

Covers:
  - Board dimension checks (min/max/standard pricing tier)
  - Track width checks (error + warning thresholds)
  - Via geometry checks (drill + size)
  - Edge.Cuts presence check
  - check_text() API (no real file needed)
  - check() API with real temp file
  - summary() output format
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler"):
    _p = str(_REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from boardsmith_hw.jlcpcb_drc import (
    JLCPCBDRCChecker,
    JLCPCBDRCResult,
    DRCIssue,
    BOARD_MAX_WIDTH_MM,
    BOARD_MAX_HEIGHT_MM,
    BOARD_MIN_WIDTH_MM,
    BOARD_MIN_HEIGHT_MM,
    BOARD_STANDARD_MAX_MM,
    TRACK_WIDTH_MIN_MM,
    DRILL_MIN_DIAMETER_MM,
    DRILL_RECOMMENDED_MM,
    VIA_SIZE_MIN_MM,
)


# ---------------------------------------------------------------------------
# Minimal valid PCB text
# ---------------------------------------------------------------------------

_VALID_PCB = """\
(kicad_pcb (version 20221018)
  (gr_rect (start 0 0) (end 80 60) (layer "Edge.Cuts") (width 0.05))
  (segment (start 10 10) (end 70 10) (width 0.25) (layer "F.Cu") (net 1))
  (via (at 50 30) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net 1))
)
"""

_PCB_NO_EDGES = """\
(kicad_pcb (version 20221018)
  (segment (start 10 10) (end 70 10) (width 0.25) (layer "F.Cu") (net 1))
)
"""

_PCB_NARROW_TRACK = """\
(kicad_pcb (version 20221018)
  (gr_rect (start 0 0) (end 80 60) (layer "Edge.Cuts") (width 0.05))
  (segment (start 10 10) (end 70 10) (width 0.10) (layer "F.Cu") (net 1))
)
"""

_PCB_BORDERLINE_TRACK = """\
(kicad_pcb (version 20221018)
  (gr_rect (start 0 0) (end 80 60) (layer "Edge.Cuts") (width 0.05))
  (segment (start 10 10) (end 70 10) (width 0.13) (layer "F.Cu") (net 1))
)
"""

_PCB_SMALL_DRILL = """\
(kicad_pcb (version 20221018)
  (gr_rect (start 0 0) (end 80 60) (layer "Edge.Cuts") (width 0.05))
  (via (at 50 30) (size 0.6) (drill 0.15) (layers "F.Cu" "B.Cu") (net 1))
)
"""

_PCB_SMALL_VIA_SIZE = """\
(kicad_pcb (version 20221018)
  (gr_rect (start 0 0) (end 80 60) (layer "Edge.Cuts") (width 0.05))
  (via (at 50 30) (size 0.3) (drill 0.2) (layers "F.Cu" "B.Cu") (net 1))
)
"""

_PCB_LARGE_BOARD = """\
(kicad_pcb (version 20221018)
  (gr_rect (start 0 0) (end 150 120) (layer "Edge.Cuts") (width 0.05))
  (segment (start 10 10) (end 70 10) (width 0.25) (layer "F.Cu") (net 1))
)
"""

_PCB_OVERSIZED = """\
(kicad_pcb (version 20221018)
  (gr_rect (start 0 0) (end 600 400) (layer "Edge.Cuts") (width 0.05))
)
"""

_PCB_TOO_SMALL = """\
(kicad_pcb (version 20221018)
  (gr_rect (start 0 0) (end 3 2) (layer "Edge.Cuts") (width 0.05))
)
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _checker() -> JLCPCBDRCChecker:
    return JLCPCBDRCChecker()


def _severities(result: JLCPCBDRCResult) -> list[str]:
    return [i.severity for i in result.issues]


# ---------------------------------------------------------------------------
# TestDRCIssue
# ---------------------------------------------------------------------------


class TestDRCIssue:
    def test_str_no_values(self):
        issue = DRCIssue(severity="error", rule="test_rule", message="Test message")
        s = str(issue)
        assert "[ERROR]" in s
        assert "test_rule" in s
        assert "Test message" in s

    def test_str_with_values(self):
        issue = DRCIssue(
            severity="warning",
            rule="min_track_width",
            message="Track too narrow",
            value=0.1,
            limit=0.127,
        )
        s = str(issue)
        assert "measured=0.100mm" in s
        assert "limit=0.127mm" in s

    def test_severity_upper_in_str(self):
        issue = DRCIssue(severity="warning", rule="r", message="m")
        assert "[WARNING]" in str(issue)


# ---------------------------------------------------------------------------
# TestJLCPCBDRCResult
# ---------------------------------------------------------------------------


class TestJLCPCBDRCResult:
    def test_errors_property(self):
        result = JLCPCBDRCResult(pcb_path=None)
        result.issues = [
            DRCIssue("error", "r1", "e1"),
            DRCIssue("warning", "r2", "w1"),
            DRCIssue("info", "r3", "i1"),
        ]
        assert len(result.errors) == 1
        assert len(result.warnings) == 1

    def test_valid_no_errors(self):
        result = JLCPCBDRCResult(pcb_path=None)
        result.issues = [DRCIssue("warning", "r", "w")]
        assert result.valid is True

    def test_valid_with_errors(self):
        result = JLCPCBDRCResult(pcb_path=None)
        result.issues = [DRCIssue("error", "r", "e")]
        assert result.valid is False

    def test_summary_contains_board_size(self):
        result = JLCPCBDRCResult(pcb_path=None)
        result.board_width_mm = 80.0
        result.board_height_mm = 60.0
        s = result.summary()
        assert "80.0" in s
        assert "60.0" in s

    def test_summary_pass_mark(self):
        result = JLCPCBDRCResult(pcb_path=None)
        assert "✓" in result.summary()

    def test_summary_fail_mark(self):
        result = JLCPCBDRCResult(pcb_path=None)
        result.issues = [DRCIssue("error", "r", "e")]
        assert "✗" in result.summary()

    def test_summary_issue_counts(self):
        result = JLCPCBDRCResult(pcb_path=None)
        result.issues = [
            DRCIssue("error", "r1", "e1"),
            DRCIssue("warning", "r2", "w1"),
        ]
        s = result.summary()
        assert "1 error" in s
        assert "1 warning" in s


# ---------------------------------------------------------------------------
# TestCheckText — board dimension checks
# ---------------------------------------------------------------------------


class TestBoardDimensionChecks:
    def test_valid_board_no_dimension_errors(self):
        result = _checker().check_text(_VALID_PCB)
        errors = [i for i in result.errors if "board" in i.rule]
        assert errors == []

    def test_board_size_extracted_correctly(self):
        result = _checker().check_text(_VALID_PCB)
        assert abs(result.board_width_mm - 80.0) < 0.1
        assert abs(result.board_height_mm - 60.0) < 0.1

    def test_no_edges_gives_warning(self):
        result = _checker().check_text(_PCB_NO_EDGES)
        rules = [i.rule for i in result.issues]
        assert "board_outline" in rules or "missing_edge_cuts" in rules

    def test_oversized_board_gives_error(self):
        result = _checker().check_text(_PCB_OVERSIZED)
        assert not result.valid
        rules = [i.rule for i in result.errors]
        assert "board_max_width" in rules or "board_max_height" in rules

    def test_too_small_board_gives_error(self):
        result = _checker().check_text(_PCB_TOO_SMALL)
        assert not result.valid
        rules = [i.rule for i in result.errors]
        assert "board_min_width" in rules or "board_min_height" in rules

    def test_large_board_extended_pricing_info(self):
        result = _checker().check_text(_PCB_LARGE_BOARD)
        rules = [i.rule for i in result.issues]
        assert "board_extended_price" in rules

    def test_standard_size_board_no_extended_info(self):
        result = _checker().check_text(_VALID_PCB)
        rules = [i.rule for i in result.issues]
        assert "board_extended_price" not in rules


# ---------------------------------------------------------------------------
# TestTrackWidthChecks
# ---------------------------------------------------------------------------


class TestTrackWidthChecks:
    def test_valid_track_no_issues(self):
        result = _checker().check_text(_VALID_PCB)
        track_issues = [i for i in result.issues if "track" in i.rule]
        assert track_issues == []

    def test_narrow_track_error(self):
        result = _checker().check_text(_PCB_NARROW_TRACK)
        assert not result.valid
        assert any(i.rule == "min_track_width" for i in result.errors)

    def test_narrow_track_value_reported(self):
        result = _checker().check_text(_PCB_NARROW_TRACK)
        issue = next(i for i in result.errors if i.rule == "min_track_width")
        assert issue.value is not None
        assert issue.value < TRACK_WIDTH_MIN_MM

    def test_borderline_track_warning(self):
        """0.13mm is above 0.127mm minimum but below 0.15mm recommended."""
        result = _checker().check_text(_PCB_BORDERLINE_TRACK)
        # Should be valid (no errors), but warn
        assert result.valid
        assert any(i.rule == "narrow_track_width" for i in result.warnings)

    def test_track_count_tracked(self):
        result = _checker().check_text(_VALID_PCB)
        assert result.track_count == 1

    def test_no_tracks_no_issues(self):
        pcb = """\
(kicad_pcb (version 20221018)
  (gr_rect (start 0 0) (end 80 60) (layer "Edge.Cuts") (width 0.05))
)
"""
        result = _checker().check_text(pcb)
        track_issues = [i for i in result.issues if "track" in i.rule]
        assert track_issues == []


# ---------------------------------------------------------------------------
# TestViaGeometryChecks
# ---------------------------------------------------------------------------


class TestViaGeometryChecks:
    def test_valid_via_no_issues(self):
        result = _checker().check_text(_VALID_PCB)
        via_issues = [i for i in result.issues if "via" in i.rule or "drill" in i.rule]
        assert via_issues == []

    def test_small_drill_error(self):
        result = _checker().check_text(_PCB_SMALL_DRILL)
        assert not result.valid
        assert any(i.rule == "min_via_drill" for i in result.errors)

    def test_small_drill_value_reported(self):
        result = _checker().check_text(_PCB_SMALL_DRILL)
        issue = next(i for i in result.errors if i.rule == "min_via_drill")
        assert issue.value == pytest.approx(0.15)

    def test_drill_between_min_and_recommended_warns(self):
        pcb = """\
(kicad_pcb (version 20221018)
  (gr_rect (start 0 0) (end 80 60) (layer "Edge.Cuts") (width 0.05))
  (via (at 50 30) (size 0.6) (drill 0.25) (layers "F.Cu" "B.Cu") (net 1))
)
"""
        result = _checker().check_text(pcb)
        assert result.valid   # 0.25 > 0.2 minimum → no error
        assert any(i.rule == "small_via_drill" for i in result.warnings)

    def test_via_size_too_small_error(self):
        result = _checker().check_text(_PCB_SMALL_VIA_SIZE)
        assert not result.valid
        assert any(i.rule == "min_via_size" for i in result.errors)

    def test_via_count_tracked(self):
        result = _checker().check_text(_VALID_PCB)
        assert result.via_count == 1

    def test_no_vias_no_issues(self):
        pcb = """\
(kicad_pcb (version 20221018)
  (gr_rect (start 0 0) (end 80 60) (layer "Edge.Cuts") (width 0.05))
  (segment (start 10 10) (end 70 10) (width 0.25) (layer "F.Cu") (net 1))
)
"""
        result = _checker().check_text(pcb)
        via_issues = [i for i in result.issues if "via" in i.rule or "drill" in i.rule]
        assert via_issues == []


# ---------------------------------------------------------------------------
# TestEdgeCutsCheck
# ---------------------------------------------------------------------------


class TestEdgeCutsCheck:
    def test_missing_edge_cuts_error(self):
        pcb = "(kicad_pcb (version 20221018))"
        result = _checker().check_text(pcb)
        assert not result.valid
        assert any(i.rule == "missing_edge_cuts" for i in result.errors)

    def test_present_edge_cuts_no_error(self):
        result = _checker().check_text(_VALID_PCB)
        edge_errors = [i for i in result.errors if "edge" in i.rule.lower()]
        assert edge_errors == []

    def test_edge_cuts_keyword_variants(self):
        """Both quoted and unquoted Edge.Cuts are accepted."""
        pcb_quoted = '(kicad_pcb (gr_rect (start 0 0) (end 80 60) (layer "Edge.Cuts")))'
        pcb_unquoted = "(kicad_pcb (gr_rect (start 0 0) (end 80 60) (layer Edge.Cuts)))"
        for pcb in (pcb_quoted, pcb_unquoted):
            result = _checker().check_text(pcb)
            assert not any(i.rule == "missing_edge_cuts" for i in result.issues), pcb


# ---------------------------------------------------------------------------
# TestCheckAPI — file-based check()
# ---------------------------------------------------------------------------


class TestCheckAPI:
    def test_check_reads_file(self, tmp_path):
        pcb_path = tmp_path / "board.kicad_pcb"
        pcb_path.write_text(_VALID_PCB, encoding="utf-8")
        result = _checker().check(pcb_path)
        assert result.pcb_path == pcb_path
        assert result.valid

    def test_check_invalid_board(self, tmp_path):
        pcb_path = tmp_path / "bad.kicad_pcb"
        pcb_path.write_text(_PCB_NARROW_TRACK, encoding="utf-8")
        result = _checker().check(pcb_path)
        assert not result.valid

    def test_check_text_pcb_path_optional(self):
        result = _checker().check_text(_VALID_PCB, pcb_path=None)
        assert result.pcb_path is None


# ---------------------------------------------------------------------------
# TestConstants — confirm limits match JLCPCB published specs
# ---------------------------------------------------------------------------


class TestJLCPCBLimits:
    def test_track_width_min(self):
        assert TRACK_WIDTH_MIN_MM == pytest.approx(0.127)

    def test_drill_min(self):
        assert DRILL_MIN_DIAMETER_MM == pytest.approx(0.2)

    def test_drill_recommended(self):
        assert DRILL_RECOMMENDED_MM == pytest.approx(0.3)

    def test_via_size_min(self):
        # drill + 2 * annular_ring = 0.2 + 2*0.1 = 0.4
        assert VIA_SIZE_MIN_MM == pytest.approx(0.4)

    def test_board_max(self):
        assert BOARD_MAX_WIDTH_MM == 500.0
        assert BOARD_MAX_HEIGHT_MM == 500.0

    def test_board_min(self):
        assert BOARD_MIN_WIDTH_MM == 5.0
        assert BOARD_MIN_HEIGHT_MM == 5.0

    def test_standard_tier_max(self):
        assert BOARD_STANDARD_MAX_MM == 100.0
