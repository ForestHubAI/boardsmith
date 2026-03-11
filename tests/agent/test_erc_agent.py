# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for ERCAgent — Phase 08-01.

RED phase: written before implementation.

Run:
    PYTHONPATH=synthesizer:shared:compiler pytest tests/agent/test_erc_agent.py -x -v
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
# Task 1: _violation_fingerprint() and ERCAgentResult
# ---------------------------------------------------------------------------


class TestViolationFingerprint:
    """_violation_fingerprint() produces deterministic sha256 hashes."""

    def test_empty_violations_deterministic(self):
        """Empty violation list always returns same hash."""
        from boardsmith_hw.agent.erc_agent import _violation_fingerprint

        fp1 = _violation_fingerprint([])
        fp2 = _violation_fingerprint([])
        assert fp1 == fp2
        assert len(fp1) == 64  # sha256 hex

    def test_warnings_excluded_from_fingerprint(self):
        """Warning-severity violations do not affect fingerprint."""
        from boardsmith_hw.agent.erc_agent import _violation_fingerprint

        fp_errors_only = _violation_fingerprint([
            {"severity": "error", "message": "A", "rule_id": "R1"},
        ])
        fp_errors_and_warnings = _violation_fingerprint([
            {"severity": "error", "message": "A", "rule_id": "R1"},
            {"severity": "warning", "message": "W", "rule_id": "RW"},
        ])
        assert fp_errors_only == fp_errors_and_warnings

    def test_order_independent(self):
        """Same error violations in different order produce same fingerprint."""
        from boardsmith_hw.agent.erc_agent import _violation_fingerprint

        v1 = {"severity": "error", "message": "B", "rule_id": "R2"}
        v2 = {"severity": "error", "message": "A", "rule_id": "R1"}
        assert _violation_fingerprint([v1, v2]) == _violation_fingerprint([v2, v1])

    def test_different_error_sets_differ(self):
        """Different error violations produce different fingerprints."""
        from boardsmith_hw.agent.erc_agent import _violation_fingerprint

        fp1 = _violation_fingerprint([{"severity": "error", "message": "A", "rule_id": "R1"}])
        fp2 = _violation_fingerprint([{"severity": "error", "message": "B", "rule_id": "R2"}])
        assert fp1 != fp2

    def test_warning_only_matches_empty(self):
        """A list with only warnings should hash the same as an empty list."""
        from boardsmith_hw.agent.erc_agent import _violation_fingerprint

        fp_empty = _violation_fingerprint([])
        fp_warn_only = _violation_fingerprint([{"severity": "warning", "message": "W"}])
        assert fp_empty == fp_warn_only


class TestERCAgentResult:
    """ERCAgentResult dataclass — is_clean property and summary_message."""

    def test_is_clean_true_when_no_violations(self):
        from boardsmith_hw.agent.erc_agent import ERCAgentResult

        r = ERCAgentResult(violations=[], iterations_used=0)
        assert r.is_clean is True

    def test_is_clean_false_when_violations_present(self):
        from boardsmith_hw.agent.erc_agent import ERCAgentResult

        r = ERCAgentResult(violations=[{"message": "err", "severity": "error"}], iterations_used=1)
        assert r.is_clean is False

    def test_summary_message_clean(self):
        from boardsmith_hw.agent.erc_agent import ERCAgentResult

        r = ERCAgentResult(violations=[], iterations_used=1)
        assert r.summary_message == "ERC agent: all violations resolved"

    def test_summary_message_stalled(self):
        from boardsmith_hw.agent.erc_agent import ERCAgentResult

        r = ERCAgentResult(
            violations=[{"message": "no pull-up", "severity": "error"}],
            iterations_used=2,
            stalled=True,
        )
        assert "stalled" in r.summary_message
        assert r.summary_message == "ERC agent stalled: same violations in 2 consecutive iterations"

    def test_summary_message_with_violations(self):
        from boardsmith_hw.agent.erc_agent import ERCAgentResult

        r = ERCAgentResult(
            violations=[
                {"message": "msg1", "severity": "error"},
                {"message": "msg2", "severity": "error"},
            ],
            iterations_used=5,
            cap_hit=True,
        )
        assert "2 ERC violations remain" in r.summary_message
        assert "[msg1]" in r.summary_message
        assert "[msg2]" in r.summary_message

    def test_default_stalled_false(self):
        from boardsmith_hw.agent.erc_agent import ERCAgentResult

        r = ERCAgentResult(violations=[], iterations_used=0)
        assert r.stalled is False
        assert r.cap_hit is False

    def test_sch_path_default_none(self):
        from boardsmith_hw.agent.erc_agent import ERCAgentResult

        r = ERCAgentResult(violations=[], iterations_used=0)
        assert r.sch_path is None


