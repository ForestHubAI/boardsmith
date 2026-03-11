# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for RP2040/Pico SDK support."""

from pathlib import Path

from boardsmith_fw.analysis.graph_builder import build_hardware_graph
from boardsmith_fw.codegen.llm_wrapper import GenerationRequest, _generate_from_templates
from boardsmith_fw.knowledge.resolver import resolve_knowledge
from boardsmith_fw.models.hardware_graph import MCUFamily
from boardsmith_fw.parser.eagle_parser import parse_eagle_schematic

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _make_rp2040_graph():
    path = FIXTURES / "rp2040_bme280_i2c" / "rp2040_bme280.sch"
    parsed = parse_eagle_schematic(path)
    return build_hardware_graph(str(path), parsed.components, parsed.nets)


class TestRP2040Detection:
    def test_detects_rp2040_mcu(self):
        graph = _make_rp2040_graph()
        assert graph.mcu is not None
        assert graph.mcu.family == MCUFamily.RP2040
        assert "RP2040" in graph.mcu.type

    def test_detects_i2c_bus(self):
        graph = _make_rp2040_graph()
        i2c = [b for b in graph.buses if b.type.value == "I2C"]
        assert len(i2c) == 1

    def test_detects_bme280_slave(self):
        graph = _make_rp2040_graph()
        i2c = [b for b in graph.buses if b.type.value == "I2C"][0]
        assert len(i2c.slave_component_ids) >= 1


class TestRP2040Templates:
    def test_generates_pico_sdk_project(self):
        graph = _make_rp2040_graph()
        knowledge = resolve_knowledge(graph)
        req = GenerationRequest(
            graph=graph,
            knowledge=knowledge,
            description="Temperature sensor",
            lang="c",
            target="rp2040",
        )
        result = _generate_from_templates(req)
        paths = [f.path for f in result.files]
        assert "CMakeLists.txt" in paths
        assert any("main.c" in p for p in paths)

    def test_cmake_has_pico_sdk(self):
        graph = _make_rp2040_graph()
        knowledge = resolve_knowledge(graph)
        req = GenerationRequest(
            graph=graph,
            knowledge=knowledge,
            description="Temperature sensor",
            lang="c",
            target="rp2040",
        )
        result = _generate_from_templates(req)
        cmake = next(f for f in result.files if f.path == "CMakeLists.txt")
        assert "pico_sdk_import" in cmake.content
        assert "hardware_i2c" in cmake.content
        assert "pico_stdlib" in cmake.content

    def test_main_uses_pico_api(self):
        graph = _make_rp2040_graph()
        knowledge = resolve_knowledge(graph)
        req = GenerationRequest(
            graph=graph,
            knowledge=knowledge,
            description="Temperature sensor",
            lang="c",
            target="rp2040",
        )
        result = _generate_from_templates(req)
        main = next(f for f in result.files if "main.c" in f.path)
        assert "i2c_init" in main.content
        assert "gpio_set_function" in main.content
        assert "stdio_init_all" in main.content

    def test_driver_uses_pico_i2c(self):
        graph = _make_rp2040_graph()
        knowledge = resolve_knowledge(graph)
        req = GenerationRequest(
            graph=graph,
            knowledge=knowledge,
            description="Temperature sensor",
            lang="c",
            target="rp2040",
        )
        result = _generate_from_templates(req)
        drivers = [f for f in result.files if "driver_" in f.path and f.path.endswith(".c")]
        assert len(drivers) >= 1
        driver = drivers[0]
        assert "i2c_write_blocking" in driver.content

    def test_auto_target_resolves_rp2040(self):
        graph = _make_rp2040_graph()
        knowledge = resolve_knowledge(graph)
        req = GenerationRequest(
            graph=graph,
            knowledge=knowledge,
            description="Temperature sensor",
            lang="c",
            target="auto",
        )
        result = _generate_from_templates(req)
        cmake = next(f for f in result.files if f.path == "CMakeLists.txt")
        assert "pico_sdk_import" in cmake.content

    def test_explanation_mentions_rp2040(self):
        graph = _make_rp2040_graph()
        knowledge = resolve_knowledge(graph)
        req = GenerationRequest(
            graph=graph,
            knowledge=knowledge,
            description="Temperature sensor",
            lang="c",
            target="rp2040",
        )
        result = _generate_from_templates(req)
        assert "RP2040" in result.explanation or "Pico" in result.explanation

    def test_knowledge_resolution_works(self):
        graph = _make_rp2040_graph()
        knowledge = resolve_knowledge(graph)
        bme_knowledge = [k for k in knowledge if "BME280" in (k.name or "").upper()]
        assert len(bme_knowledge) >= 1
