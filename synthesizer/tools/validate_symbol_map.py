#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Automated validation tool for the component database (symbol_map.py).

Performs static checks on all SymbolDef entries without requiring KiCad
or any external hardware-access library.

Checks implemented
------------------
A1  Schema correctness       — ref_prefix, footprint format, description,
                               pin types/sides, duplicate pin numbers/names
A2  Pin count vs package     — symbol pin count vs expected pad count from
                               footprint name heuristics (80% minimum)
A3  Power-pin consistency    — ICs have GND + VDD; all power pins resolvable
A4  Footprint library prefix — known KiCad library prefix list
D1  Net-mapping completeness — every power pin resolves via _net_for_pin()
D2  Net-mapping semantics    — GND pins → GND, VDD pins → +3V3, not swapped
G1  Bus-pin presence         — I2C sensors have SDA+SCL, SPI have MOSI etc.
G2  Bus pin-type sanity      — bidirectional for shared signals

Run from the repository root (or from synthesizer/):
    python3 synthesizer/tools/validate_symbol_map.py
    python3 synthesizer/tools/validate_symbol_map.py --verbose
    python3 synthesizer/tools/validate_symbol_map.py --only TP4056 FT232RL
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Path setup — allow running from repo root or from synthesizer/
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
for _candidate in [
    _HERE.parent,                          # synthesizer/
    _HERE.parent.parent / "synthesizer",   # repo_root/synthesizer/
]:
    if (_candidate / "synth_core").exists():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        break

from synth_core.knowledge.symbol_map import SYMBOL_MAP, SymbolDef, PinDef  # noqa: E402

# We import the keyword constants directly from kicad_exporter so checks stay
# in sync with the actual routing logic.
try:
    from boardsmith_hw.kicad_exporter import (  # noqa: E402
        _GND_KEYWORDS,
        _3V3_KEYWORDS,
        _VIN_KEYWORDS,
        _12V_KEYWORDS,
        _VBAT_EXACT,
        _MOTOR_SUPPLY_KEYWORDS,
        _net_for_pin,
    )
    _EXPORTER_AVAILABLE = True
except ImportError:
    _EXPORTER_AVAILABLE = False
    # Fallback inline definitions (same logic as kicad_exporter.py)
    _GND_KEYWORDS  = ("GND", "VSS", "AGND", "DGND", "PGND")
    _3V3_KEYWORDS  = ("3V3", "VDD", "VCC", "DVDD", "IOVDD", "VOUT", "VS", "VTREF", "VREF")
    _VIN_KEYWORDS  = ("VIN", "5V", "VSUP", "VBUS")
    _12V_KEYWORDS  = ("12V", "VIN12", "V12")
    _VBAT_EXACT    = frozenset(("BAT", "VBAT", "VBATT", "BATT", "LIPO"))
    _MOTOR_SUPPLY_KEYWORDS = ("VM", "VMOT", "VPWR", "VMOTOR")

    def _net_for_pin(pin_name_upper: str) -> str | None:
        if any(k in pin_name_upper for k in _GND_KEYWORDS):
            return "GND"
        if any(k in pin_name_upper for k in _12V_KEYWORDS):
            return "+12V"
        if any(k in pin_name_upper for k in _VIN_KEYWORDS):
            return "+5V"
        if any(k in pin_name_upper for k in _3V3_KEYWORDS):
            return "+3V3"
        if pin_name_upper in _VBAT_EXACT:
            return "+VBAT"
        if pin_name_upper in _MOTOR_SUPPLY_KEYWORDS:
            return "+12V"
        return None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_REF_PREFIXES = {"U", "R", "C", "J", "D", "Q", "Y", "FB", "L", "SW"}

VALID_PIN_TYPES = {
    "input", "output", "bidirectional",
    "power_in", "power_out", "passive", "no_connect",
}

VALID_PIN_SIDES = {"left", "right"}

