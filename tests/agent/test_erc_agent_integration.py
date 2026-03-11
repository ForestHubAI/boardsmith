# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration tests for ERCAgent — require live kicad-cli binary and LLM API key.

Marked @pytest.mark.integration. CI skips these unless BOARDSMITH_RUN_INTEGRATION=1.
Run locally:
  BOARDSMITH_RUN_INTEGRATION=1 PYTHONPATH=synthesizer:shared:compiler \
    pytest tests/agent/test_erc_agent_integration.py -v
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "synthesizer"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

INTEGRATION = pytest.mark.skipif(
    not os.environ.get("BOARDSMITH_RUN_INTEGRATION"),
    reason="Integration test: requires BOARDSMITH_RUN_INTEGRATION=1, live kicad-cli, and LLM API key",
)


@INTEGRATION
def test_erc_agent_resolves_missing_pwr_flag(tmp_path):
    """AGENT-01 80% success rate: ERCAgent resolves a missing PWR_FLAG violation.

    Uses a real .kicad_sch fixture with one injected PWR_FLAG violation.
    Requires:
      - kicad-cli in PATH
      - ANTHROPIC_API_KEY set (or OPENAI_API_KEY for fallback)
    """
    pytest.skip(
        "Scaffold only. Implement in v0.2 integration phase: "
        "copy a known-good .kicad_sch fixture, remove the PWR_FLAG symbol, "
        "run ERCAgent.run(), assert result.is_clean == True."
    )


@INTEGRATION
def test_erc_agent_resolves_unconnected_pin(tmp_path):
    """AGENT-01 80% success rate: ERCAgent resolves an unconnected pin violation."""
    pytest.skip(
        "Scaffold only. Implement: copy fixture schematic with deliberate unconnected pin, "
        "run ERCAgent, assert is_clean or violations reduced."
    )


@INTEGRATION
def test_erc_agent_stall_on_unfixable_violation(tmp_path):
    """AGENT-02: ERCAgent stalls cleanly when violation cannot be auto-fixed."""
    pytest.skip(
        "Scaffold only. Implement: use a fixture schematic with a complex ERC violation "
        "that the LLM cannot fix (e.g. missing library), assert result.stalled == True "
        "and result.summary_message contains 'stalled'."
    )


@INTEGRATION
def test_erc_agent_cap_summary_no_traceback(tmp_path, capsys):
    """AGENT-03: After 5 iterations without full resolution, output is plain-English."""
    pytest.skip(
        "Scaffold only. Implement: inject 3+ unfixable violations, run with max_iterations=2, "
        "assert no 'Traceback' in capsys stderr/stdout, assert result.cap_hit, "
        "assert violation messages appear in result.summary_message."
    )
