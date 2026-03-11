# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool: search_octopart — parametric component search via Octopart/Nexar API.

Octopart (now part of Nexar) provides a GraphQL API for electronic component data:
pricing, availability, specs, datasheets, and manufacturer info.

Credentials (set one of):
  - OCTOPART_API_KEY           (legacy Octopart v4 key)
  - NEXAR_CLIENT_ID + NEXAR_CLIENT_SECRET  (OAuth2, recommended)

Returns gracefully with success=False if no credentials are configured.
Returns: list of component dicts with mpn, manufacturer, category, description,
         datasheets (list of URLs), specs, pricing.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from ..base import ToolContext, ToolResult

log = logging.getLogger(__name__)

_NEXAR_TOKEN_URL = "https://identity.nexar.com/connect/token"
_NEXAR_API_URL = "https://api.nexar.com/graphql/"

_SEARCH_QUERY = """
query SearchComponents($query: String!, $limit: Int!) {
  supSearch(q: $query, limit: $limit) {
    results {
      part {
        mpn
        manufacturer { name }
        category { name path }
        shortDescription
        specs { attribute { name } displayValue }
        documentCollections {
          documents { name url }
        }
        sellers {
          offers { prices { quantity price currency } }
        }
      }
    }
  }
}
"""


@dataclass
class OctopartSearchInput:
    query: str
    max_results: int = 5


class SearchOctopartTool:
    """Searches Octopart/Nexar for electronic components.

    Returns structured component data: mpn, manufacturer, specs, datasheet URLs,
    and pricing. Falls back gracefully with success=False if no API key is set.
    """

    name = "search_octopart"
    description = (
        "Search the Octopart/Nexar component database for electronic parts. "
        "Returns mpn, manufacturer, specs, datasheet URLs, and pricing. "
        "Best for finding alternatives or verifying availability. "
        "Requires NEXAR_CLIENT_ID + NEXAR_CLIENT_SECRET env vars. "
        "Input: {\"query\": \"<part name or MPN>\", \"max_results\": 5}"
    )
    input_schema: dict = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Part name, MPN, or keyword"},
            "max_results": {"type": "integer", "description": "Maximum results to return", "default": 5},
        },
        "required": ["query"],
    }

    def __init__(self) -> None:
        self._nexar_token: str | None = None

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
                source="search_octopart",
                confidence=0.0,
                error="No query provided",
            )

        max_results = max(1, min(max_results, 20))

        # Check credentials
        has_nexar = bool(
            os.environ.get("NEXAR_CLIENT_ID") and os.environ.get("NEXAR_CLIENT_SECRET")
        )
        has_octopart = bool(os.environ.get("OCTOPART_API_KEY"))

        if not has_nexar and not has_octopart:
            return ToolResult(
                success=False,
                data=[],
                source="search_octopart",
                confidence=0.0,
                error=(
                    "Octopart/Nexar credentials not configured. "
                    "Set NEXAR_CLIENT_ID + NEXAR_CLIENT_SECRET (recommended) "
                    "or OCTOPART_API_KEY."
                ),
            )

        try:
            if has_nexar:
                results = await self._search_nexar(query, max_results)
                source = "nexar"
            else:
                results = await self._search_octopart_v4(query, max_results)
                source = "octopart_v4"
        except Exception as e:
            log.warning("Octopart search error: %s", e)
            return ToolResult(
                success=False,
                data=None,
                source="search_octopart",
                confidence=0.0,
                error=f"API error: {e}",
            )

        if not results:
            return ToolResult(
                success=False,
                data=[],
                source=f"search_octopart:{source}",
                confidence=0.0,
                error=f"No components found for query: {query!r}",
            )

        return ToolResult(
            success=True,
            data=results,
            source=f"search_octopart:{source}",
            confidence=0.85,
            metadata={"query": query, "count": len(results), "provider": source},
        )

    # ------------------------------------------------------------------
    # Nexar GraphQL (recommended, OAuth2)
    # ------------------------------------------------------------------

    async def _get_nexar_token(self) -> str:
        """Obtain a Nexar OAuth2 access token (cached per instance)."""
        if self._nexar_token:
            return self._nexar_token

        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx not installed (pip install httpx)")

        client_id = os.environ["NEXAR_CLIENT_ID"]
        client_secret = os.environ["NEXAR_CLIENT_SECRET"]

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _NEXAR_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

        self._nexar_token = token_data["access_token"]
        return self._nexar_token

    async def _search_nexar(self, query: str, max_results: int) -> list[dict]:
        """Execute GraphQL search against Nexar API."""
        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx not installed (pip install httpx)")

        token = await self._get_nexar_token()

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                _NEXAR_API_URL,
                json={"query": _SEARCH_QUERY, "variables": {"query": query, "limit": max_results}},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results_raw = (
            data.get("data", {})
            .get("supSearch", {})
            .get("results", [])
        )

        return [_parse_nexar_result(r) for r in results_raw if r.get("part")]

    # ------------------------------------------------------------------
    # Octopart v4 (legacy API key)
    # ------------------------------------------------------------------

    async def _search_octopart_v4(self, query: str, max_results: int) -> list[dict]:
        """Use legacy Octopart v4 REST API."""
        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx not installed (pip install httpx)")

        api_key = os.environ["OCTOPART_API_KEY"]

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                "https://octopart.com/api/v4/rest/parts/search",
                params={
                    "apikey": api_key,
                    "q": query,
                    "start": 0,
                    "limit": max_results,
                    "include[]": ["datasheets", "specs"],
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        return [_parse_octopart_v4_result(r) for r in results if r.get("item")]


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_nexar_result(result: dict) -> dict:
    part = result.get("part", {})

    # Datasheets
    datasheets: list[str] = []
    for coll in part.get("documentCollections", []):
        for doc in coll.get("documents", []):
            if doc.get("url"):
                datasheets.append(doc["url"])

    # Specs
    specs: dict[str, str] = {}
    for spec in part.get("specs", []):
        attr = spec.get("attribute", {}).get("name", "")
        val = spec.get("displayValue", "")
        if attr:
            specs[attr] = val

    # Pricing (lowest offer)
    unit_price: float | None = None
    for seller in part.get("sellers", []):
        for offer in seller.get("offers", []):
            for price in offer.get("prices", []):
                try:
                    p = float(price.get("price", 0))
                    if p > 0 and (unit_price is None or p < unit_price):
                        unit_price = p
                except (ValueError, TypeError):
                    pass

    mfr = part.get("manufacturer", {})
    cat = part.get("category", {})

    return {
        "mpn": part.get("mpn", ""),
        "manufacturer": mfr.get("name", ""),
        "category": cat.get("name", ""),
        "description": part.get("shortDescription", ""),
        "datasheets": datasheets[:3],
        "specs": specs,
        "unit_cost_usd": unit_price,
        "source": "nexar",
    }


def _parse_octopart_v4_result(result: dict) -> dict:
    item = result.get("item", {})

    datasheets = [
        d.get("url", "")
        for d in item.get("datasheets", [])
        if d.get("url")
    ]

    specs: dict[str, str] = {}
    for key, spec_obj in item.get("specs", {}).items():
        val = spec_obj.get("display_value", "")
        if val:
            specs[key] = val

    mfr_info = item.get("manufacturer", {})

    return {
        "mpn": item.get("mpn", ""),
        "manufacturer": mfr_info.get("name", ""),
        "category": item.get("category", {}).get("name", ""),
        "description": item.get("description", ""),
        "datasheets": datasheets[:3],
        "specs": specs,
        "unit_cost_usd": None,
        "source": "octopart_v4",
    }