# Known KiCad footprint library prefixes
VALID_LIB_PREFIXES = {
    "Package_SO",
    "Package_TO_SOT_SMD",
    "Package_TO_SOT_THT",
    "Package_DFN_QFN",
    "Package_QFP",
    "Package_LGA",
    "Package_LCC",
    "Package_BGA",
    "Package_SSOP",
    "Package_TSSOP",
    "RF_Module",
    "RF_GPS",
    "Crystal",
    "LED_SMD",
    "Button_Switch_SMD",
    "Inductor_SMD",
    "Resistor_SMD",
    "Capacitor_SMD",
    "Diode_THT",
    "TerminalBlock_Phoenix",
    "Connector_PinHeader_2.54mm",
    "Connector_PinHeader_1.27mm",
    "Connector_USB",
    "Connector_Coaxial",
    "Connector_Molex",
    "Connector_JST",
    "Sensor_Humidity",
    "Sensor_Distance",
    "Sensor_IMU",
    "Sensor_Pressure",
    "Sensor_Temperature",
    "Sensor_Motion",
    "Sensor_Current",
    "Sensor_Voltage",
    "Sensor_Audio",
    "Sensor",
}
# Prefixes that are OK even if not in the exact set above (wildcard patterns)
_VALID_LIB_PREFIX_WILDCARDS = (
    "Connector_",
    "Package_",
)

# Footprint name → expected pad count heuristics.
# Format: substring in footprint name → (min_pads, max_pads)
# max_pads=-1 means "no upper bound from this rule"
_FOOTPRINT_PAD_HINTS: list[tuple[str, int]] = [
    # SOT packages
    ("SOT-23-3",      3),
    ("SOT-23-5",      5),
    ("SOT-23-6",      6),
    ("SOT-23-8",      8),
    ("SOT-223-3",     4),   # 3 + tab pin
    ("SOT-323",       3),
    ("SOT-563",       6),
    ("SOT-89",        4),   # 3 + tab
    # SO packages
    ("SOIC-8",        8),
    ("SOIC-16",      16),
    ("SOIC-20",      20),
    ("SOIC-24",      24),
    ("SOP-8",         8),
    ("SOP-16",       16),
    ("SOP-28",       28),
    ("SSOP-16",      16),
    ("SSOP-20",      20),
    ("SSOP-24",      24),
    ("SSOP-28",      28),
    ("TSSOP-8",       8),
    ("TSSOP-14",     14),
    ("TSSOP-16",     16),
    ("TSSOP-20",     20),
    ("TSSOP-24",     24),
    ("MSOP-8",        8),
    ("MSOP-10",      10),
    # QFP / LQFP
    ("LQFP-32",      32),
    ("LQFP-48",      48),
    ("LQFP-64",      64),
    ("LQFP-100",    100),
    ("LQFP-144",    144),
    ("QFP-48",       48),
    # DFN / QFN
    ("DFN-6",         6),
    ("DFN-8",         9),   # 8 + EP
    ("DFN-10",       11),   # 10 + EP
    ("QFN-16",       17),   # 16 + EP
    ("QFN-24",       25),   # 24 + EP
    ("QFN-32",       33),   # 32 + EP
    ("QFN-48",       49),   # 48 + EP
    ("QFN-56",       57),   # 56 + EP
    # TO packages (THT)
    ("TO-220",        3),
    ("TO-92",         3),
    ("TO-263",        3),
    # Crystal
    ("HC49",          2),
    ("Crystal_SMD",   4),
    # LGA
    ("LGA-14",       14),
    ("LGA-8",         8),
    # Modules
    ("ESP32-C3-WROOM-02",  22),   # simplified OK
    ("ESP32-WROOM-32",     38),   # simplified OK
    ("ESP32-S3-WROOM-1",   36),   # simplified OK
    ("UFQFPN-32",          33),   # 32 + EP (STM32)
]

