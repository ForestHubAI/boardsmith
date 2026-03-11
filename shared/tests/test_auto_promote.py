# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for DB-4: Knowledge Agent Auto-Promote (draft state management).

Covers:
  - component_state column present after migration
  - Builtin upsert defaults to 'released'
  - upsert_draft stores 'draft' state + confidence
  - list_drafts returns only draft components
  - validate_draft: happy path → 'validated'
  - validate_draft: missing required fields → errors returned
  - validate_draft: invalid state → errors
  - find_by_state filters correctly
  - Idempotent migration (column_state column added to existing DB)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from shared.knowledge.db import (
    find_by_mpn,
    find_by_state,
    list_drafts,
    upsert,
    upsert_draft,
    validate_draft,
    _connect,
)
from shared.knowledge.schema import ComponentEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


def _minimal_draft(mpn: str = "DRF_IC_001") -> ComponentEntry:
    return {
        "mpn": mpn,
        "manufacturer": "TestCo",
        "name": mpn,
        "category": "sensor",
        "sub_type": "environmental",
        "interface_types": ["I2C"],
        "package": "DFN-4",
        "mounting": "smd",
        "pin_count": 4,
        "description": "Test draft component",
        "electrical_ratings": {"vdd_min": 1.8, "vdd_max": 3.6},
        "tags": ["test", "draft"],
        "status": "active",
    }


def _minimal_release(mpn: str = "REL_IC_001") -> ComponentEntry:
    return {
        **_minimal_draft(mpn),
        "mpn": mpn,
    }


# ---------------------------------------------------------------------------
# Column presence
# ---------------------------------------------------------------------------

class TestMigrationColumns:
    def test_component_state_column_present(self, tmp_db):
        conn = _connect(tmp_db)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(components)")}
        conn.close()
        assert "component_state" in cols

    def test_agent_confidence_column_present(self, tmp_db):
        conn = _connect(tmp_db)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(components)")}
        conn.close()
        assert "agent_confidence" in cols


# ---------------------------------------------------------------------------
# Default state for builtin upsert
# ---------------------------------------------------------------------------

class TestDefaultState:
    def test_builtin_upsert_defaults_to_released(self, tmp_db):
        upsert(_minimal_release("REL_001"), source="builtin", db_path=tmp_db)
        entry = find_by_mpn("REL_001", db_path=tmp_db)
        assert entry is not None
        assert entry.get("component_state") == "released"


# ---------------------------------------------------------------------------
# upsert_draft
# ---------------------------------------------------------------------------

class TestUpsertDraft:
    def test_draft_inserted_with_draft_state(self, tmp_db):
        upsert_draft(_minimal_draft("DRF_001"), confidence=0.82, db_path=tmp_db)
        entry = find_by_mpn("DRF_001", db_path=tmp_db)
        assert entry is not None
        assert entry.get("component_state") == "draft"

    def test_draft_confidence_stored(self, tmp_db):
        upsert_draft(_minimal_draft("DRF_002"), confidence=0.90, db_path=tmp_db)
        conn = _connect(tmp_db)
        row = conn.execute(
            "SELECT agent_confidence FROM components WHERE mpn = ?", ("DRF_002",)
        ).fetchone()
        conn.close()
        assert row is not None
        assert abs(row["agent_confidence"] - 0.90) < 0.001

    def test_list_drafts_returns_only_drafts(self, tmp_db):
        upsert(_minimal_release("REL_001"), source="builtin", db_path=tmp_db)
        upsert_draft(_minimal_draft("DRF_001"), confidence=0.80, db_path=tmp_db)
        upsert_draft(_minimal_draft("DRF_002"), confidence=0.77, db_path=tmp_db)
        drafts = list_drafts(db_path=tmp_db)
        mpns = {e["mpn"] for e in drafts}
        assert "DRF_001" in mpns
        assert "DRF_002" in mpns
        assert "REL_001" not in mpns

    def test_list_drafts_empty_when_none(self, tmp_db):
        upsert(_minimal_release(), source="builtin", db_path=tmp_db)
        assert list_drafts(db_path=tmp_db) == []


