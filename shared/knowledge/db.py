# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite-backed component knowledge store.

Single-file database (boardsmith.db) co-located next to this module.
Designed to scale to 10 000+ components without loading everything into memory.

Schema
------
components          — one row per MPN, flat + JSON blobs
component_interfaces — many-to-many: MPN ↔ interface string
component_tags       — many-to-many: MPN ↔ tag string
components_fts       — FTS5 virtual table for full-text search

Public helpers mirror the old list-based API so callers need no changes.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from knowledge.schema import ComponentEntry

# DB lives next to this file
_DB_PATH = Path(__file__).parent / "boardsmith.db"

_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS components (
    mpn                    TEXT PRIMARY KEY,
    manufacturer           TEXT,
    name                   TEXT,
    category               TEXT,
    sub_type               TEXT  DEFAULT '',
    family                 TEXT  DEFAULT '',
    series                 TEXT  DEFAULT '',
    package                TEXT,
    mounting               TEXT  DEFAULT 'smd',
    pin_count              INTEGER DEFAULT 0,
    description            TEXT,
    known_i2c_addresses    TEXT  DEFAULT '[]',   -- JSON array
    i2c_address_selectable INTEGER DEFAULT 0,
    init_contract_coverage INTEGER DEFAULT 0,
    init_contract_template TEXT  DEFAULT '{}',   -- JSON object
    electrical_ratings     TEXT  DEFAULT '{}',   -- JSON object
    timing_caps            TEXT  DEFAULT '{}',   -- JSON object
    capabilities           TEXT  DEFAULT '{}',   -- JSON object — category-specific specs
    unit_cost_usd          REAL,
    datasheet_url          TEXT  DEFAULT '',
    status                 TEXT  DEFAULT 'active',
    library_support        TEXT  DEFAULT '[]',   -- JSON array
    source                 TEXT  DEFAULT 'builtin',
    -- DB-2 flat columns (extracted from electrical_ratings for SQL range queries)
    vdd_min                REAL,
    vdd_max                REAL,
    vdd_typ                REAL,
    abs_max_vdd            REAL,
    i_active_max_ma        REAL,
    i_sleep_ua             REAL,
    temp_min_c             REAL,
    temp_max_c             REAL,
    is_5v_tolerant         INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS component_interfaces (
    mpn            TEXT NOT NULL REFERENCES components(mpn) ON DELETE CASCADE,
    interface_type TEXT NOT NULL,
    PRIMARY KEY (mpn, interface_type)
);

CREATE TABLE IF NOT EXISTS component_tags (
    mpn  TEXT NOT NULL REFERENCES components(mpn) ON DELETE CASCADE,
    tag  TEXT NOT NULL,
    PRIMARY KEY (mpn, tag)
);

CREATE VIRTUAL TABLE IF NOT EXISTS components_fts USING fts5(
    mpn, name, description, content='components', content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS components_fts_insert
    AFTER INSERT ON components BEGIN
        INSERT INTO components_fts(rowid, mpn, name, description)
        VALUES (new.rowid, new.mpn, new.name, new.description);
    END;

CREATE TRIGGER IF NOT EXISTS components_fts_delete
    AFTER DELETE ON components BEGIN
        INSERT INTO components_fts(components_fts, rowid, mpn, name, description)
        VALUES ('delete', old.rowid, old.mpn, old.name, old.description);
    END;

CREATE TRIGGER IF NOT EXISTS components_fts_update
    AFTER UPDATE ON components BEGIN
        INSERT INTO components_fts(components_fts, rowid, mpn, name, description)
        VALUES ('delete', old.rowid, old.mpn, old.name, old.description);
        INSERT INTO components_fts(rowid, mpn, name, description)
        VALUES (new.rowid, new.mpn, new.name, new.description);
    END;

-- DB-6: Procurement & Substitutes
CREATE TABLE IF NOT EXISTS supplier_parts (
    mpn          TEXT NOT NULL,
    supplier     TEXT NOT NULL,  -- "LCSC" | "DigiKey" | "Mouser"
    sku          TEXT NOT NULL,
    unit_price_usd REAL,
    moq          INTEGER DEFAULT 1,
    stock_qty    INTEGER DEFAULT 0,
    url          TEXT    DEFAULT '',
    last_seen    TEXT    DEFAULT '',  -- ISO date YYYY-MM-DD
    PRIMARY KEY (mpn, supplier)
);

CREATE TABLE IF NOT EXISTS component_substitutes (
    primary_mpn     TEXT NOT NULL,
    substitute_mpn  TEXT NOT NULL,
    reason          TEXT DEFAULT 'functional-equiv',  -- "pin-compatible"|"functional-equiv"|"drop-in"
    confidence      REAL DEFAULT 0.5,
    verified        INTEGER DEFAULT 0,
    notes           TEXT DEFAULT '',
    PRIMARY KEY (primary_mpn, substitute_mpn)
);
"""


_ADDITIVE_COLUMNS: list[tuple[str, str]] = [
    # (column_name, column_definition)  — DB-2 additions
    ("family",           "TEXT DEFAULT ''"),
    ("series",           "TEXT DEFAULT ''"),
    ("vdd_min",          "REAL"),
    ("vdd_max",          "REAL"),
    ("vdd_typ",          "REAL"),
    ("abs_max_vdd",      "REAL"),
    ("i_active_max_ma",  "REAL"),
    ("i_sleep_ua",       "REAL"),
    ("temp_min_c",       "REAL"),
    ("temp_max_c",       "REAL"),
    ("is_5v_tolerant",   "INTEGER DEFAULT 0"),
    # DB-4 additions
    ("component_state",  "TEXT DEFAULT 'released'"),
    ("agent_confidence", "REAL DEFAULT 1.0"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    """Add new columns to an existing database (idempotent, additive only)."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(components)")}
    for col_name, col_def in _ADDITIVE_COLUMNS:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE components ADD COLUMN {col_name} {col_def}")


