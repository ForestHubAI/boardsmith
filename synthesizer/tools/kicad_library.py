#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""KiCad local library adapter — read-only access to installed KiCad symbols + footprints.

Provides Flow 1 of the 3-flow component lookup:

  Flow 1: KiCad local library   (this module — exact, verified)
  Flow 2: LLM                   (llm.gateway)
  Flow 3: Our DB                (synth_core.knowledge.symbol_map)

``KICAD_AVAILABLE`` is set at import time — ``False`` when KiCad is not installed.
All public functions return ``None`` gracefully when KiCad is unavailable.

Usage::

    from synthesizer.tools.kicad_library import KiCadLibrary, KICAD_AVAILABLE

    lib = KiCadLibrary()
    sym = lib.lookup_any("STM32G431CBUx")
    if sym:
        print(sym.footprint)   # Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm
        print(len(sym.pins))   # 49
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Paths — macOS default KiCad 8 install location
# ---------------------------------------------------------------------------

KICAD_SYM_ROOT = Path(
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
)
KICAD_FP_ROOT = Path(
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
)

# True if KiCad symbol library is found at the expected location.
KICAD_AVAILABLE: bool = KICAD_SYM_ROOT.is_dir()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class KiCadPin:
    number: str                               # "21", "A7", "K14", "EP"
    name: str                                 # "PA5", "GND", "NRST", "~"
    pin_type: str                             # input|output|bidirectional|power_in|...
    alt_functions: list[str] = field(default_factory=list)  # ["ADC1_IN5", "TIM8_CH1"]
    hidden: bool = False                      # True for redundant power/GND copies


@dataclass
class KiCadSymbol:
    part_name: str      # "STM32G431CBUx" — KiCad canonical name
    lib_name: str       # "MCU_ST_STM32G4"
    footprint: str      # "Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm"
    datasheet_url: str  # "https://www.st.com/resource/en/datasheet/stm32g431cb.pdf"
    description: str    # "STMicroelectronics Arm Cortex-M4 MCU …"
    keywords: list[str]  # ["Arm", "Cortex-M4", "STM32G4"]
    pins: list[KiCadPin]


# ---------------------------------------------------------------------------
# Pin type normalisation
# ---------------------------------------------------------------------------

# KiCad raw pin type → canonical type string used in SymbolDef
_PIN_TYPE_MAP: dict[str, str] = {
    "input":          "input",
    "output":         "output",
    "bidirectional":  "bidirectional",
    "bidi":           "bidirectional",
    "power_in":       "power_in",
    "power_out":      "power_out",
    "passive":        "passive",
    "no_connect":     "no_connect",
    "open_collector": "output",
    "open_emitter":   "output",
    "unspecified":    "passive",
    "tri_state":      "output",
    "free":           "passive",
}


# ---------------------------------------------------------------------------
# KiCadLibrary
# ---------------------------------------------------------------------------


