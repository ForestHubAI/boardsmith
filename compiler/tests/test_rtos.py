# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for FreeRTOS task-per-bus code generation."""

from pathlib import Path

from boardsmith_fw.analysis.graph_builder import build_hardware_graph
from boardsmith_fw.codegen.llm_wrapper import GenerationRequest, _generate_from_templates
from boardsmith_fw.knowledge.resolver import resolve_knowledge
from boardsmith_fw.parser.eagle_parser import parse_eagle_schematic

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _pipeline_rtos(fixture: str, sch: str):
    path = FIXTURES / fixture / sch
    parsed = parse_eagle_schematic(path)
    graph = build_hardware_graph(str(path), parsed.components, parsed.nets)
    knowledge = resolve_knowledge(graph)

    req = GenerationRequest(
        graph=graph,
        knowledge=knowledge,
        description="Test RTOS firmware",
        lang="c",
        rtos=True,
        rtos_stack_size=4096,
    )
    result = _generate_from_templates(req)
    return graph, result


class TestRtosEsp32:
    def test_generates_rtos_main(self):
        _, result = _pipeline_rtos("esp32_bme280_i2c", "esp32_bme280.sch")

        main = next(f for f in result.files if f.path.endswith("main.c"))
        assert "FreeRTOS" in main.content
        assert "xTaskCreate" in main.content

    def test_has_task_function(self):
        _, result = _pipeline_rtos("esp32_bme280_i2c", "esp32_bme280.sch")

        main = next(f for f in result.files if f.path.endswith("main.c"))
        assert "static void task_" in main.content
        assert "pvParameters" in main.content

    def test_has_task_handle(self):
        _, result = _pipeline_rtos("esp32_bme280_i2c", "esp32_bme280.sch")

        main = next(f for f in result.files if f.path.endswith("main.c"))
        assert "TaskHandle_t" in main.content

    def test_no_while_loop_in_app_main(self):
        """app_main should NOT have a while(1) loop — tasks handle that."""
        _, result = _pipeline_rtos("esp32_bme280_i2c", "esp32_bme280.sch")

        main = next(f for f in result.files if f.path.endswith("main.c"))
        # Split into app_main body
        app_main_idx = main.content.find("app_main")
        after_app_main = main.content[app_main_idx:]
        # Find first closing brace of app_main
        brace_count = 0
        app_main_body = ""
        for ch in after_app_main:
            if ch == "{":
                brace_count += 1
            elif ch == "}":
                brace_count -= 1
                if brace_count == 0:
                    break
            if brace_count > 0:
                app_main_body += ch

        assert "while" not in app_main_body

    def test_task_calls_driver_init(self):
        _, result = _pipeline_rtos("esp32_bme280_i2c", "esp32_bme280.sch")

        main = next(f for f in result.files if f.path.endswith("main.c"))
        # Task should call bme280_init
        assert "bme280_init" in main.content.lower() or "BME280_init" in main.content

    def test_multi_bus_creates_multiple_tasks(self):
        _, result = _pipeline_rtos("esp32_multi_bus", "esp32_multi_bus.sch")

        main = next(f for f in result.files if f.path.endswith("main.c"))
        # Should have multiple xTaskCreate calls
        task_creates = main.content.count("xTaskCreate")
        assert task_creates >= 3  # I2C, SPI, UART tasks

    def test_rtos_includes_queue_header(self):
        _, result = _pipeline_rtos("esp32_bme280_i2c", "esp32_bme280.sch")

        main = next(f for f in result.files if f.path.endswith("main.c"))
        assert "freertos/queue.h" in main.content

    def test_non_rtos_still_works(self):
        """Without --rtos, should generate traditional while(1) loop."""
        path = FIXTURES / "esp32_bme280_i2c" / "esp32_bme280.sch"
        parsed = parse_eagle_schematic(path)
        graph = build_hardware_graph(str(path), parsed.components, parsed.nets)

        req = GenerationRequest(
            graph=graph,
            knowledge=[],
            description="Test non-RTOS",
            lang="c",
            rtos=False,
        )
        result = _generate_from_templates(req)
        main = next(f for f in result.files if f.path.endswith("main.c"))
        assert "app_main" in main.content
        assert "while" in main.content
        assert "xTaskCreate" not in main.content
