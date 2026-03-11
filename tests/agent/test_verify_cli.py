# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for boardsmith verify CLI command — Phase 11-02.

RED phase: stubs written before implementation of the verify command.

Run:
    PYTHONPATH=synthesizer:shared:compiler:boardsmith_cli .venv/bin/pytest tests/agent/test_verify_cli.py -x -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler", "boardsmith_cli"):
    _p = str(REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from click.testing import CliRunner
from boardsmith_cli.main import cli


# ---------------------------------------------------------------------------
# Test 1: --no-llm flag exits 1 with "requires LLM" message
# ---------------------------------------------------------------------------


def test_verify_no_llm_flag_exits_1(tmp_path):
    """boardsmith verify <sch> --no-llm exits 1 with 'requires LLM' in output."""
    sch = tmp_path / "test.kicad_sch"
    sch.write_text("(kicad_sch)")

    runner = CliRunner()
    result = runner.invoke(cli, ["verify", str(sch), "--no-llm"])

    assert result.exit_code == 1
    assert "requires LLM" in result.output


# ---------------------------------------------------------------------------
# Test 2: Missing hir.json exits 1 with "hir.json not found" message
# ---------------------------------------------------------------------------


def test_verify_missing_hir_exits_1(tmp_path):
    """boardsmith verify <sch> without hir.json exits 1 with 'hir.json not found'."""
    sch = tmp_path / "test.kicad_sch"
    sch.write_text("(kicad_sch)")
    # No hir.json in tmp_path

    runner = CliRunner()
    result = runner.invoke(cli, ["verify", str(sch)])

    assert result.exit_code == 1
    assert "hir.json not found" in result.output


# ---------------------------------------------------------------------------
# Test 3: --help shows all expected options
# ---------------------------------------------------------------------------


def test_verify_help():
    """boardsmith verify --help exits 0 and shows expected options."""
    runner = CliRunner()
    result = runner.invoke(cli, ["verify", "--help"])

    assert result.exit_code == 0
    assert "--hir-path" in result.output
    assert "--max-semantic-iterations" in result.output
    assert "--no-llm" in result.output


# ---------------------------------------------------------------------------
# Test 4: Clean run with mocked agent (skipped in Wave 0)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="requires live LLM — integration test")
def test_verify_clean_with_mocked_agent(tmp_path):
    """boardsmith verify with mocked SemanticVerificationAgent exits 0."""
    sch = tmp_path / "test.kicad_sch"
    sch.write_text("(kicad_sch)")
    hir = tmp_path / "hir.json"
    hir.write_text('{"version": "1.0"}')

    mock_result = MagicMock()
    mock_result.is_clean = True
    mock_result.summary_message = "all checks passed"

    mock_agent = MagicMock()
    mock_agent.run.return_value = mock_result

    runner = CliRunner()
    with patch("boardsmith_cli.main.SemanticVerificationAgent", return_value=mock_agent):
        result = runner.invoke(cli, ["verify", str(sch)])

    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Test 5: Synthesizer accepts max_semantic_iterations parameter (skipped in Wave 0)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="synthesizer integration — requires Plan 02 task 02")
def test_verify_b84_synthesizer_attribute(tmp_path):
    """Synthesizer.__init__ accepts max_semantic_iterations parameter."""
    import inspect

    from boardsmith_hw.synthesizer import Synthesizer

    sig = inspect.signature(Synthesizer.__init__)
    assert "max_semantic_iterations" in sig.parameters, (
        "Synthesizer.__init__ must have max_semantic_iterations parameter"
    )
    # Also verify it can be constructed with the parameter
    s = Synthesizer(out_dir=tmp_path, max_semantic_iterations=3)
    assert s._max_semantic_iterations == 3