# Interface bus pins required by protocol
_I2C_PINS  = {"SDA", "SCL"}
_SPI_PINS  = {"MOSI", "MISO", "SCLK", "SCK"}  # SCK alias allowed
_UART_PINS = {"TX", "RX"}

# SPI aliases: component may name them SDI, SDO, CLK etc.
_SPI_MOSI_ALIASES = {"MOSI", "SDI", "DIN", "SIN", "COPI"}
_SPI_MISO_ALIASES = {"MISO", "SDO", "DOUT", "SOUT", "CIPO"}
_SPI_SCLK_ALIASES = {"SCLK", "SCK", "CLK", "CK"}

# Components we know are MCUs / large complex ICs where simplified symbols are normal.
# These get a lower (50%) threshold in A2 so we don't flood with warnings.
_SIMPLIFIED_SYMBOL_SUBSTRINGS = (
    "ESP32", "STM32", "ATmega", "ATtiny", "SAMD", "RP2040",
    "nRF52", "STM8", "PIC", "MSP430", "LPC55", "MIMXRT", "RFM",
    "SSD1306",  # display controller — intentionally stripped down
)

# Components with no traditional VCC supply pin by design
# (darlington arrays, protection ICs, analog switch networks, etc.)
_NO_VCC_BY_DESIGN = frozenset((
    "ULN2003A",  # darlington array — COM pin is load supply, not VCC
    "ULN2803A",
))


# ---------------------------------------------------------------------------
# Result data structure
# ---------------------------------------------------------------------------

class Finding(NamedTuple):
    level: str    # "FAIL" | "WARN" | "PASS" | "INFO"
    check: str    # e.g. "A1", "D2"
    mpn: str
    message: str


# ---------------------------------------------------------------------------
# Check helpers
# ---------------------------------------------------------------------------

def _expected_pad_count(footprint: str) -> int | None:
    """Return expected pad count from footprint name, or None if unknown."""
    fp_upper = footprint.upper()
    for substr, count in _FOOTPRINT_PAD_HINTS:
        if substr.upper() in fp_upper:
            return count
    return None


def _pin_names_upper(sdef: SymbolDef) -> set[str]:
    return {p.name.upper() for p in sdef.pins}


def _is_ic(sdef: SymbolDef) -> bool:
    return sdef.ref_prefix == "U"


def _has_i2c(sdef: SymbolDef) -> bool:
    names = _pin_names_upper(sdef)
    return "SDA" in names and "SCL" in names


def _has_spi(sdef: SymbolDef) -> bool:
    names = _pin_names_upper(sdef)
    has_clk  = bool(names & _SPI_SCLK_ALIASES)
    has_mosi = bool(names & _SPI_MOSI_ALIASES)
    has_miso = bool(names & _SPI_MISO_ALIASES)
    return has_clk and (has_mosi or has_miso)


def _has_uart(sdef: SymbolDef) -> bool:
    names = _pin_names_upper(sdef)
    return bool(names & {"TX", "RX", "TXD", "RXD", "TXD0", "RXD0"})


def _lib_prefix_ok(footprint: str) -> bool:
    """Check if the library part of 'Lib:Name' is a known KiCad library."""
    if ":" not in footprint:
        return False
    lib = footprint.split(":")[0]
    if lib in VALID_LIB_PREFIXES:
        return True
    return any(lib.startswith(wc) for wc in _VALID_LIB_PREFIX_WILDCARDS)


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------

