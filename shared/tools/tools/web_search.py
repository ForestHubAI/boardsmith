# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool: web_search — search the web for hardware component information.

Provider chain (first configured provider wins):
  1. Anthropic  (ANTHROPIC_API_KEY env var) — built-in web_search_20250305, no extra key
  2. Tavily     (TAVILY_API_KEY env var)    — AI-optimized, best for technical docs
  3. SerpAPI    (SERPAPI_API_KEY env var)   — Google-backed, reliable
  4. DuckDuckGo (no key needed)             — best-effort HTML fallback

Returns: list of {"title": str, "url": str, "snippet": str} dicts.

Useful for: finding datasheet PDFs, component specs, manufacturer pages.
Use queries like: "SCD41 Sensirion datasheet filetype:pdf"
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from ..base import ToolContext, ToolResult

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Boardsmith/0.1; hardware-research-bot)",
    "Accept": "text/html,application/json",
}


@dataclass
class WebSearchInput:
    query: str
    max_results: int = 5


class WebSearchTool:
    """Searches the web for hardware component documentation and datasheets.

    Tries API providers in order (Tavily -> SerpAPI -> DuckDuckGo fallback).
    Returns results as a list of dicts with title, url, snippet.
    """

    name = "web_search"
    description = (
        "Search the web for hardware component datasheets, specs, or documentation. "
        "Returns a list of results with title, URL, and snippet. "
        "For datasheets use queries like: 'SCD41 Sensirion datasheet filetype:pdf'. "
        "Input: {\"query\": \"<search terms>\", \"max_results\": 5}"
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query string"},
            "max_results": {"type": "integer", "description": "Maximum results to return (1-10)", "default": 5},
        },
        "required": ["query"],
    }

    async def execute(self, input: Any, context: ToolContext) -> ToolResult:
        # Accept dict or dataclass
        if isinstance(input, dict):
            query = input.get("query", "")
            max_results = int(input.get("max_results", 5))
        else:
            query = getattr(input, "query", "")
            max_results = getattr(input, "max_results", 5)

        if not query:
            return ToolResult(
                success=False,
                data=None,
                source="web_search",
                confidence=0.0,
                error="No query provided",
            )

        max_results = max(1, min(max_results, 10))

        # Try providers in order
        results, provider = await self._search(query, max_results)

        if not results:
            return ToolResult(
                success=False,
                data=[],
                source="web_search",
                confidence=0.0,
                error=(
                    "No search results found. "
                    "Set TAVILY_API_KEY or SERPAPI_API_KEY for better results."
                ),
            )

        return ToolResult(
            success=True,
            data=results,
            source=f"web_search:{provider}",
            confidence=_provider_confidence(provider),
            metadata={"provider": provider, "query": query, "count": len(results)},
        )

    # ------------------------------------------------------------------
    # Internal: provider chain
    # ------------------------------------------------------------------

    async def _search(self, query: str, max_results: int) -> tuple[list[dict], str]:
        """Try each provider in order, return (results, provider_name)."""

        # 1. Anthropic built-in web search (uses existing ANTHROPIC_API_KEY, no extra key)
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if anthropic_key:
            results = await _search_anthropic(query, max_results, anthropic_key)
            if results:
                return results, "anthropic"

        # 2. Tavily
        tavily_key = os.environ.get("TAVILY_API_KEY", "").strip()
        if tavily_key:
            results = await _search_tavily(query, max_results, tavily_key)
            if results:
                return results, "tavily"

        # 3. SerpAPI
        serp_key = os.environ.get("SERPAPI_API_KEY", "").strip()
        if serp_key:
            results = await _search_serpapi(query, max_results, serp_key)
            if results:
                return results, "serpapi"

        # 4. DuckDuckGo HTML (no key needed, best-effort)
        results = await _search_duckduckgo(query, max_results)
        if results:
            return results, "duckduckgo"

        return [], "none"


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

# Model used for the Anthropic web search call — cheap haiku is fine for search
_ANTHROPIC_SEARCH_MODEL = os.environ.get(
    "ANTHROPIC_SEARCH_MODEL", "claude-haiku-4-5-20251001"
)