# ---------------------------------------------------------------------------
# Task 2: ERCAgent.run()
# ---------------------------------------------------------------------------


def _make_agent(violations_sequence, max_iterations=5):
    """Build ERCAgent with mocked dispatcher and gateway.

    violations_sequence: list returned for each _run_erc_via_tool() call.
    The mock cycles through this sequence; after it's exhausted returns the last value.
    """
    from boardsmith_hw.agent.erc_agent import ERCAgent

    # Build a mock ToolDispatcher — dispatch() is async in the real one,
    # but ERCAgent._run_erc_via_tool uses its own sync wrapper.
    # We mock _run_erc_via_tool and _request_fix directly on the instance.
    sch_path = Path("/tmp/test.kicad_sch")
    gateway = MagicMock()
    dispatcher = MagicMock()
    agent = ERCAgent(sch_path=sch_path, gateway=gateway, dispatcher=dispatcher,
                     max_iterations=max_iterations)

    # sequence iterator
    seq = iter(violations_sequence)

    def _next_violations():
        try:
            return next(seq)
        except StopIteration:
            return violations_sequence[-1]

    agent._run_erc_via_tool = _next_violations
    # _request_fix is a no-op mock — just returns messages unchanged
    agent._request_fix = lambda violations, messages: messages

    return agent


class TestERCAgentRun:
    """ERCAgent.run() loop — stall, cap, clean."""

    def test_clean_first_run_no_violations(self):
        """Zero violations on first check → is_clean=True, iterations_used=0."""
        agent = _make_agent([[]])  # first ERC returns no violations
        result = agent.run()
        assert result.is_clean is True
        assert result.iterations_used == 0

    def test_clean_after_one_iteration(self):
        """Violations on first check, clean on second → is_clean=True, iterations_used=1."""
        agent = _make_agent([
            [{"severity": "error", "message": "A", "rule_id": "R1"}],  # iteration 1
            [],  # after fix
        ])
        result = agent.run()
        assert result.is_clean is True
        assert result.iterations_used == 1

    def test_stall_detection(self):
        """Same fingerprint twice → stalled=True; exits before max_iterations."""
        same_violations = [{"severity": "error", "message": "A", "rule_id": "R1"}]
        agent = _make_agent([
            same_violations,  # initial check
            same_violations,  # iteration 1 → checks fingerprint at top of loop
            same_violations,  # iteration 2 → same fingerprint → stall
        ], max_iterations=5)
        result = agent.run()
        assert result.stalled is True
        assert result.iterations_used < 5  # exits early

    def test_cap_hit(self):
        """Never clean, never stalled → cap_hit=True after max_iterations."""
        # Use different violation messages each time to avoid stall detection.
        import itertools
        counter = itertools.count(1)

        agent = _make_agent([[]], max_iterations=3)

        call_n = [0]

        def _varying_violations():
            call_n[0] += 1
            # Return different violation each call to avoid stall
            return [{"severity": "error", "message": f"err-{call_n[0]}", "rule_id": f"R{call_n[0]}"}]

        agent._run_erc_via_tool = _varying_violations
        result = agent.run()
        assert result.cap_hit is True
        assert result.iterations_used == 3

    def test_never_raises(self):
        """run() catches all exceptions and returns ERCAgentResult with cap_hit=True."""
        from boardsmith_hw.agent.erc_agent import ERCAgent

        sch_path = Path("/tmp/test.kicad_sch")
        agent = ERCAgent(sch_path=sch_path, gateway=MagicMock(), dispatcher=MagicMock())

        def _boom():
            raise RuntimeError("kicad-cli crashed")

        agent._run_erc_via_tool = _boom
        result = agent.run()
        assert result.cap_hit is True
        assert any("kicad-cli crashed" in v.get("message", "") for v in result.violations)

    def test_progress_written_to_stderr(self, capsys):
        """Progress 'ERC iteration N/max' is written to stderr each iteration."""
        agent = _make_agent([
            [{"severity": "error", "message": "A", "rule_id": "R1"}],
            [],  # clean after 1 iteration
        ], max_iterations=5)
        agent.run()
        captured = capsys.readouterr()
        assert "ERC iteration 1/5" in captured.err

    def test_request_fix_called_at_most_max_iterations(self):
        """_request_fix() is called at most max_iterations times."""
        call_count = [0]
        orig_violations = [
            [{"severity": "error", "message": f"e{i}", "rule_id": f"R{i}"}]
            for i in range(10)
        ]

        agent = _make_agent([[]], max_iterations=3)

        call_n = [0]

        def _varying():
            call_n[0] += 1
            return [{"severity": "error", "message": f"err-{call_n[0]}", "rule_id": f"R{call_n[0]}"}]

        def _count_fix(violations, messages):
            call_count[0] += 1
            return messages

        agent._run_erc_via_tool = _varying
        agent._request_fix = _count_fix

        agent.run()
        assert call_count[0] <= 3


