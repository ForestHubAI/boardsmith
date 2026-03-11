# SPDX-License-Identifier: AGPL-3.0-or-later
"""B8+. KiCad Schematic Exporter — HIR dict -> .kicad_sch (KiCad 6 format).

Generates a valid KiCad 6 schematic (.kicad_sch) from an HIR dictionary.

Layout:
  - MCU(s) at left centre (x=100mm)
  - Peripheral / sensor components in a column to the right (x=195mm)
  - LDO power regulators above the MCU (x=100mm, y=35mm)
  - Passives between MCU and sensors (x=148mm, various y)

LLM-Boost (Phase 12):
  - When use_llm=True, asks LLM to suggest component positions.
  - LLM positions are merged with grid defaults (LLM overrides where provided).
  - Deterministic grid layout is always the fallback.

Connections:
  - Bus signals (SDA, SCL, MOSI, MISO, SCLK, SCK) -> real wire segments with
    net labels at each pin endpoint.  KiCad auto-connects all pins that share
    the same net label name on the same sheet.  HIR nets are consumed to
    handle non-standard pin names (e.g. ESP32 GPIO number "21" -> "SDA").
    No global_label (those are for multi-sheet designs).
  - Power pins (GND, VDD/VCC/3V3, VIN) -> KiCad power symbols placed at
    pin end-points with short wire stubs.
  - Passive components (R, C) use compact 2-pin symbols with proper body
    shapes (rectangle for R, capacitor plates for C).
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

from synth_core.knowledge.symbol_map import (
    SymbolDef, PinDef,
    SYMBOL_MAP, _generic_symbol,
)

log = logging.getLogger(__name__)

# Bus signals that get routed through the bus spine
_BUS_SIGNAL_KEYWORDS = ("SDA", "SCL", "MOSI", "MISO", "SCLK", "SCK", "TX", "RX")

# Power-pin name fragments mapped to canonical net name
_GND_KEYWORDS  = ("GND", "VSS", "AGND", "DGND", "PGND")
_3V3_KEYWORDS  = ("3V3", "VDD", "VCC", "DVDD", "IOVDD", "VOUT", "VS", "VTREF", "VREF")
_VIN_KEYWORDS  = ("VIN", "5V", "VSUP", "VBUS")
# 12V rail — checked BEFORE _VIN_KEYWORDS so "VIN12V" → "+12V" not "+5V"
_12V_KEYWORDS  = ("12V", "VIN12", "V12")
# Battery/LiPo net — exact-match only to avoid false hits on BAT_SENSE etc.
_VBAT_EXACT    = frozenset(("BAT", "VBAT", "VBATT", "BATT", "LIPO"))
# Motor supply pins (TB6612FNG VM, DRV8833 VM, etc.) — separate rail from logic VCC
_MOTOR_SUPPLY_KEYWORDS = ("VM", "VMOT", "VPWR", "VMOTOR")

# All power nets that have dedicated lib_symbol definitions (for lib_id lookup)
_KNOWN_POWER_NETS = frozenset(("GND", "+3V3", "+5V", "+12V", "+VBAT"))

# Non-power input pins with known required connections
# EN (enable) pins are active-high -> 3V3; CSB is I2C/SPI select -> 3V3 for I2C
# SDO/SA0 is I2C address -> GND for 0x76
_CONFIG_PIN_NETS: dict[str, str] = {
    "EN":      "+3V3",
    "CSB":     "+3V3",
    "SDO":     "GND",
    "SA0":     "GND",
    "SDO/SA0": "GND",
}

# SPI slave-side pin aliases: sensors often name SPI pins SDI/SDO rather
# than MOSI/MISO.  When a component is identified as a SPI slave via the
# bus_contracts, these aliases allow _draw_bus_wires to match and wire the
# pin even if the pin name does not contain "MOSI" or "MISO" directly.
_SPI_SLAVE_SIGNAL_ALIASES: dict[str, frozenset[str]] = {
    "MOSI": frozenset(["SDI", "DIN", "SIN", "COPI"]),
    "MISO": frozenset(["SDO", "DOUT", "SOUT", "CIPO"]),
    "SCLK": frozenset(["SCK", "CLK", "CK"]),   # SCLK itself is in by_name
}
# UART pin aliases — UART has a crossover: master TX → slave RX, slave TX → master RX.
# Signal "TX" = master TX line: master pins TXD0/TX0 + slave INPUT pins RXD/DI.
# Signal "RX" = master RX line: master pins RXD0/RX0 + slave OUTPUT pins TXD/RO.
_UART_SLAVE_SIGNAL_ALIASES: dict[str, frozenset[str]] = {
    # TX net = MCU transmit line.  MCU pins: TXD0/TX0/LPUART1_TX.
    # Slave INPUT (receive) pins: DI, RXD, DATA_IN — and the literal "RX" pin name.
    "TX": frozenset(["DI", "RXD", "DATA_IN", "TXD0", "TX0", "LPUART1_TX", "RX"]),
    # RX net = MCU receive line.  MCU pins: RXD0/RX0/LPUART1_RX.
    # Slave OUTPUT (transmit) pins: RO, TXD, DATA_OUT — and the literal "TX" pin name.
    "RX": frozenset(["RO", "TXD", "DATA_OUT", "RXD0", "RX0", "LPUART1_RX", "TX"]),
}
# Combined alias lookup for _draw_bus_wires
_ALL_BUS_SIGNAL_ALIASES: dict[str, frozenset[str]] = {
    **_SPI_SLAVE_SIGNAL_ALIASES,
    **_UART_SLAVE_SIGNAL_ALIASES,
}
# Reverse map: alias → canonical signal name.  Used to normalise signal names
# from HIR nets so "SCK" → "SCLK", "SDI" → "MOSI", etc.
_SIGNAL_CANONICAL: dict[str, str] = {}
for _canon, _aliases in _ALL_BUS_SIGNAL_ALIASES.items():
    for _a in _aliases:
        _SIGNAL_CANONICAL[_a] = _canon


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_kicad_sch(
    hir_dict: dict[str, Any],
    out_path: Path,
    use_llm: bool = True,
    add_no_connect: bool = False,
    add_pwr_flag: bool = False,
) -> None:
    """Export HIR as a KiCad 6 .kicad_sch schematic file.

    When use_llm=True the LLM is asked to suggest optimal schematic positions
    for each component. LLM positions override the default grid layout where
    provided; the grid layout is always used as fallback.

    Also generates a minimal .kicad_pro project file alongside the schematic so
    that KiCad can resolve reference annotations from the instances blocks.

    Args:
        add_no_connect: If True, adds no_connect flags on unconnected pins
                        (fixes KiCad ERC "pin not connected" violations).
        add_pwr_flag:   If True, adds PWR_FLAG symbols on power nets
                        (fixes KiCad ERC "power pin not driven" violations).
    """
    llm_positions: dict[str, tuple[float, float]] = {}
    if use_llm:
        llm_positions = _llm_plan_layout(hir_dict) or {}
        if llm_positions:
            log.debug("B8 LLM layout positions for %d components", len(llm_positions))

    project_name = out_path.stem  # e.g. "boardsmith"
    exporter = _KiCadExporter(
        hir_dict,
        llm_positions=llm_positions,
        add_no_connect=add_no_connect,
        add_pwr_flag=add_pwr_flag,
        project_name=project_name,
    )
    content = exporter.build()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")

    # Generate companion .kicad_pro so KiCad resolves (instances (project ...))
    pro_path = out_path.with_suffix(".kicad_pro")
    if not pro_path.exists():
        pro_content = json.dumps({
            "meta": {"filename": pro_path.name, "version": 1},
            "project": {"name": project_name},
        }, indent=2)
        pro_path.write_text(pro_content, encoding="utf-8")

    # Generate .kicad_sym symbol library file (unprefixed symbol names)
    lib_name = _KiCadExporter.SYM_LIB
    sym_lib_path = out_path.parent / f"{lib_name}.kicad_sym"
    sym_lib_path.write_text(exporter.get_sym_lib_content(), encoding="utf-8")

    # Generate sym-lib-table (project-level) so KiCad can resolve lib_id prefixes
    sym_lib_table_path = out_path.parent / "sym-lib-table"
    sym_lib_table_path.write_text(
        f'(sym_lib_table\n'
        f'  (version 7)\n'
        f'  (lib (name "{lib_name}")(type "KiCad")'
        f'(uri "${{KIPRJMOD}}/{lib_name}.kicad_sym")(options "")'
        f'(descr "Project symbols"))\n'
        f')\n',
        encoding="utf-8",
    )

    # Generate fp-lib-table (empty, prevents "library not configured" warnings)
    fp_lib_table_path = out_path.parent / "fp-lib-table"
    if not fp_lib_table_path.exists():
        fp_lib_table_path.write_text(
            '(fp_lib_table\n  (version 7)\n)\n',
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Internal exporter
# ---------------------------------------------------------------------------

class _KiCadExporter:
    # Layout constants (mm) — snapped to 2.54 mm (100-mil) grid so that every
    # generated coordinate is a whole multiple of 1.27 mm (KiCad 50-mil grid).
    # Formula: N × 2.54 (N chosen to preserve original approximate spacing).
    MCU_X: float = 101.60      # 40 × 2.54  (was 100.0)
    MCU_Y: float = 111.76      # 44 × 2.54  (was 110.0) — makes all pin-Y = k×1.27
    PERIPH_X: float = 195.58   # 77 × 2.54  (was 195.0)
    PERIPH_Y_START: float = 60.96  # 24 × 2.54  (was 60.0)
    PERIPH_Y_STEP: float = 55.88   # 22 × 2.54  (was 55.0)
    POWER_X: float = 101.60    # 40 × 2.54  (was 100.0)
    POWER_Y: float = 35.56     # 14 × 2.54  (was 35.0)
    POWER_X_STEP: float = 45.72   # 18 × 2.54  (was 45.0)
    PASSIVE_X: float = 149.86  # 59 × 2.54  (was 148.0)
    PASSIVE_Y_START: float = 50.80 # 20 × 2.54  (was 50.0)
    PASSIVE_Y_STEP: float = 17.78  # 7 × 2.54   (was 18.0)
    # Bus spine sits between MCU and peripherals
    BUS_SPINE_X: float = 147.32   # 58 × 2.54  (was 147.5)

    # Symbol body (IC-style) — already 2.54-mm multiples, unchanged
    BODY_HALF_W: float = 5.08     # half-width of IC component box (mm)
    PIN_LEN: float = 2.54         # pin stub length inside lib_symbol (mm)
    WIRE_LEN: float = 5.08        # wire stub for power symbols

    # Passive symbol body
    # Resistor: pin offset = R_BODY_HW + R_PIN_LEN = 1.016 + 1.524 = 2.54 ✓
    R_BODY_HW: float = 1.016      # half-width of resistor box
    R_BODY_HH: float = 0.508      # half-height of resistor box
    R_PIN_LEN: float = 1.524      # resistor pin stub length
    # Capacitor: C_PLATE_X + C_PIN_LEN = 1.27 mm (50 mil) — on 50-mil grid ✓
    C_PLATE_X: float = 0.508      # x-offset of capacitor plate (was 0.381)
    C_PLATE_H: float = 1.016      # half-height of capacitor plate
    C_PIN_LEN: float = 0.762      # capacitor pin stub length (was 1.524)

    # Library name used for all lib_id prefixes in the schematic.
    # Must match the (name "...") entry in sym-lib-table.
    SYM_LIB: str = "boardsmith"

    def __init__(
        self,
        hir_dict: dict[str, Any],
        llm_positions: dict[str, tuple[float, float]] | None = None,
        add_no_connect: bool = False,
        add_pwr_flag: bool = False,
        project_name: str = "boardsmith",
    ) -> None:
        self._hir = hir_dict
        self._pwr_counter = 1
        self._flg_counter = 1
        self._llm_positions: dict[str, tuple[float, float]] = llm_positions or {}
        self._add_no_connect = add_no_connect
        self._add_pwr_flag = add_pwr_flag
        self._project_name = project_name
        # Collected raw (unprefixed) lib_symbol strings for .kicad_sym generation
        self._lib_symbols_raw: list[str] = []
        # Root sheet UUID -- KiCad 7 requires every sheet to have a UUID and
        # all (instances) paths must include it: (path "/<root_uuid>" ...).
        # Without this, KiCad ignores annotation data and shows U?/R?/C?.
        self._root_uuid: str = str(uuid.uuid4())

    def _uid(self) -> str:
        return str(uuid.uuid4())

    def _qlib(self, name: str) -> str:
        """Qualify a symbol name with the project library prefix for lib_id."""
        return f"{self.SYM_LIB}:{name}"

    @staticmethod
    def _prefix_lib_sym(raw: str) -> str:
        """Add library prefix to the TOP-LEVEL symbol name only (not sub-symbols).

        KiCad 9 format:
          - Top-level:  ``(symbol "boardsmith:ESP32" ...)``  ← needs lib prefix
          - Sub-symbols: ``(symbol "ESP32_0_1" ...)``       ← NO lib prefix
            Sub-symbols are identified by the ``_<unit>_<body>`` suffix (e.g. _0_1, _1_1).

        Old code used str.replace which added the prefix to EVERY (symbol "…"),
        including sub-symbols — KiCad 9 refuses to load those files.
        """
        import re as _re
        lib = _KiCadExporter.SYM_LIB
        def _replace(m: "_re.Match") -> str:
            name = m.group(1)
            # Sub-symbols end with _<digits>_<digits> — leave them unprefixed
            if _re.search(r'_\d+_\d+$', name):
                return m.group(0)
            # Already prefixed (shouldn't happen, but be safe)
            if name.startswith(f"{lib}:"):
                return m.group(0)
            return f'(symbol "{lib}:{name}"'
        # Use [^"]* (zero-or-more) so empty-MPN symbols (symbol "") are also
        # prefixed to (symbol "boardsmith:") — [^"]+ would skip the empty case
        # and leave the lib_symbol without a prefix, causing KiCad to fail the
        # lookup for instances that reference lib_id "boardsmith:".
        return _re.sub(r'\(symbol "([^"]*)"', _replace, raw)

    def get_sym_lib_content(self) -> str:
        """Return .kicad_sym library file content with all project symbols (unprefixed)."""
        lines = ['(kicad_symbol_lib (version 20220914) (generator "boardsmith")']
        for raw in self._lib_symbols_raw:
            lines.append(raw)
        lines.append(")")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Main builder
    # ------------------------------------------------------------------

    def build(self) -> str:
        components: list[dict] = self._hir.get("components", [])
        bus_contracts: list[dict] = self._hir.get("bus_contracts", [])

        # Classify
        mcus      = [c for c in components if c.get("role") == "mcu"]
        power_cs  = [c for c in components if c.get("role") == "power"]
        sensors   = [c for c in components if c.get("role") in ("sensor", "comms")]
        passives  = [c for c in components if c.get("role") == "passive"]
        others    = [c for c in components if c.get("role") not in
                     ("mcu", "power", "sensor", "comms", "passive")]

        # Phase 22.6: Dynamic grid layout — adapts Y-step and adds overflow
        # columns when component count exceeds what the fixed grid can handle.
        # Max Y extent for the schematic sheet (A3 landscape usable area ~280mm)
        _SHEET_MAX_Y = 280.0
        _GRID = 1.27  # KiCad 50-mil snap grid

        def _snap(v: float) -> float:
            return round(v / _GRID) * _GRID

        positions: dict[str, tuple[float, float]] = {}
        for i, c in enumerate(mcus):
            positions[c["id"]] = (_snap(self.MCU_X), _snap(self.MCU_Y + i * 60.0))
        for i, c in enumerate(power_cs):
            positions[c["id"]] = (_snap(self.POWER_X + i * self.POWER_X_STEP), _snap(self.POWER_Y))

        # --- Dynamic peripheral placement ---
        periph = sensors + others
        n_periph = len(periph)
        if n_periph > 0:
            # Calculate available Y space
            avail_y = _SHEET_MAX_Y - self.PERIPH_Y_START
            # Max items per column before needing overflow
            max_per_col = max(int(avail_y / self.PERIPH_Y_STEP), 3)
            # If too many items, reduce step or add columns
            if n_periph <= max_per_col:
                p_step = self.PERIPH_Y_STEP
                p_cols = 1
            else:
                # Try reducing step first (min 30mm to avoid symbol overlap)
                min_step = 30.48  # 12 × 2.54
                reduced_step = max(avail_y / n_periph, min_step)
                if reduced_step >= min_step:
                    p_step = reduced_step
                    p_cols = 1
                else:
                    # Need multiple columns
                    p_step = self.PERIPH_Y_STEP
                    p_cols = (n_periph + max_per_col - 1) // max_per_col
                    p_step = min(self.PERIPH_Y_STEP, avail_y / ((n_periph + p_cols - 1) // p_cols))
                    p_step = max(p_step, min_step)

            col_offset = 80.0  # X spacing between overflow columns
            items_per_col = (n_periph + p_cols - 1) // p_cols if p_cols > 1 else n_periph
            for i, c in enumerate(periph):
                col = i // items_per_col if p_cols > 1 else 0
                row = i % items_per_col if p_cols > 1 else i
                x = self.PERIPH_X + col * col_offset
                y = self.PERIPH_Y_START + row * p_step
                positions[c["id"]] = (_snap(x), _snap(y))

        # --- Dynamic passive placement ---
        n_passives = len(passives)
        if n_passives > 0:
            avail_y = _SHEET_MAX_Y - self.PASSIVE_Y_START
            # Reduce step for many passives (min 10.16mm = 4 × 2.54)
            min_p_step = 10.16
            if n_passives * self.PASSIVE_Y_STEP <= avail_y:
                ps_step = self.PASSIVE_Y_STEP
            else:
                ps_step = max(avail_y / n_passives, min_p_step)

            # Overflow to second column if needed
            max_passive_per_col = max(int(avail_y / ps_step), 3)
            for i, c in enumerate(passives):
                col = i // max_passive_per_col
                row = i % max_passive_per_col
                # Column offset 25.40 mm (10 × 2.54) keeps col-1 pin2_x at
                # 177.80, safely left of 182.88 (peripheral-IC wire-stub
                # endpoint).  The old 30.0 mm offset placed col-1 pin2_x
                # at 182.88, causing GND/+3V3 power symbols to collide with
                # bus-signal labels on peripheral-IC pins at the same y.
                x = self.PASSIVE_X + col * 25.40
                y = self.PASSIVE_Y_START + row * ps_step
                positions[c["id"]] = (_snap(x), _snap(y))

        # LLM-override: replace grid positions where LLM provided a suggestion
        # Snap to 1.27mm (50mil) grid so all pin endpoints land on KiCad's
        # connection grid and avoid "endpoint off grid" / dangling-label ERC errors.
        for comp_id, pos in self._llm_positions.items():
            if comp_id in positions:
                positions[comp_id] = (_snap(pos[0]), _snap(pos[1]))

        # Symbol def lookup + ref-designator assignment
        sym_defs: dict[str, SymbolDef] = {}    # sym_id -> SymbolDef
        comp_sym: dict[str, str] = {}          # comp_id -> sym_id
        ref_map:  dict[str, str] = {}          # comp_id -> "U1", "R3", ...
        ref_ctr:  dict[str, int] = {}

        for comp in components:
            mpn  = comp.get("mpn", "UNKNOWN")
            role = comp.get("role", "other")
            ifaces = comp.get("interface_types", [])
            sdef = SYMBOL_MAP.get(mpn) or _generic_symbol(mpn, role, ifaces)
            # Empty MPN → sym_id would be "" → lib_id becomes "boardsmith:" (ghost symbol).
            # For empty-MPN passives, _generic_symbol defaults to "R" for ALL empty
            # MPNs (including caps like RP2040 decoupling MC_C1/MC_C2).
            # Re-derive the correct type from the component name, then use
            # ref_prefix ("R" or "C") as sym_id so lib_id is "boardsmith:R" / "boardsmith:C".
            if not mpn and role == "passive":
                _comp_name_up = str(comp.get("name", "") or "").upper()
                if any(kw in _comp_name_up for kw in ("CAP", "CAPACITOR", "DECOUPL", "BYPASS")):
                    sdef = SymbolDef(
                        ref_prefix="C",
                        footprint="Capacitor_SMD:C_0402_1005Metric",
                        pins=[PinDef("~", "1", "passive", "left"),
                              PinDef("~", "2", "passive", "right")],
                        description="Generic capacitor",
                    )
                # else: sdef is already an R SymbolDef from _generic_symbol (correct for resistors)
            sym_id = mpn if mpn else sdef.ref_prefix
            sym_defs[sym_id] = sdef
            comp_sym[comp["id"]] = sym_id
            prefix = sdef.ref_prefix
            ref_ctr[prefix] = ref_ctr.get(prefix, 1)
            ref_map[comp["id"]] = f"{prefix}{ref_ctr[prefix]}"
            ref_ctr[prefix] += 1

        # --- IC Overlap Correction ---
        # LLM positions may place ICs so close together that their left/right
        # pin Y-ranges interleave, causing power symbols and signal labels from
        # different components to land on the same wire endpoint (producing
        # GND↔+3V3 shorts and ERC errors).  After all positions are set (incl.
        # LLM overrides), group ICs by X column and push overlapping ICs apart
        # so pin rows from adjacent components never share the same Y coordinate.
        _IC_PIN_MARGIN = 5.08   # 2 × 2.54 mm minimum gap between IC pin areas
        _ic_by_col: dict[float, list[str]] = {}
        for _c in components:
            _cid = _c["id"]
            _sym_id = comp_sym.get(_cid)
            if _sym_id is None:
                continue
            _sdef = sym_defs.get(_sym_id)
            if _sdef is None:
                continue
            if _sdef.ref_prefix != "U":  # ICs only
                continue
            _cx, _cy = positions.get(_cid, (0.0, 0.0))
            _ic_by_col.setdefault(_cx, []).append(_cid)
        for _col_ids in _ic_by_col.values():
            # Sort top-to-bottom (ascending Y)
            _col_ids.sort(key=lambda cid: positions[cid][1])
            for _idx in range(len(_col_ids) - 1):
                _cid_a = _col_ids[_idx]
                _cid_b = _col_ids[_idx + 1]
                _sdef_a = sym_defs[comp_sym[_cid_a]]
                _sdef_b = sym_defs[comp_sym[_cid_b]]
                _cy_a = positions[_cid_a][1]
                _cy_b = positions[_cid_b][1]
                _n_l_a = len([p for p in _sdef_a.pins if p.side == "left"])
                _n_r_a = len([p for p in _sdef_a.pins if p.side == "right"])
                _n_l_b = len([p for p in _sdef_b.pins if p.side == "left"])
                _n_r_b = len([p for p in _sdef_b.pins if p.side == "right"])
                _hh_a = max(_n_l_a, _n_r_a, 1) * 2.54 / 2 + 1.27
                _hh_b = max(_n_l_b, _n_r_b, 1) * 2.54 / 2 + 1.27
                # Require: top-pin of B is strictly below bottom-pin of A + margin
                # bottom-pin of A at: cy_a + (hh_a - 1.27)
                # top-pin of B at:    cy_b - (hh_b - 1.27)
                _min_cy_b = _cy_a + (_hh_a - 1.27) + (_hh_b - 1.27) + _IC_PIN_MARGIN
                _min_cy_b = _snap(_min_cy_b)
                if _cy_b < _min_cy_b:
                    _delta = _min_cy_b - _cy_b
                    # Shift cid_b and all components below it in this column
                    for _j in range(_idx + 1, len(_col_ids)):
                        _cid_j = _col_ids[_j]
                        _cx_j, _cy_j = positions[_cid_j]
                        positions[_cid_j] = (_cx_j, _snap(_cy_j + _delta))

        # Collect active bus signal names from bus_contracts
        bus_signals: list[str] = []
        spi_slaves: set[str] = set()   # comp IDs that are SPI slaves
        can_slaves: set[str] = set()   # comp IDs that are CAN bus slaves
        # Maps UART slave comp_id → bus_name (e.g. "uart1").  Used to assign
        # per-bus net label names (uart0_TX, uart1_TX …) when multiple UART
        # devices are present, preventing Output-Output ERC errors from sharing
        # a single "TX" or "RX" net label across different UART buses.
        uart_slave_to_bus: dict[str, str] = {}
        uart_master_to_buses: dict[str, list[str]] = {}  # MCU id → bus names list
        for bc in bus_contracts:
            bt = bc.get("bus_type", "")
            bus_name = bc.get("bus_name", "")
            if bt == "I2C":
                bus_signals += ["SDA", "SCL"]
            elif bt == "SPI":
                bus_signals += ["MOSI", "MISO", "SCLK"]
                spi_slaves.update(bc.get("slave_ids", []))
            elif bt == "UART":
                bus_signals += ["TX", "RX"]
                for slave_id in bc.get("slave_ids", []):
                    uart_slave_to_bus[slave_id] = bus_name
                master_id = bc.get("master_id", "")
                if master_id:
                    uart_master_to_buses.setdefault(master_id, []).append(bus_name)
            elif bt == "CAN":
                can_slaves.update(bc.get("slave_ids", []))
        bus_signals = list(dict.fromkeys(bus_signals))

        # Build pin→bus-signal mapping from HIR nets.
        # HIR nets may identify a pin by GPIO number (e.g. pin_name="21" for
        # ESP32 SDA) rather than by the signal name embedded in the lib_symbol
        # pin name (e.g. "IO21/SDA").  We extract the canonical signal from the
        # net name ("i2c0_SDA" → "SDA") and record it keyed by (comp_id, pin_name).
        # Also build pin_to_hir_net_name for the full HIR net name (e.g. "uart0_TX")
        # used when assigning per-bus UART net labels in multi-UART designs.
        _bus_sig_set = frozenset(s.upper() for s in _BUS_SIGNAL_KEYWORDS)
        pin_to_signal: dict[tuple[str, str], str] = {}
        pin_to_hir_net_name: dict[tuple[str, str], str] = {}
        # Multi-map: all HIR net names for a (comp_id, pin_name) pair.
        # Needed when a shared MCU GPIO (e.g. PA2) appears in multiple UART
        # nets (uart1_TX_MCU *and* uart2_TX_MCU) — the single-entry dict
        # only keeps the last writer, losing the first UART assignment.
        pin_to_all_hir_nets: dict[tuple[str, str], list[str]] = {}
        for net in self._hir.get("nets", []):
            net_name = str(net.get("name", ""))
            # "i2c0_SDA" → "SDA"; "spi0_MOSI" → "MOSI"; "SDA" (no prefix) → "SDA"
            raw_sig = net_name.rsplit("_", 1)[-1].upper()
            if raw_sig not in _bus_sig_set:
                # Also check for MCU-suffixed UART nets: uart0_TX_MCU → "TX"
                _mcu_stripped = net_name
                if net_name.upper().endswith("_MCU"):
                    _mcu_stripped = net_name[:-4]
                raw_sig = _mcu_stripped.rsplit("_", 1)[-1].upper()
                if raw_sig not in _bus_sig_set:
                    continue
            # Normalise alias signal names so all components share one label:
            # "SCK" → "SCLK", "SDI" → "MOSI", "SDO" → "MISO"
            # IMPORTANT: Do NOT canonicalise "TX" or "RX" here.  Those two
            # signal names appear in each other's alias sets ("TX" is in the
            # "RX" alias set and vice versa) for UART cross-wiring of slave
            # peripherals.  Applying _SIGNAL_CANONICAL to "TX" would return
            # "RX" and vice versa, silently swapping every MCU UART TX/RX
            # HIR net assignment and causing Output-Output ERC errors.
            # HIR net names already use canonical signal names, so no
            # normalisation is needed for TX/RX — only SPI aliases like
            # SCK→SCLK need it.
            if raw_sig in ("TX", "RX"):
                canonical_sig = raw_sig
            else:
                canonical_sig = _SIGNAL_CANONICAL.get(raw_sig, raw_sig)
            for pin_ref in net.get("pins", []):
                cid = pin_ref.get("component_id", "")
                pname = str(pin_ref.get("pin_name", ""))
                if cid and pname:
                    pin_to_signal[(cid, pname)] = canonical_sig
                    pin_to_hir_net_name[(cid, pname)] = net_name
                    _key = (cid, pname)
                    if _key not in pin_to_all_hir_nets:
                        pin_to_all_hir_nets[_key] = []
                    if net_name not in pin_to_all_hir_nets[_key]:
                        pin_to_all_hir_nets[_key].append(net_name)

        # Extend bus_signals with signals found only in HIR nets (not in bus_contracts)
        for sig in dict.fromkeys(pin_to_signal.values()):
            if sig not in bus_signals:
                bus_signals.append(sig)

        # Prune bus signals that have no non-MCU peripheral with matching pins.
        # Prevents dangling SDA/SCL (or TX/RX) labels when a bus contract
        # erroneously lists a component with no matching pins (e.g. an Ethernet
        # PHY placed in an I2C slave slot — it has no SDA/SCL pins, so the MCU
        # bus labels would be left unconnected and trigger label_dangling ERC errors).
        _mcu_comp_ids: set[str] = {c["id"] for c in mcus}
        _prunable_sigs: set[str] = set()
        for _bsig in bus_signals:
            _all_bsig_names = {_bsig} | _ALL_BUS_SIGNAL_ALIASES.get(_bsig, frozenset())
            _has_peripheral_pin = False
            for _comp in components:
                _cid2 = _comp["id"]
                if _cid2 in _mcu_comp_ids:
                    continue
                _sym_key = comp_sym.get(_cid2)
                if not _sym_key:
                    continue
                _sdef2 = sym_defs.get(_sym_key)
                if not _sdef2 or _sdef2.ref_prefix in ("R", "C", "L", "FB", "SW"):
                    continue
                for _pin2 in _sdef2.pins:
                    _pparts2 = {p.upper() for p in _pin2.name.split("/")}
                    if _pparts2 & _all_bsig_names:
                        _has_peripheral_pin = True
                        break
                    # HIR-assigned signal (pin number or name → signal)
                    if (pin_to_signal.get((_cid2, _pin2.number)) == _bsig
                            or pin_to_signal.get((_cid2, _pin2.name.upper())) == _bsig
                            or pin_to_signal.get((_cid2, _pin2.name)) == _bsig):
                        _has_peripheral_pin = True
                        break
                if _has_peripheral_pin:
                    break
            if not _has_peripheral_pin:
                _prunable_sigs.add(_bsig)
        if _prunable_sigs:
            bus_signals = [s for s in bus_signals if s not in _prunable_sigs]

        # Analog / point-to-point nets — nets that are NOT shared bus signals.
        # Includes: non-bus signal nets (op-amp feedback, etc.) and per-slave
        # chip-select (CS) nets (is_bus=True but pattern "..._CS_...").
        # Pins in these nets get net labels so KiCad connects them symbolically.
        _CS_PIN_ALIASES = frozenset({"CS", "NSS", "SS", "NCS", "CS_N", "CSB", "LOAD", "SCSN"})
        # Power-like net names that LLMs sometimes emit without setting is_power=True.
        # These should be wired as power symbols, not net labels, to avoid dangling.
        _POWER_LIKE_NET_MAP: dict[str, str] = {
            "GND": "GND", "AGND": "GND", "DGND": "GND",
            "+3V3": "+3V3", "3V3": "+3V3", "3.3V": "+3V3",
            "+5V": "+5V", "5V": "+5V", "VCC": "+5V",
            "+12V": "+12V", "12V": "+12V",
            "+VBAT": "+VBAT", "VBAT": "+VBAT",
            "VDD": "+3V3", "VIN": "+5V",
        }
        pin_to_analog_net: dict[tuple[str, str], str] = {}
        # Count HIR pins per analog net — nets with 1 pin would create dangling
        # labels if wired as net labels; they are better handled as no_connect.
        _analog_net_pin_count: dict[str, int] = {}
        for net in self._hir.get("nets", []):
            net_name = str(net.get("name", ""))
            is_cs_net = "_CS_" in net_name.upper()
            if (net.get("is_bus") and not is_cs_net) or net.get("is_power"):
                continue
            _analog_net_pin_count[net_name] = len(net.get("pins", []))
            for pin_ref in net.get("pins", []):
                cid   = str(pin_ref.get("component_id", ""))
                pname = str(pin_ref.get("pin_name", ""))
                if cid and pname:
                    # CS nets: setdefault so the first CS net wins when
                    # two CS lines share the same MCU GPIO.  Combined
                    # with _owned_analog_count filtering below, this
                    # prevents dangling labels for the "losing" net.
                    # Non-CS nets: direct assignment (last-wins) is safe
                    # because non-CS pin collisions are rare HIR artefacts
                    # where the last (most-specific) net is preferred.
                    if is_cs_net:
                        pin_to_analog_net.setdefault((cid, pname.upper()), net_name)
                        pin_to_analog_net.setdefault((cid, pname), net_name)
                    else:
                        pin_to_analog_net[(cid, pname.upper())] = net_name
                        pin_to_analog_net[(cid, pname)] = net_name
                    # For CS nets, register common chip-select aliases for
                    # EVERY component in the net so symbols with "NSS"
                    # match HIR "CS" and vice-versa.  MCU HIR pin names
                    # are often GPIO names (e.g. "GPIO_SD_B0_01") that
                    # don't appear in _CS_PIN_ALIASES, so the old guard
                    # `pname.upper() in _CS_PIN_ALIASES` blocked the MCU
                    # from receiving the CS label altogether.
                    if is_cs_net:
                        for alias in _CS_PIN_ALIASES:
                            # setdefault: if multiple CS nets share a
                            # component, the first one wins per alias.
                            pin_to_analog_net.setdefault((cid, alias), net_name)

        # Compute "owned" pin counts per analog net.  A pin is "owned" by a
        # net iff pin_to_analog_net maps that (component, pin) to that net's
        # name.  When two nets share a pin (e.g. two CS lines sharing a GPIO),
        # setdefault above gives ownership to the first net; the second net
        # gets a lower owned count.  Nets with <2 owned pins would produce
        # dangling labels and are skipped (slave pin gets no_connect instead).
        _owned_analog_count: dict[str, int] = {}
        for _net in self._hir.get("nets", []):
            _nn = str(_net.get("name", ""))
            if not _nn or _nn not in _analog_net_pin_count:
                continue
            _cnt = 0
            for _pr in _net.get("pins", []):
                _c = str(_pr.get("component_id", ""))
                _p = str(_pr.get("pin_name", ""))
                if _c and _p and pin_to_analog_net.get((_c, _p.upper())) == _nn:
                    _cnt += 1
            _owned_analog_count[_nn] = _cnt

        # Compute effective schematic net counts: subtract pins that belong to
        # bus-signal-assigned R passives (they get bus labels, not HIR-net labels).
        # This prevents "excess" R passives from getting dangling labels when
        # their sibling Rs are consumed by bus signal slots.
        _r_passives_ordered = [
            c for c in passives
            if sym_defs[comp_sym[c["id"]]].ref_prefix == "R"
            # Exclude pullup/pulldown resistors that carry analog signals (e.g. BTN
            # pullups, feedback Rs) — those should NOT be consumed as bus-series Rs.
            # Bus termination Rs have both pins in is_bus nets, which are filtered
            # out of pin_to_analog_net, so they pass this check correctly.
            and not any(
                pin_to_analog_net.get((c["id"], pnum))
                for pnum in ("1", "2")
            )
        ]
        # Use max(bus_signals, HIR-assigned Rs) so multi-UART designs with more
        # bypass Rs than unique bus signals (TX/RX are shared across buses) don't
        # drop the extra Rs into the excess-R path.
        _n_hir_bus_Rs = sum(
            1 for c in _r_passives_ordered
            if pin_to_hir_net_name.get((c["id"], "1"))
            or pin_to_hir_net_name.get((c["id"], "2"))
        )
        _n_bus_Rs = min(max(len(bus_signals), _n_hir_bus_Rs), len(_r_passives_ordered))
        _bus_r_ids = {c["id"] for c in _r_passives_ordered[:_n_bus_Rs]}
        # Build effective count: HIR count minus pins consumed by bus-signal Rs
        _effective_net_count: dict[str, int] = dict(_analog_net_pin_count)
        for _rid in _bus_r_ids:
            for _pnum in ("1", "2"):
                _anet = pin_to_analog_net.get((_rid, _pnum))
                if _anet:
                    _effective_net_count[_anet] = max(
                        0, _effective_net_count.get(_anet, 0) - 1
                    )

        # Assemble s-expression
        lines: list[str] = []
        lines.append('(kicad_sch (version 20230121) (generator "boardsmith-fw")')
        lines.append("")
        # Root sheet UUID -- KiCad 7 requires this so (instances) paths resolve.
        lines.append(f'  (uuid "{self._root_uuid}")')
        lines.append("")
        lines.append('  (paper "A4")')
        lines.append("")

        # --- lib_symbols (prefixed with library name for KiCad resolution) ---
        raw_syms: list[str] = []
        seen: set[str] = set()
        for sym_id, sdef in sym_defs.items():
            if sym_id not in seen:
                raw_syms.append(self._lib_symbol(sym_id, sdef))
                seen.add(sym_id)
        raw_syms.append(self._power_lib_symbol("GND"))
        raw_syms.append(self._power_lib_symbol("+3V3"))
        raw_syms.append(self._power_lib_symbol("+5V"))
        raw_syms.append(self._power_lib_symbol("+12V"))
        raw_syms.append(self._power_lib_symbol("+VBAT"))
        raw_syms.append(self._pwrflag_lib_symbol())
        self._lib_symbols_raw = raw_syms
        lines.append("  (lib_symbols")
        for raw in raw_syms:
            lines.append(self._prefix_lib_sym(raw))
        lines.append("  )")
        lines.append("")

        # --- Component instances ---
        for comp in components:
            sym_id = comp_sym[comp["id"]]
            sdef   = sym_defs[sym_id]
            ref    = ref_map[comp["id"]]
            pos    = positions.get(comp["id"], (50.0, 50.0))
            lines.append(self._symbol_inst(comp, sym_id, sdef, ref, pos))

        # --- Bus wire routing (net-label based, no spine) ---
        # Primary MCU = first MCU in the design.  Secondary MCUs (co-processors)
        # have their UART TX/RX cross-connected (TX→RX, RX→TX) to the primary MCU.
        _primary_mcu_ids: set[str] = {mcus[0]["id"]} if mcus else set()
        lines.extend(
            self._draw_bus_wires(
                components, sym_defs, comp_sym, positions, bus_signals,
                pin_to_signal, spi_slaves, primary_mcu_ids=_primary_mcu_ids,
                can_slaves=can_slaves,
                uart_slave_to_bus=uart_slave_to_bus,
                uart_master_to_buses=uart_master_to_buses,
                pin_to_hir_net_name=pin_to_hir_net_name,
                pin_to_all_hir_nets=pin_to_all_hir_nets,
            )
        )

        # Track positions of placed power symbols per net so sentinel PWR_FLAGs
        # can be co-located with an existing power symbol on the same net.
        # Maps net_name -> (x, y) of the most recently placed power symbol.
        _pwr_sym_last_pos: dict[str, tuple[float, float]] = {}

        # --- Pull-up / pull-down passive wiring ---
        # Resistors: pin1 -> bus signal net label, pin2 -> +3V3 (pull-up)
        # Capacitors: pin1 -> +3V3, pin2 -> GND  (decoupling)
        bus_sig_idx = 0
        for comp in passives:
            sym_id = comp_sym[comp["id"]]
            sdef   = sym_defs[sym_id]
            px, py = positions[comp["id"]]
            if sdef.ref_prefix == "C":
                # Capacitor: horizontal pins use C_PLATE_X + C_PIN_LEN.
                # Check HIR nets first so that crystal load caps get NET_OSC_IN/OUT
                # instead of the generic +3V3/GND fallback.
                pin1_x = px - (self.C_PLATE_X + self.C_PIN_LEN)
                pin2_x = px + (self.C_PLATE_X + self.C_PIN_LEN)
                for _pnum, _cpx in [("1", pin1_x), ("2", pin2_x)]:
                    _dflt = "+3V3" if _pnum == "1" else "GND"
                    _anet = pin_to_analog_net.get((comp["id"], _pnum))
                    if _anet:
                        _std = _POWER_LIKE_NET_MAP.get(_anet)
                        if _std:
                            lines.extend(self._power_symbol_at(_std, _cpx, py))
                            _pwr_sym_last_pos[_std] = (_cpx, py)
                        elif _effective_net_count.get(_anet, 0) >= 2:
                            _angle = 180 if _pnum == "1" else 0
                            lines.append(self._net_label_sym(_anet, _cpx, py, _angle))
                        else:
                            lines.append(self._no_connect(_cpx, py))
                    else:
                        lines.extend(self._power_symbol_at(_dflt, _cpx, py))
                        _pwr_sym_last_pos[_dflt] = (_cpx, py)
            elif sdef.ref_prefix == "R" and comp["id"] in _bus_r_ids:
                # Bus R: left pin → bus signal, right pin → same signal.
                # Series protection Rs (e.g. UART TX/RX series R) carry the
                # same logical bus signal on BOTH pins.  Derive the signal
                # from pin_to_signal (built from HIR net names) so the correct
                # signal (e.g. "TX") is used even when bus_signals starts with
                # I2C signals (SDA/SCL).  The old sequential bus_sig_idx
                # would assign SDA to a UART TX series R when I2C is listed first.
                cid = comp["id"]
                _p1_sig_hir = pin_to_signal.get((cid, "1"))
                _p2_sig_hir = pin_to_signal.get((cid, "2"))
                # Prefer connector-side (pin 2) signal; fall back to MCU-side (pin 1)
                _hir_sig = _p2_sig_hir or _p1_sig_hir
                # For multi-UART: use separate HIR net names for pin 1 (MCU-
                # side, e.g. uart0_TX_MCU) and pin 2 (slave-side, e.g. uart0_TX)
                # so the series bypass R correctly bridges the two different nets.
                # Using the same label on both pins would leave the MCU-side or
                # slave-side label dangling and cause "label not connected" ERC errors.
                _is_multi_uart_here = any(
                    len(buses) > 1 for buses in uart_master_to_buses.values()
                ) if uart_master_to_buses else False
                _p1_hir_net_r = pin_to_hir_net_name.get((cid, "1")) if pin_to_hir_net_name else None
                _p2_hir_net_r = pin_to_hir_net_name.get((cid, "2")) if pin_to_hir_net_name else None
                if _is_multi_uart_here and _hir_sig in ("TX", "RX") and _p1_hir_net_r and _p2_hir_net_r:
                    # Bridge MCU net ↔ slave net via separate pin labels
                    pin1_x = px - (self.R_BODY_HW + self.R_PIN_LEN)
                    pin2_x = px + (self.R_BODY_HW + self.R_PIN_LEN)
                    lines.append(self._net_label_sym(_p1_hir_net_r, pin1_x, py, 180))
                    lines.append(self._net_label_sym(_p2_hir_net_r, pin2_x, py, 0))
                elif _is_multi_uart_here and _hir_sig in ("TX", "RX"):
                    # Fall back: use whichever net name is available
                    _hir_net = _p2_hir_net_r or _p1_hir_net_r
                    if _hir_net:
                        _hir_sig = _hir_net
                pin1_x = px - (self.R_BODY_HW + self.R_PIN_LEN)
                pin2_x = px + (self.R_BODY_HW + self.R_PIN_LEN)
                if (_is_multi_uart_here and _hir_sig in ("TX", "RX")
                        and _p1_hir_net_r and _p2_hir_net_r):
                    pass  # already emitted above
                elif _hir_sig:
                    # Series R with known signal: both pins on the same net label
                    lines.append(self._net_label_sym(_hir_sig, pin1_x, py, 180))
                    lines.append(self._net_label_sym(_hir_sig, pin2_x, py, 0))
                else:
                    # No HIR signal data → fall back to sequential bus signal slot
                    sig = bus_signals[bus_sig_idx]
                    bus_sig_idx += 1
                    lines.append(self._net_label_sym(sig, pin1_x, py, 180))
                    _p2_sig_seq = pin_to_signal.get((cid, "2"))
                    if _p2_sig_seq:
                        lines.append(self._net_label_sym(_p2_sig_seq, pin2_x, py, 0))
                    else:
                        lines.extend(self._power_symbol_at("+3V3", pin2_x, py))
            elif sdef.ref_prefix == "R":
                # Excess R passive (gate/series resistor with no bus signal slot).
                # Connect between +3V3 and GND so both pins are tied and no
                # "pin not connected" ERC error is raised.
                # HOWEVER: first check if the HIR assigned actual signal nets
                # to this resistor's pins (e.g. a pull-down R with one pin on
                # a GPIO net and the other on GND/3V3).  Prefer the real net
                # label over a generic +3V3/GND fallback so that nets like
                # BTN_SKRPACE010_IN get at least two schematic connections.
                # Nets with only 1 HIR pin cannot form a valid 2-ended label;
                # use no_connect to suppress dangling-label ERC errors.
                # Power-like names (5V, 3V3, …) are wired as power symbols.
                _POWER_LABEL_MAP_R = {"GND": "GND", "3V3_REG": "+3V3", "VIN_5V": "+5V"}
                pin1_x = px - (self.R_BODY_HW + self.R_PIN_LEN)
                pin2_x = px + (self.R_BODY_HW + self.R_PIN_LEN)
                for _pnum, _px in [("1", pin1_x), ("2", pin2_x)]:
                    _anet = pin_to_analog_net.get((comp["id"], _pnum))
                    if _anet:
                        # Check if this looks like a power rail name
                        _std_pwr = _POWER_LIKE_NET_MAP.get(_anet)
                        if _std_pwr:
                            lines.extend(self._power_symbol_at(_std_pwr, _px, py))
                            _pwr_sym_last_pos[_std_pwr] = (_px, py)
                        elif _effective_net_count.get(_anet, 0) >= 2:
                            # Multi-pin net → label will connect to ≥2 schematic pins
                            _angle = 0 if _pnum == "2" else 180
                            lines.append(self._net_label_sym(_anet, _px, py, _angle))
                        else:
                            # Single-pin net → label would dangle; mark no_connect
                            lines.append(self._no_connect(_px, py))
                    else:
                        # Check power net from HIR
                        _pwr_net = None
                        for _hnet in self._hir.get("nets", []):
                            if _hnet.get("is_power"):
                                for _hp in _hnet.get("pins", []):
                                    if _hp.get("component_id") == comp["id"] and str(_hp.get("pin_name")) == _pnum:
                                        _pwr_net = _hnet["name"]
                                        break
                            if _pwr_net:
                                break
                        if _pwr_net:
                            _pwr_label = _POWER_LABEL_MAP_R.get(_pwr_net, _pwr_net)
                            lines.extend(self._power_symbol_at(_pwr_label, _px, py))
                        else:
                            # Ultimate fallback: pin 1 → +3V3, pin 2 → GND
                            _fb = "+3V3" if _pnum == "1" else "GND"
                            lines.extend(self._power_symbol_at(_fb, _px, py))
            elif sdef.ref_prefix == "Y":
                # Crystal oscillator: wire both pins using HIR nets.
                # Pin 1 (left) → NET_OSC_IN, Pin 2 (right) → NET_OSC_OUT.
                # Uses IC-style geometry via _pin_abs() for accurate coordinates.
                for pin in sdef.pins:
                    pin_x, pin_y = self._pin_abs(sdef, pin, px, py)
                    _pnet = (
                        pin_to_analog_net.get((comp["id"], pin.number))
                        or pin_to_analog_net.get((comp["id"], pin.name.upper()))
                        or pin_to_analog_net.get((comp["id"], pin.name))
                    )
                    if _pnet:
                        _std = _POWER_LIKE_NET_MAP.get(_pnet)
                        if _std:
                            lines.extend(self._power_symbol_at(_std, pin_x, pin_y))
                        elif _effective_net_count.get(_pnet, 0) >= 2:
                            _angle = 180 if pin.side == "left" else 0
                            lines.append(self._net_label_sym(_pnet, pin_x, pin_y, _angle))
                        else:
                            lines.append(self._no_connect(pin_x, pin_y))
                    else:
                        lines.append(self._no_connect(pin_x, pin_y))

        # --- Actuator / switch wiring ---
        # Buttons (SW* components) have 2 passive pins connected via HIR nets:
        # pin 1 → signal net (BTN_*_IN), pin 2 → GND.
        # Wire them with net labels / power symbols based on HIR net assignments.
        #
        # IMPORTANT: SW symbols use _lib_symbol_ic() geometry (IC-style box with
        # PIN_LEN stubs), NOT resistor geometry. Use _pin_abs() to get the exact
        # pin endpoint coordinates so labels land precisely on the pin connection
        # points and don't produce "pin_not_connected" / "label_dangling" ERC errors.
        _POWER_LABEL_MAP = {"GND": "GND", "3V3_REG": "+3V3", "VIN_5V": "+5V"}
        for comp in components:
            sdef = sym_defs[comp_sym[comp["id"]]]
            if sdef.ref_prefix != "SW":
                continue
            cx, cy = positions.get(comp["id"], (50.0, 50.0))
            for pin in sdef.pins:
                pin_x, pin_y = self._pin_abs(sdef, pin, cx, cy)
                pname = pin.number  # "1" or "2"
                # Check analog net (non-bus, non-power signal)
                anet = pin_to_analog_net.get((comp["id"], pname))
                if anet:
                    # Draw a wire stub from pin endpoint outward, then place the
                    # net label at the stub tip.  This matches _draw_bus_wires
                    # convention and ensures KiCad's ERC can see the connection
                    # (a label placed directly on a passive pin with no wire stub
                    # can appear "dangling" in KiCad's connectivity check).
                    if pin.side == "right":
                        stub_x = pin_x + self.WIRE_LEN
                        lines.append(self._wire_seg(pin_x, pin_y, stub_x, pin_y))
                        lines.append(self._net_label_sym(anet, stub_x, pin_y, 0))
                    else:
                        stub_x = pin_x - self.WIRE_LEN
                        lines.append(self._wire_seg(stub_x, pin_y, pin_x, pin_y))
                        lines.append(self._net_label_sym(anet, stub_x, pin_y, 180))
                else:
                    # Check power net
                    pwr_net = None
                    for hnet in self._hir.get("nets", []):
                        if hnet.get("is_power"):
                            for hp in hnet.get("pins", []):
                                if hp.get("component_id") == comp["id"] and str(hp.get("pin_name")) == pname:
                                    pwr_net = hnet["name"]
                                    break
                        if pwr_net:
                            break
                    if pwr_net:
                        pwr_label = _POWER_LABEL_MAP.get(pwr_net, pwr_net)
                        lines.extend(self._power_symbol_at(pwr_label, pin_x, pin_y))
                    else:
                        lines.extend(self._power_symbol_at("GND", pin_x, pin_y))

        # --- Power connections ---
        # Build set of config-pin names to skip for SPI slaves — their SDO/SDI
        # pins are SPI data lines, NOT config pins (SDO=address is I2C-specific).
        _all_spi_aliases = {a for aliases in _SPI_SLAVE_SIGNAL_ALIASES.values() for a in aliases}
        for comp in components:
            sym_id = comp_sym[comp["id"]]
            sdef   = sym_defs[sym_id]
            pos    = positions.get(comp["id"], (50.0, 50.0))
            skip_cfg = _all_spi_aliases if comp["id"] in spi_slaves else frozenset()
            lines.extend(self._power_connections(sdef, pos, skip_config_pins=skip_cfg))

        # --- PWR_FLAG markers so power nets are "driven" ---
        # KiCad ERC requires at least one power_out pin on each power net.
        # Place PWR_FLAG on the first MCU's +3V3 and GND wire endpoints.
        # Exception: if a real component already drives the net with a
        # power_out pin (e.g. LDO VOUT), skip the PWR_FLAG — two power_out
        # pins on the same net cause pin_to_pin ERC errors in KiCad 9.
        driven_nets: set[str] = set()
        for comp in components:
            for pin in sym_defs[comp_sym[comp["id"]]].pins:
                if pin.type == "power_out":
                    n = _net_for_pin(pin.name.upper())
                    if n is not None:
                        driven_nets.add(n)

        pwr_flag_nets_placed: set[str] = set()
        for comp in mcus[:1]:
            sym_id = comp_sym[comp["id"]]
            sdef   = sym_defs[sym_id]
            pos    = positions.get(comp["id"], (50.0, 50.0))
            for pin in sdef.pins:
                if pin.type != "power_in":
                    continue
                net = _net_for_pin(pin.name.upper())
                if net is None or net in pwr_flag_nets_placed:
                    continue
                # If a real component already drives this net with a power_out
                # pin (e.g. LDO VOUT), don't add a PWR_FLAG — that would cause
                # pin_to_pin: power_out + power_out.
                if net in driven_nets:
                    pwr_flag_nets_placed.add(net)
                    continue
                px, py = self._pin_abs(sdef, pin, *pos)
                is_left = pin.side == "left"
                wx = px - self.WIRE_LEN if is_left else px + self.WIRE_LEN
                # Place PWR_FLAG one WIRE_LEN beyond the power symbol and
                # add a wire from the power symbol endpoint (wx) to the flag
                # so the flag's pin is physically on the net wire.  Without
                # this wire KiCad 9 reports pin_not_connected on the flag.
                flag_x = wx - self.WIRE_LEN if is_left else wx + self.WIRE_LEN
                lines.append(self._wire_seg(wx, py, flag_x, py))
                lines.extend(self._pwrflag_at(net, flag_x, py))
                pwr_flag_nets_placed.add(net)

        # --- Extended PWR_FLAG scan: non-MCU components ---
        # The MCU loop above only covers +3V3 and GND (MCU power rails).
        # Some nets (e.g. +5V / VBUS from USB connector, +12V from barrel jack)
        # are driven externally and only appear as power_in on connectors or
        # LDO inputs — they never appear on MCU pins and thus never get a
        # PWR_FLAG.  This second pass picks up any such unhandled nets.
        mcu_ids = {c["id"] for c in mcus[:1]}
        for comp in components:
            cid = comp["id"]
            if cid in mcu_ids:
                continue  # already handled above
            sym_id = comp_sym[cid]
            sdef   = sym_defs[sym_id]
            pos    = positions.get(cid, (50.0, 50.0))
            for pin in sdef.pins:
                if pin.type != "power_in":
                    continue
                net = _net_for_pin(pin.name.upper())
                if net is None or net in pwr_flag_nets_placed or net in driven_nets:
                    continue
                px, py = self._pin_abs(sdef, pin, *pos)
                is_left = pin.side == "left"
                wx = px - self.WIRE_LEN if is_left else px + self.WIRE_LEN
                flag_x = wx - self.WIRE_LEN if is_left else wx + self.WIRE_LEN
                lines.append(self._wire_seg(wx, py, flag_x, py))
                lines.extend(self._pwrflag_at(net, flag_x, py))
                pwr_flag_nets_placed.add(net)

        # --- Sentinel PWR_FLAG: cover power nets that appear as power symbols
        # in the schematic but have no component power_in pin to trigger the
        # MCU or extended scan.  Typical case: +5V supplied by external barrel
        # jack or USB connector where the HIR net is named "5V" (passive caps
        # only, no power_in pin on any symbol maps to +5V).
        _SENTINEL_NETS = ("+5V", "+12V", "+VBAT")
        for _snet in _SENTINEL_NETS:
            if _snet in pwr_flag_nets_placed or _snet in driven_nets:
                continue
            # Check if any HIR net resolves to this power net via _POWER_LIKE_NET_MAP.
            # If such a net has >=1 pin, it will produce a power symbol in the
            # schematic that needs a corresponding PWR_FLAG.
            _need_flag = False
            for _hnet in self._hir.get("nets", []):
                _hn = str(_hnet.get("name", ""))
                _mapped = _POWER_LIKE_NET_MAP.get(_hn) or _POWER_LIKE_NET_MAP.get(_hn.upper())
                if _mapped == _snet and len(_hnet.get("pins", [])) > 0:
                    _need_flag = True
                    break
            if not _need_flag:
                continue
            # Place sentinel PWR_FLAG co-located with an existing power symbol
            # on this net so the flag's pwr pin is on the same net wire.
            # If _pwr_sym_last_pos has a position for this net, place the flag
            # one WIRE_LEN to the right; otherwise fall back to MCU-relative pos.
            if _snet in _pwr_sym_last_pos:
                _existing_x, _existing_y = _pwr_sym_last_pos[_snet]
                # The existing power symbol is at (_existing_x, _existing_y).
                # Place flag one WIRE_LEN to the right with a connecting wire.
                _fx = _existing_x + self.WIRE_LEN
                lines.append(self._wire_seg(_existing_x, _existing_y, _fx, _existing_y))
                lines.extend(self._pwrflag_at(_snet, _fx, _existing_y))
            else:
                # Fallback: place near first MCU or at fixed offset.
                _sentinel_offset = list(_SENTINEL_NETS).index(_snet) + 3
                if mcus:
                    _sp = positions.get(mcus[0]["id"], (50.0, 50.0))
                    _sx, _sy = _sp[0], _sp[1] + self.WIRE_LEN * _sentinel_offset
                else:
                    _sx, _sy = 50.0, 50.0 + self.WIRE_LEN * _sentinel_offset
                _fx = _sx + self.WIRE_LEN
                lines.append(self._wire_seg(_sx, _sy, _fx, _sy))
                lines.extend(self._pwrflag_at(_snet, _fx, _sy))
            pwr_flag_nets_placed.add(_snet)

        # --- No-connect / net-label for unconnected pins ---
        # Pins that are neither power pins, bus-signal pins, nor config pins
        # get either:
        #   • a net label  — if the same pin name appears on both a U-peripheral
        #     and a J-connector (e.g. CANH/CANL between CAN transceiver and
        #     CAN bus connector, A/B between RS485 transceiver and connector).
        #     Net labels with the same text auto-connect in KiCad.
        #   • a no-connect marker  — all other unconnected signal/passive pins.
        #
        # Applies to: U (ICs), J (connectors), D (diodes), Q (transistors).
        # R and C passives are wired separately above; L/other passives excluded.
        all_bus_parts: set[str] = set()
        for sig in bus_signals:
            all_bus_parts.add(sig.upper())

        # Precompute active bus signal aliases — aliases of bus signals
        # that have active bus_contracts.  Used to detect bus pins that
        # use manufacturer-specific naming (e.g. "LPSPI1_SCK" for SCLK).
        _all_bus_set = set(bus_signals)
        _active_bus_aliases: set[str] = set()
        for _canon, _al_set in _ALL_BUS_SIGNAL_ALIASES.items():
            if _canon in _all_bus_set:
                _active_bus_aliases.update(_al_set)

        # Build set of component IDs that are actually assigned to a bus.
        # Bus alias matching (SDI/DIN → MOSI, DI → TX, etc.) for no-connect
        # suppression ONLY applies to components on a bus — otherwise an I2S
        # amplifier with a DIN pin would inherit the SPI-MOSI alias and skip
        # its no-connect even though it's not connected to SPI at all.
        _bussed_components: set[str] = {_ck[0] for _ck in pin_to_signal}

        # Collect pin names shared between U-peripherals and J-connectors so
        # we can connect transceiver outputs to bus connector inputs via labels.
        _u_periph_pins: set[str] = set()
        _j_conn_pins:   set[str] = set()
        for _c in components:
            _sd = sym_defs[comp_sym[_c["id"]]]
            if _sd.ref_prefix == "U" and _c.get("role") not in ("mcu",):
                for _p in _sd.pins:
                    if _p.type not in ("power_in", "power_out"):
                        _u_periph_pins.add(_p.name.upper())
            elif _sd.ref_prefix == "J":
                for _p in _sd.pins:
                    if _p.type not in ("power_in", "power_out"):
                        _j_conn_pins.add(_p.name.upper())
        uj_shared_pins: set[str] = _u_periph_pins & _j_conn_pins

        for comp in components:
            cid    = comp["id"]
            sym_id = comp_sym[cid]
            sdef   = sym_defs[sym_id]
            # ICs (U), connectors (J), diodes (D), transistors (Q) all need
            # explicit no-connect or net-label placement.  R/C passives are
            # handled by the pull-up/decoupling wiring loop above.
            if sdef.ref_prefix not in ("U", "J", "D", "Q"):
                continue
            pos    = positions.get(cid, (50.0, 50.0))
            for pin in sdef.pins:
                # power_in pins are always handled by _power_connections.
                if pin.type == "power_in":
                    continue
                pn_up = pin.name.upper()
                # power_out pins on standard nets ("+3V3", "+5V", "GND") get a
                # power symbol via _power_connections and need no no_connect.
                # power_out pins on non-standard nets (e.g. TP4056 BAT→"+VBAT")
                # are skipped by _power_connections and get a no_connect here.
                if pin.type == "power_out":
                    _po_net = _net_for_pin(pn_up)
                    if _po_net in ("GND", "+3V3", "+5V"):
                        continue  # power symbol already placed
                if _CONFIG_PIN_NETS.get(pn_up):
                    continue
                pin_parts = [p.upper() for p in pin.name.split("/")]
                _is_bus_pin = False
                for bp in all_bus_parts:
                    if bp in pin_parts:
                        _is_bus_pin = True
                        break
                    for part in pin_parts:
                        if part.endswith("_" + bp):
                            # CAN guard: CAN_TX/CAN_RX are NOT UART bus pins
                            if bp in ("TX", "RX") and any(part.startswith(cp) for cp in ("CAN_", "FDCAN", "FLEXCAN")):
                                continue
                            _is_bus_pin = True
                            break
                    if _is_bus_pin:
                        break
                if _is_bus_pin:
                    continue
                # Skip if this pin is assigned to a bus signal via HIR nets
                if pin_to_signal.get((cid, pin.number)) or pin_to_signal.get((cid, pin.name)):
                    continue
                # Skip if this pin will be wired via a bus slave alias
                # (SDI/SDO → MOSI/MISO, DI/RO → TX/RX, etc.)
                # But ONLY if the canonical signal is actually in bus_signals
                # AND this component is actually on a bus (to avoid DIN on an
                # I2S device being confused with MOSI when SPI is active).
                # Exception: Ethernet PHY RMII data pins (TXD0/TXD1/RXD0/RXD1
                # etc.) appear in UART alias sets but are NOT wired via bus
                # labels (_draw_bus_wires suppresses them for Ethernet PHYs).
                # Fall through to no-connect placement for these pins.
                _RMII_NC_ALIASES = frozenset(
                    {
                        "TXD0", "TX0", "RXD0", "RX0",
                        "TXD1", "TX1", "RXD1", "RX1",
                        # Some KiCad symbol variants omit the digit suffix:
                        "TXD", "RXD",
                    }
                )
                _ETH_PHY_KWS_NC = ("LAN8720", "LAN8741", "DP838", "KSZ80", "RTL820", "IP101")
                _is_eth_phy_nc = any(
                    k in (comp.get("mpn") or "").upper() for k in _ETH_PHY_KWS_NC
                )
                _is_rmii_nc_pin = _is_eth_phy_nc and any(
                    part in _RMII_NC_ALIASES for part in pin_parts
                )
                # UART-variant pins (TXD0, RXD0, TX0, RX0, TXD, RXD) on
                # secondary MCUs that are NOT assigned to a UART slave bus are
                # intentionally unconnected — _draw_bus_wires suppresses their
                # labels via the RMII-MCU guard.  Don't let the bussed-component
                # skip here leave them without a no-connect marker (which would
                # cause KiCad "pin_not_connected" ERC errors).
                _UART_NC_ALIASES = frozenset(
                    {"TX", "RX", "TXD0", "RXD0", "TX0", "RX0", "TXD", "RXD", "DI", "RO"}
                )
                _is_mcu_nc = comp.get("role") == "mcu"
                _is_uart_slave_nc = cid in uart_slave_to_bus
                _is_primary_nc = cid in _primary_mcu_ids
                _is_suppressed_secondary_uart = (
                    _is_mcu_nc
                    and not _is_uart_slave_nc
                    and not _is_primary_nc
                    and any(part in _UART_NC_ALIASES for part in pin_parts)
                )
                # Primary MCU: UART alternate-function pins (RXD0/TXD0 etc.) that
                # were suppressed in _draw_bus_wires because HIR already assigned
                # the canonical UART signal to a different GPIO on this MCU.  These
                # pins are in _active_bus_aliases (they'd match via alias) so the
                # bussed-component skip below would leave them without a no-connect
                # marker, causing pin_not_connected ERC errors.  Fall through to
                # no-connect placement for them instead.
                _UART_NC_TO_CANON: dict[str, str] = {
                    "TX": "TX", "TXD": "TX", "TXD0": "TX", "TX0": "TX",
                    "RX": "RX", "RXD": "RX", "RXD0": "RX", "RX0": "RX",
                    "DI": "TX", "RO": "RX",
                }
                _is_suppressed_primary_uart_nc = False
                if _is_mcu_nc and _is_primary_nc:
                    for _upart in pin_parts:
                        _ucanon = _UART_NC_TO_CANON.get(_upart)
                        if _ucanon is not None:
                            # HIR assigns this canonical signal to a different pin?
                            _hir_has_canon = any(
                                sv == _ucanon
                                for (cv, _pk), sv in pin_to_signal.items()
                                if cv == cid
                            )
                            _this_pin_hir = (
                                pin_to_signal.get((cid, pin.name)) is not None
                                or pin_to_signal.get((cid, pin.number)) is not None
                            )
                            if _hir_has_canon and not _this_pin_hir:
                                _is_suppressed_primary_uart_nc = True
                                break
                if cid in _bussed_components and any(part in _active_bus_aliases for part in pin_parts):
                    if not _is_rmii_nc_pin and not _is_suppressed_secondary_uart and not _is_suppressed_primary_uart_nc:
                        continue
                # Also check suffix matching against active bus aliases
                # (e.g. "LPSPI1_SCK" ends with "_SCK" where "SCK" is an
                # alias of SCLK).  Mirrors the suffix logic in
                # _draw_bus_wires that places bus labels on such pins.
                _suffix_alias_match = False
                for part in pin_parts:
                    for alias in _active_bus_aliases:
                        if part.endswith("_" + alias):
                            _canon_sig = _SIGNAL_CANONICAL.get(alias, alias)
                            # CAN guard: CAN_TX/CAN_RX are not UART bus pins
                            if _canon_sig in ("TX", "RX") and any(
                                part.startswith(cp)
                                for cp in ("CAN_", "FDCAN", "FLEXCAN")
                            ):
                                continue
                            # JTAG/SWD guard
                            if _canon_sig == "SCLK" and any(
                                part.startswith(jp)
                                for jp in ("SWD_", "JTAG_", "SWDIO", "SWCLK")
                            ):
                                continue
                            _suffix_alias_match = True
                            break
                    if _suffix_alias_match:
                        break
                if cid in _bussed_components and _suffix_alias_match:
                    if not _is_rmii_nc_pin and not _is_suppressed_secondary_uart and not _is_suppressed_primary_uart_nc:
                        continue
                px, py = self._pin_abs(sdef, pin, *pos)
                # Analog / point-to-point signal net (CS nets, op-amp
                # feedback, etc.): net label with the full net name takes
                # priority over the generic uj_shared_pins label so that
                # per-slave CS lines stay separate.
                # Check full pin name, then each "/" sub-part (MCU pins
                # like "PA4/CS" store HIR assignments as just "PA4").
                _anet_label: str | None = (
                    pin_to_analog_net.get((cid, pn_up))
                    or pin_to_analog_net.get((cid, pin.name))
                )
                if not _anet_label:
                    for _part in pin.name.split("/"):
                        _anet_label = pin_to_analog_net.get((cid, _part.upper())) or pin_to_analog_net.get((cid, _part))
                        if _anet_label:
                            break
                if _anet_label and _owned_analog_count.get(_anet_label, 2) >= 2:
                    angle = 0 if pin.side == "right" else 180
                    lines.append(self._net_label_sym(_anet_label, px, py, angle))
                # Shared bus-terminal pin (e.g. CANH, CANL, A, B): net label
                # so transceiver output connects to bus connector terminal.
                elif pn_up in uj_shared_pins:
                    angle = 0 if pin.side == "right" else 180
                    lines.append(self._net_label_sym(pin.name, px, py, angle))
                else:
                    lines.append(self._no_connect(px, py))

        # --- sheet_instances (required) ---
        # Path must include the root sheet UUID for KiCad 7 to resolve annotations.
        lines.append("  (sheet_instances")
        lines.append(f'    (path "/{self._root_uuid}" (page "1"))')
        lines.append("  )")
        lines.append("")
        lines.append(")")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Library symbol definition
    # ------------------------------------------------------------------

    def _lib_symbol(self, sym_id: str, sdef: SymbolDef) -> str:
        """Generate lib_symbol entry.  Passives get compact R/C body shapes."""
        if sdef.ref_prefix == "R":
            return self._lib_symbol_resistor(sym_id, sdef)
        if sdef.ref_prefix == "C":
            return self._lib_symbol_capacitor(sym_id, sdef)
        return self._lib_symbol_ic(sym_id, sdef)

    @staticmethod
    def _tri_state_fixup(pin_type: str, pin_name: str) -> str:
        """Return 'tri_state' for SPI MISO-side output pins (they only drive when
        CS is active), preventing KiCad ERC "Output+Output connected" errors
        on shared SPI buses."""
        if pin_type == "output":
            parts = {p.upper() for p in pin_name.split("/")}
            if parts & _SPI_MISO_NAMES:
                return "tri_state"
        return pin_type

    def _lib_symbol_ic(self, sym_id: str, sdef: SymbolDef) -> str:
        """IC / module symbol -- rectangular box with named pins."""
        eid = _esc_id(sym_id)
        left_pins  = [p for p in sdef.pins if p.side == "left"]
        right_pins = [p for p in sdef.pins if p.side == "right"]
        half_h = max(len(left_pins), len(right_pins), 1) * 2.54 / 2 + 1.27
        hw = self.BODY_HALF_W
        pl = self.PIN_LEN

        out: list[str] = []
        out.append(f'    (symbol "{eid}"')
        out.append(f'      (in_bom yes) (on_board yes)')
        out.append(f'      (property "Reference" "{_esc(sdef.ref_prefix)}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))')
        out.append(f'      (property "Value" "{_esc(sym_id)}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))')
        out.append(f'      (property "Footprint" "{_esc(sdef.footprint)}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))')
        out.append(f'      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))')
        # Body (unit _0_1)
        out.append(f'      (symbol "{eid}_0_1"')
        out.append(f'        (rectangle (start -{hw:.2f} {half_h:.2f}) (end {hw:.2f} -{half_h:.2f})')
        out.append(f'          (stroke (width 0.254) (type default)) (fill (type background)))')
        out.append(f'      )')
        # Pins (unit _1_1)
        out.append(f'      (symbol "{eid}_1_1"')
        # Left-side pins: connection at x=-(hw+pl), angle=0 (body in +x direction)
        y = half_h - 1.27
        for p in left_pins:
            x = -(hw + pl)
            etype = self._tri_state_fixup(p.type, p.name)
            out.append(f'        (pin {_elec(etype)} line (at {x:.2f} {y:.2f} 0) (length {pl:.2f})')
            out.append(f'          (name "{_esc(p.name)}" (effects (font (size 1.27 1.27))))')
            out.append(f'          (number "{_esc(p.number)}" (effects (font (size 1.27 1.27))))')
            out.append(f'        )')
            y -= 2.54
        # Right-side pins: connection at x=+(hw+pl), angle=180 (body in -x direction)
        y = half_h - 1.27
        for p in right_pins:
            x = hw + pl
            etype = self._tri_state_fixup(p.type, p.name)
            out.append(f'        (pin {_elec(etype)} line (at {x:.2f} {y:.2f} 180) (length {pl:.2f})')
            out.append(f'          (name "{_esc(p.name)}" (effects (font (size 1.27 1.27))))')
            out.append(f'          (number "{_esc(p.number)}" (effects (font (size 1.27 1.27))))')
            out.append(f'        )')
            y -= 2.54
        out.append(f'      )')
        out.append(f'    )')
        return "\n".join(out)

    def _lib_symbol_resistor(self, sym_id: str, sdef: SymbolDef) -> str:
        """Compact resistor symbol: rectangular body, 2 passive horizontal pins."""
        eid = _esc_id(sym_id)
        hw  = self.R_BODY_HW
        hh  = self.R_BODY_HH
        pl  = self.R_PIN_LEN
        return "\n".join([
            f'    (symbol "{eid}"',
            f'      (pin_numbers (hide yes)) (pin_names (offset 0) (hide yes))',
            f'      (in_bom yes) (on_board yes)',
            f'      (property "Reference" "{_esc(sdef.ref_prefix)}" (at 0 {hh + 1.0:.2f} 0) (effects (font (size 1.27 1.27))))',
            f'      (property "Value" "{_esc(sym_id)}" (at 0 -{hh + 1.0:.2f} 0) (effects (font (size 1.27 1.27))))',
            f'      (property "Footprint" "{_esc(sdef.footprint)}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
            f'      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
            f'      (symbol "{eid}_0_1"',
            f'        (rectangle (start -{hw:.3f} -{hh:.3f}) (end {hw:.3f} {hh:.3f})',
            f'          (stroke (width 0.254) (type default)) (fill (type none)))',
            f'      )',
            f'      (symbol "{eid}_1_1"',
            f'        (pin passive line (at -{hw + pl:.3f} 0 0) (length {pl:.3f})',
            f'          (name "~" (effects (font (size 1.27 1.27))))',
            f'          (number "1" (effects (font (size 1.27 1.27)))))',
            f'        (pin passive line (at {hw + pl:.3f} 0 180) (length {pl:.3f})',
            f'          (name "~" (effects (font (size 1.27 1.27))))',
            f'          (number "2" (effects (font (size 1.27 1.27)))))',
            f'      )',
            f'    )',
        ])

    def _lib_symbol_capacitor(self, sym_id: str, sdef: SymbolDef) -> str:
        """Compact capacitor symbol: two plate lines, 2 passive horizontal pins."""
        eid = _esc_id(sym_id)
        px  = self.C_PLATE_X
        ph  = self.C_PLATE_H
        pl  = self.C_PIN_LEN
        return "\n".join([
            f'    (symbol "{eid}"',
            f'      (pin_numbers (hide yes)) (pin_names (offset 0) (hide yes))',
            f'      (in_bom yes) (on_board yes)',
            f'      (property "Reference" "{_esc(sdef.ref_prefix)}" (at 0 {ph + 1.0:.2f} 0) (effects (font (size 1.27 1.27))))',
            f'      (property "Value" "{_esc(sym_id)}" (at 0 -{ph + 1.0:.2f} 0) (effects (font (size 1.27 1.27))))',
            f'      (property "Footprint" "{_esc(sdef.footprint)}" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
            f'      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
            f'      (symbol "{eid}_0_1"',
            f'        (polyline (pts (xy -{px:.3f} -{ph:.3f}) (xy -{px:.3f} {ph:.3f}))',
            f'          (stroke (width 0.508) (type default)) (fill (type none)))',
            f'        (polyline (pts (xy {px:.3f} -{ph:.3f}) (xy {px:.3f} {ph:.3f}))',
            f'          (stroke (width 0.508) (type default)) (fill (type none)))',
            f'      )',
            f'      (symbol "{eid}_1_1"',
            f'        (pin passive line (at -{px + pl:.3f} 0 0) (length {pl:.3f})',
            f'          (name "~" (effects (font (size 1.27 1.27))))',
            f'          (number "1" (effects (font (size 1.27 1.27)))))',
            f'        (pin passive line (at {px + pl:.3f} 0 180) (length {pl:.3f})',
            f'          (name "~" (effects (font (size 1.27 1.27))))',
            f'          (number "2" (effects (font (size 1.27 1.27)))))',
            f'      )',
            f'    )',
        ])

    def _power_lib_symbol(self, net: str) -> str:
        """Minimal power symbol definition (GND / +3V3 / +5V)."""
        eid = _esc_id(net)
        if net == "GND":
            # Connection at (0,0), body below -- triangle pointing down
            body = (
                '        (polyline (pts (xy 0 0) (xy 0 -1.27) (xy 1.27 -1.27)'
                ' (xy 0 -2.54) (xy -1.27 -1.27) (xy 0 -1.27))\n'
                '          (stroke (width 0) (type default)) (fill (type none)))'
            )
            pin_line = '        (pin power_in line (at 0 0 90) (length 0) hide'
        else:
            # Connection at (0,0), body above -- arrow pointing up
            body = (
                '        (polyline (pts (xy -0.762 0.762) (xy 0 1.524) (xy 0.762 0.762))\n'
                '          (stroke (width 0) (type default)) (fill (type none)))\n'
                '        (polyline (pts (xy 0 0) (xy 0 1.524))\n'
                '          (stroke (width 0) (type default)) (fill (type none)))'
            )
            pin_line = '        (pin power_in line (at 0 0 270) (length 0) hide'

        return (
            f'    (symbol "{eid}" (power) (pin_names (offset 0)) (in_bom yes) (on_board yes)\n'
            f'      (property "Reference" "#PWR" (at 0 -6.35 0) (effects (font (size 1.27 1.27)) hide))\n'
            f'      (property "Value" "{_esc(net)}" (at 0 3.175 0) (effects (font (size 1.27 1.27))))\n'
            f'      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
            f'      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
            f'      (symbol "{eid}_0_1"\n'
            f'{body}\n'
            f'      )\n'
            f'      (symbol "{eid}_1_1"\n'
            f'{pin_line}\n'
            f'          (name "{_esc(net)}" (effects (font (size 1.27 1.27))))\n'
            f'          (number "1" (effects (font (size 1.27 1.27))))\n'
            f'        )\n'
            f'      )\n'
            f'    )'
        )

    def _pwrflag_lib_symbol(self) -> str:
        """PWR_FLAG: standard KiCad power symbol with hidden power_out pin.

        Does NOT use the ``(power)`` attribute.  With ``(power)``, KiCad would
        use the lib symbol's base Value ("PWR_FLAG") as the global net name for
        ALL instances, overriding per-instance Values ("+3V3", "+5V") and
        collapsing every flag onto the same "PWR_FLAG" net → pin_to_pin.

        Without ``(power)``, each instance connects to its net purely through
        the physical wire drawn to it.  The ``power_out`` pin type still tells
        ERC "there is a power driver on this net."

        The other key fix is in ``_power_lib_symbol()``: each power symbol's
        hidden ``power_in`` pin uses the net name as pin name (e.g. "+3V3",
        "+5V", "GND") instead of the generic "PWR".  Hidden pins with the same
        name create implicit global connections; unique pin names prevent the
        GND / +3V3 / +5V power symbols from being merged onto one "PWR" net.
        """
        return (
            '    (symbol "PWR_FLAG" (pin_names (offset 0)) (in_bom no) (on_board no)\n'
            '      (property "Reference" "#FLG" (at 0 -3.81 0) (effects (font (size 1.27 1.27)) hide))\n'
            '      (property "Value" "PWR_FLAG" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))\n'
            '      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
            '      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
            '      (symbol "PWR_FLAG_0_0"\n'
            '        (polyline (pts (xy 0 0) (xy 0 1.27) (xy -1.016 1.905)'
            ' (xy 0 2.54) (xy 1.016 1.905) (xy 0 1.27))\n'
            '          (stroke (width 0) (type default)) (fill (type none)))\n'
            '      )\n'
            '      (symbol "PWR_FLAG_0_1"\n'
            '        (pin power_out line (at 0 0 90) (length 0) hide\n'
            '          (name "pwr" (effects (font (size 1.27 1.27))))\n'
            '          (number "1" (effects (font (size 1.27 1.27))))\n'
            '        )\n'
            '      )\n'
            '    )'
        )

    def _pwrflag_at(self, net: str, x: float, y: float) -> list[str]:
        """Place a PWR_FLAG instance at (x, y) to drive the given power net.

        The Value property is set to *net* (e.g. "+3V3") so KiCad's netlist
        correctly associates the power_out pin with that specific net.
        """
        flg_ref = f"#FLG{self._flg_counter:03d}"
        self._flg_counter += 1
        uid = self._uid()
        qflg = self._qlib("PWR_FLAG")
        return [
            f'  (symbol (lib_id "{qflg}") (at {_c(x)} {_c(y)} 0) (unit 1) (in_bom no) (on_board no)',
            f'    (uuid "{uid}")',
            f'    (property "Reference" "{_esc(flg_ref)}" (at {_c(x+2)} {_c(y)} 0)',
            f'      (effects (font (size 1.27 1.27)) hide))',
            f'    (property "Value" "{_esc(net)}" (at {_c(x+2)} {_c(y-1)} 0)',
            f'      (effects (font (size 1.27 1.27))))',
            f'    (instances (project "{self._project_name}"',
            f'      (path "/{self._root_uuid}" (reference "{_esc(flg_ref)}") (unit 1))',
            f'    ))',
            f'  )',
        ]

    # ------------------------------------------------------------------
    # Component instance
    # ------------------------------------------------------------------

    def _symbol_inst(
        self,
        comp: dict,
        sym_id: str,
        sdef: SymbolDef,
        ref: str,
        pos: tuple[float, float],
    ) -> str:
        cx, cy = pos
        eid = _esc_id(sym_id)
        mpn = comp.get("mpn", "UNKNOWN")
        uid = self._uid()
        out: list[str] = []
        qeid = self._qlib(eid)
        out.append(f'  (symbol (lib_id "{qeid}") (at {_c(cx)} {_c(cy)} 0) (unit 1) (in_bom yes) (on_board yes)')
        out.append(f'    (uuid "{uid}")')
        out.append(f'    (property "Reference" "{_esc(ref)}" (at {_c(cx+6)} {_c(cy-3)} 0)')
        out.append(f'      (effects (font (size 1.27 1.27)) (justify left)))')
        out.append(f'    (property "Value" "{_esc(mpn)}" (at {_c(cx+6)} {_c(cy-0.5)} 0)')
        out.append(f'      (effects (font (size 1.27 1.27)) (justify left)))')
        out.append(f'    (property "Footprint" "{_esc(sdef.footprint)}" (at {_c(cx)} {_c(cy)} 0)')
        out.append(f'      (effects (font (size 1.27 1.27)) hide))')
        out.append(f'    (property "Datasheet" "" (at {_c(cx)} {_c(cy)} 0)')
        out.append(f'      (effects (font (size 1.27 1.27)) hide))')
        out.append(f'    (property "MPN" "{_esc(mpn)}" (at {_c(cx)} {_c(cy)} 0)')
        out.append(f'      (effects (font (size 1.27 1.27)) hide))')
        # KiCad 6 requires an (instances ...) block for the reference to be
        # visible in the schematic.  Without it KiCad falls back to "U?" / "R?".
        out.append(f'    (instances (project "{self._project_name}"')
        out.append(f'      (path "/{self._root_uuid}" (reference "{_esc(ref)}") (unit 1))')
        out.append(f'    ))')
        out.append(f'  )')
        return "\n".join(out)

    # ------------------------------------------------------------------
    # Pin coordinate helper
    # ------------------------------------------------------------------

    def _pin_abs(
        self,
        sdef: SymbolDef,
        pin: PinDef,
        cx: float,
        cy: float,
    ) -> tuple[float, float]:
        """Absolute schematic position of a pin's connection endpoint."""
        left_pins  = [p for p in sdef.pins if p.side == "left"]
        right_pins = [p for p in sdef.pins if p.side == "right"]
        n_l = len(left_pins)
        n_r = len(right_pins)
        half_h = max(n_l, n_r, 1) * 2.54 / 2 + 1.27

        if pin.side == "left":
            idx   = left_pins.index(pin)
            y_off = half_h - 1.27 - idx * 2.54
            return (cx - (self.BODY_HALF_W + self.PIN_LEN), cy - y_off)
        else:
            idx   = right_pins.index(pin)
            y_off = half_h - 1.27 - idx * 2.54
            return (cx + (self.BODY_HALF_W + self.PIN_LEN), cy - y_off)

    # ------------------------------------------------------------------
    # Bus wire routing  (replaces global_label approach)
    # ------------------------------------------------------------------

    def _draw_bus_wires(
        self,
        components: list[dict],
        sym_defs: dict[str, SymbolDef],
        comp_sym: dict[str, str],
        positions: dict[str, tuple[float, float]],
        bus_signals: list[str],
        pin_to_signal: dict[tuple[str, str], str] | None = None,
        spi_slaves: set[str] | None = None,
        primary_mcu_ids: set[str] | None = None,
        can_slaves: set[str] | None = None,
        uart_slave_to_bus: dict[str, str] | None = None,
        uart_master_to_buses: dict[str, list[str]] | None = None,
        pin_to_hir_net_name: dict[tuple[str, str], str] | None = None,
        pin_to_all_hir_nets: dict[tuple[str, str], list[str]] | None = None,
    ) -> list[str]:
        """Draw bus connections via net labels at each pin endpoint.

        For each bus signal (SDA, SCL, MOSI, ...):
          - MCU right-side pin: short horizontal stub rightward + net label
          - Sensor/peripheral left-side pin: short horizontal stub leftward + net label
          - Sensor/peripheral right-side pin: short stub rightward + net label

        KiCad automatically connects all pins that share the same net label
        name on the same sheet.  No vertical spine is needed, which avoids the
        previous bug where SDA and SCL spines shared the same X coordinate and
        physically overlapped (creating an electrical short).

        pin_to_signal: optional mapping of (comp_id, pin_number_or_name) → signal
        built from HIR nets.  Used to wire pins identified by GPIO number rather
        than signal name (e.g. ESP32 pin "21" → "SDA").
        spi_slaves: set of comp_ids that are SPI slaves.  Used to match SDI/SDO
        pins via _SPI_SLAVE_SIGNAL_ALIASES and to skip I2C labels (SDA/SCL) for
        those components (which are in SPI mode, not I2C mode).
        """
        out: list[str] = []
        _p2s = pin_to_signal or {}
        _p2hir = pin_to_hir_net_name or {}
        _p2all = pin_to_all_hir_nets or {}   # (comp_id, pname) → [all net names]
        _spi_s = spi_slaves or set()
        _can_s = can_slaves or set()
        _uart_s2b = uart_slave_to_bus or {}   # slave_id → bus_name
        _uart_m2b = uart_master_to_buses or {}  # master_id → [bus_names]
        # Detect multi-UART: if any MCU drives more than one UART bus, we need
        # per-bus net labels (uart0_TX, uart1_TX …) to avoid Output-Output ERC
        # errors when multiple UART slaves' output pins share the same "RX" net.
        _is_multi_uart = any(len(buses) > 1 for buses in _uart_m2b.values())

        # Pre-compute set of (comp_id, signal) pairs that are HIR-assigned.
        # Used below to suppress alias-only matches (by_name/by_spi without
        # by_hir) on primary-MCU UART pins in multi-UART designs: the correct
        # GPIO (e.g. IO17) is HIR-assigned, so TXD0 alias must be suppressed
        # to avoid emitting a spurious "TX" net label that dangles.
        _hir_comp_sigs: set[tuple[str, str]] = {
            (cid, sig_val)
            for (cid, _pkey), sig_val in _p2s.items()
        }

        # ref_prefixes that are already wired by the passive wiring loop and
        # must NOT appear here — their pin geometry (R_BODY_HW/C_PLATE_X etc.)
        # differs from the generic IC layout used by _pin_abs, so generating
        # bus wires for them produces stubs at wrong positions (unconnected wire
        # endpoint ERC warnings).
        _PASSIVE_PREFIXES = frozenset({"R", "C", "L", "FB", "SW"})

        for sig in bus_signals:
            for comp in components:
                cid    = comp["id"]
                sym_id = comp_sym[cid]
                sdef   = sym_defs[sym_id]
                # Skip passives — they are wired by the dedicated wiring loop
                # above, which uses the correct passive pin geometry.
                if sdef.ref_prefix in _PASSIVE_PREFIXES:
                    continue
                pos    = positions.get(cid, (50.0, 50.0))
                cx, cy = pos

                for pin in sdef.pins:
                    # Match by pin name (split on "/" for compound names like "IO21/SDA")
                    pin_parts = [p.upper() for p in pin.name.split("/")]
                    by_name = sig in pin_parts
                    # Suffix matching for MCUs with prefixed pin names like
                    # "LPSPI1_MOSI" (i.MX RT) — the signal "MOSI" should
                    # still match if it's a suffix after '_'.
                    # Exclude CAN/FDCAN/FLEXCAN prefixed names when matching
                    # UART signals TX/RX to avoid shorting CAN_TX onto UART TX.
                    _CAN_PREFIXES = ("CAN_", "FDCAN", "FLEXCAN")
                    if not by_name:
                        for part in pin_parts:
                            if part.endswith("_" + sig) or part == sig:
                                # Guard: don't let CAN pins match UART TX/RX
                                if sig in ("TX", "RX") and any(part.upper().startswith(cp) for cp in _CAN_PREFIXES):
                                    continue
                                by_name = True
                                break
                    # Also match via signal aliases on ANY component (not just SPI slaves).
                    # E.g. signal "SCLK" should match a MCU pin named "PA5/SCK" since
                    # SCK is an alias of SCLK.  Also handles UART aliases (TX→DI, RX→RO).
                    if not by_name and sig in _ALL_BUS_SIGNAL_ALIASES:
                        all_names = {sig} | _ALL_BUS_SIGNAL_ALIASES[sig]
                        for alias in all_names:
                            if alias in pin_parts:
                                # UART cross-alias guard: a peripheral pin literally
                                # named "TX" (single part) can match signal "RX" via
                                # the cross-alias set.  But a compound MCU pin like
                                # "PA9/TX" must NOT — the "TX" part there describes
                                # the signal the pin drives, not an alias for the
                                # opposite UART direction.  Allow the cross-alias
                                # exact match only for single-part pin names.
                                if (alias in ("TX", "RX") and alias != sig
                                        and len(pin_parts) > 1):
                                    continue  # skip; try next alias
                                by_name = True
                                break
                            for part in pin_parts:
                                if part.endswith("_" + alias):
                                    # UART cross-alias guard: "TX" appears in the RX
                                    # aliases set (and vice versa) purely for exact
                                    # peripheral-pin matching (e.g. NEO-M8N pin "TX"
                                    # ↔ MCU RX net).  Suffix matching (e.g. "USART1_TX"
                                    # ending "_TX") must NOT fire for the cross alias —
                                    # that would put both TX and RX labels on the same
                                    # MCU UART pin and create a multiple_net_names ERC.
                                    if alias in ("TX", "RX") and alias != sig:
                                        continue
                                    # CAN guard: don't match CAN pins to UART aliases
                                    if sig in ("TX", "RX") and any(part.upper().startswith(cp) for cp in _CAN_PREFIXES):
                                        continue
                                    # JTAG/SWD guard: SWD_CLK must not match
                                    # SCLK via the "_CLK" alias suffix.
                                    _JTAG_SWD_PREFIXES = ("SWD_", "JTAG_", "SWDIO", "SWCLK")
                                    if sig == "SCLK" and any(part.upper().startswith(jp) for jp in _JTAG_SWD_PREFIXES):
                                        continue
                                    by_name = True
                                    break
                            if by_name:
                                break
                    # Suppress I2C labels (SDA/SCL) on SPI slaves — their compound
                    # pin names (e.g. "SDA/SDI") contain both modes, but when the
                    # component is on a SPI bus we only want the SPI signal wired.
                    if by_name and sig in ("SDA", "SCL") and cid in _spi_s:
                        by_name = False
                    # Match by HIR net assignment (pin number or pin name from HIR).
                    # Also try stripping common GPIO prefixes so that KiCad pin
                    # names like "IO17" match HIR pin_name "17", and "GP0/TX"
                    # matches "GP0" (handled by split already).
                    _gpio_prefix_stripped: list[str] = []
                    for _kp in pin.name.split("/"):
                        _gm = re.match(r'^(?:IO|GPIO|GP)(\d+)$', _kp, re.IGNORECASE)
                        if _gm:
                            _gpio_prefix_stripped.append(_gm.group(1))
                    by_hir = (
                        _p2s.get((cid, pin.number)) == sig
                        or _p2s.get((cid, pin.name)) == sig
                        or any(
                            _p2s.get((cid, _gs)) == sig
                            for _gs in _gpio_prefix_stripped
                        )
                        # Also try each slash-split part so "PA9/TX" → "PA9"
                        # matches HIR key ("STM32F103C8T6", "PA9").
                        or any(
                            _p2s.get((cid, _sp)) == sig
                            for _sp in pin.name.split("/")
                        )
                    )
                    # Match via bus slave pin aliases (SDI→MOSI, SDO→MISO, SCK→SCLK, DI→TX, RO→RX)
                    by_spi = (
                        sig in _ALL_BUS_SIGNAL_ALIASES
                        and any(alias in pin_parts for alias in _ALL_BUS_SIGNAL_ALIASES[sig])
                    )
                    # Suppress SPI signal labels (MOSI/MISO/SCLK) on non-MCU, non-SPI-slave
                    # components that match only via alias — prevents BME280's SDI/SDA from
                    # getting a MOSI label at the same coordinate as the SDA label (ERC collision)
                    _SPI_SIGNALS = frozenset({"MOSI", "MISO", "SCLK", "SCK"})
                    _is_mcu = comp.get("role") == "mcu"
                    # "Primary MCU" = first MCU in the design (or the only MCU).
                    # Secondary MCUs (e.g. RP2040 co-processor alongside ESP32) must
                    # be treated as UART peripherals so their TX pin gets an RX label
                    # (cross-connected to the primary MCU's RX) rather than a TX label
                    # (which would create a pin_to_pin ERC: two Output pins on TX net).
                    _is_primary_mcu = (
                        _is_mcu and (primary_mcu_ids is None or cid in primary_mcu_ids)
                    )
                    if sig in _SPI_SIGNALS and not _is_mcu and cid not in _spi_s and not by_hir:
                        by_name = False
                        by_spi = False
                    # Suppress UART signal labels (TX/RX) on CAN bus slave components.
                    # CAN transceivers (e.g. TCAN1042) use TXD/RXD pin names for their
                    # MCU data interface, which match UART aliases in _UART_SLAVE_SIGNAL_ALIASES.
                    # Wiring CAN transceivers via UART labels creates Output-Output ERC errors
                    # because the TCAN1042 RXD pin (Output) would share the TX net label with
                    # the MCU TX pin (also Output).  CAN transceivers are already wired via
                    # the CAN bus analog-net mechanism (CANH/CANL auto-connected by net labels),
                    # so suppress all UART labels for CAN slave components entirely.
                    _UART_SIGNALS = frozenset({"TX", "RX"})
                    if sig in _UART_SIGNALS and cid in _can_s and not by_hir:
                        by_name = False
                        by_spi = False
                    # Suppress UART signal labels (TX/RX) on non-primary-MCU components
                    # when matched only via direct name — prevents MCU-variant alias names
                    # from spuriously wiring peripheral pins that happen to share those names.
                    # Secondary MCUs (co-processors) are also suppressed here so their UART
                    # pins are cross-connected (TX→RX, RX→TX) via the alias mechanism below.
                    # Correct UART peripheral connections come via HIR (by_hir) or alias (by_spi).
                    if sig in _UART_SIGNALS and not _is_primary_mcu and not by_hir:
                        by_name = False
                        # Additionally suppress by_spi when the matched alias is an
                        # MCU-variant or Ethernet RMII-specific pin name (TXD0, TX0, RXD0,
                        # RX0, TXD, RXD) which appear in the UART alias set for MCU variant
                        # naming.  These must not wire secondary MCU pins (e.g. ESP32 TXD0)
                        # or Ethernet PHY pins (LAN8720A TXD0) via UART bus labels.
                        # EXCEPTION: genuine UART peripheral modules like SIM7600 (TXD/RXD)
                        # are NOT MCUs and are NOT Ethernet PHYs — their by_spi must be kept
                        # so the UART crossover wiring works correctly.
                        _RMII_MCU_UART_CONFLICT_ALIASES = frozenset(
                            # Numbered variants (TXD0, RXD0, TX0, RX0) — standard RMII / MCU
                            {"TXD0", "TX0", "RXD0", "RX0"}
                        )
                        _pin_parts_upper = {p.upper() for p in pin.name.split("/")}
                        _ETH_PHY_KWS_BW = ("LAN8720", "LAN8741", "DP838", "KSZ80", "RTL820", "IP101")
                        _MCU_KWS_BW = ("STM32", "ESP32", "RP2040", "NRF52", "SAMD", "LPC", "IMXRT",
                                       "STM8", "ATMEGA", "ATTINY", "PIC", "MSP430", "K20", "K60")
                        _is_eth_phy_bw = any(
                            k in (comp.get("mpn") or "").upper() for k in _ETH_PHY_KWS_BW
                        )
                        _is_mcu_bw = any(
                            k in (comp.get("mpn") or "").upper() for k in _MCU_KWS_BW
                        )
                        # Suppress numbered aliases for Ethernet PHYs and secondary MCUs
                        if by_spi and _pin_parts_upper & _RMII_MCU_UART_CONFLICT_ALIASES and (
                            _is_eth_phy_bw or _is_mcu_bw
                        ):
                            by_spi = False
                        # Also suppress bare TXD/RXD aliases on Ethernet PHYs (alternate naming)
                        _RMII_BARE_ALIASES = frozenset({"TXD", "RXD"})
                        if by_spi and _pin_parts_upper & _RMII_BARE_ALIASES and _is_eth_phy_bw:
                            by_spi = False
                    # Suppress UART cross-alias by_spi on the PRIMARY MCU: the primary
                    # MCU's own TX pin should NOT get an "RX" label (and vice versa).
                    # The cross-alias "TX"↔"RX" in _UART_SLAVE_SIGNAL_ALIASES is only
                    # for peripherals (e.g. RS-485 transceiver DI/RO ↔ TX/RX) and for
                    # secondary MCUs (co-processors) that are cross-connected via UART.
                    # On the primary MCU only non-cross aliases (LPUART1_TX, TXD0 …) apply.
                    #
                    # Extended cross-aliases for MCU compound pin names:
                    #   "RXD" appears in TX aliases (slave peripheral RXD = slave receive
                    #   input, connected to MCU TX), BUT on the primary MCU "PD0/RXD"
                    #   means the MCU's own receive-data pin → must NOT match sig="TX".
                    #   Similarly "TXD" appears in RX aliases (slave transmit output →
                    #   MCU RX), but on the primary MCU "PD1/TXD" = MCU transmit-data
                    #   pin → must NOT match sig="RX".
                    if by_spi and sig in _UART_SIGNALS and _is_primary_mcu:
                        _MCU_CROSS_ALIASES: dict[str, frozenset[str]] = {
                            "TX": frozenset({"RX", "RXD"}),
                            "RX": frozenset({"TX", "TXD"}),
                        }
                        _cross_aliases: frozenset[str] = _MCU_CROSS_ALIASES.get(
                            sig, frozenset({"TX", "RX"}) - {sig}
                        )
                        _non_cross_matches = any(
                            alias in pin_parts
                            for alias in _ALL_BUS_SIGNAL_ALIASES.get(sig, frozenset())
                            if alias not in _cross_aliases
                        )
                        if not _non_cross_matches:
                            by_spi = False
                    # Suppress alias-only UART matches on the primary MCU when a
                    # HIR-assigned pin already exists for this signal on this MCU.
                    # The HIR-correct GPIO (e.g. IO16 matched via GPIO-prefix strip)
                    # provides the correct net label; alias-only matches (RXD0/TXD0
                    # on the same primary MCU) would emit a spurious duplicate label
                    # that either dangles (label_dangling ERC) or collides with a
                    # co-processor's GND/power pin at the same schematic coordinate,
                    # causing a GND↔RX net short that corrupts PWR_FLAG placement.
                    # Applied in BOTH single-UART and multi-UART designs: if the HIR
                    # already assigned a specific GPIO for this signal, alias-only
                    # matches on the primary MCU are always suppressed.
                    if (not by_hir
                            and sig in _UART_SIGNALS and _is_primary_mcu
                            and (cid, sig) in _hir_comp_sigs):
                        by_name = False
                        by_spi = False
                    if not (by_name or by_hir or by_spi):
                        continue
                    px, py = self._pin_abs(sdef, pin, cx, cy)

                    # Determine the actual net label name to use.
                    # For multi-UART designs: use per-bus qualified names from
                    # the HIR net map (uart0_TX, uart0_TX_MCU, uart1_TX …) so
                    # different UART buses get separate KiCad nets.  This prevents
                    # Output-Output ERC errors when multiple UART slaves' output
                    # pins would otherwise share the same "RX" net label.
                    # For single-UART or non-UART signals: use the canonical sig.
                    net_label = sig
                    # For multi-UART: build list of all HIR net names for this
                    # pin.  Most pins have exactly one net; MCU pins shared
                    # across UART buses (e.g. PA2 on uart1_TX_MCU AND
                    # uart2_TX_MCU) have more than one.  We emit one label per
                    # unique net so KiCad sees every net connected at this point
                    # (KiCad merges them with a "multiple_net_names" warning,
                    # which is a warning not an error and is acceptable here).
                    _extra_net_labels: list[str] = []
                    if sig in _UART_SIGNALS and _is_multi_uart:
                        # Collect all HIR net names for this pin by trying
                        # (1) pin number, (2) full pin name, (3) each slash-
                        # separated part of the pin name (STM32 pins store
                        # "PA9" in HIR but KiCad pin.name is "PA9/TX").
                        _all_nets_for_pin: list[str] = []
                        # Build lookup key list: pin number, full name, each
                        # slash-part, and GPIO-prefix-stripped variants (IO17→17,
                        # GPIO5→5) so KiCad IO-prefixed pin names resolve to the
                        # HIR GPIO-number-keyed entries.
                        _lookup_keys = [
                            (cid, pin.number),
                            (cid, pin.name),
                        ] + [(cid, _part) for _part in pin.name.split("/")]
                        for _gs in _gpio_prefix_stripped:
                            _lookup_keys.append((cid, _gs))
                        for _lookup_key in _lookup_keys:
                            _nets = _p2all.get(_lookup_key)
                            if _nets:
                                for _n in _nets:
                                    if _n not in _all_nets_for_pin:
                                        _all_nets_for_pin.append(_n)
                            elif _lookup_key in _p2hir:
                                _n = _p2hir[_lookup_key]
                                if _n not in _all_nets_for_pin:
                                    _all_nets_for_pin.append(_n)
                        if _all_nets_for_pin:
                            net_label = _all_nets_for_pin[0]
                            _extra_net_labels = _all_nets_for_pin[1:]
                        # If no HIR net found for this pin (e.g. matched only
                        # via alias like RO→RX), derive the bus from
                        # uart_slave_to_bus and construct the net name.
                        elif cid in _uart_s2b:
                            _bus = _uart_s2b[cid]
                            net_label = f"{_bus}_{sig}"

                    if pin.side == "right":
                        # Pin connection point is to the RIGHT of the body
                        stub_x = px + self.WIRE_LEN
                        out.append(self._wire_seg(px, py, stub_x, py))
                        out.append(self._net_label_sym(net_label, stub_x, py, 0))
                        for _extra in _extra_net_labels:
                            out.append(self._net_label_sym(_extra, stub_x, py, 0))
                    else:
                        # Pin connection point is to the LEFT of the body
                        stub_x = px - self.WIRE_LEN
                        out.append(self._wire_seg(stub_x, py, px, py))
                        out.append(self._net_label_sym(net_label, stub_x, py, 180))
                        for _extra in _extra_net_labels:
                            out.append(self._net_label_sym(_extra, stub_x, py, 180))

        return out

    def _power_symbol_at(self, net: str, x: float, y: float) -> list[str]:
        """Place a power symbol at (x, y) without an additional wire stub.

        Used when the pin position IS the desired power-symbol position
        (e.g. pull-up resistor pin 2 directly connects to +3V3).
        """
        pwr_ref = f"#PWR{self._pwr_counter:03d}"
        self._pwr_counter += 1
        lib_net = net if net in _KNOWN_POWER_NETS else "+3V3"
        eid = _esc_id(lib_net)
        qeid = self._qlib(eid)
        uid = self._uid()
        return [
            f'  (symbol (lib_id "{qeid}") (at {_c(x)} {_c(y)} 0) (unit 1) (in_bom yes) (on_board yes)',
            f'    (uuid "{uid}")',
            f'    (property "Reference" "{_esc(pwr_ref)}" (at {_c(x+2)} {_c(y)} 0)',
            f'      (effects (font (size 1.27 1.27)) hide))',
            f'    (property "Value" "{_esc(net)}" (at {_c(x+2)} {_c(y-1)} 0)',
            f'      (effects (font (size 1.27 1.27))))',
            f'    (instances (project "{self._project_name}"',
            f'      (path "/{self._root_uuid}" (reference "{_esc(pwr_ref)}") (unit 1))',
            f'    ))',
            f'  )',
        ]

    # ------------------------------------------------------------------
    # Wire / junction / label helpers
    # ------------------------------------------------------------------

    def _wire_seg(self, x1: float, y1: float, x2: float, y2: float) -> str:
        return "\n".join([
            f'  (wire (pts (xy {_c(x1)} {_c(y1)}) (xy {_c(x2)} {_c(y2)}))',
            f'    (stroke (width 0) (type default))',
            f'    (uuid "{self._uid()}")',
            f'  )',
        ])

    def _net_label_sym(self, name: str, x: float, y: float, angle: int = 0) -> str:
        """Within-sheet net label (KiCad `label`, not `global_label`)."""
        return "\n".join([
            f'  (label "{_esc(name)}" (at {_c(x)} {_c(y)} {angle})',
            f'    (effects (font (size 1.27 1.27)))',
            f'    (uuid "{self._uid()}")',
            f'  )',
        ])

    def _junction_sym(self, x: float, y: float) -> str:
        return "\n".join([
            f'  (junction (at {_c(x)} {_c(y)}) (diameter 0) (color 0 0 0 0)',
            f'    (uuid "{self._uid()}")',
            f'  )',
        ])

    def _no_connect(self, x: float, y: float) -> str:
        return "\n".join([
            f'  (no_connect (at {_c(x)} {_c(y)})',
            f'    (uuid "{self._uid()}")',
            f'  )',
        ])

    # ------------------------------------------------------------------
    # Power connections
    # ------------------------------------------------------------------

    def _power_connections(
        self,
        sdef: SymbolDef,
        pos: tuple[float, float],
        skip_config_pins: frozenset[str] = frozenset(),
    ) -> list[str]:
        """Return power symbol instances placed at power-pin endpoints.

        Args:
            skip_config_pins: Pin names (upper-case) to exclude from
                _CONFIG_PIN_NETS lookup.  Used for SPI slaves whose SDO/SDI
                pins are data lines, not I2C address-config pins.
        """
        cx, cy = pos
        out: list[str] = []
        for pin in sdef.pins:
            if pin.type not in ("power_in", "power_out"):
                continue
            pn_up = pin.name.upper()
            net = _net_for_pin(pn_up)
            if net is None:
                continue
            # power_out pins on non-standard nets (e.g. TP4056 BAT → "+VBAT")
            # skip the power symbol here; the no-connect loop places an X on
            # them instead.  Placing a (power) symbol on a power_out pin whose
            # net is "+VBAT" causes a spurious pin_to_pin ERC in KiCad 9.0.7
            # when a PWR_FLAG is simultaneously present on the "+3V3" net.
            # Standard power_out pins (LDO VOUT → "+3V3") still get symbols.
            # "+12V" and "+VBAT" power_out pins are skipped (avoid spurious ERC).
            if pin.type == "power_out" and net not in ("GND", "+3V3", "+5V"):
                continue
            px, py = self._pin_abs(sdef, pin, cx, cy)
            # Route power wire HORIZONTALLY away from component body.
            # Vertical routing would cross adjacent signal pins (e.g. +3V3 on
            # VDD would land exactly on the SDI/SDA pin below it).
            is_left = pin.side == "left"
            wx = px - self.WIRE_LEN if is_left else px + self.WIRE_LEN
            pwr_ref = f"#PWR{self._pwr_counter:03d}"
            self._pwr_counter += 1
            lib_net = net if net in _KNOWN_POWER_NETS else "+3V3"
            eid = _esc_id(lib_net)
            qeid = self._qlib(eid)
            # Horizontal wire from pin -> power symbol
            out.append(self._wire_seg(px, py, wx, py))
            # Power symbol instance at wire endpoint
            uid = self._uid()
            out.append(f'  (symbol (lib_id "{qeid}") (at {_c(wx)} {_c(py)} 0) (unit 1) (in_bom yes) (on_board yes)')
            out.append(f'    (uuid "{uid}")')
            out.append(f'    (property "Reference" "{_esc(pwr_ref)}" (at {_c(wx+2)} {_c(py)} 0)')
            out.append(f'      (effects (font (size 1.27 1.27)) hide))')
            out.append(f'    (property "Value" "{_esc(net)}" (at {_c(wx+2)} {_c(py-1)} 0)')
            out.append(f'      (effects (font (size 1.27 1.27))))')
            out.append(f'    (instances (project "{self._project_name}"')
            out.append(f'      (path "/{self._root_uuid}" (reference "{_esc(pwr_ref)}") (unit 1))')
            out.append(f'    ))')
            out.append(f'  )')

        # Connect well-known configuration input pins (EN, CSB, SDO, ...)
        for pin in sdef.pins:
            if pin.type in ("power_in", "power_out"):
                continue  # already handled above
            pn_up = pin.name.upper()
            # Skip config-pin mapping for SPI slave data pins (SDO/SDI are
            # SPI data lines, not I2C address pins, on SPI-bus components).
            if pn_up in skip_config_pins:
                continue
            net = _CONFIG_PIN_NETS.get(pn_up)
            if net is None:
                continue
            px, py = self._pin_abs(sdef, pin, cx, cy)
            is_left = pin.side == "left"
            wx = px - self.WIRE_LEN if is_left else px + self.WIRE_LEN
            pwr_ref = f"#PWR{self._pwr_counter:03d}"
            self._pwr_counter += 1
            lib_net = net if net in _KNOWN_POWER_NETS else "+3V3"
            eid = _esc_id(lib_net)
            qeid = self._qlib(eid)
            out.append(self._wire_seg(px, py, wx, py))
            uid = self._uid()
            out.append(f'  (symbol (lib_id "{qeid}") (at {_c(wx)} {_c(py)} 0) (unit 1) (in_bom yes) (on_board yes)')
            out.append(f'    (uuid "{uid}")')
            out.append(f'    (property "Reference" "{_esc(pwr_ref)}" (at {_c(wx+2)} {_c(py)} 0)')
            out.append(f'      (effects (font (size 1.27 1.27)) hide))')
            out.append(f'    (property "Value" "{_esc(net)}" (at {_c(wx+2)} {_c(py-1)} 0)')
            out.append(f'      (effects (font (size 1.27 1.27))))')
            out.append(f'    (instances (project "{self._project_name}"')
            out.append(f'      (path "/{self._root_uuid}" (reference "{_esc(pwr_ref)}") (unit 1))')
            out.append(f'    ))')
            out.append(f'  )')
        return out


