# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for PlatformIO integration."""

from boardsmith_fw.codegen.platformio import generate_platformio_ini
from boardsmith_fw.models.hardware_graph import (
    HardwareGraph,
    MCUFamily,
    MCUInfo,
)


def _make_graph(family: MCUFamily = MCUFamily.ESP32, mcu_type: str = "ESP32"):
    return HardwareGraph(
        source="test",
        mcu=MCUInfo(component_id="U1", type=mcu_type, family=family),
        components=[],
        nets=[],
    )


class TestPlatformIOGeneration:
    def test_esp32_platformio(self):
        graph = _make_graph(MCUFamily.ESP32, "ESP32")
        pio = generate_platformio_ini(graph)
        assert "espressif32" in pio.content
        assert "esp32dev" in pio.content
        assert "espidf" in pio.content
        assert pio.path == "platformio.ini"

    def test_stm32_platformio(self):
        graph = _make_graph(MCUFamily.STM32, "STM32F4")
        pio = generate_platformio_ini(graph)
        assert "ststm32" in pio.content
        assert "stm32cube" in pio.content

    def test_rp2040_platformio(self):
        graph = _make_graph(MCUFamily.RP2040, "RP2040")
        pio = generate_platformio_ini(graph)
        assert "raspberrypi" in pio.content
        assert "pico" in pio.content

    def test_explicit_target_overrides(self):
        graph = _make_graph(MCUFamily.ESP32, "ESP32")
        pio = generate_platformio_ini(graph, target="rp2040")
        assert "raspberrypi" in pio.content

    def test_monitor_speed(self):
        graph = _make_graph()
        pio = generate_platformio_ini(graph)
        assert "monitor_speed = 115200" in pio.content

    def test_contains_env_section(self):
        graph = _make_graph()
        pio = generate_platformio_ini(graph)
        assert "[env:default]" in pio.content