def _connect(db_path: Path = _DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    _migrate(conn)
    return conn


def _row_to_entry(row: sqlite3.Row, interfaces: list[str], tags: list[str]) -> ComponentEntry:
    keys = row.keys()
    return {  # type: ignore[return-value]
        "mpn": row["mpn"],
        "manufacturer": row["manufacturer"] or "",
        "name": row["name"] or "",
        "category": row["category"] or "",
        "sub_type": row["sub_type"] or "",
        "family": row["family"] if "family" in keys else "",
        "series": row["series"] if "series" in keys else "",
        "interface_types": interfaces,
        "package": row["package"] or "",
        "mounting": row["mounting"] or "smd",
        "pin_count": row["pin_count"] or 0,
        "description": row["description"] or "",
        "known_i2c_addresses": json.loads(row["known_i2c_addresses"] or "[]"),
        "i2c_address_selectable": bool(row["i2c_address_selectable"]),
        "init_contract_coverage": bool(row["init_contract_coverage"]),
        "init_contract_template": json.loads(row["init_contract_template"] or "{}"),
        "electrical_ratings": json.loads(row["electrical_ratings"] or "{}"),
        "timing_caps": json.loads(row["timing_caps"] or "{}"),
        "capabilities": json.loads(row["capabilities"] or "{}"),
        "unit_cost_usd": row["unit_cost_usd"] or 0.0,
        "datasheet_url": row["datasheet_url"] or "",
        "status": row["status"] or "active",
        "library_support": json.loads(row["library_support"] or "[]"),
        "tags": tags,
        "component_state": row["component_state"] if "component_state" in keys else "released",
    }


def _fetch_one(conn: sqlite3.Connection, mpn: str) -> ComponentEntry | None:
    row = conn.execute("SELECT * FROM components WHERE mpn = ?", (mpn,)).fetchone()
    if row is None:
        return None
    ifaces = [r[0] for r in conn.execute(
        "SELECT interface_type FROM component_interfaces WHERE mpn = ?", (mpn,))]
    tags = [r[0] for r in conn.execute(
        "SELECT tag FROM component_tags WHERE mpn = ?", (mpn,))]
    return _row_to_entry(row, ifaces, tags)


def _fetch_many(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[ComponentEntry]:
    result = []
    for row in rows:
        mpn = row["mpn"]
        ifaces = [r[0] for r in conn.execute(
            "SELECT interface_type FROM component_interfaces WHERE mpn = ?", (mpn,))]
        tags = [r[0] for r in conn.execute(
            "SELECT tag FROM component_tags WHERE mpn = ?", (mpn,))]
        result.append(_row_to_entry(row, ifaces, tags))
    return result


# ---------------------------------------------------------------------------
# SQL for insert/replace
# ---------------------------------------------------------------------------

_UPSERT_SQL = """
    INSERT OR REPLACE INTO components
      (mpn, manufacturer, name, category, sub_type, family, series,
       package, mounting, pin_count,
       description, known_i2c_addresses, i2c_address_selectable,
       init_contract_coverage, init_contract_template,
       electrical_ratings, timing_caps, capabilities,
       unit_cost_usd, datasheet_url, status, library_support, source,
       vdd_min, vdd_max, vdd_typ, abs_max_vdd,
       i_active_max_ma, i_sleep_ua, temp_min_c, temp_max_c, is_5v_tolerant,
       component_state, agent_confidence)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""


def _entry_to_row(entry: ComponentEntry, source: str,
                  component_state: str = "released",
                  agent_confidence: float = 1.0) -> tuple:
    er: dict = entry.get("electrical_ratings", {}) or {}
    vdd_min = entry.get("vdd_min") or er.get("vdd_min")
    vdd_max = entry.get("vdd_max") or er.get("vdd_max")
    # vdd_typ: midpoint if not explicit
    vdd_typ = er.get("io_voltage_nominal") or (
        round((vdd_min + vdd_max) / 2, 3) if vdd_min and vdd_max else None
    )
    return (
        entry.get("mpn", ""),
        entry.get("manufacturer", ""),
        entry.get("name", ""),
        entry.get("category", ""),
        entry.get("sub_type", ""),
        entry.get("family", ""),
        entry.get("series", ""),
        entry.get("package", ""),
        entry.get("mounting", "smd"),
        entry.get("pin_count", 0),
        entry.get("description", ""),
        json.dumps(entry.get("known_i2c_addresses", [])),
        int(entry.get("i2c_address_selectable", False)),
        int(entry.get("init_contract_coverage", False)),
        json.dumps(entry.get("init_contract_template", {})),
        json.dumps(entry.get("electrical_ratings", {})),
        json.dumps(entry.get("timing_caps", {})),
        json.dumps(entry.get("capabilities", {})),
        entry.get("unit_cost_usd"),
        entry.get("datasheet_url", ""),
        entry.get("status", "active"),
        json.dumps(entry.get("library_support", [])),
        source,
        # DB-2 flat columns
        vdd_min,
        vdd_max,
        vdd_typ,
        entry.get("abs_max_vdd") or er.get("abs_max_voltage"),
        entry.get("i_active_max_ma") or er.get("current_draw_max_ma"),
        entry.get("i_sleep_ua") or er.get("sleep_current_ua"),
        entry.get("temp_min_c") or er.get("temp_min_c"),
        entry.get("temp_max_c") or er.get("temp_max_c"),
        int(er.get("is_5v_tolerant") or entry.get("is_5v_tolerant") or False),
        # DB-4 state
        component_state,
        agent_confidence,
    )


# ---------------------------------------------------------------------------
# Public write API
# ---------------------------------------------------------------------------

def upsert(entry: ComponentEntry, source: str = "builtin",
           db_path: Path = _DB_PATH) -> None:
    """Insert or replace a single component entry."""
    conn = _connect(db_path)
    with conn:
        conn.execute(_UPSERT_SQL, _entry_to_row(entry, source))
        mpn = entry["mpn"]
        conn.execute("DELETE FROM component_interfaces WHERE mpn = ?", (mpn,))
        for iface in entry.get("interface_types", []):
            conn.execute("INSERT OR IGNORE INTO component_interfaces VALUES (?,?)", (mpn, iface))
        conn.execute("DELETE FROM component_tags WHERE mpn = ?", (mpn,))
        for tag in entry.get("tags", []):
            conn.execute("INSERT OR IGNORE INTO component_tags VALUES (?,?)", (mpn, tag))
    conn.close()


def upsert_many(entries: list[ComponentEntry], source: str = "builtin",
                db_path: Path = _DB_PATH) -> None:
    """Bulk-insert/replace — single transaction, much faster than repeated upsert()."""
    conn = _connect(db_path)
    with conn:
        for entry in entries:
            conn.execute(_UPSERT_SQL, _entry_to_row(entry, source))
            mpn = entry["mpn"]
            conn.execute("DELETE FROM component_interfaces WHERE mpn = ?", (mpn,))
            for iface in entry.get("interface_types", []):
                conn.execute("INSERT OR IGNORE INTO component_interfaces VALUES (?,?)", (mpn, iface))
            conn.execute("DELETE FROM component_tags WHERE mpn = ?", (mpn,))
            for tag in entry.get("tags", []):
                conn.execute("INSERT OR IGNORE INTO component_tags VALUES (?,?)", (mpn, tag))
    conn.close()


# ---------------------------------------------------------------------------
# Public read API  (mirrors the old list-based helpers)
# ---------------------------------------------------------------------------

def get_all(db_path: Path = _DB_PATH) -> list[ComponentEntry]:
    conn = _connect(db_path)
    rows = conn.execute("SELECT * FROM components ORDER BY category, mpn").fetchall()
    result = _fetch_many(conn, rows)
    conn.close()
    return result


def find_by_mpn(mpn: str, db_path: Path = _DB_PATH) -> ComponentEntry | None:
    conn = _connect(db_path)
    result = _fetch_one(conn, mpn)
    conn.close()
    return result


def find_by_category(category: str, db_path: Path = _DB_PATH) -> list[ComponentEntry]:
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT * FROM components WHERE category = ? ORDER BY mpn", (category,)
    ).fetchall()
    result = _fetch_many(conn, rows)
    conn.close()
    return result


def find_by_sub_type(sub_type: str, db_path: Path = _DB_PATH) -> list[ComponentEntry]:
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT * FROM components WHERE sub_type = ? ORDER BY mpn", (sub_type,)
    ).fetchall()
    result = _fetch_many(conn, rows)
    conn.close()
    return result


def find_by_interface(interface: str, db_path: Path = _DB_PATH) -> list[ComponentEntry]:
    conn = _connect(db_path)
    rows = conn.execute("""
        SELECT c.* FROM components c
        JOIN component_interfaces ci ON c.mpn = ci.mpn
        WHERE ci.interface_type = ?
        ORDER BY c.mpn
    """, (interface,)).fetchall()
    result = _fetch_many(conn, rows)
    conn.close()
    return result


def find_by_tag(tag: str, db_path: Path = _DB_PATH) -> list[ComponentEntry]:
    conn = _connect(db_path)
    rows = conn.execute("""
        SELECT c.* FROM components c
        JOIN component_tags ct ON c.mpn = ct.mpn
        WHERE ct.tag = ?
        ORDER BY c.mpn
    """, (tag,)).fetchall()
    result = _fetch_many(conn, rows)
    conn.close()
    return result


def search(query: str, limit: int = 20, db_path: Path = _DB_PATH) -> list[ComponentEntry]:
    """Full-text search across MPN, name and description."""
    conn = _connect(db_path)
    rows = conn.execute("""
        SELECT c.* FROM components c
        JOIN components_fts fts ON c.rowid = fts.rowid
        WHERE components_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (query, limit)).fetchall()
    result = _fetch_many(conn, rows)
    conn.close()
    return result


def count(db_path: Path = _DB_PATH) -> int:
    conn = _connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM components").fetchone()[0]
    conn.close()
    return n


# ---------------------------------------------------------------------------
# DB-2: Range / filter queries on flat columns
# ---------------------------------------------------------------------------

def find_by_voltage_range(
    supply_v: float,
    db_path: Path = _DB_PATH,
) -> list[ComponentEntry]:
    """Return components that operate at `supply_v` (vdd_min ≤ supply_v ≤ vdd_max)."""
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT * FROM components WHERE vdd_min <= ? AND vdd_max >= ? ORDER BY mpn",
        (supply_v, supply_v),
    ).fetchall()
    result = _fetch_many(conn, rows)
    conn.close()
    return result