# ---------------------------------------------------------------------------
# LLM layout planning (B8 boost -- graceful fallback on any error)
# ---------------------------------------------------------------------------

def _llm_plan_layout(
    hir_dict: dict[str, Any],
) -> dict[str, tuple[float, float]] | None:
    """Ask LLM to suggest X/Y positions (mm) for each component.

    Returns a dict {component_id: (x_mm, y_mm)} or None on failure.
    Only positions that match existing component IDs in hir_dict are used.
    """
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

    comp_summary = [
        {"id": c["id"], "role": c.get("role", "other"), "mpn": c.get("mpn", "?")}
        for c in components
    ]

    try:
        resp = gateway.complete_sync(
            task=TaskType.COMPONENT_SUGGEST,
            messages=[{"role": "user", "content": (
                "Plan a KiCad schematic layout for these components (A4 page, mm).\n"
                "Typical zones: MCU x=100 y=110, power/LDO x=100 y=35, "
                "sensors x=195 y=60..200 (55mm apart), passives x=148 y=50..200 (18mm apart).\n\n"
                f"Components:\n{json.dumps(comp_summary, indent=2)}\n\n"
                "Return ONLY a JSON object with component IDs as keys and {\"x\": float, \"y\": float} as values.\n"
                "Include only components where the position differs meaningfully from the typical zone. "
                "Return ONLY valid JSON, nothing else."
            )}],
            temperature=0.2,
            max_tokens=400,
        )
    except Exception:
        return None

    if resp.skipped or not resp.content:
        return None

    # Extract JSON block (possibly multi-line)
    match = re.search(r'\{.*\}', resp.content, re.DOTALL)
    if not match:
        return None

    try:
        raw: dict[str, Any] = json.loads(match.group())
    except Exception:
        return None

    # Build validated position map -- only for known component IDs
    known_ids = {c["id"] for c in components}
    positions: dict[str, tuple[float, float]] = {}
    for comp_id, pos in raw.items():
        if comp_id not in known_ids:
            continue
        if isinstance(pos, dict) and "x" in pos and "y" in pos:
            try:
                positions[comp_id] = (float(pos["x"]), float(pos["y"]))
            except (TypeError, ValueError):
                pass

    return positions if positions else None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _c(v: float) -> str:
    """Format a coordinate value with enough precision to prevent rounding errors.

    Using .2f causes 146.095 (capacitor pin endpoint) to round to 146.09 due to
    IEEE 754 representation (146.0949999...), creating a 0.005mm gap that KiCad
    treats as an unconnected pin.  Four decimal places avoids all such issues.
    """
    return f"{v:.4f}"


