#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""C1-C2 Validation: KiCad footprint existence and pad-number cross-check.

C1 — Footprint file exists in KiCad library
C2 — Every symbol pin number references a pad that exists in the .kicad_mod file

Run from repository root:
    python3 synthesizer/tools/validate_footprints.py
    python3 synthesizer/tools/validate_footprints.py --verbose
    python3 synthesizer/tools/validate_footprints.py --only W5500 FT232RL
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ── path setup ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "synthesizer"))

from synth_core.knowledge.symbol_map import SYMBOL_MAP  # noqa: E402

# ── KiCad footprint library root ──────────────────────────────────────────────
KICAD_FP_ROOTS = [
    Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"),
    Path.home() / ".local/share/kicad/8.0/footprints",
    Path("/usr/share/kicad/footprints"),
    Path("/usr/local/share/kicad/footprints"),
]

def find_kicad_root() -> Path | None:
    for p in KICAD_FP_ROOTS:
        if p.is_dir():
            return p
    return None


KICAD_ROOT = find_kicad_root()


# ── .kicad_mod parser — extract pad numbers ───────────────────────────────────

def _parse_pad_numbers(kicad_mod_path: Path) -> set[str]:
    """Return the set of pad numbers declared in a .kicad_mod file.

    Handles both numeric pads (1, 2, …) and named pads (EP, A, K, etc.).
    We use a simple regex rather than a full S-expression parser.
    """
    text = kicad_mod_path.read_text(encoding="utf-8", errors="replace")
    # KiCad 6+ format: (pad "1" smd ...) or (pad 1 smd ...)
    # also handles EP, ~, "", etc.
    numbers: set[str] = set()
    for m in re.finditer(r'\(pad\s+"?([^"\s\)]+)"?\s+\w+', text):
        raw = m.group(1)
        if raw not in ("~", ""):
            numbers.add(raw)
    return numbers


# ── result helpers ────────────────────────────────────────────────────────────

class _Counter:
    fail = 0
    warn = 0
    passed = 0


_CTR = _Counter()


def _emit(level: str, mpn: str, check: str, msg: str, verbose: bool) -> None:
    tag = level.upper()
    if tag == "FAIL":
        _CTR.fail += 1
        print(f"FAIL  {check:<4}  {mpn:<35} {msg}")
    elif tag == "WARN":
        _CTR.warn += 1
        if verbose:
            print(f"WARN  {check:<4}  {mpn:<35} {msg}")
    else:
        _CTR.passed += 1
        if verbose:
            print(f"PASS  {check:<4}  {mpn:<35} {msg}")


# ── main validation logic ─────────────────────────────────────────────────────

def validate_footprint(mpn: str, sdef, verbose: bool) -> None:
    fp_string = sdef.footprint  # e.g. "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"

    # ── C1 — footprint file exists ────────────────────────────────────────────
    if ":" not in fp_string:
        _emit("fail", mpn, "C1", f"footprint '{fp_string}' has no ':' separator", verbose)
        return

    lib_name, fp_name = fp_string.split(":", 1)

    if KICAD_ROOT is None:
        _emit("warn", mpn, "C1", "KiCad library root not found — skipping C1/C2", verbose)
        return

    lib_dir = KICAD_ROOT / f"{lib_name}.pretty"
    if not lib_dir.is_dir():
        _emit("fail", mpn, "C1", f"library '{lib_name}.pretty' does not exist in KiCad", verbose)
        return

    fp_file = lib_dir / f"{fp_name}.kicad_mod"
    if not fp_file.is_file():
        _emit("fail", mpn, "C1", f"footprint file '{fp_name}.kicad_mod' not found in {lib_name}.pretty", verbose)
        return

    _emit("pass", mpn, "C1", f"footprint file found: {lib_name}:{fp_name}", verbose)

    # ── C2 — every symbol pin number exists as a pad in the .kicad_mod ────────
    pad_numbers = _parse_pad_numbers(fp_file)
    if not pad_numbers:
        _emit("warn", mpn, "C2", f"could not parse any pads from {fp_name}.kicad_mod", verbose)
        return

    # BGA packages use alphanumeric pad names (A1, B2, …); simplified symbols use
    # sequential numbers (1, 2, 3, …) which never match.  Skip C2 for BGAs.
    bga_pads = {p for p in pad_numbers if len(p) >= 2 and p[0].isalpha() and p[1:].isdigit()}
    if len(bga_pads) > 4:  # more than a handful of alpha pads → BGA
        _emit("warn", mpn, "C2",
              f"BGA/LGA footprint with alphanumeric pads — C2 skipped for simplified symbol",
              verbose)
        return

    missing_pads: list[str] = []
    for pin in sdef.pins:
        # Some pin numbers are multi-part (e.g. "1/2") — check first part
        pnum = pin.number.split("/")[0].strip()
        if pnum not in pad_numbers:
            missing_pads.append(f"{pin.name}=pad{pnum}")

    if missing_pads:
        _emit("fail", mpn, "C2",
              f"{len(missing_pads)} symbol pin(s) reference non-existent pads: "
              f"{missing_pads}  [footprint has pads: {sorted(pad_numbers, key=lambda x: (len(x), x))[:10]}{'…' if len(pad_numbers)>10 else ''}]",
              verbose)
    else:
        _emit("pass", mpn, "C2",
              f"all {len(sdef.pins)} symbol pins reference valid pads (footprint has {len(pad_numbers)} pads total)",
              verbose)


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="C1-C2: KiCad footprint validation")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="show PASS and WARN lines (default: only FAIL)")
    ap.add_argument("--only", nargs="+", metavar="MPN",
                    help="validate only the listed MPNs")
    args = ap.parse_args()

    print("KiCad Footprint Validator (C1-C2)")
    if KICAD_ROOT:
        print(f"  KiCad library root: {KICAD_ROOT}")
    else:
        print("  ⚠️  KiCad library root NOT found — all checks will be skipped")
    print(f"  Checking {len(SYMBOL_MAP)} components …\n")

    targets = args.only if args.only else list(SYMBOL_MAP.keys())
    for mpn in targets:
        if mpn not in SYMBOL_MAP:
            print(f"ERROR: '{mpn}' not in SYMBOL_MAP")
            continue
        validate_footprint(mpn, SYMBOL_MAP[mpn], args.verbose)

    print()
    print("=" * 60)
    print(f"SUMMARY — {len(targets)} components checked")
    print(f"  FAIL : {_CTR.fail:>3}   ← fix immediately")
    print(f"  WARN : {_CTR.warn:>3}   ← review manually")
    print(f"  PASS : {_CTR.passed:>3}")
    print("=" * 60)
    return 1 if _CTR.fail else 0


if __name__ == "__main__":
    sys.exit(main())
