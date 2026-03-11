# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for ManufacturingExporter — PCB manufacturing file packaging.

Covers:
  - LCSC part number lookup
  - JLCPCB BOM CSV generation
  - Generic BOM CSV generation
  - CPL CSV generation
  - CPL parsing from .kicad_pcb S-expression
  - Gerber ZIP packaging
  - README generation
  - Full export() integration
"""
from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler"):
    _p = str(_REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from boardsmith_hw.manufacturing_exporter import (
    ManufacturingExporter,
    ManufacturingPackage,
    ComponentPlacement,
    _split_footprint_blocks,
    _extract_reference,
    _extract_at,
    _extract_layer,
    _LCSC_MAP,
)
from boardsmith_hw.pcb_pipeline import PcbResult


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_MINI_PCB = """\
(kicad_pcb (version 20221018) (generator "boardsmith-fw")
  (footprint "RF_Module:ESP32-WROOM-32" (layer "F.Cu")
    (at 30.00 30.00 0)
    (property "Reference" "U1" (at 0 -15 0)
      (effects (font (size 1 1))))
    (property "Value" "ESP32-WROOM-32" (at 0 15 0)
      (effects (font (size 1 1))))
  )
  (footprint "Package_LGA:LGA-8_3x3mm_P0.8mm" (layer "F.Cu")
    (at 130.00 30.00 45)
    (property "Reference" "U2" (at 0 -3 0)
      (effects (font (size 1 1))))
    (property "Value" "BME280" (at 0 3 0)
      (effects (font (size 1 1))))
  )
  (footprint "Package_TO_SOT_SMD:SOT-23" (layer "B.Cu")
    (at 70.00 60.00 180)
    (property "Reference" "Q1" (at 0 -2 0)
      (effects (font (size 1 1))))
    (property "Value" "2N7002" (at 0 2 0)
      (effects (font (size 1 1))))
  )
)
"""


def _make_pcb_result(tmp_path: Path, real: bool = False) -> PcbResult:
    """Build a minimal PcbResult with stub Gerbers and the _MINI_PCB layout."""
    pcb_path = tmp_path / "pcb.kicad_pcb"
    gerber_dir = tmp_path / "gerbers"
    gerber_dir.mkdir(exist_ok=True)

    pcb_path.write_text(_MINI_PCB, encoding="utf-8")

    for fname in ["pcb-F_Cu.gbr", "pcb-B_Cu.gbr", "pcb-Edge_Cuts.gbr", "pcb.drl"]:
        (gerber_dir / fname).write_text(
            "%FSLAX46Y46*%\n%MOMM*%\n; stub\nM02*\n", encoding="utf-8"
        )

    return PcbResult(
        pcb_path=pcb_path,
        gerber_dir=gerber_dir,
        routed=False,
        real_gerbers=real,
        footprints={
            "ESP32_WROOM_32": "RF_Module:ESP32-WROOM-32",
            "BME280_U2": "Package_LGA:LGA-8_3x3mm_P0.8mm",
        },
        router_method="stub",
    )


def _make_bom() -> list[dict]:
    return [
        {
            "line_id": "L001",
            "component_id": "ESP32_WROOM_32",
            "mpn": "ESP32-WROOM-32",
            "manufacturer": "Espressif",
            "description": "ESP32 Wi-Fi+BT Module",
            "qty": 1,
        },
        {
            "line_id": "L002",
            "component_id": "BME280_U2",
            "mpn": "BME280",
            "manufacturer": "Bosch Sensortec",
            "description": "BME280 Environmental Sensor",
            "qty": 1,
        },
    ]


def _make_hir(bom: list[dict] | None = None) -> dict:
    return {
        "version": "1.1.0",
        "components": [
            {
                "id": "ESP32_WROOM_32",
                "mpn": "ESP32-WROOM-32",
                "role": "mcu",
                "interface_types": ["I2C", "SPI"],
            },
            {
                "id": "BME280_U2",
                "mpn": "BME280",
                "role": "sensor",
                "interface_types": ["I2C"],
            },
        ],
        "bus_contracts": [],
        "bom": bom if bom is not None else _make_bom(),
    }


# ---------------------------------------------------------------------------
# LCSC lookup
# ---------------------------------------------------------------------------


class TestLcscLookup:
    def test_known_esp32_found(self):
        exp = ManufacturingExporter()
        assert exp._lookup_lcsc("ESP32-WROOM-32") != ""

    def test_known_bme280_found(self):
        exp = ManufacturingExporter()
        assert exp._lookup_lcsc("BME280") != ""

    def test_known_rp2040_found(self):
        exp = ManufacturingExporter()
        assert exp._lookup_lcsc("RP2040") != ""

    def test_unknown_mpn_returns_empty(self):
        exp = ManufacturingExporter()
        assert exp._lookup_lcsc("TOTALLY_UNKNOWN_PART_XYZ_999") == ""

    def test_empty_mpn_returns_empty(self):
        exp = ManufacturingExporter()
        assert exp._lookup_lcsc("") == ""

    def test_case_insensitive(self):
        exp = ManufacturingExporter()
        upper = exp._lookup_lcsc("BME280")
        lower = exp._lookup_lcsc("bme280")
        assert upper == lower != ""

    def test_lcsc_map_has_entries(self):
        assert len(_LCSC_MAP) >= 10

    def test_lcsc_values_start_with_c(self):
        for key, val in _LCSC_MAP.items():
            assert val.startswith("C"), f"Unexpected LCSC number for {key}: {val}"


# ---------------------------------------------------------------------------
# S-expression parsing helpers
# ---------------------------------------------------------------------------


class TestSExpressionHelpers:
    def test_split_finds_two_footprints(self):
        blocks = _split_footprint_blocks(_MINI_PCB)
        assert len(blocks) == 3

    def test_split_each_block_starts_with_footprint(self):
        for block in _split_footprint_blocks(_MINI_PCB):
            assert block.startswith("(footprint ")

    def test_split_empty_text(self):
        assert _split_footprint_blocks("(kicad_pcb)") == []

    def test_extract_reference_u1(self):
        block = '(footprint "X" (at 0 0)\n  (property "Reference" "U1" (at 0 0)))'
        assert _extract_reference(block) == "U1"

    def test_extract_reference_r3(self):
        block = '(property "Reference" "R3" (at 0 0))'
        assert _extract_reference(block) == "R3"

    def test_extract_reference_missing(self):
        block = "(footprint \"X\" (at 0 0))"
        assert _extract_reference(block) is None

    def test_extract_at_with_rotation(self):
        block = "(footprint \"X\" (layer \"F.Cu\") (at 10.5 20.3 90))"
        x, y, rot = _extract_at(block)
        assert x == pytest.approx(10.5)
        assert y == pytest.approx(20.3)
        assert rot == pytest.approx(90.0)

    def test_extract_at_without_rotation_defaults_zero(self):
        block = "(footprint \"X\" (layer \"F.Cu\") (at 5.0 7.0))"
        x, y, rot = _extract_at(block)
        assert x == pytest.approx(5.0)
        assert y == pytest.approx(7.0)
        assert rot == pytest.approx(0.0)

    def test_extract_at_missing_returns_none(self):
        block = "(footprint \"X\" (layer \"F.Cu\"))"
        x, y, rot = _extract_at(block)
        assert x is None
        assert y is None

    def test_extract_layer_front_copper(self):
        block = "(footprint \"X\" (layer \"F.Cu\") (at 0 0))"
        assert _extract_layer(block) == "F.Cu"

    def test_extract_layer_back_copper(self):
        block = "(footprint \"X\" (layer \"B.Cu\") (at 0 0))"
        assert _extract_layer(block) == "B.Cu"

    def test_extract_layer_missing_returns_none(self):
        block = "(footprint \"X\" (at 0 0))"
        assert _extract_layer(block) is None

    def test_split_negative_coordinates(self):
        text = '(footprint "X" (layer "F.Cu") (at -5.5 -10.0 270) (property "Reference" "R1" ()))'
        blocks = _split_footprint_blocks(text)
        assert len(blocks) == 1
        x, y, rot = _extract_at(blocks[0])
        assert x == pytest.approx(-5.5)
        assert y == pytest.approx(-10.0)
        assert rot == pytest.approx(270.0)


# ---------------------------------------------------------------------------
# CPL parsing
# ---------------------------------------------------------------------------


class TestCplParsing:
    def test_parse_returns_three_placements(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        placements = ManufacturingExporter().parse_cpl_from_pcb(result.pcb_path)
        assert len(placements) == 3

    def test_parse_references_correct(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        placements = ManufacturingExporter().parse_cpl_from_pcb(result.pcb_path)
        refs = {p.designator for p in placements}
        assert "U1" in refs
        assert "U2" in refs
        assert "Q1" in refs

    def test_parse_u1_position(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        placements = ManufacturingExporter().parse_cpl_from_pcb(result.pcb_path)
        u1 = next(p for p in placements if p.designator == "U1")
        assert u1.mid_x_mm == pytest.approx(30.0)
        assert u1.mid_y_mm == pytest.approx(30.0)
        assert u1.rotation == pytest.approx(0.0)

    def test_parse_u2_rotation(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        placements = ManufacturingExporter().parse_cpl_from_pcb(result.pcb_path)
        u2 = next(p for p in placements if p.designator == "U2")
        assert u2.rotation == pytest.approx(45.0)

    def test_parse_q1_rotation(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        placements = ManufacturingExporter().parse_cpl_from_pcb(result.pcb_path)
        q1 = next(p for p in placements if p.designator == "Q1")
        assert q1.rotation == pytest.approx(180.0)

    def test_parse_layer_front_copper(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        placements = ManufacturingExporter().parse_cpl_from_pcb(result.pcb_path)
        u1 = next(p for p in placements if p.designator == "U1")
        assert u1.layer == "Top"

    def test_parse_layer_back_copper(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        placements = ManufacturingExporter().parse_cpl_from_pcb(result.pcb_path)
        q1 = next(p for p in placements if p.designator == "Q1")
        assert q1.layer == "Bottom"

    def test_parse_empty_pcb(self, tmp_path):
        pcb = tmp_path / "empty.kicad_pcb"
        pcb.write_text("(kicad_pcb (version 20221018))", encoding="utf-8")
        placements = ManufacturingExporter().parse_cpl_from_pcb(pcb)
        assert placements == []

    def test_parse_returns_component_placement_objects(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        placements = ManufacturingExporter().parse_cpl_from_pcb(result.pcb_path)
        for p in placements:
            assert isinstance(p, ComponentPlacement)


# ---------------------------------------------------------------------------
# JLCPCB BOM CSV
# ---------------------------------------------------------------------------


class TestJlcpcbBom:
    def _parse(self, csv_text: str) -> list[dict]:
        return list(csv.DictReader(io.StringIO(csv_text)))

    def test_has_required_header_columns(self):
        exp = ManufacturingExporter()
        text = exp.build_jlcpcb_bom(_make_bom(), {})
        reader = csv.DictReader(io.StringIO(text))
        assert reader.fieldnames is not None
        for col in ("Comment", "Designator", "Footprint", "LCSC Part #"):
            assert col in reader.fieldnames

    def test_row_count_matches_bom(self):
        exp = ManufacturingExporter()
        rows = self._parse(exp.build_jlcpcb_bom(_make_bom(), {}))
        assert len(rows) == 2

    def test_lcsc_populated_for_esp32(self):
        exp = ManufacturingExporter()
        rows = self._parse(exp.build_jlcpcb_bom(_make_bom(), {}))
        esp32 = next(r for r in rows if "ESP32" in r["Comment"])
        assert esp32["LCSC Part #"] != ""

    def test_lcsc_populated_for_bme280(self):
        exp = ManufacturingExporter()
        rows = self._parse(exp.build_jlcpcb_bom(_make_bom(), {}))
        bme = next(r for r in rows if "BME280" in r["Comment"])
        assert bme["LCSC Part #"] != ""

    def test_footprint_no_library_prefix(self):
        exp = ManufacturingExporter()
        footprints = {"ESP32_WROOM_32": "RF_Module:ESP32-WROOM-32"}
        rows = self._parse(exp.build_jlcpcb_bom(_make_bom(), footprints))
        esp32 = next(r for r in rows if "ESP32" in r["Comment"])
        assert esp32["Footprint"] == "ESP32-WROOM-32"

    def test_footprint_without_prefix_unchanged(self):
        exp = ManufacturingExporter()
        footprints = {"BME280_U2": "LGA-8_3x3mm"}
        rows = self._parse(exp.build_jlcpcb_bom(_make_bom(), footprints))
        bme = next(r for r in rows if "BME280" in r["Comment"])
        assert bme["Footprint"] == "LGA-8_3x3mm"

    def test_empty_bom_produces_header_only(self):
        exp = ManufacturingExporter()
        text = exp.build_jlcpcb_bom([], {})
        rows = self._parse(text)
        assert rows == []

    def test_unknown_mpn_lcsc_is_empty(self):
        exp = ManufacturingExporter()
        bom = [{"component_id": "X", "mpn": "COMPLETELY_UNKNOWN_PART", "description": "X", "qty": 1}]
        rows = self._parse(exp.build_jlcpcb_bom(bom, {}))
        assert rows[0]["LCSC Part #"] == ""


# ---------------------------------------------------------------------------
# Generic BOM CSV
# ---------------------------------------------------------------------------


class TestGenericBom:
    def _parse(self, csv_text: str) -> list[dict]:
        return list(csv.DictReader(io.StringIO(csv_text)))

    def test_has_required_header_columns(self):
        exp = ManufacturingExporter()
        text = exp.build_generic_bom(_make_bom(), {})
        reader = csv.DictReader(io.StringIO(text))
        assert reader.fieldnames is not None
        for col in ("MPN", "Qty", "Reference", "Footprint"):
            assert col in reader.fieldnames

    def test_row_count_matches_bom(self):
        exp = ManufacturingExporter()
        rows = self._parse(exp.build_generic_bom(_make_bom(), {}))
        assert len(rows) == 2

    def test_no_lcsc_column(self):
        exp = ManufacturingExporter()
        text = exp.build_generic_bom(_make_bom(), {})
        assert "LCSC" not in text

    def test_mpn_field_populated(self):
        exp = ManufacturingExporter()
        rows = self._parse(exp.build_generic_bom(_make_bom(), {}))
        assert rows[0]["MPN"] == "ESP32-WROOM-32"

    def test_manufacturer_field_populated(self):
        exp = ManufacturingExporter()
        rows = self._parse(exp.build_generic_bom(_make_bom(), {}))
        assert rows[0]["Manufacturer"] == "Espressif"

    def test_qty_field_correct(self):
        exp = ManufacturingExporter()
        rows = self._parse(exp.build_generic_bom(_make_bom(), {}))
        for r in rows:
            assert r["Qty"] == "1"


# ---------------------------------------------------------------------------
# CPL CSV
# ---------------------------------------------------------------------------


class TestCplCsv:
    _PLACEMENTS = [
        ComponentPlacement("U1", 30.0, 30.0, "Top", 0.0),
        ComponentPlacement("U2", 130.0, 30.0, "Top", 45.0),
        ComponentPlacement("Q1", 70.0, 60.0, "Bottom", 180.0),
    ]

    def _parse(self, csv_text: str) -> list[dict]:
        return list(csv.DictReader(io.StringIO(csv_text)))

    def test_has_required_header_columns(self):
        exp = ManufacturingExporter()
        text = exp.build_cpl_csv(self._PLACEMENTS)
        reader = csv.DictReader(io.StringIO(text))
        assert reader.fieldnames is not None
        for col in ("Designator", "Mid X", "Mid Y", "Layer", "Rotation"):
            assert col in reader.fieldnames

    def test_row_count(self):
        rows = self._parse(ManufacturingExporter().build_cpl_csv(self._PLACEMENTS))
        assert len(rows) == 3

    def test_coordinates_include_mm_suffix(self):
        text = ManufacturingExporter().build_cpl_csv(self._PLACEMENTS)
        assert "mm" in text

    def test_designator_correct(self):
        rows = self._parse(ManufacturingExporter().build_cpl_csv(self._PLACEMENTS))
        assert rows[0]["Designator"] == "U1"

    def test_layer_top(self):
        rows = self._parse(ManufacturingExporter().build_cpl_csv(self._PLACEMENTS))
        assert rows[0]["Layer"] == "Top"

    def test_layer_bottom(self):
        rows = self._parse(ManufacturingExporter().build_cpl_csv(self._PLACEMENTS))
        assert rows[2]["Layer"] == "Bottom"

    def test_rotation_correct(self):
        rows = self._parse(ManufacturingExporter().build_cpl_csv(self._PLACEMENTS))
        assert rows[1]["Rotation"] == "45.00"

    def test_empty_placements_produces_header_only(self):
        rows = self._parse(ManufacturingExporter().build_cpl_csv([]))
        assert rows == []


# ---------------------------------------------------------------------------
# Gerber ZIP packaging
# ---------------------------------------------------------------------------


class TestGerberZip:
    def test_zip_is_valid(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        zip_bytes = ManufacturingExporter().package_gerbers_zip(
            result.gerber_dir, "pcb", "jlcpcb"
        )
        assert len(zip_bytes) > 0
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            assert len(zf.namelist()) > 0

    def test_zip_contains_gbr_files(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        zip_bytes = ManufacturingExporter().package_gerbers_zip(
            result.gerber_dir, "pcb", "jlcpcb"
        )
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
        assert any(n.endswith(".gbr") for n in names)

    def test_zip_contains_drl_file(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        zip_bytes = ManufacturingExporter().package_gerbers_zip(
            result.gerber_dir, "pcb", "jlcpcb"
        )
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
        assert any(n.endswith(".drl") for n in names)

    def test_zip_files_at_root_no_subdirectory(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        zip_bytes = ManufacturingExporter().package_gerbers_zip(
            result.gerber_dir, "pcb", "jlcpcb"
        )
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                assert "/" not in name, f"File should be at ZIP root: {name}"

    def test_zip_file_count_matches_gerber_dir(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        expected = len(list(result.gerber_dir.glob("*.gbr"))) + len(
            list(result.gerber_dir.glob("*.drl"))
        )
        zip_bytes = ManufacturingExporter().package_gerbers_zip(
            result.gerber_dir, "pcb", "jlcpcb"
        )
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            assert len(zf.namelist()) == expected

    def test_empty_gerber_dir_produces_valid_empty_zip(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        zip_bytes = ManufacturingExporter().package_gerbers_zip(empty_dir, "pcb", "jlcpcb")
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            assert zf.namelist() == []


# ---------------------------------------------------------------------------
# README generation
# ---------------------------------------------------------------------------


class TestReadme:
    def _make_pkg(self, tmp_path: Path, service: str = "jlcpcb") -> ManufacturingPackage:
        return ManufacturingPackage(
            service=service,
            out_dir=tmp_path,
            gerber_zip=tmp_path / f"gerbers_{service}.zip",
            bom_csv=tmp_path / f"bom_{service}.csv",
            cpl_csv=tmp_path / f"cpl_{service}.csv",
            readme=None,
        )

    def test_readme_contains_service_name_jlcpcb(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        exp = ManufacturingExporter()
        text = exp._make_readme("jlcpcb", self._make_pkg(tmp_path), result)
        assert "JLCPCB" in text

    def test_readme_contains_service_name_seeed(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        exp = ManufacturingExporter()
        text = exp._make_readme("seeed", self._make_pkg(tmp_path, "seeed"), result)
        assert "Seeed" in text or "seeed" in text.lower()

    def test_readme_has_stub_warning_when_not_real(self, tmp_path):
        result = _make_pcb_result(tmp_path, real=False)
        exp = ManufacturingExporter()
        text = exp._make_readme("jlcpcb", self._make_pkg(tmp_path), result)
        assert "WARNING" in text

    def test_readme_no_warning_when_real_gerbers(self, tmp_path):
        result = _make_pcb_result(tmp_path, real=True)
        exp = ManufacturingExporter()
        text = exp._make_readme("jlcpcb", self._make_pkg(tmp_path), result)
        assert "WARNING" not in text

    def test_readme_contains_jlcpcb_url(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        exp = ManufacturingExporter()
        text = exp._make_readme("jlcpcb", self._make_pkg(tmp_path), result)
        assert "jlcpcb.com" in text.lower()

    def test_readme_contains_seeed_url(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        exp = ManufacturingExporter()
        text = exp._make_readme("seeed", self._make_pkg(tmp_path, "seeed"), result)
        assert "seeedstudio.com" in text.lower()

    def test_readme_contains_file_names(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        exp = ManufacturingExporter()
        pkg = self._make_pkg(tmp_path)
        text = exp._make_readme("jlcpcb", pkg, result)
        assert "gerbers_jlcpcb.zip" in text

    def test_readme_is_markdown(self, tmp_path):
        result = _make_pcb_result(tmp_path)
        exp = ManufacturingExporter()
        text = exp._make_readme("jlcpcb", self._make_pkg(tmp_path), result)
        assert text.startswith("#")


# ---------------------------------------------------------------------------
# Full export() integration
# ---------------------------------------------------------------------------


class TestFullExport:
    def test_export_creates_output_directory(self, tmp_path):
        pcb_result = _make_pcb_result(tmp_path)
        mfg_dir = tmp_path / "manufacturing" / "jlcpcb"
        ManufacturingExporter().export("jlcpcb", pcb_result, _make_hir(), mfg_dir)
        assert mfg_dir.exists()

    def test_export_returns_manufacturing_package(self, tmp_path):
        pcb_result = _make_pcb_result(tmp_path)
        pkg = ManufacturingExporter().export(
            "jlcpcb", pcb_result, _make_hir(), tmp_path / "mfg"
        )
        assert isinstance(pkg, ManufacturingPackage)

    def test_export_jlcpcb_creates_gerber_zip(self, tmp_path):
        pcb_result = _make_pcb_result(tmp_path)
        pkg = ManufacturingExporter().export(
            "jlcpcb", pcb_result, _make_hir(), tmp_path / "mfg"
        )
        assert pkg.gerber_zip is not None
        assert pkg.gerber_zip.exists()

    def test_export_jlcpcb_creates_bom_csv(self, tmp_path):
        pcb_result = _make_pcb_result(tmp_path)
        pkg = ManufacturingExporter().export(
            "jlcpcb", pcb_result, _make_hir(), tmp_path / "mfg"
        )
        assert pkg.bom_csv is not None
        assert pkg.bom_csv.exists()

    def test_export_jlcpcb_creates_cpl_csv(self, tmp_path):
        pcb_result = _make_pcb_result(tmp_path)
        pkg = ManufacturingExporter().export(
            "jlcpcb", pcb_result, _make_hir(), tmp_path / "mfg"
        )
        assert pkg.cpl_csv is not None
        assert pkg.cpl_csv.exists()

    def test_export_jlcpcb_creates_readme(self, tmp_path):
        pcb_result = _make_pcb_result(tmp_path)
        pkg = ManufacturingExporter().export(
            "jlcpcb", pcb_result, _make_hir(), tmp_path / "mfg"
        )
        assert pkg.readme is not None
        assert pkg.readme.exists()

    def test_export_seeed_uses_generic_bom_format(self, tmp_path):
        pcb_result = _make_pcb_result(tmp_path)
        pkg = ManufacturingExporter().export(
            "seeed", pcb_result, _make_hir(), tmp_path / "mfg_seeed"
        )
        assert pkg.bom_csv is not None
        content = pkg.bom_csv.read_text()
        assert "LCSC" not in content

    def test_export_generic_produces_all_files(self, tmp_path):
        pcb_result = _make_pcb_result(tmp_path)
        pkg = ManufacturingExporter().export(
            "generic", pcb_result, _make_hir(), tmp_path / "mfg_generic"
        )
        assert pkg.gerber_zip is not None
        assert pkg.bom_csv is not None
        assert pkg.cpl_csv is not None
        assert pkg.readme is not None

    def test_export_empty_bom_skips_bom_file(self, tmp_path):
        pcb_result = _make_pcb_result(tmp_path)
        hir = _make_hir(bom=[])
        pkg = ManufacturingExporter().export(
            "jlcpcb", pcb_result, hir, tmp_path / "mfg"
        )
        assert pkg.bom_csv is None
        assert any("BOM" in w for w in pkg.warnings)

    def test_export_component_count(self, tmp_path):
        pcb_result = _make_pcb_result(tmp_path)
        pkg = ManufacturingExporter().export(
            "jlcpcb", pcb_result, _make_hir(), tmp_path / "mfg"
        )
        assert pkg.component_count == 2

    def test_export_placements_found(self, tmp_path):
        pcb_result = _make_pcb_result(tmp_path)
        pkg = ManufacturingExporter().export(
            "jlcpcb", pcb_result, _make_hir(), tmp_path / "mfg"
        )
        assert pkg.placements_found == 3

    def test_export_warns_on_stub_gerbers(self, tmp_path):
        pcb_result = _make_pcb_result(tmp_path, real=False)
        pkg = ManufacturingExporter().export(
            "jlcpcb", pcb_result, _make_hir(), tmp_path / "mfg"
        )
        assert any("stub" in w.lower() or "placeholder" in w.lower() for w in pkg.warnings)

    def test_export_no_gerber_dir_adds_warning(self, tmp_path):
        pcb_result = _make_pcb_result(tmp_path)
        pcb_result = PcbResult(
            pcb_path=pcb_result.pcb_path,
            gerber_dir=None,
            routed=False,
            real_gerbers=False,
            footprints={},
            router_method="stub",
        )
        pkg = ManufacturingExporter().export(
            "jlcpcb", pcb_result, _make_hir(), tmp_path / "mfg"
        )
        assert pkg.gerber_zip is None
        assert len(pkg.warnings) > 0

    def test_export_no_pcb_path_skips_cpl(self, tmp_path):
        pcb_result = _make_pcb_result(tmp_path)
        pcb_result = PcbResult(
            pcb_path=None,
            gerber_dir=pcb_result.gerber_dir,
            routed=False,
            real_gerbers=False,
            footprints={},
            router_method="stub",
        )
        pkg = ManufacturingExporter().export(
            "jlcpcb", pcb_result, _make_hir(), tmp_path / "mfg"
        )
        assert pkg.cpl_csv is None

    def test_export_jlcpcb_zip_name_includes_service(self, tmp_path):
        pcb_result = _make_pcb_result(tmp_path)
        pkg = ManufacturingExporter().export(
            "jlcpcb", pcb_result, _make_hir(), tmp_path / "mfg"
        )
        assert "jlcpcb" in pkg.gerber_zip.name

    def test_export_pcbway_service_supported(self, tmp_path):
        pcb_result = _make_pcb_result(tmp_path)
        pkg = ManufacturingExporter().export(
            "pcbway", pcb_result, _make_hir(), tmp_path / "mfg_pcbway"
        )
        assert isinstance(pkg, ManufacturingPackage)
        assert pkg.readme is not None


# ---------------------------------------------------------------------------
# Phase 25.1 — JLCPCB BOM Grouping
# ---------------------------------------------------------------------------


class TestJLCPCBBomGrouping:
    """build_jlcpcb_bom() must group identical MPN+footprint into one row."""

    def test_single_component_single_row(self):
        exporter = ManufacturingExporter()
        entries = [
            {"component_id": "R1", "mpn": "RC0402JR-07100RL", "qty": 1,
             "description": "100R 0402"},
        ]
        footprints = {"R1": "Resistor_SMD:R_0402_1005Metric"}
        bom = exporter.build_jlcpcb_bom(entries, footprints)
        rows = [r for r in csv.reader(io.StringIO(bom)) if r]
        data_rows = rows[1:]  # skip header
        assert len(data_rows) == 1

    def test_two_different_mpns_two_rows(self):
        exporter = ManufacturingExporter()
        entries = [
            {"component_id": "R1", "mpn": "RC0402JR-07100RL", "qty": 1,
             "description": "100R 0402"},
            {"component_id": "C1", "mpn": "CL05A104KA5NNNC", "qty": 1,
             "description": "100nF 0402"},
        ]
        footprints = {
            "R1": "Resistor_SMD:R_0402_1005Metric",
            "C1": "Capacitor_SMD:C_0402_1005Metric",
        }
        bom = exporter.build_jlcpcb_bom(entries, footprints)
        rows = [r for r in csv.reader(io.StringIO(bom)) if r]
        assert len(rows) - 1 == 2  # 2 data rows

    def test_same_mpn_grouped_into_one_row(self):
        exporter = ManufacturingExporter()
        entries = [
            {"component_id": "R1", "mpn": "RC0402JR-07100RL", "qty": 1,
             "description": "100R 0402"},
            {"component_id": "R2", "mpn": "RC0402JR-07100RL", "qty": 1,
             "description": "100R 0402"},
            {"component_id": "R3", "mpn": "RC0402JR-07100RL", "qty": 1,
             "description": "100R 0402"},
        ]
        fp = "Resistor_SMD:R_0402_1005Metric"
        footprints = {"R1": fp, "R2": fp, "R3": fp}
        bom = exporter.build_jlcpcb_bom(entries, footprints)
        rows = [r for r in csv.reader(io.StringIO(bom)) if r]
        data_rows = rows[1:]
        assert len(data_rows) == 1
        # Designator must contain all 3
        designator_col = data_rows[0][1]
        for ref in ("R1", "R2", "R3"):
            assert ref in designator_col

    def test_header_row_present(self):
        exporter = ManufacturingExporter()
        entries = [{"component_id": "R1", "mpn": "RC0402", "qty": 1, "description": "R"}]
        bom = exporter.build_jlcpcb_bom(entries, {"R1": "Resistor_SMD:R_0402"})
        rows = [r for r in csv.reader(io.StringIO(bom)) if r]
        header = rows[0]
        assert "Comment" in header
        assert "Designator" in header
        assert "Footprint" in header
        assert "LCSC Part #" in header

    def test_lcsc_number_in_bom(self):
        exporter = ManufacturingExporter()
        entries = [{"component_id": "U2", "mpn": "BME280", "qty": 1,
                    "description": "BME280"}]
        bom = exporter.build_jlcpcb_bom(entries, {"U2": "LGA-8:LGA8"})
        rows = [r for r in csv.reader(io.StringIO(bom)) if r]
        data_row = rows[1]
        lcsc_col = data_row[3]
        assert lcsc_col == "C92489"  # BME280 known LCSC number

    def test_footprint_stripped_to_short_name(self):
        """Only the part after ':' should appear in the Footprint column."""
        exporter = ManufacturingExporter()
        entries = [{"component_id": "R1", "mpn": "RC0402", "qty": 1, "description": "R"}]
        bom = exporter.build_jlcpcb_bom(entries, {"R1": "Resistor_SMD:R_0402_1005Metric"})
        rows = [r for r in csv.reader(io.StringIO(bom)) if r]
        fp_col = rows[1][2]
        assert fp_col == "R_0402_1005Metric"
        assert "Resistor_SMD" not in fp_col


# ---------------------------------------------------------------------------
# Phase 25.2 — LCSC Coverage Tracking
# ---------------------------------------------------------------------------


class TestLCSCCoverage:
    """compute_lcsc_coverage() must calculate % of MPNs with LCSC numbers."""

    def test_all_known_mpns_full_coverage(self):
        exporter = ManufacturingExporter()
        entries = [
            {"component_id": "U1", "mpn": "ESP32-WROOM-32", "qty": 1},
            {"component_id": "U2", "mpn": "BME280", "qty": 1},
        ]
        pct, missing = exporter.compute_lcsc_coverage(entries)
        assert pct == pytest.approx(100.0)
        assert missing == []

    def test_unknown_mpn_reduces_coverage(self):
        exporter = ManufacturingExporter()
        entries = [
            {"component_id": "U1", "mpn": "BME280", "qty": 1},
            {"component_id": "U2", "mpn": "UNKNOWN_PART_XYZ", "qty": 1},
        ]
        pct, missing = exporter.compute_lcsc_coverage(entries)
        assert pct == pytest.approx(50.0)
        assert "UNKNOWN_PART_XYZ" in missing

    def test_all_unknown_zero_coverage(self):
        exporter = ManufacturingExporter()
        entries = [
            {"component_id": "X1", "mpn": "FAKE_PART_A", "qty": 1},
            {"component_id": "X2", "mpn": "FAKE_PART_B", "qty": 1},
        ]
        pct, missing = exporter.compute_lcsc_coverage(entries)
        assert pct == pytest.approx(0.0)
        assert len(missing) == 2

    def test_empty_entries_returns_100(self):
        exporter = ManufacturingExporter()
        pct, missing = exporter.compute_lcsc_coverage([])
        assert pct == pytest.approx(100.0)
        assert missing == []

    def test_duplicate_mpns_counted_once(self):
        """3 identical BME280 = 1 unique MPN, should not inflate counts."""
        exporter = ManufacturingExporter()
        entries = [
            {"component_id": "U1", "mpn": "BME280", "qty": 1},
            {"component_id": "U2", "mpn": "BME280", "qty": 1},
            {"component_id": "U3", "mpn": "FAKE_XYZ", "qty": 1},
        ]
        pct, missing = exporter.compute_lcsc_coverage(entries)
        # 1/2 unique MPNs have LCSC = 50%
        assert pct == pytest.approx(50.0)

    def test_coverage_field_on_package(self, tmp_path):
        pcb_result = _make_pcb_result(tmp_path)
        pkg = ManufacturingExporter().export(
            "jlcpcb", pcb_result, _make_hir(), tmp_path / "mfg25"
        )
        # Both ESP32-WROOM-32 and BME280 have LCSC numbers
        assert pkg.lcsc_coverage_pct == pytest.approx(100.0)
        assert pkg.missing_lcsc == []

    def test_low_coverage_adds_warning(self, tmp_path):
        pcb_result = _make_pcb_result(tmp_path)
        hir = _make_hir(bom=[
            {"line_id": "L1", "component_id": "X1", "mpn": "FAKE_A",
             "manufacturer": "?", "description": "?", "qty": 1},
            {"line_id": "L2", "component_id": "X2", "mpn": "FAKE_B",
             "manufacturer": "?", "description": "?", "qty": 1},
            {"line_id": "L3", "component_id": "X3", "mpn": "FAKE_C",
             "manufacturer": "?", "description": "?", "qty": 1},
        ])
        pkg = ManufacturingExporter().export(
            "jlcpcb", pcb_result, hir, tmp_path / "mfg25low"
        )
        assert pkg.lcsc_coverage_pct == pytest.approx(0.0)
        # Warning should mention low coverage
        warning_text = " ".join(pkg.warnings)
        assert "LCSC" in warning_text or "lcsc" in warning_text.lower()


# ---------------------------------------------------------------------------
# Phase 25.3 — Expanded LCSC Map
# ---------------------------------------------------------------------------


class TestExpandedLCSCMap:
    """Phase 25.3: Verify key new MPNs are in _LCSC_MAP."""

    def _has_lcsc(self, mpn: str) -> bool:
        return mpn in _LCSC_MAP and bool(_LCSC_MAP[mpn])

    # Level shifters (Phase 22.8)
    def test_bss138_in_map(self):
        assert self._has_lcsc("BSS138")

    def test_txs0102_in_map(self):
        assert self._has_lcsc("TXS0102")

    def test_txs0104_in_map(self):
        assert self._has_lcsc("TXS0104")

    # Buck converters
    def test_tps563200_in_map(self):
        assert self._has_lcsc("TPS563200")

    def test_mp1584en_in_map(self):
        assert self._has_lcsc("MP1584EN")

    def test_lm2596s_5v_in_map(self):
        assert self._has_lcsc("LM2596S-5.0")

    # Ferrite beads
    def test_blm18pg121sn1d_in_map(self):
        assert self._has_lcsc("BLM18PG121SN1D")

    # USB components
    def test_ch340g_in_map(self):
        assert self._has_lcsc("CH340G")

    def test_usblc6_in_map(self):
        assert self._has_lcsc("USBLC6-2SC6")

    # Common transistors
    def test_2n7002_in_map(self):
        assert self._has_lcsc("2N7002")

    def test_mmbt3904_in_map(self):
        assert self._has_lcsc("MMBT3904")

    # Map size check (should be ≥180 entries after Phase 25 audit)
    def test_map_has_180_plus_entries(self):
        assert len(_LCSC_MAP) >= 180
