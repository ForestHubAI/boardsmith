# SPDX-License-Identifier: AGPL-3.0-or-later
"""Built-in component knowledge database — thin wrapper around shared/knowledge.

All component data lives in shared/knowledge/components.py.
This module re-exports the shared API so that existing synthesizer code
continues to work without modification.
"""
from __future__ import annotations

# Re-export TypedDicts from shared schema
from knowledge.schema import (  # noqa: F401
    ComponentEntry,
    ElectricalRatings,
    InitContractTemplate,
    TimingCaps,
)

# Re-export the full component list and lookup functions from shared components
from knowledge.components import (  # noqa: F401
    COMPONENTS as BUILTIN_DB,
    find_by_category,
    find_by_interface,
    find_by_mpn,
    get_all,
)
