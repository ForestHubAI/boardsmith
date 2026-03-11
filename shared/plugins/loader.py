# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plugin discovery and loading via Python entry_points.

Plugins register under the ``boardsmith.plugins`` entry_points group::

    [project.entry-points."boardsmith.plugins"]
    my_plugin = "my_package.plugin:MyPlugin"

Usage::

    from shared.plugins import discover_plugins, get_plugin

    plugins = discover_plugins()
    for p in plugins:
        hir = p.post_synthesize(hir)
"""
from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

from shared.plugins.base import PLUGIN_API_VERSION, BoardsmithPlugin

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "boardsmith.plugins"

_loaded_plugins: dict[str, BoardsmithPlugin] = {}


def _get_entry_points() -> list:
    """Load entry points, compatible with Python 3.10+."""
    if sys.version_info >= (3, 12):
        from importlib.metadata import entry_points
        return list(entry_points(group=ENTRY_POINT_GROUP))

    # Python 3.10–3.11
    from importlib.metadata import entry_points as _ep
    eps = _ep()
    if isinstance(eps, dict):
        return list(eps.get(ENTRY_POINT_GROUP, []))
    # SelectableGroups (Python 3.10/3.11)
    return list(eps.select(group=ENTRY_POINT_GROUP))


def discover_plugins() -> list[BoardsmithPlugin]:
    """Discover and load all installed Boardsmith plugins.

    Returns a list of instantiated plugin objects. Plugins whose API version
    does not match the current PLUGIN_API_VERSION are skipped with a warning.
    """
    _loaded_plugins.clear()
    plugins: list[BoardsmithPlugin] = []

    for ep in _get_entry_points():
        try:
            plugin_cls = ep.load()

            if not (isinstance(plugin_cls, type) and issubclass(plugin_cls, BoardsmithPlugin)):
                logger.warning("Plugin %r is not a BoardsmithPlugin subclass — skipping", ep.name)
                continue

            instance = plugin_cls()

            # Version compatibility check
            major_required = PLUGIN_API_VERSION.split(".")[0]
            major_plugin = instance.plugin_api_version.split(".")[0]
            if major_required != major_plugin:
                logger.warning(
                    "Plugin %r targets API v%s (current: v%s) — skipping",
                    instance.name,
                    instance.plugin_api_version,
                    PLUGIN_API_VERSION,
                )
                continue

            instance.on_load()
            _loaded_plugins[instance.name] = instance
            plugins.append(instance)
            logger.info("Loaded plugin: %s (tier=%s)", instance.name, instance.tier)

        except Exception:
            logger.exception("Failed to load plugin %r", ep.name)

    return plugins


def get_plugin(name: str) -> BoardsmithPlugin | None:
    """Get a loaded plugin by name."""
    return _loaded_plugins.get(name)


def unload_all() -> None:
    """Unload all plugins, calling on_unload() for each."""
    for plugin in _loaded_plugins.values():
        try:
            plugin.on_unload()
        except Exception:
            logger.exception("Error unloading plugin %r", plugin.name)
    _loaded_plugins.clear()
