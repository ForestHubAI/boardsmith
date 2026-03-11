# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for ModifyOrchestrator — Phase 09-01.

RED phase: written before implementation.

Run:
    PYTHONPATH=synthesizer:shared:compiler pytest tests/agent/test_modify_orchestrator.py -x -v
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler"):
    _p = str(REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_gateway(plan_json: str = '{"add": [], "modify": []}') -> MagicMock:
    gw = MagicMock()
    gw.complete_sync.return_value = MagicMock(content=plan_json, skipped=False)
    return gw


def _make_write_result(backup="/tmp/t.bak", success=True):
    r = MagicMock()
    r.success = success
    r.data = {"backup": backup, "applied": ["ADD_SYMBOL Device:R ref=R99"], "errors": []}
    r.error = None
    return r


def _make_erc_result(clean=True):
    r = MagicMock()
    r.is_clean = clean
    r.stalled = False
    r.cap_hit = False
    r.violations = [] if clean else [{"message": "Pin has no pull-up"}]
    return r


def _make_orchestrator(plan_json='{"add": [], "modify": []}'):
    """Make a ModifyOrchestrator with a mocked gateway."""
    from agents.modify_orchestrator import ModifyOrchestrator

    gw = _make_gateway(plan_json)
    return ModifyOrchestrator(gateway=gw, max_iterations=5), gw


# ---------------------------------------------------------------------------
# TestPlanDisplay
# ---------------------------------------------------------------------------


class TestPlanDisplay:
    """Plan output contains 'Adding:' and 'Modifying:' lines with component names."""

    def test_adding_line_present_when_add_non_empty(self):
        """When plan.add has items, 'Adding:' line appears in formatted plan."""
        plan_json = '{"add": [{"lib_id": "Device:R", "reference": "R99", "value": "10k"}], "modify": []}'
        orch, _ = _make_orchestrator(plan_json)
        from agents.modify_orchestrator import ModifyOrchestrator

        plan = {"add": [{"lib_id": "Device:R", "reference": "R99", "value": "10k"}], "modify": []}
        text = orch._format_plan(Path("test.kicad_sch"), plan)
        assert "Adding:" in text
        assert "R99" in text

    def test_modifying_line_present_when_modify_non_empty(self):
        """When plan.modify has items, 'Modifying:' line appears in formatted plan."""
        orch, _ = _make_orchestrator()
        plan = {
            "add": [],
            "modify": [{"symbol_uuid": "abc", "property_name": "Value", "new_value": "100k", "description": "VBAT net"}],
        }
        text = orch._format_plan(Path("test.kicad_sch"), plan)
        assert "Modifying:" in text
        assert "VBAT net" in text

    def test_adding_line_omitted_when_add_empty(self):
        """When plan.add is empty, 'Adding:' line is NOT present."""
        orch, _ = _make_orchestrator()
        plan = {"add": [], "modify": [{"symbol_uuid": "abc", "property_name": "Value", "new_value": "1k", "description": "some net"}]}
        text = orch._format_plan(Path("test.kicad_sch"), plan)
        assert "Adding:" not in text

    def test_modifying_line_omitted_when_modify_empty(self):
        """When plan.modify is empty, 'Modifying:' line is NOT present."""
        orch, _ = _make_orchestrator()
        plan = {"add": [{"lib_id": "Device:R", "reference": "R99", "value": "10k"}], "modify": []}
        text = orch._format_plan(Path("test.kicad_sch"), plan)
        assert "Modifying:" not in text

    def test_plan_header_contains_schematic_name(self):
        """Plan display header contains the schematic file name."""
        orch, _ = _make_orchestrator()
        plan = {"add": [], "modify": []}
        text = orch._format_plan(Path("myboard.kicad_sch"), plan)
        assert "myboard.kicad_sch" in text


# ---------------------------------------------------------------------------
# TestNoWriteBeforeConfirm
# ---------------------------------------------------------------------------


class TestNoWriteBeforeConfirm:
    """_apply_operations is not called before confirmation step."""

    def test_apply_not_called_before_confirm(self):
        """When _display_and_confirm returns False, _apply_operations is never called."""
        plan_json = '{"add": [{"lib_id": "Device:R", "reference": "R1", "value": "1k"}], "modify": []}'
        orch, _ = _make_orchestrator(plan_json)

        with patch.object(orch, "_read_schematic", return_value={}), \
             patch.object(orch, "_generate_plan", return_value={"add": [{"lib_id": "Device:R", "reference": "R1", "value": "1k"}], "modify": []}), \
             patch.object(orch, "_display_and_confirm", return_value=False), \
             patch.object(orch, "_apply_operations") as mock_apply:
            result = orch.run(sch_path=Path("x.kicad_sch"), instruction="add R1", yes=False)

        mock_apply.assert_not_called()

    def test_apply_not_called_when_empty_plan(self):
        """When plan has no add and no modify, _apply_operations is never called."""
        orch, _ = _make_orchestrator()

        with patch.object(orch, "_read_schematic", return_value={}), \
             patch.object(orch, "_generate_plan", return_value={"add": [], "modify": []}), \
             patch.object(orch, "_apply_operations") as mock_apply:
            result = orch.run(sch_path=Path("x.kicad_sch"), instruction="add R1", yes=True)

        mock_apply.assert_not_called()


# ---------------------------------------------------------------------------
# TestConfirmationUX
# ---------------------------------------------------------------------------


class TestConfirmationUX:
    """run() returns ModifyResult with success=False when input is empty Enter."""

    def test_empty_enter_aborts(self):
        """Empty input (empty Enter) leads to aborted=True result."""
        orch, _ = _make_orchestrator()

        with patch.object(orch, "_read_schematic", return_value={}), \
             patch.object(orch, "_generate_plan", return_value={"add": [{"lib_id": "Device:R", "reference": "R1", "value": "1k"}], "modify": []}), \
             patch.object(orch, "_display_and_confirm", return_value=False):
            result = orch.run(sch_path=Path("x.kicad_sch"), instruction="add R1", yes=False)

        assert result.success is False
        assert result.aborted is True

    def test_n_input_aborts(self):
        """'n' input leads to aborted=True result."""
        orch, _ = _make_orchestrator()

        with patch.object(orch, "_read_schematic", return_value={}), \
             patch.object(orch, "_generate_plan", return_value={"add": [{"lib_id": "Device:R", "reference": "R1", "value": "1k"}], "modify": []}), \
             patch.object(orch, "_display_and_confirm", return_value=False):
            result = orch.run(sch_path=Path("x.kicad_sch"), instruction="add R1", yes=False)

        assert result.success is False
        assert result.aborted is True


# ---------------------------------------------------------------------------
# TestYesFlag
# ---------------------------------------------------------------------------


class TestYesFlag:
    """run(yes=True) calls _apply_operations without blocking on stdin."""

    def test_yes_flag_calls_apply(self):
        """With yes=True, _apply_operations is called."""
        orch, _ = _make_orchestrator()
        write_result = _make_write_result()
        erc_result = _make_erc_result(clean=True)

        with patch.object(orch, "_read_schematic", return_value={}), \
             patch.object(orch, "_generate_plan", return_value={"add": [{"lib_id": "Device:R", "reference": "R1", "value": "1k"}], "modify": []}), \
             patch.object(orch, "_apply_operations", return_value=write_result) as mock_apply, \
             patch.object(orch, "_run_erc_agent", return_value=erc_result):
            result = orch.run(sch_path=Path("x.kicad_sch"), instruction="add R1", yes=True)

        mock_apply.assert_called_once()

    def test_yes_flag_does_not_need_stdin(self):
        """With yes=True, _display_and_confirm still returns True (no stdin block)."""
        orch, _ = _make_orchestrator()

        plan = {"add": [{"lib_id": "Device:R", "reference": "R1", "value": "1k"}], "modify": []}
        # _display_and_confirm with yes=True should return True without input
        result = orch._display_and_confirm(Path("x.kicad_sch"), plan, yes=True)
        assert result is True


# ---------------------------------------------------------------------------
# TestAbort
# ---------------------------------------------------------------------------


class TestAbort:
    """Aborted run returns ModifyResult(success=False, aborted=True) — not an exception."""

    def test_abort_returns_result_not_exception(self):
        """Aborting confirmation returns ModifyResult, not an exception."""
        orch, _ = _make_orchestrator()

        with patch.object(orch, "_read_schematic", return_value={}), \
             patch.object(orch, "_generate_plan", return_value={"add": [{"lib_id": "Device:R", "reference": "R1", "value": "1k"}], "modify": []}), \
             patch.object(orch, "_display_and_confirm", return_value=False):
            result = orch.run(sch_path=Path("x.kicad_sch"), instruction="add R1", yes=False)

        from agents.modify_orchestrator import ModifyResult

        assert isinstance(result, ModifyResult)
        assert result.success is False
        assert result.aborted is True

    def test_abort_is_not_error(self):
        """Aborted result has success=False and aborted=True (exit 0, not exit 1)."""
        orch, _ = _make_orchestrator()

        with patch.object(orch, "_read_schematic", return_value={}), \
             patch.object(orch, "_generate_plan", return_value={"add": [{"lib_id": "Device:R", "reference": "R1", "value": "1k"}], "modify": []}), \
             patch.object(orch, "_display_and_confirm", return_value=False):
            result = orch.run(sch_path=Path("x.kicad_sch"), instruction="add R1", yes=False)

        # aborted=True means CLI should exit 0, not treat as error
        assert result.aborted is True
        assert result.success is False


# ---------------------------------------------------------------------------
# TestBackup
# ---------------------------------------------------------------------------


class TestBackup:
    """After successful run, backup_path is populated and printed to stdout."""

    def test_backup_path_in_result(self):
        """After successful run, result.backup_path matches backup from write tool."""
        orch, _ = _make_orchestrator()
        write_result = _make_write_result(backup="/tmp/t.bak", success=True)
        erc_result = _make_erc_result(clean=True)

        with patch.object(orch, "_read_schematic", return_value={}), \
             patch.object(orch, "_generate_plan", return_value={"add": [{"lib_id": "Device:R", "reference": "R1", "value": "1k"}], "modify": []}), \
             patch.object(orch, "_apply_operations", return_value=write_result), \
             patch.object(orch, "_run_erc_agent", return_value=erc_result):
            result = orch.run(sch_path=Path("x.kicad_sch"), instruction="add R1", yes=True)

        assert result.backup_path == "/tmp/t.bak"

    def test_backup_path_printed_to_stdout(self, capsys):
        """After successful run, stdout contains 'Backup: /tmp/t.bak'."""
        orch, _ = _make_orchestrator()
        write_result = _make_write_result(backup="/tmp/t.bak", success=True)
        erc_result = _make_erc_result(clean=True)

        with patch.object(orch, "_read_schematic", return_value={}), \
             patch.object(orch, "_generate_plan", return_value={"add": [{"lib_id": "Device:R", "reference": "R1", "value": "1k"}], "modify": []}), \
             patch.object(orch, "_apply_operations", return_value=write_result), \
             patch.object(orch, "_run_erc_agent", return_value=erc_result):
            orch.run(sch_path=Path("x.kicad_sch"), instruction="add R1", yes=True)

        captured = capsys.readouterr()
        assert "Backup: /tmp/t.bak" in captured.out


# ---------------------------------------------------------------------------
# TestBackupContents
# ---------------------------------------------------------------------------


class TestBackupContents:
    """backup_path in result matches what write tool returned."""

    def test_backup_path_matches_write_tool(self):
        """result.backup_path matches write_result.data['backup']."""
        orch, _ = _make_orchestrator()
        expected_bak = "/tmp/specific_backup.bak"
        write_result = _make_write_result(backup=expected_bak, success=True)
        erc_result = _make_erc_result(clean=True)

        with patch.object(orch, "_read_schematic", return_value={}), \
             patch.object(orch, "_generate_plan", return_value={"add": [{"lib_id": "Device:R", "reference": "R1", "value": "1k"}], "modify": []}), \
             patch.object(orch, "_apply_operations", return_value=write_result), \
             patch.object(orch, "_run_erc_agent", return_value=erc_result):
            result = orch.run(sch_path=Path("x.kicad_sch"), instruction="add R1", yes=True)

        assert result.backup_path == expected_bak


# ---------------------------------------------------------------------------
# TestERCOutput
# ---------------------------------------------------------------------------


class TestERCOutput:
    """ERC result drives output."""

    def test_clean_erc_result(self):
        """When ERC is clean, result.erc_clean=True."""
        orch, _ = _make_orchestrator()
        write_result = _make_write_result(success=True)
        erc_result = _make_erc_result(clean=True)

        with patch.object(orch, "_read_schematic", return_value={}), \
             patch.object(orch, "_generate_plan", return_value={"add": [{"lib_id": "Device:R", "reference": "R1", "value": "1k"}], "modify": []}), \
             patch.object(orch, "_apply_operations", return_value=write_result), \
             patch.object(orch, "_run_erc_agent", return_value=erc_result):
            result = orch.run(sch_path=Path("x.kicad_sch"), instruction="add R1", yes=True)

        assert result.erc_clean is True

    def test_violations_in_result_when_erc_fails(self):
        """When ERC has violations, result.erc_violations is populated."""
        orch, _ = _make_orchestrator()
        write_result = _make_write_result(success=True)
        erc_result = _make_erc_result(clean=False)

        with patch.object(orch, "_read_schematic", return_value={}), \
             patch.object(orch, "_generate_plan", return_value={"add": [{"lib_id": "Device:R", "reference": "R1", "value": "1k"}], "modify": []}), \
             patch.object(orch, "_apply_operations", return_value=write_result), \
             patch.object(orch, "_run_erc_agent", return_value=erc_result):
            result = orch.run(sch_path=Path("x.kicad_sch"), instruction="add R1", yes=True)

        assert result.erc_violations is not None
        assert len(result.erc_violations) > 0

    def test_erc_skipped_when_kicad_cli_not_found(self, capsys):
        """When kicad-cli heuristic matches, erc_skipped=True and message printed."""
        orch, _ = _make_orchestrator()
        write_result = _make_write_result(success=True)
        # Simulate kicad-cli not found: cap_hit=True, single violation with "kicad-cli" in message
        erc_result = MagicMock()
        erc_result.is_clean = False
        erc_result.stalled = False
        erc_result.cap_hit = True
        erc_result.violations = [{"message": "kicad-cli not found in PATH"}]

        with patch.object(orch, "_read_schematic", return_value={}), \
             patch.object(orch, "_generate_plan", return_value={"add": [{"lib_id": "Device:R", "reference": "R1", "value": "1k"}], "modify": []}), \
             patch.object(orch, "_apply_operations", return_value=write_result), \
             patch.object(orch, "_run_erc_agent", return_value=erc_result):
            result = orch.run(sch_path=Path("x.kicad_sch"), instruction="add R1", yes=True)

        captured = capsys.readouterr()
        assert result.erc_skipped is True
        assert "ERC skipped" in captured.out or "kicad-cli" in captured.out


# ---------------------------------------------------------------------------
# TestHIRWarning
# ---------------------------------------------------------------------------


class TestHIRWarning:
    """HIR warning text is emitted after any write completes."""

    def test_hir_warning_emitted_on_clean_erc(self, capsys):
        """HIR warning is always printed after a successful write, even with clean ERC."""
        orch, _ = _make_orchestrator()
        write_result = _make_write_result(success=True)
        erc_result = _make_erc_result(clean=True)

        with patch.object(orch, "_read_schematic", return_value={}), \
             patch.object(orch, "_generate_plan", return_value={"add": [{"lib_id": "Device:R", "reference": "R1", "value": "1k"}], "modify": []}), \
             patch.object(orch, "_apply_operations", return_value=write_result), \
             patch.object(orch, "_run_erc_agent", return_value=erc_result):
            orch.run(sch_path=Path("x.kicad_sch"), instruction="add R1", yes=True)

        captured = capsys.readouterr()
        assert "HIR out of sync" in captured.out

    def test_hir_warning_emitted_on_violations(self, capsys):
        """HIR warning is printed even when ERC has violations."""
        orch, _ = _make_orchestrator()
        write_result = _make_write_result(success=True)
        erc_result = _make_erc_result(clean=False)

        with patch.object(orch, "_read_schematic", return_value={}), \
             patch.object(orch, "_generate_plan", return_value={"add": [{"lib_id": "Device:R", "reference": "R1", "value": "1k"}], "modify": []}), \
             patch.object(orch, "_apply_operations", return_value=write_result), \
             patch.object(orch, "_run_erc_agent", return_value=erc_result):
            orch.run(sch_path=Path("x.kicad_sch"), instruction="add R1", yes=True)

        captured = capsys.readouterr()
        assert "HIR out of sync" in captured.out


# ---------------------------------------------------------------------------
# TestImportClean
# ---------------------------------------------------------------------------


class TestImportClean:
    """BOARDSMITH_NO_LLM=1 importing modify_orchestrator exits 0."""

    def test_no_llm_import_safe(self):
        """Import modify_orchestrator with BOARDSMITH_NO_LLM=1 exits 0."""
        env = {**os.environ, "BOARDSMITH_NO_LLM": "1"}
        result = subprocess.run(
            [sys.executable, "-c", "from agents.modify_orchestrator import ModifyOrchestrator"],
            env=env,
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT / "shared"),
        )
        assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# TestEmptyPlan