def check_a1_schema(mpn: str, sdef: SymbolDef) -> list[Finding]:
    """A1 — Schema correctness."""
    findings: list[Finding] = []
    tag = "A1"

    # ref_prefix
    if sdef.ref_prefix not in VALID_REF_PREFIXES:
        findings.append(Finding("FAIL", tag, mpn,
            f"ref_prefix='{sdef.ref_prefix}' not in {sorted(VALID_REF_PREFIXES)}"))

    # footprint contains exactly one ':'
    colon_count = sdef.footprint.count(":")
    if colon_count != 1:
        findings.append(Finding("FAIL", tag, mpn,
            f"footprint '{sdef.footprint}' has {colon_count} colons (expected 1)"))

    # description not empty
    if not sdef.description.strip():
        findings.append(Finding("FAIL", tag, mpn, "description is empty"))

    # at least 2 pins
    if len(sdef.pins) < 2:
        findings.append(Finding("FAIL", tag, mpn,
            f"only {len(sdef.pins)} pin(s) defined (minimum 2)"))

    # pin type and side validation
    seen_numbers: dict[str, str] = {}
    seen_names: dict[str, int] = {}
    for pin in sdef.pins:
        if pin.type not in VALID_PIN_TYPES:
            findings.append(Finding("FAIL", tag, mpn,
                f"pin '{pin.name}' has invalid type='{pin.type}'"))
        if pin.side not in VALID_PIN_SIDES:
            findings.append(Finding("FAIL", tag, mpn,
                f"pin '{pin.name}' has invalid side='{pin.side}'"))
        # duplicate pin number
        if pin.number in seen_numbers:
            findings.append(Finding("FAIL", tag, mpn,
                f"duplicate pin number '{pin.number}' "
                f"('{seen_numbers[pin.number]}' and '{pin.name}')"))
        else:
            seen_numbers[pin.number] = pin.name
        # duplicate pin name (warn, not fail — GND1/GND2 OK for multi-ground)
        name_up = pin.name.upper()
        seen_names[name_up] = seen_names.get(name_up, 0) + 1

    for name, count in seen_names.items():
        if count > 1 and name not in ("GND", "~", "NC", "AGND", "DGND", "PGND"):
            findings.append(Finding("WARN", tag, mpn,
                f"pin name '{name}' appears {count} times"))

    if not findings:
        findings.append(Finding("PASS", tag, mpn,
            f"ref_prefix={sdef.ref_prefix!r}, "
            f"footprint OK, {len(sdef.pins)} pins"))
    return findings


def check_a2_pin_count_vs_package(mpn: str, sdef: SymbolDef) -> list[Finding]:
    """A2 — Pin count vs package (heuristic-based)."""
    findings: list[Finding] = []
    tag = "A2"

    expected = _expected_pad_count(sdef.footprint)
    if expected is None:
        findings.append(Finding("INFO", tag, mpn,
            f"no pad-count heuristic for footprint '{sdef.footprint}'"))
        return findings

    n_pins = len(sdef.pins)

    # Too many pins in symbol than pads in package → definitely wrong
    if n_pins > expected:
        findings.append(Finding("FAIL", tag, mpn,
            f"{n_pins} symbol pins > {expected} package pads "
            f"(footprint: {sdef.footprint.split(':')[1]})"))
    # Simplified symbols: MCUs / large ICs → 50% threshold; discrete ICs → 80%
    threshold = 0.50 if any(s in mpn for s in _SIMPLIFIED_SYMBOL_SUBSTRINGS) else 0.80
    min_required = max(2, int(expected * threshold))
    if n_pins < min_required:
        findings.append(Finding("WARN", tag, mpn,
            f"only {n_pins}/{expected} pads defined in symbol "
            f"(threshold {int(threshold*100)}%, min {min_required}) "
            f"— simplified symbol OK if pad numbers are correct"))

    if not findings:
        findings.append(Finding("PASS", tag, mpn,
            f"{n_pins} pins, package expects {expected} pads "
            f"(footprint: {sdef.footprint.split(':')[1]})"))
    return findings