class TestImportClean:
    """BOARDSMITH_NO_LLM=1 import must not import anthropic or any LLM package."""

    def test_import_clean_no_llm(self):
        """Import erc_agent with BOARDSMITH_NO_LLM=1 — no LLM side-effects."""
        import subprocess

        result = subprocess.run(
            [sys.executable, "-c",
             "import os; os.environ['BOARDSMITH_NO_LLM'] = '1'; "
             "from boardsmith_hw.agent.erc_agent import ERCAgentResult, _violation_fingerprint; "
             "print('OK')"],
            capture_output=True,
            text=True,
            env={**__import__("os").environ, "PYTHONPATH": ":".join([
                str(REPO_ROOT / "synthesizer"),
                str(REPO_ROOT / "shared"),
                str(REPO_ROOT / "compiler"),
            ]), "BOARDSMITH_NO_LLM": "1"},
        )
        assert result.returncode == 0, f"Import failed:\n{result.stderr}"
        assert "OK" in result.stdout


# ---------------------------------------------------------------------------
# Phase 08-03: Additional unit tests using patch.object mocking pattern
# Tests use pytest fixtures and patch at _run_erc_via_tool / _request_fix level
# ---------------------------------------------------------------------------

PULL_UP = {"message": "Pin SDA has no pull-up", "severity": "error", "rule_id": "pin_unc", "fixable": True}
PWR_FLAG = {"message": "Power flag missing on VCC", "severity": "error", "rule_id": "pwr_flag", "fixable": True}
WARN = {"message": "Footprint mismatch", "severity": "warning", "rule_id": "fp_warn", "fixable": False}


@pytest.fixture
def agent(tmp_path):
    from boardsmith_hw.agent.erc_agent import ERCAgent

    sch = tmp_path / "test.kicad_sch"
    sch.write_text("(kicad_sch)")
    return ERCAgent(
        sch_path=sch,
        gateway=MagicMock(),
        dispatcher=MagicMock(),
        max_iterations=5,
    )


def test_fingerprint_excludes_warnings(agent):
    """fingerprint([PULL_UP, WARN]) == fingerprint([PULL_UP]): warnings don't affect fp."""
    from boardsmith_hw.agent.erc_agent import _violation_fingerprint

    assert _violation_fingerprint([PULL_UP, WARN]) == _violation_fingerprint([PULL_UP])


def test_fingerprint_is_order_independent(agent):
    """fingerprint([PULL_UP, PWR_FLAG]) == fingerprint([PWR_FLAG, PULL_UP])."""
    from boardsmith_hw.agent.erc_agent import _violation_fingerprint

    assert _violation_fingerprint([PULL_UP, PWR_FLAG]) == _violation_fingerprint([PWR_FLAG, PULL_UP])


def test_fingerprint_differs_on_different_violations(agent):
    """fingerprint([PULL_UP]) != fingerprint([PWR_FLAG])."""
    from boardsmith_hw.agent.erc_agent import _violation_fingerprint

    assert _violation_fingerprint([PULL_UP]) != _violation_fingerprint([PWR_FLAG])


def test_clean_on_first_erc_call(agent):
    """When _run_erc_via_tool returns [], run() is clean without calling _request_fix."""
    with patch.object(agent, "_run_erc_via_tool", return_value=[]) as mock_erc, \
         patch.object(agent, "_request_fix", return_value=[]) as mock_fix:
        result = agent.run()

    assert result.is_clean is True
    assert result.iterations_used == 0
    mock_erc.assert_called_once()
    mock_fix.assert_not_called()


def test_resolves_on_second_iteration(agent):
    """First ERC returns [PULL_UP], second returns [] → is_clean=True, iterations_used=1."""
    with patch.object(agent, "_run_erc_via_tool", side_effect=[[PULL_UP], []]) as mock_erc, \
         patch.object(agent, "_request_fix", return_value=[]) as mock_fix:
        result = agent.run()

    assert result.is_clean is True
    assert result.iterations_used == 1
    assert mock_fix.call_count == 1


