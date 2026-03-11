# SPDX-License-Identifier: AGPL-3.0-or-later
"""DB-3: Pattern Library schema — Pydantic models for circuit patterns.

A CircuitPattern is a parameterised, reusable subcircuit rule:
  - Trigger condition selects when the pattern applies
  - Parameters define the design variables (with defaults and formulas)
  - OutputComponents describe what passive/active components to add
  - OutputNets describe the connectivity
  - Validations are post-instantiation checks

PatternBundle groups patterns that always apply together (e.g. usb_devboard).
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Parameter
# ---------------------------------------------------------------------------

class PatternParameter(BaseModel):
    """A single design parameter for a circuit pattern."""
    name: str
    type: Literal["float", "int", "str", "bool"]
    default: Any
    unit: str = ""
    description: str = ""
    min: float | None = None
    max: float | None = None
    formula: str = ""   # Python expression to derive this param from others


# ---------------------------------------------------------------------------
# Output component
# ---------------------------------------------------------------------------

class OutputComponent(BaseModel):
    """A component that this pattern instantiates.

    ``value_expr`` is a Python expression evaluated with the pattern parameters
    in scope.  Result must be in SI units (Ω, F, H) for passives.

    Example:
        role="R_pull_sda", value_expr="t_rise_ns * 1e-9 / (0.8473 * bus_cap_pf * 1e-12)"
    """
    role: str               # Unique ID within the pattern, e.g. "R_pull_sda"
    category: str           # "resistor" | "capacitor" | "inductor" | "ic" | "diode" | "fuse"
    value_expr: str = ""    # Python expression → SI value (empty for ICs)
    unit: str = ""          # "Ω" | "F" | "H" | "V"
    package: str = "0402"
    mpn_suggestion: str = ""
    nets: list[str] = Field(default_factory=list)  # net name templates; {bus} substituted
    description: str = ""
    quantity: int = 1       # how many instances (e.g. 2 pullup resistors for I2C)


# ---------------------------------------------------------------------------
# Output net
# ---------------------------------------------------------------------------

class OutputNet(BaseModel):
    """A net produced / used by this pattern."""
    name: str               # template, e.g. "{bus}_SDA_PULL"
    is_power: bool = False
    roles: list[str] = Field(default_factory=list)  # OutputComponent.role values on this net


# ---------------------------------------------------------------------------
# Circuit Pattern
# ---------------------------------------------------------------------------

class CircuitPattern(BaseModel):
    """Formalised, parameterised circuit pattern.

    trigger: Python expression evaluated in the synthesis context.
      Available variables: interface_type, v_supply, v_io, bus_cap_pf, bus_speed_hz,
      component_category, sub_type, etc.

    validations: list of Python expressions that MUST be True after instantiation.
      Can reference the resolved parameter values.
    """
    pattern_id: str
    version: str = "v1"
    category: Literal["interface", "protection", "power", "analog", "emc"]
    name: str
    description: str
    trigger: str            # e.g. "interface_type == 'I2C'"
    parameters: list[PatternParameter] = Field(default_factory=list)
    output_components: list[OutputComponent] = Field(default_factory=list)
    output_nets: list[OutputNet] = Field(default_factory=list)
    validations: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)

    @property
    def param_defaults(self) -> dict[str, Any]:
        """Return {name: default} for all parameters."""
        return {p.name: p.default for p in self.parameters}

    def resolve_parameters(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        """Merge defaults with overrides. Evaluate formula params."""
        resolved = self.param_defaults.copy()
        if overrides:
            resolved.update(overrides)
        # Evaluate formula params in dependency order
        for param in self.parameters:
            if param.formula and param.name not in (overrides or {}):
                try:
                    resolved[param.name] = eval(param.formula, {}, resolved)  # noqa: S307
                except Exception:
                    pass
        return resolved


# ---------------------------------------------------------------------------
# Pattern Bundle
# ---------------------------------------------------------------------------

class PatternBundle(BaseModel):
    """An ordered collection of patterns that apply together for a use-case."""
    bundle_id: str
    name: str
    description: str
    pattern_ids: list[str]      # applied in order
    trigger: str = ""           # optional overall trigger condition
    notes: list[str] = Field(default_factory=list)