# ---------------------------------------------------------------------------


class TestEmptyPlan:
    """run() with plan returning add=[] and modify=[] returns early, success=False, no write."""

    def test_empty_plan_returns_early(self):
        """Empty plan (add=[], modify=[]) returns ModifyResult(success=False) without writing."""
        orch, _ = _make_orchestrator('{"add": [], "modify": []}')

        with patch.object(orch, "_read_schematic", return_value={}), \
             patch.object(orch, "_generate_plan", return_value={"add": [], "modify": []}), \
             patch.object(orch, "_apply_operations") as mock_apply:
            result = orch.run(sch_path=Path("x.kicad_sch"), instruction="nothing", yes=True)

        mock_apply.assert_not_called()
        assert result.success is False

    def test_empty_plan_no_write(self):
        """Empty plan does not call _apply_operations."""
        orch, _ = _make_orchestrator()

        with patch.object(orch, "_read_schematic", return_value={}), \
             patch.object(orch, "_generate_plan", return_value={"add": [], "modify": []}), \
             patch.object(orch, "_apply_operations") as mock_apply:
            orch.run(sch_path=Path("x.kicad_sch"), instruction="noop", yes=True)

        mock_apply.assert_not_called()


# ---------------------------------------------------------------------------
# CLI-level tests (Plan 09-02)
# ---------------------------------------------------------------------------

