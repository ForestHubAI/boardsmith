# SPDX-License-Identifier: AGPL-3.0-or-later
"""KiCad .kicad_sch parser — S-Expression based schematic format.

KiCad 6+ uses S-Expression (.kicad_sch) format.
This parser extracts components, pins, nets, and connections.
"""

from __future__ import annotations

from pathlib import Path

from boardsmith_fw.models.hardware_graph import Component, Net, NetPin, Pin, PinDirection


class ParseResult:
    def __init__(self, components: list[Component], nets: list[Net], warnings: list[str]):
        self.components = components
        self.nets = nets
        self.warnings = warnings


def parse_kicad_schematic(path: Path) -> ParseResult:
    """Parse a KiCad 6+ .kicad_sch file."""
    if not path.exists():
        return ParseResult([], [], [f"File not found: {path}"])

    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        return ParseResult([], [], [f"Failed to read file: {e}"])

    try:
        tree = _parse_sexpr(text)
    except Exception as e:
        return ParseResult([], [], [f"Failed to parse S-Expression: {e}"])

    if not tree or (isinstance(tree, list) and tree and tree[0] != "kicad_sch"):
        return ParseResult([], [], ["Not a valid KiCad schematic file"])

    warnings: list[str] = []
    components = _extract_symbols(tree, warnings)
    nets = _extract_nets(tree, components, warnings)

    return ParseResult(components, nets, warnings)


# ---------------------------------------------------------------------------
# S-Expression tokenizer + parser
# ---------------------------------------------------------------------------

def _parse_sexpr(text: str) -> list:
    """Parse S-Expression text into nested Python lists."""
    tokens = _tokenize(text)
    if not tokens:
        return []
    result, _ = _parse_tokens(tokens, 0)
    return result


def _tokenize(text: str) -> list[str]:
    """Tokenize S-Expression text into a flat list of tokens."""
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in (" ", "\t", "\n", "\r"):
            i += 1
        elif c == "(":
            tokens.append("(")
            i += 1
        elif c == ")":
            tokens.append(")")
            i += 1
        elif c == '"':
            # Quoted string
            j = i + 1
            while j < n and text[j] != '"':
                if text[j] == "\\":
                    j += 1
                j += 1
            tokens.append(text[i + 1:j])
            i = j + 1
        else:
            # Unquoted atom
            j = i
            while j < n and text[j] not in (" ", "\t", "\n", "\r", "(", ")"):
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def _parse_tokens(tokens: list[str], pos: int) -> tuple[list, int]:
    """Recursively parse tokens from position. Returns (parsed_list, new_pos)."""
    if tokens[pos] != "(":
        return [tokens[pos]], pos + 1

    pos += 1  # skip "("
    result: list = []
    while pos < len(tokens) and tokens[pos] != ")":
        if tokens[pos] == "(":
            child, pos = _parse_tokens(tokens, pos)
            result.append(child)
        else:
            result.append(tokens[pos])
            pos += 1
    pos += 1  # skip ")"
    return result, pos


# ---------------------------------------------------------------------------
# Component extraction
# ---------------------------------------------------------------------------

def _find_all(tree: list, tag: str) -> list[list]:
    """Find all sub-lists starting with the given tag."""
    results: list[list] = []
    if isinstance(tree, list):
        if tree and tree[0] == tag:
            results.append(tree)
        for item in tree:
            if isinstance(item, list):
                results.extend(_find_all(item, tag))
    return results


def _find_first(tree: list, tag: str) -> list | None:
    """Find the first sub-list starting with the given tag."""
    for item in tree:
        if isinstance(item, list) and item and item[0] == tag:
            return item
    return None


def _get_property(symbol: list, prop_name: str) -> str:
    """Get a named property value from a KiCad symbol."""
    for item in symbol:
        if isinstance(item, list) and item and item[0] == "property":
            if len(item) >= 3 and item[1] == prop_name:
                return item[2]
    return ""


def _extract_symbols(tree: list, warnings: list[str]) -> list[Component]:
    """Extract component symbols from the schematic."""
    components: list[Component] = []
    symbols = _find_all(tree, "symbol")

    # Filter to top-level placed symbols (not lib_symbols definitions)
    placed: list[list] = []
    for sym in symbols:
        # Placed symbols have a "lib_id" property
        lib_id = _find_first(sym, "lib_id")
        if lib_id:
            placed.append(sym)

    for sym in placed:
        try:
            comp = _parse_symbol(sym, tree, warnings)
            if comp:
                components.append(comp)
        except Exception as e:
            warnings.append(f"Failed to parse symbol: {e}")

    return components


def _parse_symbol(sym: list, tree: list, warnings: list[str]) -> Component | None:
    """Parse a single placed symbol into a Component."""
    # Get lib_id
    lib_id_node = _find_first(sym, "lib_id")
    lib_id = lib_id_node[1] if lib_id_node and len(lib_id_node) > 1 else ""

    # Get properties
    reference = _get_property(sym, "Reference")
    value = _get_property(sym, "Value")
    footprint = _get_property(sym, "Footprint")
    mpn = _get_property(sym, "MPN") or _get_property(sym, "Manufacturer_Part_Number")
    manufacturer = _get_property(sym, "Manufacturer")

    if not reference:
        return None

    # Skip power symbols
    if reference.startswith("#") or reference.startswith("PWR"):
        return None

    # Extract pins from lib_symbols
    pins = _extract_pins_from_lib(lib_id, tree)

    comp_id = reference  # Use reference designator as ID (e.g., U1, R1)
    return Component(
        id=comp_id,
        name=reference,
        value=value,
        package=footprint.split(":")[-1] if ":" in footprint else footprint,
        library=lib_id.split(":")[0] if ":" in lib_id else "",
        deviceset=lib_id,
        manufacturer=manufacturer,
        mpn=mpn,
        pins=pins,
    )


