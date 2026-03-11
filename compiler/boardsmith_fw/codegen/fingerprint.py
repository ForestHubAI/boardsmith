# SPDX-License-Identifier: AGPL-3.0-or-later
"""Incremental regeneration — fingerprint tracking.

Tracks what changed between schematic revisions so only
affected drivers need to be regenerated.

Fingerprints are stored in .boardsmith-fw-state.json in the output directory.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from boardsmith_fw.models.component_knowledge import ComponentKnowledge
from boardsmith_fw.models.hardware_graph import HardwareGraph

STATE_FILE = ".boardsmith-fw-state.json"


def compute_graph_fingerprint(graph: HardwareGraph) -> str:
    """Compute a hash fingerprint for the entire hardware graph."""
    data = graph.model_dump_json(exclude={"metadata", "timestamp"})
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def compute_component_fingerprints(
    graph: HardwareGraph,
    knowledge: list[ComponentKnowledge],
) -> dict[str, str]:
    """Compute per-component fingerprints.

    Each fingerprint captures: component pins, bus connections, knowledge.
    A change in any of these means the driver needs regeneration.
    """
    knowledge_map = {k.component_id: k for k in knowledge}
    fingerprints: dict[str, str] = {}

    for comp in graph.components:
        # Hash component data
        parts: list[str] = [
            comp.id,
            comp.name,
            comp.value or "",
            comp.mpn or "",
        ]

        # Add pin info
        for pin in sorted(comp.pins, key=lambda p: p.name):
            parts.append(f"pin:{pin.name}:{pin.net or ''}")

        # Add bus membership
        for bus in graph.buses:
            if comp.id in bus.slave_component_ids or comp.id == bus.master_component_id:
                parts.append(f"bus:{bus.name}:{bus.type.value}")
                for pm in bus.pin_mapping:
                    parts.append(f"pm:{pm.signal}:{pm.gpio or ''}")

        # Add knowledge hash
        kn = knowledge_map.get(comp.id)
        if kn:
            parts.append(f"kn:{kn.model_dump_json()}")

        combined = "|".join(parts)
        fingerprints[comp.id] = hashlib.sha256(combined.encode()).hexdigest()[:16]

    return fingerprints


def load_state(output_dir: Path) -> dict:
    """Load previous generation state."""
    state_file = output_dir / STATE_FILE
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except Exception:
            return {}
    return {}


def save_state(
    output_dir: Path,
    graph_fingerprint: str,
    component_fingerprints: dict[str, str],
    generated_files: dict[str, str],
) -> None:
    """Save generation state for incremental tracking."""
    state = {
        "graph_fingerprint": graph_fingerprint,
        "component_fingerprints": component_fingerprints,
        "generated_files": generated_files,
    }
    state_file = output_dir / STATE_FILE
    state_file.write_text(json.dumps(state, indent=2))


def diff_fingerprints(
    old: dict[str, str], new: dict[str, str]
) -> tuple[list[str], list[str], list[str]]:
    """Compare fingerprints and return (added, changed, removed) component IDs."""
    old_ids = set(old.keys())
    new_ids = set(new.keys())

    added = sorted(new_ids - old_ids)
    removed = sorted(old_ids - new_ids)
    changed = sorted(
        cid for cid in old_ids & new_ids if old[cid] != new[cid]
    )

    return added, changed, removed