def _esc(s: str) -> str:
    """Escape double-quotes for s-expression string values."""
    return s.replace('"', '\\"')


def _esc_id(s: str) -> str:
    """Escape symbol IDs (spaces -> underscore, quotes escaped)."""
    return s.replace('"', '\\"').replace(" ", "_")


def _elec(type_str: str) -> str:
    """Map PinDef.type -> KiCad electrical type keyword."""
    known = {
        "input":          "input",
        "output":         "output",
        "bidirectional":  "bidirectional",
        "tri_state":      "tri_state",
        "power_in":       "power_in",
        "power_out":      "power_out",
        "passive":        "passive",
        "open_collector": "open_collector",
        "no_connect":     "no_connect",
    }
    return known.get(type_str, "bidirectional")


# SPI MISO-side pin names — these are output pins that should be tri_state
# in KiCad because they only drive when CS is asserted.
_SPI_MISO_NAMES = frozenset(["SDO", "MISO", "DOUT", "SOUT", "CIPO", "DO"])


def _net_for_pin(pin_name_upper: str) -> str | None:
    """Return canonical KiCad power net name for a power pin, or None."""
    if any(k in pin_name_upper for k in _GND_KEYWORDS):
        return "GND"
    # 12V rail check BEFORE generic VIN check — "VIN12V" must map to "+12V" not "+5V"
    if any(k in pin_name_upper for k in _12V_KEYWORDS):
        return "+12V"
    if any(k in pin_name_upper for k in _VIN_KEYWORDS):
        return "+5V"
    if any(k in pin_name_upper for k in _3V3_KEYWORDS):
        return "+3V3"
    if pin_name_upper in _VBAT_EXACT:
        return "+VBAT"
    # Motor supply rail (TB6612FNG VM, DRV8833 VMOT, etc.) — use +12V net.
    # Exact-match to avoid false hits on pins like "VSYS", "VMON", etc.
    if pin_name_upper in _MOTOR_SUPPLY_KEYWORDS:
        return "+12V"
    return None
