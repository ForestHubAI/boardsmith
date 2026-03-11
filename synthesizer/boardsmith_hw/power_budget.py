# SPDX-License-Identifier: AGPL-3.0-or-later
"""B17. Power Budget Calculator — current headroom analysis for synthesized designs.

Computes per-rail current budgets by summing component current draws, checks
headroom against regulator limits, and flags potential over-current conditions
before hardware is built.

Algorithm
---------
1. Walk all components in the HIR / SynthesizedTopology.
2. For each component, look up its max current draw from:
     a. The component's own ``electrical_ratings.current_draw_max_ma`` field.
     b. If not available, the built-in fallback table (_DEFAULT_CURRENT_MA).
3. Sum per-rail (3V3, 5V, VIN, …).
4. Compare each rail's total against its regulator's ``max_current_ma`` with a
   configurable safety margin (default 20 %).
5. Return a ``PowerBudget`` with per-rail breakdowns and pass/fail status.

Usage::

    from boardsmith_hw.power_budget import calculate_power_budget
    budget = calculate_power_budget(hir_dict, topology)
    if not budget.passes:
        for r in budget.rails:
            if not r.passes:
                print(f"OVER-CURRENT on {r.rail_name}: {r.total_load_ma:.0f}mA > {r.regulator_max_ma:.0f}mA")
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safety margin: regulator must have this much headroom above total load.
# E.g. 0.20 → 20% margin required.
# ---------------------------------------------------------------------------
DEFAULT_SAFETY_MARGIN = 0.20

# ---------------------------------------------------------------------------
# Fallback current estimates (mA) when not in electrical_ratings.
# Keyed by role or MPN keyword (lowercase, checked in order).
# ---------------------------------------------------------------------------
_DEFAULT_CURRENT_MA: dict[str, float] = {
    # MCUs
    "esp32":    240.0,   # WiFi active peak
    "esp32c3":  150.0,
    "rp2040":    25.0,
    "stm32":     50.0,
    "nrf52":     15.0,   # BLE active
    # Sensors
    "bme280":     3.6,
    "bmp280":     2.8,
    "aht20":      0.3,
    "shtc3":      0.6,
    "sht31":      1.5,
    "mpu6050":    3.9,
    "icm42688":   0.5,
    "lsm6ds":     0.9,
    "vl53l":     19.0,   # VCSEL laser
    "scd41":     18.5,
    # Displays
    "ssd1306":    9.0,
    "il9341":    30.0,   # backlight depends on application
    # Wireless
    "sx1276":   120.0,   # TX peak
    "nrf24":    115.0,
    # Generic fallbacks by role
    "mcu":       100.0,
    "sensor":      5.0,
    "display":    20.0,
    "comms":      50.0,
    "actuator":  200.0,
    "other":      10.0,
}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ComponentLoad:
    """Current draw attribution for one component on a rail."""
    comp_id: str
    mpn: str
    current_ma: float
    source: str   # "datasheet" | "fallback_mpn" | "fallback_role"


@dataclass
class RailBudget:
    """Current budget for one power rail."""
    rail_name: str
    supply_voltage: float           # nominal rail voltage (V)
    total_load_ma: float            # Σ current_ma across all consumers
    regulator_mpn: str | None       # LDO / converter MPN, or None for direct supply
    regulator_max_ma: float | None  # regulator capacity, None for direct supply
    safety_margin: float            # required fraction (e.g. 0.20)
    loads: list[ComponentLoad] = field(default_factory=list)

    @property
    def margin_ma(self) -> float | None:
        if self.regulator_max_ma is None:
            return None
        return self.regulator_max_ma - self.total_load_ma

    @property
    def margin_pct(self) -> float | None:
        if self.regulator_max_ma is None or self.regulator_max_ma == 0:
            return None
        return (self.margin_ma / self.regulator_max_ma) * 100  # type: ignore[operator]

    @property
    def passes(self) -> bool:
        """True if total load fits within the regulator capacity incl. safety margin."""
        if self.regulator_max_ma is None:
            return True   # no regulator → no constraint to check
        required = self.total_load_ma * (1.0 + self.safety_margin)
        return required <= self.regulator_max_ma

    @property
    def utilisation_pct(self) -> float | None:
        if self.regulator_max_ma is None or self.regulator_max_ma == 0:
            return None
        return (self.total_load_ma / self.regulator_max_ma) * 100


@dataclass
class PowerBudget:
    """Complete power budget for a synthesized design."""
    rails: list[RailBudget]
    safety_margin: float            # fraction (e.g. 0.20 → 20%)

    @property
    def passes(self) -> bool:
        return all(r.passes for r in self.rails)

    @property
    def total_load_ma(self) -> float:
        """Total current across all rails (note: components may appear on multiple rails)."""
        return sum(r.total_load_ma for r in self.rails)

    def get_rail(self, name: str) -> RailBudget | None:
        for r in self.rails:
            if r.rail_name == name:
                return r
        return None

    def summary_lines(self) -> list[str]:
        """Return human-readable summary lines."""
        lines: list[str] = []
        for r in self.rails:
            status = "OK" if r.passes else "OVER-CURRENT"
            if r.regulator_max_ma is not None:
                lines.append(
                    f"  {r.rail_name} ({r.supply_voltage:.1f}V): "
                    f"{r.total_load_ma:.0f}mA / {r.regulator_max_ma:.0f}mA "
                    f"[{r.utilisation_pct:.0f}% utilisation] — {status}"
                )
            else:
                lines.append(
                    f"  {r.rail_name} ({r.supply_voltage:.1f}V): "
                    f"{r.total_load_ma:.0f}mA — {status}"
                )
        return lines


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_power_budget(
    hir_dict: dict[str, Any],
    topology: Any | None = None,        # SynthesizedTopology | None
    safety_margin: float = DEFAULT_SAFETY_MARGIN,
) -> PowerBudget:
    """Calculate power budget from an HIR dict and optional topology.

    Args:
        hir_dict:       HIR dict (output of HIRComposer / B5).
        topology:       Optional SynthesizedTopology from B4 for voltage
                        regulator data.  If None, regulator data is extracted
                        from hir_dict["components"] (role == "power").
        safety_margin:  Required headroom fraction above total load.
                        Default 0.20 = 20%.

    Returns:
        PowerBudget with per-rail breakdown and pass/fail status.
    """
    # --- Collect regulator info ---
    # Regulator map: output_rail_name → (regulator_mpn, max_current_ma, input_voltage)
    reg_map: dict[str, tuple[str, float, float]] = {}

    if topology is not None:
        for reg in getattr(topology, "voltage_regulators", []):
            reg_map[reg.output_rail] = (
                reg.mpn,
                reg.max_current_ma,
                reg.input_voltage_nom,
            )

    # Also scan HIR components with role="power" (LDOs written into HIR)
    for comp in hir_dict.get("components", []):
        if comp.get("role") != "power":
            continue
        out_rail = comp.get("output_rail") or comp.get("id", "")
        caps = comp.get("capabilities", {})
        max_ma = caps.get("output_current_max_ma") or caps.get("current_draw_max_ma")
        if out_rail and max_ma and out_rail not in reg_map:
            reg_map[out_rail] = (comp.get("mpn", ""), float(max_ma), 0.0)

    # --- Identify all active rails from HIR power_sequence / components ---
    # Rail voltage map: rail_name → nominal_voltage
    rail_voltages: dict[str, float] = {}

    # From HIR power_sequence.rails (if present)
    ps = hir_dict.get("power_sequence", {})
    for rail in ps.get("rails", []):
        v = rail.get("voltage", {})
        nom = v.get("nominal") if isinstance(v, dict) else None
        if nom and rail.get("name"):
            rail_voltages[rail["name"]] = float(nom)

    # Fallback: synthesize typical rail names
    if not rail_voltages:
        if topology is not None:
            for pr in getattr(topology, "power_rails", []):
                rail_voltages[pr.name] = pr.voltage_nominal
        else:
            rail_voltages["3V3"] = 3.3

    # --- Collect component current draws per rail ---
    # All active (non-passive, non-power) components draw from the regulated rail.
    active_comps = [
        c for c in hir_dict.get("components", [])
        if c.get("role") not in ("passive", "power")
    ]

    # Determine which rail each component uses (simplification: all use the first
    # 3V3-class rail; components on 5V rails are noted separately).
    regulated_rail = _pick_regulated_rail(rail_voltages)

    # Build per-rail load lists
    rail_loads: dict[str, list[ComponentLoad]] = {name: [] for name in rail_voltages}
    if regulated_rail not in rail_loads:
        rail_loads[regulated_rail] = []

    for comp in active_comps:
        current_ma, source = _estimate_current(comp)
        load = ComponentLoad(
            comp_id=comp.get("id", "?"),
            mpn=comp.get("mpn", "?"),
            current_ma=current_ma,
            source=source,
        )
        rail_loads.setdefault(regulated_rail, []).append(load)

    # --- Build RailBudget objects ---
    rails: list[RailBudget] = []
    for rail_name, voltage in sorted(rail_voltages.items()):
        loads = rail_loads.get(rail_name, [])
        total = sum(l.current_ma for l in loads)

        reg_info = reg_map.get(rail_name)
        reg_mpn = reg_info[0] if reg_info else None
        reg_max = reg_info[1] if reg_info else None

        rails.append(RailBudget(
            rail_name=rail_name,
            supply_voltage=voltage,
            total_load_ma=total,
            regulator_mpn=reg_mpn,
            regulator_max_ma=reg_max,
            safety_margin=safety_margin,
            loads=loads,
        ))

    if not rails:
        # Degenerate: no rails found — synthesize one for the total
        total = sum(_estimate_current(c)[0] for c in active_comps)
        rails.append(RailBudget(
            rail_name="3V3",
            supply_voltage=3.3,
            total_load_ma=total,
            regulator_mpn=None,
            regulator_max_ma=None,
            safety_margin=safety_margin,
        ))

    return PowerBudget(rails=rails, safety_margin=safety_margin)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_regulated_rail(rail_voltages: dict[str, float]) -> str:
    """Return the name of the primary regulated rail (3.3V class)."""
    for name, v in rail_voltages.items():
        if 3.0 <= v <= 3.6:
            return name
    # Fallback: first rail found, or synthetic default
    return next(iter(rail_voltages), "3V3")


def _estimate_current(comp: dict[str, Any]) -> tuple[float, str]:
    """Estimate max current draw (mA) for a component.

    Returns (current_ma, source) where source is one of:
      "datasheet"    — value came from electrical_ratings.current_draw_max_ma
      "fallback_mpn" — value came from _DEFAULT_CURRENT_MA keyed by MPN keyword
      "fallback_role"— value came from _DEFAULT_CURRENT_MA keyed by role
    """
    # 1. Prefer explicit electrical_ratings
    ratings = comp.get("electrical_ratings", {})
    explicit = ratings.get("current_draw_max_ma")
    if explicit is not None:
        try:
            return float(explicit), "datasheet"
        except (TypeError, ValueError):
            pass

    # Also check capabilities.output_current_max_ma for power ICs
    caps = comp.get("capabilities", {})
    cap_current = caps.get("current_draw_max_ma")
    if cap_current is not None:
        try:
            return float(cap_current), "datasheet"
        except (TypeError, ValueError):
            pass

    # 2. MPN keyword lookup
    mpn_low = (comp.get("mpn") or "").lower()
    for keyword, ma in _DEFAULT_CURRENT_MA.items():
        if keyword in mpn_low and not keyword in ("mcu", "sensor", "display", "comms", "actuator", "other"):
            return ma, "fallback_mpn"

    # 3. Role fallback
    role = (comp.get("role") or "other").lower()
    return _DEFAULT_CURRENT_MA.get(role, 10.0), "fallback_role"
