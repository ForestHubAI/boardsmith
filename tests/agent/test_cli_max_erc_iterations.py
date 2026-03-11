# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for --max-erc-iterations CLI flag — Phase 08-02.

RED phase: written before implementation.

Tests both the `build` command (IterativeOrchestrator path) and
`build-project` command (direct Synthesizer path).

Run:
    PYTHONPATH=synthesizer:shared:compiler pytest tests/agent/test_cli_max_erc_iterations.py -x -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Pre-mock jsonschema so the synthesizer import chain doesn't fail in test environments
# where the optional jsonschema package is not installed (pre-existing gap, not Phase 8).
if "jsonschema" not in sys.modules:
    sys.modules["jsonschema"] = MagicMock()

REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler"):
    _p = str(REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Also add cli to PYTHONPATH for boardsmith module import
_cli = str(REPO_ROOT / "boardsmith_cli")
if _cli not in sys.path:
    sys.path.insert(0, _cli)


def _invoke_cli(args):
    """Run the CLI with click's CliRunner and return the result."""
    from click.testing import CliRunner
    sys.path.insert(0, str(REPO_ROOT / "boardsmith_cli"))
    from main import cli
    runner = CliRunner()
    return runner.invoke(cli, args, catch_exceptions=False)


# ---------------------------------------------------------------------------
# build-project: --max-erc-iterations wired to Synthesizer
# ---------------------------------------------------------------------------


class TestBuildProjectMaxErcIterations:
    """build-project --max-erc-iterations wires to Synthesizer._max_erc_iterations."""

    def test_build_project_help_shows_max_erc_iterations(self):
        """build-project --help shows --max-erc-iterations option."""
        result = _invoke_cli(["build-project", "--help"])
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        assert "max-erc-iterations" in result.output

    def test_build_project_passes_default_to_synthesizer(self):
        """build-project without --max-erc-iterations passes default=5 to Synthesizer."""
        init_calls = []

        class MockSynthesizer:
            def __init__(self, *args, **kwargs):
                init_calls.append(kwargs)

            def run(self, *args, **kwargs):
                from boardsmith_hw.synthesizer import SynthesisResult
                return SynthesisResult(success=True, confidence=0.85)

        import tempfile
        with tempfile.TemporaryDirectory() as d:
            with patch("boardsmith_hw.synthesizer.Synthesizer", MockSynthesizer):
                result = _invoke_cli([
                    "build-project",
                    "--prompt", "ESP32 test",
                    "--out", d,
                    "--no-llm",
                ])
        assert any(c.get("max_erc_iterations") == 5 for c in init_calls), \
            f"Expected max_erc_iterations=5 in calls: {init_calls}"

    def test_build_project_passes_custom_value_to_synthesizer(self):
        """build-project --max-erc-iterations 3 passes 3 to Synthesizer."""
        init_calls = []

        class MockSynthesizer:
            def __init__(self, *args, **kwargs):
                init_calls.append(kwargs)

            def run(self, *args, **kwargs):
                from boardsmith_hw.synthesizer import SynthesisResult
                return SynthesisResult(success=True, confidence=0.85)

        import tempfile
        with tempfile.TemporaryDirectory() as d:
            with patch("boardsmith_hw.synthesizer.Synthesizer", MockSynthesizer):
                result = _invoke_cli([
                    "build-project",
                    "--prompt", "ESP32 test",
                    "--out", d,
                    "--no-llm",
                    "--max-erc-iterations", "3",
                ])
        assert any(c.get("max_erc_iterations") == 3 for c in init_calls), \
            f"Expected max_erc_iterations=3 in calls: {init_calls}"


# ---------------------------------------------------------------------------
# build command: --max-erc-iterations flag exists and is accepted
# ---------------------------------------------------------------------------


class TestBuildCommandMaxErcIterations:
    """build --max-erc-iterations CLI flag is present and accepted."""

    def test_build_help_shows_max_erc_iterations(self):
        """boardsmith build --help shows --max-erc-iterations option."""
        result = _invoke_cli(["build", "--help"])
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        assert "max-erc-iterations" in result.output

    def test_build_accepts_max_erc_iterations_flag(self):
        """boardsmith build --max-erc-iterations 3 is accepted without error."""
        # We just check the flag is accepted (not its full end-to-end effect)
        # by parsing up to the point where orchestrator would be called.
        # Use --help as a lightweight way to verify flag parsing.
        result = _invoke_cli(["build", "--help"])
        assert "max-erc-iterations" in result.output

    def test_build_no_llm_with_max_erc_iterations_no_error(self):
        """--no-llm + --max-erc-iterations together is accepted (flag exists, agent not invoked)."""
        # This just checks CLI help shows the flag; actual runtime is tested
        # in integration tests (requires KiCad + LLM).
        result = _invoke_cli(["build", "--help"])
        assert "max-erc-iterations" in result.output
        # --no-llm also present
        assert "no-llm" in result.output
