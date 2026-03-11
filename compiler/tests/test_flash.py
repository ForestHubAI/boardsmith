# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for flash and serial monitor commands."""

from boardsmith_fw.commands.flash import _detect_port


class TestDetectPort:
    def test_returns_string(self):
        port = _detect_port()
        assert isinstance(port, str)
        assert len(port) > 0

    def test_fallback_port(self):
        port = _detect_port()
        # Should return at least the fallback
        assert port is not None


class TestFlashImport:
    def test_flash_import(self):
        """Verify flash module imports correctly."""
        from boardsmith_fw.commands.flash import run_flash, run_monitor

        assert callable(run_flash)
        assert callable(run_monitor)
