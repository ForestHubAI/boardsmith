# SPDX-License-Identifier: AGPL-3.0-or-later
"""Knowledge resolver — connects HardwareGraph components to ComponentKnowledge.

Resolution order:
1. Built-in DB (instant, verified)
2. Local cache (~/.boardsmith-fw/knowledge/)
3. Datasheet extraction (slow, requires PDF download)
4. LLM extraction (optional, requires API key)
"""

from __future__ import annotations

import re
from pathlib import Path

from boardsmith_fw.knowledge.builtin_db import lookup_builtin
from boardsmith_fw.models.component_knowledge import ComponentKnowledge
from boardsmith_fw.models.hardware_graph import Component, HardwareGraph


def resolve_knowledge(
    graph: HardwareGraph,
    cache_dir: Path | None = None,
) -> list[ComponentKnowledge]:
    """Resolve ComponentKnowledge for all non-passive components in the graph.

    Returns a list of ComponentKnowledge objects, one per resolvable component.
    """
    if cache_dir is None:
        cache_dir = Path.home() / ".boardsmith-fw" / "knowledge"

    results: list[ComponentKnowledge] = []

    for comp in graph.components:
        # Skip passives (R, C, L, D)
        if comp.name and comp.name[0].upper() in ("R", "C", "L", "D"):
            continue

        knowledge = _resolve_single(comp, cache_dir)
        if knowledge:
            knowledge.component_id = comp.id
            results.append(knowledge)

    return results


def _resolve_single(comp: Component, cache_dir: Path) -> ComponentKnowledge | None:
    """Try to resolve knowledge for a single component."""
    mpn = comp.mpn or comp.value or ""
    if not mpn:
        return None

    # 1. Built-in DB
    builtin = lookup_builtin(mpn)
    if builtin:
        builtin.component_id = comp.id
        return builtin

    # 2. Local cache
    cached = _load_from_cache(mpn, cache_dir)
    if cached:
        cached.component_id = comp.id
        return cached

    # 3. Minimal knowledge from schematic info alone
    return _minimal_knowledge(comp)


def _load_from_cache(mpn: str, cache_dir: Path) -> ComponentKnowledge | None:
    """Try to load cached knowledge JSON for a given MPN."""
    if not cache_dir.exists():
        return None

    safe_mpn = re.sub(r"[^a-zA-Z0-9_-]", "_", mpn)[:64]
    candidates = [
        cache_dir / f"{safe_mpn}.json",
        cache_dir / f"{mpn.upper()}.json",
        cache_dir / f"{mpn.lower()}.json",
    ]

    for path in candidates:
        if path.exists():
            try:
                return ComponentKnowledge.model_validate_json(path.read_text())
            except Exception:
                continue

    return None


def save_to_cache(knowledge: ComponentKnowledge, cache_dir: Path) -> Path:
    """Save knowledge to the local cache. Returns the file path."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_mpn = re.sub(r"[^a-zA-Z0-9_-]", "_", knowledge.mpn or knowledge.name)[:64]
    path = cache_dir / f"{safe_mpn}.json"
    path.write_text(knowledge.model_dump_json(indent=2))
    return path


def _minimal_knowledge(comp: Component) -> ComponentKnowledge | None:
    """Create minimal knowledge from schematic component info."""
    from boardsmith_fw.models.component_knowledge import InterfaceType

    mpn = comp.mpn or comp.value or ""
    if not mpn:
        return None

    pin_names = {p.name.upper() for p in comp.pins}

    interface = InterfaceType.OTHER
    if {"SDA", "SCL"} & pin_names:
        interface = InterfaceType.I2C
    elif {"MOSI", "MISO", "SCK"} & pin_names:
        interface = InterfaceType.SPI
    elif {"TX", "RX", "TXD", "RXD"} & pin_names:
        interface = InterfaceType.UART

    return ComponentKnowledge(
        component_id=comp.id,
        name=mpn,
        mpn=mpn,
        manufacturer=comp.manufacturer,
        interface=interface,
        notes=["Minimal knowledge from schematic — no datasheet data available"],
    )
