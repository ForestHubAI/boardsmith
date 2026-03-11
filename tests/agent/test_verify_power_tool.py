# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for VerifyPowerTool — Wave 1 implementation."""
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


def _hir_comp(ref: str, role: str, mpn: str = "GENERIC") -> dict:
    return {
        "id": ref,
        "name": ref,
        "role": role,
        "mpn": mpn,
        "interface_types": [],
        "pins": [],
        "provenance": {"source_type": "builtin_db", "confidence": 0.9, "evidence": []},
    }


def _make_sch(tmp_path) -> str:
    """Write a minimal empty .kicad_sch and return its path string."""
    p = tmp_path / "test.kicad_sch"
    p.write_text("(kicad_sch (version 20230121) (generator test))")
    return str(p)


def _make_graph(components=None, nets=None):
    """Build a HardwareGraph from dict spec.

    components: list of dicts with keys: id, name, mpn, role, pins
        Each pin dict: {name, number, electrical_type}
    nets: list of dicts with keys: name, pins (list of [comp_id, pin_name]), is_power
    """
    from synth_core.hir_bridge.graph import HardwareGraph, GraphComponent, GraphPin, GraphNet

    graph = HardwareGraph()
    for c in (components or []):
        pins = [
            GraphPin(name=p["name"], number=p.get("number", ""), electrical_type=p.get("electrical_type", ""))
            for p in c.get("pins", [])
        ]
        graph.components.append(GraphComponent(
            id=c["id"],
            name=c.get("name", c["id"]),
            mpn=c.get("mpn", ""),
            role=c.get("role", "other"),
            pins=pins,
        ))
    for n in (nets or []):
        pins = [(t[0], t[1]) for t in n.get("pins", [])]
        graph.nets.append(GraphNet(
            name=n["name"],
            pins=pins,
            is_power=n.get("is_power", False),
        ))
    return graph


# ---------------------------------------------------------------------------
# TestVerifyPowerTool
# ---------------------------------------------------------------------------

