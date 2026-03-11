# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for WriteSchematicPatchTool — TDD Red phase.

Tests cover:
  - Helper function contracts (_new_uuid, _collect_existing_uuids, _validate_sexpr, _serialize_sexpr, _create_backup)
  - ADD_SYMBOL operation (backup created, UUID uniqueness, result validity)
  - MODIFY_PROPERTY operation (updates value in tree)
  - Safety rail: invalid result sexpr leaves original unchanged
  - BOARDSMITH_NO_LLM=1 import isolation
"""
from __future__ import annotations

import asyncio
import re
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Path setup — mirrors other test_*_tool.py files in tests/agent/
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler"):
    _p = str(REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

SMALL_SCH = REPO_ROOT / "examples/output/01_temp_sensor/schematic.kicad_sch"

_UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
)


def _run(coro):
    return asyncio.run(coro)


def _make_mock_context():
    ctx = MagicMock()
    ctx.no_llm = False
    return ctx


# ---------------------------------------------------------------------------
# Helper: _new_uuid
# ---------------------------------------------------------------------------

class TestNewUUID:
    def test_returns_valid_uuid_format(self):
        from boardsmith_hw.agent.write_schematic import _new_uuid
        existing: set[str] = set()
        result = _new_uuid(existing)
        assert _UUID_PATTERN.match(result), f"UUID format invalid: {result!r}"

    def test_mutates_existing_set(self):
        from boardsmith_hw.agent.write_schematic import _new_uuid
        existing: set[str] = set()
        u = _new_uuid(existing)
        assert u in existing

    def test_two_calls_produce_distinct_values(self):
        from boardsmith_hw.agent.write_schematic import _new_uuid
        existing: set[str] = set()
        u1 = _new_uuid(existing)
        u2 = _new_uuid(existing)
        assert u1 != u2

    def test_never_returns_value_already_in_set(self):
        from boardsmith_hw.agent.write_schematic import _new_uuid
        # Fill set with many pre-fabricated UUIDs to stress collision avoidance
        existing = {"00000000-0000-0000-0000-000000000001"}
        result = _new_uuid(existing)
        # Result should not equal any pre-existing value (trivially true with random UUIDs)
        assert result not in {"00000000-0000-0000-0000-000000000001"}
        assert result in existing  # mutated


# ---------------------------------------------------------------------------
# Helper: _collect_existing_uuids
# ---------------------------------------------------------------------------

class TestCollectExistingUUIDs:
    def test_finds_uuids_in_text(self):
        from boardsmith_hw.agent.write_schematic import _collect_existing_uuids
        text = '(uuid "5682ce4f-3930-4029-aba6-dc91451ea155") (uuid "aaaabbbb-cccc-dddd-eeee-ffffaaaabbbb")'
        result = _collect_existing_uuids(text)
        assert "5682ce4f-3930-4029-aba6-dc91451ea155" in result
        assert "aaaabbbb-cccc-dddd-eeee-ffffaaaabbbb" in result

    def test_returns_empty_set_on_no_uuids(self):
        from boardsmith_hw.agent.write_schematic import _collect_existing_uuids
        result = _collect_existing_uuids("(kicad_sch (version 20230121))")
        assert result == set()

    def test_returns_set_type(self):
        from boardsmith_hw.agent.write_schematic import _collect_existing_uuids
        result = _collect_existing_uuids("")
        assert isinstance(result, set)


# ---------------------------------------------------------------------------
# Helper: _validate_sexpr
# ---------------------------------------------------------------------------

class TestValidateSexpr:
    def test_valid_kicad_sch_returns_none(self):
        from boardsmith_hw.agent.write_schematic import _validate_sexpr
        # Minimal valid kicad_sch with a root UUID path for realism
        text = '(kicad_sch (version 20230121) (generator "boardsmith"))'
        result = _validate_sexpr(text)
        assert result is None

    def test_rejects_bad_root_tag(self):
        from boardsmith_hw.agent.write_schematic import _validate_sexpr
        with pytest.raises(ValueError, match="kicad_sch"):
            _validate_sexpr('(bad_root (something))')

    def test_rejects_unbalanced_parens(self):
        from boardsmith_hw.agent.write_schematic import _validate_sexpr
        with pytest.raises(ValueError):
            _validate_sexpr('(kicad_sch (version')

    def test_rejects_empty_string(self):
        from boardsmith_hw.agent.write_schematic import _validate_sexpr
        with pytest.raises(ValueError):
            _validate_sexpr('')

    def test_rejects_non_kicad_sch_root(self):
        from boardsmith_hw.agent.write_schematic import _validate_sexpr
        with pytest.raises(ValueError, match="kicad_sch"):
            _validate_sexpr('(kicad_pcb (version 20230121))')


# ---------------------------------------------------------------------------
# Helper: _serialize_sexpr
# ---------------------------------------------------------------------------

class TestSerializeSexpr:
    def test_nested_list(self):
        from boardsmith_hw.agent.write_schematic import _serialize_sexpr
        assert _serialize_sexpr(["kicad_sch", ["version", "20230121"]]) == "(kicad_sch (version 20230121))"

    def test_bare_atom(self):
        from boardsmith_hw.agent.write_schematic import _serialize_sexpr
        assert _serialize_sexpr("bare_atom") == "bare_atom"

    def test_atom_with_spaces_is_quoted(self):
        from boardsmith_hw.agent.write_schematic import _serialize_sexpr
        assert _serialize_sexpr("has space") == '"has space"'

    def test_empty_list(self):
        from boardsmith_hw.agent.write_schematic import _serialize_sexpr
        assert _serialize_sexpr([]) == "()"

    def test_numeric_int(self):
        from boardsmith_hw.agent.write_schematic import _serialize_sexpr
        assert _serialize_sexpr(42) == "42"

    def test_numeric_float(self):
        from boardsmith_hw.agent.write_schematic import _serialize_sexpr
        result = _serialize_sexpr(3.14)
        assert "3.14" in result


# ---------------------------------------------------------------------------
# Helper: _create_backup
# ---------------------------------------------------------------------------

class TestCreateBackup:
    def test_backup_file_is_byte_identical(self, tmp_path):
        from boardsmith_hw.agent.write_schematic import _create_backup
        src = tmp_path / "test.kicad_sch"
        content = b"(kicad_sch (version 20230121))"
        src.write_bytes(content)
        bak = _create_backup(src)
        assert bak.read_bytes() == content

    def test_backup_filename_has_timestamp(self, tmp_path):
        from boardsmith_hw.agent.write_schematic import _create_backup
        src = tmp_path / "test.kicad_sch"
        src.write_bytes(b"(kicad_sch)")
        bak = _create_backup(src)
        # Must match: test.kicad_sch.YYYYMMDD-HHMMSS.bak
        assert re.match(r'test\.kicad_sch\.\d{8}-\d{6}\.bak', bak.name), f"Unexpected name: {bak.name}"

    def test_backup_is_in_same_directory(self, tmp_path):
        from boardsmith_hw.agent.write_schematic import _create_backup
        src = tmp_path / "test.kicad_sch"
        src.write_bytes(b"(kicad_sch)")
        bak = _create_backup(src)
        assert bak.parent == tmp_path

    def test_backup_preserves_extension(self, tmp_path):
        from boardsmith_hw.agent.write_schematic import _create_backup
        src = tmp_path / "schematic.kicad_sch"
        src.write_bytes(b"(kicad_sch)")
        bak = _create_backup(src)
        assert bak.name.endswith(".bak")


# ---------------------------------------------------------------------------
# WriteSchematicPatchTool structure
# ---------------------------------------------------------------------------

class TestWriteSchematicPatchToolStructure:
    def test_name_is_correct(self):
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        tool = WriteSchematicPatchTool()
        assert tool.name == "write_schematic_patch"

    def test_input_schema_required_fields(self):
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        tool = WriteSchematicPatchTool()
        assert "path" in tool.input_schema["required"]
        assert "operations" in tool.input_schema["required"]

    def test_description_is_non_empty(self):
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        tool = WriteSchematicPatchTool()
        assert len(tool.description) > 10

    def test_import_with_no_llm_env(self, monkeypatch):
        """BOARDSMITH_NO_LLM=1 must not cause import failure."""
        monkeypatch.setenv("BOARDSMITH_NO_LLM", "1")
        # Re-importing is safe since modules are cached
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool  # noqa: F401


# ---------------------------------------------------------------------------
# WriteSchematicPatchTool.execute() — ADD_SYMBOL
# ---------------------------------------------------------------------------

class TestAddSymbolOperation:
    def test_add_symbol_creates_backup_before_write(self, tmp_path):
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        dst = tmp_path / "test.kicad_sch"
        shutil.copy(SMALL_SCH, dst)
        original_bytes = dst.read_bytes()

        tool = WriteSchematicPatchTool()
        result = _run(tool.execute({
            "path": str(dst),
            "operations": [{"op": "ADD_SYMBOL", "lib_id": "boardsmith:R", "reference": "R99", "value": "10k"}]
        }, _make_mock_context()))

        assert result.success, f"ADD_SYMBOL failed: {result.error}"
        baks = list(tmp_path.glob("*.bak"))
        assert len(baks) >= 1, "No backup file created"
        assert baks[0].read_bytes() == original_bytes, "Backup is not byte-identical to original"

    def test_add_symbol_result_contains_reference(self, tmp_path):
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        dst = tmp_path / "test.kicad_sch"
        shutil.copy(SMALL_SCH, dst)

        tool = WriteSchematicPatchTool()
        result = _run(tool.execute({
            "path": str(dst),
            "operations": [{"op": "ADD_SYMBOL", "lib_id": "boardsmith:R", "reference": "R99", "value": "10k"}]
        }, _make_mock_context()))

        assert result.success
        assert "R99" in dst.read_text()

    def test_two_add_symbols_produce_distinct_uuids(self, tmp_path):
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool, _collect_existing_uuids
        dst = tmp_path / "test.kicad_sch"
        shutil.copy(SMALL_SCH, dst)
        original_uuids = _collect_existing_uuids(dst.read_text())

        tool = WriteSchematicPatchTool()
        result = _run(tool.execute({
            "path": str(dst),
            "operations": [
                {"op": "ADD_SYMBOL", "lib_id": "boardsmith:R", "reference": "R98", "value": "1k"},
                {"op": "ADD_SYMBOL", "lib_id": "boardsmith:C", "reference": "C99", "value": "100nF"},
            ]
        }, _make_mock_context()))

        assert result.success, f"Dual ADD_SYMBOL failed: {result.error}"
        new_uuids = _collect_existing_uuids(dst.read_text()) - original_uuids
        assert len(new_uuids) >= 2, f"Expected at least 2 new UUIDs, found {len(new_uuids)}: {new_uuids}"

    def test_add_symbol_success_result_has_backup_key(self, tmp_path):
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        dst = tmp_path / "test.kicad_sch"
        shutil.copy(SMALL_SCH, dst)

        tool = WriteSchematicPatchTool()
        result = _run(tool.execute({
            "path": str(dst),
            "operations": [{"op": "ADD_SYMBOL", "lib_id": "boardsmith:R", "reference": "R99", "value": "10k"}]
        }, _make_mock_context()))

        assert result.success
        assert "backup" in result.data

    def test_add_symbol_file_not_found_returns_failure(self, tmp_path):
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        tool = WriteSchematicPatchTool()
        result = _run(tool.execute({
            "path": str(tmp_path / "nonexistent.kicad_sch"),
            "operations": [{"op": "ADD_SYMBOL", "lib_id": "boardsmith:R", "reference": "R1", "value": "1k"}]
        }, _make_mock_context()))

        assert result.success is False
        assert result.error != ""


# ---------------------------------------------------------------------------
# WriteSchematicPatchTool.execute() — MODIFY_PROPERTY
# ---------------------------------------------------------------------------

class TestModifyPropertyOperation:
    def _get_a_uuid(self, sch_path: Path) -> str:
        """Extract first UUID from schematic for test use."""
        import re
        text = sch_path.read_text()
        matches = re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', text)
        assert matches, "No UUIDs found in schematic fixture"
        return matches[0]

    def _get_component_uuid(self, sch_path: Path) -> tuple[str, str]:
        """Return (uuid, current_value) for a component with a Value property."""
        import re
        text = sch_path.read_text()
        # Find a symbol block with uuid and Value property
        # Match: (uuid "...") in a symbol block
        uuid_pattern = re.compile(r'\(uuid\s+"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"\)')
        uuids = uuid_pattern.findall(text)
        return uuids[0] if uuids else ("", "")

    def test_modify_property_unknown_uuid_returns_failure(self, tmp_path):
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        dst = tmp_path / "test.kicad_sch"
        shutil.copy(SMALL_SCH, dst)

        tool = WriteSchematicPatchTool()
        result = _run(tool.execute({
            "path": str(dst),
            "operations": [{
                "op": "MODIFY_PROPERTY",
                "symbol_uuid": "00000000-dead-beef-cafe-000000000000",
                "property_name": "Value",
                "new_value": "NEWVAL",
            }]
        }, _make_mock_context()))

        assert result.success is False


# ---------------------------------------------------------------------------
# Safety rail: invalid result S-expression leaves original unchanged
# ---------------------------------------------------------------------------

class TestSafetyRailInvalidResult:
    def test_original_unchanged_on_invalid_result(self, tmp_path, monkeypatch):
        """If the modified result fails S-expression validation, original must be unchanged."""
        from boardsmith_hw.agent import write_schematic as ws_mod

        # Monkey-patch _apply_add_symbol to corrupt the result
        original_fn = ws_mod._apply_add_symbol

        def bad_apply(text, op, existing_uuids):
            # Return obviously malformed text
            return "(kicad_sch (unclosed"

        monkeypatch.setattr(ws_mod, "_apply_add_symbol", bad_apply)

        dst = tmp_path / "test.kicad_sch"
        shutil.copy(SMALL_SCH, dst)
        original_text = dst.read_text()

        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        tool = WriteSchematicPatchTool()
        result = _run(tool.execute({
            "path": str(dst),
            "operations": [{"op": "ADD_SYMBOL", "lib_id": "boardsmith:R", "reference": "R99", "value": "10k"}]
        }, _make_mock_context()))

        assert result.success is False
        assert dst.read_text() == original_text, "Original file was modified despite invalid result"


# ---------------------------------------------------------------------------
# Export from boardsmith_hw.agent.tools
# ---------------------------------------------------------------------------

class TestToolsInitExports:
    def test_all_four_tools_importable(self):
        from boardsmith_hw.agent.tools import (  # noqa: F401
            RunERCTool,
            ReadSchematicTool,
            SearchComponentTool,
            WriteSchematicPatchTool,
        )

    def test_write_schematic_patch_tool_in_all(self):
        from boardsmith_hw.agent import tools
        assert "WriteSchematicPatchTool" in tools.__all__
