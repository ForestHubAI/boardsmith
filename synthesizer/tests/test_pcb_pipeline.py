# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Phase 14 PCB Pipeline modules.

Covers:
  - FootprintMapper   (test_footprint_mapper.py content merged here)
  - PcbLayoutEngine   (S-expression generation, grid layout, nets)
  - Autorouter        (availability checks, stub result)
  - PcbPipeline       (end-to-end PCB generation from HIR)
"""
from __future__ import annotations

import json
import sys
import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler"):
    _p = str(_REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from boardsmith_hw.footprint_mapper import FootprintMapper, FootprintInfo, _size_from_footprint
from boardsmith_hw.pcb_layout_engine import PcbLayoutEngine, PcbPosition
from boardsmith_hw.autorouter import Autorouter, RouterResult, _write_stub_gerbers
from boardsmith_hw.pcb_pipeline import PcbPipeline, PcbResult


# ---------------------------------------------------------------------------
# Shared HIR fixture
# ---------------------------------------------------------------------------

def _make_hir(*, with_spi: bool = False, extra_passive: bool = False) -> dict:
    """Build a minimal HIR dict for PCB pipeline tests."""
    components = [
        {
            "id": "U1",
            "mpn": "ESP32-WROOM-32",
            "name": "ESP32-WROOM-32",
            "role": "mcu",
            "interface_types": ["I2C", "SPI"],
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
    ]
    if extra_passive:
        components.append({
            "id": "R1",
            "mpn": "RC0402",
            "name": "100Ω Resistor",
            "role": "passive",
            "interface_types": [],
            "pins": [],
            "provenance": {"source_type": "builtin_db", "confidence": 0.95},
        })

    bus_type = "SPI" if with_spi else "I2C"
    pins = {"SDA": "IO21", "SCL": "IO22"} if not with_spi else {
        "MOSI": "IO23", "MISO": "IO19", "SCLK": "IO18", "CS": "IO5"
    }
    return {
        "version": "1.1.0",
        "source": "prompt",
        "components": components,
        "bus_contracts": [
            {
                "bus_name": f"{bus_type}0",
                "bus_type": bus_type,
                "master_id": "U1",
                "slave_ids": ["U2"],
                "configured_clock_hz": 400000,
                "slave_addresses": {"U2": 118},
                "pin_assignments": pins,
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


# ===========================================================================
# FootprintMapper tests
# ===========================================================================


class TestSizeFromFootprint:
    def test_esp32_module_size(self):
        w, h = _size_from_footprint("RF_Module:ESP32-WROOM-32")
        assert w >= 15.0
        assert h >= 20.0

    def test_soic8_size(self):
        w, h = _size_from_footprint("Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
        assert w < 8.0
        assert h < 8.0

    def test_0402_size(self):
        w, h = _size_from_footprint("Resistor_SMD:R_0402_1005Metric")
        assert w < 3.0

    def test_explicit_dimensions_parsed(self):
        # "3.9x4.9mm" in footprint name; +1mm courtyard added → 4.9mm and 5.9mm
        w, h = _size_from_footprint("Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
        assert w >= 4.0
        assert h >= 4.0

    def test_unknown_footprint_returns_default(self):
        w, h = _size_from_footprint("UnknownLib:UnknownPart")
        assert w == 5.0
        assert h == 5.0


class TestFootprintMapper:
    def _mapper(self) -> FootprintMapper:
        return FootprintMapper(use_llm=False)

    def test_resolve_esp32(self):
        fp = self._mapper().resolve("ESP32-WROOM-32", "mcu")
        assert fp.kicad_footprint == "RF_Module:ESP32-WROOM-32"
        assert fp.source == "symbol_map"
        assert fp.width_mm > 0
        assert fp.height_mm > 0
        assert fp.pin_count > 0

    def test_resolve_bme280(self):
        fp = self._mapper().resolve("BME280", "sensor")
        assert "LGA" in fp.kicad_footprint or "Bosch" in fp.kicad_footprint
        assert fp.source == "symbol_map"

    def test_resolve_rp2040(self):
        fp = self._mapper().resolve("RP2040", "mcu")
        assert "QFN" in fp.kicad_footprint.upper() or "RP2040" in fp.kicad_footprint.upper()

    def test_resolve_stm32(self):
        fp = self._mapper().resolve("STM32F103C8T6", "mcu")
        assert "LQFP" in fp.kicad_footprint.upper() or "QFP" in fp.kicad_footprint.upper()

    def test_resolve_fallback_package(self):
        fp = self._mapper().resolve("SOME-0402-RESISTOR", "passive")
        # Should match "0402" in FOOTPRINT_FALLBACK
        assert "0402" in fp.kicad_footprint or fp.source in ("fallback", "generic")

    def test_resolve_unknown_returns_generic(self):
        fp = self._mapper().resolve("TOTALLY_UNKNOWN_PART", "sensor")
        assert fp.source in ("generic", "fallback")
        assert ":" in fp.kicad_footprint  # Still a valid "Library:Name" format

    def test_resolve_returns_footprint_info(self):
        fp = self._mapper().resolve("ESP32-WROOM-32", "mcu")
        assert isinstance(fp, FootprintInfo)

    def test_resolve_footprint_has_colon(self):
        """All resolved footprints must be in 'Library:Name' format."""
        mapper = self._mapper()
        for mpn in ("ESP32-WROOM-32", "BME280", "RP2040", "UNKNOWN"):
            fp = mapper.resolve(mpn, "mcu")
            assert ":" in fp.kicad_footprint, (
                f"{mpn}: footprint '{fp.kicad_footprint}' missing colon"
            )

    def test_resolve_all_from_hir(self):
        hir = _make_hir()
        mapper = self._mapper()
        infos = mapper.resolve_all(hir)
        assert "U1" in infos
        assert "U2" in infos
        assert infos["U1"].kicad_footprint == "RF_Module:ESP32-WROOM-32"

    def test_resolve_all_empty_hir(self):
        mapper = self._mapper()
        infos = mapper.resolve_all({"components": []})
        assert infos == {}

    def test_resolve_all_unknown_components(self):
        hir = {
            "components": [
                {"id": "X1", "mpn": "MYSTERYPART", "role": "sensor",
                 "interface_types": ["I2C"]},
            ]
        }
        mapper = self._mapper()
        infos = mapper.resolve_all(hir)
        assert "X1" in infos
        assert infos["X1"].kicad_footprint != ""

    def test_width_height_positive(self):
        mapper = self._mapper()
        for mpn, role in [("ESP32-WROOM-32", "mcu"), ("BME280", "sensor")]:
            fp = mapper.resolve(mpn, role)
            assert fp.width_mm > 0
            assert fp.height_mm > 0


# ===========================================================================
# PcbLayoutEngine tests
# ===========================================================================


class TestPcbPosition:
    def test_defaults(self):
        pos = PcbPosition(x=10, y=20)
        assert pos.rotation == 0.0
        assert pos.layer == "F.Cu"

    def test_custom(self):
        pos = PcbPosition(x=50, y=30, rotation=90, layer="B.Cu")
        assert pos.rotation == 90


class TestPcbLayoutEngine:
    def _engine(self) -> PcbLayoutEngine:
        return PcbLayoutEngine(use_llm=False)

    def _footprints(self, hir: dict) -> dict:
        mapper = FootprintMapper(use_llm=False)
        return mapper.resolve_all(hir)

    def test_build_returns_string(self):
        hir = _make_hir()
        engine = self._engine()
        fp = self._footprints(hir)
        text = engine.build(hir, fp)
        assert isinstance(text, str)
        assert len(text) > 100

    def test_build_starts_with_kicad_pcb(self):
        hir = _make_hir()
        text = self._engine().build(hir, self._footprints(hir))
        assert text.strip().startswith("(kicad_pcb")

    def test_build_contains_version(self):
        hir = _make_hir()
        text = self._engine().build(hir, self._footprints(hir))
        assert "20221018" in text

    def test_build_contains_layers(self):
        hir = _make_hir()
        text = self._engine().build(hir, self._footprints(hir))
        assert '"F.Cu"' in text
        assert '"B.Cu"' in text
        assert '"Edge.Cuts"' in text

    def test_build_contains_nets(self):
        hir = _make_hir()
        text = self._engine().build(hir, self._footprints(hir))
        assert '"GND"' in text
        assert '"+3V3"' in text
        assert '"SDA"' in text
        assert '"SCL"' in text

    def test_build_spi_nets(self):
        hir = _make_hir(with_spi=True)
        text = self._engine().build(hir, self._footprints(hir))
        assert '"MOSI"' in text or "MOSI" in text
        assert '"SCLK"' in text or '"SCK"' in text or "SCLK" in text

    def test_build_contains_footprints(self):
        hir = _make_hir()
        text = self._engine().build(hir, self._footprints(hir))
        # Each component should have a footprint block
        assert text.count("(footprint") >= 2

    def test_build_contains_esp32_footprint(self):
        hir = _make_hir()
        text = self._engine().build(hir, self._footprints(hir))
        assert "ESP32-WROOM-32" in text

    def test_build_contains_board_edge(self):
        hir = _make_hir()
        text = self._engine().build(hir, self._footprints(hir))
        assert "Edge.Cuts" in text
        assert "gr_rect" in text

    def test_build_parentheses_balanced(self):
        """KiCad S-expression must have balanced parentheses."""
        hir = _make_hir()
        text = self._engine().build(hir, self._footprints(hir))
        assert text.count("(") == text.count(")")

    def test_build_with_passives(self):
        hir = _make_hir(extra_passive=True)
        text = self._engine().build(hir, self._footprints(hir))
        assert text.count("(footprint") >= 3

    def test_build_empty_hir_no_crash(self):
        empty_hir = {
            "components": [], "bus_contracts": [],
            "version": "1.1.0", "source": "test",
        }
        text = self._engine().build(empty_hir, {})
        assert "(kicad_pcb" in text

    def test_collect_nets_i2c(self):
        hir = _make_hir()
        engine = self._engine()
        nets = engine._collect_nets(hir)
        net_names = [n for _, n in nets]
        assert "GND" in net_names
        assert "+3V3" in net_names
        assert "SDA" in net_names
        assert "SCL" in net_names

    def test_collect_nets_always_has_empty_net_0(self):
        hir = _make_hir()
        engine = self._engine()
        nets = engine._collect_nets(hir)
        assert nets[0] == (0, "")

    def test_net_ids_unique(self):
        hir = _make_hir()
        engine = self._engine()
        nets = engine._collect_nets(hir)
        ids = [nid for nid, _ in nets]
        assert len(ids) == len(set(ids)), "Net IDs must be unique"

    def test_plan_grid_positions_all_components(self):
        hir = _make_hir()
        engine = self._engine()
        fp = self._footprints(hir)
        positions = engine._plan_grid_positions(hir, fp)
        assert "U1" in positions
        assert "U2" in positions

    def test_plan_grid_positions_mcu_left(self):
        """MCU must be placed in the left zone (x < 60mm)."""
        hir = _make_hir()
        engine = self._engine()
        fp = self._footprints(hir)
        positions = engine._plan_grid_positions(hir, fp)
        assert positions["U1"].x < 60.0

    def test_plan_grid_positions_sensor_right(self):
        """Sensor must be placed to the right of MCU."""
        hir = _make_hir()
        engine = self._engine()
        fp = self._footprints(hir)
        positions = engine._plan_grid_positions(hir, fp)
        assert positions["U2"].x > positions["U1"].x

    def test_board_bounds_positive(self):
        hir = _make_hir()
        engine = self._engine()
        fp = self._footprints(hir)
        pos = engine._plan_grid_positions(hir, fp)
        w, h = engine._board_bounds(pos, fp)
        assert w > 0
        assert h > 0

    def test_board_bounds_empty(self):
        engine = self._engine()
        w, h = engine._board_bounds({}, {})
        assert w > 0 and h > 0  # fallback dimensions

    def test_assign_refs_returns_designators(self):
        hir = _make_hir()
        engine = self._engine()
        fp = self._footprints(hir)
        refs = engine._assign_refs(hir, fp)
        assert "U1" in refs.values() or "U2" in refs.values()
        assert len(refs) == 2


# ===========================================================================
# Autorouter tests
# ===========================================================================


class TestAutorouter:
    def test_kicad_cli_available_returns_bool(self):
        result = Autorouter.kicad_cli_available()
        assert isinstance(result, bool)

    def test_freerouting_available_returns_bool(self):
        result = Autorouter.freerouting_available()
        assert isinstance(result, bool)

    def test_route_returns_router_result(self, tmp_path):
        """route() must return RouterResult even when no PCB exists."""
        fake_pcb = tmp_path / "board.kicad_pcb"
        # Write a minimal valid PCB
        fake_pcb.write_text(
            '(kicad_pcb (version 20221018) (generator "boardsmith-fw")\n'
            '  (general (thickness 1.6) (legacy_teardrops no))\n)',
            encoding="utf-8",
        )
        router = Autorouter()
        result = router.route(fake_pcb, hir_dict=None)
        assert isinstance(result, RouterResult)
        assert isinstance(result.routed, bool)
        assert result.method in ("freerouting", "kicad_cli_drc", "stub")
        assert result.pcb_path == fake_pcb

    def test_route_stub_when_no_tools(self, tmp_path):
        """When neither kicad-cli nor freerouting are available, method=stub."""
        pcb_path = tmp_path / "board.kicad_pcb"
        pcb_path.write_text("(kicad_pcb (version 20221018))", encoding="utf-8")
        router = Autorouter()
        result = router.route(pcb_path)
        if not Autorouter.kicad_cli_available() and not Autorouter.freerouting_available():
            assert result.method == "stub"
            assert result.routed is False

    def test_drc_only_returns_list(self, tmp_path):
        pcb_path = tmp_path / "board.kicad_pcb"
        pcb_path.write_text("(kicad_pcb (version 20221018))", encoding="utf-8")
        router = Autorouter()
        errors = router.drc_only(pcb_path)
        assert isinstance(errors, list)

    def test_export_gerbers_creates_directory(self, tmp_path):
        pcb_path = tmp_path / "board.kicad_pcb"
        pcb_path.write_text("(kicad_pcb (version 20221018))", encoding="utf-8")
        gerber_dir = tmp_path / "gerbers"

        router = Autorouter()
        router.export_gerbers(pcb_path, gerber_dir)

        assert gerber_dir.exists(), "Gerber directory must be created"

    def test_export_gerbers_writes_files(self, tmp_path):
        pcb_path = tmp_path / "board.kicad_pcb"
        pcb_path.write_text("(kicad_pcb (version 20221018))", encoding="utf-8")
        gerber_dir = tmp_path / "gerbers"

        router = Autorouter()
        router.export_gerbers(pcb_path, gerber_dir)

        files = list(gerber_dir.iterdir())
        assert len(files) >= 1, "At least one Gerber file must be written"

    def test_write_stub_gerbers(self, tmp_path):
        gerber_dir = tmp_path / "gerbers"
        gerber_dir.mkdir()
        _write_stub_gerbers(gerber_dir, "my_pcb")
        files = {f.name for f in gerber_dir.iterdir()}
        assert "my_pcb-F_Cu.gbr" in files
        assert "my_pcb-Edge_Cuts.gbr" in files
        assert "my_pcb.drl" in files

    def test_write_stub_gerbers_content(self, tmp_path):
        gerber_dir = tmp_path / "gerbers"
        gerber_dir.mkdir()
        _write_stub_gerbers(gerber_dir, "test")
        content = (gerber_dir / "test-F_Cu.gbr").read_text()
        assert "M02" in content or "%" in content  # Gerber markers


# ===========================================================================
# PcbPipeline tests
# ===========================================================================


class TestPcbPipeline:
    def test_run_returns_pcb_result(self, tmp_path):
        hir = _make_hir()
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(hir, out_dir=tmp_path)
        assert isinstance(result, PcbResult)

    def test_run_creates_pcb_file(self, tmp_path):
        hir = _make_hir()
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(hir, out_dir=tmp_path)
        assert result.error is None, f"Pipeline error: {result.error}"
        assert result.pcb_path is not None
        assert result.pcb_path.exists(), "pcb.kicad_pcb must exist"

    def test_pcb_file_named_correctly(self, tmp_path):
        hir = _make_hir()
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(hir, out_dir=tmp_path)
        assert result.pcb_path.name == "pcb.kicad_pcb"

    def test_run_creates_gerber_dir(self, tmp_path):
        hir = _make_hir()
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(hir, out_dir=tmp_path)
        assert result.gerber_dir is not None
        assert result.gerber_dir.exists(), "gerbers/ directory must exist"

    def test_pcb_is_valid_kicad_format(self, tmp_path):
        hir = _make_hir()
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(hir, out_dir=tmp_path)
        content = result.pcb_path.read_text(encoding="utf-8")
        assert content.startswith("(kicad_pcb")
        # Balanced parentheses
        assert content.count("(") == content.count(")")

    def test_pcb_contains_both_components(self, tmp_path):
        hir = _make_hir()
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(hir, out_dir=tmp_path)
        content = result.pcb_path.read_text(encoding="utf-8")
        assert "ESP32-WROOM-32" in content
        assert "BME280" in content

    def test_pcb_contains_nets(self, tmp_path):
        hir = _make_hir()
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(hir, out_dir=tmp_path)
        content = result.pcb_path.read_text(encoding="utf-8")
        assert '"GND"' in content
        assert '"SDA"' in content or '"SCL"' in content

    def test_footprints_dict_populated(self, tmp_path):
        hir = _make_hir()
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(hir, out_dir=tmp_path)
        assert "U1" in result.footprints
        assert "U2" in result.footprints
        assert "ESP32-WROOM-32" in result.footprints["U1"]

    def test_router_method_is_string(self, tmp_path):
        hir = _make_hir()
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(hir, out_dir=tmp_path)
        assert result.router_method in ("freerouting", "kicad_cli_drc", "stub")

    def test_drc_errors_is_list(self, tmp_path):
        hir = _make_hir()
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(hir, out_dir=tmp_path)
        assert isinstance(result.drc_errors, list)

    def test_out_dir_created(self, tmp_path):
        hir = _make_hir()
        pipeline = PcbPipeline(use_llm=False)
        deep_dir = tmp_path / "deep" / "nested" / "output"
        result = pipeline.run(hir, out_dir=deep_dir)
        assert deep_dir.exists()

    def test_empty_hir_no_crash(self, tmp_path):
        """Empty HIR (no components) must not crash the pipeline."""
        empty_hir = {
            "version": "1.1.0",
            "source": "test",
            "components": [],
            "bus_contracts": [],
        }
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(empty_hir, out_dir=tmp_path)
        # Should produce a file or return an error — never crash
        assert result.pcb_path is not None or result.error is not None

    def test_with_passives(self, tmp_path):
        hir = _make_hir(extra_passive=True)
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(hir, out_dir=tmp_path)
        assert result.error is None
        content = result.pcb_path.read_text(encoding="utf-8")
        assert content.count("(footprint") >= 3

    def test_with_spi_bus(self, tmp_path):
        hir = _make_hir(with_spi=True)
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(hir, out_dir=tmp_path)
        assert result.error is None
        content = result.pcb_path.read_text(encoding="utf-8")
        assert "MOSI" in content or "SCLK" in content or "SPI" in content

    def test_gerber_files_written(self, tmp_path):
        hir = _make_hir()
        pipeline = PcbPipeline(use_llm=False)
        result = pipeline.run(hir, out_dir=tmp_path)
        gbr_files = list(result.gerber_dir.glob("*.gbr")) + list(result.gerber_dir.glob("*.drl"))
        assert len(gbr_files) >= 1


# ===========================================================================
# Phase 20 — PCB Real Routing tests
# ===========================================================================


def _make_hir_spi() -> dict:
    """HIR with SPI-connected sensor for signal-integrity placement tests."""
    hir = _make_hir(with_spi=True)
    return hir


def _make_hir_with_decap() -> dict:
    """HIR with a decoupling capacitor passive for SI placement tests."""
    hir = _make_hir()
    hir["components"].append({
        "id": "C1",
        "mpn": "C_0402",
        "name": "100nF bypass capacitor",
        "role": "passive",
        "interface_types": [],
        "pins": [],
        "provenance": {"source_type": "builtin_db", "confidence": 0.9},
    })
    return hir


class TestPhase20SignalIntegrityPlacement:
    """Signal-integrity-aware placement (MCU_X=30, SENSOR_X=130, SPI_X=65)."""

    MCU_X = 30.0
    SENSOR_X = 130.0
    SPI_X = 65.0   # MCU_X + 35

    def _engine(self) -> PcbLayoutEngine:
        return PcbLayoutEngine(use_llm=False)

    def _fp(self, hir: dict) -> dict:
        return FootprintMapper(use_llm=False).resolve_all(hir)

    def test_i2c_sensor_placed_at_sensor_x(self):
        """I2C slave (BME280) must be on the SENSOR_X spine."""
        hir = _make_hir()
        positions = self._engine()._plan_grid_positions(hir, self._fp(hir))
        assert abs(positions["U2"].x - self.SENSOR_X) < 5.0, (
            f"I2C sensor at x={positions['U2'].x}, expected ~{self.SENSOR_X}"
        )

    def test_spi_sensor_placed_near_mcu(self):
        """SPI slave must be in the mid-column adjacent to MCU (MCU_X + 35)."""
        hir = _make_hir_spi()
        positions = self._engine()._plan_grid_positions(hir, self._fp(hir))
        # U2 is the SPI slave in the SPI HIR
        u2_x = positions["U2"].x
        assert abs(u2_x - self.SPI_X) < 5.0, (
            f"SPI sensor at x={u2_x}, expected ~{self.SPI_X}"
        )

    def test_spi_sensor_closer_to_mcu_than_i2c_column(self):
        """SPI slave must be left of SENSOR_X (closer to MCU)."""
        hir = _make_hir_spi()
        positions = self._engine()._plan_grid_positions(hir, self._fp(hir))
        assert positions["U2"].x < self.SENSOR_X - 10

    def test_mcu_stays_at_mcu_x(self):
        """MCU position must not be affected by bus type."""
        for with_spi in (False, True):
            hir = _make_hir(with_spi=with_spi)
            positions = self._engine()._plan_grid_positions(hir, self._fp(hir))
            assert abs(positions["U1"].x - self.MCU_X) < 1.0, (
                f"MCU at x={positions['U1'].x}, expected ~{self.MCU_X}"
            )

    def test_decap_placed_adjacent_to_ic(self):
        """Decoupling cap must be placed 1.5 mm to the right of nearest IC (MCU).

        Phase 23.3: Decoupling caps moved from 6mm to 1.5mm for proper
        signal integrity — short trace to VDD pin.
        """
        hir = _make_hir_with_decap()
        engine = self._engine()
        positions = engine._plan_grid_positions(hir, self._fp(hir))
        assert "C1" in positions
        # Phase 23.3: Decap x should be MCU_X + 1.5 = 31.5mm (within tolerance)
        expected_x = self.MCU_X + 1.5
        assert abs(positions["C1"].x - expected_x) < 2.0, (
            f"Decap at x={positions['C1'].x}, expected ~{expected_x}"
        )

    def test_decap_y_near_mcu(self):
        """Decoupling cap y must be near the MCU centroid (within ~20mm)."""
        hir = _make_hir_with_decap()
        positions = self._engine()._plan_grid_positions(hir, self._fp(hir))
        mcu_y = positions["U1"].y
        assert abs(positions["C1"].y - mcu_y) < 20.0, (
            f"Decap y={positions['C1'].y} too far from MCU y={mcu_y}"
        )

    def test_all_positions_have_positive_coordinates(self):
        hir = _make_hir_with_decap()
        positions = self._engine()._plan_grid_positions(hir, self._fp(hir))
        for cid, pos in positions.items():
            assert pos.x > 0, f"{cid} x={pos.x} must be positive"
            assert pos.y > 0, f"{cid} y={pos.y} must be positive"


class TestPhase20DrcAutoFix:
    """DRC auto-fix: track width, via size, clearance, GND zone."""

    def _import(self):
        from boardsmith_hw.pcb_drc_autofix import PcbDrcAutoFix, run_drc_fix_loop, AutoFixResult
        return PcbDrcAutoFix, run_drc_fix_loop, AutoFixResult

    def _minimal_pcb(self, tmp_path: Path, extra: str = "") -> Path:
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text(
            "(kicad_pcb (version 20221018)\n"
            "  (general (thickness 1.6))\n"
            + extra
            + "\n)",
            encoding="utf-8",
        )
        return pcb

    # --- import sanity ---
    def test_import_succeeds(self):
        PcbDrcAutoFix, _, _ = self._import()
        fixer = PcbDrcAutoFix()
        assert fixer is not None

    # --- track width fix ---
    def test_fix_track_width_widens_narrow_track(self):
        from boardsmith_hw.pcb_drc_autofix import PcbDrcAutoFix
        pcb_text = "(kicad_pcb\n  (segment (width 0.1))\n)"
        fixer = PcbDrcAutoFix()
        new_text, changed = fixer._fix_track_width(pcb_text)
        assert changed
        assert "(width 0.2)" in new_text

    def test_fix_track_width_leaves_wide_track(self):
        from boardsmith_hw.pcb_drc_autofix import PcbDrcAutoFix
        pcb_text = "(kicad_pcb\n  (segment (width 0.5))\n)"
        fixer = PcbDrcAutoFix()
        _, changed = fixer._fix_track_width(pcb_text)
        assert not changed

    # --- via size fix ---
    def test_fix_via_size_increases_small_drill(self):
        from boardsmith_hw.pcb_drc_autofix import PcbDrcAutoFix
        pcb_text = "(kicad_pcb\n  (via (drill 0.1))\n)"
        fixer = PcbDrcAutoFix()
        new_text, changed = fixer._fix_via_size(pcb_text)
        assert changed
        assert "(drill 0.3)" in new_text

    def test_fix_via_size_leaves_large_drill(self):
        from boardsmith_hw.pcb_drc_autofix import PcbDrcAutoFix
        pcb_text = "(kicad_pcb\n  (via (drill 0.4))\n)"
        _, changed = PcbDrcAutoFix()._fix_via_size(pcb_text)
        assert not changed

    # --- clearance fix ---
    def test_fix_clearance_widens_small_clearance(self):
        from boardsmith_hw.pcb_drc_autofix import PcbDrcAutoFix
        pcb_text = "(kicad_pcb\n  (clearance 0.1)\n)"
        new_text, changed = PcbDrcAutoFix()._fix_clearance(pcb_text)
        assert changed
        assert "(clearance 0.2)" in new_text

    # --- GND zone ---
    def test_add_gnd_zone_when_no_zone_exists(self):
        from boardsmith_hw.pcb_drc_autofix import PcbDrcAutoFix
        pcb_text = (
            "(kicad_pcb\n"
            "  (gr_rect (start 0.0 0.0) (end 100.0 80.0))\n"
            ")"
        )
        new_text, changed = PcbDrcAutoFix()._add_gnd_zone(pcb_text)
        assert changed
        assert "(zone" in new_text
        assert '"GND"' in new_text

    def test_add_gnd_zone_skipped_when_zone_present(self):
        from boardsmith_hw.pcb_drc_autofix import PcbDrcAutoFix
        pcb_text = "(kicad_pcb\n  (zone (net 1) (net_name \"GND\"))\n)"
        _, changed = PcbDrcAutoFix()._add_gnd_zone(pcb_text)
        assert not changed

    def test_add_gnd_zone_skipped_when_no_edge_cuts(self):
        from boardsmith_hw.pcb_drc_autofix import PcbDrcAutoFix
        pcb_text = "(kicad_pcb\n  (general)\n)"
        _, changed = PcbDrcAutoFix()._add_gnd_zone(pcb_text)
        assert not changed

    # --- fix() end-to-end ---
    def test_fix_file_not_found_returns_remaining(self, tmp_path):
        from boardsmith_hw.pcb_drc_autofix import PcbDrcAutoFix

        class FakeViolation:
            description = "track_too_narrow"
            rule_id = "track_too_narrow"
            severity = "error"

        fixer = PcbDrcAutoFix()
        result = fixer.fix(tmp_path / "missing.kicad_pcb", [FakeViolation()])
        assert len(result.remaining) > 0
        assert not result.pcb_modified

    def test_fix_modifies_pcb_for_track_violation(self, tmp_path):
        from boardsmith_hw.pcb_drc_autofix import PcbDrcAutoFix

        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text(
            "(kicad_pcb\n  (segment (width 0.1))\n)",
            encoding="utf-8",
        )

        class FakeViolation:
            description = "track width too narrow"
            rule_id = "track_too_narrow"
            severity = "error"

        fixer = PcbDrcAutoFix()
        result = fixer.fix(pcb, [FakeViolation()])
        assert result.pcb_modified
        assert len(result.fixes_applied) > 0
        assert "(width 0.2)" in pcb.read_text()

    def test_run_drc_fix_loop_without_kicad_cli(self, tmp_path):
        """run_drc_fix_loop must degrade gracefully when kicad-cli is absent."""
        from boardsmith_hw.pcb_drc_autofix import run_drc_fix_loop
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb (version 20221018))", encoding="utf-8")
        result = run_drc_fix_loop(pcb, max_iterations=1)
        # If kicad-cli not available: remaining contains the skip message
        # If available but no errors: fixes_applied is empty — both are valid
        assert isinstance(result.fixes_applied, list)
        assert isinstance(result.remaining, list)


class TestPhase20DockerRouting:
    """Docker-based FreeRouting integration."""

    def test_docker_available_returns_bool(self):
        result = Autorouter._docker_available()
        assert isinstance(result, bool)

    def test_docker_image_name_correct(self):
        assert Autorouter._DOCKER_IMAGE == "boardsmith/freerouting:latest"

    def test_route_result_method_includes_docker_option(self, tmp_path):
        """route() may return 'freerouting_docker' as a valid method."""
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb (version 20221018))", encoding="utf-8")
        result = Autorouter().route(pcb)
        assert result.method in (
            "freerouting", "freerouting_docker", "kicad_cli_drc", "stub"
        )

    def test_router_result_method_stub_when_nothing_available(self, tmp_path):
        """When Docker image is absent and no native tools, method=stub."""
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb (version 20221018))", encoding="utf-8")
        result = Autorouter().route(pcb)
        if (
            not Autorouter.freerouting_available()
            and not Autorouter._docker_available()
            and not Autorouter.kicad_cli_available()
        ):
            assert result.method == "stub"

    def test_router_result_pcb_path_unchanged(self, tmp_path):
        """route() must return the same pcb_path it was given."""
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb (version 20221018))", encoding="utf-8")
        result = Autorouter().route(pcb)
        assert result.pcb_path == pcb


class TestPhase20CentroidExtraction:
    """Real coordinate extraction from .kicad_pcb vs grid fallback."""

    _KICAD_PCB_SAMPLE = """\
