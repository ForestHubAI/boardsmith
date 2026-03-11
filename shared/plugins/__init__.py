# SPDX-License-Identifier: AGPL-3.0-or-later
"""Boardsmith plugin system — entry_points-based discovery and loading."""
from __future__ import annotations

from shared.plugins.base import BoardsmithPlugin
from shared.plugins.loader import discover_plugins, get_plugin

__all__ = ["BoardsmithPlugin", "discover_plugins", "get_plugin"]
