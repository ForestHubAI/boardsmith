# SPDX-License-Identifier: AGPL-3.0-or-later
"""HIR import-shim — re-exports shared HIR v1.1.0.

The canonical HIR model lives in ``shared/models/hir.py`` (v1.1.0).
This module re-exports everything from there so that existing code using
``from synth_core.models.hir import ...`` continues to work without change.

**Phase 15 change** — previously a 394-line standalone copy.
Now an import-shim, identical in approach to ``compiler/boardsmith_fw/models/hir.py``.

The synthesizer test suite and CLI both add ``shared/`` to sys.path, so the
primary import path always succeeds inside the monorepo.
"""
from __future__ import annotations

import os
import sys

# Ensure shared/ is on sys.path so `from models.hir import ...` resolves.
# synthesizer/boardsmith_fw/models/hir.py → up 4 dirs → monorepo root → shared/
_monorepo_root = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
    )
)
_shared_path = os.path.join(_monorepo_root, "shared")
if _shared_path not in sys.path and os.path.isdir(_shared_path):
    sys.path.insert(0, _shared_path)

from models.hir import (  # type: ignore[import]  # noqa: E402
    HIR,
    HIRMetadata,
    SourceType,
    ComponentRole,
    InterfaceType,
    BusType,
    ConstraintCategory,
    ConstraintStatus,
    Severity,
    InitPhaseTag,
    Provenance,
    Voltage,
    CurrentDraw,
    Pin,
    Component,
    NetPin,
    Net,
    PinMapping,
    Bus,
    I2CSpec,
    SPISpec,
    UARTSpec,
    BusContract,
    ElectricalSpec,
    RegWrite,
    RegRead,
    InitPhase,
    InitContract,
    PowerRail,
    PowerDependency,
    PowerSequence,
    Constraint,
    BOMEntry,
    ConfidenceSubscores,
    Confidence,
)

__all__ = [
    "HIR", "HIRMetadata", "SourceType", "ComponentRole", "InterfaceType",
    "BusType", "ConstraintCategory", "ConstraintStatus", "Severity",
    "InitPhaseTag", "Provenance", "Voltage", "CurrentDraw",
    "Pin", "Component", "NetPin", "Net", "PinMapping", "Bus",
    "I2CSpec", "SPISpec", "UARTSpec", "BusContract", "ElectricalSpec",
    "RegWrite", "RegRead", "InitPhase", "InitContract",
    "PowerRail", "PowerDependency", "PowerSequence",
    "Constraint", "BOMEntry", "ConfidenceSubscores", "Confidence",
]
