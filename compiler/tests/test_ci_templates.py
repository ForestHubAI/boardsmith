# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for CI/CD pipeline template generation."""

from boardsmith_fw.codegen.ci_templates import generate_github_actions
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


class TestGitHubActions:
    def test_esp32_workflow(self):
        graph = _make_graph(MCUFamily.ESP32, "ESP32")
        ci = generate_github_actions(graph)
        assert ci.path == ".github/workflows/build.yml"
        assert "espressif/idf" in ci.content
        assert "idf.py build" in ci.content
        assert "actions/checkout" in ci.content

    def test_stm32_workflow(self):
        graph = _make_graph(MCUFamily.STM32, "STM32F4")
        ci = generate_github_actions(graph)
        assert "arm-none-eabi-gcc" in ci.content
        assert "cmake" in ci.content

    def test_rp2040_workflow(self):
        graph = _make_graph(MCUFamily.RP2040, "RP2040")
        ci = generate_github_actions(graph)
        assert "pico-sdk" in ci.content
        assert "*.uf2" in ci.content

    def test_explicit_target(self):
        graph = _make_graph(MCUFamily.ESP32, "ESP32")
        ci = generate_github_actions(graph, target="rp2040")
        assert "pico-sdk" in ci.content

    def test_has_upload_artifacts(self):
        graph = _make_graph()
        ci = generate_github_actions(graph)
        assert "upload-artifact" in ci.content

    def test_triggers_on_push_and_pr(self):
        graph = _make_graph()
        ci = generate_github_actions(graph)
        assert "push:" in ci.content
        assert "pull_request:" in ci.content