def test_stall_detection_stops_loop(agent):
    """Same fingerprint on two consecutive iterations → stalled=True, _request_fix called once."""
    # _run_erc_via_tool always returns [PULL_UP] (same fingerprint every call)
    with patch.object(agent, "_run_erc_via_tool", return_value=[PULL_UP]) as mock_erc, \
         patch.object(agent, "_request_fix", return_value=[]) as mock_fix:
        result = agent.run()

    assert result.stalled is True
    # Stall detected at start of iteration 2 before fix; _request_fix called exactly once
    assert mock_fix.call_count == 1
    # iterations_used is the iteration counter when stall was detected (2)
    assert result.iterations_used == 2


def test_cap_hit_after_max_iterations():
    """max_iterations=3, alternating violations (never stalls, never clean) → cap_hit=True."""
    from boardsmith_hw.agent.erc_agent import ERCAgent

    agent_cap = ERCAgent(
        sch_path=Path("/tmp/cap.kicad_sch"),
        gateway=MagicMock(),
        dispatcher=MagicMock(),
        max_iterations=3,
    )
    # Alternate PULL_UP / PWR_FLAG so fingerprint always differs (no stall)
    # Need 4 calls: initial + 3 post-fix calls, all returning violations
    with patch.object(agent_cap, "_run_erc_via_tool",
                      side_effect=[[PULL_UP], [PWR_FLAG], [PULL_UP], [PWR_FLAG]]) as mock_erc, \
         patch.object(agent_cap, "_request_fix", return_value=[]) as mock_fix:
        result = agent_cap.run()

    assert result.cap_hit is True
    # _request_fix called exactly 3 times (once per iteration, cap=3)
    assert mock_fix.call_count == 3


def test_cap_summary_contains_violation_messages():
    """After cap hit with two violations, summary_message contains both message strings."""
    from boardsmith_hw.agent.erc_agent import ERCAgentResult

    r = ERCAgentResult(
        violations=[PULL_UP, PWR_FLAG],
        iterations_used=3,
        cap_hit=True,
    )
    assert "Pin SDA has no pull-up" in r.summary_message
    assert "Power flag missing on VCC" in r.summary_message


def test_stall_summary_message(agent):
    """Stalled result summary_message contains 'stalled' and 'same violations'."""
    with patch.object(agent, "_run_erc_via_tool", return_value=[PULL_UP]), \
         patch.object(agent, "_request_fix", return_value=[]):
        result = agent.run()

    assert "stalled" in result.summary_message
    assert "same violations" in result.summary_message


def test_progress_written_to_stderr(agent, capsys):
    """'ERC iteration 1/' and 'errors remain' appear in stderr output."""
    with patch.object(agent, "_run_erc_via_tool", side_effect=[[PULL_UP], []]), \
         patch.object(agent, "_request_fix", return_value=[]):
        agent.run()

    err = capsys.readouterr().err
    assert "ERC iteration 1/" in err
    assert "errors remain" in err


def test_exception_in_run_erc_returns_result_not_traceback(agent):
    """If _run_erc_via_tool raises, run() returns ERCAgentResult (never re-raises)."""
    with patch.object(agent, "_run_erc_via_tool", side_effect=RuntimeError("kicad-cli not found")), \
         patch.object(agent, "_request_fix", return_value=[]):
        result = agent.run()

    assert not isinstance(result, Exception)
    # cap_hit or stalled must be True (exception path sets cap_hit=True)
    assert result.cap_hit is True
    # The exception message must appear in violations
    assert any("kicad-cli not found" in v.get("message", "") for v in result.violations)


def test_write_patch_not_called_more_than_max_iterations():
    """With max_iterations=2, _request_fix is called at most 2 times."""
    from boardsmith_hw.agent.erc_agent import ERCAgent

    agent_two = ERCAgent(
        sch_path=Path("/tmp/two.kicad_sch"),
        gateway=MagicMock(),
        dispatcher=MagicMock(),
        max_iterations=2,
    )
    # Alternate to avoid stall; need 3 calls (initial + 2 post-fix)
    with patch.object(agent_two, "_run_erc_via_tool",
                      side_effect=[[PULL_UP], [PWR_FLAG], [PULL_UP]]) as mock_erc, \
         patch.object(agent_two, "_request_fix", return_value=[]) as mock_fix:
        agent_two.run()

    assert mock_fix.call_count <= 2
