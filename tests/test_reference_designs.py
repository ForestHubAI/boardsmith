# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for shared/knowledge/reference_designs (Phase 18)."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure shared/ on path
_shared = Path(__file__).parent.parent / "shared"
if str(_shared) not in sys.path:
    sys.path.insert(0, str(_shared))

import pytest
from knowledge.reference_designs import (
    ReferenceDesignLibrary,
    ReferenceDesign,
    _hir_to_features,
    _similarity,
    _REFERENCE_DESIGNS,
)


# ---------------------------------------------------------------------------
# Sample HIR dicts
# ---------------------------------------------------------------------------

def _esp32_i2c_hir() -> dict:
    return {
        "components": [
            {"id": "ESP32", "mpn": "ESP32-WROOM-32", "role": "mcu"},
            {"id": "BME280", "mpn": "BME280", "role": "sensor", "category": "sensor"},
            {"id": "LDO", "mpn": "AMS1117-3.3", "role": "power"},
        ],
        "bus_contracts": [
            {"bus_type": "I2C", "bus_name": "i2c0"},
        ],
    }


def _battery_lora_hir() -> dict:
    return {
        "components": [
            {"id": "ESP32", "mpn": "ESP32-WROOM-32", "role": "mcu"},
            {"id": "SX1276", "mpn": "SX1276", "role": "comms"},
            {"id": "CHARGER", "mpn": "MCP73831T-2ATI", "role": "power"},
        ],
        "bus_contracts": [
            {"bus_type": "SPI", "bus_name": "spi0"},
            {"bus_type": "I2C", "bus_name": "i2c0"},
        ],
    }


def _rp2040_hir() -> dict:
    return {
        "components": [
            {"id": "RP2040", "mpn": "RP2040", "role": "mcu"},
        ],
        "bus_contracts": [
            {"bus_type": "SPI", "bus_name": "spi0"},
        ],
    }


# ---------------------------------------------------------------------------
# Tests — _hir_to_features
# ---------------------------------------------------------------------------

class TestHirToFeatures:
    def test_mcu_family_esp32(self):
        feats = _hir_to_features(_esp32_i2c_hir())
        assert feats["mcu_family"] == "esp32"

    def test_mcu_family_rp2040(self):
        feats = _hir_to_features(_rp2040_hir())
        assert feats["mcu_family"] == "rp2040"

    def test_bus_types_extracted(self):
        feats = _hir_to_features(_esp32_i2c_hir())
        assert "I2C" in feats["bus_types"]

    def test_multiple_bus_types(self):
        feats = _hir_to_features(_battery_lora_hir())
        assert "I2C" in feats["bus_types"]
        assert "SPI" in feats["bus_types"]

    def test_power_source_lipo_charger(self):
        feats = _hir_to_features(_battery_lora_hir())
        assert feats["power_source"] == "lipo"

    def test_power_source_default_usb(self):
        feats = _hir_to_features(_esp32_i2c_hir())
        assert feats["power_source"] == "usb5v"

    def test_sensor_count(self):
        feats = _hir_to_features(_esp32_i2c_hir())
        assert feats["sensor_count"] >= 1

    def test_no_display(self):
        feats = _hir_to_features(_esp32_i2c_hir())
        assert feats["has_display"] is False

    def test_has_rf_lora(self):
        feats = _hir_to_features(_battery_lora_hir())
        assert feats["has_rf"] is True

    def test_empty_hir(self):
        feats = _hir_to_features({})
        assert feats["mcu_family"] == "unknown"
        assert feats["bus_types"] == set()


# ---------------------------------------------------------------------------
# Tests — _similarity
# ---------------------------------------------------------------------------

class TestSimilarity:
    def _esp32_i2c_design(self) -> ReferenceDesign:
        return ReferenceDesign(
            name="Test",
            description="",
            mcu_family="esp32",
            bus_types=["I2C"],
            power_source="usb5v",
            components=[],
            has_display=False,
            has_rf=False,
            sensor_count=1,
        )

    def test_perfect_match(self):
        feats = _hir_to_features(_esp32_i2c_hir())
        design = self._esp32_i2c_design()
        score = _similarity(feats, design)
        assert score >= 0.90

    def test_wrong_mcu_reduces_score(self):
        feats = _hir_to_features(_rp2040_hir())
        design = self._esp32_i2c_design()
        score = _similarity(feats, design)
        assert score < 0.70  # MCU mismatch

    def test_score_range(self):
        feats = _hir_to_features(_esp32_i2c_hir())
        design = self._esp32_i2c_design()
        score = _similarity(feats, design)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Tests — ReferenceDesignLibrary
# ---------------------------------------------------------------------------

class TestReferenceDesignLibrary:
    def test_has_built_in_designs(self):
        lib = ReferenceDesignLibrary()
        assert len(lib.all_designs()) >= 5

    def test_find_closest_returns_result(self):
        lib = ReferenceDesignLibrary()
        match, conf = lib.find_closest(_esp32_i2c_hir())
        assert match is not None
        assert 0.0 <= conf <= 1.0

    def test_esp32_i2c_matches_env_station(self):
        lib = ReferenceDesignLibrary()
        match, conf = lib.find_closest(_esp32_i2c_hir())
        assert match is not None
        assert conf >= 0.70
        assert "esp32" in match.name.lower() or "esp32" in match.mcu_family

    def test_battery_lora_matches_lora_design(self):
        lib = ReferenceDesignLibrary()
        match, conf = lib.find_closest(_battery_lora_hir())
        assert match is not None
        assert conf >= 0.40

    def test_empty_library_returns_none(self):
        lib = ReferenceDesignLibrary(designs=[])
        match, conf = lib.find_closest(_esp32_i2c_hir())
        assert match is None
        assert conf == 0.0

    def test_conf_below_1(self):
        lib = ReferenceDesignLibrary()
        _, conf = lib.find_closest(_esp32_i2c_hir())
        assert conf <= 1.0

    def test_all_designs_accessible(self):
        lib = ReferenceDesignLibrary()
        designs = lib.all_designs()
        assert all(isinstance(d, ReferenceDesign) for d in designs)
