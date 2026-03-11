# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for DB-2: SQLite Normalization — flat columns + range queries.

Covers:
  - Flat columns populated from electrical_ratings during upsert
  - vdd_min / vdd_max range queries
  - Temperature range queries
  - 5V-tolerant filter
  - Low-power filter
  - family / series fields
  - Migration idempotency (existing DB gets new columns)
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from shared.knowledge.db import (
    count,
    find_5v_tolerant,
    find_by_family,
    find_by_interface,
    find_by_mpn,
    find_by_temp_range,
    find_by_voltage_range,
    find_by_vdd_max,
    find_low_power,
    upsert,
    upsert_many,
)
from shared.knowledge.schema import ComponentEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Fresh temporary DB for each test."""
    return tmp_path / "test.db"


def _bme280_entry() -> ComponentEntry:
    return {
        "mpn": "BME280",
        "manufacturer": "Bosch",
        "name": "BME280",
        "category": "sensor",
        "sub_type": "environmental",
        "family": "BME",
        "series": "BME280",
        "interface_types": ["I2C", "SPI"],
        "package": "LGA-8",
        "mounting": "smd",
        "pin_count": 8,
        "description": "Humidity/Temp/Pressure",
        "electrical_ratings": {
            "vdd_min": 1.71,
            "vdd_max": 3.6,
            "io_voltage_nominal": 3.3,
            "is_5v_tolerant": False,
            "current_draw_max_ma": 1.0,
            "sleep_current_ua": 0.1,
            "abs_max_voltage": 4.25,
            "temp_min_c": -40.0,
            "temp_max_c": 85.0,
        },
        "tags": ["sensor", "i2c"],
        "status": "active",
    }


def _stm32_entry() -> ComponentEntry:
    return {
        "mpn": "STM32F103C8T6",
        "manufacturer": "ST",
        "name": "STM32F103",
        "category": "mcu",
        "sub_type": "arm-cortex-m3",
        "family": "STM32F1",
        "series": "STM32F103",
        "interface_types": ["I2C", "SPI", "UART"],
        "package": "LQFP-48",
        "mounting": "smd",
        "pin_count": 48,
        "description": "ARM Cortex-M3 MCU",
        "electrical_ratings": {
            "vdd_min": 2.0,
            "vdd_max": 3.6,
            "io_voltage_nominal": 3.3,
            "is_5v_tolerant": True,
            "current_draw_max_ma": 50.0,
            "sleep_current_ua": 2.0,
            "abs_max_voltage": 4.0,
            "temp_min_c": -40.0,
            "temp_max_c": 85.0,
        },
        "tags": ["mcu", "stm32"],
        "status": "active",
    }


def _lp_sensor_entry() -> ComponentEntry:
    """Ultra-low-power sensor at 1.8V only."""
    return {
        "mpn": "SHTC3",
        "manufacturer": "Sensirion",
        "name": "SHTC3",
        "category": "sensor",
        "sub_type": "environmental",
        "family": "SHTC",
        "series": "SHTC3",
        "interface_types": ["I2C"],
        "package": "DFN-4",
        "mounting": "smd",
        "pin_count": 4,
        "description": "Temp+Humidity 1.8V",
        "electrical_ratings": {
            "vdd_min": 1.62,
            "vdd_max": 1.98,
            "is_5v_tolerant": False,
            "current_draw_max_ma": 0.28,
            "sleep_current_ua": 0.04,
            "temp_min_c": -40.0,
            "temp_max_c": 125.0,
        },
        "tags": ["sensor"],
        "status": "active",
    }


# ---------------------------------------------------------------------------
# Flat column population
# ---------------------------------------------------------------------------

class TestFlatColumns:
    def test_vdd_columns_from_electrical_ratings(self, tmp_db):
        upsert(_bme280_entry(), db_path=tmp_db)
        entry = find_by_mpn("BME280", db_path=tmp_db)
        assert entry is not None
        er = entry["electrical_ratings"]
        assert er["vdd_min"] == pytest.approx(1.71)
        assert er["vdd_max"] == pytest.approx(3.6)

    def test_temp_columns_from_electrical_ratings(self, tmp_db):
        upsert(_bme280_entry(), db_path=tmp_db)
        entry = find_by_mpn("BME280", db_path=tmp_db)
        assert entry["electrical_ratings"]["temp_min_c"] == -40.0
        assert entry["electrical_ratings"]["temp_max_c"] == 85.0

    def test_family_series_stored_and_retrieved(self, tmp_db):
        upsert(_bme280_entry(), db_path=tmp_db)
        entry = find_by_mpn("BME280", db_path=tmp_db)
        assert entry["family"] == "BME"
        assert entry["series"] == "BME280"

    def test_family_series_default_empty(self, tmp_db):
        """Entry without family/series still inserts cleanly."""
        e: ComponentEntry = {
            "mpn": "BARE_IC",
            "category": "other",
            "name": "Bare IC",
            "interface_types": [],
            "tags": [],
        }
        upsert(e, db_path=tmp_db)
        entry = find_by_mpn("BARE_IC", db_path=tmp_db)
        assert entry is not None
        assert entry["family"] == ""
        assert entry["series"] == ""

    def test_5v_tolerant_flag_stored(self, tmp_db):
        upsert(_stm32_entry(), db_path=tmp_db)
        upsert(_bme280_entry(), db_path=tmp_db)
        tolerant = find_5v_tolerant(db_path=tmp_db)
        mpns = {e["mpn"] for e in tolerant}
        assert "STM32F103C8T6" in mpns
        assert "BME280" not in mpns


# ---------------------------------------------------------------------------
# Voltage range queries
# ---------------------------------------------------------------------------

class TestVoltageRangeQueries:
    def test_find_by_voltage_range_3v3(self, tmp_db):
        upsert_many([_bme280_entry(), _stm32_entry(), _lp_sensor_entry()], db_path=tmp_db)
        results = find_by_voltage_range(3.3, db_path=tmp_db)
        mpns = {e["mpn"] for e in results}
        assert "BME280" in mpns
        assert "STM32F103C8T6" in mpns
        assert "SHTC3" not in mpns  # SHTC3 max is 1.98 V

    def test_find_by_voltage_range_1v8(self, tmp_db):
        upsert_many([_bme280_entry(), _stm32_entry(), _lp_sensor_entry()], db_path=tmp_db)
        results = find_by_voltage_range(1.8, db_path=tmp_db)
        mpns = {e["mpn"] for e in results}
        assert "SHTC3" in mpns
        assert "BME280" in mpns       # 1.71 ≤ 1.8 ≤ 3.6
        assert "STM32F103C8T6" not in mpns   # STM32 needs min 2.0 V

    def test_find_by_vdd_max(self, tmp_db):
        upsert_many([_bme280_entry(), _stm32_entry(), _lp_sensor_entry()], db_path=tmp_db)
        results = find_by_vdd_max(2.0, db_path=tmp_db)
        mpns = {e["mpn"] for e in results}
        assert "SHTC3" in mpns        # max 1.98 ≤ 2.0
        assert "BME280" not in mpns   # max 3.6 > 2.0
        assert "STM32F103C8T6" not in mpns


# ---------------------------------------------------------------------------
# Temperature range queries
# ---------------------------------------------------------------------------

class TestTemperatureRangeQueries:
    def test_find_by_temp_range_standard(self, tmp_db):
        upsert_many([_bme280_entry(), _stm32_entry(), _lp_sensor_entry()], db_path=tmp_db)
        results = find_by_temp_range(-40.0, 85.0, db_path=tmp_db)
        mpns = {e["mpn"] for e in results}
        # All three have temp range ≥ [-40, 85]
        assert "BME280" in mpns
        assert "STM32F103C8T6" in mpns
        assert "SHTC3" in mpns  # SHTC3 is -40 to 125

    def test_find_by_temp_range_extended(self, tmp_db):
        upsert_many([_bme280_entry(), _lp_sensor_entry()], db_path=tmp_db)
        results = find_by_temp_range(-40.0, 100.0, db_path=tmp_db)
        mpns = {e["mpn"] for e in results}
        assert "SHTC3" in mpns        # 125 ≥ 100
        assert "BME280" not in mpns   # 85 < 100


# ---------------------------------------------------------------------------
# Low-power filter
# ---------------------------------------------------------------------------

class TestLowPowerFilter:
    def test_find_low_power(self, tmp_db):
        upsert_many([_bme280_entry(), _stm32_entry(), _lp_sensor_entry()], db_path=tmp_db)
        results = find_low_power(i_active_max_ma=1.0, db_path=tmp_db)
        mpns = {e["mpn"] for e in results}
        assert "BME280" in mpns       # 1.0 mA ≤ 1.0
        assert "SHTC3" in mpns        # 0.28 mA ≤ 1.0
        assert "STM32F103C8T6" not in mpns  # 50 mA > 1.0


# ---------------------------------------------------------------------------
# Family filter
# ---------------------------------------------------------------------------

class TestFamilyFilter:
    def test_find_by_family(self, tmp_db):
        stm32_g: ComponentEntry = {
            **_stm32_entry(),
            "mpn": "STM32F103RBT6",
            "family": "STM32F1",
            "series": "STM32F103",
        }
        upsert_many([_stm32_entry(), stm32_g, _bme280_entry()], db_path=tmp_db)
        results = find_by_family("STM32F1", db_path=tmp_db)
        mpns = {e["mpn"] for e in results}
        assert "STM32F103C8T6" in mpns
        assert "STM32F103RBT6" in mpns
        assert "BME280" not in mpns


# ---------------------------------------------------------------------------
# Migration idempotency
# ---------------------------------------------------------------------------

class TestMigration:
    def test_migration_is_idempotent(self, tmp_db):
        """Connecting twice should not raise (columns already exist on second connect)."""
        from shared.knowledge.db import _connect
        conn1 = _connect(tmp_db)
        conn1.close()
        conn2 = _connect(tmp_db)  # should not fail even though columns exist
        conn2.close()

    def test_all_new_columns_present(self, tmp_db):
        from shared.knowledge.db import _connect
        conn = _connect(tmp_db)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(components)")}
        conn.close()
        for col, _ in [
            ("family", ""), ("series", ""),
            ("vdd_min", ""), ("vdd_max", ""), ("vdd_typ", ""),
            ("abs_max_vdd", ""), ("i_active_max_ma", ""),
            ("i_sleep_ua", ""), ("temp_min_c", ""), ("temp_max_c", ""),
            ("is_5v_tolerant", ""),
        ]:
            assert col in cols, f"Column '{col}' missing from components table"