def find_by_vdd_max(max_supply_v: float, db_path: Path = _DB_PATH) -> list[ComponentEntry]:
    """Return components whose max supply voltage does not exceed `max_supply_v`."""
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT * FROM components WHERE vdd_max IS NOT NULL AND vdd_max <= ? ORDER BY vdd_max, mpn",
        (max_supply_v,),
    ).fetchall()
    result = _fetch_many(conn, rows)
    conn.close()
    return result


def find_by_temp_range(
    min_c: float,
    max_c: float,
    db_path: Path = _DB_PATH,
) -> list[ComponentEntry]:
    """Return components that cover the full temperature range [min_c, max_c]."""
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT * FROM components WHERE temp_min_c <= ? AND temp_max_c >= ? ORDER BY mpn",
        (min_c, max_c),
    ).fetchall()
    result = _fetch_many(conn, rows)
    conn.close()
    return result


def find_5v_tolerant(db_path: Path = _DB_PATH) -> list[ComponentEntry]:
    """Return components with 5V-tolerant I/O."""
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT * FROM components WHERE is_5v_tolerant = 1 ORDER BY mpn"
    ).fetchall()
    result = _fetch_many(conn, rows)
    conn.close()
    return result


def find_by_family(family: str, db_path: Path = _DB_PATH) -> list[ComponentEntry]:
    """Return all variants of a component family (case-insensitive prefix match)."""
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT * FROM components WHERE family = ? ORDER BY mpn",
        (family,),
    ).fetchall()
    result = _fetch_many(conn, rows)
    conn.close()
    return result