def check_a3_power_pins(mpn: str, sdef: SymbolDef) -> list[Finding]:
    """A3 — Power-pin consistency for ICs."""
    findings: list[Finding] = []
    tag = "A3"

    if not _is_ic(sdef):
        findings.append(Finding("PASS", tag, mpn, "not an IC — skipped"))
        return findings

    # Known ICs without traditional VCC pin (darlington arrays etc.)
    if mpn in _NO_VCC_BY_DESIGN:
        findings.append(Finding("INFO", tag, mpn,
            "no VCC pin by design (e.g. darlington array — COM is load supply)"))
        return findings

    power_in_names = [p.name.upper() for p in sdef.pins if p.type == "power_in"]
    power_out_names = [p.name.upper() for p in sdef.pins if p.type == "power_out"]

    # Must have at least one GND-like pin
    has_gnd = any(any(k in n for k in _GND_KEYWORDS) for n in power_in_names)
    if not has_gnd:
        findings.append(Finding("FAIL", tag, mpn,
            f"IC has no power_in pin with GND keyword — power pins: {power_in_names}"))

    # Must have at least one VDD-like pin (but not just GND)
    non_gnd_power = [n for n in power_in_names
                     if not any(k in n for k in _GND_KEYWORDS)]
    # Also count power_out as VDD-capable (LDOs, regulators)
    non_gnd_power += power_out_names
    if not non_gnd_power:
        findings.append(Finding("WARN", tag, mpn,
            "IC has no non-GND power pin (VDD/VCC/VIN/VOUT) — possible omission"))

    # Unresolvable power pins
    unresolved = []
    for p in sdef.pins:
        if p.type in ("power_in", "power_out"):
            net = _net_for_pin(p.name.upper())
            if net is None:
                unresolved.append(p.name)
    if unresolved:
        findings.append(Finding("FAIL", tag, mpn,
            f"power pins with no net mapping: {unresolved} "
            f"— these will be unconnected in schematic"))

    if not findings:
        findings.append(Finding("PASS", tag, mpn,
            f"GND={has_gnd}, supply pins={non_gnd_power[:3]}"))
    return findings


def check_a4_footprint_prefix(mpn: str, sdef: SymbolDef) -> list[Finding]:
    """A4 — Footprint library prefix."""
    findings: list[Finding] = []
    tag = "A4"

    if ":" not in sdef.footprint:
        findings.append(Finding("FAIL", tag, mpn,
            f"footprint '{sdef.footprint}' has no ':' separator"))
        return findings

    lib, name = sdef.footprint.split(":", 1)

    if not _lib_prefix_ok(sdef.footprint):
        findings.append(Finding("WARN", tag, mpn,
            f"library prefix '{lib}' not in known KiCad library list"))

    if " " in name:
        findings.append(Finding("FAIL", tag, mpn,
            f"footprint name part '{name}' contains spaces"))

    # Check for common umlaut/non-ASCII
    try:
        sdef.footprint.encode("ascii")
    except UnicodeEncodeError:
        findings.append(Finding("FAIL", tag, mpn,
            f"footprint string contains non-ASCII characters: '{sdef.footprint}'"))

    if not findings:
        findings.append(Finding("PASS", tag, mpn,
            f"library='{lib}', name='{name}'"))
    return findings


def check_c1_footprint_exists(mpn: str, sdef: SymbolDef) -> list[Finding]:
    """C1 — Footprint exists in local KiCad installation (requires KiCad)."""
    findings: list[Finding] = []
    tag = "C1"

    try:
        from tools.kicad_library import KiCadLibrary, KICAD_AVAILABLE
    except ImportError:
        return [Finding("SKIP", tag, mpn, "kicad_library module not importable")]

    if not KICAD_AVAILABLE:
        return [Finding("SKIP", tag, mpn, "KiCad not installed — skipping C1")]

    lib = KiCadLibrary()
    if lib.footprint_exists(sdef.footprint):
        findings.append(Finding("PASS", tag, mpn,
            f"footprint '{sdef.footprint}' found in KiCad"))
    else:
        findings.append(Finding("WARN", tag, mpn,
            f"footprint '{sdef.footprint}' NOT found in local KiCad install "
            f"(may be custom or non-standard library)"))
    return findings


