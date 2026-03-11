# SPDX-License-Identifier: AGPL-3.0-or-later
"""KiCad 6 Schematic Parser — .kicad_sch → HardwareGraph.

Reads a KiCad 6 S-expression schematic and produces a HardwareGraph
ready for HIR compilation via build_hir().

Algorithm
---------
1. Tokenise the S-expression file.
2. Extract lib_symbol pin definitions (connection-point positions
   relative to symbol centre).
3. Extract placed symbol instances (position, rotation, MPN from
   properties).
4. Extract wire segments and net labels.
5. Build net connectivity via union-find on wire-endpoint clusters.
6. Match component pin endpoints (transformed to schematic coordinates)
   to nets.
7. Infer bus topology from canonical net names (SDA/SCL → I2C,
   MOSI/MISO/SCLK → SPI, TX/RX → UART).
8. Return a HardwareGraph.

Limitations
-----------
- Only KiCad 6 / 7 S-expression format (.kicad_sch) is supported.
- Eagle XML (.sch) is NOT supported here; see eagle_parser.py (TODO).
- Power-flag symbols (#PWR, #FLG) and no-connect markers are silently
  ignored — they carry no topology information.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union

from synth_core.hir_bridge.graph import (
    GraphBus,
    GraphComponent,
    GraphNet,
    GraphPin,
    HardwareGraph,
)
from synth_core.knowledge.symbol_map import SYMBOL_MAP


# ---------------------------------------------------------------------------
# S-expression tokeniser + parser
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Return a flat list of S-expression tokens from *text*."""
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\n\r":
            i += 1
        elif c == "(":
            tokens.append("(")
            i += 1
        elif c == ")":
            tokens.append(")")
            i += 1
        elif c == '"':
            # Quoted string — collect until unescaped closing quote
            j = i + 1
            while j < n:
                if text[j] == "\\" and j + 1 < n:
                    j += 2
                elif text[j] == '"':
                    break
                else:
                    j += 1
            tokens.append(text[i : j + 1])
            i = j + 1
        else:
            # Atom (keyword, number, UUID, …)
            j = i
            while j < n and text[j] not in '() \t\n\r"':
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


# A KiCad S-expression node is either a plain string (atom) or a list
# whose first element is the tag (also a string).
SExpr = Union[list, str]


def _parse_sexpr(tokens: list[str], pos: int) -> tuple[SExpr, int]:
    """Recursively parse one S-expression node from *tokens* at *pos*."""
    if tokens[pos] != "(":
        tok = tokens[pos]
        if tok.startswith('"'):
            tok = tok[1:-1].replace('\\"', '"')
        return tok, pos + 1

    result: list[SExpr] = []
    pos += 1  # skip "("
    while pos < len(tokens) and tokens[pos] != ")":
        item, pos = _parse_sexpr(tokens, pos)
        result.append(item)
    return result, pos + 1  # skip ")"


def parse_kicad_sexpr(text: str) -> SExpr:
    """Parse a complete KiCad S-expression string into a nested list."""
    tokens = _tokenize(text)
    if not tokens:
        return []
    root, _ = _parse_sexpr(tokens, 0)
    return root


# ---------------------------------------------------------------------------
# S-expression tree helpers
# ---------------------------------------------------------------------------

def _children(node: list, tag: str) -> list[list]:
    """Return all direct children of *node* whose first element is *tag*."""
    return [c for c in node if isinstance(c, list) and c and c[0] == tag]


def _child(node: list, tag: str) -> list | None:
    """Return the first direct child of *node* whose first element is *tag*."""
    for c in node:
        if isinstance(c, list) and c and c[0] == tag:
            return c
    return None


# ---------------------------------------------------------------------------
# Internal data classes (intermediate representation)
# ---------------------------------------------------------------------------

@dataclass
class _LibPin:
    """A pin defined inside a lib_symbol entry."""
    name: str
    number: str
    pin_type: str   # "bidirectional" | "input" | "output" | "power_in" | …
    at_x: float     # connection endpoint X, relative to symbol origin (mm)
    at_y: float     # connection endpoint Y, relative to symbol origin (mm)
    at_angle: float # pin orientation in lib (degrees)