def find_low_power(
    i_active_max_ma: float,
    db_path: Path = _DB_PATH,
) -> list[ComponentEntry]:
    """Return components with active current ≤ `i_active_max_ma` mA."""
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT * FROM components WHERE i_active_max_ma IS NOT NULL AND i_active_max_ma <= ?"
        " ORDER BY i_active_max_ma, mpn",
        (i_active_max_ma,),
    ).fetchall()
    result = _fetch_many(conn, rows)
    conn.close()
    return result


# ---------------------------------------------------------------------------
# DB-4: Draft state management
# ---------------------------------------------------------------------------

ComponentState = str  # "draft" | "validated" | "verified" | "released"
_VALID_STATES = frozenset({"draft", "validated", "verified", "released"})


def upsert_draft(
    entry: ComponentEntry,
    confidence: float,
    source: str = "agent",
    db_path: Path = _DB_PATH,
) -> None:
    """Insert a component found by the Knowledge Agent as a draft.

    ``confidence`` is the agent's confidence score (0.0–1.0).
    Only called when confidence >= the auto-promote threshold (0.75).
    The draft can later be promoted to 'validated' via validate_draft().
    """
    conn = _connect(db_path)
    with conn:
        conn.execute(_UPSERT_SQL, _entry_to_row(
            entry, source, component_state="draft", agent_confidence=confidence,
        ))
        mpn = entry["mpn"]
        conn.execute("DELETE FROM component_interfaces WHERE mpn = ?", (mpn,))
        for iface in entry.get("interface_types", []):
            conn.execute("INSERT OR IGNORE INTO component_interfaces VALUES (?,?)", (mpn, iface))
        conn.execute("DELETE FROM component_tags WHERE mpn = ?", (mpn,))
        for tag in entry.get("tags", []):
            conn.execute("INSERT OR IGNORE INTO component_tags VALUES (?,?)", (mpn, tag))
    conn.close()


