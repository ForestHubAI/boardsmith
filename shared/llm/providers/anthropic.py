# SPDX-License-Identifier: AGPL-3.0-or-later
"""Anthropic Claude provider."""

from __future__ import annotations

from ..types import LLMResponse, Message


class AnthropicProvider:
    """Wraps the Anthropic SDK."""

    name = "anthropic"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def complete(
        self,
        messages: list[Message],
        system: str | None,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "LLM features require the anthropic package. "
                "Install with: pip install boardsmith[llm]"
            ) from exc

        client = anthropic.Anthropic(api_key=self._api_key)

        api_messages = [
            {"role": m["role"] if isinstance(m, dict) else m.role,
             "content": m["content"] if isinstance(m, dict) else m.content}
            for m in messages
        ]

        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": api_messages,
        }
        if system:
            kwargs["system"] = system
        if temperature != 0.0:
            kwargs["temperature"] = temperature

        # Run sync Anthropic call in thread to not block the event loop
        import asyncio
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.messages.create(**kwargs),
        )

        content = response.content[0].text if response.content else ""
        input_tokens = response.usage.input_tokens if response.usage else 0
        output_tokens = response.usage.output_tokens if response.usage else 0

        return LLMResponse(
            content=content,
            model=model,
            provider=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def complete_with_tools(
        self,
        tools: list[dict],
        messages: list[dict],
        model: str,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> "ToolCallResponse":
        """Send tool definitions to Claude and handle tool_use stop_reason.

        complete() is NOT called or modified by this method.
        tools: list of Anthropic tool definition dicts (name, description, input_schema).
        messages: already-formatted API message dicts (not Message dataclasses).
        Returns ToolCallResponse. raw_content holds SDK content blocks — pass directly
        to next API call as assistant content without calling .to_dict().
        """
        try:
            import anthropic as _anthropic
        except ImportError as exc:
            raise ImportError(
                "LLM features require the anthropic package. "
                "Install with: pip install boardsmith[llm]"
            ) from exc

        from ..types import ToolCall, ToolCallResponse

        client = _anthropic.Anthropic(api_key=self._api_key)

        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "tools": tools,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        import asyncio
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.messages.create(**kwargs),
        )

        # Filter to tool_use blocks only — Claude may emit TextBlock preamble before tool_use
        tool_calls = [
            ToolCall(id=block.id, name=block.name, input=dict(block.input))
            for block in response.content
            if block.type == "tool_use"
        ]

        return ToolCallResponse(
            tool_calls=tool_calls,
            model=model,
            provider=self.name,
            input_tokens=response.usage.input_tokens if response.usage else 0,
            output_tokens=response.usage.output_tokens if response.usage else 0,
            raw_content=response.content,  # pass directly to next messages.create() call
            stop_reason=response.stop_reason or "tool_use",
        )
