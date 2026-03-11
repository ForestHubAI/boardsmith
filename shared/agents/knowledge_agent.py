# SPDX-License-Identifier: AGPL-3.0-or-later
"""Knowledge Agent — finds component specs via ReAct loop.

Resolution chain (agent-first):
  1. Builtin DB (55+ entries)   → instant,   confidence 0.95
  2. Local cache (~/.boardsmith/) → instant,   confidence 0.85
  3. Agent (ReAct + 5 Tools)    → 5–30 sec,  confidence 0.60–0.80
  4. None                       → no result

The agent uses 5 tools:
  - query_knowledge   — local DB lookup
  - search_octopart   — Nexar/Octopart parametric search
  - web_search        — Tavily/Perplexity web search
  - download_pdf      — PDF datasheet download + cache
  - extract_datasheet — LLM-based PDF extraction

Cache entries grow richer over time via merge-on-write: when a component
is found from multiple sources, per-field provenance is tracked and the
best data wins.

Usage:
    agent = KnowledgeAgent()
    result = await agent.find("SCD41")
    result = await agent.find("CO2 sensor I2C 3.3V")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class AgentComponentResult:
    """A component found by the Knowledge Agent."""

    mpn: str
    name: str
    manufacturer: str
    category: str
    interface_types: list[str]
    electrical_ratings: dict[str, Any]
    known_i2c_addresses: list[str]
    unit_cost_usd: float
    tags: list[str]
    confidence: float
    source: str        # "builtin_db", "local_cache", "agent_extracted", "minimal"
    raw: dict[str, Any] = field(default_factory=dict)
    agent_trace: list[str] = field(default_factory=list)  # step summaries


class KnowledgeAgent:
    """Finds and returns component knowledge using a 4-tier resolution chain."""

    _UNSET = object()  # sentinel: gateway not provided → use default

    #: Minimum confidence for auto-promoting agent results as 'draft' to the DB
    AUTO_PROMOTE_THRESHOLD: float = 0.75

    def __init__(
        self,
        gateway: Any | None = _UNSET,   # LLMGateway; pass None to disable LLM
        cache_dir: Path | None = None,
        max_agent_steps: int = 8,
        auto_promote_threshold: float = AUTO_PROMOTE_THRESHOLD,
    ) -> None:
        # Distinguish between "not provided" (use default) and explicit None (disable)
        self._gateway = gateway
        self._gateway_explicit_none = (gateway is None)
        self._cache_dir = cache_dir or Path.home() / ".boardsmith" / "knowledge"
        self._max_steps = max_agent_steps
        self._auto_promote_threshold = auto_promote_threshold
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def find(self, query: str) -> AgentComponentResult | None:
        """Find a component by MPN or description.

        Tries each tier in order, returning the first hit.
        """
        log.info("Knowledge Agent: query='%s'", query)

        # Tier 1: Builtin DB
        result = self._query_builtin(query)
        if result:
            log.info("  → hit in builtin DB (conf=%.2f)", result.confidence)
            return result

        # Tier 2: Local cache
        result = self._query_cache(query)
        if result:
            log.info("  → hit in local cache (conf=%.2f)", result.confidence)
            return result

        # Tier 3: Agent (LLM + Tools)
        gw = self._get_gateway()
        if gw and gw.is_llm_available():
            result = await self._run_agent(query, gw)
            if result:
                # Only cache if result is substantive (has real data, not just query text)
                if result.confidence >= 0.5 and result.manufacturer:
                    self._save_to_cache(result)
                    log.info("  → agent found %s (conf=%.2f)", result.mpn, result.confidence)
                    # DB-4: Auto-promote high-confidence results as draft
                    if result.confidence >= self._auto_promote_threshold:
                        self._auto_promote_to_db(result)
                else:
                    log.info("  → agent result too low quality to cache (conf=%.2f, mpn=%s)", result.confidence, result.mpn)
                return result

        # Tier 4: Minimal fallback
        log.warning("  → no result for '%s'", query)
        return None

    async def find_for_modality(self, modality: str, requirements: dict[str, Any] | None = None) -> AgentComponentResult | None:
        """Find the best component for a sensing modality (e.g. 'CO2', 'pressure')."""
        # First: check if we have something in the DB for this modality
        result = self._query_builtin_by_modality(modality)
        if result:
            return result

        # Agent: search for modality
        query = f"{modality} sensor"
        if requirements:
            interface = requirements.get("interface", "I2C")
            voltage = requirements.get("supply_voltage", 3.3)
            query = f"{modality} sensor {interface} {voltage}V"

        return await self.find(query)

    # ------------------------------------------------------------------
    # Tier 1: Builtin DB
    # ------------------------------------------------------------------

    def _query_builtin(self, query: str) -> AgentComponentResult | None:
        try:
            from knowledge import db
        except ImportError:
            return None

        # Exact MPN match
        entry = db.find_by_mpn(query)
        if entry:
            return self._entry_to_result(entry, source="builtin_db", confidence=0.95)

        # FTS search
        results = db.search(query, limit=1)
        if results:
            return self._entry_to_result(results[0], source="builtin_db", confidence=0.90)

        # Fuzzy: normalize query (strip dashes/spaces) and match
        q_norm = query.lower().replace("-", "").replace(" ", "")
        for entry in db.get_all():
            mpn_norm = entry.get("mpn", "").lower().replace("-", "")
            if q_norm == mpn_norm:
                return self._entry_to_result(entry, source="builtin_db", confidence=0.95)

        return None

    def _query_builtin_by_modality(self, modality: str) -> AgentComponentResult | None:
        """Check if we have a component tagged with this modality in the builtin DB."""
        try:
            from knowledge import db
        except ImportError:
            return None

        q = modality.lower()
        # Try FTS first
        results = db.search(q, limit=1)
        if results:
            return self._entry_to_result(results[0], source="builtin_db", confidence=0.90)

        # Fallback: tag/category scan
        for entry in db.get_all():
            tags = [t.lower() for t in entry.get("tags", [])]
            cat = entry.get("category", "").lower()
            if q in tags or q in cat:
                return self._entry_to_result(entry, source="builtin_db", confidence=0.90)
        return None

    # ------------------------------------------------------------------
    # Tier 2: Local cache
    # ------------------------------------------------------------------

    def _query_cache(self, query: str) -> AgentComponentResult | None:
        """Search the local cache by filename AND by JSON content (mpn field).

        This catches cases where the cache filename doesn't exactly match
        the query (e.g. ``BOSCH_BME280.json`` for query ``BME280``).
        """
        q_norm = query.upper().replace(" ", "_").replace("-", "")

        for path in self._cache_dir.glob("*.json"):
            # Fast: filename match
            stem_norm = path.stem.upper().replace("-", "")
            if q_norm in stem_norm:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    conf = data.get("_provenance", {}).get("confidence", 0.85)
                    return self._dict_to_result(data, source="local_cache", confidence=max(conf, 0.80))
                except Exception:
                    pass

            # Slow: content match on mpn / tags
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                mpn_norm = data.get("mpn", "").upper().replace("-", "")
                if q_norm == mpn_norm:
                    conf = data.get("_provenance", {}).get("confidence", 0.85)
                    return self._dict_to_result(data, source="local_cache", confidence=max(conf, 0.80))
            except Exception:
                continue

        return None

    def _auto_promote_to_db(self, result: AgentComponentResult) -> None:
        """Write a high-confidence agent result into the local SQLite DB as 'draft'.

        Called automatically when confidence >= auto_promote_threshold (default 0.75).
        The draft can later be promoted to 'validated' via `boardsmith validate-draft`.
        """
        try:
            from knowledge.db import find_by_mpn, upsert_draft
            # Don't overwrite existing released/validated/verified entries
            existing = find_by_mpn(result.mpn)
            if existing and existing.get("component_state", "released") != "draft":
                log.debug("Auto-promote skipped: '%s' already in state '%s'",
                          result.mpn, existing.get("component_state"))
                return

            entry = self._result_to_component_entry(result)
            upsert_draft(entry, confidence=result.confidence, source=result.source)
            log.info("  → auto-promoted '%s' to DB as draft (conf=%.2f)",
                     result.mpn, result.confidence)
        except Exception as exc:
            log.warning("Auto-promote to DB failed for '%s': %s", result.mpn, exc)

    @staticmethod
    def _result_to_component_entry(result: AgentComponentResult) -> Any:
        """Convert AgentComponentResult to a ComponentEntry-compatible dict."""
        return {
            "mpn": result.mpn,
            "manufacturer": result.manufacturer,
            "name": result.name,
            "category": result.category,
            "interface_types": result.interface_types,
            "electrical_ratings": result.electrical_ratings,
            "known_i2c_addresses": result.known_i2c_addresses,
            "unit_cost_usd": result.unit_cost_usd,
            "tags": result.tags,
            "status": "active",
        }

    def _save_to_cache(self, result: AgentComponentResult) -> None:
        """Save or merge result into the local cache.

        If the MPN already exists in cache, merges per-field (keeping the
        richer value) and tracks provenance for each field.
        """
        if not result.mpn:
            return
        path = self._cache_path(result.mpn)

        # Build the new dict with extended ComponentEntry fields + provenance
        new_dict = self._result_to_dict(result)

        # Check if there's an existing cache entry to merge with
        existing_data = None
        if path.exists():
            try:
                existing_data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                existing_data = None

        if existing_data is not None:
            merged = self._merge_dicts(existing_data, new_dict, result.source)
        else:
            merged = new_dict

        try:
            path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
            log.debug("Saved to cache: %s", path)
        except Exception as e:
            log.warning("Failed to save cache: %s", e)

    def _cache_path(self, mpn: str) -> Path:
        """Canonical cache file path for an MPN."""
        return self._cache_dir / f"{mpn.upper().replace('/', '_')}.json"

    @staticmethod
    def _merge_dicts(existing: dict, new: dict, new_source: str) -> dict:
        """Merge new data into existing cache entry, keeping the richer value per field.

        Provenance is tracked in ``_provenance.field_sources``.
        """
        merged = dict(existing)
        prov = merged.get("_provenance", {})
        field_sources: dict[str, str] = prov.get("field_sources", {})

        # Simple string/list fields: fill empty
        for key in ("manufacturer", "package", "description", "name"):
            new_val = new.get(key, "")
            old_val = merged.get(key, "")
            if new_val and not old_val:
                merged[key] = new_val
                field_sources[key] = new_source

        # List fields: union
        for key in ("interface_types", "known_i2c_addresses", "tags"):
            old_list = merged.get(key, [])
            new_list = new.get(key, [])
            combined = list(dict.fromkeys(old_list + new_list))  # dedup, preserve order
            if combined != old_list:
                merged[key] = combined
                field_sources[key] = f"{field_sources.get(key, '')}+{new_source}".lstrip("+")

        # Electrical ratings: merge sub-fields
        old_ratings = merged.get("electrical_ratings", {})
        new_ratings = new.get("electrical_ratings", {})
        for k, v in new_ratings.items():
            if v and (k not in old_ratings or not old_ratings[k]):
                old_ratings[k] = v
                field_sources[f"electrical_ratings.{k}"] = new_source
        merged["electrical_ratings"] = old_ratings

        # Timing caps: merge sub-fields
        old_timing = merged.get("timing_caps", {})
        new_timing = new.get("timing_caps", {})
        for k, v in new_timing.items():
            if v and (k not in old_timing or not old_timing[k]):
                old_timing[k] = v
                field_sources[f"timing_caps.{k}"] = new_source
        merged["timing_caps"] = old_timing

        # Scalar fields: prefer new if present and old is 0/empty
        for key in ("unit_cost_usd",):
            new_val = new.get(key, 0)
            old_val = merged.get(key, 0)
            if new_val and not old_val:
                merged[key] = new_val
                field_sources[key] = new_source

        # Update provenance
        new_prov = new.get("_provenance", {})
        prov["confidence"] = max(
            prov.get("confidence", 0),
            new_prov.get("confidence", 0),
        )
        prov["field_sources"] = field_sources
        prov["last_updated"] = datetime.now(timezone.utc).isoformat()
        # Append trace
        old_trace = prov.get("agent_trace", [])
        new_trace = new_prov.get("agent_trace", [])
        if new_trace:
            prov["agent_trace"] = old_trace + new_trace
        merged["_provenance"] = prov

        return merged

    # ------------------------------------------------------------------
    # Tier 3: Agent (ReAct)
    # ------------------------------------------------------------------

    async def _run_agent(self, query: str, gateway: Any) -> AgentComponentResult | None:
        from agents.react_loop import run_react_loop
        from llm.types import TaskType
        from tools.base import ToolContext
        from tools.tools.download_pdf import DownloadPDFTool
        from tools.tools.extract_datasheet import ExtractDatasheetTool
        from tools.tools.query_knowledge import QueryKnowledgeTool
        from tools.tools.search_octopart import SearchOctopartTool
        from tools.tools.web_search import WebSearchTool

        context = ToolContext(
            session_id=f"knowledge_agent_{query}",
            llm_gateway=gateway,
            cache_dir=self._cache_dir,
        )

        tools: dict[str, Any] = {
            "query_knowledge": QueryKnowledgeTool(),
            "search_octopart": SearchOctopartTool(),
            "web_search": WebSearchTool(),
            "download_pdf": DownloadPDFTool(),
            "extract_datasheet": ExtractDatasheetTool(),
        }

        task = (
            f"Find complete electrical specifications for: '{query}'\n"
            f"Steps:\n"
            f"1) Check local knowledge DB first (query_knowledge tool).\n"
            f"2) If not found or incomplete, search Octopart (search_octopart).\n"
            f"3) If Octopart is unavailable, use web_search to find specs or datasheet URL.\n"
            f"4) Optionally download and extract the datasheet PDF.\n"
            f"5) When you have enough info, use Action: FINISH.\n"
            f"CRITICAL: Your Final Answer MUST be a valid JSON object (no prose, no markdown "
            f"code blocks) with these fields:\n"
            f'{{"mpn": "...", "name": "...", "manufacturer": "...", "category": "sensor|mcu|power|...", '
            f'"interface_types": ["I2C"], "package": "...", "description": "...", '
            f'"electrical_ratings": {{"vdd_min": 0.0, "vdd_max": 0.0, "io_voltage_nominal": 0.0, '
            f'"current_draw_typical_ma": 0.0}}, "known_i2c_addresses": [], '
            f'"unit_cost_usd": 0.0, "tags": []}}\n'
            f"If query_knowledge returns a match, use that data directly in your JSON answer."
        )

        react_result = await run_react_loop(
            task=task,
            tools=tools,
            gateway=gateway,
            context=context,
            max_steps=self._max_steps,
            task_type=TaskType.AGENT_REASONING,
        )

        if not react_result.success or not react_result.answer:
            return None

        return self._parse_agent_answer(
            react_result.answer,
            query,
            trace=[f"Step {s.step_num}: {s.action}" for s in react_result.steps],
        )

    def _parse_agent_answer(
        self, answer: str, query: str, trace: list[str]
    ) -> AgentComponentResult | None:
        """Try to parse the agent's final answer as a component spec JSON."""
        import re as _re
        # Try to extract JSON from the answer (handles raw JSON, ```json blocks, etc.)
        candidates = []
        # 1. ```json ... ``` or ``` ... ``` code block (greedy inner content)
        for m in _re.finditer(r"```(?:json)?\s*(\{[\s\S]+\})\s*```", answer):
            candidates.append(m.group(1))
        # 2. Raw JSON object — greedy: find largest {...} block containing "mpn"
        for m in _re.finditer(r"\{[\s\S]+\}", answer):
            candidates.append(m.group())

        for raw in candidates:
            try:
                data = json.loads(raw)
                if "mpn" in data:
                    result = self._dict_to_result(data, source="agent_extracted", confidence=0.70)
                    result.agent_trace = trace
                    return result
            except (json.JSONDecodeError, ValueError):
                continue

        # If no JSON, return a minimal result from the text
        if len(answer) > 20:
            return AgentComponentResult(
                mpn=query.upper(),
                name=query,
                manufacturer="",
                category="sensor",
                interface_types=["I2C"],
                electrical_ratings={},
                known_i2c_addresses=[],
                unit_cost_usd=0.0,
                tags=[query.lower()],
                confidence=0.30,
                source="agent_extracted",
                agent_trace=trace,
            )
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _entry_to_result(entry: dict, source: str, confidence: float) -> AgentComponentResult:
        ratings = entry.get("electrical_ratings", {})
        return AgentComponentResult(
            mpn=entry.get("mpn", ""),
            name=entry.get("name", entry.get("mpn", "")),
            manufacturer=entry.get("manufacturer", ""),
            category=entry.get("category", "other"),
            interface_types=entry.get("interface_types", []),
            electrical_ratings=ratings,
            known_i2c_addresses=entry.get("known_i2c_addresses", []),
            unit_cost_usd=entry.get("unit_cost_usd", 0.0),
            tags=entry.get("tags", []),
            confidence=confidence,
            source=source,
            raw=entry,
        )

    @staticmethod
    def _dict_to_result(data: dict, source: str, confidence: float) -> AgentComponentResult:
        return AgentComponentResult(
            mpn=data.get("mpn", data.get("MPN", "")),
            name=data.get("name", data.get("mpn", "")),
            manufacturer=data.get("manufacturer", ""),
            category=data.get("category", "sensor"),
            interface_types=data.get("interface_types", data.get("interfaces", [])),
            electrical_ratings=data.get("electrical_ratings", {}),
            known_i2c_addresses=data.get("known_i2c_addresses", data.get("i2c_addresses", [])),
            unit_cost_usd=float(data.get("unit_cost_usd", 0.0)),
            tags=data.get("tags", []),
            confidence=confidence,
            source=source,
            raw=data,
        )

    @staticmethod
    def _result_to_dict(r: AgentComponentResult) -> dict:
        raw = r.raw or {}
        return {
            "mpn": r.mpn,
            "name": r.name,
            "manufacturer": r.manufacturer,
            "category": r.category,
            "interface_types": r.interface_types,
            "electrical_ratings": r.electrical_ratings,
            "known_i2c_addresses": r.known_i2c_addresses,
            "unit_cost_usd": r.unit_cost_usd,
            "tags": r.tags,
            "confidence": r.confidence,
            "source": r.source,
            # Extended ComponentEntry fields (for future promotion to builtin DB)
            "package": raw.get("package", ""),
            "description": raw.get("description", ""),
            "timing_caps": raw.get("timing_caps", {}),
            "i2c_address_selectable": raw.get("i2c_address_selectable", False),
            "init_contract_coverage": raw.get("init_contract_coverage", False),
            "init_contract_template": raw.get("init_contract_template", {}),
            # Provenance tracking
            "_provenance": {
                "source": r.source,
                "confidence": r.confidence,
                "agent_trace": r.agent_trace,
                "discovered_at": datetime.now(timezone.utc).isoformat(),
                "field_sources": {},
            },
        }

    def _get_gateway(self) -> Any:
        # Explicit None means "no LLM" — skip default lookup
        if self._gateway_explicit_none:
            return None
        gw = self._gateway
        if gw is not None and gw is not KnowledgeAgent._UNSET:
            return gw
        try:
            from llm.gateway import get_default_gateway
            return get_default_gateway()
        except ImportError:
            return None