# ---------------------------------------------------------------------------
# validate_draft
# ---------------------------------------------------------------------------

class TestValidateDraft:
    def test_valid_draft_promotes_to_validated(self, tmp_db):
        upsert_draft(_minimal_draft("DRF_OK"), confidence=0.85, db_path=tmp_db)
        errors = validate_draft("DRF_OK", db_path=tmp_db)
        assert errors == []
        entry = find_by_mpn("DRF_OK", db_path=tmp_db)
        assert entry["component_state"] == "validated"

    def test_missing_manufacturer_returns_error(self, tmp_db):
        e = _minimal_draft("DRF_BAD")
        e["manufacturer"] = ""  # type: ignore[typeddict-item]
        upsert_draft(e, confidence=0.80, db_path=tmp_db)
        errors = validate_draft("DRF_BAD", db_path=tmp_db)
        assert any("manufacturer" in err for err in errors)

    def test_missing_interface_types_returns_error(self, tmp_db):
        e = _minimal_draft("DRF_NO_IFACE")
        e["interface_types"] = []
        upsert_draft(e, confidence=0.80, db_path=tmp_db)
        errors = validate_draft("DRF_NO_IFACE", db_path=tmp_db)
        assert any("interface_types" in err for err in errors)

    def test_missing_electrical_ratings_returns_error(self, tmp_db):
        e = _minimal_draft("DRF_NO_VDD")
        e["electrical_ratings"] = {}
        upsert_draft(e, confidence=0.80, db_path=tmp_db)
        errors = validate_draft("DRF_NO_VDD", db_path=tmp_db)
        assert any("vdd" in err.lower() for err in errors)

    def test_unknown_category_returns_error(self, tmp_db):
        e = _minimal_draft("DRF_BAD_CAT")
        e["category"] = "magic_gadget"  # type: ignore
        upsert_draft(e, confidence=0.80, db_path=tmp_db)
        errors = validate_draft("DRF_BAD_CAT", db_path=tmp_db)
        assert any("category" in err for err in errors)

    def test_nonexistent_mpn_returns_error(self, tmp_db):
        errors = validate_draft("DOES_NOT_EXIST_XYZ", db_path=tmp_db)
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_released_component_cannot_be_promoted(self, tmp_db):
        upsert(_minimal_release("REL_X"), source="builtin", db_path=tmp_db)
        errors = validate_draft("REL_X", db_path=tmp_db)
        assert any("released" in err for err in errors)

    def test_promote_to_verified(self, tmp_db):
        upsert_draft(_minimal_draft("DRF_V"), confidence=0.92, db_path=tmp_db)
        validate_draft("DRF_V", new_state="validated", db_path=tmp_db)
        errors = validate_draft("DRF_V", new_state="verified", db_path=tmp_db)
        assert errors == []
        entry = find_by_mpn("DRF_V", db_path=tmp_db)
        assert entry["component_state"] == "verified"

    def test_invalid_target_state_returns_error(self, tmp_db):
        upsert_draft(_minimal_draft("DRF_INV"), confidence=0.80, db_path=tmp_db)
        errors = validate_draft("DRF_INV", new_state="production_ready", db_path=tmp_db)
        assert any("Invalid state" in err for err in errors)


# ---------------------------------------------------------------------------
# find_by_state
# ---------------------------------------------------------------------------

class TestFindByState:
    def test_find_released(self, tmp_db):
        upsert(_minimal_release("REL_A"), source="builtin", db_path=tmp_db)
        upsert_draft(_minimal_draft("DRF_B"), confidence=0.80, db_path=tmp_db)
        released = find_by_state("released", db_path=tmp_db)
        mpns = {e["mpn"] for e in released}
        assert "REL_A" in mpns
        assert "DRF_B" not in mpns

    def test_find_draft(self, tmp_db):
        upsert(_minimal_release("REL_A"), source="builtin", db_path=tmp_db)
        upsert_draft(_minimal_draft("DRF_B"), confidence=0.80, db_path=tmp_db)
        drafts = find_by_state("draft", db_path=tmp_db)
        mpns = {e["mpn"] for e in drafts}
        assert "DRF_B" in mpns
        assert "REL_A" not in mpns
