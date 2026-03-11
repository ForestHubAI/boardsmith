# SPDX-License-Identifier: AGPL-3.0-or-later
"""Token counting and cost tracking per session."""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import CostEntry, CostSummary


# Pricing per 1M tokens (as of early 2026)
_COST_PER_1M: dict[str, tuple[float, float]] = {
    # model: (input_per_1M, output_per_1M)
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-haiku-4-5": (0.80, 4.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "ollama": (0.00, 0.00),  # Local — free
}

_DEFAULT_COST = (2.50, 10.00)  # Conservative fallback


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a single LLM call."""
    inp_rate, out_rate = _COST_PER_1M.get(model, _DEFAULT_COST)
    return (input_tokens * inp_rate + output_tokens * out_rate) / 1_000_000


@dataclass
class CostTracker:
    """Tracks all LLM calls within a session."""

    _entries: list[CostEntry] = field(default_factory=list)

    def log(
        self,
        task: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Record an LLM call and return its USD cost."""
        cost = estimate_cost(model, input_tokens, output_tokens)
        self._entries.append(CostEntry(
            task=task,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        ))
        return cost

    def total_usd(self) -> float:
        return sum(e.cost_usd for e in self._entries)

    def total_tokens(self) -> int:
        return sum(e.input_tokens + e.output_tokens for e in self._entries)

    def is_over_budget(self, limit_usd: float) -> bool:
        return self.total_usd() >= limit_usd

    def get_summary(self) -> CostSummary:
        calls_by_task: dict[str, int] = {}
        calls_by_provider: dict[str, int] = {}
        cost_by_provider: dict[str, float] = {}

        for e in self._entries:
            calls_by_task[e.task] = calls_by_task.get(e.task, 0) + 1
            calls_by_provider[e.provider] = calls_by_provider.get(e.provider, 0) + 1
            cost_by_provider[e.provider] = cost_by_provider.get(e.provider, 0.0) + e.cost_usd

        return CostSummary(
            total_usd=self.total_usd(),
            total_tokens=self.total_tokens(),
            total_calls=len(self._entries),
            calls_by_task=calls_by_task,
            calls_by_provider=calls_by_provider,
            cost_by_provider=cost_by_provider,
        )

    def format_summary(self) -> str:
        s = self.get_summary()
        if s.total_calls == 0:
            return "LLM: keine Aufrufe"
        lines = [
            f"LLM: {s.total_calls} Aufrufe, {s.total_tokens:,} Tokens, ${s.total_usd:.4f}",
        ]
        for provider, cost in s.cost_by_provider.items():
            calls = s.calls_by_provider.get(provider, 0)
            lines.append(f"  {provider}: {calls} Aufrufe, ${cost:.4f}")
        return "\n".join(lines)
