# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for VerifyBootabilityTool — Wave 1 implementation."""
from __future__ import annotations
import asyncio
import datetime
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler"):
    _p = str(REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

FIXTURES = Path(__file__).parent / "fixtures"


def _make_mock_context():
    ctx = MagicMock()
    ctx.no_llm = False
    return ctx


def _run(coro):
    return asyncio.run(coro)


def _make_hir(tmp_path, components=None):
    """Write a minimal hir.json to tmp_path and return its path string."""
    hir_dict = {
        "version": "1.1.0",
        "source": "prompt",
        "components": components or [],
        "nets": [],
        "buses": [],
        "bus_contracts": [],
        "electrical_specs": [],
        "init_contracts": [],
        "power_sequence": {"rails": [], "dependencies": []},
        "constraints": [],
        "bom": [],
        "metadata": {
            "created_at": datetime.datetime.utcnow().isoformat(),
            "track": "B",
            "confidence": {"overall": 0.9, "subscores": None, "explanations": []},
            "assumptions": [],
            "session_id": None,
        },
    }
    p = tmp_path / "hir.json"
    p.write_text(json.dumps(hir_dict))
    return str(p)


def _mcu_component(mpn: str, ref: str = "U1") -> dict:
    return {
        "id": ref,
        "name": mpn,
        "role": "mcu",
        "mpn": mpn,
        "interface_types": [],
        "pins": [],
        "provenance": {"source_type": "builtin_db", "confidence": 0.95, "evidence": []},
    }


def _make_sch(tmp_path) -> str:
    """Write a minimal empty .kicad_sch and return its path string."""
    p = tmp_path / "test.kicad_sch"
    p.write_text("(kicad_sch (version 20230121) (generator test))")
    return str(p)


def _make_graph(net_names=None, components=None):
    """Build a HardwareGraph from dict with the specified nets and components."""
    from synth_core.hir_bridge.graph import HardwareGraph
    return HardwareGraph.from_dict({
        "components": components or [],
        "nets": [{"name": n, "pins": [], "is_power": False, "is_bus": False} for n in (net_names or [])],
    })


# ---------------------------------------------------------------------------
# TestBootabilitySkip
# ---------------------------------------------------------------------------

class TestBootabilitySkip:
    def test_no_mcu_no_violations(self, tmp_path):
        """HIR with no MCU components → success=True, violations=[]."""
        from boardsmith_hw.agent.verify_bootability import VerifyBootabilityTool

        tool = VerifyBootabilityTool()
        hir_path = _make_hir(tmp_path, components=[])
        sch_path = _make_sch(tmp_path)
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        assert result.data["violations"] == []
        assert result.data["violation_count"] == 0

    def test_hir_not_found_returns_failure(self, tmp_path):
        """Missing hir.json → success=False, graceful error."""
        from boardsmith_hw.agent.verify_bootability import VerifyBootabilityTool

        tool = VerifyBootabilityTool()
        sch_path = _make_sch(tmp_path)
        result = _run(tool.execute(
            {"hir_path": str(tmp_path / "nonexistent.json"), "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is False
        assert result.error


# ---------------------------------------------------------------------------
# TestResetCheck
# ---------------------------------------------------------------------------

class TestResetCheck:
    def test_missing_reset_net_is_warning(self, tmp_path):
        """MCU in HIR, no NRST/RESET/RST/EN net → missing_reset_circuit warning."""
        from boardsmith_hw.agent.verify_bootability import VerifyBootabilityTool

        tool = VerifyBootabilityTool()
        hir_path = _make_hir(tmp_path, components=[_mcu_component("STM32F103C8")])
        sch_path = _make_sch(tmp_path)
        # Graph with no reset-related nets
        mock_graph = _make_graph(net_names=["MOSI", "MISO", "SWDIO", "SWDCLK"])
        with patch(
            "synth_core.hir_bridge.kicad_parser.KiCadSchematicParser.parse",
            return_value=mock_graph,
        ):
            result = _run(tool.execute(
                {"hir_path": hir_path, "sch_path": sch_path},
                _make_mock_context(),
            ))
        assert result.success is True
        violations = result.data["violations"]
        reset_viols = [v for v in violations if v["type"] == "missing_reset_circuit"]
        assert len(reset_viols) >= 1
        assert reset_viols[0]["severity"] == "warning"

    def test_reset_net_present_no_violation(self, tmp_path):
        """Net named NRST present → no missing_reset_circuit violation."""
        from boardsmith_hw.agent.verify_bootability import VerifyBootabilityTool

        tool = VerifyBootabilityTool()
        hir_path = _make_hir(tmp_path, components=[_mcu_component("STM32F103C8")])
        sch_path = _make_sch(tmp_path)
        mock_graph = _make_graph(net_names=["NRST", "SWDIO", "SWDCLK"])
        with patch(
            "synth_core.hir_bridge.kicad_parser.KiCadSchematicParser.parse",
            return_value=mock_graph,
        ):
            result = _run(tool.execute(
                {"hir_path": hir_path, "sch_path": sch_path},
                _make_mock_context(),
            ))
        assert result.success is True
        violations = result.data["violations"]
        reset_viols = [v for v in violations if v["type"] == "missing_reset_circuit"]
        assert len(reset_viols) == 0


# ---------------------------------------------------------------------------
# TestSWDCheck
# ---------------------------------------------------------------------------

class TestSWDCheck:
    def test_stm32_missing_swd_is_warning(self, tmp_path):
        """STM32 MCU, no SWDIO/SWDCLK nets → missing_programming_interface warning."""
        from boardsmith_hw.agent.verify_bootability import VerifyBootabilityTool

        tool = VerifyBootabilityTool()
        hir_path = str(FIXTURES / "hir_stm32_swd.json")
        sch_path = _make_sch(tmp_path)
        # Only reset net — no SWD
        mock_graph = _make_graph(net_names=["NRST"])
        with patch(
            "synth_core.hir_bridge.kicad_parser.KiCadSchematicParser.parse",
            return_value=mock_graph,
        ):
            result = _run(tool.execute(
                {"hir_path": hir_path, "sch_path": sch_path},
                _make_mock_context(),
            ))
        assert result.success is True
        violations = result.data["violations"]
        swd_viols = [v for v in violations if v["type"] == "missing_programming_interface"]
        assert len(swd_viols) >= 1
        assert swd_viols[0]["severity"] == "warning"

    def test_swd_present_no_violation(self, tmp_path):
        """SWDIO and SWDCLK nets present → no missing_programming_interface violation."""
        from boardsmith_hw.agent.verify_bootability import VerifyBootabilityTool

        tool = VerifyBootabilityTool()
        hir_path = str(FIXTURES / "hir_stm32_swd.json")
        sch_path = _make_sch(tmp_path)
        mock_graph = _make_graph(net_names=["NRST", "SWDIO", "SWDCLK"])
        with patch(
            "synth_core.hir_bridge.kicad_parser.KiCadSchematicParser.parse",
            return_value=mock_graph,
        ):
            result = _run(tool.execute(
                {"hir_path": hir_path, "sch_path": sch_path},
                _make_mock_context(),
            ))
        assert result.success is True
        violations = result.data["violations"]
        swd_viols = [v for v in violations if v["type"] == "missing_programming_interface"]
        assert len(swd_viols) == 0


# ---------------------------------------------------------------------------
# TestClockCheck
# ---------------------------------------------------------------------------

class TestClockCheck:
    def test_esp32_skips_crystal_check(self, tmp_path):
        """ESP32 MCU → no missing_crystal_load_caps violation at all."""
        from boardsmith_hw.agent.verify_bootability import VerifyBootabilityTool

        tool = VerifyBootabilityTool()
        hir_path = _make_hir(tmp_path, components=[_mcu_component("ESP32-WROOM-32")])
        sch_path = _make_sch(tmp_path)
        # Graph with EN reset net but no crystal/caps — ESP32 should still pass
        mock_graph = _make_graph(net_names=["EN"])
        with patch(
            "synth_core.hir_bridge.kicad_parser.KiCadSchematicParser.parse",
            return_value=mock_graph,
        ):
            result = _run(tool.execute(
                {"hir_path": hir_path, "sch_path": sch_path},
                _make_mock_context(),
            ))
        assert result.success is True
        violations = result.data["violations"]
        crystal_viols = [v for v in violations if v["type"] == "missing_crystal_load_caps"]
        assert len(crystal_viols) == 0

    def test_stm32_missing_crystal_is_warning(self, tmp_path):
        """STM32 MCU, no crystal/load caps found → missing_crystal_load_caps warning."""
        from boardsmith_hw.agent.verify_bootability import VerifyBootabilityTool

        tool = VerifyBootabilityTool()
        hir_path = _make_hir(tmp_path, components=[_mcu_component("STM32F103C8")])
        sch_path = _make_sch(tmp_path)
        # Only reset + SWD nets, no passives with crystal values in graph
        mock_graph = _make_graph(net_names=["NRST", "SWDIO", "SWDCLK"])
        with patch(
            "synth_core.hir_bridge.kicad_parser.KiCadSchematicParser.parse",
            return_value=mock_graph,
        ):
            result = _run(tool.execute(
                {"hir_path": hir_path, "sch_path": sch_path},
                _make_mock_context(),
            ))
        assert result.success is True
        violations = result.data["violations"]
        crystal_viols = [v for v in violations if v["type"] == "missing_crystal_load_caps"]
        assert len(crystal_viols) >= 1
        assert crystal_viols[0]["severity"] == "warning"
