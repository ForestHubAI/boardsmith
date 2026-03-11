# SPDX-License-Identifier: AGPL-3.0-or-later
"""WriteSchematicPatchTool — ADD/MODIFY operations on .kicad_sch files.

Safety rails (enforced in this order inside execute()):
  1. Read original file into memory.
  2. Create timestamped .bak BEFORE any write.
  3. Apply all operations in-memory.
  4. Validate S-expression of result using parse_kicad_sexpr().
  5. Write result to original path only if validation passes.
  6. On validation failure: original file is unchanged, .bak still exists.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# UUID helpers
# ---------------------------------------------------------------------------

_UUID_RE = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
)


def _collect_existing_uuids(text: str) -> set[str]:
    """Return all UUID strings found in file text via regex scan."""
    return set(_UUID_RE.findall(text))


def _new_uuid(existing: set[str]) -> str:
    """Generate a UUID not already in existing. Mutates existing to prevent re-use."""
    while True:
        candidate = str(uuid.uuid4())
        if candidate not in existing:
            existing.add(candidate)
            return candidate


# ---------------------------------------------------------------------------
# S-expression helpers
# ---------------------------------------------------------------------------

def _check_paren_balance(text: str) -> None:
    """Raise ValueError if parens are unbalanced (ignoring parens inside quoted strings)."""
    depth = 0
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth < 0:
                    raise ValueError("Unbalanced S-expression: unexpected ')'")
    if depth != 0:
        raise ValueError(f"Unbalanced S-expression: {depth} unclosed '(' paren(s)")


def _validate_sexpr(text: str) -> None:
    """Raise ValueError if text is not a valid kicad_sch S-expression.

    Uses the production parse_kicad_sexpr() parser — handles quoted strings
    with embedded parens correctly. Also enforces strict paren balance which
    the upstream parser may be lenient about.
    """
    if not text or not text.strip():
        raise ValueError("S-expression is empty")
    # Check paren balance first — the upstream parser is lenient about unclosed parens
    _check_paren_balance(text)
    try:
        from synth_core.hir_bridge.kicad_parser import parse_kicad_sexpr
        result = parse_kicad_sexpr(text)
    except Exception as exc:
        raise ValueError(f"S-expression parse failed: {exc}") from exc
    if not isinstance(result, list) or not result:
        raise ValueError("S-expression parsed to empty or non-list — invalid KiCad file")
    if result[0] != "kicad_sch":
        raise ValueError(
            f"Root tag must be 'kicad_sch', got {result[0]!r}. "
            "Not a valid .kicad_sch file."
        )


def _serialize_sexpr(node: Any) -> str:
    """Recursively serialize a nested list tree back to S-expression text.

    Rules:
      - list → '(' + space-joined children + ')'
      - str atom with spaces or special chars → quoted with double-quotes
      - str atom without special chars → bare atom
      - numeric types → str(node)
    """
    if isinstance(node, list):
        return "(" + " ".join(_serialize_sexpr(c) for c in node) + ")"
    if isinstance(node, str):
        # Quote if contains spaces, parens, or double-quote characters
        if re.search(r'[ (){}"\\]', node):
            escaped = node.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return node
    # int, float
    return str(node)


# ---------------------------------------------------------------------------
# Backup helper
# ---------------------------------------------------------------------------

def _create_backup(path: Path) -> Path:
    """Create a byte-identical backup at {path}.{YYYYMMDD-HHMMSS}.bak.

    MUST be called before any write to the original file.
    Raises OSError if the backup cannot be created — caller must not write on error.
    """
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak_path = path.with_suffix(f"{path.suffix}.{ts}.bak")
    bak_path.write_bytes(path.read_bytes())
    return bak_path


# ---------------------------------------------------------------------------
# Operation implementations
# ---------------------------------------------------------------------------

def _build_symbol_instance_sexpr(
    op: dict[str, Any],
    existing_uuids: set[str],
    root_uuid: str,
) -> str:
    """Build the S-expression text for an ADD_SYMBOL placed instance."""
    sym_uuid = _new_uuid(existing_uuids)
    lib_id = op["lib_id"]
    reference = op["reference"]
    value = op["value"]
    footprint = op.get("footprint", "")
    mpn = op.get("mpn", "")
    at_x = op.get("at_x", 100.0)
    at_y = op.get("at_y", 100.0)
    angle = op.get("angle", 0)

    return (
        f'(symbol (lib_id "{lib_id}") (at {at_x} {at_y} {angle}) '
        f'(unit 1) (in_bom yes) (on_board yes)\n'
        f'  (uuid "{sym_uuid}")\n'
        f'  (property "Reference" "{reference}" (at {at_x} {at_y} 0)\n'
        f'    (effects (font (size 1.27 1.27)) (justify left)))\n'
        f'  (property "Value" "{value}" (at {at_x} {at_y} 0)\n'
        f'    (effects (font (size 1.27 1.27)) (justify left)))\n'
        f'  (property "Footprint" "{footprint}" (at {at_x} {at_y} 0)\n'
        f'    (effects (font (size 1.27 1.27)) hide))\n'
        f'  (property "Datasheet" "" (at {at_x} {at_y} 0)\n'
        f'    (effects (font (size 1.27 1.27)) hide))\n'
        f'  (property "MPN" "{mpn}" (at {at_x} {at_y} 0)\n'
        f'    (effects (font (size 1.27 1.27)) hide))\n'
        f'  (instances (project "boardsmith"\n'
        f'    (path "/{root_uuid}" (reference "{reference}") (unit 1))\n'
        f'  ))\n'
        f')'
    )


def _apply_add_symbol(text: str, op: dict[str, Any], existing_uuids: set[str]) -> str:
    """Insert a symbol instance before the closing paren of the kicad_sch root.

    If lib_symbol_sexpr is provided and the lib_id is not already in lib_symbols,
    insert it into the lib_symbols block as well.
    """
    lib_id = op["lib_id"]
    lib_symbol_sexpr = op.get("lib_symbol_sexpr")

    # Step A: Insert lib_symbol if provided and not already in file
    if lib_symbol_sexpr and f'"{lib_id}"' not in text:
        # Find lib_symbols block closing paren
        lib_sym_match = re.search(r'\(lib_symbols', text)
        if lib_sym_match:
            # Find the matching close paren of lib_symbols
            start = lib_sym_match.start()
            depth = 0
            i = start
            while i < len(text):
                if text[i] == '(':
                    depth += 1
                elif text[i] == ')':
                    depth -= 1
                    if depth == 0:
                        # Insert lib_symbol before the closing paren of lib_symbols
                        text = text[:i] + "\n  " + lib_symbol_sexpr + "\n" + text[i:]
                        break
                i += 1

    # Step B: Extract root UUID from first path element for instances block
    root_uuid_match = re.search(r'\(path\s+"\/([^"]+)"', text)
    root_uuid = root_uuid_match.group(1) if root_uuid_match else _new_uuid(existing_uuids)

    # Step C: Build and insert placed symbol instance before the last ")" of kicad_sch
    instance_sexpr = _build_symbol_instance_sexpr(op, existing_uuids, root_uuid)
    # Insert before the final closing paren of the root kicad_sch expression
    last_paren = text.rfind(")")
    if last_paren == -1:
        raise ValueError("Malformed kicad_sch: no closing paren found")
    text = text[:last_paren] + "\n" + instance_sexpr + "\n" + text[last_paren:]
    return text


def _apply_modify_property(text: str, op: dict[str, Any]) -> str:
    """Modify a property value on a symbol identified by UUID.

    Uses S-expression parse + tree walk + serialize to avoid regex fragility.
    Raises ValueError if symbol UUID not found or property not found on that symbol.
    """
    from synth_core.hir_bridge.kicad_parser import parse_kicad_sexpr

    symbol_uuid = op["symbol_uuid"]
    property_name = op["property_name"]
    new_value = op["new_value"]

    tree = parse_kicad_sexpr(text)

    def _find_and_modify(node: Any) -> bool:
        """Walk tree in-place. Returns True if modification was made."""
        if not isinstance(node, list):
            return False
        # Look for a symbol node containing the target UUID
        if node and node[0] == "symbol":
            # Check if this symbol has a uuid child matching target
            for child in node:
                if isinstance(child, list) and child and child[0] == "uuid":
                    if len(child) > 1 and child[1] == symbol_uuid:
                        # Found target symbol — find property node
                        for prop_child in node:
                            if (isinstance(prop_child, list)
                                    and prop_child
                                    and prop_child[0] == "property"
                                    and len(prop_child) > 1
                                    and prop_child[1] == property_name):
                                # prop_child[2] is the value atom — replace it
                                prop_child[2] = new_value
                                return True
                        raise ValueError(
                            f"Property '{property_name}' not found on symbol {symbol_uuid}"
                        )
        # Recurse
        for child in node:
            if _find_and_modify(child):
                return True
        return False

    if not _find_and_modify(tree):
        raise ValueError(f"Symbol with UUID '{symbol_uuid}' not found in schematic")

    return _serialize_sexpr(tree)


# ---------------------------------------------------------------------------
# Tool class
# ---------------------------------------------------------------------------

class WriteSchematicPatchTool:
    """LLM-callable tool to ADD or MODIFY elements in a .kicad_sch file.

    All imports are lazy — this module is safe to import with BOARDSMITH_NO_LLM=1.
    """

    name = "write_schematic_patch"
    description = (
        "Execute ADD_SYMBOL or MODIFY_PROPERTY operations on a .kicad_sch file. "
        "Validates S-expression syntax before writing. "
        "Creates a timestamped .bak backup before the first write. "
        "Returns a summary of applied operations and the backup file path."
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the .kicad_sch file.",
            },
            "operations": {
                "type": "array",
                "description": (
                    "List of operations. Each has 'op' field: "
                    "'ADD_SYMBOL' or 'MODIFY_PROPERTY'."
                ),
                "items": {"type": "object"},
            },
        },
        "required": ["path", "operations"],
    }

    async def execute(self, input: Any, context: Any) -> Any:
        from tools.base import ToolResult

        path = Path(input["path"])
        operations = input.get("operations", [])

        if not path.exists():
            return ToolResult(
                success=False, data={}, source="write_schematic_patch",
                confidence=0.0, error=f"File not found: {path}",
            )

        # Step 1: Read original into memory
        original_text = path.read_text(encoding="utf-8")

        # Step 2: Validate original before doing anything
        try:
            _validate_sexpr(original_text)
        except ValueError as exc:
            return ToolResult(
                success=False, data={}, source="write_schematic_patch",
                confidence=0.0, error=f"Original file is not valid kicad_sch: {exc}",
            )

        # Step 3: Create backup (BEFORE any write — this is the safety invariant)
        try:
            bak_path = _create_backup(path)
        except OSError as exc:
            return ToolResult(
                success=False, data={}, source="write_schematic_patch",
                confidence=0.0, error=f"Backup creation failed: {exc} — write aborted",
            )

        # Step 4: Collect existing UUIDs once (mutated set prevents same-session collisions)
        existing_uuids = _collect_existing_uuids(original_text)

        # Step 5: Apply operations in-memory
        modified_text = original_text
        applied: list[str] = []
        errors: list[str] = []

        for op in operations:
            op_type = op.get("op", "")
            try:
                if op_type == "ADD_SYMBOL":
                    modified_text = _apply_add_symbol(modified_text, op, existing_uuids)
                    applied.append(f"ADD_SYMBOL {op.get('lib_id', '?')} ref={op.get('reference', '?')}")
                elif op_type == "MODIFY_PROPERTY":
                    modified_text = _apply_modify_property(modified_text, op)
                    applied.append(
                        f"MODIFY_PROPERTY uuid={op.get('symbol_uuid', '?')[:8]}... "
                        f"{op.get('property_name')}={op.get('new_value')}"
                    )
                else:
                    errors.append(f"Unknown op: {op_type!r}")
            except (ValueError, KeyError) as exc:
                errors.append(f"{op_type} failed: {exc}")

        if not applied:
            return ToolResult(
                success=False,
                data={"applied": [], "errors": errors, "backup": str(bak_path)},
                source="write_schematic_patch",
                confidence=0.0,
                error=f"No operations applied. Errors: {errors}",
            )

        # Step 6: Validate result S-expression BEFORE writing
        try:
            _validate_sexpr(modified_text)
        except ValueError as exc:
            # Original file is unchanged — backup exists but we didn't overwrite
            return ToolResult(
                success=False,
                data={"applied": applied, "errors": [str(exc)], "backup": str(bak_path)},
                source="write_schematic_patch",
                confidence=0.0,
                error=f"Result S-expression invalid — original file unchanged: {exc}",
            )

        # Step 7: Write — only if validation passed
        path.write_text(modified_text, encoding="utf-8")

        return ToolResult(
            success=True,
            data={
                "applied": applied,
                "errors": errors,
                "backup": str(bak_path),
                "ops_count": len(applied),
            },
            source="write_schematic_patch",
            confidence=1.0,
            metadata={"path": str(path)},
        )
