# SPDX-License-Identifier: AGPL-3.0-or-later
"""B14. PCB Layout Engine — HIR + footprints → .kicad_pcb.

Generates a KiCad 6 S-expression PCB file with:
  - Component footprints placed on a grid (deterministic fallback)
  - Net definitions derived from HIR bus_contracts
  - Simplified inline SMD pad footprints (valid KiCad 6 format)
  - Board outline (Edge.Cuts rectangle, auto-sized)
  - LLM-boost: when use_llm=True, asks LLM for improved placement

The generated PCB is valid and openable in KiCad 6/7.
Routing (traces) is left to the Autorouter module — this engine
only places components and defines nets/pads.

Layout algorithm (grid fallback):
  - MCU(s):    left column, x=30mm, stacked top-to-bottom
  - Power:     top row, y=15mm, evenly spaced
  - Sensors:   right column, x=board_w-30mm, stacked
  - Passives:  centre column, x=board_w/2, stacked
  - Others:    right column, below sensors
  Board margin: 20mm around outermost component boundary.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from boardsmith_hw.footprint_mapper import FootprintInfo

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Power net constants
# ---------------------------------------------------------------------------

_GND_KW  = ("GND", "VSS", "AGND", "DGND", "PGND")
_3V3_KW  = ("3V3", "VDD", "VCC", "DVDD", "IOVDD", "VOUT", "VS")
_5V_KW   = ("VIN", "5V", "VSUP", "VBUS")
_BUS_KW  = ("SDA", "SCL", "MOSI", "MISO", "SCLK", "SCK", "CS", "TX", "RX")

# Config-pin overrides: exact pin-name (upper) → net name
# These take priority over keyword matching and fix BME280 / sensor config pins.
# Must be checked BEFORE _5V_KW so VREG_VIN → +3V3 (not +5V).
_CONFIG_PIN_EXACT: dict[str, str] = {
    # RP2040: internal LDO input — must be ≤3.3V (NOT +5V)
    "VREG_VIN":  "+3V3",
    "VREG_VOUT": "+3V3",
    # BME280/BMP280: CSB must be tied to VDD for I2C mode
    "CSB":       "+3V3",
    # BME280 I2C address select: SDO/SA0/SAO → GND = addr 0x76
    "SDO":       "GND",
    "SA0":       "GND",
    "SDO/SA0":   "GND",
    "SAO":       "GND",
    # Common enable/reset pins
    "EN":        "+3V3",
    "ENABLE":    "+3V3",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PcbPosition:
    """Component placement on the PCB."""
    x: float              # mm from board origin
    y: float              # mm from board origin
    rotation: float = 0.0  # degrees (0 = no rotation)
    layer: str = "F.Cu"   # "F.Cu" | "B.Cu"


# ---------------------------------------------------------------------------
# PcbLayoutEngine
# ---------------------------------------------------------------------------


class PcbLayoutEngine:
    """Generates a .kicad_pcb S-expression file from HIR + footprint data.

    Usage::

        engine = PcbLayoutEngine(use_llm=False)
        pcb_text = engine.build(hir_dict, footprints)
        Path("output.kicad_pcb").write_text(pcb_text)
    """

    # Layout constants (mm)
    MCU_X: float = 30.0
    SENSOR_X: float = 130.0
    POWER_Y: float = 15.0
    PASSIVE_X: float = 80.0
    COMP_Y_START: float = 30.0
    COMP_Y_STEP: float = 20.0
    BOARD_MARGIN: float = 20.0

    def __init__(self, use_llm: bool = True, routing_available: bool = False) -> None:
        self._use_llm = use_llm
        self._routing_available = routing_available

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        hir_dict: dict[str, Any],
        footprints: dict[str, FootprintInfo],
    ) -> str:
        """Build complete .kicad_pcb text from HIR + resolved footprints.

        Returns:
            String content of a valid KiCad 6 .kicad_pcb file.
        """
        # Grid positions (deterministic fallback)
        positions = self._plan_grid_positions(hir_dict, footprints)

        # LLM-boost: override with LLM suggestions where provided
        if self._use_llm:
            llm_pos = self._llm_plan_positions(hir_dict, footprints)
            if llm_pos:
                for comp_id, pos in llm_pos.items():
                    if comp_id in positions:
                        positions[comp_id] = pos
                log.debug("PCB layout: LLM improved positions for %d components",
                          len(llm_pos))

        # Net table
        nets = self._collect_nets(hir_dict)

        # HIR-based pin→net map for accurate signal assignment
        pin_net_map = self._build_pin_net_map(hir_dict, nets)

        # Board bounds
        board_w, board_h = self._board_bounds(positions, footprints)

        # Ref-designator assignment
        ref_map = self._assign_refs(hir_dict, footprints)

        # Build S-expression
        return self._render(hir_dict, footprints, positions, nets, ref_map,
                            board_w, board_h, pin_net_map)

    # ------------------------------------------------------------------
    # Grid layout planning
    # ------------------------------------------------------------------

    def _plan_grid_positions(
        self,
        hir_dict: dict[str, Any],
        footprints: dict[str, FootprintInfo],
    ) -> dict[str, PcbPosition]:
        """Assign signal-integrity-aware grid positions to all components.

        Signal integrity rules applied:
        - Decoupling capacitors are placed adjacent to their associated IC
          (5 mm offset in y from the IC's centroid) — not in the generic
          passive column, which would create long power-rail stubs.
        - SPI-connected components are placed in a mid-column adjacent to
          the MCU (short MOSI/MISO/SCLK traces).
        - I2C-connected components share a vertical spine at SENSOR_X;
          each device is stacked with even spacing along the same SDA/SCL bus.
        """
        components = hir_dict.get("components", [])
        bus_contracts = hir_dict.get("bus_contracts", [])

        def _right_pad_extent(fp_obj) -> float:
            """Right-most pad edge from component centre (for decap offset).

            For SOIC/SOP/SSOP/TSSOP packages the pads protrude beyond the
            courtyard body boundary listed in fp.width_mm.  We add the actual
            pad overhang so decoupling caps are placed with the correct 1 mm
            physical clearance rather than overlapping the pad.
            """
            if fp_obj is None:
                return 5.0
            hw = fp_obj.width_mm / 2
            fp_u = fp_obj.kicad_footprint.upper()
            if any(k in fp_u for k in ("SOIC", "SOP", "SSOP", "TSSOP")):
                m = re.search(r'_P([\d.]+)mm', fp_obj.kicad_footprint)
                pitch = float(m.group(1)) if m else 1.27
                pad_long = max(1.5, pitch * 1.2)
                return hw + 0.45 + pad_long / 2   # body_hw + overhang + half_pad_long
            return hw

        # Classify buses by type for placement hints
        spi_slave_ids: set[str] = set()
        i2c_slave_ids: set[str] = set()
        for bc in bus_contracts:
            btype = bc.get("bus_type", "")
            slaves = bc.get("slave_ids", [])
            if btype == "SPI":
                spi_slave_ids.update(slaves)
            elif btype == "I2C":
                i2c_slave_ids.update(slaves)

        mcus      = [c for c in components if c.get("role") == "mcu"]
        power_cs  = [c for c in components if c.get("role") == "power"]
        sensors   = [c for c in components if c.get("role") in ("sensor", "comms")]
        passives  = [c for c in components if c.get("role") == "passive"]
        others    = [c for c in components if c.get("role") not in
                     ("mcu", "power", "sensor", "comms", "passive")]

        positions: dict[str, PcbPosition] = {}

        # --- MCUs — left column ---
        y = self.COMP_Y_START
        # (x, y, right_pad_extent) — right_pad_extent used for decoupling cap offset
        mcu_centroids: list[tuple[float, float, float]] = []
        for c in mcus:
            fp = footprints.get(c["id"])
            positions[c["id"]] = PcbPosition(x=self.MCU_X, y=y)
            hw = _right_pad_extent(fp)
            mcu_centroids.append((self.MCU_X, y, hw))
            y += (fp.height_mm if fp else 15.0) + self.COMP_Y_STEP

        # --- Power — top row ---
        x = 60.0
        power_centroids: list[tuple[float, float, float]] = []
        for c in power_cs:
            fp = footprints.get(c["id"])
            positions[c["id"]] = PcbPosition(x=x, y=self.POWER_Y)
            hw = _right_pad_extent(fp)
            power_centroids.append((x, self.POWER_Y, hw))
            x += (fp.width_mm if fp else 8.0) + 15.0

        # --- SPI sensors/comms — mid column adjacent to MCU (short SPI traces) ---
        SPI_X = self.MCU_X + 35.0  # close to MCU for short SPI traces
        spi_comps = [c for c in (sensors + others) if c["id"] in spi_slave_ids]
        y = self.COMP_Y_START
        spi_centroids: dict[str, tuple[float, float, float]] = {}
        for c in spi_comps:
            fp = footprints.get(c["id"])
            positions[c["id"]] = PcbPosition(x=SPI_X, y=y)
            hw = _right_pad_extent(fp)
            spi_centroids[c["id"]] = (SPI_X, y, hw)
            y += (fp.height_mm if fp else 10.0) + self.COMP_Y_STEP

        # --- I2C sensors/comms — right column (I2C spine: shared SDA/SCL bus) ---
        i2c_comps = [c for c in (sensors + others)
                     if c["id"] in i2c_slave_ids and c["id"] not in spi_slave_ids]
        remaining = [c for c in (sensors + others)
                     if c["id"] not in spi_slave_ids and c["id"] not in i2c_slave_ids]
        y = self.COMP_Y_START
        i2c_centroids: dict[str, tuple[float, float, float]] = {}
        for c in (i2c_comps + remaining):
            fp = footprints.get(c["id"])
            positions[c["id"]] = PcbPosition(x=self.SENSOR_X, y=y)
            hw = _right_pad_extent(fp)
            i2c_centroids[c["id"]] = (self.SENSOR_X, y, hw)
            y += (fp.height_mm if fp else 10.0) + self.COMP_Y_STEP

        # --- Passives — signal-integrity aware ---
        # Identify decoupling capacitors: passives whose MPN starts with C_
        # or whose name contains "decoupling"/"bypass"/"100nF"/"10uF".
        # Place them adjacent to the IC they decouple.
        all_ic_centroids: list[tuple[float, float, float]] = (
            mcu_centroids + power_centroids
            + list(spi_centroids.values())
            + list(i2c_centroids.values())
        )

        generic_passives: list[Any] = []
        passive_y = self.COMP_Y_START + 5.0
        decap_offset_y: dict[int, float] = {}  # centroid_idx → next y placement offset

        for c in passives:
            cname = (c.get("name") or c.get("mpn") or "").lower()
            is_decap = (
                any(kw in cname for kw in ("decoupl", "bypass", "100nf", "10uf", "1uf"))
                or c.get("role_hint") == "decoupling"
            )

            if is_decap and all_ic_centroids:
                # Place adjacent to nearest IC — outside its courtyard.
                ic_x, ic_y, ic_hw = all_ic_centroids[0]  # default to first IC (MCU)
                # Find nearest IC by Manhattan distance to passive's natural position
                natural_y = passive_y
                best_dist = float("inf")
                for cx, cy, chw in all_ic_centroids:
                    dist = abs(cy - natural_y) + abs(cx - self.PASSIVE_X)
                    if dist < best_dist:
                        best_dist = dist
                        ic_x, ic_y, ic_hw = cx, cy, chw

                # Stack multiple decaps near same IC using a per-IC y-counter
                ic_key = round(ic_y)
                slot = decap_offset_y.get(ic_key, 0)
                decap_offset_y[ic_key] = slot + 4.0  # 4.0 mm between stacked decaps (avoid silk overlap)

                fp = footprints.get(c["id"])
                h = (fp.height_mm if fp else 2.0)
                # Cap half-extent in X after 90° rotation = original height / 2
                cap_half_x = max((fp.height_mm if fp else 1.0), (fp.width_mm if fp else 1.0)) / 2
                # Place cap outside IC courtyard: ic_half_width + cap_half + 1mm gap
                x_offset = ic_hw + cap_half_x + 1.0
                positions[c["id"]] = PcbPosition(
                    x=ic_x + x_offset,   # outside IC courtyard
                    y=ic_y + slot,
                    rotation=90.0,        # rotated for short VDD trace
                )
                passive_y += h + 4.0
            else:
                generic_passives.append(c)

        # Non-decoupling passives go in the centre column
        for c in generic_passives:
            fp = footprints.get(c["id"])
            positions[c["id"]] = PcbPosition(x=self.PASSIVE_X, y=passive_y)
            passive_y += (fp.height_mm if fp else 3.0) + 8.0

        return positions

    # ------------------------------------------------------------------
    # Net collection
    # ------------------------------------------------------------------

    def _collect_nets(
        self,
        hir_dict: dict[str, Any],
    ) -> list[tuple[int, str]]:
        """Build net list: [(net_id, net_name), …].

        Always includes net 0 ("") plus GND, +3V3, +5V.
        Adds all named nets from HIR nets[] plus bus signal aliases
        from bus_contracts for backward compatibility.
        """
        net_names: list[str] = []

        # Fixed power nets
        for n in ("GND", "+3V3", "+5V"):
            net_names.append(n)

        # Normalise bare power rail names to KiCad-style "+…" names so
        # passives and ICs share the same copper net.
        _POWER_NET_NORMALISE = {
            "3V3": "+3V3", "3V3_REG": "+3V3",
            "5V": "+5V",   "VIN_5V": "+5V",
            "GND": "GND",
        }

        # All nets from HIR nets[] — these carry the actual connectivity
        for net in hir_dict.get("nets", []):
            name = net.get("name", "")
            name = _POWER_NET_NORMALISE.get(name, name)
            if name and name not in net_names:
                net_names.append(name)

        # Bus signal aliases from bus_contracts — only add generic names
        # (SDA, SCL, …) if the HIR doesn't already define a qualified net
        # that contains the signal name (e.g. "i2c0_SDA" covers "SDA").
        for bc in hir_dict.get("bus_contracts", []):
            bt = bc.get("bus_type", "")
            sigs = {
                "I2C": ("SDA", "SCL"),
                "SPI": ("MOSI", "MISO", "SCLK", "CS"),
                "UART": ("TX", "RX"),
            }.get(bt, ())
            for sig in sigs:
                # Skip if a qualified HIR net already covers this signal
                # e.g. "i2c0_SDA" already exists → don't add bare "SDA"
                already_covered = any(
                    sig in existing_name and existing_name != sig
                    for existing_name in net_names
                )
                if not already_covered and sig not in net_names:
                    net_names.append(sig)

        # Return with IDs (0 = empty net, 1-based for named nets)
        return [(0, "")] + [(i + 1, name) for i, name in enumerate(net_names)]

    # ------------------------------------------------------------------
    # HIR-based pin → net mapping
    # ------------------------------------------------------------------

    def _build_pin_net_map(
        self,
        hir_dict: dict[str, Any],
        nets: list[tuple[int, str]],
    ) -> dict[tuple[str, str], tuple[int, str]]:
        """Build (comp_id, pin_name) → (net_id, net_name) from HIR nets[].

        This replicates the pattern from kicad_exporter.py and provides
        accurate net assignment for all signal pins, not just power/bus
        keywords.
        """
        _POWER_NET_NORMALISE = {
            "3V3": "+3V3", "3V3_REG": "+3V3",
            "5V": "+5V",   "VIN_5V": "+5V",
            "GND": "GND",
        }
        pin_map: dict[tuple[str, str], tuple[int, str]] = {}
        for net in hir_dict.get("nets", []):
            net_name = _POWER_NET_NORMALISE.get(net.get("name", ""), net.get("name", ""))
            nid = self._net_id(net_name, nets)
            if not nid:
                continue
            for pin_ref in net.get("pins", []):
                cid = pin_ref.get("component_id", "")
                pname = str(pin_ref.get("pin_name", ""))
                if cid and pname:
                    pin_map[(cid, pname)] = (nid, net_name)
                    pin_map[(cid, pname.upper())] = (nid, net_name)
        return pin_map

    def _net_id(
        self,
        net_name: str,
        nets: list[tuple[int, str]],
    ) -> int:
        """Return net ID for a name, or 0 if not found."""
        for nid, name in nets:
            if name == net_name:
                return nid
        return 0

    def _pin_net(
        self,
        pin_name: str,
        nets: list[tuple[int, str]],
    ) -> tuple[int, str]:
        """Map a pin name to (net_id, net_name) based on signal keywords.

        Only matches power keywords by substring (GND, VDD always valid).
        Bus signals are matched as whole tokens (split on ``/``, ``_``, digits)
        to prevent false positives like "SCL" matching inside "SCLK".
        """
        pn = pin_name.upper()
        # Config-pin overrides — exact match, checked BEFORE keyword fallbacks
        if pn in _CONFIG_PIN_EXACT:
            net_name = _CONFIG_PIN_EXACT[pn]
            nid = self._net_id(net_name, nets)
            return (nid, net_name)
        if any(k in pn for k in _GND_KW):
            nid = self._net_id("GND", nets)
            return (nid, "GND")
        if any(k in pn for k in _5V_KW):
            nid = self._net_id("+5V", nets)
            return (nid, "+5V")
        if any(k in pn for k in _3V3_KW):
            nid = self._net_id("+3V3", nets)
            return (nid, "+3V3")
        # Split pin name into tokens for exact bus signal matching
        tokens = set(re.split(r'[/_\s]+', pn))
        # Check longest signals first to prefer SCLK over SCK
        for bus_sig in ("SCLK", "MOSI", "MISO", "SDA", "SCL", "SCK", "CS", "TX", "RX"):
            if bus_sig in tokens:
                # Prefer qualified HIR net (e.g. "i2c0_SDA") over bare "SDA"
                for nid_q, name_q in nets:
                    if nid_q and bus_sig in name_q and name_q != bus_sig:
                        return (nid_q, name_q)
                nid = self._net_id(bus_sig, nets)
                if nid:
                    return (nid, bus_sig)
        return (0, "")

    # ------------------------------------------------------------------
    # Board sizing
    # ------------------------------------------------------------------

    def _board_bounds(
        self,
        positions: dict[str, PcbPosition],
        footprints: dict[str, FootprintInfo],
    ) -> tuple[float, float]:
        """Compute board width and height from component placements."""
        if not positions:
            return (100.0, 80.0)

        max_x = max_y = 0.0
        for comp_id, pos in positions.items():
            fp = footprints.get(comp_id)
            w = (fp.width_mm / 2) if fp else 5.0
            h = (fp.height_mm / 2) if fp else 5.0
            max_x = max(max_x, pos.x + w)
            max_y = max(max_y, pos.y + h)

        return (
            max_x + self.BOARD_MARGIN,
            max_y + self.BOARD_MARGIN,
        )

    # ------------------------------------------------------------------
    # Phase 23.4: Net classes — trace widths per signal type
    # ------------------------------------------------------------------

    # Net class trace width constants (mm)
    NC_SIGNAL_WIDTH: float = 0.25
    NC_POWER_WIDTH: float = 0.40
    NC_HIGH_CURRENT_WIDTH: float = 0.80
    NC_CLEARANCE: float = 0.15   # fine-pitch QFN-56 (0.4mm pitch) needs ≤0.16mm gap → 0.15mm clearance

    def _build_net_classes(
        self,
        hir_dict: dict[str, Any],
        nets: list[tuple[int, str]],
    ) -> list[str]:
        """Generate KiCad 6 net class S-expressions.

        Three classes:
        - **Default** (signal): 0.25 mm traces, 0.20 mm clearance
        - **Power**: 0.40 mm traces, 0.25 mm clearance (GND, +3V3, +5V)
        - **HighCurrent**: 0.80 mm traces, 0.30 mm clearance (motor, heater)

        Net assignment is based on net name keywords.
        """
        # Classify nets into classes
        power_nets: list[str] = []
        high_current_nets: list[str] = []
        signal_nets: list[str] = []

        for nid, name in nets:
            if not name:
                continue
            upper = name.upper()
            if any(k in upper for k in ("MOTOR", "HEATER", "RELAY", "12V")):
                high_current_nets.append(name)
            elif any(k in upper for k in _GND_KW + _3V3_KW + _5V_KW):
                power_nets.append(name)
            else:
                signal_nets.append(name)

        out: list[str] = []

        # Default net class (signal)
        out.append('  (net_class "Default" "Signal traces"')
        out.append(f'    (clearance {self.NC_CLEARANCE})')
        out.append(f'    (trace_width {self.NC_SIGNAL_WIDTH})')
        out.append(f'    (via_dia 0.6) (via_drill 0.3)')
        out.append(f'    (uvia_dia 0.3) (uvia_drill 0.1)')
        for name in signal_nets:
            out.append(f'    (add_net "{_esc(name)}")')
        out.append('  )')

        # Power net class — use same clearance as Default so fine-pitch QFN power pads don't violate
        out.append('  (net_class "Power" "Power rails"')
        out.append(f'    (clearance {self.NC_CLEARANCE})')
        out.append(f'    (trace_width {self.NC_POWER_WIDTH})')
        out.append(f'    (via_dia 0.8) (via_drill 0.4)')
        out.append(f'    (uvia_dia 0.3) (uvia_drill 0.1)')
        for name in power_nets:
            out.append(f'    (add_net "{_esc(name)}")')
        out.append('  )')

        # High-current net class
        if high_current_nets:
            out.append('  (net_class "HighCurrent" "High-current paths (motor, heater)"')
            out.append(f'    (clearance 0.30)')
            out.append(f'    (trace_width {self.NC_HIGH_CURRENT_WIDTH})')
            out.append(f'    (via_dia 1.0) (via_drill 0.5)')
            out.append(f'    (uvia_dia 0.3) (uvia_drill 0.1)')
            for name in high_current_nets:
                out.append(f'    (add_net "{_esc(name)}")')
            out.append('  )')

        return out

    # ------------------------------------------------------------------
    # Ref-designator assignment
    # ------------------------------------------------------------------

    def _assign_refs(
        self,
        hir_dict: dict[str, Any],
        footprints: dict[str, FootprintInfo],
    ) -> dict[str, str]:
        """Return {comp_id: ref_designator} e.g. {"U1": "U1", "R1": "R1"}."""
        try:
            from synth_core.knowledge.symbol_map import SYMBOL_MAP, _generic_symbol
        except ImportError:
            return {c["id"]: f"U{i+1}"
                    for i, c in enumerate(hir_dict.get("components", []))}

        ref_map: dict[str, str] = {}
        ref_ctr: dict[str, int] = {}
        for comp in hir_dict.get("components", []):
            mpn  = comp.get("mpn", "UNKNOWN")
            role = comp.get("role", "other")
            ifaces = comp.get("interface_types", [])
            sdef = SYMBOL_MAP.get(mpn) or _generic_symbol(mpn, role, ifaces)
            prefix = sdef.ref_prefix
            ref_ctr[prefix] = ref_ctr.get(prefix, 1)
            ref_map[comp["id"]] = f"{prefix}{ref_ctr[prefix]}"
            ref_ctr[prefix] += 1
        return ref_map

    # ------------------------------------------------------------------
    # S-expression renderer
    # ------------------------------------------------------------------

    def _uid(self) -> str:
        return str(uuid.uuid4())

    def _render(
        self,
        hir_dict: dict[str, Any],
        footprints: dict[str, FootprintInfo],
        positions: dict[str, PcbPosition],
        nets: list[tuple[int, str]],
        ref_map: dict[str, str],
        board_w: float,
        board_h: float,
        pin_net_map: dict[tuple[str, str], tuple[int, str]] | None = None,
    ) -> str:
        lines: list[str] = []

        # --- Header ---
        lines.append('(kicad_pcb (version 20221018) (generator "boardsmith-fw")')
        lines.append("")
        lines.append("  (general")
        lines.append("    (thickness 1.6)")
        lines.append("    (legacy_teardrops no))")
        lines.append("")
        lines.append('  (paper "A4")')
        lines.append("")

        # --- Layers ---
        lines.append("  (layers")
        for layer in _KICAD_LAYERS:
            lines.append(f"    {layer}")
        lines.append("  )")
        lines.append("")

        # --- Setup + Net Classes (Phase 23.4) ---
        lines.append("  (setup")
        lines.append("    (pad_to_mask_clearance 0)")
        lines.append("    (stackup")
        lines.append('      (layer "F.Cu" (type "copper"))')
        lines.append('      (layer "dielectric 1" (type "core") (thickness 1.6))')
        lines.append('      (layer "B.Cu" (type "copper"))')
        lines.append("    )")
        lines.append("  )")
        lines.append("")

        # Net classes: Signal, Power, High-Current
        net_classes = self._build_net_classes(hir_dict, nets)
        for nc in net_classes:
            lines.append(nc)
        lines.append("")

        # --- Nets ---
        for nid, name in nets:
            lines.append(f'  (net {nid} "{_esc(name)}")')
        lines.append("")

        # --- Footprints ---
        for comp in hir_dict.get("components", []):
            comp_id = comp["id"]
            mpn     = comp.get("mpn", "UNKNOWN")
            role    = comp.get("role", "other")
            fp_info = footprints.get(comp_id)
            pos     = positions.get(comp_id, PcbPosition(50, 50))
            ref     = ref_map.get(comp_id, comp_id)
            lines.append(self._footprint_sexp(
                comp, mpn, role, fp_info, pos, ref, nets,
                pin_net_map=pin_net_map,
            ))

        # --- Board edge ---
        lines.append(self._board_edge(board_w, board_h))
        lines.append("")

        # --- GND copper fill zones (Phase 23.2) ---
        lines.append(self._gnd_zones(board_w, board_h, nets))
        lines.append("")

        # --- Stitching vias (Phase 23.2) — only when routing is available ---
        # Stitching vias connect F.Cu/B.Cu GND planes but require zone fill
        # to be meaningful.  Without routing, they produce via_dangling warnings.
        if self._routing_available:
            lines.append(self._stitching_vias(board_w, board_h, nets))
            lines.append("")

        # --- Silkscreen: board name + revision (Phase 23.5) ---
        system_name = hir_dict.get("system_name", "Boardsmith Board")
        lines.append(self._board_silkscreen(system_name, board_w, board_h))
        lines.append("")

        lines.append(")")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Footprint S-expression
    # ------------------------------------------------------------------

    def _footprint_sexp(
        self,
        comp: dict[str, Any],
        mpn: str,
        role: str,
        fp_info: FootprintInfo | None,
        pos: PcbPosition,
        ref: str,
        nets: list[tuple[int, str]],
        pin_net_map: dict[tuple[str, str], tuple[int, str]] | None = None,
    ) -> str:
        """Generate a single footprint S-expression block."""
        fp_ref = fp_info.kicad_footprint if fp_info else "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
        w = fp_info.width_mm  if fp_info else 5.0
        h = fp_info.height_mm if fp_info else 5.0
        cx, cy = pos.x, pos.y
        layer = pos.layer
        rot   = pos.rotation
        comp_id = comp["id"]

        # Derive pins from SYMBOL_MAP or generic
        pins = self._get_pins(mpn, role, comp.get("interface_types", []))

        out: list[str] = []
        out.append(f'  (footprint "{_esc(fp_ref)}" (layer "{layer}")')
        out.append(f'    (at {cx:.2f} {cy:.2f} {rot:.0f})')
        out.append(f'    (descr "{_esc(mpn)}")')
        out.append(f'    (uuid "{self._uid()}")')
        out.append(f'    (property "Reference" "{_esc(ref)}" (at 0 {-(h/2 + 1.5):.2f} 0)')
        out.append(f'      (effects (font (size 1 1))))')
        out.append(f'    (property "Value" "{_esc(mpn)}" (at 0 {h/2 + 1.5:.2f} 0)')
        out.append(f'      (effects (font (size 1 1))))')

        # Compute courtyard size — for QFN/DFN/QFP packages the pads extend well
        # beyond the body edge, so the courtyard must cover them
        # (pad_center + half_pad + 0.25mm clearance margin).
        fp_up_cyd = fp_ref.upper()
        if "QFN" in fp_up_cyd or "DFN" in fp_up_cyd or "QFP" in fp_up_cyd:
            # Parse real body dimensions from footprint name ("_7x7mm")
            m_body_cyd = re.search(r'_(\d+\.?\d*)x(\d+\.?\d*)mm', fp_ref)
            rbw = float(m_body_cyd.group(1)) if m_body_cyd else (w - 0.5)
            rbh = float(m_body_cyd.group(2)) if m_body_cyd else (h - 0.5)
            # Pad center: body_edge/2 + 0.5mm overhang; pad_long = 1.5mm
            cyd_hw = rbw / 2 + 0.5 + 0.75 + 0.25   # pad centre + half_pad + clearance
            cyd_hh = rbh / 2 + 0.5 + 0.75 + 0.25
            # Body outline (Fab) = actual body, Silkscreen = body + margin
            fab_hw, fab_hh = rbw / 2, rbh / 2
        else:
            cyd_hw, cyd_hh = w / 2, h / 2
            fab_hw, fab_hh = w / 2, h / 2

        # Courtyard
        out.append(f'    (fp_rect (start {-cyd_hw:.2f} {-cyd_hh:.2f}) (end {cyd_hw:.2f} {cyd_hh:.2f})')
        out.append(f'      (layer "F.CrtYd") (width 0.05))')
        # Fab outline
        out.append(f'    (fp_rect (start {-fab_hw:.2f} {-fab_hh:.2f}) (end {fab_hw:.2f} {fab_hh:.2f})')
        out.append(f'      (layer "F.Fab") (width 0.1))')
        # Silkscreen outline (slightly outside fab body)
        silk_margin = 0.15  # mm outside body
        silk_hw = fab_hw + silk_margin
        silk_hh = fab_hh + silk_margin
        out.append(f'    (fp_rect (start {-silk_hw:.2f} {-silk_hh:.2f})'
                   f' (end {silk_hw:.2f} {silk_hh:.2f})')
        out.append(f'      (layer "F.SilkS") (width 0.12))')
        # Pin-1 marker on silkscreen
        pin1_x = -(fab_hw + silk_margin + 0.3)
        pin1_y = -(fab_hh)
        out.append(f'    (fp_circle (center {pin1_x:.2f} {pin1_y:.2f}) (end {pin1_x + 0.2:.2f} {pin1_y:.2f})')
        out.append(f'      (layer "F.SilkS") (width 0.12))')

        # SMD pads — pass fp_ref so package-specific generators can fire
        pad_lines = self._make_pads(pins, w, h, nets, role,
                                    comp_id=comp_id, pin_net_map=pin_net_map,
                                    fp_ref=fp_ref)
        out.extend(pad_lines)

        out.append("  )")
        return "\n".join(out)

    def _get_pins(self, mpn: str, role: str, ifaces: list[str]) -> list[dict]:
        """Return pin list [{name, number, side, type}, …] for a component."""
        try:
            from synth_core.knowledge.symbol_map import SYMBOL_MAP, _generic_symbol, PinDef
        except ImportError:
            return [
                {"name": "GND", "number": "1", "side": "left",  "type": "power_in"},
                {"name": "VDD", "number": "2", "side": "left",  "type": "power_in"},
            ]

        sdef = SYMBOL_MAP.get(mpn) or _generic_symbol(mpn, role, ifaces)
        return [
            {"name": p.name, "number": p.number,
             "side": p.side,  "type": p.type}
            for p in sdef.pins
        ]

    def _resolve_pin_net(
        self,
        pin_name: str,
        nets: list[tuple[int, str]],
        comp_id: str = "",
        pin_net_map: dict[tuple[str, str], tuple[int, str]] | None = None,
    ) -> tuple[int, str]:
        """Resolve net for a pin: first try HIR pin_net_map, then keyword fallback.

        The HIR records GPIO numbers as pin_name (e.g. "21") while the symbol
        has pin names like "IO21/SDA".  When the direct lookup fails, we extract
        embedded GPIO numbers from the pin name and retry.
        """
        if pin_net_map and comp_id:
            # Try exact match, then uppercase match
            hit = pin_net_map.get((comp_id, pin_name))
            if hit:
                return hit
            hit = pin_net_map.get((comp_id, pin_name.upper()))
            if hit:
                return hit
            # Extract GPIO numbers from composite pin names like "IO21/SDA",
            # "GP19", "PA4" and try matching against HIR pin_name ("21", "GP19")
            for token in re.split(r'[/_]', pin_name):
                # "IO21" → "21", "GP19" → "GP19", "SDA" → skip
                gpio_num = re.sub(r'^(?:IO|GPIO)', '', token.upper())
                if gpio_num and gpio_num != token.upper():
                    hit = pin_net_map.get((comp_id, gpio_num))
                    if hit:
                        return hit
                # Also try raw token (handles "GP19", "PA4")
                hit = pin_net_map.get((comp_id, token))
                if not hit:
                    hit = pin_net_map.get((comp_id, token.upper()))
                if hit:
                    return hit
        # Signal-name scan: last-resort fallback when GPIO names in HIR don't
        # match symbol pin names (e.g. HIR "PA7" vs symbol "PB5/MOSI", or
        # HIR net "spi0_SCK" vs symbol pin "PB3/SCLK").
        # Token length >= 3 prevents two-letter port prefixes (PA, PB, IO)
        # from false-matching power net abbreviations.
        #
        # Known clock-signal aliases normalised before matching:
        #   SCLK → SCK, CLK → SCK
        _SIGNAL_ALIASES: dict[str, str] = {"SCLK": "SCK", "CLK": "SCK"}
        if pin_net_map and comp_id:
            raw_tokens = {t for t in re.split(r'[/_]', pin_name.upper()) if len(t) >= 3}
            # Expand with known aliases so SCLK also searches as SCK
            tokens_up = raw_tokens | {_SIGNAL_ALIASES.get(t, t) for t in raw_tokens}
            pn_up = pin_name.upper()
            for (cid, _pn), (nid, nname) in pin_net_map.items():
                if cid != comp_id or not nid:
                    continue
                nname_up = nname.upper()
                # Strategy A: any (aliased) pin token appears in the net name
                if any(tok in nname_up for tok in tokens_up):
                    return (nid, nname)
                # Strategy B: any net-name token appears in the pin name
                net_tokens = {t for t in re.split(r'[_\d]', nname_up) if len(t) >= 3}
                if any(ntok in pn_up for ntok in net_tokens):
                    return (nid, nname)
        # Keyword-based fallback for power pins and generic bus signals
        return self._pin_net(pin_name, nets)

    def _load_kicad_pads(
        self,
        fp_ref: str,
        pins: list[dict],
        nets: list[tuple[int, str]],
        comp_id: str,
        pin_net_map: dict[tuple[str, str], tuple[int, str]] | None,
    ) -> list[str] | None:
        """Load real pad geometry from a KiCad .kicad_mod library file.

        Returns list of pad S-expression strings if the library file exists and
        contains parseable pads, or None to signal algorithmic fallback.

        Skips np_thru_hole (mechanical/non-plated) pads — no solder, no net.
        Imports are lazy so BOARDSMITH_NO_LLM=1 stays import-clean.
        """
        if not fp_ref or ":" not in fp_ref:
            return None
        try:
            from pathlib import Path as _Path
            from synth_core.hir_bridge.kicad_parser import _tokenize, _parse_sexpr
        except ImportError:
            return None

        lib_name, fp_name = fp_ref.split(":", 1)
        fp_path = (
            _Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
            / f"{lib_name}.pretty"
            / f"{fp_name}.kicad_mod"
        )
        if not fp_path.is_file():
            return None

        try:
            text = fp_path.read_text(encoding="utf-8", errors="replace")
            tokens = _tokenize(text)
            tree, _ = _parse_sexpr(tokens, 0)
        except Exception:
            return None

        if not isinstance(tree, list) or not tree:
            return None

        # Build pad-number -> pin dict for net lookup
        pin_by_num: dict[str, dict] = {str(p["number"]): p for p in pins}

        pad_strings: list[str] = []
        for node in tree:
            if not isinstance(node, list) or not node or node[0] != "pad":
                continue
            if len(node) < 4:
                continue

            pad_num = str(node[1]).strip('"')
            pad_type = str(node[2])   # smd | thru_hole | np_thru_hole
            pad_shape = str(node[3])  # rect | circle | oval | roundrect | trapezoid

            # Skip non-plated mechanical pads (no solder, no net)
            if pad_type == "np_thru_hole":
                continue

            # Extract position
            at_x, at_y = 0.0, 0.0
            for sub in node[4:]:
                if isinstance(sub, list) and sub and sub[0] == "at":
                    try:
                        at_x = float(sub[1])
                        at_y = float(sub[2]) if len(sub) > 2 else 0.0
                    except (IndexError, ValueError):
                        pass
                    break

            # Extract size
            pad_w, pad_h = 1.0, 1.0
            for sub in node[4:]:
                if isinstance(sub, list) and sub and sub[0] == "size":
                    try:
                        pad_w = float(sub[1])
                        pad_h = float(sub[2]) if len(sub) > 2 else pad_w
                    except (IndexError, ValueError):
                        pass
                    break

            # Extract layers (preserve from library)
            layers: list[str] = []
            for sub in node[4:]:
                if isinstance(sub, list) and sub and sub[0] == "layers":
                    layers = [str(x).strip('"') for x in sub[1:] if x]
                    break
            if not layers:
                layers = ["F.Cu", "F.Paste", "F.Mask"]
            layers_str = " ".join(f'"{lyr}"' for lyr in layers)

            # Resolve net for this pad via pin lookup
            nid, nname = self._pad_net_by_num(pad_num, pin_by_num, nets, comp_id, pin_net_map)
            net_str = f' (net {nid} "{_esc(nname)}")' if nid else ""

            if pad_type == "thru_hole":
                drill_d = max(0.30, round(min(pad_w, pad_h) * 0.5, 2))
                pad_strings.append(
                    f'    (pad "{_esc(pad_num)}" thru_hole {pad_shape}'
                    f' (at {at_x:.3f} {at_y:.3f} 0)'
                    f' (size {pad_w:.2f} {pad_h:.2f})'
                    f' (drill {drill_d:.2f})'
                    f' (layers {layers_str})'
                    f'{net_str} (uuid "{self._uid()}"))'
                )
            else:
                pad_strings.append(
                    f'    (pad "{_esc(pad_num)}" {pad_type} {pad_shape}'
                    f' (at {at_x:.3f} {at_y:.3f} 0)'
                    f' (size {pad_w:.2f} {pad_h:.2f})'
                    f' (layers {layers_str})'
                    f'{net_str} (uuid "{self._uid()}"))'
                )

        return pad_strings if pad_strings else None

    def _make_pads(
        self,
        pins: list[dict],
        body_w: float,
        body_h: float,
        nets: list[tuple[int, str]],
        role: str,
        comp_id: str = "",
        pin_net_map: dict[tuple[str, str], tuple[int, str]] | None = None,
        fp_ref: str = "",
    ) -> list[str]:
        """Dispatch to package-specific pad generator based on footprint name."""
        # Try loading real pad geometry from KiCad library first.
        # Falls back to algorithmic generators if library file unavailable.
        real_pads = self._load_kicad_pads(fp_ref, pins, nets, comp_id, pin_net_map)
        if real_pads is not None:
            return real_pads

        # Passives: 2-pad horizontal layout
        if role == "passive":
            return self._make_passive_pads(pins, body_w, nets,
                                           comp_id=comp_id,
                                           pin_net_map=pin_net_map)

        fp_up = fp_ref.upper()
        # Build pad-number → pin-dict lookup from symbol definition
        pin_by_num: dict[str, dict] = {str(p["number"]): p for p in pins}

        # Dispatch to package-specific generators
        # QFP/LQFP/TQFP use the same 4-sided layout as QFN/DFN
        if "QFN" in fp_up or "DFN" in fp_up or "QFP" in fp_up:
            return self._make_qfn_pads(fp_ref, body_w, body_h,
                                       nets, pin_by_num, comp_id, pin_net_map)
        if "TO-92" in fp_up:
            return self._make_to92_pads(nets, pin_by_num, comp_id, pin_net_map)
        if "SOT-223" in fp_up:
            return self._make_sot223_pads(nets, pin_by_num, comp_id, pin_net_map)
        if "LGA" in fp_up:
            return self._make_lga_pads(fp_ref, body_w, body_h,
                                       nets, pin_by_num, comp_id, pin_net_map)
        if any(x in fp_up for x in ("SOIC", "SOP", "SSOP", "TSSOP")):
            return self._make_soic_pads(fp_ref, body_w, body_h,
                                        nets, pin_by_num, comp_id, pin_net_map)

        # Generic fallback: left/right two-side layout
        return self._make_2side_pads(pins, body_w, body_h, nets,
                                     comp_id, pin_net_map)

    # ------------------------------------------------------------------
    # Package-specific pad generators
    # ------------------------------------------------------------------

    def _pad_net_by_num(
        self,
        pad_num: str,
        pin_by_num: dict[str, dict],
        nets: list[tuple[int, str]],
        comp_id: str,
        pin_net_map: dict[tuple[str, str], tuple[int, str]] | None,
    ) -> tuple[int, str]:
        """Resolve net for a physical pad number via symbol pin lookup."""
        p = pin_by_num.get(pad_num)
        if p:
            # "GND2", "GND3", … → normalise to "GND"
            raw = p["name"]
            norm = re.sub(r'\d+$', '', raw) if re.match(r'^(GND|DVDD|IOVDD|VDD)', raw) else raw
            nid, nname = self._resolve_pin_net(norm, nets, comp_id, pin_net_map)
            if nid:
                return nid, nname
            # Also try with original name
            return self._resolve_pin_net(raw, nets, comp_id, pin_net_map)
        return (0, "")

    def _smd_pad(self, num: str, x: float, y: float,
                 pw: float, ph: float, nid: int, nname: str) -> str:
        """Return a KiCad SMD pad S-expression."""
        net_str = f' (net {nid} "{_esc(nname)}")' if nid else ""
        return (f'    (pad "{_esc(num)}" smd rect'
                f' (at {x:.3f} {y:.3f} 0)'
                f' (size {pw:.2f} {ph:.2f})'
                f' (layers "F.Cu" "F.Paste" "F.Mask")'
                f'{net_str})')

    def _make_qfn_pads(
        self,
        fp_ref: str,
        body_w: float,
        body_h: float,
        nets: list[tuple[int, str]],
        pin_by_num: dict[str, dict],
        comp_id: str,
        pin_net_map: dict[tuple[str, str], tuple[int, str]] | None,
    ) -> list[str]:
        """Physically accurate QFN/DFN/QFP/LQFP pad layout — all N pads on 4 sides + EP."""
        # Match QFN, DFN, QFP, LQFP, TQFP, UFQFPN, etc.
        m_n = re.search(r'(?:[QD]FN|[LTU]?QFP|UFQFPN)-?(\d+)', fp_ref, re.IGNORECASE)
        n_total = int(m_n.group(1)) if m_n else 16
        n_per_side = max(1, n_total // 4)

        m_p = re.search(r'_P([\d.]+)mm', fp_ref)
        pitch = float(m_p.group(1)) if m_p else 0.5

        # Parse actual body size from _WxHmm (e.g. "_7x7mm") FIRST so that
        # the EP fallback can use real_bw/real_bh rather than footprint_mapper
        # body_w/body_h (which includes courtyard margin and is too large).
        m_body = re.search(r'_(\d+\.?\d*)x(\d+\.?\d*)mm', fp_ref)
        real_bw = float(m_body.group(1)) if m_body else max(1.0, body_w - 0.5)
        real_bh = float(m_body.group(2)) if m_body else max(1.0, body_h - 0.5)

        # Parse EP dimensions from EPWxHmm (e.g. "EP5.6x5.6mm").
        # Fall back to real body size minus pad overhang — NOT body_w from
        # the footprint_mapper courtyard, which is oversized and causes the
        # EP to extend beyond the chip body and overlap signal pads.
        m_ep = re.search(r'EP([\d.]+)x([\d.]+)mm', fp_ref, re.IGNORECASE)
        ep_w = float(m_ep.group(1)) if m_ep else max(1.0, real_bw - 2.5)
        ep_h = float(m_ep.group(2)) if m_ep else max(1.0, real_bh - 2.5)

        # Pad dimensions: long side perpendicular to package edge.
        # Scale pad_long with pitch to prevent EP clearance violations on
        # small packages (e.g. TDFN-16 at 0.5mm pitch needs shorter pads).
        _clr = 0.16  # min clearance gap (0.15 + 0.01 margin)
        pad_long  = min(1.5, max(0.6, pitch * 2.0))
        pad_short = max(0.15, pitch * 0.6)  # mm, parallel to edge
        overhang  = 0.50           # pad center extends this far beyond body edge

        hw = real_bw / 2
        hh = real_bh / 2
        span = (n_per_side - 1) * pitch  # distance from first to last pad

        # Cap EP to ensure signal pads maintain ≥0.15mm clearance from EP edge.
        # The closest signal pad's inner edge = hh + overhang - pad_long/2.
        # EP must not extend beyond that minus the clearance gap.
        _max_ep_half = min(hw, hh) + overhang - pad_long - _clr
        if _max_ep_half > 0:
            ep_w = min(ep_w, max(1.0, 2 * _max_ep_half))
            ep_h = min(ep_h, max(1.0, 2 * _max_ep_half))

        # Cap n_per_side to prevent corner-pad overlap between adjacent sides.
        # When span/2 > (hw + overhang) - pad_long/2 - pad_short/2 - clearance,
        # the last pad on the west side enters the south side's territory,
        # and those two pads' extents overlap (long+short dimensions collide).
        # No-overlap condition: span/2 <= (hw + overhang) - pad_long/2 - pad_short/2 - gap
        _max_half_span = min(hw, hh) + overhang - pad_long / 2 - pad_short / 2 - _clr
        if _max_half_span > 0 and span / 2 > _max_half_span:
            n_per_side = max(1, 1 + int(2 * _max_half_span / pitch))
            span = (n_per_side - 1) * pitch

        out: list[str] = []

        def _net(pnum: str) -> tuple[int, str]:
            return self._pad_net_by_num(pnum, pin_by_num, nets, comp_id, pin_net_map)

        # West side: pads 1..n/4, top→bottom (y increases in KiCad)
        x_w = -(hw + overhang)
        for i in range(n_per_side):
            pnum = str(1 + i)
            y = -span / 2 + i * pitch
            nid, nn = _net(pnum)
            out.append(self._smd_pad(pnum, x_w, y, pad_long, pad_short, nid, nn))

        # South side: pads n/4+1..n/2, left→right (x increases)
        y_s = hh + overhang
        for i in range(n_per_side):
            pnum = str(n_per_side + 1 + i)
            x = -span / 2 + i * pitch
            nid, nn = _net(pnum)
            out.append(self._smd_pad(pnum, x, y_s, pad_short, pad_long, nid, nn))

        # East side: pads n/2+1..3n/4, bottom→top (y decreases)
        x_e = hw + overhang
        for i in range(n_per_side):
            pnum = str(2 * n_per_side + 1 + i)
            y = span / 2 - i * pitch
            nid, nn = _net(pnum)
            out.append(self._smd_pad(pnum, x_e, y, pad_long, pad_short, nid, nn))

        # North side: pads 3n/4+1..n, right→left (x decreases)
        y_n = -(hh + overhang)
        for i in range(n_per_side):
            pnum = str(3 * n_per_side + 1 + i)
            x = span / 2 - i * pitch
            nid, nn = _net(pnum)
            out.append(self._smd_pad(pnum, x, y_n, pad_short, pad_long, nid, nn))

        # EP (centre thermal pad) — only for QFN/DFN packages (not QFP/LQFP).
        # QFP/LQFP packages have no exposed thermal pad; adding one would cause
        # false DRC clearance violations and incorrect footprint geometry.
        fp_up_ep = fp_ref.upper()
        _is_qfn_dfn = "QFN" in fp_up_ep or "DFN" in fp_up_ep
        if _is_qfn_dfn or m_ep:
            ep_num = str(n_total + 1)
            ep_nid, ep_nn = self._pin_net("GND", nets)
            out.append(self._smd_pad(ep_num, 0.0, 0.0, ep_w, ep_h, ep_nid, ep_nn))

        return out

    def _make_soic_pads(
        self,
        fp_ref: str,
        body_w: float,
        body_h: float,
        nets: list[tuple[int, str]],
        pin_by_num: dict[str, dict],
        comp_id: str,
        pin_net_map: dict[tuple[str, str], tuple[int, str]] | None,
    ) -> list[str]:
        """SOIC/SOP two-side pad layout — all N pads at correct physical positions."""
        m_n = re.search(r'(?:SOIC|SOP|SSOP|TSSOP)-?(\d+)', fp_ref, re.IGNORECASE)
        n_total = int(m_n.group(1)) if m_n else 8
        n_per_side = max(1, n_total // 2)

        m_p = re.search(r'_P([\d.]+)mm', fp_ref)
        pitch = float(m_p.group(1)) if m_p else 1.27

        pad_long  = max(1.5, pitch * 1.2)
        pad_short = max(0.4, pitch * 0.6)
        span = (n_per_side - 1) * pitch
        hw = body_w / 2
        overhang = 0.45

        x_left  = -(hw + overhang)
        x_right =  (hw + overhang)
        out: list[str] = []

        for i in range(n_per_side):
            pnum = str(1 + i)
            y = -span / 2 + i * pitch
            nid, nn = self._pad_net_by_num(pnum, pin_by_num, nets, comp_id, pin_net_map)
            out.append(self._smd_pad(pnum, x_left, y, pad_long, pad_short, nid, nn))

        for i in range(n_per_side):
            pnum = str(n_per_side + 1 + i)
            y = span / 2 - i * pitch   # reversed: pin n/2+1 at bottom-right
            nid, nn = self._pad_net_by_num(pnum, pin_by_num, nets, comp_id, pin_net_map)
            out.append(self._smd_pad(pnum, x_right, y, pad_long, pad_short, nid, nn))

        return out

    def _make_to92_pads(
        self,
        nets: list[tuple[int, str]],
        pin_by_num: dict[str, dict],
        comp_id: str,
        pin_net_map: dict[tuple[str, str], tuple[int, str]] | None,
    ) -> list[str]:
        """TO-92 through-hole: 3 pins in a 2.54mm-pitch line."""
        pad_dia   = 1.6
        drill_dia = 0.8
        pitch     = 2.54
        out: list[str] = []
        for i, pnum in enumerate(["1", "2", "3"]):
            x = -pitch + i * pitch   # −2.54, 0, +2.54
            nid, nn = self._pad_net_by_num(pnum, pin_by_num, nets, comp_id, pin_net_map)
            net_str = f' (net {nid} "{_esc(nn)}")' if nid else ""
            out.append(
                f'    (pad "{pnum}" thru_hole circle'
                f' (at {x:.2f} 0.00 0)'
                f' (size {pad_dia:.2f} {pad_dia:.2f})'
                f' (drill {drill_dia:.2f})'
                f' (layers "*.Cu" "*.Mask")'
                f'{net_str})'
            )
        return out

    def _make_sot223_pads(
        self,
        nets: list[tuple[int, str]],
        pin_by_num: dict[str, dict],
        comp_id: str,
        pin_net_map: dict[tuple[str, str], tuple[int, str]] | None,
    ) -> list[str]:
        """SOT-223: 3 front signal pads + 1 wide tab pad (pin 4 = pin 2 net)."""
        pitch    = 2.30   # SOT-223 pin pitch
        y_front  = 2.30   # front pads y offset
        y_tab    = -2.30  # tab pad y offset
        pw_front = 1.40
        ph_front = 1.60
        out: list[str] = []
        for i, pnum in enumerate(["1", "2", "3"]):
            x = -pitch + i * pitch   # −2.3, 0, +2.3
            nid, nn = self._pad_net_by_num(pnum, pin_by_num, nets, comp_id, pin_net_map)
            out.append(self._smd_pad(pnum, x, y_front, pw_front, ph_front, nid, nn))
        # Tab (pad 4) shares net with pin 2 per SOT-223-3_TabPin2 convention
        p2 = pin_by_num.get("2")
        if p2:
            raw2 = re.sub(r'\d+$', '', p2["name"]) if re.match(r'^(GND|DVDD|IOVDD|VDD)', p2["name"]) else p2["name"]
            nid, nn = self._resolve_pin_net(raw2, nets, comp_id, pin_net_map)
        else:
            nid, nn = (0, "")
        out.append(self._smd_pad("4", 0.0, y_tab, 5.40, 2.90, nid, nn))
        return out

    def _make_lga_pads(
        self,
        fp_ref: str,
        body_w: float,
        body_h: float,
        nets: list[tuple[int, str]],
        pin_by_num: dict[str, dict],
        comp_id: str,
        pin_net_map: dict[tuple[str, str], tuple[int, str]] | None,
    ) -> list[str]:
        """LGA pad layout: rectangular pads arranged in two rows under body."""
        m_n = re.search(r'LGA-?(\d+)', fp_ref, re.IGNORECASE)
        n_total = int(m_n.group(1)) if m_n else 8

        m_p = re.search(r'_P([\d.]+)mm', fp_ref)
        pitch = float(m_p.group(1)) if m_p else 0.65

        n_per_row = max(1, n_total // 2)
        pad_size  = max(0.25, pitch * 0.65)
        row_span  = (n_per_row - 1) * pitch
        y_top = -pitch * 0.5
        y_bot =  pitch * 0.5
        out: list[str] = []
        for i in range(n_per_row):
            pnum = str(1 + i)
            x = -row_span / 2 + i * pitch
            nid, nn = self._pad_net_by_num(pnum, pin_by_num, nets, comp_id, pin_net_map)
            out.append(self._smd_pad(pnum, x, y_top, pad_size, pad_size, nid, nn))
        for i in range(n_per_row):
            pnum = str(n_per_row + 1 + i)
            x = row_span / 2 - i * pitch   # CCW: right to left on bottom row
            nid, nn = self._pad_net_by_num(pnum, pin_by_num, nets, comp_id, pin_net_map)
            out.append(self._smd_pad(pnum, x, y_bot, pad_size, pad_size, nid, nn))
        return out

    def _make_2side_pads(
        self,
        pins: list[dict],
        body_w: float,
        body_h: float,
        nets: list[tuple[int, str]],
        comp_id: str,
        pin_net_map: dict[tuple[str, str], tuple[int, str]] | None,
    ) -> list[str]:
        """Generic fallback: left/right two-side layout (schematic symbol sides)."""
        left_pins  = [p for p in pins if p["side"] == "left"]
        right_pins = [p for p in pins if p["side"] == "right"]
        pad_h = 0.5  # X-dimension (horizontal protrusion beyond body edge)

        # Compute the Y-step for the busiest side to prevent pad overlap.
        # The Y-dimension (pad_w) must not exceed 60% of the pin-to-pin step.
        n_max = max(len(left_pins), len(right_pins), 2)
        _span_est = min(body_h * 0.8, n_max * 1.2)
        _step_est = _span_est / (n_max - 1) if n_max > 1 else _span_est
        # Cap pad_w so adjacent pads have ≥0.15mm clearance (pad_w ≤ step * 0.6)
        pad_w = min(1.0, max(0.3, _step_est * 0.6))

        x_left  = -(body_w / 2 + pad_h / 2)
        x_right =  (body_w / 2 + pad_h / 2)

        def _y_for(idx: int, total: int, bh: float) -> float:
            if total <= 1:
                return 0.0
            span = min(bh * 0.8, total * 1.2)
            step = span / (total - 1) if total > 1 else 0
            return -span / 2 + idx * step

        out: list[str] = []
        for i, pin in enumerate(left_pins):
            y = _y_for(i, len(left_pins), body_h)
            nid, nn = self._resolve_pin_net(pin["name"], nets, comp_id, pin_net_map)
            net_str = f' (net {nid} "{_esc(nn)}")' if nid else ""
            out.append(
                f'    (pad "{_esc(pin["number"])}" smd rect'
                f' (at {x_left:.2f} {y:.2f} 0)'
                f' (size {pad_h:.2f} {pad_w:.2f})'
                f' (layers {_layer_str(pin.get("side","left"))})'
                f'{net_str})'
            )
        for i, pin in enumerate(right_pins):
            y = _y_for(i, len(right_pins), body_h)
            nid, nn = self._resolve_pin_net(pin["name"], nets, comp_id, pin_net_map)
            net_str = f' (net {nid} "{_esc(nn)}")' if nid else ""
            out.append(
                f'    (pad "{_esc(pin["number"])}" smd rect'
                f' (at {x_right:.2f} {y:.2f} 0)'
                f' (size {pad_h:.2f} {pad_w:.2f})'
                f' (layers {_layer_str("right")})'
                f'{net_str})'
            )
        if not out:
            for i, (pname, num) in enumerate([("GND", "1"), ("VDD", "2")]):
                y = _y_for(i, 2, body_h)
                nid, nn = self._pin_net(pname, nets)
                net_str = f' (net {nid} "{_esc(nn)}")' if nid else ""
                out.append(
                    f'    (pad "{num}" smd rect'
                    f' (at {x_left:.2f} {y:.2f} 0)'
                    f' (size {pad_h:.2f} {pad_w:.2f})'
                    f' (layers "F.Cu" "F.Paste" "F.Mask")'
                    f'{net_str})'
                )
        return out

    def _make_passive_pads(
        self,
        pins: list[dict],
        body_w: float,
        nets: list[tuple[int, str]],
        comp_id: str = "",
        pin_net_map: dict[tuple[str, str], tuple[int, str]] | None = None,
    ) -> list[str]:
        """Two-pad SMD passive (R, C) — horizontal layout."""
        pad_size = max(0.5, body_w * 0.3)
        out: list[str] = []
        for i, pin in enumerate(pins[:2]):
            x = -(body_w / 2 - pad_size / 2) if i == 0 else (body_w / 2 - pad_size / 2)
            # For passives, try pin NUMBER first against HIR map (HIR stores
            # pin_name as "1"/"2"), then fall back to pin NAME (keyword match).
            nid, nname = 0, ""
            if pin_net_map and comp_id:
                pnum = pin.get("number", str(i + 1))
                hit = pin_net_map.get((comp_id, pnum))
                if hit:
                    nid, nname = hit
            if not nid:
                nid, nname = self._resolve_pin_net(
                    pin["name"], nets, comp_id, pin_net_map)
            net_str = f' (net {nid} "{_esc(nname)}")' if nid else ""
            out.append(
                f'    (pad "{_esc(pin["number"])}" smd rect'
                f' (at {x:.2f} 0)'
                f' (size {pad_size:.2f} {pad_size:.2f})'
                f' (layers "F.Cu" "F.Paste" "F.Mask")'
                f'{net_str})'
            )
        # If no pins given, add 2 generic pads
        if not pins:
            for i, num in enumerate(["1", "2"]):
                x = -(body_w / 2 - 0.25) if i == 0 else (body_w / 2 - 0.25)
                out.append(
                    f'    (pad "{num}" smd rect'
                    f' (at {x:.2f} 0)'
                    f' (size 0.5 0.5)'
                    f' (layers "F.Cu" "F.Paste" "F.Mask"))'
                )
        return out

    def _board_edge(self, w: float, h: float) -> str:
        """Board outline on Edge.Cuts layer."""
        return (
            f'  (gr_rect (start 0 0) (end {w:.2f} {h:.2f})\n'
            f'    (stroke (width 0.05) (type solid))\n'
            f'    (layer "Edge.Cuts")\n'
            f'    (uuid "{self._uid()}"))'
        )

    # ------------------------------------------------------------------
    # Phase 23.2: GND copper fill zones
    # ------------------------------------------------------------------

    def _gnd_zones(
        self,
        board_w: float,
        board_h: float,
        nets: list[tuple[int, str]],
    ) -> str:
        """Generate GND copper fill zones on both F.Cu and B.Cu.

        Creates two solid copper zones (front and back) that fill the
        board area with a 0.3 mm clearance from pads/traces.  The zones
        connect to the GND net for a proper ground plane.
        """
        gnd_id = self._net_id("GND", nets)
        inset = 0.5  # mm inside board edge
        clearance = 0.3  # mm pad-to-zone clearance

        out: list[str] = []
        for layer in ("B.Cu", "F.Cu"):
            # B.Cu gets priority (full GND plane), F.Cu is supplementary
            out.append(f'  (zone (net {gnd_id}) (net_name "GND") (layer "{layer}")')
            out.append(f'    (tstamp "{self._uid()}")')
            out.append(f'    (hatch edge 0.508)')
            out.append(f'    (connect_pads (clearance {clearance}))')
            out.append(f'    (min_thickness 0.25)')
            out.append(f'    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))')
            out.append(f'    (polygon (pts')
            out.append(f'      (xy {inset:.2f} {inset:.2f})')
            out.append(f'      (xy {board_w - inset:.2f} {inset:.2f})')
            out.append(f'      (xy {board_w - inset:.2f} {board_h - inset:.2f})')
            out.append(f'      (xy {inset:.2f} {board_h - inset:.2f})')
            out.append(f'    ))')
            out.append(f'  )')

        return "\n".join(out)

    # ------------------------------------------------------------------
    # Phase 23.2: Stitching vias
    # ------------------------------------------------------------------

    STITCH_VIA_SPACING_MM: float = 5.0
    STITCH_VIA_DRILL_MM: float = 0.3
    STITCH_VIA_SIZE_MM: float = 0.6
    STITCH_VIA_MARGIN_MM: float = 3.0  # offset from board edge

    def _stitching_vias(
        self,
        board_w: float,
        board_h: float,
        nets: list[tuple[int, str]],
    ) -> str:
        """Generate stitching vias on a grid to connect F.Cu and B.Cu GND planes.

        Places vias every ``STITCH_VIA_SPACING_MM`` mm around the board
        perimeter and in a grid across the board interior.  All vias
        connect to the GND net.
        """
        gnd_id = self._net_id("GND", nets)
        margin = self.STITCH_VIA_MARGIN_MM
        spacing = self.STITCH_VIA_SPACING_MM
        drill = self.STITCH_VIA_DRILL_MM
        size = self.STITCH_VIA_SIZE_MM

        out: list[str] = []

        # Grid of stitching vias across the board interior
        x = margin
        while x < board_w - margin:
            y = margin
            while y < board_h - margin:
                out.append(
                    f'  (via (at {x:.2f} {y:.2f}) (size {size}) (drill {drill})'
                    f' (layers "F.Cu" "B.Cu") (net {gnd_id})'
                    f' (tstamp "{self._uid()}"))'
                )
                y += spacing
            x += spacing

        return "\n".join(out)

    # ------------------------------------------------------------------
    # Phase 23.5: Silkscreen — board name + revision
    # ------------------------------------------------------------------

    def _board_silkscreen(
        self,
        system_name: str,
        board_w: float,
        board_h: float,
    ) -> str:
        """Add board name and revision text on F.SilkS layer."""
        # Board name at bottom-left (>= 1mm inside Edge.Cuts + text height)
        name_y = board_h - 5.0
        name_x = 5.0
        # Revision at bottom-right
        rev_x = board_w - 20.0
        rev_y = board_h - 5.0

        out: list[str] = []
        out.append(
            f'  (gr_text "{_esc(system_name)}" (at {name_x:.2f} {name_y:.2f})'
            f' (layer "F.SilkS") (uuid "{self._uid()}")'
            f' (effects (font (size 1.5 1.5) (thickness 0.15))))'
        )
        out.append(
            f'  (gr_text "v1.0" (at {rev_x:.2f} {rev_y:.2f})'
            f' (layer "F.SilkS") (uuid "{self._uid()}")'
            f' (effects (font (size 1 1) (thickness 0.15))))'
        )
        return "\n".join(out)

    # ------------------------------------------------------------------
    # LLM position planning
    # ------------------------------------------------------------------

    def _llm_plan_positions(
        self,
        hir_dict: dict[str, Any],
        footprints: dict[str, FootprintInfo],
    ) -> dict[str, PcbPosition] | None:
        """Ask LLM to suggest PCB component positions."""
        try:
            from llm.gateway import get_default_gateway
            from llm.types import TaskType
            gateway = get_default_gateway()
            if not gateway.is_llm_available():
                return None
        except ImportError:
            return None

        components = hir_dict.get("components", [])
        if not components:
            return None

        summary = [
            {
                "id": c["id"],
                "role": c.get("role", "other"),
                "mpn": c.get("mpn", "?"),
                "size_mm": (
                    f"{footprints[c['id']].width_mm:.1f}×{footprints[c['id']].height_mm:.1f}"
                    if c["id"] in footprints else "5×5"
                ),
            }
            for c in components
        ]
        bus_types = [bc.get("bus_type") for bc in hir_dict.get("bus_contracts", [])]

        try:
            resp = gateway.complete_sync(
                task=TaskType.COMPONENT_SUGGEST,
                messages=[{"role": "user", "content": (
                    "Plan PCB component placement (mm, origin top-left).\n"
                    f"Bus types: {', '.join(bt for bt in bus_types if bt) or 'none'}\n"
                    f"Board target: ~150×120mm\n\n"
                    f"Components:\n{json.dumps(summary, indent=2)}\n\n"
                    "Rules: MCU left-centre, power top, sensors right, passives between.\n"
                    "Return ONLY JSON: {\"comp_id\": {\"x\": float, \"y\": float}, ...}\n"
                    "Only include components where default placement should change."
                )}],
                temperature=0.2,
                max_tokens=500,
            )
        except Exception:
            return None

        if resp.skipped or not resp.content:
            return None

        m = re.search(r'\{.*\}', resp.content, re.DOTALL)
        if not m:
            return None
        try:
            raw = json.loads(m.group())
        except Exception:
            return None

        known_ids = {c["id"] for c in components}
        result: dict[str, PcbPosition] = {}
        for comp_id, pos in raw.items():
            if comp_id not in known_ids:
                continue
            if isinstance(pos, dict) and "x" in pos and "y" in pos:
                try:
                    result[comp_id] = PcbPosition(
                        x=float(pos["x"]),
                        y=float(pos["y"]),
                        rotation=float(pos.get("rotation", 0)),
                    )
                except (TypeError, ValueError):
                    pass
        return result or None


# ---------------------------------------------------------------------------
# Standard KiCad 6 layers
# ---------------------------------------------------------------------------

_KICAD_LAYERS: list[str] = [
    '(0 "F.Cu" signal)',
    '(31 "B.Cu" signal)',
    '(32 "B.Adhes" user "B.Adhesive")',
    '(33 "F.Adhes" user "F.Adhesive")',
    '(34 "B.Paste" user)',
    '(35 "F.Paste" user)',
    '(36 "B.SilkS" user "B.Silkscreen")',
    '(37 "F.SilkS" user "F.Silkscreen")',
    '(38 "B.Mask" user)',
    '(39 "F.Mask" user)',
    '(40 "Dwgs.User" user "User.Drawings")',
    '(44 "Edge.Cuts" user)',
    '(46 "B.CrtYd" user "B.Courtyard")',
    '(47 "F.CrtYd" user "F.Courtyard")',
    '(48 "B.Fab" user "B.Fab")',
    '(49 "F.Fab" user "F.Fab")',
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _esc(s: str) -> str:
    return s.replace('"', '\\"')


def _layer_str(side: str) -> str:
    # Returns space-separated quoted tokens for KiCad S-expr: (layers "F.Cu" "F.Paste" "F.Mask")
    if side == "back":
        return '"B.Cu" "B.Paste" "B.Mask"'
    return '"F.Cu" "F.Paste" "F.Mask"'
