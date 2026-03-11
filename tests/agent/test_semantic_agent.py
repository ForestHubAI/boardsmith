# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for SemanticVerificationAgent — Phase 11-01.

RED phase: written before implementation.

Run:
    PYTHONPATH=synthesizer:shared:compiler pytest tests/agent/test_semantic_agent.py -x -v
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
# Violation constants — use `type` field (not `rule_id`)
# ---------------------------------------------------------------------------

MISSING_COMP = {
    "type": "missing_component",
    "severity": "error",
    "message": "HIR component 'ESP32' not found",
    "ref": "U1",
}
MISSING_BUS = {
    "type": "missing_bus_net",
    "severity": "error",
    "message": "Net 'SDA' for I2C bus not found",
    "ref": "I2C_BUS",
}
MISSING_PWR = {
    "type": "missing_power_rail",
    "severity": "error",
    "message": "3.3V rail has no regulator",
    "ref": "VREG",
}
WARN = {
    "type": "missing_decoupling_cap",
    "severity": "warning",
    "message": "No 100nF decoupling caps found",
}


# ---------------------------------------------------------------------------
# Helper: _make_agent
# ---------------------------------------------------------------------------


def _make_agent(violations_sequence, max_iterations=5):
    """Build SemanticVerificationAgent with mocked dispatcher and gateway.

    violations_sequence: list returned for each _run_verification_via_tools() call.
    The mock cycles through this sequence; after it's exhausted returns the last value.
    """
    from boardsmith_hw.agent.semantic_agent import SemanticVerificationAgent

    sch_path = Path("/tmp/test.kicad_sch")
    hir_path = Path("/tmp/hir.json")
    gateway = MagicMock()
    dispatcher = MagicMock()
    agent = SemanticVerificationAgent(
        sch_path=sch_path,
        hir_path=hir_path,
        gateway=gateway,
        dispatcher=dispatcher,
        max_iterations=max_iterations,
    )

    seq = iter(violations_sequence)

    def _next_violations():
        try:
            return next(seq)
        except StopIteration:
            return violations_sequence[-1]

    agent._run_verification_via_tools = _next_violations
    agent._request_fix = lambda violations, messages: messages

    return agent


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def agent(tmp_path):
    from boardsmith_hw.agent.semantic_agent import SemanticVerificationAgent

    sch = tmp_path / "test.kicad_sch"
    hir = tmp_path / "hir.json"
    sch.write_text("(kicad_sch)")
    hir.write_text("{}")
    return SemanticVerificationAgent(
        sch_path=sch,
        hir_path=hir,
        gateway=MagicMock(),
        dispatcher=MagicMock(),
        max_iterations=5,
    )


# ---------------------------------------------------------------------------
# TestViolationFingerprint
# ---------------------------------------------------------------------------