@dataclass
class _LibSymbol:
    """Aggregated pin layout for one lib_symbol entry."""
    name: str
    pins: list[_LibPin] = field(default_factory=list)


@dataclass
class _Instance:
    """A placed symbol instance on the schematic sheet."""
    lib_id: str
    at_x: float
    at_y: float
    at_angle: float  # CCW rotation in degrees
    mirror_x: bool = False
    properties: dict[str, str] = field(default_factory=dict)

    @property
    def reference(self) -> str:
        return self.properties.get("Reference", "")

    @property
    def mpn(self) -> str:
        return (
            self.properties.get("MPN")
            or self.properties.get("Value")
            or self.lib_id
        )

    @property
    def value(self) -> str:
        return self.properties.get("Value", self.lib_id)


@dataclass
class _Wire:
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class _Label:
    text: str
    x: float
    y: float


# ---------------------------------------------------------------------------
# Union-find for wire connectivity
# ---------------------------------------------------------------------------

class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        if x not in self._parent:
            self._parent[x] = x
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[rb] = ra


# KiCad grid is 50mil = 1.27mm; we snap to this grid for connectivity
_GRID_MM = 1.27


def _snap(x: float, y: float) -> tuple[int, int]:
    """Return integer grid coordinates by snapping to the KiCad grid."""
    return (round(x / _GRID_MM), round(y / _GRID_MM))


# ---------------------------------------------------------------------------
# Main parser class
# ---------------------------------------------------------------------------

