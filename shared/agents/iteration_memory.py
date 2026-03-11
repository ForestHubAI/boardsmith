# SPDX-License-Identifier: AGPL-3.0-or-later
"""IterationMemory — Phase 21: cross-iteration state for the agentic loop.

Prevents fix oscillation by tracking:
  - Which issue codes have been seen and when
  - Which fixes have been applied (to avoid re-applying the same fix)
  - Which issues persist across multiple iterations (chronic vs. transient)

Used by IterativeOrchestrator to give DesignImprover context about what
has already been tried, and to surface "stuck" issues to the user.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IssueHistory:
    """Per-issue-code tracking across iterations."""

    code: str
    first_seen_iteration: int
    last_seen_iteration: int
    times_seen: int = 1
    times_fix_attempted: int = 0
    resolved: bool = False


@dataclass
class IterationMemory:
    """Tracks issue + fix history across the full agentic build loop.

    Usage::

        memory = IterationMemory()

        # After each review:
        memory.record_issues(iteration=1, issue_codes=["OVERCURRENT", "MISSING_INIT"])

        # After applying fixes:
        memory.record_fixes(iteration=1, fix_codes=["OVERCURRENT"])

        # Before next iteration's improvement pass:
        skippable = memory.already_fixed_codes()   # codes tried already
        persistent = memory.persistent_issues(min_iterations=2)
    """

    _history: dict[str, IssueHistory] = field(default_factory=dict)
    _fixes_applied: list[tuple[int, str]] = field(default_factory=list)  # (iter, code)

    def record_issues(self, iteration: int, issue_codes: list[str]) -> None:
        """Record which issue codes were found in this iteration."""
        for code in issue_codes:
            if code in self._history:
                h = self._history[code]
                h.last_seen_iteration = iteration
                h.times_seen += 1
                h.resolved = False
            else:
                self._history[code] = IssueHistory(
                    code=code,
                    first_seen_iteration=iteration,
                    last_seen_iteration=iteration,
                )

        # Mark anything NOT seen this iteration as potentially resolved
        for code, h in self._history.items():
            if code not in issue_codes and h.last_seen_iteration < iteration:
                h.resolved = True

    def record_fixes(self, iteration: int, fix_codes: list[str]) -> None:
        """Record which issue codes had fix attempts applied this iteration."""
        for code in fix_codes:
            self._fixes_applied.append((iteration, code))
            if code in self._history:
                self._history[code].times_fix_attempted += 1

    def already_fixed_codes(self) -> set[str]:
        """Return the set of issue codes for which a fix has already been tried."""
        return {code for _, code in self._fixes_applied}

    def persistent_issues(self, min_iterations: int = 2) -> list[IssueHistory]:
        """Return issues that have appeared in at least min_iterations iterations."""
        return [
            h for h in self._history.values()
            if h.times_seen >= min_iterations and not h.resolved
        ]

    def resolved_issues(self) -> list[IssueHistory]:
        """Return issues that appear to be resolved (not seen in last iteration)."""
        return [h for h in self._history.values() if h.resolved]

    def summary(self, current_iteration: int) -> dict[str, Any]:
        """Return a JSON-serializable summary for the audit trail."""
        return {
            "current_iteration": current_iteration,
            "total_unique_issues": len(self._history),
            "resolved": len(self.resolved_issues()),
            "persistent": len(self.persistent_issues()),
            "fix_attempts": len(self._fixes_applied),
            "issue_history": [
                {
                    "code": h.code,
                    "first_seen": h.first_seen_iteration,
                    "last_seen": h.last_seen_iteration,
                    "times_seen": h.times_seen,
                    "times_fixed": h.times_fix_attempted,
                    "resolved": h.resolved,
                }
                for h in sorted(self._history.values(), key=lambda x: x.first_seen_iteration)
            ],
        }

    def chronic_issue_codes(self, min_fix_attempts: int = 2) -> list[str]:
        """Return codes of issues that have resisted multiple fix attempts.

        These are 'stuck' issues that may need human intervention.
        """
        return [
            h.code
            for h in self._history.values()
            if h.times_fix_attempted >= min_fix_attempts and not h.resolved
        ]