def list_drafts(db_path: Path = _DB_PATH) -> list[ComponentEntry]:
    """Return all components in 'draft' state (agent-found, not yet validated)."""
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT * FROM components WHERE component_state = 'draft' ORDER BY mpn"
    ).fetchall()
    result = _fetch_many(conn, rows)
    conn.close()
    return result


def validate_draft(
    mpn: str,
    new_state: ComponentState = "validated",
    db_path: Path = _DB_PATH,
) -> list[str]:
    """Validate a draft component: check required fields, promote to new_state.

    Returns list of validation errors (empty = promoted successfully).

    Validation rules:
      - mpn must exist and be in 'draft' or 'validated' state
      - manufacturer must be non-empty
      - category must be one of the known categories
      - interface_types must be non-empty
      - electrical_ratings must have vdd_min or vdd_max
    """
    if new_state not in _VALID_STATES:
        return [f"Invalid state '{new_state}'. Must be one of {sorted(_VALID_STATES)}"]

    entry = find_by_mpn(mpn, db_path=db_path)
    if entry is None:
        return [f"Component '{mpn}' not found in DB"]

    current_state = entry.get("component_state", "released")
    if current_state not in ("draft", "validated"):
        return [f"Component '{mpn}' is in state '{current_state}' — only draft/validated can be promoted"]

    errors: list[str] = []
    if not entry.get("manufacturer"):
        errors.append("manufacturer is missing")
    known_categories = {"mcu", "sensor", "display", "actuator", "memory", "power", "comms", "other"}
    if entry.get("category") not in known_categories:
        errors.append(f"category '{entry.get('category')}' is unknown (expected: {sorted(known_categories)})")
    if not entry.get("interface_types"):
        errors.append("interface_types is empty — must have at least one")
    er = entry.get("electrical_ratings") or {}
    if not er.get("vdd_min") and not er.get("vdd_max"):
        errors.append("electrical_ratings: vdd_min and vdd_max are both missing")

    if errors:
        return errors

    conn = _connect(db_path)
    with conn:
        conn.execute(
            "UPDATE components SET component_state = ? WHERE mpn = ?",
            (new_state, mpn),
        )
    conn.close()
    return []