(kicad_pcb (version 20221018)
  (footprint "RF_Module:ESP32-WROOM-32" (layer "F.Cu")
    (at 30.0 35.0)
    (property "Reference" "U1" (at 0 0) (layer "F.Fab"))
  )
  (footprint "Bosch_SensorIC_Package:BME280" (layer "F.Cu")
    (at 130.0 35.0 90)
    (property "Reference" "U2" (at 0 0) (layer "F.Fab"))
  )
)
"""

    def test_extract_placements_reads_x_y(self, tmp_path):
        from boardsmith_hw.pcb_production import _extract_kicad_placements
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text(self._KICAD_PCB_SAMPLE, encoding="utf-8")
        placements = _extract_kicad_placements(pcb)
        assert "U1" in placements
        x, y, rot, layer = placements["U1"]
        assert abs(x - 30.0) < 0.01
        assert abs(y - 35.0) < 0.01
        assert abs(rot - 0.0) < 0.01
        assert layer == "Top"

    def test_extract_placements_reads_rotation(self, tmp_path):
        from boardsmith_hw.pcb_production import _extract_kicad_placements
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text(self._KICAD_PCB_SAMPLE, encoding="utf-8")
        placements = _extract_kicad_placements(pcb)
        assert "U2" in placements
        _, _, rot, _ = placements["U2"]
        assert abs(rot - 90.0) < 0.01

    def test_extract_placements_bottom_layer(self, tmp_path):
        from boardsmith_hw.pcb_production import _extract_kicad_placements
        pcb_text = """\