class TestViolationFingerprint:
    """_violation_fingerprint() produces deterministic sha256 hashes."""

    def test_empty_violations_deterministic(self):
        """Empty violation list always returns same hash."""
        from boardsmith_hw.agent.semantic_agent import _violation_fingerprint

        fp1 = _violation_fingerprint([])
        fp2 = _violation_fingerprint([])
        assert fp1 == fp2
        assert len(fp1) == 64  # sha256 hex

    def test_warnings_excluded(self):
        """Warning-severity violations do not affect fingerprint."""
        from boardsmith_hw.agent.semantic_agent import _violation_fingerprint

        fp_errors_only = _violation_fingerprint([MISSING_COMP])
        fp_errors_and_warnings = _violation_fingerprint([MISSING_COMP, WARN])
        assert fp_errors_only == fp_errors_and_warnings

    def test_order_independent(self):
        """Same error violations in different order produce same fingerprint."""
        from boardsmith_hw.agent.semantic_agent import _violation_fingerprint

        assert _violation_fingerprint([MISSING_COMP, MISSING_BUS]) == _violation_fingerprint(
            [MISSING_BUS, MISSING_COMP]
        )

    def test_different_error_sets_differ(self):
        """Different error violations produce different fingerprints."""
        from boardsmith_hw.agent.semantic_agent import _violation_fingerprint

        fp1 = _violation_fingerprint([MISSING_COMP])
        fp2 = _violation_fingerprint([MISSING_BUS])
        assert fp1 != fp2

    def test_type_field_used_not_rule_id(self):
        """Violations with same message but different type produce DIFFERENT fingerprints.

        This validates that `type` is the sort key, not `rule_id`.
        """
        from boardsmith_hw.agent.semantic_agent import _violation_fingerprint

        v_a = {"type": "a", "severity": "error", "message": "same"}
        v_b = {"type": "b", "severity": "error", "message": "same"}
        fp_a = _violation_fingerprint([v_a])
        fp_b = _violation_fingerprint([v_b])
        assert fp_a != fp_b

    def test_combined_violations_fingerprint(self):
        """Violations from two tool outputs combined fingerprint same as when merged before hashing."""
        from boardsmith_hw.agent.semantic_agent import _violation_fingerprint

        group1 = [MISSING_COMP]
        group2 = [MISSING_BUS]
        combined = group1 + group2
        fp_combined = _violation_fingerprint(combined)
        fp_merged = _violation_fingerprint([MISSING_COMP, MISSING_BUS])
        assert fp_combined == fp_merged


# ---------------------------------------------------------------------------
# TestSemanticAgentResult
# ---------------------------------------------------------------------------


class TestSemanticAgentResult:
    """SemanticAgentResult dataclass — is_clean property and summary_message."""

    def test_is_clean_true_when_no_violations(self):
        from boardsmith_hw.agent.semantic_agent import SemanticAgentResult

        r = SemanticAgentResult(violations=[], iterations_used=0)
        assert r.is_clean is True

    def test_is_clean_false_when_violations_present(self):
        from boardsmith_hw.agent.semantic_agent import SemanticAgentResult

        r = SemanticAgentResult(violations=[MISSING_COMP], iterations_used=1)
        assert r.is_clean is False

    def test_summary_message_clean(self):
        from boardsmith_hw.agent.semantic_agent import SemanticAgentResult

        r = SemanticAgentResult(violations=[], iterations_used=1)
        assert r.summary_message == "Semantic agent: all violations resolved"

    def test_summary_message_stalled(self):
        from boardsmith_hw.agent.semantic_agent import SemanticAgentResult

        r = SemanticAgentResult(
            violations=[MISSING_COMP],
            iterations_used=2,
            stalled=True,
        )
        assert r.summary_message == "Semantic agent stalled: same violations in 2 consecutive iterations"

    def test_summary_message_cap_hit(self):
        from boardsmith_hw.agent.semantic_agent import SemanticAgentResult

        r = SemanticAgentResult(
            violations=[MISSING_COMP, MISSING_BUS],
            iterations_used=3,
            cap_hit=True,
        )
        assert "2 violations remain" in r.summary_message
        assert "HIR component 'ESP32' not found" in r.summary_message
        assert "Net 'SDA' for I2C bus not found" in r.summary_message

    def test_default_stalled_false(self):
        from boardsmith_hw.agent.semantic_agent import SemanticAgentResult

        r = SemanticAgentResult(violations=[], iterations_used=0)
        assert r.stalled is False
        assert r.cap_hit is False

    def test_sch_path_default_none(self):
        from boardsmith_hw.agent.semantic_agent import SemanticAgentResult

        r = SemanticAgentResult(violations=[], iterations_used=0)
        assert r.sch_path is None


# ---------------------------------------------------------------------------
# TestSemanticAgentRun
# ---------------------------------------------------------------------------


