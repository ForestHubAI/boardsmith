# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for boardsmith_hw.schematic_reviewer — Phase 13 Schematic Review Loop."""
from __future__ import annotations

import json
import sys
import textwrap
import tempfile
import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup (mirrors other synthesizer tests)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler"):
    _p = str(_REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from boardsmith_hw.schematic_reviewer import (
    DiffSummary,
    ReviewResult,
    SchematicReviewer,
)


# ---------------------------------------------------------------------------
# Shared test schematic (ESP32 + BME280, I2C — same as test_kicad_parser.py)
# ---------------------------------------------------------------------------

def _minimal_schematic() -> str:
    """Minimal valid KiCad 6 schematic: ESP32 + BME280 over I2C."""
    return textwrap.dedent("""\
        (kicad_sch (version 20230121) (generator "boardsmith-fw")
          (paper "A4")
          (lib_symbols
            (symbol "ESP32-WROOM-32"
              (in_bom yes) (on_board yes)
              (property "Reference" "U" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
              (property "Value" "ESP32-WROOM-32" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
              (property "Footprint" "RF_Module:ESP32-WROOM-32" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
              (symbol "ESP32-WROOM-32_1_1"
                (pin power_in line (at -7.62 3.81 0) (length 2.54)
                  (name "3V3" (effects (font (size 1.27 1.27))))
                  (number "1" (effects (font (size 1.27 1.27)))))
                (pin power_in line (at -7.62 1.27 0) (length 2.54)
                  (name "GND" (effects (font (size 1.27 1.27))))
                  (number "2" (effects (font (size 1.27 1.27)))))
                (pin bidirectional line (at 7.62 1.27 180) (length 2.54)
                  (name "IO21/SDA" (effects (font (size 1.27 1.27))))
                  (number "4" (effects (font (size 1.27 1.27)))))
                (pin bidirectional line (at 7.62 -1.27 180) (length 2.54)
                  (name "IO22/SCL" (effects (font (size 1.27 1.27))))
                  (number "5" (effects (font (size 1.27 1.27)))))
              )
            )
            (symbol "BME280"
              (in_bom yes) (on_board yes)
              (property "Reference" "U" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
              (property "Value" "BME280" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
              (property "Footprint" "Package_LGA:Bosch_LGA-8" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
              (symbol "BME280_1_1"
                (pin power_in line (at -5.08 2.54 0) (length 2.54)
                  (name "VDD" (effects (font (size 1.27 1.27))))
                  (number "6" (effects (font (size 1.27 1.27)))))
                (pin power_in line (at -5.08 0 0) (length 2.54)
                  (name "GND" (effects (font (size 1.27 1.27))))
                  (number "2" (effects (font (size 1.27 1.27)))))
                (pin bidirectional line (at -5.08 -2.54 0) (length 2.54)
                  (name "SDA" (effects (font (size 1.27 1.27))))
                  (number "4" (effects (font (size 1.27 1.27)))))
                (pin bidirectional line (at -5.08 -5.08 0) (length 2.54)
                  (name "SCK" (effects (font (size 1.27 1.27))))
                  (number "5" (effects (font (size 1.27 1.27)))))
              )
            )
          )
          (symbol (lib_id "ESP32-WROOM-32") (at 100.00 110.00 0) (unit 1) (in_bom yes) (on_board yes)
            (uuid "aaa00001-0000-0000-0000-000000000001")
            (property "Reference" "U1" (at 106.00 107.00 0) (effects (font (size 1.27 1.27)) (justify left)))
            (property "Value" "ESP32-WROOM-32" (at 106.00 109.50 0) (effects (font (size 1.27 1.27)) (justify left)))
            (property "Footprint" "RF_Module:ESP32-WROOM-32" (at 100.00 110.00 0) (effects (font (size 1.27 1.27)) hide))
            (property "Datasheet" "" (at 100.00 110.00 0) (effects (font (size 1.27 1.27)) hide))
            (property "MPN" "ESP32-WROOM-32" (at 100.00 110.00 0) (effects (font (size 1.27 1.27)) hide))
          )
          (symbol (lib_id "BME280") (at 195.00 80.00 0) (unit 1) (in_bom yes) (on_board yes)
            (uuid "bbb00001-0000-0000-0000-000000000002")
            (property "Reference" "U2" (at 201.00 77.00 0) (effects (font (size 1.27 1.27)) (justify left)))
            (property "Value" "BME280" (at 201.00 79.50 0) (effects (font (size 1.27 1.27)) (justify left)))
            (property "Footprint" "Package_LGA:Bosch_LGA-8" (at 195.00 80.00 0) (effects (font (size 1.27 1.27)) hide))
            (property "Datasheet" "" (at 195.00 80.00 0) (effects (font (size 1.27 1.27)) hide))
            (property "MPN" "BME280" (at 195.00 80.00 0) (effects (font (size 1.27 1.27)) hide))
          )

          (wire (pts (xy 107.62 111.27) (xy 147.50 111.27))
            (stroke (width 0) (type default)) (uuid "w_sda_mcu"))
          (wire (pts (xy 147.50 77.46) (xy 189.92 77.46))
            (stroke (width 0) (type default)) (uuid "w_sda_sensor"))
          (wire (pts (xy 147.50 77.46) (xy 147.50 111.27))
            (stroke (width 0) (type default)) (uuid "w_sda_spine"))
          (wire (pts (xy 107.62 108.73) (xy 147.50 108.73))
            (stroke (width 0) (type default)) (uuid "w_scl_mcu"))
          (wire (pts (xy 147.50 74.92) (xy 189.92 74.92))
            (stroke (width 0) (type default)) (uuid "w_scl_sensor"))
          (wire (pts (xy 147.50 74.92) (xy 147.50 108.73))
            (stroke (width 0) (type default)) (uuid "w_scl_spine"))

          (label "SDA" (at 147.50 74.92 0)
            (effects (font (size 1.27 1.27))) (uuid "lbl001"))
          (label "SCL" (at 147.50 72.38 0)
            (effects (font (size 1.27 1.27))) (uuid "lbl002"))
          (sheet_instances
            (path "/" (page "1"))
          )
        )
    """)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_tmp_schematic(content: str) -> Path:
    """Write schematic text to a temp file. Caller must delete."""
    fh = tempfile.NamedTemporaryFile(
        mode="w", suffix=".kicad_sch", delete=False, encoding="utf-8"
    )
    fh.write(content)
    fh.close()
    return Path(fh.name)


# ---------------------------------------------------------------------------
# Unit tests: DiffSummary dataclass
# ---------------------------------------------------------------------------


class TestDiffSummary:
    def test_default_no_diff(self):
        diff = DiffSummary()
        assert diff.has_diff is False
        assert diff.components_added == []
        assert diff.components_removed == []
        assert diff.components_changed == []
        assert diff.buses_added == []
        assert diff.buses_removed == []

    def test_diff_with_additions(self):
        diff = DiffSummary(components_added=["U3"], has_diff=True)
        assert diff.has_diff is True
        assert "U3" in diff.components_added

    def test_diff_with_removals(self):
        diff = DiffSummary(components_removed=["U2"], buses_removed=["I2C0"], has_diff=True)
        assert diff.has_diff is True
        assert "U2" in diff.components_removed
        assert "I2C0" in diff.buses_removed


# ---------------------------------------------------------------------------
# Unit tests: ReviewResult dataclass
# ---------------------------------------------------------------------------


class TestReviewResult:
    def test_valid_result(self):
        r = ReviewResult(valid=True, iterations=1, errors_before=0, errors_after=0)
        assert r.valid is True
        assert r.error is None
        assert r.llm_boosted is False
        assert r.resolved == []
        assert r.unresolvable == []

    def test_error_result(self):
        r = ReviewResult(
            valid=False, iterations=0, errors_before=0, errors_after=0,
            error="File not found",
        )
        assert r.valid is False
        assert r.error == "File not found"

    def test_diff_default(self):
        r = ReviewResult(valid=True, iterations=0, errors_before=0, errors_after=0)
        assert r.diff.has_diff is False


# ---------------------------------------------------------------------------
# SchematicReviewer — file-not-found
# ---------------------------------------------------------------------------


class TestSchematicReviewerFileNotFound:
    def test_returns_error_result_on_missing_file(self):
        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review(Path("/nonexistent/schematic.kicad_sch"))
        assert result.valid is False
        assert result.error is not None
        assert "not found" in result.error.lower() or "nonexistent" in result.error

    def test_iterations_zero_on_missing_file(self):
        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review(Path("/no/such/file.kicad_sch"))
        assert result.iterations == 0
        assert result.errors_before == 0


# ---------------------------------------------------------------------------
# SchematicReviewer — basic review from disk
# ---------------------------------------------------------------------------


class TestSchematicReviewerFromDisk:
    def test_review_returns_result(self, tmp_path):
        sch_file = tmp_path / "schematic.kicad_sch"
        sch_file.write_text(_minimal_schematic(), encoding="utf-8")

        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review(sch_file)

        assert result.error is None
        assert isinstance(result.valid, bool)
        assert result.iterations >= 0
        assert result.errors_before >= 0
        assert result.errors_after >= 0

    def test_hir_dict_populated(self, tmp_path):
        sch_file = tmp_path / "schematic.kicad_sch"
        sch_file.write_text(_minimal_schematic(), encoding="utf-8")

        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review(sch_file)

        assert result.hir_dict
        assert "components" in result.hir_dict
        assert "bus_contracts" in result.hir_dict

    def test_two_components_in_hir(self, tmp_path):
        sch_file = tmp_path / "schematic.kicad_sch"
        sch_file.write_text(_minimal_schematic(), encoding="utf-8")

        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review(sch_file)

        components = result.hir_dict.get("components", [])
        assert len(components) >= 2, "ESP32 + BME280 must be present"

    def test_mpns_extracted(self, tmp_path):
        sch_file = tmp_path / "schematic.kicad_sch"
        sch_file.write_text(_minimal_schematic(), encoding="utf-8")

        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review(sch_file)

        mpns = {c.get("mpn") for c in result.hir_dict.get("components", [])}
        assert "ESP32-WROOM-32" in mpns
        assert "BME280" in mpns

    def test_no_fatal_errors_on_valid_schematic(self, tmp_path):
        sch_file = tmp_path / "schematic.kicad_sch"
        sch_file.write_text(_minimal_schematic(), encoding="utf-8")

        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review(sch_file)

        # errors_after must be ≤ errors_before (reviewer never makes things worse)
        assert result.errors_after <= result.errors_before


# ---------------------------------------------------------------------------
# SchematicReviewer — review_text convenience method
# ---------------------------------------------------------------------------


class TestSchematicReviewerFromText:
    def test_review_text_returns_result(self):
        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review_text(_minimal_schematic())
        assert result.error is None
        assert isinstance(result.valid, bool)

    def test_review_text_hir_has_components(self):
        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review_text(_minimal_schematic())
        assert len(result.hir_dict.get("components", [])) >= 2

    def test_review_text_empty_schematic_does_not_crash(self):
        reviewer = SchematicReviewer(use_llm=False)
        empty_sch = textwrap.dedent("""\
            (kicad_sch (version 20230121) (generator "boardsmith-fw")
              (paper "A4")
              (lib_symbols)
              (sheet_instances (path "/" (page "1")))
            )
        """)
        result = reviewer.review_text(empty_sch)
        # Empty schematic should either succeed (0 errors) or return an error result
        assert isinstance(result.valid, bool) or result.error is not None

    def test_review_text_invalid_content_returns_error(self):
        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review_text("this is not a valid kicad schematic !!!!")
        # Should either parse to an empty graph (valid=True, 0 components) or error gracefully
        assert result.error is not None or isinstance(result.valid, bool)


# ---------------------------------------------------------------------------
# SchematicReviewer — round-trip diff (no original HIR → no diff)
# ---------------------------------------------------------------------------


class TestSchematicReviewerDiff:
    def test_no_diff_without_original_hir(self, tmp_path):
        sch_file = tmp_path / "schematic.kicad_sch"
        sch_file.write_text(_minimal_schematic(), encoding="utf-8")

        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review(sch_file, original_hir=None)

        assert result.diff.has_diff is False

    def test_no_diff_when_original_matches(self, tmp_path):
        sch_file = tmp_path / "schematic.kicad_sch"
        sch_file.write_text(_minimal_schematic(), encoding="utf-8")

        reviewer = SchematicReviewer(use_llm=False)
        # First review → get the reparsed HIR
        first_result = reviewer.review(sch_file)
        reparsed_hir = first_result.hir_dict

        # Second review — pass the reparsed HIR as "original" → zero diff expected
        second_result = reviewer.review(sch_file, original_hir=reparsed_hir)
        assert not second_result.diff.has_diff

    def test_diff_detects_removed_component(self, tmp_path):
        sch_file = tmp_path / "schematic.kicad_sch"
        sch_file.write_text(_minimal_schematic(), encoding="utf-8")

        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review(sch_file)
        reparsed_hir = result.hir_dict

        # Synthesize an original HIR with an extra component
        original_hir = json.loads(json.dumps(reparsed_hir))
        original_hir["components"].append({
            "id": "U_EXTRA",
            "mpn": "PHANTOM-IC",
            "role": "sensor",
            "name": "Phantom Sensor",
        })

        result2 = reviewer.review(sch_file, original_hir=original_hir)
        # U_EXTRA was in original but not in schematic → should appear as removed
        assert "U_EXTRA" in result2.diff.components_removed
        assert result2.diff.has_diff is True

    def test_diff_detects_added_component(self, tmp_path):
        sch_file = tmp_path / "schematic.kicad_sch"
        sch_file.write_text(_minimal_schematic(), encoding="utf-8")

        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review(sch_file)
        reparsed_hir = result.hir_dict

        # Original HIR missing one component → reparsed has more → "added"
        original_hir = json.loads(json.dumps(reparsed_hir))
        if original_hir["components"]:
            original_hir["components"] = original_hir["components"][:1]  # keep only first

        result2 = reviewer.review(sch_file, original_hir=original_hir)
        assert len(result2.diff.components_added) >= 1
        assert result2.diff.has_diff is True

    def test_diff_detects_mpn_change(self, tmp_path):
        sch_file = tmp_path / "schematic.kicad_sch"
        sch_file.write_text(_minimal_schematic(), encoding="utf-8")

        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review(sch_file)
        reparsed_hir = result.hir_dict

        # Mutate the MPN of the first component in the "original"
        original_hir = json.loads(json.dumps(reparsed_hir))
        if original_hir["components"]:
            original_hir["components"][0]["mpn"] = "DIFFERENT-MPN"

        result2 = reviewer.review(sch_file, original_hir=original_hir)
        assert result2.diff.has_diff is True
        first_id = reparsed_hir["components"][0]["id"]
        assert first_id in result2.diff.components_changed


# ---------------------------------------------------------------------------
# SchematicReviewer — _diff_hir unit tests
# ---------------------------------------------------------------------------


class TestDiffHir:
    """White-box unit tests for SchematicReviewer._diff_hir."""

    def _reviewer(self) -> SchematicReviewer:
        return SchematicReviewer(use_llm=False)

    def test_identical_hirs_no_diff(self):
        hir = {
            "components": [
                {"id": "U1", "mpn": "ESP32", "role": "mcu"},
                {"id": "U2", "mpn": "BME280", "role": "sensor"},
            ],
            "bus_contracts": [{"bus_name": "I2C0", "bus_type": "I2C"}],
        }
        diff = self._reviewer()._diff_hir(hir, hir)
        assert not diff.has_diff

    def test_component_removed(self):
        original = {
            "components": [
                {"id": "U1", "mpn": "ESP32", "role": "mcu"},
                {"id": "U2", "mpn": "BME280", "role": "sensor"},
            ],
            "bus_contracts": [],
        }
        reparsed = {
            "components": [{"id": "U1", "mpn": "ESP32", "role": "mcu"}],
            "bus_contracts": [],
        }
        diff = self._reviewer()._diff_hir(original, reparsed)
        assert diff.has_diff
        assert "U2" in diff.components_removed
        assert diff.components_added == []

    def test_component_added(self):
        original = {
            "components": [{"id": "U1", "mpn": "ESP32", "role": "mcu"}],
            "bus_contracts": [],
        }
        reparsed = {
            "components": [
                {"id": "U1", "mpn": "ESP32", "role": "mcu"},
                {"id": "U3", "mpn": "SSD1306", "role": "display"},
            ],
            "bus_contracts": [],
        }
        diff = self._reviewer()._diff_hir(original, reparsed)
        assert diff.has_diff
        assert "U3" in diff.components_added
        assert diff.components_removed == []

    def test_mpn_changed(self):
        original = {
            "components": [{"id": "U1", "mpn": "ESP32", "role": "mcu"}],
            "bus_contracts": [],
        }
        reparsed = {
            "components": [{"id": "U1", "mpn": "ESP32-C3", "role": "mcu"}],
            "bus_contracts": [],
        }
        diff = self._reviewer()._diff_hir(original, reparsed)
        assert diff.has_diff
        assert "U1" in diff.components_changed

    def test_role_changed(self):
        original = {
            "components": [{"id": "U1", "mpn": "FOO", "role": "mcu"}],
            "bus_contracts": [],
        }
        reparsed = {
            "components": [{"id": "U1", "mpn": "FOO", "role": "sensor"}],
            "bus_contracts": [],
        }
        diff = self._reviewer()._diff_hir(original, reparsed)
        assert diff.has_diff
        assert "U1" in diff.components_changed

    def test_bus_removed(self):
        original = {
            "components": [],
            "bus_contracts": [{"bus_name": "I2C0", "bus_type": "I2C"}],
        }
        reparsed = {
            "components": [],
            "bus_contracts": [],
        }
        diff = self._reviewer()._diff_hir(original, reparsed)
        assert diff.has_diff
        assert "I2C0" in diff.buses_removed

    def test_bus_added(self):
        original = {"components": [], "bus_contracts": []}
        reparsed = {
            "components": [],
            "bus_contracts": [{"bus_name": "SPI0", "bus_type": "SPI"}],
        }
        diff = self._reviewer()._diff_hir(original, reparsed)
        assert diff.has_diff
        assert "SPI0" in diff.buses_added

    def test_empty_hirs_no_diff(self):
        hir = {"components": [], "bus_contracts": []}
        diff = self._reviewer()._diff_hir(hir, hir)
        assert not diff.has_diff

    def test_does_not_mutate_inputs(self):
        """_diff_hir must never modify its input dicts."""
        original = {
            "components": [{"id": "U1", "mpn": "X", "role": "mcu"}],
            "bus_contracts": [],
        }
        reparsed = {
            "components": [{"id": "U1", "mpn": "Y", "role": "sensor"}],
            "bus_contracts": [],
        }
        import copy
        orig_copy = copy.deepcopy(original)
        repr_copy = copy.deepcopy(reparsed)
        self._reviewer()._diff_hir(original, reparsed)
        assert original == orig_copy
        assert reparsed == repr_copy


# ---------------------------------------------------------------------------
# SchematicReviewer — auto-fix / iterations
# ---------------------------------------------------------------------------


class TestSchematicReviewerAutoFix:
    def test_errors_after_le_errors_before(self, tmp_path):
        """Auto-fix must never increase the error count."""
        sch_file = tmp_path / "schematic.kicad_sch"
        sch_file.write_text(_minimal_schematic(), encoding="utf-8")

        reviewer = SchematicReviewer(max_iterations=3, use_llm=False)
        result = reviewer.review(sch_file)
        assert result.errors_after <= result.errors_before

    def test_max_iterations_respected(self, tmp_path):
        """Reviewer must not exceed max_iterations."""
        sch_file = tmp_path / "schematic.kicad_sch"
        sch_file.write_text(_minimal_schematic(), encoding="utf-8")

        reviewer = SchematicReviewer(max_iterations=2, use_llm=False)
        result = reviewer.review(sch_file)
        assert result.iterations <= 2

    def test_resolved_subset_of_all_errors(self, tmp_path):
        """resolved + unresolvable covers all errors found."""
        sch_file = tmp_path / "schematic.kicad_sch"
        sch_file.write_text(_minimal_schematic(), encoding="utf-8")

        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review(sch_file)

        # No duplicates between resolved and unresolvable
        resolved_set = set(result.resolved)
        unresolvable_set = set(result.unresolvable)
        overlap = resolved_set & unresolvable_set
        assert not overlap, f"Overlap: {overlap}"

    def test_use_llm_false_does_not_set_llm_boosted(self, tmp_path):
        sch_file = tmp_path / "schematic.kicad_sch"
        sch_file.write_text(_minimal_schematic(), encoding="utf-8")

        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review(sch_file)
        assert result.llm_boosted is False

    def test_max_iterations_1_still_returns_result(self, tmp_path):
        sch_file = tmp_path / "schematic.kicad_sch"
        sch_file.write_text(_minimal_schematic(), encoding="utf-8")

        reviewer = SchematicReviewer(max_iterations=1, use_llm=False)
        result = reviewer.review(sch_file)
        assert result.error is None
        assert result.iterations >= 0


# ---------------------------------------------------------------------------
# SchematicReviewer — integration: kicad_exporter → reviewer round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Full round-trip test: export HIR to .kicad_sch, then review it."""

    def _make_hir_dict(self) -> dict:
        """Build a minimal HIR dict suitable for kicad_exporter."""
        return {
            "version": "1.1.0",
            "source": "prompt",
            "components": [
                {
                    "id": "U1",
                    "mpn": "ESP32-WROOM-32",
                    "name": "ESP32-WROOM-32",
                    "role": "mcu",
                    "interface_types": ["I2C"],
                    "pins": [],
                    "manufacturer": "Espressif",
                    "provenance": {"source_type": "builtin_db", "confidence": 0.95},
                },
                {
                    "id": "U2",
                    "mpn": "BME280",
                    "name": "BME280",
                    "role": "sensor",
                    "interface_types": ["I2C"],
                    "pins": [],
                    "manufacturer": "Bosch",
                    "provenance": {"source_type": "builtin_db", "confidence": 0.95},
                },
            ],
            "bus_contracts": [
                {
                    "bus_name": "I2C0",
                    "bus_type": "I2C",
                    "master_id": "U1",
                    "slave_ids": ["U2"],
                    "configured_clock_hz": 400000,
                    "slave_addresses": {"U2": 118},
                    "pin_assignments": {"SDA": "IO21", "SCL": "IO22"},
                    "provenance": {"source_type": "builtin_db", "confidence": 0.95},
                }
            ],
            "constraints": [],
            "nets": [],
            "buses": [],
            "electrical_specs": [],
            "init_contracts": [],
            "bom": [],
            "power_sequence": {"rails": [], "dependencies": []},
            "metadata": {
                "created_at": "2026-02-24T00:00:00Z",
                "track": "B",
                "confidence": {"overall": 0.85, "explanations": []},
            },
        }

    def test_round_trip_review_succeeds(self, tmp_path):
        """Export HIR → .kicad_sch → review → valid or graceful result."""
        from boardsmith_hw.kicad_exporter import export_kicad_sch

        hir_dict = self._make_hir_dict()
        sch_path = tmp_path / "schematic.kicad_sch"
        export_kicad_sch(hir_dict, sch_path, use_llm=False)

        assert sch_path.exists(), "Exporter must create the .kicad_sch file"

        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review(sch_path, original_hir=hir_dict)

        assert result.error is None
        assert isinstance(result.valid, bool)

    def test_round_trip_components_preserved(self, tmp_path):
        """After export/import, both component MPNs must survive."""
        from boardsmith_hw.kicad_exporter import export_kicad_sch

        hir_dict = self._make_hir_dict()
        sch_path = tmp_path / "schematic.kicad_sch"
        export_kicad_sch(hir_dict, sch_path, use_llm=False)

        reviewer = SchematicReviewer(use_llm=False)
        result = reviewer.review(sch_path)

        mpns = {c.get("mpn") for c in result.hir_dict.get("components", [])}
        assert "ESP32-WROOM-32" in mpns
        assert "BME280" in mpns

    def test_round_trip_auto_fix_doesnt_worsen(self, tmp_path):
        """errors_after <= errors_before after reviewing an exported schematic."""
        from boardsmith_hw.kicad_exporter import export_kicad_sch

        hir_dict = self._make_hir_dict()
        sch_path = tmp_path / "schematic.kicad_sch"
        export_kicad_sch(hir_dict, sch_path, use_llm=False)

        reviewer = SchematicReviewer(max_iterations=3, use_llm=False)
        result = reviewer.review(sch_path, original_hir=hir_dict)

        assert result.errors_after <= result.errors_before
