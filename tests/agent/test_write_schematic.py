# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for WriteSchematicPatchTool.

TOOL-03: ADD_SYMBOL inserts valid KiCad syntax; .bak exists before write;
invalid S-expression is rejected; two symbols have distinct UUIDs.

All tests use the minimal.kicad_sch fixture — no real kicad-cli required.

Run: PYTHONPATH=synthesizer:shared:compiler pytest tests/agent/test_write_schematic.py -x -v
"""
from __future__ import annotations
import asyncio
import re
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler"):
    _p = str(REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

FIXTURES = Path(__file__).parent / "fixtures"
MINIMAL_KCH = FIXTURES / "minimal.kicad_sch"


def _run(coro):
    return asyncio.run(coro)


def _make_context():
    ctx = MagicMock()
    ctx.no_llm = False
    return ctx


def _copy_fixture(tmp_path: Path) -> Path:
    """Copy minimal.kicad_sch to a temp directory and return the copy path."""
    dst = tmp_path / "test.kicad_sch"
    shutil.copy(MINIMAL_KCH, dst)
    return dst


class TestBackupCreation:
    """TOOL-03: .bak file exists before any write occurs."""

    def test_backup_created_on_execute(self, tmp_path):
        """A .bak file must exist after execute() — even if operations are empty list."""
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        dst = _copy_fixture(tmp_path)
        original_bytes = dst.read_bytes()
        tool = WriteSchematicPatchTool()
        ctx = _make_context()

        _run(tool.execute({"path": str(dst), "operations": [
            {"op": "ADD_SYMBOL", "lib_id": "boardsmith:R",
             "reference": "R99", "value": "4.7k"}
        ]}, ctx))

        baks = list(tmp_path.glob("*.bak"))
        assert baks, "No .bak file found after execute()"

    def test_backup_byte_identical_to_original(self, tmp_path):
        """The .bak must be byte-identical to the pre-run original."""
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        dst = _copy_fixture(tmp_path)
        original_bytes = dst.read_bytes()
        tool = WriteSchematicPatchTool()
        ctx = _make_context()

        _run(tool.execute({"path": str(dst), "operations": [
            {"op": "ADD_SYMBOL", "lib_id": "boardsmith:R",
             "reference": "R99", "value": "4.7k"}
        ]}, ctx))

        baks = list(tmp_path.glob("*.bak"))
        assert baks[0].read_bytes() == original_bytes

    def test_backup_timestamp_format(self, tmp_path):
        """Backup filename matches {name}.kicad_sch.{YYYYMMDD-HHMMSS}.bak pattern."""
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        dst = _copy_fixture(tmp_path)
        tool = WriteSchematicPatchTool()
        ctx = _make_context()

        _run(tool.execute({"path": str(dst), "operations": [
            {"op": "ADD_SYMBOL", "lib_id": "boardsmith:R",
             "reference": "R99", "value": "4.7k"}
        ]}, ctx))

        baks = list(tmp_path.glob("*.bak"))
        bak_name = baks[0].name
        assert re.search(r'\.\d{8}-\d{6}\.bak$', bak_name), (
            f"Backup name '{bak_name}' does not match YYYYMMDD-HHMMSS pattern"
        )

    def test_create_backup_helper_directly(self, tmp_path):
        """_create_backup() returns the backup path and creates a byte-identical copy."""
        from boardsmith_hw.agent.write_schematic import _create_backup
        src = _copy_fixture(tmp_path)
        original_bytes = src.read_bytes()

        bak_path = _create_backup(src)

        assert bak_path.exists()
        assert bak_path.read_bytes() == original_bytes
        assert src.exists()  # original must still be there


class TestAddSymbol:
    """TOOL-03: ADD_SYMBOL inserts a valid KiCad symbol into the schematic."""

    def test_add_symbol_success(self, tmp_path):
        """ADD_SYMBOL returns ToolResult(success=True) for valid input."""
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        dst = _copy_fixture(tmp_path)
        tool = WriteSchematicPatchTool()
        ctx = _make_context()

        result = _run(tool.execute({"path": str(dst), "operations": [
            {"op": "ADD_SYMBOL", "lib_id": "boardsmith:R",
             "reference": "R99", "value": "4.7k", "footprint": "Resistor_SMD:R_0402_1005Metric"}
        ]}, ctx))

        assert result.success, f"Expected success but got error: {result.error}"

    def test_add_symbol_reference_in_file(self, tmp_path):
        """After ADD_SYMBOL, the reference designator appears in the modified file."""
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        dst = _copy_fixture(tmp_path)
        tool = WriteSchematicPatchTool()
        ctx = _make_context()

        _run(tool.execute({"path": str(dst), "operations": [
            {"op": "ADD_SYMBOL", "lib_id": "boardsmith:R",
             "reference": "R_UNIQUE_TEST", "value": "100k"}
        ]}, ctx))

        content = dst.read_text()
        assert "R_UNIQUE_TEST" in content, "Reference not found in modified file"

    def test_add_symbol_result_is_valid_kicad_sch(self, tmp_path):
        """Modified file must parse as valid kicad_sch after ADD_SYMBOL."""
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool, _validate_sexpr
        dst = _copy_fixture(tmp_path)
        tool = WriteSchematicPatchTool()
        ctx = _make_context()

        _run(tool.execute({"path": str(dst), "operations": [
            {"op": "ADD_SYMBOL", "lib_id": "boardsmith:R",
             "reference": "R99", "value": "4.7k"}
        ]}, ctx))

        # Must not raise
        _validate_sexpr(dst.read_text())

    def test_add_symbol_uuid_in_file(self, tmp_path):
        """After ADD_SYMBOL, the inserted symbol has a UUID in the file."""
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        dst = _copy_fixture(tmp_path)
        original_text = dst.read_text()
        tool = WriteSchematicPatchTool()
        ctx = _make_context()

        _run(tool.execute({"path": str(dst), "operations": [
            {"op": "ADD_SYMBOL", "lib_id": "boardsmith:R",
             "reference": "R99", "value": "4.7k"}
        ]}, ctx))

        modified_text = dst.read_text()
        original_uuids = set(re.findall(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            original_text
        ))
        new_uuids = set(re.findall(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            modified_text
        ))
        added_uuids = new_uuids - original_uuids
        assert added_uuids, "No new UUID found in modified file after ADD_SYMBOL"

    def test_file_not_found_returns_failure(self, tmp_path):
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        tool = WriteSchematicPatchTool()
        ctx = _make_context()

        result = _run(tool.execute({"path": str(tmp_path / "nonexistent.kicad_sch"),
                                     "operations": []}, ctx))

        assert result.success is False
        assert "not found" in result.error.lower()


class TestModifyProperty:
    """TOOL-03: MODIFY_PROPERTY updates a property in the S-expression tree."""

    def test_modify_property_value(self, tmp_path):
        """MODIFY_PROPERTY changes the Value property of a known symbol UUID."""
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        dst = _copy_fixture(tmp_path)
        tool = WriteSchematicPatchTool()
        ctx = _make_context()

        # R1 in minimal.kicad_sch has UUID "5682ce4f-3930-4029-aba6-dc91451ea155"
        result = _run(tool.execute({"path": str(dst), "operations": [
            {
                "op": "MODIFY_PROPERTY",
                "symbol_uuid": "5682ce4f-3930-4029-aba6-dc91451ea155",
                "property_name": "Value",
                "new_value": "22k",
            }
        ]}, ctx))

        assert result.success, f"MODIFY_PROPERTY failed: {result.error}"
        content = dst.read_text()
        assert "22k" in content

    def test_modify_property_unknown_uuid_fails(self, tmp_path):
        """MODIFY_PROPERTY with a non-existent UUID returns success=False."""
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        dst = _copy_fixture(tmp_path)
        tool = WriteSchematicPatchTool()
        ctx = _make_context()

        result = _run(tool.execute({"path": str(dst), "operations": [
            {
                "op": "MODIFY_PROPERTY",
                "symbol_uuid": "00000000-0000-0000-0000-000000000000",
                "property_name": "Value",
                "new_value": "should_not_appear",
            }
        ]}, ctx))

        assert result.success is False
        content = dst.read_text()
        assert "should_not_appear" not in content


class TestSExprValidation:
    """TOOL-03: invalid S-expression is rejected; original file is unchanged."""

    def test_invalid_result_leaves_original_unchanged(self, tmp_path, monkeypatch):
        """If the patched result is invalid S-expression, original file is not overwritten."""
        from boardsmith_hw.agent import write_schematic as ws_module
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        dst = _copy_fixture(tmp_path)
        original_text = dst.read_text()
        tool = WriteSchematicPatchTool()
        ctx = _make_context()

        # Monkeypatch _apply_add_symbol to return deliberately broken S-expression
        def _bad_add(text, op, existing_uuids):
            return "(kicad_sch (this is (missing close paren)"
        monkeypatch.setattr(ws_module, "_apply_add_symbol", _bad_add)

        result = _run(tool.execute({"path": str(dst), "operations": [
            {"op": "ADD_SYMBOL", "lib_id": "boardsmith:R",
             "reference": "R99", "value": "4.7k"}
        ]}, ctx))

        assert result.success is False
        assert "invalid" in result.error.lower() or "unchanged" in result.error.lower()
        assert dst.read_text() == original_text, "Original file was modified on validation failure"

    def test_validate_sexpr_rejects_bad_root(self):
        from boardsmith_hw.agent.write_schematic import _validate_sexpr
        with pytest.raises(ValueError, match="kicad_sch"):
            _validate_sexpr("(not_kicad_sch (version 1))")

    def test_validate_sexpr_accepts_minimal_fixture(self):
        from boardsmith_hw.agent.write_schematic import _validate_sexpr
        text = MINIMAL_KCH.read_text()
        # Must not raise
        _validate_sexpr(text)

    def test_backup_exists_even_on_validation_failure(self, tmp_path, monkeypatch):
        """Backup is created even when the result is rejected — it documents what was there."""
        from boardsmith_hw.agent import write_schematic as ws_module
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        dst = _copy_fixture(tmp_path)
        tool = WriteSchematicPatchTool()
        ctx = _make_context()

        def _bad_add(text, op, existing_uuids):
            return "(kicad_sch (broken"
        monkeypatch.setattr(ws_module, "_apply_add_symbol", _bad_add)

        _run(tool.execute({"path": str(dst), "operations": [
            {"op": "ADD_SYMBOL", "lib_id": "boardsmith:R",
             "reference": "R99", "value": "4.7k"}
        ]}, ctx))

        baks = list(tmp_path.glob("*.bak"))
        assert baks, "Backup must exist even when validation fails"


class TestUUIDUniqueness:
    """TOOL-03: Two symbols created in the same session have distinct UUIDs."""

    def test_two_add_ops_produce_distinct_uuids(self, tmp_path):
        """Two ADD_SYMBOL ops in one execute() call must produce different UUIDs."""
        from boardsmith_hw.agent.write_schematic import WriteSchematicPatchTool
        dst = _copy_fixture(tmp_path)
        original_text = dst.read_text()
        original_uuids = set(re.findall(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            original_text
        ))
        tool = WriteSchematicPatchTool()
        ctx = _make_context()

        result = _run(tool.execute({"path": str(dst), "operations": [
            {"op": "ADD_SYMBOL", "lib_id": "boardsmith:R", "reference": "R_A", "value": "1k"},
            {"op": "ADD_SYMBOL", "lib_id": "boardsmith:R", "reference": "R_B", "value": "2k"},
        ]}, ctx))

        assert result.success, f"Expected success but got: {result.error}"
        modified_text = dst.read_text()
        all_uuids = set(re.findall(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            modified_text
        ))
        new_uuids = all_uuids - original_uuids
        assert len(new_uuids) >= 2, (
            f"Expected at least 2 new UUIDs for 2 ADD ops, got {len(new_uuids)}: {new_uuids}"
        )

    def test_new_uuid_helper_no_collision(self):
        """_new_uuid() never returns the same value twice for the same set."""
        from boardsmith_hw.agent.write_schematic import _new_uuid
        existing: set[str] = set()
        uuids = {_new_uuid(existing) for _ in range(50)}
        assert len(uuids) == 50, "UUID collision detected in 50 sequential calls"

    def test_new_uuid_format(self):
        """_new_uuid() output matches KiCad UUID format."""
        from boardsmith_hw.agent.write_schematic import _new_uuid
        u = _new_uuid(set())
        assert re.fullmatch(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', u
        ), f"UUID format mismatch: {u!r}"
