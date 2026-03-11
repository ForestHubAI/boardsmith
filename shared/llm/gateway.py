# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLMGateway — provider-agnostic LLM abstraction layer.

Usage (async):
    gateway = LLMGateway()
    response = await gateway.complete(
        task=TaskType.INTENT_PARSE,
        messages=[Message(role="user", content=prompt)],
        system=SYSTEM_PROMPT,
        max_tokens=1024,
    )

Usage (sync, e.g. from non-async code):
    gateway = LLMGateway()
    response = gateway.complete_sync(
        task=TaskType.INTENT_PARSE,
        messages=[Message(role="user", content=prompt)],
        system=SYSTEM_PROMPT,
        max_tokens=1024,
    )

--no-llm mode:
    gateway = LLMGateway(LLMConfig.no_llm_mode())
    response = await gateway.complete(...)
    assert response.skipped is True
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import TYPE_CHECKING

from .config import LLMConfig
from .cost_tracker import CostTracker
from .router import get_provider_chain
from .types import LLMResponse, Message, TaskType

if TYPE_CHECKING:
    from .types import CostSummary, ToolCallResponse

log = logging.getLogger(__name__)


class LLMGateway:
    """Central LLM entry point.  Thread-safe, provider-agnostic."""

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()
        self._tracker = CostTracker()
        self._providers: dict = {}
        self._init_providers()

    # ------------------------------------------------------------------
    # Provider setup
    # ------------------------------------------------------------------

    def _init_providers(self) -> None:
        from .providers.anthropic import AnthropicProvider
        from .providers.ollama import OllamaProvider
        from .providers.openai import OpenAIProvider

        if self.config.anthropic_api_key:
            self._providers["anthropic"] = AnthropicProvider(self.config.anthropic_api_key)
        if self.config.openai_api_key:
            self._providers["openai"] = OpenAIProvider(self.config.openai_api_key)
        # Ollama is always tried if configured (no key needed)
        self._providers["ollama"] = OllamaProvider(self.config.ollama_base_url)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def complete(
        self,
        task: TaskType | str,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        model_override: str | None = None,
    ) -> LLMResponse:
        """Route the request to the best available provider.

        Returns a skipped response if --no-llm mode is active or all providers fail.
        """
        if self.config.no_llm:
            return LLMResponse(content="", model="", provider="", skipped=True)

        # Check budget
        if self.config.budget_limit_usd is not None:
            if self._tracker.is_over_budget(self.config.budget_limit_usd):
                log.warning(
                    "LLM budget limit $%.2f exceeded (spent: $%.4f). Skipping.",
                    self.config.budget_limit_usd,
                    self._tracker.total_usd(),
                )
                return LLMResponse(content="", model="", provider="", skipped=True)

        task_str = task.value if isinstance(task, TaskType) else str(task)
        chain = get_provider_chain(task_str)

        # Apply model override to first chain entry if given
        if model_override:
            chain = [(chain[0][0], model_override)] + list(chain[1:]) if chain else chain

        last_error: Exception | None = None

        for provider_name, model in chain:
            provider = self._providers.get(provider_name)
            if provider is None or not provider.is_available():
                continue

            try:
                response = await provider.complete(
                    messages=messages,
                    system=system,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                # Track cost
                cost = self._tracker.log(
                    task=task_str,
                    provider=provider_name,
                    model=model,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                )
                response.cost_usd = cost
                log.debug(
                    "LLM [%s/%s] task=%s tokens=%d+%d cost=$%.4f",
                    provider_name, model, task_str,
                    response.input_tokens, response.output_tokens, cost,
                )
                return response

            except Exception as e:
                last_error = e
                log.warning(
                    "LLM provider %s/%s failed for task %s: %s — trying next.",
                    provider_name, model, task_str, e,
                )
                continue

        # All providers failed
        if last_error:
            log.error("All LLM providers failed for task %s: %s", task_str, last_error)
        return LLMResponse(content="", model="", provider="", skipped=True)

    def complete_sync(
        self,
        task: TaskType | str,
        messages: list[Message],
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        model_override: str | None = None,
    ) -> LLMResponse:
        """Synchronous wrapper for complete() — safe to call from non-async code."""
        # Use a factory so the except-clause always gets a fresh coroutine object.
        # Reusing an already-started coroutine raises "cannot reuse already awaited coroutine"
        # when the coroutine itself raised RuntimeError (e.g. missing API key).
        def _make_coro():
            return self.complete(
                task=task,
                messages=messages,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                model_override=model_override,
            )

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an async context (e.g., Jupyter, existing event loop).
                # Run in a separate thread with its own event loop.
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, _make_coro())
                    return future.result(timeout=120)
            return loop.run_until_complete(_make_coro())
        except RuntimeError:
            return asyncio.run(_make_coro())

    async def complete_with_tools(
        self,
        tools: list[dict],
        messages: list[dict],
        model: str,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> "ToolCallResponse":
        """Route a tool-use request to AnthropicProvider.complete_with_tools().

        Only Anthropic supports tool-use in v0.2. Returns a ToolCallResponse with
        empty tool_calls list if no_llm mode is active (caller must check stop_reason).

        tools: Anthropic tool definition dicts built from Tool.input_schema.
        messages: API-format message dicts (not Message dataclasses).
        """
        if self.config.no_llm:
            from .types import ToolCallResponse
            return ToolCallResponse(tool_calls=[], model="", provider="", stop_reason="no_llm")

        provider = self._providers.get("anthropic")
        if provider is None or not provider.is_available():
            raise RuntimeError(
                "complete_with_tools() requires an Anthropic API key. "
                "Set ANTHROPIC_API_KEY or install with: pip install boardsmith[llm]"
            )

        return await provider.complete_with_tools(
            tools=tools,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            system=system,
        )

    def complete_with_tools_sync(
        self,
        tools: list[dict],
        messages: list[dict],
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> "ToolCallResponse":
        """Synchronous wrapper for complete_with_tools() — safe to call from non-async code.

        Same event-loop handling as complete_sync(): uses ThreadPoolExecutor when a loop
        is already running (e.g. from within ERCAgent called by an async CLI command).
        """
        # Use a factory so the except-clause always gets a fresh coroutine object.
        # Reusing an already-started coroutine raises "cannot reuse already awaited coroutine"
        # when the coroutine itself raised RuntimeError (e.g. missing API key).
        def _make_coro():
            return self.complete_with_tools(
                tools=tools,
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                system=system,
            )

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, _make_coro())
                    return future.result(timeout=120)
            return loop.run_until_complete(_make_coro())
        except RuntimeError:
            return asyncio.run(_make_coro())

    # ------------------------------------------------------------------
    # Cost / introspection
    # ------------------------------------------------------------------

    def get_cost_summary(self) -> "CostSummary":
        return self._tracker.get_summary()

    def format_cost_summary(self) -> str:
        return self._tracker.format_summary()

    def is_llm_available(self) -> bool:
        """True if at least one real LLM provider is configured."""
        if self.config.no_llm:
            return False
        return any(
            name in self._providers and self._providers[name].is_available()
            for name in ("anthropic", "openai")
        )


# ---------------------------------------------------------------------------
# Module-level convenience: a default gateway (created lazily)
# ---------------------------------------------------------------------------

_default_gateway: LLMGateway | None = None


def get_default_gateway() -> LLMGateway:
    """Return the module-level default gateway (created from env vars)."""
    global _default_gateway
    if _default_gateway is None:
        _default_gateway = LLMGateway()
    return _default_gateway


def reset_default_gateway(config: LLMConfig | None = None) -> None:
    """Reset the default gateway (useful for tests)."""
    global _default_gateway
    _default_gateway = LLMGateway(config) if config is not None else None
