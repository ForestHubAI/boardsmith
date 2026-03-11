# SPDX-License-Identifier: AGPL-3.0-or-later
"""Task → Provider/Model routing table.

Each task type has an ordered list of (provider_name, model) tuples.
The gateway tries them in order and uses the first available provider.
"""

from __future__ import annotations

from .types import TaskType

# Routing table: task → [(provider, model), ...]
# Order = priority. First available provider wins.
ROUTING_TABLE: dict[str, list[tuple[str, str]]] = {
    TaskType.INTENT_PARSE: [
        ("anthropic", "claude-haiku-4-5-20251001"),
        ("openai", "gpt-4o-mini"),
        ("ollama", "llama3.2"),
    ],
    TaskType.COMPONENT_SUGGEST: [
        ("anthropic", "claude-sonnet-4-5"),
        ("openai", "gpt-4o"),
    ],
    TaskType.TOPOLOGY_SUGGEST: [
        ("anthropic", "claude-sonnet-4-5"),
        ("openai", "gpt-4o"),
    ],
    TaskType.CONSTRAINT_FIX: [
        ("anthropic", "claude-sonnet-4-5"),
        ("openai", "gpt-4o"),
    ],
    TaskType.LAYOUT_PLAN: [
        ("anthropic", "claude-sonnet-4-5"),
        ("openai", "gpt-4o"),
    ],
    TaskType.CODE_GEN: [
        ("openai", "gpt-4o"),
        ("anthropic", "claude-sonnet-4-5"),
    ],
    TaskType.DATASHEET_EXTRACT: [
        ("openai", "gpt-4o"),
        ("anthropic", "claude-sonnet-4-5"),
    ],
    TaskType.AGENT_REASONING: [
        ("anthropic", "claude-sonnet-4-5"),
        ("openai", "gpt-4o"),
        ("ollama", "llama3.2"),
    ],
}

# Fallback if task not in table
_DEFAULT_CHAIN: list[tuple[str, str]] = [
    ("anthropic", "claude-haiku-4-5-20251001"),
    ("openai", "gpt-4o-mini"),
]


def get_provider_chain(task: str) -> list[tuple[str, str]]:
    """Return the ordered (provider, model) chain for a task."""
    return ROUTING_TABLE.get(task, _DEFAULT_CHAIN)
