# SPDX-License-Identifier: AGPL-3.0-or-later
"""B14. Footprint Mapper — MPN → KiCad footprint reference + physical size.

Resolves the KiCad footprint string and estimated PCB size for each
component in an HIR dict.  Used by PcbLayoutEngine to plan placement
and generate pad geometry.

Resolution order:
  0. KiCad local library — exact, canonical (when KiCad is installed)
  1. SYMBOL_MAP  — known MPNs with exact KiCad footprint references
  2. FOOTPRINT_FALLBACK table — package-name keywords (SOIC-8, 0402, …)
  3. LLM suggestion — when use_llm=True and the component is unknown
  4. Generic fallback — "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm" (5×5 mm)

All sizes are in millimetres (courtyard dimensions incl. pad clearance).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Package size table (footprint keyword → (width_mm, height_mm))
# ---------------------------------------------------------------------------

_PACKAGE_SIZES: dict[str, tuple[float, float]] = {
    "esp32-wroom-32":    (18.0, 25.4),
    "esp32-wrover":      (18.0, 31.4),
    # ESP32-C3-WROOM-02: actual body 13.2×16.6mm; use courtyard with margin
    "esp32-c3-wroom":    (14.5, 18.0),
    # ESP32-S3-WROOM-1: actual body 18.0×20.0mm; use courtyard with margin
    "esp32-s3-wroom":    (19.5, 21.5),
    "rp2040":            ( 7.0,  7.0),
    "nrf52840":          ( 7.0,  7.0),
    "stm32f103":         ( 8.0,  8.0),
    "lqfp-48":           ( 8.0,  8.0),
    "lqfp-64":           (10.0, 10.0),
    "qfn-56":            (10.0, 10.0),  # courtyard = body(7mm)/2 + pad_overhang(0.5) + pad_long/2(0.75) + clr(0.25) = 5.0mm half → 10mm total
    "aqfn-73":           (10.0, 10.0),  # similar large QFN
    "qfn-32":            ( 5.5,  5.5),
    "qfn-24":            ( 4.5,  4.5),
    "tssop-24":          ( 5.0,  8.0),
    "soic-8":            ( 5.0,  4.0),
    "soic-16":           ( 5.0,  9.0),
    "soic_3.9x4.9":      ( 5.0,  4.0),
    "lga-8":             ( 3.0,  3.0),
    "lga-14":            ( 3.5,  3.5),
    "dfn-6":             ( 3.5,  3.5),
    "dfn-4":             ( 2.5,  2.5),
    "sot-23-5":          ( 3.0,  3.0),
    "sot-23":            ( 3.0,  3.0),
    "sot-25":            ( 3.0,  3.0),
    "sot-223":           ( 7.0,  7.0),
    "0402":              ( 1.2,  0.8),
    "0603":              ( 2.0,  1.2),
    "0805":              ( 2.5,  1.5),
    "1206":              ( 3.5,  2.0),
    "1812":              ( 5.0,  3.5),
    "lqfp-100":          (14.0, 14.0),
    "lqfp-144":          (20.0, 20.0),
    "tqfp-32":           ( 8.0,  8.0),
    "tqfp-64":           (10.0, 10.0),
    "tqfp-100":          (14.0, 14.0),
    "ufqfpn-48":         ( 8.0,  8.0),
    "htssop-16":         ( 5.5,  5.0),
    "ssop-28":           ( 6.0, 10.5),
    "sop-16":            ( 5.0, 10.0),
    "soic-16":           ( 5.0,  9.0),
    "soic-16w":          ( 8.0, 10.0),
    "bga-196":           (12.0, 12.0),
    "to-220":            ( 5.0, 10.0),
    "to-263-5":          ( 9.0, 10.0),
    "do-214ac":          ( 5.0,  4.0),
    "smb":               ( 4.5,  3.5),
    # SMD tactile push-buttons (Alps SKRK/SKRP: 6.0×6.0mm courtyard)
    "sw_push_spst_no_alps_skrk": ( 6.0,  6.0),
    "panasonic_evqpul":  ( 3.5,  3.5),
    # SMD LEDs
    "led_0603":          ( 2.0,  1.2),
    "led_0805":          ( 2.5,  1.5),
    # Power shunt resistors — Vishay WSL2512 series (6.35×3.2mm body)
    "2512":              ( 7.0,  4.0),
    "r_2512":            ( 7.0,  4.0),
    # RF antenna connectors
    "u.fl":              ( 3.5,  3.5),
    "u_fl":              ( 3.5,  3.5),
    "ipex":              ( 3.5,  3.5),
    "sma":               ( 6.5,  6.5),
}

_DEFAULT_SIZE: tuple[float, float] = (5.0, 5.0)


def _size_from_footprint(footprint: str) -> tuple[float, float]:
    """Estimate courtyard size (w, h) from a KiCad footprint reference."""
    fp_lower = footprint.lower()
    for key, size in _PACKAGE_SIZES.items():
        if key in fp_lower:
            return size
    # Try to parse explicit dimensions from footprint name, e.g. "3.9x4.9mm"
    m = re.search(r"(\d+\.?\d*)x(\d+\.?\d*)mm", fp_lower)
    if m:
        try:
            w = float(m.group(1)) + 1.0   # add 1mm courtyard clearance each side
            h = float(m.group(2)) + 1.0
            return (w, h)
        except ValueError:
            pass
    return _DEFAULT_SIZE


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FootprintInfo:
    """Resolved footprint data for one component.

    Attributes:
        mpn:            Manufacturer part number.
        kicad_footprint: KiCad footprint reference ("Library:Name").
        source:         How the footprint was resolved.
        width_mm:       Courtyard width estimate (mm).
        height_mm:      Courtyard height estimate (mm).
        pin_count:      Number of pins (from SymbolDef or estimate).
    """

    mpn: str
    kicad_footprint: str
    source: str          # "symbol_map" | "fallback" | "llm" | "generic"
    width_mm: float = 5.0
    height_mm: float = 5.0
    pin_count: int = 4


# ---------------------------------------------------------------------------
# FootprintMapper
# ---------------------------------------------------------------------------


class FootprintMapper:
    """Resolves KiCad footprint strings and physical sizes for HIR components.

    Usage::

        mapper = FootprintMapper(use_llm=False)
        infos = mapper.resolve_all(hir_dict)
        for comp_id, fp in infos.items():
            print(f"{comp_id}: {fp.kicad_footprint}  ({fp.width_mm}×{fp.height_mm} mm)")
    """

    _GENERIC_FOOTPRINT = "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"

    def __init__(self, use_llm: bool = True) -> None:
        self._use_llm = use_llm
        self._llm_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(
        self,
        mpn: str,
        role: str = "other",
        interface_types: list[str] | None = None,
    ) -> FootprintInfo:
        """Resolve footprint for a single component.

        Args:
            mpn:             Manufacturer part number.
            role:            Component role ("mcu", "sensor", "passive", …).
            interface_types: List of interface strings (["I2C"], ["SPI"], …).

        Returns:
            FootprintInfo with kicad_footprint and physical size.
        """
        interface_types = interface_types or []

        # 0. KiCad local library (canonical, highest priority)
        fp, source, pin_count = self._from_kicad_library(mpn)
        if fp:
            w, h = _size_from_footprint(fp)
            return FootprintInfo(mpn=mpn, kicad_footprint=fp, source=source,
                                 width_mm=w, height_mm=h, pin_count=pin_count)

        # 1. SYMBOL_MAP (exact match)
        fp, source, pin_count = self._from_symbol_map(mpn)
        if fp:
            w, h = _size_from_footprint(fp)
            return FootprintInfo(mpn=mpn, kicad_footprint=fp, source=source,
                                 width_mm=w, height_mm=h, pin_count=pin_count)

        # 2. FOOTPRINT_FALLBACK (keyword match in MPN or package hint)
        fp = self._from_fallback_table(mpn)
        if fp:
            w, h = _size_from_footprint(fp)
            return FootprintInfo(mpn=mpn, kicad_footprint=fp, source="fallback",
                                 width_mm=w, height_mm=h, pin_count=4)

        # 3. LLM suggestion
        if self._use_llm:
            fp = self._llm_suggest_footprint(mpn, role, interface_types)
            if fp:
                w, h = _size_from_footprint(fp)
                return FootprintInfo(mpn=mpn, kicad_footprint=fp, source="llm",
                                     width_mm=w, height_mm=h, pin_count=4)

        # 4. Role-based generic
        fp = self._role_generic(role)
        w, h = _size_from_footprint(fp)
        return FootprintInfo(mpn=mpn, kicad_footprint=fp, source="generic",
                             width_mm=w, height_mm=h, pin_count=4)

    def resolve_all(self, hir_dict: dict[str, Any]) -> dict[str, FootprintInfo]:
        """Resolve footprints for all components in an HIR dict.

        Returns:
            Mapping from component_id → FootprintInfo.
        """
        result: dict[str, FootprintInfo] = {}
        for comp in hir_dict.get("components", []):
            comp_id = comp.get("id", "?")
            mpn = comp.get("mpn", "UNKNOWN")
            role = comp.get("role", "other")
            ifaces = comp.get("interface_types", [])
            result[comp_id] = self.resolve(mpn, role, ifaces)
        return result

    # ------------------------------------------------------------------
    # Internal resolution steps
    # ------------------------------------------------------------------

    def _from_kicad_library(self, mpn: str) -> tuple[str, str, int]:
        """Look up KiCad local library (Tier 0).  Returns (footprint, source, pin_count)."""
        try:
            try:
                from synthesizer.tools.kicad_library import KiCadLibrary, KICAD_AVAILABLE
            except ImportError:
                from tools.kicad_library import KiCadLibrary, KICAD_AVAILABLE  # type: ignore[import]
            if not KICAD_AVAILABLE:
                return ("", "", 0)
            sym = KiCadLibrary().lookup_any(mpn)
            if sym and sym.footprint:
                return (sym.footprint, "kicad", len(sym.pins))
        except Exception:
            pass
        return ("", "", 0)

    def _from_symbol_map(self, mpn: str) -> tuple[str, str, int]:
        """Look up the SYMBOL_MAP.  Returns (footprint, source, pin_count)."""
        try:
            from synth_core.knowledge.symbol_map import SYMBOL_MAP
        except ImportError:
            return ("", "", 0)

        sdef = SYMBOL_MAP.get(mpn)
        if sdef:
            return (sdef.footprint, "symbol_map", len(sdef.pins))
        # Case-insensitive fallback
        mpn_lower = mpn.lower()
        for key, sdef in SYMBOL_MAP.items():
            if key.lower() == mpn_lower:
                return (sdef.footprint, "symbol_map", len(sdef.pins))
        return ("", "", 0)

    def _from_fallback_table(self, mpn: str) -> str:
        """Check FOOTPRINT_FALLBACK and common package-name substrings."""
        try:
            from synth_core.knowledge.symbol_map import FOOTPRINT_FALLBACK
        except ImportError:
            return ""

        # Direct key match
        if mpn in FOOTPRINT_FALLBACK:
            return FOOTPRINT_FALLBACK[mpn]

        # Substring match (e.g. MPN contains "0402", "SOIC-8")
        mpn_upper = mpn.upper()
        for key, fp in FOOTPRINT_FALLBACK.items():
            if key.upper() in mpn_upper:
                return fp
        return ""

    def _role_generic(self, role: str) -> str:
        """Return a reasonable generic footprint for a component role."""
        role_map = {
            "mcu":     "Package_QFP:LQFP-48_7x7mm_P0.5mm",
            "sensor":  "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            "display": "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
            "comms":   "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            "power":   "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
            "passive": "Resistor_SMD:R_0402_1005Metric",
            "other":   "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        }
        return role_map.get(role, self._GENERIC_FOOTPRINT)

    def _llm_suggest_footprint(
        self,
        mpn: str,
        role: str,
        interface_types: list[str],
    ) -> str | None:
        """Ask LLM to suggest a KiCad footprint for an unknown component."""
        if mpn in self._llm_cache:
            return self._llm_cache[mpn]

        try:
            from llm.gateway import get_default_gateway
            from llm.types import TaskType
            gateway = get_default_gateway()
            if not gateway.is_llm_available():
                return None
        except ImportError:
            return None

        try:
            resp = gateway.complete_sync(
                task=TaskType.COMPONENT_SUGGEST,
                messages=[{"role": "user", "content": (
                    f"What is the KiCad 6 footprint reference for: {mpn} ({role}, "
                    f"interfaces: {', '.join(interface_types) or 'unknown'})?\n"
                    "Reply with ONLY the footprint string in format 'Library:FootprintName'. "
                    "Example: 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm'"
                )}],
                temperature=0.1,
                max_tokens=60,
            )
            if resp.skipped or not resp.content:
                return None
            fp = resp.content.strip().strip('"').strip("'")
            # Validate: must contain a colon
            if ":" in fp and len(fp) < 120:
                self._llm_cache[mpn] = fp
                return fp
        except Exception:
            pass
        return None
