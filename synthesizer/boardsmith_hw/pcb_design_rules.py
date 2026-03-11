# SPDX-License-Identifier: AGPL-3.0-or-later
"""PCB Design Rules Engine — IPC-2221 trace widths, clearances, via rules.

Generates design constraints from HIR data:
  - Trace widths based on current (IPC-2221 formula, 1oz copper)
  - Via size rules (standard, micro-via)
  - Clearance rules
  - Signal integrity notes (SPI, I2C, USB, RF keepouts)
  - DSN constraint block for FreeRouting

Usage::

    from boardsmith_hw.pcb_design_rules import build_design_rules
    rules = build_design_rules(hir_dict)
    print(rules.signal_integrity_notes)
    dsn = rules.to_dsn_constraints()
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# IPC-2221 constants (1oz copper = 1.37 mil thick, external layer)
# ---------------------------------------------------------------------------

_K_EXTERNAL = 0.048   # external layer constant (IPC-2221B Table 6-1)
_K_INTERNAL = 0.024   # internal layer constant
_CU_THICK_MILS = 1.37  # 1oz copper = 1.37 mils
_MILS_TO_MM = 0.0254


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TraceRule:
    """Trace width rule for a specific net or signal type."""

    net_name: str
    min_width_mm: float
    preferred_width_mm: float
    is_differential: bool = False
    impedance_ohm: Optional[float] = None
    note: str = ""


@dataclass
class ViaRule:
    """Via size and clearance rules."""

    drill_mm: float = 0.3
    pad_mm: float = 0.6
    min_annular_ring_mm: float = 0.15
    min_clearance_mm: float = 0.15

    @property
    def microvias_ok(self) -> bool:
        return self.drill_mm <= 0.15


@dataclass
class PcbDesignRules:
    """Complete PCB design rules derived from an HIR dict.

    Attributes:
        min_trace_mm:         Absolute minimum trace width (fab limit).
        default_trace_mm:     Default signal trace width.
        power_trace_mm:       Power rail traces.
        gnd_trace_mm:         Ground traces (usually same as power).
        high_current_trace_mm: Traces carrying >500 mA.
        min_clearance_mm:     Electrical clearance between nets.
        via:                  Via size rules.
        trace_rules:          Per-net trace width overrides.
        signal_integrity_notes: Human-readable SI recommendations.
    """

    min_trace_mm: float = 0.15
    default_trace_mm: float = 0.25
    power_trace_mm: float = 0.50
    gnd_trace_mm: float = 0.50
    high_current_trace_mm: float = 1.00
    min_clearance_mm: float = 0.15
    via: ViaRule = field(default_factory=ViaRule)
    trace_rules: list[TraceRule] = field(default_factory=list)
    signal_integrity_notes: list[str] = field(default_factory=list)

    def to_dsn_constraints(self) -> str:
        """Emit a FreeRouting-compatible DSN constraint block.

        This string is inserted into the (rules ...) section of a .dsn file.
        All widths in DSN are in µm (FreeRouting convention).
        """

        def mm_to_um(mm: float) -> int:
            return int(round(mm * 1000))

        lines = [
            "(rule",
            f"  (width {mm_to_um(self.default_trace_mm)})",
            f"  (clearance {mm_to_um(self.min_clearance_mm)})",
            ")",
            "(rule",
            "  (layer_usage signal)",
            f"  (width {mm_to_um(self.default_trace_mm)})",
            f"  (clearance {mm_to_um(self.min_clearance_mm)})",
            ")",
            "(rule",
            "  (layer_usage power)",
            f"  (width {mm_to_um(self.power_trace_mm)})",
            f"  (clearance {mm_to_um(self.min_clearance_mm * 1.5)})",
            ")",
        ]

        # Differential pair rules
        for rule in self.trace_rules:
            if rule.is_differential:
                lines += [
                    f"(rule (net {rule.net_name})",
                    f"  (width {mm_to_um(rule.preferred_width_mm)})",
                    f"  (clearance {mm_to_um(self.min_clearance_mm)})",
                    ")",
                ]

        # Via rules
        lines += [
            "(via",
            f"  (drill {mm_to_um(self.via.drill_mm)})",
            f"  (diameter {mm_to_um(self.via.pad_mm)})",
            f"  (clearance {mm_to_um(self.via.min_clearance_mm)})",
            ")",
        ]

        return "\n".join(lines)

    def summary(self) -> str:
        """Return a human-readable summary of design rules."""
        lines = [
            "PCB Design Rules (IPC-2221)",
            f"  Default trace:       {self.default_trace_mm:.2f} mm",
            f"  Power/GND trace:     {self.power_trace_mm:.2f} mm",
            f"  High-current trace:  {self.high_current_trace_mm:.2f} mm",
            f"  Min clearance:       {self.min_clearance_mm:.2f} mm",
            f"  Via drill/pad:       {self.via.drill_mm:.2f}/{self.via.pad_mm:.2f} mm",
        ]
        if self.trace_rules:
            lines.append("  Per-net rules:")
            for rule in self.trace_rules:
                diff = " (diff pair)" if rule.is_differential else ""
                lines.append(f"    {rule.net_name}: {rule.preferred_width_mm:.2f} mm{diff}")
        if self.signal_integrity_notes:
            lines.append("  Signal integrity notes:")
            for note in self.signal_integrity_notes:
                lines.append(f"    • {note}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# IPC-2221 formula
# ---------------------------------------------------------------------------


def trace_width_for_current(
    current_ma: float,
    temp_rise_c: float = 10.0,
    layer: str = "external",
) -> float:
    """Return minimum trace width in mm for the given current.

    Uses IPC-2221B Section 6 formula for 1oz copper:
        I = k * ΔT^0.44 * A^0.725
    Solving for A (cross-section in mils²), then width = A / thickness_mils.

    Args:
        current_ma:   Current in milliamps.
        temp_rise_c:  Allowed temperature rise above ambient (default 10°C).
        layer:        "external" or "internal" (internal → narrower due to thermal).

    Returns:
        Minimum trace width in mm, rounded to 0.01 mm, minimum 0.10 mm.
    """
    if current_ma <= 0:
        return 0.10

    k = _K_EXTERNAL if layer == "external" else _K_INTERNAL
    i_amps = current_ma / 1000.0

    # Solve for area: A = (I / (k * ΔT^0.44))^(1/0.725)
    area_mils2 = (i_amps / (k * (temp_rise_c ** 0.44))) ** (1.0 / 0.725)
    width_mils = area_mils2 / _CU_THICK_MILS
    width_mm = width_mils * _MILS_TO_MM

    return max(0.10, round(width_mm, 2))


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_design_rules(hir: dict) -> PcbDesignRules:
    """Build PCB design rules from an HIR dict.

    Analyses:
      - Total current draw → power trace width
      - Bus types → signal integrity notes + per-net rules
      - RF components → antenna keepout note
      - USB presence → differential pair rules

    Args:
        hir: HIR as a plain dict.

    Returns:
        PcbDesignRules with computed widths and notes.
    """
    rules = PcbDesignRules()
    notes: list[str] = []

    components = hir.get("components", [])
    bus_contracts = hir.get("bus_contracts", [])

    # ------------------------------------------------------------------
    # Power analysis → trace width for power rails
    # ------------------------------------------------------------------
    total_current_ma = 0.0
    for comp in components:
        er = comp.get("electrical_ratings", {})
        total_current_ma += float(er.get("current_draw_max_ma", 0.0))

    if total_current_ma > 0:
        required_ma = total_current_ma * 1.20   # 20% safety margin
        rules.power_trace_mm = max(0.50, trace_width_for_current(required_ma))
        rules.gnd_trace_mm = rules.power_trace_mm

        if total_current_ma > 500:
            rules.high_current_trace_mm = max(
                1.00, trace_width_for_current(required_ma)
            )
            notes.append(
                f"High current path ({total_current_ma:.0f} mA) — "
                f"power/GND traces ≥ {rules.power_trace_mm:.2f} mm"
            )

    # ------------------------------------------------------------------
    # Bus-type specific rules
    # ------------------------------------------------------------------
    bus_types = {b.get("bus_type", "").upper() for b in bus_contracts}

    if "USB" in bus_types:
        # USB full-speed: 90Ω differential, 0.20 mm traces, 0.20 mm gap
        for net in ("USB_DP", "USB_DM"):
            rules.trace_rules.append(
                TraceRule(
                    net_name=net,
                    min_width_mm=0.20,
                    preferred_width_mm=0.20,
                    is_differential=True,
                    impedance_ohm=90.0,
                    note="USB 2.0 full-speed differential pair",
                )
            )
        notes.append(
            "USB D+/D−: 0.20 mm traces, 0.20 mm gap, equal length "
            "(skew < 100 ps); no vias in differential segment"
        )

    if "SPI" in bus_types:
        notes.append(
            "SPI (MOSI/MISO/SCLK/CS): keep traces short and parallel; "
            "CS traces may be longer — avoid cross-talk with I2C"
        )
        notes.append(
            "Place 100 nF decoupling cap within 1 mm of every SPI peripheral VDD pin"
        )

    if "I2C" in bus_types:
        notes.append(
            "I2C (SDA/SCL): route on same layer; avoid sharp 90° bends; "
            "4.7 kΩ pull-ups near MCU (not near peripheral)"
        )

    if "UART" in bus_types:
        notes.append(
            "UART (TX/RX): cross TX→RX carefully; do not parallel-route "
            "with SPI SCLK over long distances"
        )

    if "CAN" in bus_types:
        # CAN high-speed: 120Ω differential
        for net in ("CANH", "CANL"):
            rules.trace_rules.append(
                TraceRule(
                    net_name=net,
                    min_width_mm=0.25,
                    preferred_width_mm=0.25,
                    is_differential=True,
                    impedance_ohm=120.0,
                    note="CAN bus differential pair",
                )
            )
        notes.append(
            "CAN (CANH/CANL): 120Ω differential, equal-length traces; "
            "120Ω termination at cable ends"
        )

    # ------------------------------------------------------------------
    # RF keepouts
    # ------------------------------------------------------------------
    rf_keywords = {
        "SX1276", "SX1278", "SX1262", "CC1101", "CC2500",
        "NRF24L01", "NRF52840", "ESP32", "ESP8266", "ESP32-C3",
        "WROOM", "WROVER", "W25Q",
    }
    for comp in components:
        mpn = comp.get("mpn", "").upper()
        cid = comp.get("id", "")
        if any(kw in mpn for kw in rf_keywords):
            notes.append(
                f"RF component ({cid}): maintain copper-free keepout around "
                "antenna area; no ground/power plane under antenna trace"
            )
            break

    # ------------------------------------------------------------------
    # Crystal / oscillator
    # ------------------------------------------------------------------
    xtal_roles = {"crystal", "oscillator", "xtal"}
    for comp in components:
        role = comp.get("role", "").lower()
        mpn = comp.get("mpn", "").lower()
        if role in xtal_roles or "crystal" in mpn or "osc" in mpn:
            notes.append(
                f"Crystal/oscillator ({comp.get('id', '')}): keep load caps "
                "within 5 mm; guard ring around circuit; avoid routing under crystal"
            )
            break

    # ------------------------------------------------------------------
    # Decoupling caps
    # ------------------------------------------------------------------
    mcu_present = any(
        c.get("role", "").lower() == "mcu" for c in components
    )
    if mcu_present:
        notes.append(
            "MCU decoupling: 100 nF cap on every VDD/VDDA pin within 1 mm; "
            "10 µF bulk cap near power entry; connect directly to GND plane"
        )

    rules.signal_integrity_notes = notes
    return rules
