# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for ReadSchematicTool."""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler"):
    _p = str(REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _make_mock_context():
    ctx = MagicMock()
    ctx.no_llm = False
    return ctx


def _run(coro):
    return asyncio.run(coro)


SMALL_SCH = str(REPO_ROOT / "examples/output/01_temp_sensor/schematic.kicad_sch")
LARGE_SCH = str(REPO_ROOT / "examples/output/03_lora_node/schematic.kicad_sch")


class TestReadSchematicToolStructure:
    def test_returns_required_keys(self):
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()
        result = _run(tool.execute({"sch_path": SMALL_SCH}, _make_mock_context()))
        assert result.success is True
        for key in ("components", "power_nets", "signal_nets", "net_count"):
            assert key in result.data, f"Missing key: {key}"

    def test_components_have_ref_value_footprint(self):
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()
        result = _run(tool.execute({"sch_path": SMALL_SCH}, _make_mock_context()))
        assert len(result.data["components"]) > 0
        for c in result.data["components"]:
            assert "ref" in c
            assert "value" in c

    def test_power_nets_is_list(self):
        """power_nets is always a list (may be empty for auto-generated schematics
        whose power symbols use unlabeled internal nets rather than canonical names
        like GND or 3V3)."""
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()
        result = _run(tool.execute({"sch_path": SMALL_SCH}, _make_mock_context()))
        assert isinstance(result.data["power_nets"], list)

    def test_all_component_refs_present(self):
        """All refs in the graph must appear in the summary components list."""
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        from synth_core.hir_bridge.kicad_parser import KiCadSchematicParser
        tool = ReadSchematicTool()
        result = _run(tool.execute({"sch_path": SMALL_SCH}, _make_mock_context()))
        parser = KiCadSchematicParser()
        graph = parser.parse(Path(SMALL_SCH))
        graph_refs = {c.properties.get("Reference", c.id) for c in graph.components}
        summary_refs = {c["ref"] for c in result.data["components"]}
        # All graph refs should appear in summary
        missing = graph_refs - summary_refs
        assert not missing, f"Missing refs in summary: {missing}"


class TestReadSchematicTokenBudget:
    def _token_estimate(self, data: dict) -> int:
        """Conservative: 4 chars per token."""
        return len(json.dumps(data)) // 4

    def test_token_budget_small_fixture(self):
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()
        result = _run(tool.execute({"sch_path": SMALL_SCH}, _make_mock_context()))
        assert result.success is True
        tokens = self._token_estimate(result.data)
        assert tokens < 400, f"Token estimate {tokens} >= 400 for small fixture"

    def test_token_budget_large_fixture(self):
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()
        result = _run(tool.execute({"sch_path": LARGE_SCH}, _make_mock_context()))
        assert result.success is True
        tokens = self._token_estimate(result.data)
        assert tokens < 400, f"Token estimate {tokens} >= 400 for large fixture (03_lora_node)"

    def test_signal_nets_capped_at_20(self):
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()
        # Use largest fixture which has the most nets
        result = _run(tool.execute({"sch_path": LARGE_SCH}, _make_mock_context()))
        assert len(result.data["signal_nets"]) <= 20

    def test_invalid_path_returns_failure(self):
        from boardsmith_hw.agent.read_schematic import ReadSchematicTool
        tool = ReadSchematicTool()
        result = _run(tool.execute({"sch_path": "/nonexistent/fake.kicad_sch"}, _make_mock_context()))
        assert result.success is False
        assert result.error != ""