def check_c2_kicad_ref_consistent(mpn: str, sdef: SymbolDef) -> list[Finding]:
    """C2 — kicad_ref footprint matches our DB footprint (requires KiCad)."""
    findings: list[Finding] = []
    tag = "C2"

    if not sdef.kicad_ref:
        return [Finding("SKIP", tag, mpn, "no kicad_ref set — skipping C2")]

    try:
        from tools.kicad_library import KiCadLibrary, KICAD_AVAILABLE
    except ImportError:
        return [Finding("SKIP", tag, mpn, "kicad_library module not importable")]

    if not KICAD_AVAILABLE:
        return [Finding("SKIP", tag, mpn, "KiCad not installed — skipping C2")]

    lib_name, part_name = sdef.kicad_ref.split(":", 1) if ":" in sdef.kicad_ref else ("", sdef.kicad_ref)
    lib = KiCadLibrary()
    sym = lib.lookup(part_name, lib_name) if lib_name else lib.lookup_any(part_name)

    if sym is None:
        findings.append(Finding("WARN", tag, mpn,
            f"kicad_ref '{sdef.kicad_ref}' not found in KiCad (library missing?)"))
        return findings

    if sym.footprint != sdef.footprint:
        findings.append(Finding("WARN", tag, mpn,
            f"footprint mismatch with KiCad: "
            f"our='{sdef.footprint}' kicad='{sym.footprint}'"))
    else:
        findings.append(Finding("PASS", tag, mpn,
            f"footprint matches KiCad: '{sdef.footprint}'"))
    return findings


def check_d1_net_mapping_complete(mpn: str, sdef: SymbolDef) -> list[Finding]:
    """D1 — All power pins resolve via _net_for_pin()."""
    findings: list[Finding] = []
    tag = "D1"

    unresolved = []
    for p in sdef.pins:
        if p.type in ("power_in", "power_out"):
            net = _net_for_pin(p.name.upper())
            if net is None:
                unresolved.append((p.name, p.number))

    if unresolved:
        for name, num in unresolved:
            findings.append(Finding("FAIL", tag, mpn,
                f"pin {num} '{name}' (power_in/out) has no net mapping — "
                f"will be unconnected in schematic"))
    else:
        power_pins = [p for p in sdef.pins if p.type in ("power_in", "power_out")]
        if power_pins:
            findings.append(Finding("PASS", tag, mpn,
                f"all {len(power_pins)} power pins resolve to a net"))
        else:
            findings.append(Finding("INFO", tag, mpn,
                "no power_in/power_out pins defined"))
    return findings


def check_d2_net_mapping_semantics(mpn: str, sdef: SymbolDef) -> list[Finding]:
    """D2 — Net-mapping semantics: GND pin → GND (not +3V3), etc."""
    findings: list[Finding] = []
    tag = "D2"
    errors = 0

    for p in sdef.pins:
        if p.type not in ("power_in", "power_out"):
            continue
        name_up = p.name.upper()
        net = _net_for_pin(name_up)
        if net is None:
            continue  # handled by D1

        gnd_like = any(k in name_up for k in _GND_KEYWORDS)

        # GND-named pin must resolve to "GND"
        if gnd_like and net != "GND":
            findings.append(Finding("FAIL", tag, mpn,
                f"pin '{p.name}' looks like GND but resolves to '{net}'"))
            errors += 1

        # VDD/VCC-named pin must NOT resolve to GND.
        # Exclude pins already matched by GND keywords (e.g. VSS contains "VS"
        # which is also in _3V3_KEYWORDS — the GND match takes precedence).
        vdd_like = any(k in name_up for k in _3V3_KEYWORDS) and not gnd_like
        if vdd_like and net == "GND":
            findings.append(Finding("FAIL", tag, mpn,
                f"pin '{p.name}' looks like VDD but resolves to 'GND'"))
            errors += 1

        # VIN-named pin must resolve to +5V or +12V (not GND, not +3V3)
        vin_like = any(k in name_up for k in _VIN_KEYWORDS) and not gnd_like
        if vin_like and net in ("GND", "+3V3"):
            findings.append(Finding("WARN", tag, mpn,
                f"pin '{p.name}' looks like VIN but resolves to '{net}' "
                f"(expected +5V or +12V)"))

    if errors == 0 and not findings:
        findings.append(Finding("PASS", tag, mpn, "net semantics OK"))
    return findings