class TestVerifyPowerTool:
    def test_returns_violations_list(self, tmp_path):
        """Any valid input → result.success=True, result.data['violations'] is list."""
        from boardsmith_hw.agent.verify_power import VerifyPowerTool

        tool = VerifyPowerTool()
        hir_path = _make_hir(tmp_path, components=[])
        sch_path = _make_sch(tmp_path)
        mock_graph = _make_graph()
        with patch(
            "synth_core.hir_bridge.kicad_parser.KiCadSchematicParser.parse",
            return_value=mock_graph,
        ):
            result = _run(tool.execute(
                {"hir_path": hir_path, "sch_path": sch_path},
                _make_mock_context(),
            ))
        assert result.success is True
        assert "violations" in result.data
        assert isinstance(result.data["violations"], list)

    def test_hir_not_found_returns_failure(self, tmp_path):
        """Missing hir.json → success=False, graceful error."""
        from boardsmith_hw.agent.verify_power import VerifyPowerTool

        tool = VerifyPowerTool()
        sch_path = _make_sch(tmp_path)
        result = _run(tool.execute(
            {"hir_path": str(tmp_path / "nonexistent.json"), "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is False
        assert result.error


# ---------------------------------------------------------------------------
# TestPowerPinCheck
# ---------------------------------------------------------------------------

class TestPowerPinCheck:
    def test_unconnected_vcc_is_error(self, tmp_path):
        """Component has power_in pin NOT in any net.pins → unconnected_power_pin error."""
        from boardsmith_hw.agent.verify_power import VerifyPowerTool

        tool = VerifyPowerTool()
        # Empty HIR (no MCU needed for this check — it operates on graph only)
        hir_path = _make_hir(tmp_path, components=[])
        sch_path = _make_sch(tmp_path)
        mock_graph = _make_graph(
            components=[
                {
                    "id": "U1",
                    "name": "ESP32",
                    "role": "mcu",
                    "mpn": "ESP32-WROOM-32",
                    "pins": [
                        {"name": "VCC", "number": "1", "electrical_type": "power_in"},
                    ],
                }
            ],
            nets=[
                # VCC pin is NOT in any net
                {"name": "GND", "pins": [], "is_power": True},
            ],
        )
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
        power_viols = [v for v in violations if v["type"] == "unconnected_power_pin"]
        assert len(power_viols) >= 1
        assert power_viols[0]["severity"] == "error"
        assert power_viols[0]["ref"] == "U1"

    def test_connected_vcc_no_violation(self, tmp_path):
        """power_in pin IS in a net.pins → no unconnected_power_pin violation."""
        from boardsmith_hw.agent.verify_power import VerifyPowerTool

        tool = VerifyPowerTool()
        hir_path = _make_hir(tmp_path, components=[])
        sch_path = _make_sch(tmp_path)
        mock_graph = _make_graph(
            components=[
                {
                    "id": "U1",
                    "name": "ESP32",
                    "role": "mcu",
                    "mpn": "ESP32-WROOM-32",
                    "pins": [
                        {"name": "VCC", "number": "1", "electrical_type": "power_in"},
                    ],
                }
            ],
            nets=[
                # VCC pin IS in the VCC net
                {"name": "VCC", "pins": [["U1", "VCC"]], "is_power": True},
            ],
        )
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
        power_viols = [v for v in violations if v["type"] == "unconnected_power_pin"]
        assert len(power_viols) == 0


# ---------------------------------------------------------------------------
# TestRegulatorCheck
# ---------------------------------------------------------------------------

class TestRegulatorCheck:
    def test_missing_regulator_is_warning(self, tmp_path):
        """HIR has MCU component + graph has no role='power' component → missing_voltage_regulator warning."""
        from boardsmith_hw.agent.verify_power import VerifyPowerTool

        tool = VerifyPowerTool()
        hir_path = _make_hir(tmp_path, components=[_hir_comp("U1", "mcu", "STM32F103")])
        sch_path = _make_sch(tmp_path)
        # Graph has only an MCU, no power component
        mock_graph = _make_graph(
            components=[
                {"id": "U1", "name": "STM32", "role": "mcu", "mpn": "STM32F103", "pins": []}
            ]
        )
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
        reg_viols = [v for v in violations if v["type"] == "missing_voltage_regulator"]
        assert len(reg_viols) >= 1
        assert reg_viols[0]["severity"] == "warning"

    def test_regulator_present_no_violation(self, tmp_path):
        """Graph has role='power' component → no missing_voltage_regulator violation."""
        from boardsmith_hw.agent.verify_power import VerifyPowerTool

        tool = VerifyPowerTool()
        hir_path = _make_hir(tmp_path, components=[_hir_comp("U1", "mcu", "STM32F103")])
        sch_path = _make_sch(tmp_path)
        mock_graph = _make_graph(
            components=[
                {"id": "U1", "name": "STM32", "role": "mcu", "mpn": "STM32F103", "pins": []},
                {"id": "U2", "name": "LDO", "role": "power", "mpn": "AMS1117-3.3", "pins": []},
            ]
        )
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
        reg_viols = [v for v in violations if v["type"] == "missing_voltage_regulator"]
        assert len(reg_viols) == 0


# ---------------------------------------------------------------------------
# TestBulkCapCheck
# ---------------------------------------------------------------------------

class TestBulkCapCheck:
    def test_missing_bulk_cap_is_warning(self, tmp_path):
        """Graph has role='power' component + no passive with 10uF/47uF/100uF → missing_bulk_cap warning."""
        from boardsmith_hw.agent.verify_power import VerifyPowerTool

        tool = VerifyPowerTool()
        hir_path = _make_hir(tmp_path, components=[_hir_comp("U1", "mcu")])
        sch_path = _make_sch(tmp_path)
        # Regulator present but only small caps (100nF decoupling, no bulk)
        mock_graph = _make_graph(
            components=[
                {"id": "U2", "name": "AMS1117", "role": "power", "mpn": "AMS1117-3.3", "pins": []},
                {"id": "C1", "name": "100nF", "role": "passive", "mpn": "100nF", "pins": []},
            ]
        )
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
        bulk_viols = [v for v in violations if v["type"] == "missing_bulk_cap"]
        assert len(bulk_viols) >= 1
        assert bulk_viols[0]["severity"] == "warning"

    def test_bulk_cap_present_no_violation(self, tmp_path):
        """Passive with '10uF' value present → no missing_bulk_cap violation."""
        from boardsmith_hw.agent.verify_power import VerifyPowerTool

        tool = VerifyPowerTool()
        hir_path = _make_hir(tmp_path, components=[_hir_comp("U1", "mcu")])
        sch_path = _make_sch(tmp_path)
        mock_graph = _make_graph(
            components=[
                {"id": "U2", "name": "AMS1117", "role": "power", "mpn": "AMS1117-3.3", "pins": []},
                {"id": "C1", "name": "10uF", "role": "passive", "mpn": "10uF", "pins": []},
            ]
        )
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
        bulk_viols = [v for v in violations if v["type"] == "missing_bulk_cap"]
        assert len(bulk_viols) == 0
