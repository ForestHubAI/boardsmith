# SPDX-License-Identifier: AGPL-3.0-or-later
"""OpenAI GPT provider."""

from __future__ import annotations

from ..types import LLMResponse, Message


class OpenAIProvider:
    """Wraps the OpenAI async SDK."""

    name = "openai"

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
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError(
                "LLM features require the openai package. "
                "Install with: pip install boardsmith[llm]"
            ) from exc

        client = AsyncOpenAI(api_key=self._api_key)

        api_messages = []
        if system:
            api_messages.append({"role": "system", "content": system})
        for m in messages:
            api_messages.append({"role": m.role, "content": m.content})

        resp = await client.chat.completions.create(
            model=model,
            messages=api_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = resp.choices[0].message.content or ""
        input_tokens = resp.usage.prompt_tokens if resp.usage else 0
        output_tokens = resp.usage.completion_tokens if resp.usage else 0

        return LLMResponse(
            content=content,
            model=model,
            provider=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
