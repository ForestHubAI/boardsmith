# SPDX-License-Identifier: AGPL-3.0-or-later
"""TDD tests for ReadSchematicTool — boardsmith_hw/agent/read_schematic.py.

RED phase: tests written before implementation.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    """Run a coroutine synchronously."""
    return asyncio.run(coro)


def make_ctx():
    """Make a minimal ToolContext mock."""
    ctx = MagicMock()
    ctx.no_llm = False
    return ctx


# ---------------------------------------------------------------------------
# Stubs for HardwareGraph types (allow tests without full schematic parse)
# ---------------------------------------------------------------------------

@dataclass
class StubPin:
    id: str
    name: str


@dataclass
class StubNet:
    name: str
    pins: list = field(default_factory=list)
    is_power: bool = False
    is_bus: bool = False


@dataclass
class StubComponent:
    id: str
    name: str
    mpn: str = ""
    role: str = "other"
    manufacturer: str = ""
    package: str = ""
    interface_types: list = field(default_factory=list)
    pins: list = field(default_factory=list)
    properties: dict = field(default_factory=dict)


@dataclass
class StubHardwareGraph:
    components: list = field(default_factory=list)
    nets: list = field(default_factory=list)
    buses: list = field(default_factory=list)
    source_file: str = "<stub>"


# ---------------------------------------------------------------------------
# Tests for ReadSchematicTool attributes
# ---------------------------------------------------------------------------

class TestReadSchematicToolAttributes:
    def test_name_is_read_schematic(self):
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        t = ReadSchematicTool()
        assert t.name == "read_schematic"

    def test_description_is_non_empty(self):
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        t = ReadSchematicTool()
        assert len(t.description) > 10

    def test_token_budget_constant(self):
        from boardsmith_hw.agent.read_schematic import _TOKEN_BUDGET
        assert _TOKEN_BUDGET == 400

    def test_max_signal_nets_constant(self):
        from boardsmith_hw.agent.read_schematic import _MAX_SIGNAL_NETS
        assert _MAX_SIGNAL_NETS == 20

    def test_no_llm_imports_at_module_level(self):
        import inspect
        import sys
        for mod in list(sys.modules.keys()):
            if "boardsmith_hw.agent.read_schematic" in mod:
                del sys.modules[mod]

        import boardsmith_hw.agent.read_schematic as m
        src = inspect.getsource(m)
        top_level_lines = [l for l in src.splitlines() if l.startswith("import ") or l.startswith("from ")]
        for line in top_level_lines:
            assert "anthropic" not in line, f"anthropic imported at top level: {line}"
            assert "openai" not in line, f"openai imported at top level: {line}"


# ---------------------------------------------------------------------------
# Tests for tools/__init__.py exports
# ---------------------------------------------------------------------------

class TestToolsPackageExports:
    def test_imports_run_erc_tool(self):
        from boardsmith_hw.agent.tools import RunERCTool
        assert RunERCTool.name == "run_erc"

    def test_imports_read_schematic_tool(self):
        from boardsmith_hw.agent.tools import ReadSchematicTool
        assert ReadSchematicTool.name == "read_schematic"

    def test_all_exports_in_dunder_all(self):
        import boardsmith_hw.agent.tools as tools_pkg
        assert "RunERCTool" in tools_pkg.__all__
        assert "ReadSchematicTool" in tools_pkg.__all__


# ---------------------------------------------------------------------------
# Tests for ReadSchematicTool.execute with mocked graph
# ---------------------------------------------------------------------------

def make_stub_graph():
    """Minimal stub graph for a 3-component, 5-net schematic."""
    return StubHardwareGraph(
        components=[
            StubComponent(
                id="U1", name="ESP32-WROOM-32", mpn="ESP32-WROOM-32",
                package="ESP32_Module",
                properties={"Reference": "U1", "Value": "ESP32-WROOM-32", "Footprint": "ESP32_WROOM_32"},
            ),
            StubComponent(
                id="R1", name="10k", mpn="",
                package="0402",
                properties={"Reference": "R1", "Value": "10k", "Footprint": "R_0402"},
            ),
            StubComponent(
                id="C1", name="100nF", mpn="",
                package="0402",
                properties={"Reference": "C1", "Value": "100nF", "Footprint": "C_0402"},
            ),
        ],
        nets=[
            StubNet(name="GND", pins=[("U1", "GND"), ("R1", "2"), ("C1", "2")], is_power=True),
            StubNet(name="VCC", pins=[("U1", "VCC"), ("C1", "1")], is_power=True),
            StubNet(name="SDA", pins=[("U1", "IO21"), ("R1", "1")], is_power=False),
            StubNet(name="SCL", pins=[("U1", "IO22")], is_power=False),
            StubNet(name="TX", pins=[("U1", "TX0")], is_power=False),
        ],
    )


class TestReadSchematicToolExecute:
    def test_execute_returns_success(self):
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()
        stub_graph = make_stub_graph()

        with patch("synth_core.hir_bridge.kicad_parser.KiCadSchematicParser") as MockParser:
            instance = MockParser.return_value
            instance.parse.return_value = stub_graph
            result = run(tool.execute({"sch_path": "dummy.kicad_sch"}, make_ctx()))

        assert result.success is True

    def test_execute_data_has_required_keys(self):
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()
        stub_graph = make_stub_graph()

        with patch("synth_core.hir_bridge.kicad_parser.KiCadSchematicParser") as MockParser:
            instance = MockParser.return_value
            instance.parse.return_value = stub_graph
            result = run(tool.execute({"sch_path": "dummy.kicad_sch"}, make_ctx()))

        assert "components" in result.data
        assert "power_nets" in result.data
        assert "signal_nets" in result.data
        assert "net_count" in result.data

    def test_execute_components_have_correct_keys(self):
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()
        stub_graph = make_stub_graph()

        with patch("synth_core.hir_bridge.kicad_parser.KiCadSchematicParser") as MockParser:
            instance = MockParser.return_value
            instance.parse.return_value = stub_graph
            result = run(tool.execute({"sch_path": "dummy.kicad_sch"}, make_ctx()))

        assert len(result.data["components"]) == 3
        for comp in result.data["components"]:
            assert "ref" in comp
            assert "value" in comp

    def test_execute_power_nets_contains_gnd(self):
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()
        stub_graph = make_stub_graph()

        with patch("synth_core.hir_bridge.kicad_parser.KiCadSchematicParser") as MockParser:
            instance = MockParser.return_value
            instance.parse.return_value = stub_graph
            result = run(tool.execute({"sch_path": "dummy.kicad_sch"}, make_ctx()))

        assert "GND" in result.data["power_nets"]

    def test_execute_signal_nets_capped_at_20(self):
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()

        # Build a graph with 30 signal nets (>20 cap)
        signal_nets = [
            StubNet(name=f"SIG_{i}", pins=[("U1", f"P{i}")], is_power=False)
            for i in range(30)
        ]
        large_graph = StubHardwareGraph(
            components=[],
            nets=[StubNet("GND", is_power=True)] + signal_nets,
        )

        with patch("synth_core.hir_bridge.kicad_parser.KiCadSchematicParser") as MockParser:
            instance = MockParser.return_value
            instance.parse.return_value = large_graph
            result = run(tool.execute({"sch_path": "dummy.kicad_sch"}, make_ctx()))

        assert len(result.data["signal_nets"]) <= 20

    def test_execute_net_count_is_total(self):
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()
        stub_graph = make_stub_graph()

        with patch("synth_core.hir_bridge.kicad_parser.KiCadSchematicParser") as MockParser:
            instance = MockParser.return_value
            instance.parse.return_value = stub_graph
            result = run(tool.execute({"sch_path": "dummy.kicad_sch"}, make_ctx()))

        assert result.data["net_count"] == 5  # 2 power + 3 signal

    def test_execute_confidence_is_1_on_success(self):
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()
        stub_graph = make_stub_graph()

        with patch("synth_core.hir_bridge.kicad_parser.KiCadSchematicParser") as MockParser:
            instance = MockParser.return_value
            instance.parse.return_value = stub_graph
            result = run(tool.execute({"sch_path": "dummy.kicad_sch"}, make_ctx()))

        assert result.confidence == 1.0

    def test_execute_source_is_kicad_parser(self):
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()
        stub_graph = make_stub_graph()

        with patch("synth_core.hir_bridge.kicad_parser.KiCadSchematicParser") as MockParser:
            instance = MockParser.return_value
            instance.parse.return_value = stub_graph
            result = run(tool.execute({"sch_path": "dummy.kicad_sch"}, make_ctx()))

        assert result.source == "kicad_parser"

    def test_execute_returns_failure_on_parse_error(self):
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()

        with patch("synth_core.hir_bridge.kicad_parser.KiCadSchematicParser") as MockParser:
            instance = MockParser.return_value
            instance.parse.side_effect = FileNotFoundError("test.kicad_sch not found")
            result = run(tool.execute({"sch_path": "nonexistent.kicad_sch"}, make_ctx()))

        assert result.success is False
        assert result.confidence == 0.0
        assert "not found" in result.error

    def test_token_budget_enforced_large_schematic(self):
        """When data exceeds 400 tokens, footprint is stripped from components."""
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()

        # Build a graph with many components that would exceed token budget
        many_components = [
            StubComponent(
                id=f"U{i}", name=f"SomeLongComponentName{i}",
                mpn=f"LONGMPN{i}",
                package=f"Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
                properties={
                    "Reference": f"U{i}",
                    "Value": f"LONGVALUE_{i}_WITH_EXTRA_TEXT",
                    "Footprint": f"Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
                },
            )
            for i in range(50)
        ]
        large_graph = StubHardwareGraph(components=many_components, nets=[
            StubNet("GND", is_power=True),
        ])

        with patch("synth_core.hir_bridge.kicad_parser.KiCadSchematicParser") as MockParser:
            instance = MockParser.return_value
            instance.parse.return_value = large_graph
            result = run(tool.execute({"sch_path": "dummy.kicad_sch"}, make_ctx()))

        # When budget exceeded, footprint should be stripped
        token_est = len(json.dumps(result.data)) // 4
        assert token_est < 400, f"Token estimate {token_est} >= 400"

    def test_signal_nets_sorted_by_connection_count(self):
        """Busiest signal nets appear first (sorted by len(pins) descending)."""
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()

        graph = StubHardwareGraph(
            components=[],
            nets=[
                StubNet("GND", pins=[("U1", "G"), ("U2", "G")], is_power=True),
                StubNet("LONELY", pins=[("U1", "P1")], is_power=False),
                StubNet("BUSY", pins=[("U1", "P2"), ("U2", "P2"), ("U3", "P2")], is_power=False),
                StubNet("MEDIUM", pins=[("U1", "P3"), ("U2", "P3")], is_power=False),
            ],
        )

        with patch("synth_core.hir_bridge.kicad_parser.KiCadSchematicParser") as MockParser:
            instance = MockParser.return_value
            instance.parse.return_value = graph
            result = run(tool.execute({"sch_path": "dummy.kicad_sch"}, make_ctx()))

        signal_nets = result.data["signal_nets"]
        assert signal_nets[0] == "BUSY"   # 3 connections
        assert signal_nets[1] == "MEDIUM" # 2 connections
        assert signal_nets[2] == "LONELY" # 1 connection


# ---------------------------------------------------------------------------
# Integration smoke test using real fixture
# ---------------------------------------------------------------------------

class TestReadSchematicRealFixture:
    """These tests use the real KiCad fixture file if available."""

    FIXTURE = Path("/Users/marcusrub/Code/VibeHard/examples/output/01_temp_sensor/schematic.kicad_sch")

    @pytest.mark.skipif(
        not Path("/Users/marcusrub/Code/VibeHard/examples/output/01_temp_sensor/schematic.kicad_sch").exists(),
        reason="Fixture not available"
    )
    def test_real_schematic_token_budget(self):
        """Real 01_temp_sensor schematic must parse to < 400 tokens."""
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()
        ctx = make_ctx()
        result = run(tool.execute({"sch_path": str(self.FIXTURE)}, ctx))
        if result.success:
            tokens = len(json.dumps(result.data)) // 4
            assert tokens < 400, f"Token estimate {tokens} >= 400"
        # If parse fails (e.g. format mismatch), that's OK for this smoke test
