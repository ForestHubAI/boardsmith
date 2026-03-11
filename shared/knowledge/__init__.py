# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared component knowledge database — used by both compiler and synthesizer."""
from knowledge import db as _db
from knowledge.schema import ComponentEntry, ElectricalRatings, TimingCaps, InitContractTemplate

# Ensure the SQLite DB is seeded on first import
_db.ensure_seeded()

# Public API — mirrors the old list-based interface; all calls go to SQLite
get_all = _db.get_all
find_by_mpn = _db.find_by_mpn
find_by_category = _db.find_by_category
find_by_interface = _db.find_by_interface
find_by_tag = _db.find_by_tag
search = _db.search
upsert = _db.upsert
upsert_many = _db.upsert_many
count = _db.count
rebuild = _db.rebuild

# Backwards-compat alias — lazy-evaluated so it doesn't hammer the DB every import
def _get_components():
    return _db.get_all()

# COMPONENTS kept for direct list access in legacy callers
COMPONENTS = _db.get_all()

__all__ = [
    "COMPONENTS",
    "get_all",
    "find_by_mpn",
    "find_by_category",
    "find_by_interface",
    "find_by_tag",
    "search",
    "upsert",
    "upsert_many",
    "count",
    "rebuild",
    "ComponentEntry",
    "ElectricalRatings",
    "TimingCaps",
    "InitContractTemplate",
]
