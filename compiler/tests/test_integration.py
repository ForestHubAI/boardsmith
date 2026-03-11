# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration tests: full pipeline import → analyze → generate."""

from pathlib import Path

from boardsmith_fw.analysis.analysis_report import generate_analysis_report
from boardsmith_fw.analysis.graph_builder import build_hardware_graph
from boardsmith_fw.codegen.llm_wrapper import GenerationRequest, _generate_from_templates
from boardsmith_fw.knowledge.resolver import resolve_knowledge
from boardsmith_fw.models.hardware_graph import HardwareGraph
from boardsmith_fw.parser.eagle_parser import parse_eagle_schematic

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _full_pipeline(fixture: str, sch: str, target: str = "auto", with_knowledge: bool = False):
    """Run import → analyze → generate and return all artifacts."""
    path = FIXTURES / fixture / sch

    # Import
    parsed = parse_eagle_schematic(path)
    assert len(parsed.components) > 0
    assert len(parsed.nets) > 0

    # Analyze
    graph = build_hardware_graph(str(path), parsed.components, parsed.nets)
    assert graph.mcu is not None
    assert len(graph.buses) > 0

    # Resolve knowledge
    knowledge = resolve_knowledge(graph) if with_knowledge else []

    # Generate
    req = GenerationRequest(
        graph=graph,
        knowledge=knowledge,
        description="Test firmware",
        lang="c",
        target=target,
    )
    result = _generate_from_templates(req)
    assert len(result.files) > 0

    return parsed, graph, result


class TestEsp32Pipeline:
    def test_full_pipeline(self):
        parsed, graph, result = _full_pipeline("esp32_bme280_i2c", "esp32_bme280.sch")

        # Verify ESP32 detected
        assert graph.mcu.family.value == "esp32"

        # Verify files generated
        paths = {f.path for f in result.files}
        assert "CMakeLists.txt" in paths
        assert any("main.c" in p for p in paths)
        assert any("driver_BME280" in p for p in paths)

    def test_generated_code_has_correct_pins(self):
        _, graph, result = _full_pipeline("esp32_bme280_i2c", "esp32_bme280.sch")

        main = next(f for f in result.files if f.path.endswith("main.c"))
        assert "GPIO_NUM_21" in main.content  # SDA from schematic
        assert "GPIO_NUM_22" in main.content  # SCL from schematic

    def test_analysis_report(self):
        parsed, graph, _ = _full_pipeline("esp32_bme280_i2c", "esp32_bme280.sch")

        report = generate_analysis_report(graph)
        assert "ESP32" in report
        assert "I2C" in report
        assert "BME280" in report
        assert "Pin Mapping" in report

    def test_hardware_graph_json_roundtrip(self):
        _, graph, _ = _full_pipeline("esp32_bme280_i2c", "esp32_bme280.sch")

        json_str = graph.model_dump_json()
        restored = HardwareGraph.model_validate_json(json_str)
        assert restored.mcu.type == graph.mcu.type
        assert len(restored.buses) == len(graph.buses)
        assert len(restored.components) == len(graph.components)


class TestStm32Pipeline:
    def test_full_pipeline(self):
        parsed, graph, result = _full_pipeline("stm32f4_bme280_i2c", "stm32f4_bme280.sch")

        assert graph.mcu.family.value == "stm32"

        paths = {f.path for f in result.files}
        assert "CMakeLists.txt" in paths
        assert any("Src/main.c" in p for p in paths)
        assert any("Inc/" in p for p in paths)

    def test_stm32_uses_hal_apis(self):
        _, _, result = _full_pipeline("stm32f4_bme280_i2c", "stm32f4_bme280.sch")

        main = next(f for f in result.files if f.path.endswith("main.c"))
        assert "HAL_Init" in main.content
        assert "HAL_I2C_Init" in main.content
        assert "HAL_Delay" in main.content

    def test_explicit_target_override(self):
        """Even though MCU is STM32, forcing esp32 should use ESP-IDF templates."""
        _, _, result = _full_pipeline(
            "stm32f4_bme280_i2c", "stm32f4_bme280.sch", target="esp32"
        )

        main = next(f for f in result.files if f.path.endswith("main.c"))
        assert "app_main" in main.content
        assert "ESP_LOGI" in main.content