def find_by_state(state: ComponentState, db_path: Path = _DB_PATH) -> list[ComponentEntry]:
    """Return all components in the given lifecycle state."""
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT * FROM components WHERE component_state = ? ORDER BY mpn",
        (state,),
    ).fetchall()
    result = _fetch_many(conn, rows)
    conn.close()
    return result


# ---------------------------------------------------------------------------
# DB initialisation / seeding
# ---------------------------------------------------------------------------

def ensure_seeded(db_path: Path = _DB_PATH) -> None:
    """Seed the DB from seed/ package if it is empty."""
    conn = _connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM components").fetchone()[0]
    conn.close()
    if n == 0:
        _seed(db_path)


def _seed(db_path: Path = _DB_PATH) -> None:
    # Primary source: canonical components.py (145+ entries)
    from knowledge.components import COMPONENTS as _canonical  # lazy import avoids circular
    # Secondary source: modular seed/ packages (may contain newer additions)
    from knowledge.seed import ALL_COMPONENTS as _seed_comps
    # Merge: canonical first, then seed additions by MPN
    seen: set[str] = set()
    merged: list[dict] = []
    for c in _canonical:
        merged.append(c)
        seen.add(c.get("mpn", ""))
    for c in _seed_comps:
        mpn = c.get("mpn", "")
        if mpn not in seen:
            merged.append(c)
            seen.add(mpn)
    upsert_many(merged, source="builtin", db_path=db_path)


def rebuild(db_path: Path = _DB_PATH) -> None:
    """Drop and re-seed the DB from seed/ — useful after adding new entries."""
    if db_path.exists():
        db_path.unlink()
    # Also clean up WAL files
    for suffix in ("-shm", "-wal"):
        p = db_path.parent / (db_path.name + suffix)
        if p.exists():
            p.unlink()
    _seed(db_path)


# ---------------------------------------------------------------------------
# DB-6: Procurement — supplier_parts
# ---------------------------------------------------------------------------

SupplierPart = dict  # keys: mpn, supplier, sku, unit_price_usd, moq, stock_qty, url, last_seen


def upsert_supplier_part(
    mpn: str,
    supplier: str,
    sku: str,
    unit_price_usd: float | None = None,
    moq: int = 1,
    stock_qty: int = 0,
    url: str = "",
    last_seen: str = "",
    db_path: Path = _DB_PATH,
) -> None:
    """Insert or replace a supplier listing for a component."""
    conn = _connect(db_path)
    with conn:
        conn.execute(
            """INSERT OR REPLACE INTO supplier_parts
               (mpn, supplier, sku, unit_price_usd, moq, stock_qty, url, last_seen)
               VALUES (?,?,?,?,?,?,?,?)""",
            (mpn, supplier, sku, unit_price_usd, moq, stock_qty, url, last_seen),
        )
    conn.close()