async def _search_anthropic(query: str, max_results: int, api_key: str) -> list[dict]:
    """Anthropic built-in web search via the web_search_20250305 tool.

    No extra API key needed — uses the existing ANTHROPIC_API_KEY.
    The model runs the search internally and returns structured results.
    """
    try:
        import anthropic
        import asyncio
        import json as _json
    except ImportError:
        log.debug("anthropic SDK not available for web search")
        return []

    try:
        client = anthropic.Anthropic(api_key=api_key)

        prompt = (
            f'Search the web for: "{query}"\n\n'
            f"Return ONLY a JSON array of the top {max_results} results.\n"
            f'Each item must have exactly these keys: "title" (string), "url" (string), '
            f'"snippet" (string, ≤300 chars).\n'
            f"No prose, no markdown code fences — raw JSON array only."
        )

        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.messages.create(
                model=_ANTHROPIC_SEARCH_MODEL,
                max_tokens=2048,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": prompt}],
            ),
        )

        results: list[dict] = []

        for block in response.content:
            btype = getattr(block, "type", None)

            # Case A: tool_result block — Anthropic returns structured search docs
            if btype == "tool_result":
                inner = getattr(block, "content", []) or []
                for item in inner:
                    itype = getattr(item, "type", None)
                    if itype == "document":
                        doc = getattr(item, "document", {}) or {}
                        url = doc.get("url") or ""
                        if url:
                            results.append({
                                "title": str(doc.get("title", "")),
                                "url": url,
                                "snippet": str(doc.get("content", ""))[:300],
                            })

            # Case B: text block — model formatted results as JSON (our prompt asks for this)
            elif btype == "text" and not results:
                text = getattr(block, "text", "")
                # Strip optional ```json ... ``` fences
                text = re.sub(r"```(?:json)?\s*", "", text).strip()
                m = re.search(r"\[[\s\S]+\]", text)
                if m:
                    try:
                        items = _json.loads(m.group(0))
                        for item in items:
                            if isinstance(item, dict) and item.get("url"):
                                results.append({
                                    "title": str(item.get("title", "")),
                                    "url": str(item.get("url", "")),
                                    "snippet": str(item.get("snippet", ""))[:300],
                                })
                    except _json.JSONDecodeError:
                        pass

        log.debug("Anthropic web search: %d results for %r", len(results), query)
        return results[:max_results]

    except Exception as e:
        log.debug("Anthropic web search failed: %s", e)
        return []


async def _search_tavily(query: str, max_results: int, api_key: str) -> list[dict]:
    """Tavily AI search API — returns high-quality, AI-curated results."""
    try:
        import httpx
    except ImportError:
        log.debug("httpx not available for Tavily")
        return []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                    "include_answer": False,
                },
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        raw = data.get("results", [])
        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", r.get("snippet", ""))[:300],
            }
            for r in raw
            if r.get("url")
        ]
        log.debug("Tavily returned %d results for %r", len(results), query)
        return results[:max_results]

    except Exception as e:
        log.debug("Tavily search failed: %s", e)
        return []


async def _search_serpapi(query: str, max_results: int, api_key: str) -> list[dict]:
    """SerpAPI — Google search proxy."""
    try:
        import httpx
    except ImportError:
        return []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://serpapi.com/search",
                params={
                    "q": query,
                    "api_key": api_key,
                    "engine": "google",
                    "num": max_results,
                    "hl": "en",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        raw = data.get("organic_results", [])
        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("link", ""),
                "snippet": r.get("snippet", "")[:300],
            }
            for r in raw
            if r.get("link")
        ]
        log.debug("SerpAPI returned %d results for %r", len(results), query)
        return results[:max_results]

    except Exception as e:
        log.debug("SerpAPI search failed: %s", e)
        return []


async def _search_duckduckgo(query: str, max_results: int) -> list[dict]:
    """DuckDuckGo HTML — no API key needed. Best-effort, may be rate-limited."""
    try:
        import httpx
    except ImportError:
        log.debug("httpx not available for DuckDuckGo")
        return []

    try:
        # DuckDuckGo Lite: simple HTML, easier to parse
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            headers=_HEADERS,
        ) as client:
            resp = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query, "b": "", "kl": "us-en"},
            )
            html = resp.text

        # Extract result links (class="result__a") and snippets
        links = re.findall(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        )
        snippets = re.findall(
            r'class="result__snippet"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        )

        results: list[dict] = []
        for i, (href, raw_title) in enumerate(links):
            # Skip DuckDuckGo-internal links
            if href.startswith("/") or "duckduckgo.com" in href:
                continue
            title = re.sub(r"<[^>]+>", "", raw_title).strip()
            snippet_raw = snippets[i] if i < len(snippets) else ""
            snippet = re.sub(r"<[^>]+>", "", snippet_raw).strip()
            if href and title:
                results.append({"title": title, "url": href, "snippet": snippet})
            if len(results) >= max_results:
                break

        log.debug("DuckDuckGo returned %d results for %r", len(results), query)
        return results

    except Exception as e:
        log.debug("DuckDuckGo search failed: %s", e)
        return []


def _provider_confidence(provider: str) -> float:
    return {
        "anthropic": 0.92,
        "tavily": 0.90,
        "serpapi": 0.85,
        "duckduckgo": 0.70,
        "none": 0.0,
    }.get(provider, 0.50)