class TestSemanticAgentRun:
    """SemanticVerificationAgent.run() loop — stall, cap, clean."""

    def test_clean_first_run_no_violations(self):
        """Zero violations on first check → is_clean=True, iterations_used=0."""
        agent = _make_agent([[]])
        result = agent.run()
        assert result.is_clean is True
        assert result.iterations_used == 0

    def test_clean_after_one_iteration(self):
        """Violations on first check, clean on second → is_clean=True, iterations_used=1."""
        agent = _make_agent([
            [MISSING_COMP],  # iteration 1
            [],              # after fix
        ])
        result = agent.run()
        assert result.is_clean is True
        assert result.iterations_used == 1

    def test_stall_detection(self):
        """Same fingerprint twice → stalled=True; exits before max_iterations."""
        same_violations = [MISSING_COMP]
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
        agent = _make_agent([[]], max_iterations=3)

        call_n = [0]

        def _varying_violations():
            call_n[0] += 1
            return [{"type": f"type_{call_n[0]}", "severity": "error",
                     "message": f"err-{call_n[0]}"}]

        agent._run_verification_via_tools = _varying_violations
        result = agent.run()
        assert result.cap_hit is True
        assert result.iterations_used == 3

    def test_never_raises(self):
        """run() catches all exceptions and returns SemanticAgentResult with cap_hit=True."""
        from boardsmith_hw.agent.semantic_agent import SemanticVerificationAgent

        agent = SemanticVerificationAgent(
            sch_path=Path("/tmp/test.kicad_sch"),
            hir_path=Path("/tmp/hir.json"),
            gateway=MagicMock(),
            dispatcher=MagicMock(),
        )

        def _boom():
            raise RuntimeError("tool crashed")

        agent._run_verification_via_tools = _boom
        result = agent.run()
        assert result.cap_hit is True
        assert any("tool crashed" in v.get("message", "") for v in result.violations)

    def test_progress_written_to_stderr(self, capsys, monkeypatch):
        """Progress 'Semantic iteration N/max' is written to stderr when BOARDSMITH_VERBOSE is set."""
        monkeypatch.setenv("BOARDSMITH_VERBOSE", "1")
        agent = _make_agent([
            [MISSING_COMP],
            [],  # clean after 1 iteration
        ], max_iterations=5)
        agent.run()
        captured = capsys.readouterr()
        assert "Semantic iteration 1/5" in captured.err


# ---------------------------------------------------------------------------
# Module-level tests using patch.object (same pattern as Phase 08-03)
# ---------------------------------------------------------------------------


def test_fingerprint_excludes_warnings(agent):
    """fingerprint([MISSING_COMP, WARN]) == fingerprint([MISSING_COMP])."""
    from boardsmith_hw.agent.semantic_agent import _violation_fingerprint

    assert _violation_fingerprint([MISSING_COMP, WARN]) == _violation_fingerprint([MISSING_COMP])


def test_fingerprint_is_order_independent(agent):
    """fingerprint([MISSING_COMP, MISSING_BUS]) == fingerprint([MISSING_BUS, MISSING_COMP])."""
    from boardsmith_hw.agent.semantic_agent import _violation_fingerprint

    assert _violation_fingerprint([MISSING_COMP, MISSING_BUS]) == _violation_fingerprint(
        [MISSING_BUS, MISSING_COMP]
    )


def test_stall_detection_stops_loop(agent):
    """Same fingerprint on two consecutive iterations → stalled=True, _request_fix called once."""
    with patch.object(agent, "_run_verification_via_tools", return_value=[MISSING_COMP]) as mock_verif, \
         patch.object(agent, "_request_fix", return_value=[]) as mock_fix:
        result = agent.run()

    assert result.stalled is True
    assert mock_fix.call_count == 1
    assert result.iterations_used == 2


