# SPDX-License-Identifier: AGPL-3.0-or-later
"""LLM configuration — reads from environment variables or ~/.boardsmith/llm.toml.

Priority order (highest wins):
  1. Environment variables  (ANTHROPIC_API_KEY, BOARDSMITH_NO_LLM, ...)
  2. ~/.boardsmith/llm.toml   (user config file)
  3. Compiled-in defaults

TOML file format::

    [llm]
    anthropic_api_key = "sk-ant-..."
    openai_api_key    = "sk-..."
    ollama_base_url   = "http://localhost:11434"
    no_llm            = false
    budget_limit_usd  = 1.00

    [llm.models]        # optional per-task model overrides
    intent_parse = "claude-haiku-4-5-20251001"
    code_gen     = "gpt-4o"

    [llm.search]        # optional search provider keys
    tavily_api_key       = "tvly-..."
    nexar_client_id      = "..."
    nexar_client_secret  = "..."
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TOML parser — stdlib tomllib (Python 3.11+) with tomli fallback
# ---------------------------------------------------------------------------

try:
    import tomllib as _tomllib          # Python >= 3.11
except ImportError:
    try:
        import tomli as _tomllib        # pip install tomli  (Python 3.10)
    except ImportError:
        _tomllib = None                 # type: ignore[assignment]

_DEFAULT_CONFIG_PATH = Path.home() / ".boardsmith" / "llm.toml"


def _load_toml(path: Path) -> dict:
    """Load a TOML file. Returns empty dict if file missing or TOML unavailable."""
    if _tomllib is None or not path.exists():
        return {}
    try:
        with path.open("rb") as fh:
            return _tomllib.loads(fh.read().decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------


@dataclass
class LLMConfig:
    """Runtime configuration for the LLM Gateway."""

    # Provider API keys
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # Behaviour flags
    no_llm: bool = False                    # --no-llm: skip all LLM calls
    budget_limit_usd: float | None = None   # Session budget cap

    # Default model overrides (empty = use router defaults)
    default_models: dict[str, str] = field(default_factory=dict)

    # Search provider keys (used by web_search / search_octopart tools)
    tavily_api_key: str = ""
    nexar_client_id: str = ""
    nexar_client_secret: str = ""

    # ------------------------------------------------------------------
    # Factory constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls, config_path: Path | None = None) -> "LLMConfig":
        """Build config from TOML file + environment variables.

        Environment variables always override the TOML file.

        Args:
            config_path: Path to llm.toml. Defaults to ~/.boardsmith/llm.toml.
        """
        # 1. TOML base
        toml_data = _load_toml(config_path or _DEFAULT_CONFIG_PATH)
        llm_section: dict = toml_data.get("llm", {})
        models_section: dict = llm_section.pop("models", {})
        search_section: dict = llm_section.pop("search", {})

        # 2. Env vars override TOML
        anthropic_key = (
            os.environ.get("ANTHROPIC_API_KEY")
            or llm_section.get("anthropic_api_key", "")
        )
        openai_key = (
            os.environ.get("OPENAI_API_KEY")
            or llm_section.get("openai_api_key", "")
        )
        ollama_url = (
            os.environ.get("OLLAMA_BASE_URL")
            or llm_section.get("ollama_base_url", "http://localhost:11434")
        )

        # no_llm: env var wins; then TOML; then default False
        env_no_llm = os.environ.get("BOARDSMITH_NO_LLM", "")
        if env_no_llm:
            no_llm = env_no_llm.lower() in ("1", "true", "yes")
        else:
            no_llm = bool(llm_section.get("no_llm", False))

        # budget_limit_usd
        env_budget = os.environ.get("BOARDSMITH_BUDGET_USD")
        if env_budget:
            budget = _parse_float(env_budget)
        else:
            raw = llm_section.get("budget_limit_usd")
            budget = float(raw) if raw is not None else None

        # Search provider keys
        tavily_key = (
            os.environ.get("TAVILY_API_KEY")
            or search_section.get("tavily_api_key", "")
        )
        nexar_id = (
            os.environ.get("NEXAR_CLIENT_ID")
            or search_section.get("nexar_client_id", "")
        )
        nexar_secret = (
            os.environ.get("NEXAR_CLIENT_SECRET")
            or search_section.get("nexar_client_secret", "")
        )

        return cls(
            anthropic_api_key=anthropic_key,
            openai_api_key=openai_key,
            ollama_base_url=ollama_url,
            no_llm=no_llm,
            budget_limit_usd=budget,
            default_models=dict(models_section),
            tavily_api_key=tavily_key,
            nexar_client_id=nexar_id,
            nexar_client_secret=nexar_secret,
        )

    @classmethod
    def no_llm_mode(cls) -> "LLMConfig":
        """Create a config that disables all LLM calls (for testing)."""
        return cls(no_llm=True)

    @classmethod
    def from_toml(cls, path: Path) -> "LLMConfig":
        """Load config from a specific TOML file (env vars still override)."""
        return cls.from_env(config_path=path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)

    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    def has_ollama(self) -> bool:
        """Ollama is always 'available' if configured — no key needed."""
        return bool(self.ollama_base_url)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
