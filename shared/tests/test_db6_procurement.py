# SPDX-License-Identifier: AGPL-3.0-or-later
"""DB-6: Procurement & Substitutes — supplier_parts + component_substitutes tests."""
from __future__ import annotations

import sys
from pathlib import Path
import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_REPO = Path(__file__).parent.parent.parent
for p in [str(_REPO / "shared"), str(_REPO)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import knowledge.db as db
from knowledge.seed.procurement import SUPPLIER_PARTS, SUBSTITUTES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    return tmp_path / "test_procurement.db"


# ---------------------------------------------------------------------------
# TestSupplierParts
# ---------------------------------------------------------------------------

class TestSupplierParts:
    def test_upsert_and_find_single(self, tmp_db):
        db.upsert_supplier_part(
            mpn="BME280", supplier="LCSC", sku="C17024",
            unit_price_usd=2.90, moq=1, stock_qty=20000,
            url="https://lcsc.com/C17024", last_seen="2026-03-01",
            db_path=tmp_db,
        )
        parts = db.find_supplier_parts("BME280", db_path=tmp_db)
        assert len(parts) == 1
        assert parts[0]["sku"] == "C17024"
        assert parts[0]["unit_price_usd"] == pytest.approx(2.90)
        assert parts[0]["supplier"] == "LCSC"

    def test_upsert_multiple_suppliers(self, tmp_db):
        db.upsert_supplier_part("BME280","LCSC","C17024",2.90,db_path=tmp_db)
        db.upsert_supplier_part("BME280","DigiKey","828-1063-1-ND",3.50,db_path=tmp_db)
        parts = db.find_supplier_parts("BME280", db_path=tmp_db)
        assert len(parts) == 2
        # Sorted by price ascending
        assert parts[0]["unit_price_usd"] < parts[1]["unit_price_usd"]

    def test_get_best_price_returns_cheapest(self, tmp_db):
        db.upsert_supplier_part("BME280","LCSC","C17024",2.90,db_path=tmp_db)
        db.upsert_supplier_part("BME280","DigiKey","828-1063-1-ND",3.50,db_path=tmp_db)
        best = db.get_best_price("BME280", db_path=tmp_db)
        assert best is not None
        assert best["unit_price_usd"] == pytest.approx(2.90)
        assert best["supplier"] == "LCSC"

    def test_get_best_price_returns_none_for_unknown(self, tmp_db):
        assert db.get_best_price("NONEXISTENT-MPN", db_path=tmp_db) is None

    def test_find_by_supplier(self, tmp_db):
        db.upsert_supplier_part("BME280","LCSC","C17024",2.90,db_path=tmp_db)
        db.upsert_supplier_part("MPU-6050","LCSC","C24112",0.75,db_path=tmp_db)
        db.upsert_supplier_part("BME280","DigiKey","828-1063-1-ND",3.50,db_path=tmp_db)
        lcsc = db.find_by_supplier("LCSC", db_path=tmp_db)
        assert len(lcsc) == 2
        mpns = {p["mpn"] for p in lcsc}
        assert "BME280" in mpns and "MPU-6050" in mpns

    def test_upsert_replaces_existing(self, tmp_db):
        db.upsert_supplier_part("BME280","LCSC","C17024",2.90,stock_qty=5000,db_path=tmp_db)
        db.upsert_supplier_part("BME280","LCSC","C17024",2.75,stock_qty=25000,db_path=tmp_db)
        parts = db.find_supplier_parts("BME280", db_path=tmp_db)
        assert len(parts) == 1
        assert parts[0]["unit_price_usd"] == pytest.approx(2.75)
        assert parts[0]["stock_qty"] == 25000

    def test_bulk_upsert(self, tmp_db):
        db.upsert_supplier_parts_bulk(SUPPLIER_PARTS[:10], db_path=tmp_db)
        total = sum(
            len(db.find_supplier_parts(p["mpn"], db_path=tmp_db))
            for p in SUPPLIER_PARTS[:10]
        )
        assert total == 10

    def test_no_parts_for_empty_db(self, tmp_db):
        assert db.find_supplier_parts("BME280", db_path=tmp_db) == []

    def test_missing_price_handled(self, tmp_db):
        db.upsert_supplier_part("BME280","LCSC","C17024",db_path=tmp_db)
        parts = db.find_supplier_parts("BME280", db_path=tmp_db)
        assert len(parts) == 1
        # Best price still works even with None price
        best = db.get_best_price("BME280", db_path=tmp_db)
        assert best is not None


# ---------------------------------------------------------------------------
# TestComponentSubstitutes
# ---------------------------------------------------------------------------

class TestComponentSubstitutes:
    def test_upsert_and_find_substitute(self, tmp_db):
        db.upsert_substitute(
            "BME280", "BMP280", reason="functional-equiv",
            confidence=0.85, verified=True, notes="No humidity",
            db_path=tmp_db,
        )
        subs = db.find_substitutes("BME280", db_path=tmp_db)
        assert len(subs) == 1
        assert subs[0]["substitute_mpn"] == "BMP280"
        assert subs[0]["confidence"] == pytest.approx(0.85)
        assert subs[0]["verified"] == 1

    def test_multiple_substitutes_sorted_by_confidence(self, tmp_db):
        db.upsert_substitute("BME280","BMP280",confidence=0.85,db_path=tmp_db)
        db.upsert_substitute("BME280","BME680",confidence=0.90,db_path=tmp_db)
        db.upsert_substitute("BME280","SHT31",confidence=0.60,db_path=tmp_db)
        subs = db.find_substitutes("BME280", db_path=tmp_db)
        assert len(subs) == 3
        confidences = [s["confidence"] for s in subs]
        assert confidences == sorted(confidences, reverse=True)

    def test_find_primary_for(self, tmp_db):
        db.upsert_substitute("BME280","BMP280",confidence=0.85,db_path=tmp_db)
        db.upsert_substitute("BME680","BMP280",confidence=0.70,db_path=tmp_db)
        primaries = db.find_primary_for("BMP280", db_path=tmp_db)
        assert len(primaries) == 2
        primary_mpns = {p["primary_mpn"] for p in primaries}
        assert "BME280" in primary_mpns and "BME680" in primary_mpns

    def test_verified_substitutes_filter(self, tmp_db):
        db.upsert_substitute("BME280","BMP280",confidence=0.85,verified=True,db_path=tmp_db)
        db.upsert_substitute("BME280","SHT31",confidence=0.60,verified=False,db_path=tmp_db)
        verified = db.find_verified_substitutes(db_path=tmp_db)
        assert len(verified) == 1
        assert verified[0]["substitute_mpn"] == "BMP280"

    def test_no_substitutes_returns_empty(self, tmp_db):
        assert db.find_substitutes("NONEXISTENT", db_path=tmp_db) == []

    def test_bulk_substitutes(self, tmp_db):
        db.upsert_substitutes_bulk(SUBSTITUTES, db_path=tmp_db)
        bme_subs = db.find_substitutes("BME280", db_path=tmp_db)
        assert len(bme_subs) >= 2
        mpu_subs = db.find_substitutes("MPU-6050", db_path=tmp_db)
        assert len(mpu_subs) >= 1

    def test_substitute_reasons(self, tmp_db):
        db.upsert_substitutes_bulk(SUBSTITUTES, db_path=tmp_db)
        all_verified = db.find_verified_substitutes(db_path=tmp_db)
        reasons = {s["reason"] for s in all_verified}
        assert "pin-compatible" in reasons or "functional-equiv" in reasons

    def test_upsert_replaces_existing_substitute(self, tmp_db):
        db.upsert_substitute("BME280","BMP280",confidence=0.5,verified=False,db_path=tmp_db)
        db.upsert_substitute("BME280","BMP280",confidence=0.9,verified=True,db_path=tmp_db)
        subs = db.find_substitutes("BME280", db_path=tmp_db)
        assert len(subs) == 1
        assert subs[0]["confidence"] == pytest.approx(0.9)
        assert subs[0]["verified"] == 1


# ---------------------------------------------------------------------------
# TestSeedData
# ---------------------------------------------------------------------------

class TestSeedData:
    def test_supplier_parts_seed_has_critical_mpns(self):
        mpns = {p["mpn"] for p in SUPPLIER_PARTS}
        assert "BME280" in mpns
        assert "MPU-6050" in mpns
        assert "AMS1117-3.3" in mpns
        assert "SX1276" in mpns
        assert "W25Q128JV" in mpns

    def test_supplier_parts_seed_has_valid_prices(self):
        for p in SUPPLIER_PARTS:
            if p.get("unit_price_usd") is not None:
                assert p["unit_price_usd"] > 0, f"{p['mpn']} has zero/negative price"

    def test_supplier_parts_all_have_lcsc_sku(self):
        lcsc = [p for p in SUPPLIER_PARTS if p["supplier"] == "LCSC"]
        assert len(lcsc) >= 20
        for p in lcsc:
            assert p["sku"].startswith("C"), f"{p['mpn']} LCSC SKU should start with C"

    def test_substitutes_seed_coverage(self):
        primary_mpns = {s["primary_mpn"] for s in SUBSTITUTES}
        assert "BME280" in primary_mpns
        assert "MPU-6050" in primary_mpns
        assert len(SUBSTITUTES) >= 10

    def test_substitutes_confidence_in_range(self):
        for s in SUBSTITUTES:
            assert 0.0 <= s.get("confidence", 0.5) <= 1.0, (
                f"Confidence out of range for {s['primary_mpn']}→{s['substitute_mpn']}"
            )