def test_cap_hit_after_max_iterations():
    """max_iterations=3, alternating violations (never stalls, never clean) → cap_hit=True."""
    from boardsmith_hw.agent.semantic_agent import SemanticVerificationAgent

    agent_cap = SemanticVerificationAgent(
        sch_path=Path("/tmp/cap.kicad_sch"),
        hir_path=Path("/tmp/cap_hir.json"),
        gateway=MagicMock(),
        dispatcher=MagicMock(),
        max_iterations=3,
    )
    with patch.object(
        agent_cap,
        "_run_verification_via_tools",
        side_effect=[[MISSING_COMP], [MISSING_BUS], [MISSING_COMP], [MISSING_BUS]],
    ) as mock_verif, \
         patch.object(agent_cap, "_request_fix", return_value=[]) as mock_fix:
        result = agent_cap.run()

    assert result.cap_hit is True
    assert mock_fix.call_count == 3


def test_clean_on_first_verification_call(agent):
    """When _run_verification_via_tools returns [], run() is clean without calling _request_fix."""
    with patch.object(agent, "_run_verification_via_tools", return_value=[]) as mock_verif, \
         patch.object(agent, "_request_fix", return_value=[]) as mock_fix:
        result = agent.run()

    assert result.is_clean is True
    assert result.iterations_used == 0
    mock_verif.assert_called_once()
    mock_fix.assert_not_called()


def test_resolves_on_second_iteration(agent):
    """First verification returns [MISSING_COMP], second returns [] → is_clean=True, iterations_used=1."""
    with patch.object(
        agent, "_run_verification_via_tools", side_effect=[[MISSING_COMP], []]
    ) as mock_verif, \
         patch.object(agent, "_request_fix", return_value=[]) as mock_fix:
        result = agent.run()

    assert result.is_clean is True
    assert result.iterations_used == 1
    assert mock_fix.call_count == 1


def test_exception_in_run_verification_returns_result_not_traceback(agent):
    """If _run_verification_via_tools raises, run() returns SemanticAgentResult (never re-raises)."""
    with patch.object(
        agent, "_run_verification_via_tools", side_effect=RuntimeError("tool not found")
    ), \
         patch.object(agent, "_request_fix", return_value=[]):
        result = agent.run()

    assert not isinstance(result, Exception)
    assert result.cap_hit is True
    assert any("tool not found" in v.get("message", "") for v in result.violations)


def test_write_patch_not_called_more_than_max_iterations():
    """With max_iterations=2, _request_fix is called at most 2 times."""
    from boardsmith_hw.agent.semantic_agent import SemanticVerificationAgent

    agent_two = SemanticVerificationAgent(
        sch_path=Path("/tmp/two.kicad_sch"),
        hir_path=Path("/tmp/two_hir.json"),
        gateway=MagicMock(),
        dispatcher=MagicMock(),
        max_iterations=2,
    )
    with patch.object(
        agent_two,
        "_run_verification_via_tools",
        side_effect=[[MISSING_COMP], [MISSING_BUS], [MISSING_COMP]],
    ) as mock_verif, \
         patch.object(agent_two, "_request_fix", return_value=[]) as mock_fix:
        agent_two.run()

    assert mock_fix.call_count <= 2


# ---------------------------------------------------------------------------
# TestImportClean
# ---------------------------------------------------------------------------


class TestImportClean:
    """BOARDSMITH_NO_LLM=1 import must not import anthropic or any LLM package."""

    def test_import_clean_no_llm(self):
        """Import semantic_agent with BOARDSMITH_NO_LLM=1 — no LLM side-effects."""
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os; os.environ['BOARDSMITH_NO_LLM'] = '1'; "
                "from boardsmith_hw.agent.semantic_agent import SemanticAgentResult, _violation_fingerprint; "
                "print('OK')",
            ],
            capture_output=True,
            text=True,
            env={
                **__import__("os").environ,
                "PYTHONPATH": ":".join([
                    str(REPO_ROOT / "synthesizer"),
                    str(REPO_ROOT / "shared"),
                    str(REPO_ROOT / "compiler"),
                ]),
                "BOARDSMITH_NO_LLM": "1",
            },
        )
        assert result.returncode == 0, f"Import failed:\n{result.stderr}"
        assert "OK" in result.stdout