class TestMultiBusPipeline:
    """Test full pipeline with I2C + SPI + UART on ESP32."""

    def test_full_pipeline(self):
        parsed, graph, result = _full_pipeline("esp32_multi_bus", "esp32_multi_bus.sch")

        assert graph.mcu.family.value == "esp32"
        bus_types = {b.type.value for b in graph.buses}
        assert "I2C" in bus_types
        assert "SPI" in bus_types
        assert "UART" in bus_types

        paths = {f.path for f in result.files}
        assert "CMakeLists.txt" in paths
        assert any("main.c" in p for p in paths)

    def test_multi_bus_generates_drivers(self):
        _, graph, result = _full_pipeline("esp32_multi_bus", "esp32_multi_bus.sch")

        paths = {f.path for f in result.files}
        # I2C driver for BME280
        assert any("driver_BME280" in p for p in paths)
        # SPI driver for W25Q128
        assert any("driver_W25Q128" in p for p in paths)
        # UART driver for NEO_M8N
        assert any("NEO" in p for p in paths)

    def test_multi_bus_pin_numbers(self):
        _, graph, result = _full_pipeline("esp32_multi_bus", "esp32_multi_bus.sch")

        main = next(f for f in result.files if f.path.endswith("main.c"))
        # I2C pins
        assert "GPIO_NUM_21" in main.content
        assert "GPIO_NUM_22" in main.content
        # SPI pins
        assert "GPIO_NUM_23" in main.content
        assert "GPIO_NUM_19" in main.content
        assert "GPIO_NUM_18" in main.content
        # UART pins
        assert "GPIO_NUM_17" in main.content or "17" in main.content

    def test_multi_bus_analysis_report(self):
        _, graph, _ = _full_pipeline("esp32_multi_bus", "esp32_multi_bus.sch")

        report = generate_analysis_report(graph)
        assert "I2C" in report
        assert "SPI" in report
        assert "UART" in report
        assert "BME280" in report or "U2" in report


class TestKnowledgePipeline:
    """Test that the knowledge pipeline produces real register values in generated code."""

    def test_bme280_real_registers(self):
        """Generated BME280 driver must have real register values, not 0x00 placeholders."""
        _, graph, result = _full_pipeline(
            "esp32_bme280_i2c", "esp32_bme280.sch", with_knowledge=True
        )

        bme_driver = next(
            (f for f in result.files if "driver_BME280" in f.path and f.path.endswith(".c")), None
        )
        assert bme_driver is not None

        # Must contain real BME280 I2C address
        assert "0x76" in bme_driver.content

        # Must contain real register writes from init sequence
        assert "0xE0" in bme_driver.content  # soft reset register
        assert "0xB6" in bme_driver.content  # reset value
        assert "0xF4" in bme_driver.content  # ctrl_meas register
        assert "0x27" in bme_driver.content  # oversampling + normal mode

    def test_bme280_header_has_real_address(self):
        _, graph, result = _full_pipeline(
            "esp32_bme280_i2c", "esp32_bme280.sch", with_knowledge=True
        )

        bme_header = next(
            (f for f in result.files if "driver_BME280" in f.path and f.path.endswith(".h")), None
        )
        assert bme_header is not None
        assert "0x76" in bme_header.content

    def test_multi_bus_with_knowledge(self):
        """Multi-bus: BME280 gets real registers, W25Q128 gets real commands."""
        _, graph, result = _full_pipeline(
            "esp32_multi_bus", "esp32_multi_bus.sch", with_knowledge=True
        )

        bme_driver = next(
            (f for f in result.files if "BME280" in f.path and f.path.endswith(".c")), None
        )
        assert bme_driver is not None
        assert "0xF4" in bme_driver.content  # ctrl_meas

        # W25Q128 gets SPI driver (no init_sequence register writes for SPI template yet,
        # but header should exist)
        w25_files = [f for f in result.files if "W25Q128" in f.path]
        assert len(w25_files) >= 1

    def test_stm32_with_knowledge(self):
        """STM32 pipeline with knowledge produces real HAL_I2C_Mem_Write calls."""
        _, graph, result = _full_pipeline(
            "stm32f4_bme280_i2c", "stm32f4_bme280.sch", with_knowledge=True
        )

        bme_driver = next(
            (f for f in result.files if "BME280" in f.path and f.path.endswith(".c")), None
        )
        assert bme_driver is not None
        assert "HAL_I2C_Mem_Write" in bme_driver.content
        assert "0xF4" in bme_driver.content
        assert "0x27" in bme_driver.content