def check_g1_bus_pins(mpn: str, sdef: SymbolDef) -> list[Finding]:
    """G1 — Interface protocol completeness.

    Only checks components that have *at least one* bus signal — avoids false
    positives for passives, regulators and other non-bus components.
    """
    findings: list[Finding] = []
    tag = "G1"

    has_i2c  = _has_i2c(sdef)
    has_spi  = _has_spi(sdef)
    has_uart = _has_uart(sdef)

    if not (has_i2c or has_spi or has_uart):
        findings.append(Finding("INFO", tag, mpn, "no bus interface detected — skipped"))
        return findings

    names = _pin_names_upper(sdef)

    if has_i2c:
        missing = _I2C_PINS - names
        if missing:
            findings.append(Finding("FAIL", tag, mpn,
                f"I2C component missing pin(s): {missing}"))
        else:
            findings.append(Finding("PASS", tag, mpn, "I2C: SDA+SCL present"))

    if has_spi:
        # SPI: require CLK + at least one of MOSI/MISO (read-only sensors OK)
        has_clk  = bool(names & _SPI_SCLK_ALIASES)
        has_mosi = bool(names & _SPI_MOSI_ALIASES)
        has_miso = bool(names & _SPI_MISO_ALIASES)
        missing_parts = []
        if not has_clk:
            missing_parts.append("CLK(SCLK/SCK)")
        if not has_mosi and not has_miso:
            missing_parts.append("MOSI and MISO")
        if missing_parts:
            findings.append(Finding("FAIL", tag, mpn,
                f"SPI component missing: {', '.join(missing_parts)}"))
        else:
            findings.append(Finding("PASS", tag, mpn,
                f"SPI: CLK={has_clk} MOSI={has_mosi} MISO={has_miso}"))

    if has_uart:
        # UART: TX+RX (or aliased names)
        uart_names = {"TX", "RX", "TXD", "RXD", "TXD0", "RXD0",
                      "LPUART1_TX", "LPUART1_RX", "DI", "RO"}
        found_uart = names & uart_names
        if len(found_uart) < 2:
            findings.append(Finding("WARN", tag, mpn,
                f"UART component only has {len(found_uart)} UART pin(s): {found_uart}"))
        else:
            findings.append(Finding("PASS", tag, mpn,
                f"UART: {found_uart & uart_names}"))

    return findings