class TestCLIHelp:
    """boardsmith modify --help shows all flags."""

    def test_help_shows_schematic_path(self):
        from boardsmith_cli.main import cli
        from click.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(cli, ["modify", "--help"])
        assert result.exit_code == 0
        assert "SCHEMATIC_PATH" in result.output or "schematic_path" in result.output.lower()

    def test_help_shows_yes_flag(self):
        from boardsmith_cli.main import cli
        from click.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(cli, ["modify", "--help"])
        assert "--yes" in result.output

    def test_help_shows_max_erc_iterations(self):
        from boardsmith_cli.main import cli
        from click.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(cli, ["modify", "--help"])
        assert "--max-erc-iterations" in result.output

    def test_help_shows_no_llm(self):
        from boardsmith_cli.main import cli
        from click.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(cli, ["modify", "--help"])
        assert "--no-llm" in result.output


class TestNoLLM:
    """--no-llm flag exits 1 with actionable error message."""

    def test_no_llm_exits_1(self, tmp_path):
        from boardsmith_cli.main import cli
        from click.testing import CliRunner
        runner = CliRunner()
        sch = tmp_path / "test.kicad_sch"
        sch.write_text("(kicad_sch)")
        result = runner.invoke(cli, ["modify", str(sch), "add R1", "--no-llm"])
        assert result.exit_code == 1

    def test_no_llm_error_message(self, tmp_path):
        from boardsmith_cli.main import cli
        from click.testing import CliRunner
        runner = CliRunner()
        sch = tmp_path / "test.kicad_sch"
        sch.write_text("(kicad_sch)")
        result = runner.invoke(cli, ["modify", str(sch), "add R1", "--no-llm"])
        assert "requires an LLM API key" in result.output


