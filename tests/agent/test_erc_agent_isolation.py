# SPDX-License-Identifier: AGPL-3.0-or-later
"""Isolation test: erc_agent.py is import-clean under BOARDSMITH_NO_LLM=1."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


SYNTHESIZER_DIR = str(Path(__file__).parent.parent.parent / "synthesizer")
SHARED_DIR = str(Path(__file__).parent.parent.parent / "shared")


def test_erc_agent_import_clean_no_llm():
    """BOARDSMITH_NO_LLM=1 must not cause ImportError when importing erc_agent."""
    env = {
        **os.environ,
        "BOARDSMITH_NO_LLM": "1",
        "PYTHONPATH": f"{SYNTHESIZER_DIR}:{SHARED_DIR}",
    }
    result = subprocess.run(
        [
            sys.executable, "-c",
            "from boardsmith_hw.agent import erc_agent; print('import clean')",
        ],
        env=env,
        capture_output=True,
        text=True,
        cwd=SYNTHESIZER_DIR,
    )
    assert result.returncode == 0, (
        f"Import failed under BOARDSMITH_NO_LLM=1:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "import clean" in result.stdout


def test_erc_agent_result_and_fingerprint_no_llm():
    """ERCAgentResult and _violation_fingerprint use only stdlib — must work without LLM."""
    env = {
        **os.environ,
        "BOARDSMITH_NO_LLM": "1",
        "PYTHONPATH": f"{SYNTHESIZER_DIR}:{SHARED_DIR}",
    }
    result = subprocess.run(
        [
            sys.executable, "-c",
            (
                "from boardsmith_hw.agent.erc_agent import ERCAgentResult, _violation_fingerprint; "
                "r = ERCAgentResult(violations=[], iterations_used=0); "
                "assert r.is_clean; "
                "fp = _violation_fingerprint([]); "
                "assert isinstance(fp, str) and len(fp) == 64; "
                "print('stdlib-only OK')"
            ),
        ],
        env=env,
        capture_output=True,
        text=True,
        cwd=SYNTHESIZER_DIR,
    )
    assert result.returncode == 0, (
        f"Stdlib-only test failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "stdlib-only OK" in result.stdout