def upsert_supplier_parts_bulk(
    parts: list[SupplierPart],
    db_path: Path = _DB_PATH,
) -> None:
    """Bulk insert supplier parts — single transaction."""
    conn = _connect(db_path)
    with conn:
        for p in parts:
            conn.execute(
                """INSERT OR REPLACE INTO supplier_parts
                   (mpn, supplier, sku, unit_price_usd, moq, stock_qty, url, last_seen)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    p["mpn"], p["supplier"], p["sku"],
                    p.get("unit_price_usd"), p.get("moq", 1),
                    p.get("stock_qty", 0), p.get("url", ""), p.get("last_seen", ""),
                ),
            )
    conn.close()


def find_supplier_parts(mpn: str, db_path: Path = _DB_PATH) -> list[SupplierPart]:
    """Return all supplier listings for a given MPN, sorted by price."""
    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT mpn, supplier, sku, unit_price_usd, moq, stock_qty, url, last_seen
           FROM supplier_parts WHERE mpn = ? ORDER BY unit_price_usd ASC""",
        (mpn,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_best_price(mpn: str, db_path: Path = _DB_PATH) -> SupplierPart | None:
    """Return the cheapest supplier listing for an MPN (or None if no data)."""
    parts = find_supplier_parts(mpn, db_path=db_path)
    if not parts:
        return None
    # Prefer parts with a price; fallback to first
    priced = [p for p in parts if p.get("unit_price_usd") is not None]
    return priced[0] if priced else parts[0]


def find_by_supplier(supplier: str, db_path: Path = _DB_PATH) -> list[SupplierPart]:
    """Return all parts available at a given supplier."""
    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT mpn, supplier, sku, unit_price_usd, moq, stock_qty, url, last_seen
           FROM supplier_parts WHERE supplier = ? ORDER BY mpn""",
        (supplier,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# DB-6: Substitutes — component_substitutes
# ---------------------------------------------------------------------------

SubstituteRecord = dict  # keys: primary_mpn, substitute_mpn, reason, confidence, verified, notes


def upsert_substitute(
    primary_mpn: str,
    substitute_mpn: str,
    reason: str = "functional-equiv",
    confidence: float = 0.5,
    verified: bool = False,
    notes: str = "",
    db_path: Path = _DB_PATH,
) -> None:
    """Register a substitute MPN for a primary component."""
    conn = _connect(db_path)
    with conn:
        conn.execute(
            """INSERT OR REPLACE INTO component_substitutes
               (primary_mpn, substitute_mpn, reason, confidence, verified, notes)
               VALUES (?,?,?,?,?,?)""",
            (primary_mpn, substitute_mpn, reason, confidence, int(verified), notes),
        )
    conn.close()


def upsert_substitutes_bulk(
    records: list[SubstituteRecord],
    db_path: Path = _DB_PATH,
) -> None:
    """Bulk insert substitute records — single transaction."""
    conn = _connect(db_path)
    with conn:
        for r in records:
            conn.execute(
                """INSERT OR REPLACE INTO component_substitutes
                   (primary_mpn, substitute_mpn, reason, confidence, verified, notes)
                   VALUES (?,?,?,?,?,?)""",
                (
                    r["primary_mpn"], r["substitute_mpn"],
                    r.get("reason", "functional-equiv"),
                    r.get("confidence", 0.5),
                    int(r.get("verified", False)),
                    r.get("notes", ""),
                ),
            )
    conn.close()


def find_substitutes(mpn: str, db_path: Path = _DB_PATH) -> list[SubstituteRecord]:
    """Return all known substitutes for a primary MPN, sorted by confidence desc."""
    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT primary_mpn, substitute_mpn, reason, confidence, verified, notes
           FROM component_substitutes WHERE primary_mpn = ?
           ORDER BY confidence DESC, verified DESC""",
        (mpn,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def find_primary_for(substitute_mpn: str, db_path: Path = _DB_PATH) -> list[SubstituteRecord]:
    """Return all primary MPNs for which this MPN is listed as a substitute."""
    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT primary_mpn, substitute_mpn, reason, confidence, verified, notes
           FROM component_substitutes WHERE substitute_mpn = ?
           ORDER BY confidence DESC""",
        (substitute_mpn,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def find_verified_substitutes(db_path: Path = _DB_PATH) -> list[SubstituteRecord]:
    """Return all verified substitute relationships."""
    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT primary_mpn, substitute_mpn, reason, confidence, verified, notes
           FROM component_substitutes WHERE verified = 1
           ORDER BY primary_mpn, confidence DESC""",
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