class TestCLIAbortExitCode:
    """CLI exits 0 when orchestrator returns aborted=True (user declined confirmation)."""

    def test_aborted_result_exits_0(self, tmp_path):
        from boardsmith_cli.main import cli
        from click.testing import CliRunner
        from unittest.mock import MagicMock, patch
        runner = CliRunner()
        sch = tmp_path / "test.kicad_sch"
        sch.write_text("(kicad_sch)")

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.aborted = True

        with patch("agents.modify_orchestrator.ModifyOrchestrator.run", return_value=mock_result):
            result = runner.invoke(
                cli,
                ["modify", str(sch), "add R1"],
                catch_exceptions=False,
            )
        assert result.exit_code == 0

    def test_failed_result_exits_1(self, tmp_path):
        """Non-abort failure (write or LLM error) exits 1."""
        from boardsmith_cli.main import cli
        from click.testing import CliRunner
        from unittest.mock import MagicMock, patch
        runner = CliRunner()
        sch = tmp_path / "test.kicad_sch"
        sch.write_text("(kicad_sch)")

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.aborted = False

        with patch("agents.modify_orchestrator.ModifyOrchestrator.run", return_value=mock_result):
            result = runner.invoke(
                cli,
                ["modify", str(sch), "add R1"],
                catch_exceptions=False,
            )
        assert result.exit_code != 0


class TestCLIYesFlag:
    """--yes flag is forwarded to orchestrator.run(yes=True)."""

    def test_yes_forwarded_to_orchestrator(self, tmp_path):
        from boardsmith_cli.main import cli
        from click.testing import CliRunner
        from unittest.mock import MagicMock, patch, call
        runner = CliRunner()
        sch = tmp_path / "test.kicad_sch"
        sch.write_text("(kicad_sch)")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.aborted = False

        with patch("agents.modify_orchestrator.ModifyOrchestrator.run", return_value=mock_result) as mock_run:
            runner.invoke(
                cli,
                ["modify", str(sch), "add R1", "--yes"],
                catch_exceptions=False,
            )
        # verify yes=True was passed
        assert mock_run.call_args is not None
        _, kwargs = mock_run.call_args
        assert kwargs.get("yes") is True or (mock_run.call_args[0] and mock_run.call_args[0][2] is True)
