# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ollama local model provider (offline mode)."""

from __future__ import annotations

from ..types import LLMResponse, Message


class OllamaProvider:
    """Wraps the Ollama REST API for local models."""

    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self._base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        """Check if Ollama is reachable (best-effort, non-blocking)."""
        return bool(self._base_url)

    async def complete(
        self,
        messages: list[Message],
        system: str | None,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        import httpx

        api_messages = []
        if system:
            api_messages.append({"role": "system", "content": system})
        for m in messages:
            api_messages.append({"role": m.role, "content": m.content})

        payload = {
            "model": model,
            "messages": api_messages,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        content = data.get("message", {}).get("content", "")
        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)

        return LLMResponse(
            content=content,
            model=model,
            provider=self.name,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            cost_usd=0.0,
        )
