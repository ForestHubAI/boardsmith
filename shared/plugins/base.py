# SPDX-License-Identifier: AGPL-3.0-or-later
"""Abstract base class for Boardsmith plugins.

Third-party and enterprise plugins extend this class and register via
the ``boardsmith.plugins`` entry_points group in their ``pyproject.toml``::

    [project.entry-points."boardsmith.plugins"]
    my_plugin = "my_package.plugin:MyPlugin"
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

PLUGIN_API_VERSION = "1.0"


class BoardsmithPlugin(ABC):
    """Base class for all Boardsmith plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier (e.g. 'thermal-modeling')."""

    @property
    def plugin_api_version(self) -> str:
        """Plugin API version this plugin targets."""
        return PLUGIN_API_VERSION

    @property
    def description(self) -> str:
        """Human-readable plugin description."""
        return ""

    @property
    def tier(self) -> str:
        """License tier required: 'community', 'commercial', or 'enterprise'."""
        return "community"

    # ── Lifecycle hooks ──────────────────────────────────────────

    def on_load(self) -> None:
        """Called when the plugin is loaded. Use for initialization."""

    def on_unload(self) -> None:
        """Called when the plugin is unloaded. Use for cleanup."""

    # ── Pipeline hooks ───────────────────────────────────────────

    def post_synthesize(self, hir: dict[str, Any]) -> dict[str, Any]:
        """Called after HIR synthesis. May modify and return the HIR."""
        return hir

    def post_compile(self, firmware_files: dict[str, str]) -> dict[str, str]:
        """Called after firmware compilation. May modify and return files."""
        return firmware_files

    def post_export(self, export_path: str) -> None:
        """Called after KiCad/output export. Use for post-processing."""

    # ── Knowledge hooks ──────────────────────────────────────────

    def register_components(self) -> list[dict[str, Any]]:
        """Return additional component definitions to add to the knowledge DB."""
        return []

    def register_constraints(self) -> list[dict[str, Any]]:
        """Return additional constraint rules for the constraint engine."""
        return []
