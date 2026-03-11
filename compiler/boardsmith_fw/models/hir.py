# SPDX-License-Identifier: AGPL-3.0-or-later
"""HIR compatibility shim — re-exports shared HIR v1.1.0 with v1.0 aliases.

The canonical HIR model lives in `shared/models/hir.py` (v1.1.0).
This module re-exports everything from there and provides backward-compatible
aliases for the v1.0 class names used throughout the compiler.

v1.0 → v1.1.0 renames:
  VoltageLevel     → Voltage
  CurrentSpec      → CurrentDraw
  RegisterWrite    → RegWrite
  RegisterRead     → RegRead
  InitPhaseSpec    → InitPhase  (the model)
  InitPhase        → InitPhaseTag  (the enum)
  ConstraintSeverity → Severity
"""
from __future__ import annotations

import sys
import os

# Allow importing from the shared package when running inside the monorepo.
# If shared is not on sys.path, add the monorepo root.
_monorepo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
_shared_path = os.path.join(_monorepo_root, "shared")
if _shared_path not in sys.path and os.path.isdir(_shared_path):
    sys.path.insert(0, _shared_path)

try:
    from models.hir import (  # type: ignore[import]
        # Core
        HIR,
        HIRMetadata,
        # Enums
        SourceType,
        ComponentRole,
        InterfaceType,
        BusType,
        ConstraintCategory,
        ConstraintStatus,
        Severity,
        InitPhaseTag,
        # Primitives
        Provenance,
        Voltage,
        CurrentDraw,
        # Components
        Pin,
        Component,
        # Nets
        NetPin,
        Net,
        # Buses
        PinMapping,
        Bus,
        # Bus contracts
        I2CSpec,
        SPISpec,
        UARTSpec,
        BusContract,
        # Electrical
        ElectricalSpec,
        # Init contracts
        RegWrite,
        RegRead,
        InitPhase,
        InitContract,
        # Power
        PowerRail,
        PowerDependency,
        PowerSequence,
        # Constraints
        Constraint,
        # BOM
        BOMEntry,
        # Confidence
        ConfidenceSubscores,
        Confidence,
    )
except ImportError:
    # Fallback: use the synthesizer's copy of the HIR models
    # (happens when running compiler standalone without the monorepo)
    from boardsmith_fw.models._hir_v110 import *  # type: ignore[import]

# ---------------------------------------------------------------------------
# Backward-compatible aliases (v1.0 names → v1.1.0 names)
# ---------------------------------------------------------------------------

# Voltage
VoltageLevel = Voltage

# Current
CurrentSpec = CurrentDraw

# Register ops
RegisterWrite = RegWrite
RegisterRead = RegRead

# InitPhase naming collision between v1.0 and v1.1.0:
#   v1.0: InitPhase (enum: RESET/CONFIGURE/CALIBRATE/ENABLE/VERIFY), InitPhaseSpec (model)
#   v1.1: InitPhaseTag (enum: reset/configure/...), InitPhase (model)
#
# Compiler code uses InitPhase.RESET (uppercase) → define a compat enum with uppercase attrs.
# InitPhaseSpec → alias for the v1.1.0 model (called InitPhase in v1.1.0).

from enum import Enum as _Enum

_InitPhaseModel = InitPhase      # save the v1.1.0 model before redefining the name
InitPhaseSpec = _InitPhaseModel  # v1.0 "InitPhaseSpec" → v1.1.0 "InitPhase" model


class InitPhase(str, _Enum):    # type: ignore[no-redef]
    """v1.0-compatible InitPhase enum with UPPERCASE attribute names.

    Values match the v1.1.0 string values so cross-version comparisons work:
        InitPhase.RESET == "reset"  →  True
    """
    RESET = "reset"
    CONFIGURE = "configure"
    CALIBRATE = "calibrate"
    ENABLE = "enable"
    VERIFY = "verify"

# Constraint severity
ConstraintSeverity = Severity

__all__ = [
    # v1.1.0 canonical names
    "HIR", "HIRMetadata", "SourceType", "ComponentRole", "InterfaceType",
    "BusType", "ConstraintCategory", "ConstraintStatus", "Severity",
    "InitPhaseTag", "Provenance", "Voltage", "CurrentDraw",
    "Pin", "Component", "NetPin", "Net", "PinMapping", "Bus",
    "I2CSpec", "SPISpec", "UARTSpec", "BusContract", "ElectricalSpec",
    "RegWrite", "RegRead", "InitPhase", "InitContract",
    "PowerRail", "PowerDependency", "PowerSequence",
    "Constraint", "BOMEntry", "ConfidenceSubscores", "Confidence",
    # v1.0 aliases
    "VoltageLevel", "CurrentSpec", "RegisterWrite", "RegisterRead",
    "InitPhaseSpec", "ConstraintSeverity",
]
