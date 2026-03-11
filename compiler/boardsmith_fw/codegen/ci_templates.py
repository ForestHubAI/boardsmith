# SPDX-License-Identifier: AGPL-3.0-or-later
"""CI/CD pipeline template generation — GitHub Actions / GitLab CI."""

from __future__ import annotations

from boardsmith_fw.codegen.llm_wrapper import GeneratedFile
from boardsmith_fw.models.hardware_graph import HardwareGraph, MCUFamily


def generate_github_actions(
    graph: HardwareGraph,
    target: str = "auto",
) -> GeneratedFile:
    """Generate a GitHub Actions workflow for building firmware."""
    resolved = _resolve_ci_target(graph, target)

    if resolved == "rp2040":
        return _github_actions_rp2040()
    if resolved == "stm32":
        return _github_actions_stm32()
    return _github_actions_esp32()


def _resolve_ci_target(graph: HardwareGraph, target: str) -> str:
    if target != "auto":
        return target
    if graph.mcu:
        if graph.mcu.family == MCUFamily.STM32:
            return "stm32"
        if graph.mcu.family == MCUFamily.RP2040:
            return "rp2040"
    return "esp32"


def _github_actions_esp32() -> GeneratedFile:
    return GeneratedFile(
        path=".github/workflows/build.yml",
        content=(
            "name: Build ESP32 Firmware\n\n"
            "on:\n"
            "  push:\n"
            "    branches: [main]\n"
            "  pull_request:\n"
            "    branches: [main]\n\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    container: espressif/idf:latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n\n"
            "      - name: Build\n"
            "        shell: bash\n"
            "        run: |\n"
            "          . $IDF_PATH/export.sh\n"
            "          idf.py set-target esp32\n"
            "          idf.py build\n\n"
            "      - name: Upload artifacts\n"
            "        uses: actions/upload-artifact@v4\n"
            "        with:\n"
            "          name: firmware\n"
            "          path: |\n"
            "            build/*.bin\n"
            "            build/*.elf\n"
            "            build/bootloader/*.bin\n"
            "            build/partition_table/*.bin\n"
        ),
    )


def _github_actions_stm32() -> GeneratedFile:
    return GeneratedFile(
        path=".github/workflows/build.yml",
        content=(
            "name: Build STM32 Firmware\n\n"
            "on:\n"
            "  push:\n"
            "    branches: [main]\n"
            "  pull_request:\n"
            "    branches: [main]\n\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n\n"
            "      - name: Install ARM toolchain\n"
            "        run: |\n"
            "          sudo apt-get update\n"
            "          sudo apt-get install -y gcc-arm-none-eabi cmake\n\n"
            "      - name: Build\n"
            "        run: |\n"
            "          mkdir -p build && cd build\n"
            "          cmake -DCMAKE_C_COMPILER=arm-none-eabi-gcc \\\n"
            "                -DCMAKE_SYSTEM_NAME=Generic \\\n"
            "                -DCMAKE_SYSTEM_PROCESSOR=arm ..\n"
            "          cmake --build .\n\n"
            "      - name: Upload artifacts\n"
            "        uses: actions/upload-artifact@v4\n"
            "        with:\n"
            "          name: firmware\n"
            "          path: build/*.elf\n"
        ),
    )


def _github_actions_rp2040() -> GeneratedFile:
    return GeneratedFile(
        path=".github/workflows/build.yml",
        content=(
            "name: Build RP2040 Firmware\n\n"
            "on:\n"
            "  push:\n"
            "    branches: [main]\n"
            "  pull_request:\n"
            "    branches: [main]\n\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n\n"
            "      - name: Install dependencies\n"
            "        run: |\n"
            "          sudo apt-get update\n"
            "          sudo apt-get install -y cmake gcc-arm-none-eabi\n\n"
            "      - name: Install Pico SDK\n"
            "        run: |\n"
            "          git clone https://github.com/raspberrypi/pico-sdk.git\n"
            "          cd pico-sdk && git submodule update --init\n"
            "          echo \"PICO_SDK_PATH=$PWD\" >> $GITHUB_ENV\n\n"
            "      - name: Build\n"
            "        run: |\n"
            "          mkdir -p build && cd build\n"
            "          cmake ..\n"
            "          cmake --build .\n\n"
            "      - name: Upload artifacts\n"
            "        uses: actions/upload-artifact@v4\n"
            "        with:\n"
            "          name: firmware\n"
            "          path: |\n"
            "            build/*.uf2\n"
            "            build/*.elf\n"
        ),
    )