def _extract_pins_from_lib(lib_id: str, tree: list) -> list[Pin]:
    """Extract pin definitions from the lib_symbols section."""
    pins: list[Pin] = []

    lib_symbols = _find_first(tree, "lib_symbols")
    if not lib_symbols:
        return pins

    # Find matching library symbol
    for item in lib_symbols:
        if not isinstance(item, list) or not item or item[0] != "symbol":
            continue
        if len(item) < 2:
            continue
        sym_name = item[1]
        # KiCad lib symbols use the lib_id as name
        if sym_name != lib_id:
            continue

        # Recurse into sub-symbols (e.g., "BME280_0_1", "BME280_1_1")
        all_pins = _find_all(item, "pin")
        for pin_node in all_pins:
            pin = _parse_pin(pin_node)
            if pin:
                pins.append(pin)
        break

    return pins


_KICAD_DIR_MAP: dict[str, PinDirection] = {
    "input": PinDirection.INPUT,
    "output": PinDirection.OUTPUT,
    "bidirectional": PinDirection.BIDIRECTIONAL,
    "power_in": PinDirection.POWER,
    "power_out": PinDirection.POWER,
    "passive": PinDirection.PASSIVE,
    "tri_state": PinDirection.BIDIRECTIONAL,
    "unspecified": PinDirection.UNKNOWN,
    "open_collector": PinDirection.OUTPUT,
    "open_emitter": PinDirection.OUTPUT,
    "unconnected": PinDirection.UNKNOWN,
    "no_connect": PinDirection.UNKNOWN,
    "free": PinDirection.UNKNOWN,
}


def _parse_pin(pin_node: list) -> Pin | None:
    """Parse a KiCad pin node into a Pin."""
    if not pin_node or pin_node[0] != "pin":
        return None

    # (pin <electrical_type> <graphical_style> (at ...) (length ...) (name "...") (number "..."))
    electrical_type = pin_node[1] if len(pin_node) > 1 else "unspecified"
    direction = _KICAD_DIR_MAP.get(electrical_type, PinDirection.UNKNOWN)

    name_node = _find_first(pin_node, "name")
    number_node = _find_first(pin_node, "number")

    name = name_node[1] if name_node and len(name_node) > 1 else ""
    number = number_node[1] if number_node and len(number_node) > 1 else ""

    if not name and not number:
        return None

    return Pin(
        name=name or number,
        number=number or "?",
        direction=direction,
        electrical_type=electrical_type,
    )


# ---------------------------------------------------------------------------
# Net extraction
# ---------------------------------------------------------------------------

def _extract_nets(tree: list, components: list[Component], warnings: list[str]) -> list[Net]:
    """Extract nets from wire connections and labels."""
    nets: dict[str, Net] = {}
    comp_map = {c.id: c for c in components}

    # Find all net labels
    labels = _find_all(tree, "label")
    global_labels = _find_all(tree, "global_label")

    # KiCad uses hierarchical connections.
    # For a simplified approach, we extract net names from labels
    # and connect symbols that share pin connections.

    # Extract net labels and their positions
    label_positions: list[tuple[str, float, float]] = []
    for lbl in labels + global_labels:
        name = lbl[1] if len(lbl) > 1 and isinstance(lbl[1], str) else ""
        if not name:
            continue
        at_node = _find_first(lbl, "at")
        if at_node and len(at_node) >= 3:
            try:
                x, y = float(at_node[1]), float(at_node[2])
                label_positions.append((name, x, y))
                if name not in nets:
                    is_power = name.upper() in ("VCC", "VDD", "GND", "3V3", "5V", "+3V3", "+5V", "3.3V")
                    nets[name] = Net(name=name, is_power=is_power)
            except (ValueError, IndexError):
                pass

    # Extract symbol pin positions and match to labels via wire connectivity
    for sym in _find_all(tree, "symbol"):
        lib_id = _find_first(sym, "lib_id")
        if not lib_id:
            continue
        ref = _get_property(sym, "Reference")
        if not ref or ref.startswith("#"):
            continue

        # Get symbol position
        at_node = _find_first(sym, "at")
        if not at_node or len(at_node) < 3:
            continue

        # Extract pin connections from the symbol
        comp = comp_map.get(ref)
        if not comp:
            continue

        for pin in comp.pins:
            # Match pins to nets by checking if any net label connects
            for net_name, lx, ly in label_positions:
                if pin.name.upper() in net_name.upper() or net_name.upper() in pin.name.upper():
                    if net_name in nets:
                        # Check not already connected
                        already = any(
                            p.component_id == ref and p.pin_name == pin.name for p in nets[net_name].pins
                        )
                        if not already:
                            nets[net_name].pins.append(NetPin(component_id=ref, pin_name=pin.name))
                            pin.net = net_name

    # Also try to infer connections from matching pin/net names
    _infer_connections_from_names(nets, components)

    return list(nets.values())


def _infer_connections_from_names(nets: dict[str, Net], components: list[Component]) -> None:
    """Infer net connections when pin names match net names (common pattern)."""
    for comp in components:
        for pin in comp.pins:
            pin_upper = pin.name.upper()
            # Check each net name
            for net_name, net in nets.items():
                net_upper = net_name.upper()
                # Direct match or signal suffix match
                if pin_upper == net_upper or pin_upper.endswith(f"/{net_upper}"):
                    already = any(
                        p.component_id == comp.id and p.pin_name == pin.name for p in net.pins
                    )
                    if not already:
                        net.pins.append(NetPin(component_id=comp.id, pin_name=pin.name))
                        if not pin.net:
                            pin.net = net_name
