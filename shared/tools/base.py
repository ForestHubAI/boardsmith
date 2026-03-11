# SPDX-License-Identifier: AGPL-3.0-or-later
"""Base protocol and types for the Tool System."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from llm.gateway import LLMGateway


@dataclass
class ToolResult:
    """Standardized result from any tool execution."""

    success: bool
    data: Any
    source: str         # Provenance: "builtin_db", "octopart", "datasheet:SCD41", etc.
    confidence: float   # 0.0–1.0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolContext:
    """Shared context passed to every tool execution."""

    session_id: str
    llm_gateway: "LLMGateway"
    cache_dir: Path = field(default_factory=lambda: Path.home() / ".boardsmith" / "cache")
    budget_remaining_usd: float | None = None
    no_llm: bool = False

    def __post_init__(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)


@runtime_checkable
class Tool(Protocol):
    """Protocol that all tools must implement."""

    name: str
    description: str
    input_schema: dict  # JSON Schema dict for Anthropic tool definition

    async def execute(self, input: Any, context: ToolContext) -> ToolResult:
        """Execute the tool and return a result."""
        ...
