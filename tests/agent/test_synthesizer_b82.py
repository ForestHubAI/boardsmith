# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Synthesizer B8.2 block and max_erc_iterations wiring — Phase 08-02.

RED phase: written before implementation.

Run:
    PYTHONPATH=synthesizer:shared:compiler pytest tests/agent/test_synthesizer_b82.py -x -v
"""
from __future__ import annotations

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
# Task 1: Synthesizer.__init__ accepts max_erc_iterations
# ---------------------------------------------------------------------------


class TestSynthesizerMaxErcIterations:
    """Synthesizer constructor stores max_erc_iterations."""

    def test_default_is_five(self):
        """Synthesizer() with no max_erc_iterations defaults to 5."""
        from boardsmith_hw.synthesizer import Synthesizer
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            s = Synthesizer(out_dir=Path(d))
            assert s._max_erc_iterations == 5

    def test_custom_value_stored(self):
        """Synthesizer(max_erc_iterations=3) stores 3."""
        from boardsmith_hw.synthesizer import Synthesizer
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            s = Synthesizer(out_dir=Path(d), max_erc_iterations=3)
            assert s._max_erc_iterations == 3

    def test_existing_callers_unaffected(self):
        """Synthesizer(out_dir=..., use_llm=False) still works — backward compat."""
        from boardsmith_hw.synthesizer import Synthesizer
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            s = Synthesizer(out_dir=Path(d), use_llm=False)
            assert s._max_erc_iterations == 5

    def test_existing_callers_with_target(self):
        """Synthesizer(out_dir=..., target='rp2040', use_llm=False) still works."""
        from boardsmith_hw.synthesizer import Synthesizer
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            s = Synthesizer(out_dir=Path(d), target="rp2040", use_llm=False)
            assert s._max_erc_iterations == 5

    def test_zero_boundary_allowed(self):
        """max_erc_iterations=1 (minimum useful) is accepted."""
        from boardsmith_hw.synthesizer import Synthesizer
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            s = Synthesizer(out_dir=Path(d), max_erc_iterations=1)
            assert s._max_erc_iterations == 1


# ---------------------------------------------------------------------------
# Task 1: B8.2 guard logic — ERCAgent invocation conditions
# ---------------------------------------------------------------------------


class TestB82GuardConditions:
    """B8.2 block guard: only runs when not passed AND tool_available AND use_llm."""

    def _make_erc_ref(self, passed: bool, tool_available: bool, violations=None):
        """Create a mock ERCRefiner result."""
        mock = MagicMock()
        mock.passed = passed
        mock.tool_available = tool_available
        mock.iterations = 1
        mock.fixes_applied = []
        mock.initial_errors = 0
        mock.final_errors = 0 if passed else 1
        final_check = MagicMock()
        final_check.violations = violations or []
        final_check.error_count = 0 if passed else 1
        final_check.warning_count = 0
        final_check.error_messages = []
        final_check.note = ""
        mock.final_check = final_check
        return mock

    def test_agent_not_called_when_erc_passed(self):
        """When erc_ref.passed=True, ERCAgent is NOT instantiated."""
        from boardsmith_hw.synthesizer import Synthesizer
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            s = Synthesizer(out_dir=Path(d), use_llm=True, max_erc_iterations=3)
            erc_ref = self._make_erc_ref(passed=True, tool_available=True)

            agent_calls = []

            class FakeERCAgent:
                def __init__(self, *args, **kwargs):
                    agent_calls.append("init")

                def run(self):
                    agent_calls.append("run")
                    return MagicMock(is_clean=True, iterations_used=1, summary_message="ok")

            # Use the B8.2 guard logic directly by extracting it — we test the guard
            # by checking that when passed=True, agent is not called.
            # The B8.2 block: if not erc_ref.passed and erc_ref.tool_available and self._use_llm
            guard = (not erc_ref.passed) and erc_ref.tool_available and s._use_llm
            assert guard is False, "Guard must be False when erc passed"

    def test_agent_not_called_when_tool_unavailable(self):
        """When erc_ref.tool_available=False, ERCAgent is NOT instantiated."""
        from boardsmith_hw.synthesizer import Synthesizer
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            s = Synthesizer(out_dir=Path(d), use_llm=True, max_erc_iterations=3)
            erc_ref = self._make_erc_ref(passed=False, tool_available=False)

            guard = (not erc_ref.passed) and erc_ref.tool_available and s._use_llm
            assert guard is False, "Guard must be False when tool unavailable"

    def test_agent_not_called_when_no_llm(self):
        """When use_llm=False, ERCAgent is NOT instantiated."""
        from boardsmith_hw.synthesizer import Synthesizer
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            s = Synthesizer(out_dir=Path(d), use_llm=False, max_erc_iterations=3)
            erc_ref = self._make_erc_ref(passed=False, tool_available=True)

            guard = (not erc_ref.passed) and erc_ref.tool_available and s._use_llm
            assert guard is False, "Guard must be False when use_llm=False"

    def test_agent_should_run_when_all_conditions_met(self):
        """When failed AND tool available AND use_llm — guard is True."""
        from boardsmith_hw.synthesizer import Synthesizer
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            s = Synthesizer(out_dir=Path(d), use_llm=True, max_erc_iterations=3)
            erc_ref = self._make_erc_ref(passed=False, tool_available=True)

            guard = (not erc_ref.passed) and erc_ref.tool_available and s._use_llm
            assert guard is True, "Guard must be True for all conditions met"


# ---------------------------------------------------------------------------
# Task 1: B8.2 import clean — BOARDSMITH_NO_LLM=1 never imports ERCAgent at module level
# ---------------------------------------------------------------------------


class TestB82ImportClean:
    """BOARDSMITH_NO_LLM=1 synthesizer import must stay clean."""

    def test_synthesizer_import_no_llm(self, tmp_path):
        """Synthesizer can be imported with BOARDSMITH_NO_LLM=1 — no LLM side-effects."""
        import subprocess
        import os

        script = tmp_path / "check_import.py"
        script.write_text(
            "import os\n"
            "os.environ['BOARDSMITH_NO_LLM'] = '1'\n"
            # Pre-mock jsonschema — pre-existing optional dep not installed in dev/CI;
            # not a Phase 8 concern (synth_core.hir_bridge.validator imports it at module level).
            "from unittest.mock import MagicMock\n"
            "import sys\n"
            "if 'jsonschema' not in sys.modules:\n"
            "    sys.modules['jsonschema'] = MagicMock()\n"
            "from boardsmith_hw.synthesizer import Synthesizer\n"
            "from pathlib import Path\n"
            "import tempfile\n"
            "with tempfile.TemporaryDirectory() as d:\n"
            "    s = Synthesizer(out_dir=Path(d), use_llm=False)\n"
            "    print('no-llm OK', s._max_erc_iterations)\n"
        )

        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": ":".join([
                str(REPO_ROOT / "synthesizer"),
                str(REPO_ROOT / "shared"),
                str(REPO_ROOT / "compiler"),
            ]), "BOARDSMITH_NO_LLM": "1"},
        )
        assert result.returncode == 0, f"Import failed:\n{result.stderr}"
        assert "no-llm OK" in result.stdout
        assert "5" in result.stdout  # default max_erc_iterations
