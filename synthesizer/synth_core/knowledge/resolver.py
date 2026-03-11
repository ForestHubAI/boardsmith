# SPDX-License-Identifier: AGPL-3.0-or-later
"""Knowledge resolution chain: builtin_db → cache → minimal fallback."""
from __future__ import annotations

import json
from pathlib import Path

from synth_core.knowledge.builtin_db import ComponentEntry, get_all, find_by_mpn


_CACHE_DIR = Path.home() / ".boardsmith-fw" / "component_cache"


def _load_cache() -> list[ComponentEntry]:
    """Load components from the local cache directory."""
    if not _CACHE_DIR.exists():
        return []
    entries: list[ComponentEntry] = []
    for path in _CACHE_DIR.glob("*.json"):
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, list):
                entries.extend(data)
            elif isinstance(data, dict):
                entries.append(data)  # type: ignore[arg-type]
        except Exception:
            pass
    return entries


def save_to_cache(entry: ComponentEntry) -> None:
    """Persist a component entry to local cache."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    mpn = str(entry.get("mpn", "unknown")).replace("/", "_")
    path = _CACHE_DIR / f"{mpn}.json"
    with open(path, "w") as f:
        json.dump(entry, f, indent=2)


class KnowledgeResolver:
    """Resolves component knowledge through the priority chain:
    builtin_db → cache → minimal_fallback.
    """

    def __init__(self, extra_dirs: list[Path] | None = None) -> None:
        self._cache: list[ComponentEntry] = _load_cache()
        self._extra: list[ComponentEntry] = []
        if extra_dirs:
            for d in extra_dirs:
                for p in Path(d).glob("*.json"):
                    try:
                        with open(p) as f:
                            data = json.load(f)
                        if isinstance(data, list):
                            self._extra.extend(data)
                        else:
                            self._extra.append(data)  # type: ignore[arg-type]
                    except Exception:
                        pass

    def get_all(self, include_cache: bool = True) -> list[ComponentEntry]:
        entries = list(get_all())
        if include_cache:
            entries.extend(self._cache)
            entries.extend(self._extra)
        # Deduplicate by mpn (builtin takes priority)
        seen: set[str] = set()
        out: list[ComponentEntry] = []
        for e in entries:
            mpn = str(e.get("mpn", "")).upper()
            if mpn and mpn not in seen:
                seen.add(mpn)
                out.append(e)
        return out

    def resolve_mpn(self, mpn: str) -> ComponentEntry | None:
        """Return component entry or None. Priority: builtin → cache → extra."""
        result = find_by_mpn(mpn)
        if result:
            return result
        mpn_up = mpn.upper()
        for pool in (self._cache, self._extra):
            for e in pool:
                if str(e.get("mpn", "")).upper() == mpn_up:
                    return e
        return None

    def query(
        self,
        category: str | None = None,
        interface: str | None = None,
        voltage_range: tuple[float, float] | None = None,
        max_cost: float | None = None,
        temp_range: tuple[float, float] | None = None,
        include_cache: bool = True,
    ) -> list[ComponentEntry]:
        """Filter component catalog by given criteria."""
        entries = self.get_all(include_cache=include_cache)
        results = []
        for e in entries:
            if category and e.get("category") != category:
                continue
            if interface:
                iface_up = interface.upper()
                if iface_up not in [i.upper() for i in e.get("interface_types", [])]:
                    continue
            if voltage_range:
                ratings = e.get("electrical_ratings", {})
                vdd_min = ratings.get("vdd_min", 0.0)
                vdd_max = ratings.get("vdd_max", 99.0)
                req_min, req_max = voltage_range
                if vdd_max < req_min or vdd_min > req_max:
                    continue
            if max_cost is not None:
                cost = e.get("unit_cost_usd", 0.0)
                if cost > max_cost:
                    continue
            if temp_range:
                ratings = e.get("electrical_ratings", {})
                t_min = ratings.get("temp_min_c", -999.0)
                t_max = ratings.get("temp_max_c", 999.0)
                req_t_min, req_t_max = temp_range
                if t_max < req_t_min or t_min > req_t_max:
                    continue
            results.append(e)
        return results