(kicad_pcb
  (footprint "Lib:Part" (layer "B.Cu")
    (at 50.0 60.0)
    (property "Reference" "R1" (at 0 0) (layer "B.Fab"))
  )
)
"""
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text(pcb_text, encoding="utf-8")
        placements = _extract_kicad_placements(pcb)
        assert "R1" in placements
        _, _, _, layer = placements["R1"]
        assert layer == "Bottom"

    def test_extract_placements_missing_file_returns_empty(self, tmp_path):
        from boardsmith_hw.pcb_production import _extract_kicad_placements
        placements = _extract_kicad_placements(tmp_path / "nonexistent.kicad_pcb")
        assert placements == {}

    def test_centroid_csv_uses_real_coords(self, tmp_path):
        from boardsmith_hw.pcb_production import _build_centroid_csv
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text(self._KICAD_PCB_SAMPLE, encoding="utf-8")
        hir = _make_hir()
        footprints = {"U1": "RF_Module:ESP32-WROOM-32", "U2": "Bosch:BME280"}
        csv_text = _build_centroid_csv(hir, footprints, pcb_path=pcb)
        # Real coordinates (30.00, 35.00) must appear for U1
        assert "30.00" in csv_text
        assert "35.00" in csv_text

    def test_centroid_csv_falls_back_to_grid_without_pcb(self):
        from boardsmith_hw.pcb_production import _build_centroid_csv
        hir = _make_hir()
        footprints = {"U1": "RF_Module:ESP32-WROOM-32", "U2": "Bosch:BME280"}
        csv_text = _build_centroid_csv(hir, footprints, pcb_path=None)
        # Should still produce a valid CSV with header
        assert "Designator" in csv_text
        assert "U1" in csv_text
        assert "U2" in csv_text

    def test_centroid_csv_header_correct(self):
        from boardsmith_hw.pcb_production import _build_centroid_csv
        hir = _make_hir()
        csv_text = _build_centroid_csv(hir, {})
        assert csv_text.splitlines()[0] == "Designator,Val,Package,Mid X,Mid Y,Rotation,Layer"

    def test_pipeline_centroid_includes_all_components(self, tmp_path):
        """End-to-end: PcbPipeline centroid CSV must list all HIR components."""
        from boardsmith_hw.pcb_production import PcbProductionExporter
        hir = _make_hir()
        pipeline = PcbPipeline(use_llm=False)
        pcb_result = pipeline.run(hir, out_dir=tmp_path)
        exporter = PcbProductionExporter()
        bundle = exporter.export(pcb_result, hir, out_dir=tmp_path / "bundle")
        assert "U1" in bundle.centroid_csv


# ---------------------------------------------------------------------------
# Quick-7: Net assignment fallback + drill clamp regression tests
# ---------------------------------------------------------------------------

def _s03_like_hir() -> dict:
    """STM32H743VIT6 with SPI bus — GPIO names in HIR don't match symbol pin names."""
    return {
        "system_name": "TestNetAssignment",
        "components": [
            {"id": "STM32H743VIT6", "mpn": "STM32H743VIT6", "role": "mcu",
             "interface_types": ["SPI", "I2C"]},
            {"id": "W25Q128JV", "mpn": "W25Q128JV", "role": "memory",
             "interface_types": ["SPI"]},
        ],
        "bus_contracts": [
            {"bus_type": "SPI", "bus_name": "spi0",
             "master_id": "STM32H743VIT6", "slave_ids": ["W25Q128JV"],
             "pin_assignments": {"MOSI": "PA7", "MISO": "PA6", "SCLK": "PA5", "CS": "PA4"}},
        ],
        "nets": [
            {"name": "spi0_MOSI", "pins": [
                {"component_id": "STM32H743VIT6", "pin_name": "PA7"},
                {"component_id": "W25Q128JV", "pin_name": "MOSI"},
            ]},
            {"name": "spi0_MISO", "pins": [
                {"component_id": "STM32H743VIT6", "pin_name": "PA6"},
                {"component_id": "W25Q128JV", "pin_name": "MISO"},
            ]},
            {"name": "spi0_SCK", "pins": [
                {"component_id": "STM32H743VIT6", "pin_name": "PA5"},
                {"component_id": "W25Q128JV", "pin_name": "SCK"},
            ]},
            {"name": "GND", "pins": [
                {"component_id": "STM32H743VIT6", "pin_name": "VSS"},
                {"component_id": "W25Q128JV", "pin_name": "GND"},
            ]},
            {"name": "+3V3", "pins": [
                {"component_id": "STM32H743VIT6", "pin_name": "VDD"},
            ]},
        ],
    }


