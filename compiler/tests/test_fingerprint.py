# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for incremental regeneration fingerprinting."""

from pathlib import Path

from boardsmith_fw.analysis.graph_builder import build_hardware_graph
from boardsmith_fw.codegen.fingerprint import (
    compute_component_fingerprints,
    compute_graph_fingerprint,
    diff_fingerprints,
    load_state,
    save_state,
)
from boardsmith_fw.knowledge.resolver import resolve_knowledge
from boardsmith_fw.parser.eagle_parser import parse_eagle_schematic

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _make_graph(fixture: str, sch: str):
    path = FIXTURES / fixture / sch
    parsed = parse_eagle_schematic(path)
    return build_hardware_graph(str(path), parsed.components, parsed.nets)


class TestGraphFingerprint:
    def test_same_graph_same_fingerprint(self):
        g1 = _make_graph("esp32_bme280_i2c", "esp32_bme280.sch")
        g2 = _make_graph("esp32_bme280_i2c", "esp32_bme280.sch")
        assert compute_graph_fingerprint(g1) == compute_graph_fingerprint(g2)

    def test_different_graph_different_fingerprint(self):
        g1 = _make_graph("esp32_bme280_i2c", "esp32_bme280.sch")
        g2 = _make_graph("esp32_multi_bus", "esp32_multi_bus.sch")
        assert compute_graph_fingerprint(g1) != compute_graph_fingerprint(g2)

    def test_fingerprint_is_string(self):
        g = _make_graph("esp32_bme280_i2c", "esp32_bme280.sch")
        fp = compute_graph_fingerprint(g)
        assert isinstance(fp, str)
        assert len(fp) == 16  # SHA256 truncated to 16 hex chars


class TestComponentFingerprints:
    def test_returns_dict(self):
        graph = _make_graph("esp32_bme280_i2c", "esp32_bme280.sch")
        knowledge = resolve_knowledge(graph)
        fps = compute_component_fingerprints(graph, knowledge)
        assert isinstance(fps, dict)
        assert len(fps) > 0

    def test_includes_all_components(self):
        graph = _make_graph("esp32_bme280_i2c", "esp32_bme280.sch")
        knowledge = resolve_knowledge(graph)
        fps = compute_component_fingerprints(graph, knowledge)
        for comp in graph.components:
            assert comp.id in fps

    def test_deterministic(self):
        graph = _make_graph("esp32_bme280_i2c", "esp32_bme280.sch")
        knowledge = resolve_knowledge(graph)
        fp1 = compute_component_fingerprints(graph, knowledge)
        fp2 = compute_component_fingerprints(graph, knowledge)
        assert fp1 == fp2


class TestDiffFingerprints:
    def test_identical(self):
        fps = {"U1": "abc", "U2": "def"}
        added, changed, removed = diff_fingerprints(fps, fps)
        assert added == []
        assert changed == []
        assert removed == []

    def test_added(self):
        old = {"U1": "abc"}
        new = {"U1": "abc", "U2": "def"}
        added, changed, removed = diff_fingerprints(old, new)
        assert added == ["U2"]
        assert changed == []
        assert removed == []

    def test_removed(self):
        old = {"U1": "abc", "U2": "def"}
        new = {"U1": "abc"}
        added, changed, removed = diff_fingerprints(old, new)
        assert added == []
        assert changed == []
        assert removed == ["U2"]

    def test_changed(self):
        old = {"U1": "abc", "U2": "def"}
        new = {"U1": "abc", "U2": "xyz"}
        added, changed, removed = diff_fingerprints(old, new)
        assert added == []
        assert changed == ["U2"]
        assert removed == []


class TestStatePersistence:
    def test_save_and_load(self, tmp_path):
        save_state(tmp_path, "fp123", {"U1": "a", "U2": "b"}, {"main.c": "main.c"})
        state = load_state(tmp_path)
        assert state["graph_fingerprint"] == "fp123"
        assert state["component_fingerprints"]["U1"] == "a"
        assert state["generated_files"]["main.c"] == "main.c"

    def test_load_empty(self, tmp_path):
        state = load_state(tmp_path)
        assert state == {}