def check_g2_bus_pin_types(mpn: str, sdef: SymbolDef) -> list[Finding]:
    """G2 — Shared bus signals must be bidirectional or correctly typed."""
    findings: list[Finding] = []
    tag = "G2"

    by_name = {p.name.upper(): p for p in sdef.pins}

    # SDA / SCL on I2C
    for sig in ("SDA",):
        if sig in by_name:
            p = by_name[sig]
            if p.type not in ("bidirectional", "passive"):
                findings.append(Finding("WARN", tag, mpn,
                    f"I2C {sig} has type='{p.type}' — should be 'bidirectional'"))

    # MISO should be output (from sensor/slave perspective) or bidirectional
    for alias in _SPI_MISO_ALIASES:
        if alias in by_name:
            p = by_name[alias]
            if p.type not in ("output", "bidirectional", "passive"):
                findings.append(Finding("WARN", tag, mpn,
                    f"SPI MISO ({alias}) has type='{p.type}' — expected output/bidirectional"))

    # MOSI should be input (from sensor/slave perspective) or bidirectional
    for alias in _SPI_MOSI_ALIASES:
        if alias in by_name:
            p = by_name[alias]
            if p.type not in ("input", "bidirectional", "passive"):
                findings.append(Finding("WARN", tag, mpn,
                    f"SPI MOSI ({alias}) has type='{p.type}' — expected input/bidirectional"))

    if not findings:
        findings.append(Finding("PASS", tag, mpn, "bus pin types OK"))
    return findings


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_all_checks(
    symbol_map: dict,
    verbose: bool = False,
    only: list[str] | None = None,
) -> tuple[int, int, int]:
    """Run all checks and print results.

    Returns (n_fail, n_warn, n_pass).
    """
    all_checks = [
        check_a1_schema,
        check_a2_pin_count_vs_package,
        check_a3_power_pins,
        check_a4_footprint_prefix,
        check_c1_footprint_exists,        # requires KiCad (SKIP if not installed)
        check_c2_kicad_ref_consistent,    # requires KiCad + kicad_ref field
        check_d1_net_mapping_complete,
        check_d2_net_mapping_semantics,
        check_g1_bus_pins,
        check_g2_bus_pin_types,
    ]

    n_fail = n_warn = n_pass = 0
    component_results: list[tuple[str, list[Finding]]] = []

    for mpn, sdef in sorted(symbol_map.items()):
        if only and mpn not in only:
            continue
        comp_findings: list[Finding] = []
        for check_fn in all_checks:
            comp_findings.extend(check_fn(mpn, sdef))
        component_results.append((mpn, comp_findings))

    # Print results
    for mpn, findings in component_results:
        # Determine worst level for this component
        levels = [f.level for f in findings]
        worst = "PASS"
        if "FAIL" in levels:
            worst = "FAIL"
        elif "WARN" in levels:
            worst = "WARN"
        # SKIP does not affect the worst-level tally

        if not verbose and worst == "PASS":
            n_pass += 1
            continue

        for f in findings:
            if not verbose and f.level in ("PASS", "INFO", "SKIP"):
                continue
            color = ""
            reset = ""
            if sys.stdout.isatty():
                color = {"FAIL": "\033[91m", "WARN": "\033[93m",
                         "PASS": "\033[92m", "INFO": "\033[94m",
                         "SKIP": "\033[90m"}.get(f.level, "")
                reset = "\033[0m"
            print(f"{color}{f.level:4s}{reset}  {f.check}  {f.mpn:<30s}  {f.message}")

        # Tally per-component
        comp_fail = sum(1 for f in findings if f.level == "FAIL")
        comp_warn = sum(1 for f in findings if f.level == "WARN")
        if comp_fail:
            n_fail += 1
        elif comp_warn:
            n_warn += 1
        else:
            n_pass += 1

    return n_fail, n_warn, n_pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate component symbol_map.py database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show PASS and INFO results as well")
    parser.add_argument("--only", nargs="+", metavar="MPN",
                        help="Only check these MPNs (space-separated)")
    parser.add_argument("--checks", nargs="+", metavar="CHECK",
                        help="Only run these checks (e.g. A1 D1 G1)")
    args = parser.parse_args()

    total = len(SYMBOL_MAP)
    if args.only:
        unknown = set(args.only) - set(SYMBOL_MAP)
        if unknown:
            print(f"Warning: MPNs not found in database: {unknown}", file=sys.stderr)

    print(f"BoardSmith Component Database Validator")
    print(f"Checking {total} components in SYMBOL_MAP …")
    if not _EXPORTER_AVAILABLE:
        print("⚠️  kicad_exporter not importable — using inline fallback keyword lists")
    print()

    n_fail, n_warn, n_pass = run_all_checks(
        SYMBOL_MAP,
        verbose=args.verbose,
        only=args.only,
    )

    checked = n_fail + n_warn + n_pass
    print()
    print("=" * 60)
    print(f"SUMMARY — {checked} components checked")
    print(f"  FAIL : {n_fail:3d}   ← fix immediately")
    print(f"  WARN : {n_warn:3d}   ← review manually")
    print(f"  PASS : {n_pass:3d}")
    print("=" * 60)

    if n_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
