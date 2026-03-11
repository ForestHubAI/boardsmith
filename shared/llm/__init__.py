# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLM abstraction layer for Boardsmith.

Provides a provider-agnostic interface to Anthropic, OpenAI, and Ollama.

Quick start:
    from llm.gateway import LLMGateway
    from llm.types import Message, TaskType

    gateway = LLMGateway()   # reads ANTHROPIC_API_KEY / OPENAI_API_KEY from env

    # Async
    response = await gateway.complete(
        task=TaskType.INTENT_PARSE,
        messages=[Message(role="user", content="ESP32 with BME280 over I2C")],
        system="Extract hardware requirements as JSON.",
        max_tokens=1024,
    )
    print(response.content)       # JSON string
    print(response.cost_usd)      # e.g. 0.0003

    # Sync (from non-async code)
    response = gateway.complete_sync(task=TaskType.CODE_GEN, messages=[...])
"""

from .config import LLMConfig
from .gateway import LLMGateway, get_default_gateway, reset_default_gateway
from .types import CostSummary, LLMResponse, Message, TaskType

__all__ = [
    "LLMConfig",
    "LLMGateway",
    "LLMResponse",
    "Message",
    "TaskType",
    "CostSummary",
    "get_default_gateway",
    "reset_default_gateway",
]