class KiCadSchematicParser:
    """Parse a KiCad 6 .kicad_sch file and produce a HardwareGraph."""

    _I2C_SIGNALS: frozenset[str] = frozenset({"SDA", "SCL"})
    _SPI_SIGNALS: frozenset[str] = frozenset({"MOSI", "MISO", "SCLK", "SCK"})
    _UART_SIGNALS: frozenset[str] = frozenset({"TX", "RX", "TXD", "RXD", "UART_TX", "UART_RX"})

    _GND_KW: tuple[str, ...] = ("GND", "VSS", "AGND", "DGND", "PGND")
    _3V3_KW: tuple[str, ...] = ("3V3", "VDD", "VCC", "DVDD", "IOVDD", "VOUT", "VS")
    _5V_KW:  tuple[str, ...] = ("VIN", "5V", "VSUP", "VBUS")

    # MPN substrings → role
    _MCU_KW:    tuple[str, ...] = ("ESP32", "STM32", "RP2040", "NRF52", "ATMEGA", "ATTINY", "PIC", "LPC")
    _SENSOR_KW: tuple[str, ...] = ("BME", "BMP", "AHT", "SHT", "ICM", "MPU", "LSM", "VL53", "INA", "ADXL", "SHTC", "TCS")
    _POWER_KW:  tuple[str, ...] = ("AMS1117", "AP2112", "LM317", "LDO", "REG", "XC6206", "MCP1700")

    def __init__(self) -> None:
        self._lib_symbols: dict[str, _LibSymbol] = {}
        self._instances: list[_Instance] = []
        self._wires: list[_Wire] = []
        self._labels: list[_Label] = []

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def parse(self, path: Path) -> HardwareGraph:
        """Parse a .kicad_sch file from disk and return a HardwareGraph."""
        text = path.read_text(encoding="utf-8", errors="replace")
        return self.parse_text(text, source_file=str(path))

    def parse_text(self, text: str, source_file: str = "<text>") -> HardwareGraph:
        """Parse KiCad 6 S-expression text and return a HardwareGraph."""
        # Reset state so the parser can be reused
        self._lib_symbols.clear()
        self._instances.clear()
        self._wires.clear()
        self._labels.clear()

        root = parse_kicad_sexpr(text)
        if not isinstance(root, list):
            return HardwareGraph(source_file=source_file)

        self._extract(root)
        return self._build_graph(source_file)

    # ------------------------------------------------------------------
    # Phase 1 — extraction
    # ------------------------------------------------------------------

    def _extract(self, root: list) -> None:
        for node in root[1:]:
            if not isinstance(node, list) or not node:
                continue
            tag = node[0]
            if tag == "lib_symbols":
                self._extract_lib_symbols(node)
            elif tag == "symbol":
                self._extract_instance(node)
            elif tag == "wire":
                self._extract_wire(node)
            elif tag in ("label", "net_label", "global_label"):
                self._extract_label(node)

    # --- lib_symbols ---

    def _extract_lib_symbols(self, lib_node: list) -> None:
        for sym_node in lib_node[1:]:
            if not isinstance(sym_node, list) or not sym_node or sym_node[0] != "symbol":
                continue
            name = str(sym_node[1]) if len(sym_node) > 1 else ""
            ls = _LibSymbol(name=name)
            self._collect_lib_pins(sym_node, ls)
            self._lib_symbols[name] = ls

    def _collect_lib_pins(self, sym_node: list, ls: _LibSymbol) -> None:
        """Recursively collect pins from a lib_symbol node (handles sub-units)."""
        for child in sym_node[1:]:
            if not isinstance(child, list) or not child:
                continue
            if child[0] == "symbol":
                self._collect_lib_pins(child, ls)
            elif child[0] == "pin":
                pin = self._parse_lib_pin(child)
                if pin:
                    ls.pins.append(pin)

    def _parse_lib_pin(self, pin_node: list) -> _LibPin | None:
        if len(pin_node) < 3:
            return None
        pin_type = str(pin_node[1]) if len(pin_node) > 1 else "bidirectional"

        at_node = _child(pin_node, "at")
        if not at_node or len(at_node) < 3:
            return None
        try:
            at_x = float(at_node[1])
            at_y = float(at_node[2])
            at_angle = float(at_node[3]) if len(at_node) > 3 else 0.0
        except (ValueError, TypeError):
            return None

        name_node = _child(pin_node, "name")
        pin_name = str(name_node[1]) if (name_node and len(name_node) > 1) else "~"

        num_node = _child(pin_node, "number")
        pin_num = str(num_node[1]) if (num_node and len(num_node) > 1) else ""

        return _LibPin(
            name=pin_name,
            number=pin_num,
            pin_type=pin_type,
            at_x=at_x,
            at_y=at_y,
            at_angle=at_angle,
        )

    # --- symbol instances ---

    def _extract_instance(self, sym_node: list) -> None:
        """Extract a placed symbol instance (must have lib_id, not a lib_symbol def)."""
        lib_id_node = _child(sym_node, "lib_id")
        if lib_id_node is None:
            return  # sub-unit inside a lib_symbol, not an instance

        lib_id = str(lib_id_node[1]) if len(lib_id_node) > 1 else ""
        if not lib_id:
            return

        at_node = _child(sym_node, "at")
        if not at_node:
            return
        try:
            at_x = float(at_node[1])
            at_y = float(at_node[2])
            at_angle = float(at_node[3]) if len(at_node) > 3 else 0.0
        except (ValueError, TypeError):
            return

        mirror_x = _child(sym_node, "mirror") is not None

        props: dict[str, str] = {}
        for prop_node in _children(sym_node, "property"):
            if len(prop_node) >= 3:
                props[str(prop_node[1])] = str(prop_node[2])

        # Skip power symbols (#PWR…) and no-connect flags
        ref = props.get("Reference", "")
        if ref.startswith("#") or lib_id.startswith("#"):
            return

        self._instances.append(_Instance(
            lib_id=lib_id,
            at_x=at_x,
            at_y=at_y,
            at_angle=at_angle,
            mirror_x=mirror_x,
            properties=props,
        ))

    # --- wires ---

    def _extract_wire(self, wire_node: list) -> None:
        pts_node = _child(wire_node, "pts")
        if not pts_node:
            return
        xys = _children(pts_node, "xy")
        if len(xys) < 2:
            return
        try:
            x1, y1 = float(xys[0][1]), float(xys[0][2])
            x2, y2 = float(xys[1][1]), float(xys[1][2])
        except (ValueError, TypeError, IndexError):
            return
        self._wires.append(_Wire(x1, y1, x2, y2))

    # --- labels ---

    def _extract_label(self, label_node: list) -> None:
        if len(label_node) < 2:
            return
        text = str(label_node[1])
        at_node = _child(label_node, "at")
        if not at_node or len(at_node) < 3:
            return
        try:
            x, y = float(at_node[1]), float(at_node[2])
        except (ValueError, TypeError):
            return
        self._labels.append(_Label(text=text, x=x, y=y))

    # ------------------------------------------------------------------
    # Phase 2 — build graph
    # ------------------------------------------------------------------

    def _build_graph(self, source_file: str) -> HardwareGraph:
        graph = HardwareGraph(source_file=source_file)

        # Build coordinate → net_name map
        coord_to_net = self._build_net_map()

        # Build components and collect per-pin net assignments
        comp_pin_to_net: dict[str, dict[str, str]] = {}  # comp_id → {pin_name → net}

        for inst in self._instances:
            comp_id = self._comp_id(inst)
            lib_sym = self._lib_symbols.get(inst.lib_id)

            graph_pins: list[GraphPin] = []
            pin_nets: dict[str, str] = {}

            if lib_sym:
                for lp in lib_sym.pins:
                    if lp.name in ("~", ""):
                        continue
                    abs_x, abs_y = self._transform_pin(lp.at_x, lp.at_y, inst)
                    net = self._net_at(abs_x, abs_y, coord_to_net)
                    graph_pins.append(GraphPin(
                        name=lp.name,
                        number=lp.number,
                        function="",
                        electrical_type=lp.pin_type,
                    ))
                    if net:
                        pin_nets[lp.name] = net

            comp_pin_to_net[comp_id] = pin_nets

            mpn = inst.mpn
            role = self._infer_role(inst.reference, mpn)
            ifaces = self._infer_interfaces(lib_sym.pins if lib_sym else [])

            graph.components.append(GraphComponent(
                id=comp_id,
                name=inst.value or mpn,
                mpn=mpn,
                role=role,
                manufacturer="",
                package="",
                interface_types=ifaces,
                pins=graph_pins,
                properties={"reference": inst.reference},
            ))

        # Build net objects
        net_pin_map = self._invert_pin_nets(comp_pin_to_net)
        for net_name, pin_tuples in net_pin_map.items():
            graph.nets.append(GraphNet(
                name=net_name,
                pins=pin_tuples,
                is_power=self._is_power_net(net_name),
                is_bus=self._is_bus_net(net_name),
            ))

        # Infer buses
        graph.buses = self._infer_buses(graph)

        return graph

    # ------------------------------------------------------------------
    # Net connectivity — union-find
    # ------------------------------------------------------------------

    # Maximum distance (mm) for matching a floating net label to a wire group.
    # Our exporter places labels 2.54 mm above the wire-spine top; real KiCad
    # schematics place labels exactly on wire endpoints (0 mm).  5 mm gives
    # comfortable headroom without risking cross-signal false positives.
    _LABEL_PROXIMITY_MM: float = 5.08

    def _build_net_map(self) -> dict[tuple[int, int], str]:
        """Return a map from snapped coordinate → net name.

        Algorithm
        ---------
        1. Add all wire endpoints to a union-find; union each wire pair.
        2. For each net label, find the nearest known coordinate within
           ``_LABEL_PROXIMITY_MM`` and union the label position with it.
           This handles labels placed slightly off-grid (e.g. our exporter
           places them 2.54 mm above the spine top).
        3. Assign net names from labels to their connected groups.
        4. Unnamed groups get synthetic names (Net-N).
        """
        coord_to_id: dict[tuple[int, int], int] = {}
        id_counter = [0]

        def get_id(x: float, y: float) -> int:
            k = _snap(x, y)
            if k not in coord_to_id:
                coord_to_id[k] = id_counter[0]
                id_counter[0] += 1
            return coord_to_id[k]

        uf = _UnionFind()

        # Step 1: union wire endpoints
        for w in self._wires:
            uf.union(get_id(w.x1, w.y1), get_id(w.x2, w.y2))

        # Step 2: union each label with the nearest coordinate within proximity
        for lbl in self._labels:
            lbl_id = get_id(lbl.x, lbl.y)

            best_cid: int | None = None
            best_dist = self._LABEL_PROXIMITY_MM + 1.0

            for (kx, ky), cid in coord_to_id.items():
                if cid == lbl_id:
                    continue  # skip self
                real_x = kx * _GRID_MM
                real_y = ky * _GRID_MM
                dist = math.hypot(real_x - lbl.x, real_y - lbl.y)
                if dist < best_dist:
                    best_dist = dist
                    best_cid = cid

            if best_cid is not None and best_dist <= self._LABEL_PROXIMITY_MM:
                uf.union(lbl_id, best_cid)

        # Step 3: assign net names; prefer bus signal names over generic ones
        root_to_name: dict[int, str] = {}
        for lbl in self._labels:
            lbl_id = coord_to_id[_snap(lbl.x, lbl.y)]
            root = uf.find(lbl_id)
            existing = root_to_name.get(root)
            if existing is None:
                root_to_name[root] = lbl.text
            elif self._is_bus_signal(lbl.text) and not self._is_bus_signal(existing):
                root_to_name[root] = lbl.text

        # Step 4: auto-names for unlabelled groups
        net_counter = [1]
        for _k, cid in coord_to_id.items():
            root = uf.find(cid)
            if root not in root_to_name:
                root_to_name[root] = f"Net-{net_counter[0]}"
                net_counter[0] += 1

        return {k: root_to_name[uf.find(v)] for k, v in coord_to_id.items()}

    def _net_at(
        self,
        x: float,
        y: float,
        coord_to_net: dict[tuple[int, int], str],
    ) -> str | None:
        """Return the net name at (x, y), or None if unconnected."""
        k = _snap(x, y)
        return coord_to_net.get(k)

    # ------------------------------------------------------------------
    # Pin transform
    # ------------------------------------------------------------------

    def _transform_pin(self, px: float, py: float, inst: _Instance) -> tuple[float, float]:
        """Transform pin position from symbol-local coords to schematic coords.

        KiCad uses CCW rotation internally (Y-down screen → CW appearance).
        In lib_symbol, (at px py) is the pin's connection endpoint in mm
        relative to the symbol origin.
        """
        angle_rad = math.radians(inst.at_angle)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        rx = px * cos_a - py * sin_a
        ry = px * sin_a + py * cos_a
        if inst.mirror_x:
            rx = -rx
        return inst.at_x + rx, inst.at_y + ry

    # ------------------------------------------------------------------
    # Role / interface inference
    # ------------------------------------------------------------------

    def _comp_id(self, inst: _Instance) -> str:
        ref = inst.reference
        if ref:
            return ref
        return f"{inst.lib_id}_{int(inst.at_x)}_{int(inst.at_y)}"

    def _infer_role(self, ref: str, mpn: str) -> str:
        mpn_up = mpn.upper()
        for kw in self._MCU_KW:
            if kw in mpn_up:
                return "mcu"
        for kw in self._SENSOR_KW:
            if kw in mpn_up:
                return "sensor"
        for kw in self._POWER_KW:
            if kw in mpn_up:
                return "power"
        # Fall back to ref-prefix heuristic
        prefix = re.sub(r"\d+", "", ref).upper() if ref else "U"
        if prefix in ("R", "C", "L"):
            return "passive"
        return "other"

    def _infer_interfaces(self, pins: list[_LibPin]) -> list[str]:
        ifaces: set[str] = set()
        for p in pins:
            pn = p.name.upper()
            if "SDA" in pn or "SCL" in pn:
                ifaces.add("I2C")
            if "MOSI" in pn or "MISO" in pn or "SCLK" in pn or "SCK" in pn:
                ifaces.add("SPI")
            if re.search(r"\bTXD?\b|\bRXD?\b", pn):
                ifaces.add("UART")
            if re.search(r"\bGPIO\b|\bIO\d|\bPA\d|\bPB\d|\bPC\d", pn):
                ifaces.add("GPIO")
            if "ADC" in pn or "AIN" in pn:
                ifaces.add("ADC")
            if "PWM" in pn:
                ifaces.add("PWM")
        return sorted(ifaces)

    # ------------------------------------------------------------------
    # Net classification helpers
    # ------------------------------------------------------------------

    def _is_power_net(self, name: str) -> bool:
        nu = name.upper()
        return (
            any(k in nu for k in self._GND_KW)
            or any(k in nu for k in self._3V3_KW)
            or any(k in nu for k in self._5V_KW)
        )

    def _is_bus_net(self, name: str) -> bool:
        return self._is_bus_signal(name)

    def _is_bus_signal(self, name: str) -> bool:
        nu = name.upper()
        return nu in self._I2C_SIGNALS or nu in self._SPI_SIGNALS or nu in self._UART_SIGNALS

    # ------------------------------------------------------------------
    # Net inversion
    # ------------------------------------------------------------------

    @staticmethod
    def _invert_pin_nets(
        comp_pin_to_net: dict[str, dict[str, str]],
    ) -> dict[str, list[tuple[str, str]]]:
        """Build net_name → [(comp_id, pin_name), …] mapping."""
        result: dict[str, list[tuple[str, str]]] = {}
        for comp_id, pin_map in comp_pin_to_net.items():
            for pin_name, net_name in pin_map.items():
                result.setdefault(net_name, []).append((comp_id, pin_name))
        return result

    # ------------------------------------------------------------------
    # Bus inference
    # ------------------------------------------------------------------

    def _infer_buses(self, graph: HardwareGraph) -> list[GraphBus]:
        """Infer buses from net-name patterns on the assembled graph."""
        buses: list[GraphBus] = []
        mcus = [c for c in graph.components if c.role == "mcu"]
        if not mcus:
            return buses
        mcu = mcus[0]

        def _slaves_on_nets(sig_set: set[str]) -> tuple[list[str], list[str]]:
            """Return (matching_net_names, slave_comp_ids) for a bus signal set."""
            matching_nets = [
                n.name for n in graph.nets
                if n.name.upper() in sig_set or any(s in n.name.upper() for s in sig_set)
            ]
            slaves: list[str] = []
            for comp in graph.components:
                if comp.id == mcu.id:
                    continue
                comp_nets = {
                    n.name for n in graph.nets
                    if any(p[0] == comp.id for p in n.pins)
                }
                if comp_nets.intersection(matching_nets):
                    slaves.append(comp.id)
            return matching_nets, slaves

        i2c_nets, i2c_slaves = _slaves_on_nets(self._I2C_SIGNALS)
        spi_nets, spi_slaves = _slaves_on_nets(self._SPI_SIGNALS)
        uart_nets, uart_slaves = _slaves_on_nets(self._UART_SIGNALS)

        if i2c_nets and i2c_slaves:
            buses.append(GraphBus(
                name="I2C0",
                type="I2C",
                master_id=mcu.id,
                slave_ids=i2c_slaves,
                net_names=sorted(set(i2c_nets)),
            ))
        if spi_nets and spi_slaves:
            buses.append(GraphBus(
                name="SPI0",
                type="SPI",
                master_id=mcu.id,
                slave_ids=spi_slaves,
                net_names=sorted(set(spi_nets)),
            ))
        if uart_nets and uart_slaves:
            buses.append(GraphBus(
                name="UART0",
                type="UART",
                master_id=mcu.id,
                slave_ids=uart_slaves,
                net_names=sorted(set(uart_nets)),
            ))
        return buses


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------

def parse_kicad_schematic(path: Path) -> HardwareGraph:
    """Parse *path* (.kicad_sch) and return a HardwareGraph.

    Convenience wrapper around KiCadSchematicParser.
    """
    return KiCadSchematicParser().parse(path)