class KiCadLibrary:
    """Read-only access to local KiCad symbol + footprint libraries.

    Each ``.kicad_sym`` file is loaded lazily and cached in memory so that
    ``lookup_any`` (which scans all libraries) only pays the I/O cost once.

    Example::

        lib = KiCadLibrary()
        sym = lib.lookup("STM32G431CBUx", "MCU_ST_STM32G4")
        sym2 = lib.lookup_any("WM8731CLSEFL")
        ok = lib.footprint_exists("Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm")
        n   = lib.footprint_pad_count("Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm")
    """

    # Library name → .kicad_sym filename.  Extend as new categories are added.
    SYMBOL_LIBS: dict[str, str] = {
        "MCU_ST_STM32F0":        "MCU_ST_STM32F0.kicad_sym",
        "MCU_ST_STM32F1":        "MCU_ST_STM32F1.kicad_sym",
        "MCU_ST_STM32F2":        "MCU_ST_STM32F2.kicad_sym",
        "MCU_ST_STM32F3":        "MCU_ST_STM32F3.kicad_sym",
        "MCU_ST_STM32F4":        "MCU_ST_STM32F4.kicad_sym",
        "MCU_ST_STM32F7":        "MCU_ST_STM32F7.kicad_sym",
        "MCU_ST_STM32G0":        "MCU_ST_STM32G0.kicad_sym",
        "MCU_ST_STM32G4":        "MCU_ST_STM32G4.kicad_sym",
        "MCU_ST_STM32H7":        "MCU_ST_STM32H7.kicad_sym",
        "MCU_ST_STM32L0":        "MCU_ST_STM32L0.kicad_sym",
        "MCU_ST_STM32L4":        "MCU_ST_STM32L4.kicad_sym",
        "MCU_ST_STM32U5":        "MCU_ST_STM32U5.kicad_sym",
        "MCU_Microchip_ATmega":  "MCU_Microchip_ATmega.kicad_sym",
        "MCU_Microchip_PIC":     "MCU_Microchip_PIC.kicad_sym",
        "MCU_Espressif":         "MCU_Espressif.kicad_sym",
        "MCU_Nordic":            "MCU_Nordic.kicad_sym",
        "MCU_RaspberryPi":       "MCU_RaspberryPi.kicad_sym",
        "MCU_NXP_LPC":           "MCU_NXP_LPC.kicad_sym",
        "MCU_NXP_iMX":           "MCU_NXP_iMX.kicad_sym",
        "Audio":                 "Audio.kicad_sym",
        "RF":                    "RF.kicad_sym",
        "RF_Module":             "RF_Module.kicad_sym",
        "RF_GPS":                "RF_GPS.kicad_sym",
        "Sensor":                "Sensor.kicad_sym",
        "Sensor_Audio":          "Sensor_Audio.kicad_sym",
        "Sensor_Current":        "Sensor_Current.kicad_sym",
        "Sensor_Distance":       "Sensor_Distance.kicad_sym",
        "Sensor_Energy":         "Sensor_Energy.kicad_sym",
        "Sensor_Gas":            "Sensor_Gas.kicad_sym",
        "Sensor_Humidity":       "Sensor_Humidity.kicad_sym",
        "Sensor_Magnetic":       "Sensor_Magnetic.kicad_sym",
        "Sensor_Motion":         "Sensor_Motion.kicad_sym",
        "Sensor_Optical":        "Sensor_Optical.kicad_sym",
        "Sensor_Pressure":       "Sensor_Pressure.kicad_sym",
        "Sensor_Proximity":      "Sensor_Proximity.kicad_sym",
        "Sensor_Temperature":    "Sensor_Temperature.kicad_sym",
        "Sensor_Touch":          "Sensor_Touch.kicad_sym",
        "Sensor_Voltage":        "Sensor_Voltage.kicad_sym",
        "Interface_Ethernet":    "Interface_Ethernet.kicad_sym",
        "Interface_CAN_LIN":     "Interface_CAN_LIN.kicad_sym",
        "Interface_UART":        "Interface_UART.kicad_sym",
        "Interface_USB":         "Interface_USB.kicad_sym",
        "Interface_Optical":     "Interface_Optical.kicad_sym",
        "Regulator_Linear":      "Regulator_Linear.kicad_sym",
        "Regulator_Switching":   "Regulator_Switching.kicad_sym",
        "Isolator":              "Isolator.kicad_sym",
        "Memory":                "Memory.kicad_sym",
        "Display":               "Display.kicad_sym",
        "Driver_Motor":          "Driver_Motor.kicad_sym",
        "Analog_DAC":            "Analog_DAC.kicad_sym",
        "Analog_ADC":            "Analog_ADC.kicad_sym",
    }

    def __init__(self) -> None:
        # Lazy cache: lib_name → file text (None = file not found)
        self._cache: dict[str, Optional[str]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup(self, part_name: str, lib_name: str) -> Optional[KiCadSymbol]:
        """Look up a part in a specific KiCad symbol library.

        Follows the ``extends`` chain automatically.
        Returns ``None`` if not found or if KiCad is not installed.

        Example::

            sym = lib.lookup("STM32G431CBUx", "MCU_ST_STM32G4")
            # → footprint: "Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm"
        """
        if not KICAD_AVAILABLE:
            return None
        text = self._load_lib(lib_name)
        if text is None:
            return None
        return self._parse_symbol(text, part_name, lib_name)

    def lookup_any(self, part_name: str) -> Optional[KiCadSymbol]:
        """Search all registered libraries for a part name.

        Performs an exact-match pass first, then a case-insensitive pass.
        Returns the first match as a ``KiCadSymbol``, or ``None``.
        """
        if not KICAD_AVAILABLE:
            return None

        # Exact match pass
        for lib_name in self.SYMBOL_LIBS:
            text = self._load_lib(lib_name)
            if text is None:
                continue
            sym = self._parse_symbol(text, part_name, lib_name)
            if sym is not None:
                return sym

        # Case-insensitive pass (only scans already-cached libraries)
        part_lower = part_name.lower()
        for lib_name, text in self._cache.items():
            if text is None:
                continue
            for name in re.findall(r'^\s+\(symbol\s+"([^"]+)"', text, re.MULTILINE):
                # Skip sub-symbols (they have _N_N suffix)
                if re.search(r'_\d+_\d+$', name):
                    continue
                if name.lower() == part_lower:
                    sym = self._parse_symbol(text, name, lib_name)
                    if sym is not None:
                        return sym
        return None

    def footprint_exists(self, footprint: str) -> bool:
        """Check if a ``Library:Name`` footprint string exists locally.

        Example::

            lib.footprint_exists("Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm")
            # → True
        """
        if not KICAD_AVAILABLE or ":" not in footprint:
            return False
        lib_part, fp_name = footprint.split(":", 1)
        fp_file = KICAD_FP_ROOT / f"{lib_part}.pretty" / f"{fp_name}.kicad_mod"
        return fp_file.is_file()

    def footprint_pad_count(self, footprint: str) -> Optional[int]:
        """Return the number of pads in a KiCad footprint (from ``.kicad_mod`` file).

        Returns ``None`` if the footprint file is not found.
        """
        if not KICAD_AVAILABLE or ":" not in footprint:
            return None
        lib_part, fp_name = footprint.split(":", 1)
        fp_file = KICAD_FP_ROOT / f"{lib_part}.pretty" / f"{fp_name}.kicad_mod"
        if not fp_file.is_file():
            return None
        text = fp_file.read_text(encoding="utf-8", errors="replace")
        # Count pad entries: (pad "NUMBER" TYPE SHAPE ...)
        pads = re.findall(r'\(pad\s+"?[^"\s]+"?\s+\w+', text)
        return len(pads)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_lib(self, lib_name: str) -> Optional[str]:
        """Load and cache a ``.kicad_sym`` file.  Returns ``None`` if not found."""
        if lib_name in self._cache:
            return self._cache[lib_name]
        filename = self.SYMBOL_LIBS.get(lib_name)
        if filename is None:
            self._cache[lib_name] = None
            return None
        path = KICAD_SYM_ROOT / filename
        if not path.is_file():
            self._cache[lib_name] = None
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
        self._cache[lib_name] = text
        return text

    def _parse_symbol(
        self, text: str, part_name: str, lib_name: str
    ) -> Optional[KiCadSymbol]:
        """Parse one symbol from ``.kicad_sym`` text, following extends chains.

        Returns ``None`` if the symbol is not found in the file.
        """
        # 1. Check the part exists in this file
        if not re.search(
            r'^\s+\(symbol\s+"' + re.escape(part_name) + r'"',
            text, re.MULTILINE,
        ):
            return None

        # 2. Extract properties from the direct symbol block (child overrides parent)
        props = self._extract_props(text, part_name)

        # 3. Follow extends chain to find where the pins actually live
        base_name = self._resolve_extends(text, part_name)

        # 4. Merge parent properties where child has none
        if base_name != part_name:
            base_props = self._extract_props(text, base_name)
            for k, v in base_props.items():
                if k not in props or not props[k]:
                    props[k] = v

        # 5. Extract pins from base symbol's sub-symbols (_0_1, _1_1, etc.)
        pins = self._extract_pins(text, base_name)

        return KiCadSymbol(
            part_name=part_name,
            lib_name=lib_name,
            footprint=props.get("Footprint", ""),
            datasheet_url=props.get("Datasheet", ""),
            description=props.get("Description", ""),
            keywords=props.get("ki_keywords", "").split(),
            pins=pins,
        )

    def _extract_props(self, text: str, symbol_name: str) -> dict[str, str]:
        """Extract property key→value pairs from a symbol's top-level block."""
        # Match the symbol block but stop before the first sub-symbol (_N_M)
        # or the next top-level symbol
        block_re = re.compile(
            r'^\s+\(symbol\s+"' + re.escape(symbol_name) + r'"\s*\n'
            r'(.*?)'
            r'(?=^\s+\(symbol\s+"[^"]+"\s*$|^\))',
            re.MULTILINE | re.DOTALL,
        )
        m = block_re.search(text)
        if not m:
            return {}
        block = m.group(1)
        props: dict[str, str] = {}
        for pm in re.finditer(r'\(property\s+"([^"]+)"\s+"([^"]*)"', block):
            props[pm.group(1)] = pm.group(2)
        return props

    def _resolve_extends(self, text: str, symbol_name: str, _depth: int = 0) -> str:
        """Follow the ``extends`` chain and return the ultimate base name.

        The base symbol is where the pin sub-symbols (_N_M) actually live.
        Guard against infinite loops with a depth limit.
        """
        if _depth > 10:
            return symbol_name
        m = re.search(
            r'^\s+\(symbol\s+"' + re.escape(symbol_name) + r'"\s*\n\s*\(extends\s+"([^"]+)"',
            text, re.MULTILINE,
        )
        if m:
            return self._resolve_extends(text, m.group(1), _depth + 1)
        return symbol_name

    def _extract_pins(self, text: str, base_name: str) -> list[KiCadPin]:
        """Extract all pins from sub-symbols of ``base_name`` (``_N_M`` suffixes)."""
        # Sub-symbols are named "BaseName_0_1", "BaseName_1_1", etc.
        subsym_re = re.compile(
            r'\(symbol\s+"' + re.escape(base_name) + r'_\d+_\d+"'
            r'(.*?)'
            r'(?=\n\t\t\(symbol\s+"|\n\t\(symbol\s+"|\Z)',
            re.DOTALL,
        )

        pins: list[KiCadPin] = []
        seen: set[str] = set()  # deduplicate by pad number

        for block_m in subsym_re.finditer(text):
            block = block_m.group(1)

            # Each pin: (pin TYPE STYLE (at ...) (length ...) (name "N") (number "P") ...)
            # Use a greedy-stop pattern: stop at the next pin or end of block
            pin_re = re.compile(
                r'\(pin\s+(\S+)\s+\S+\s+\(at[^)]+\)\s+\(length[^)]+\)'
                r'(.*?)'
                r'(?=\(pin\s+\S+\s+\S+\s+\(at|\Z)',
                re.DOTALL,
            )
            for pm in pin_re.finditer(block):
                ptype_raw = pm.group(1)
                pbody = pm.group(2)

                nm = re.search(r'\(name\s+"([^"]*)"', pbody)
                nu = re.search(r'\(number\s+"([^"]*)"', pbody)
                if not nm or not nu:
                    continue

                pname = nm.group(1)
                pnum = nu.group(1)

                if pnum in seen:
                    continue
                seen.add(pnum)

                # Hidden? (hide yes) appears in the effects block of name/number
                hidden = bool(
                    re.search(r'\(hide\s+yes\)', pbody[:pbody.find("(number") if "(number" in pbody else len(pbody)])
                )

                # Alternate functions: (alternate "NAME" TYPE STYLE) inside pin block
                alts = re.findall(r'\(alternate\s+"([^"]+)"', pbody)

                pins.append(KiCadPin(
                    number=pnum,
                    name=pname,
                    pin_type=_PIN_TYPE_MAP.get(ptype_raw, "passive"),
                    alt_functions=alts,
                    hidden=hidden,
                ))

        return pins


# ---------------------------------------------------------------------------
# Self-test (run with: python3 synthesizer/tools/kicad_library.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"KiCad verfügbar: {KICAD_AVAILABLE}")
    if not KICAD_AVAILABLE:
        print(f"KiCad nicht gefunden unter: {KICAD_SYM_ROOT}")
        raise SystemExit(1)

    lib = KiCadLibrary()
    all_ok = True

    print("\n=== Symbol-Lookup-Tests ===")
    tests = [
        # (lib_name, part_name, expected_pin_count, fp_substr)
        ("MCU_ST_STM32G4",       "STM32G431CBUx",    49, "QFN-48"),
        ("Audio",                 "WM8731CLSEFL",     29, "QFN-28"),
        ("RF",                    "SX1276",            0, "QFN-28"),  # pin count varies
        ("MCU_Microchip_ATmega",  "ATmega328P-A",     32, "TQFP"),
        ("MCU_Nordic",            "nRF52840",          0, ""),  # just test found
    ]

    for lib_name, part, expected_pins, fp_substr in tests:
        sym = lib.lookup(part, lib_name)
        if sym is None:
            print(f"  FAIL  {lib_name}:{part} → nicht gefunden")
            all_ok = False
            continue
        pin_ok = expected_pins == 0 or len(sym.pins) == expected_pins
        fp_ok  = not fp_substr or fp_substr in sym.footprint
        status = "OK  " if (pin_ok and fp_ok) else "FAIL"
        if not (pin_ok and fp_ok):
            all_ok = False
        print(f"  {status}  {lib_name}:{part}")
        print(f"         footprint={sym.footprint}")
        print(f"         pins={len(sym.pins)}" + (f" (erwartet {expected_pins})" if expected_pins else ""))
        if sym.datasheet_url:
            print(f"         datasheet={sym.datasheet_url[:70]}")

    print("\n=== lookup_any-Tests ===")
    for part in ["WM8731CLSEFL", "STM32G431CBUx", "BMP280", "SX1276"]:
        sym = lib.lookup_any(part)
        status = "OK  " if sym else "FAIL"
        if not sym:
            all_ok = False
        lib_found = sym.lib_name if sym else "N/A"
        fp = sym.footprint if sym else "N/A"
        print(f"  {status}  lookup_any('{part}') → lib={lib_found}")

    print("\n=== Footprint-Tests ===")
    fp_tests = [
        ("Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.6x5.6mm", True,  49),
        ("Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",                   True,   8),
        ("Package_DFN_QFN:NONEXISTENT_FOOTPRINT",                  False, None),
    ]
    for fp, expect_exists, expect_pads in fp_tests:
        exists = lib.footprint_exists(fp)
        pads   = lib.footprint_pad_count(fp)
        ex_ok  = exists == expect_exists
        pad_ok = expect_pads is None or pads == expect_pads
        status = "OK  " if (ex_ok and pad_ok) else "FAIL"
        if not (ex_ok and pad_ok):
            all_ok = False
        fp_short = fp.split(":")[-1][:45]
        print(f"  {status}  {fp_short}")
        print(f"         exists={exists} (erwartet {expect_exists}), pads={pads} (erwartet {expect_pads})")

    print(f"\n{'=== ALLE TESTS BESTANDEN ===' if all_ok else '=== FEHLER GEFUNDEN ==='}")
    raise SystemExit(0 if all_ok else 1)