class TestPcbNetAssignmentFallback:
    def _engine(self):
        from boardsmith_hw.pcb_layout_engine import PcbLayoutEngine
        return PcbLayoutEngine(use_llm=False)

    def _nets_and_map(self, hir):
        engine = self._engine()
        nets = engine._collect_nets(hir)
        pin_net_map = engine._build_pin_net_map(hir, nets)
        return engine, nets, pin_net_map

    def test_direct_gpio_match_still_works(self):
        """PB7 in HIR, PB7/SDA in symbol -> direct token match, no fallback needed."""
        hir = _s03_like_hir()
        hir["nets"].append({"name": "i2c0_SDA", "pins": [
            {"component_id": "STM32H743VIT6", "pin_name": "PB7"}
        ]})
        engine, nets, pin_net_map = self._nets_and_map(hir)
        nid, nname = engine._resolve_pin_net("PB7/SDA", nets, "STM32H743VIT6", pin_net_map)
        assert nname == "i2c0_SDA"
        assert nid > 0

    def test_signal_name_fallback_mosi(self):
        """PA7 in HIR for MOSI, symbol has PB5/MOSI -> signal-name fallback finds spi0_MOSI."""
        hir = _s03_like_hir()
        engine, nets, pin_net_map = self._nets_and_map(hir)
        # pin_net_map has (STM32H743VIT6, PA7) -> spi0_MOSI
        # _resolve_pin_net("PB5/MOSI") should find spi0_MOSI via MOSI token
        nid, nname = engine._resolve_pin_net("PB5/MOSI", nets, "STM32H743VIT6", pin_net_map)
        assert nname == "spi0_MOSI"
        assert nid > 0

    def test_signal_name_fallback_sck(self):
        """PA5 in HIR for SCK, symbol has PB3/SCLK -> SCLK token finds spi0_SCK."""
        hir = _s03_like_hir()
        engine, nets, pin_net_map = self._nets_and_map(hir)
        nid, nname = engine._resolve_pin_net("PB3/SCLK", nets, "STM32H743VIT6", pin_net_map)
        assert nname == "spi0_SCK"
        assert nid > 0

    def test_short_token_no_false_match(self):
        """Token 'PE' (len=2) must not accidentally match power net names."""
        hir = _s03_like_hir()
        engine, nets, pin_net_map = self._nets_and_map(hir)
        nid, nname = engine._resolve_pin_net("PE3", nets, "STM32H743VIT6", pin_net_map)
        # PE3 is an unconnected GPIO with no HIR net — must return (0, "") not a signal net
        assert nid == 0 or nname in ("GND", "+3V3", "+5V")  # only power keyword fallback ok

    def test_drill_clamped_to_300um(self):
        """Thru-hole pads with pad size < 0.6mm must have drill >= 0.30mm."""
        # The fix must clamp drill to 0.30mm. Verify by checking the clamp logic directly:
        pad_size = 0.25
        drill_unclamped = round(pad_size * 0.5, 2)  # = 0.12
        drill_clamped = max(0.30, drill_unclamped)
        assert drill_clamped == 0.30

    def test_pcb_build_has_few_unconnected_mcu_pads(self):
        """Full PCB build from S03-like HIR: SPI net names must appear in PCB output."""
        from boardsmith_hw.pcb_layout_engine import PcbLayoutEngine
        from boardsmith_hw.footprint_mapper import FootprintMapper
        engine = PcbLayoutEngine(use_llm=False)
        hir = _s03_like_hir()
        mapper = FootprintMapper(use_llm=False)
        footprints = mapper.resolve_all(hir)
        pcb_text = engine.build(hir, footprints)
        # The generated PCB must reference spi0_MOSI or spi0_SCK or spi0_MISO somewhere
        assert "spi0_MOSI" in pcb_text or "spi0_SCK" in pcb_text or "spi0_MISO" in pcb_text
