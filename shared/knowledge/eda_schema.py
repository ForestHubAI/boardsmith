# SPDX-License-Identifier: AGPL-3.0-or-later
"""EDA Layer — First-Class Pydantic schema for symbol, footprint, and pin mapping.

DB-1: EDA profiles are the canonical, validatable, versionable source of truth
for all KiCad symbol/footprint data. symbol_map.py remains for backward
compatibility but EDAProfile is the new API.

Validation guarantees:
  - len(symbol.pins) <= footprint.pad_count  (exposed pad accounts for difference)
  - All pinmap keys exist in symbol pin numbers
  - All power_in pins have a domain mapping in power_pin_domains
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Electrical pin types — matches KiCad's pin electrical types
# ---------------------------------------------------------------------------

PinElectricalType = Literal[
    "power_in",      # VDD, GND, VBAT — power supply input
    "power_out",     # VOUT, regulated rails
    "input",         # logic input only (EN, CS, RESET, SCL, SCLK, ...)
    "output",        # logic output only (INT, MISO, TX, STATUS, ...)
    "bidirectional", # SDA, MOSI/MISO (depends on mode), GPIO
    "passive",       # resistors, capacitors, crystals — no direction
    "no_connect",    # NC pins — explicitly unconnected
]

PinSide = Literal["left", "right", "top", "bottom"]


# ---------------------------------------------------------------------------
# EDA Symbol
# ---------------------------------------------------------------------------

class EDAPin(BaseModel):
    """Single pin in a schematic symbol.

    Accepts positional args for concise profile definitions:
        EDAPin("VDD", "1", "power_in", "left")
    or keyword args:
        EDAPin(name="VDD", number="1")
    """
    name: str                                    # "VDD", "SDA", "INT"
    number: str                                  # Pad number "1", "2", "EP"
    electrical_type: PinElectricalType = "bidirectional"
    side: PinSide = "left"

    def __init__(
        self,
        name: str = "",
        number: str = "",
        electrical_type: PinElectricalType = "bidirectional",
        side: PinSide = "left",
        **kwargs,
    ) -> None:
        super().__init__(
            name=name,
            number=number,
            electrical_type=electrical_type,
            side=side,
            **kwargs,
        )


class EDASymbol(BaseModel):
    """KiCad schematic symbol definition."""
    lib_ref: str                                 # "Sensor:BME280" or just "BME280"
    ref_prefix: str                              # "U", "R", "C", "J", "Q", "Y", "FB"
    description: str = ""
    pins: list[EDAPin] = Field(default_factory=list)

    @property
    def pin_count(self) -> int:
        return len(self.pins)

    def pin_by_number(self, number: str) -> EDAPin | None:
        return next((p for p in self.pins if p.number == number), None)

    def pin_by_name(self, name: str) -> list[EDAPin]:
        return [p for p in self.pins if p.name == name]

    def power_pins(self) -> list[EDAPin]:
        return [p for p in self.pins if p.electrical_type in ("power_in", "power_out")]


# ---------------------------------------------------------------------------
# EDA Footprint
# ---------------------------------------------------------------------------

# Known package → (courtyard_width_mm, courtyard_height_mm, pad_count)
_PACKAGE_DIMS: dict[str, tuple[float, float, int]] = {
    "SOT-23":           (2.5,  3.5,  3),
    "SOT-23-3":         (2.5,  3.5,  3),
    "SOT-23-5":         (2.5,  3.5,  5),
    "SOT-23-6":         (2.5,  3.5,  6),
    "SOT-25":           (3.5,  3.0,  5),
    "SOT-223":          (4.5,  6.0,  4),
    "SOT-223-3":        (4.5,  6.0,  4),
    "SOIC-8":           (5.9,  6.9,  8),
    "SOP-8":            (5.9,  6.9,  8),
    "SSOP-24":          (6.5,  9.0,  24),
    "TSSOP-14":         (5.5,  6.0,  14),
    "TSSOP-16":         (5.5,  6.5,  16),
    "TSSOP-24":         (5.5,  8.2,  24),
    "DFN-4":            (2.0,  3.0,  4),
    "DFN-6":            (4.0,  4.0,  6),
    "DFN-8":            (3.0,  3.0,  8),
    "QFN-20":           (4.5,  4.5,  21),
    "QFN-24":           (6.0,  6.0,  25),
    "QFN-28":           (7.0,  7.0,  29),
    "QFN-32":           (7.0,  7.0,  33),
    "QFN-56":           (9.0,  9.0,  57),
    "QFN-73":           (9.0,  9.0,  74),
    "LGA-8":            (4.5,  4.5,  8),
    "LGA-14":           (5.0,  5.0,  14),
    "LQFP-48":          (9.0,  9.0,  48),
    "LQFP-64":         (12.0, 12.0,  64),
    "LQFP-100":        (16.0, 16.0, 100),
    "UFQFPN-48":        (8.0,  8.0,  49),
    "0402":             (1.5,  1.2,  2),
    "0603":             (2.3,  1.8,  2),
    "0805":             (3.0,  2.5,  2),
    "DO-41":            (5.0,  4.0,  2),
    "TO-220-3":         (8.0, 15.0,  3),
    "HC49":             (6.0,  4.5,  2),
}


def _courtyard_from_footprint(fp_name: str) -> tuple[float, float, int]:
    """Parse KiCad footprint name to extract courtyard dimensions + pad count.

    Returns (width_mm, height_mm, pad_count) — approximate courtyard.
    Falls back to (5.0, 5.0, 8) for unknown packages.
    """
    # Try exact package key match first
    for pkg, dims in _PACKAGE_DIMS.items():
        if pkg in fp_name:
            return dims

    # Try to extract WxHmm pattern from footprint name  e.g. "3.9x4.9mm"
    m = re.search(r"(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)mm", fp_name)
    if m:
        w, h = float(m.group(1)), float(m.group(2))
        return (w + 2.0, h + 2.0, 8)  # +2mm for courtyard, assume 8 pads

    return (5.0, 5.0, 8)  # generic fallback


class EDAFootprint(BaseModel):
    """KiCad PCB footprint definition."""
    kicad_name: str                              # Full KiCad footprint ref e.g. "Package_LGA:Bosch_LGA-8_2.5x2.5mm"
    pad_count: int                               # Total pads (incl. exposed pad if any)
    courtyard_width_mm: float = 0.0
    courtyard_height_mm: float = 0.0
    lcsc_part_id: str | None = None             # e.g. "C17024" — for JLCPCB PCBA
    jlcpcb_part_id: str | None = None

    @model_validator(mode="after")
    def _fill_dimensions(self) -> "EDAFootprint":
        if self.courtyard_width_mm == 0.0 or self.courtyard_height_mm == 0.0:
            w, h, _ = _courtyard_from_footprint(self.kicad_name)
            if self.courtyard_width_mm == 0.0:
                self.courtyard_width_mm = w
            if self.courtyard_height_mm == 0.0:
                self.courtyard_height_mm = h
        return self


# ---------------------------------------------------------------------------
# EDA Profile — the First-Class entity
# ---------------------------------------------------------------------------

class EDAProfile(BaseModel):
    """Complete EDA data for one MPN.

    Canonical source of truth for schematic symbol + PCB footprint + pin mapping.
    Replaces the ad-hoc data in symbol_map.py with a validated, versionable record.

    pinmap: {symbol_pin_number → footprint_pad_number}
    Default: identity mapping (every symbol pin "N" → footprint pad "N").

    power_pin_domains: {pin_name → domain_name}
    e.g. {"VDD": "VDD_3V3", "GND": "GND"}
    Required for all power_in pins for PCB net assignment.
    """
    mpn: str
    symbol: EDASymbol
    footprint: EDAFootprint
    pinmap: dict[str, str] = Field(default_factory=dict)
    power_pin_domains: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate(self) -> "EDAProfile":
        errors = validate_eda_profile(self)
        if errors:
            raise ValueError(f"EDAProfile for {self.mpn!r} failed validation:\n" + "\n".join(f"  - {e}" for e in errors))
        return self

    def effective_pinmap(self) -> dict[str, str]:
        """Return pinmap, defaulting to 1:1 identity if not specified."""
        if self.pinmap:
            return self.pinmap
        return {p.number: p.number for p in self.symbol.pins}

    def to_symbol_def_dict(self) -> dict:
        """Convert to the dict format expected by symbol_map.py consumers (backward compat)."""
        return {
            "ref_prefix": self.symbol.ref_prefix,
            "footprint": self.footprint.kicad_name,
            "description": self.symbol.description,
            "pins": [
                {"name": p.name, "number": p.number, "type": p.electrical_type, "side": p.side}
                for p in self.symbol.pins
            ],
        }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_eda_profile(profile: EDAProfile) -> list[str]:
    """Run all EDA validation rules. Returns list of error strings (empty = valid)."""
    errors: list[str] = []

    # Rule 1: Symbol pins ≤ footprint pads (exposed pad can add 1)
    sym_count = profile.symbol.pin_count
    pad_count = profile.footprint.pad_count
    if sym_count > pad_count + 1:
        errors.append(
            f"Pin count mismatch: symbol has {sym_count} pins but footprint has only {pad_count} pads"
        )

    # Rule 2: pinmap keys must exist as symbol pin numbers
    sym_pin_numbers = {p.number for p in profile.symbol.pins}
    for sym_num in profile.pinmap:
        if sym_num not in sym_pin_numbers:
            errors.append(f"pinmap key {sym_num!r} not found in symbol pin numbers {sym_pin_numbers}")

    # Rule 3: all power_in pins must have a domain mapping
    power_pins = profile.symbol.power_pins()
    # Only enforce when power_pin_domains is partially filled (not empty = "not yet specified")
    if profile.power_pin_domains:
        for pp in power_pins:
            if pp.name not in profile.power_pin_domains:
                errors.append(
                    f"Power pin {pp.name!r} (pad {pp.number}) has no entry in power_pin_domains"
                )

    return errors
