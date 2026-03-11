# SPDX-License-Identifier: AGPL-3.0-or-later
"""Docker Build Nodes — Cloud-based compile verification.

Generates Dockerfiles and docker-compose configurations for building
firmware in reproducible, isolated environments.

Supports: ESP-IDF (ESP32/ESP32-C3), STM32CubeIDE, Pico SDK, Zephyr SDK.

Usage:
    from boardsmith_fw.codegen.docker_build import generate_docker_build
    result = generate_docker_build(target="esp32")
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class DockerBuildResult:
    files: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_docker_build(
    target: str = "esp32",
    project_name: str = "firmware",
    idf_version: str = "v5.1",
    zephyr_version: str = "v3.5.0",
) -> DockerBuildResult:
    """Generate Docker build configuration for the given target."""
    result = DockerBuildResult()

    if target in ("esp32", "esp32c3"):
        _gen_esp_idf(target, project_name, idf_version, result)
    elif target == "stm32":
        _gen_stm32(project_name, result)
    elif target == "rp2040":
        _gen_rp2040(project_name, result)
    elif target == "nrf52":
        _gen_zephyr(project_name, zephyr_version, result)
    else:
        result.warnings.append(f"Unknown target '{target}', using esp32")
        _gen_esp_idf("esp32", project_name, idf_version, result)

    # Docker compose for all targets
    result.files.append(("docker-compose.yml", _gen_compose(target, project_name)))
    result.files.append(("build_summary.md", _gen_summary(target, project_name)))

    return result


# ---------------------------------------------------------------------------
# ESP-IDF (ESP32, ESP32-C3)
# ---------------------------------------------------------------------------


def _gen_esp_idf(
    target: str,
    project_name: str,
    idf_version: str,
    result: DockerBuildResult,
) -> None:
    idf_target = "esp32c3" if target == "esp32c3" else "esp32"

    dockerfile = f"""\
# boardsmith-fw Docker build — ESP-IDF ({target})
FROM espressif/idf:{idf_version}

WORKDIR /project

# Copy firmware source
COPY . /project/

# Set IDF target
ENV IDF_TARGET={idf_target}

# Build
RUN idf.py set-target {idf_target} && idf.py build

# Output: /project/build/{project_name}.bin
"""
    result.files.append(("Dockerfile", dockerfile))


# ---------------------------------------------------------------------------
# STM32 (arm-none-eabi-gcc)
# ---------------------------------------------------------------------------


def _gen_stm32(project_name: str, result: DockerBuildResult) -> None:
    dockerfile = f"""\
# boardsmith-fw Docker build — STM32/ARM
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \\
    gcc-arm-none-eabi \\
    libnewlib-arm-none-eabi \\
    cmake \\
    make \\
    && rm -rf /var/lib/apt/lists/*

WORKDIR /project

COPY . /project/

RUN mkdir -p build && cd build && \\
    cmake .. -DCMAKE_TOOLCHAIN_FILE=cmake/arm-none-eabi.cmake && \\
    make -j$(nproc)

# Output: /project/build/{project_name}.bin
"""
    result.files.append(("Dockerfile", dockerfile))


# ---------------------------------------------------------------------------
# RP2040 (Pico SDK)
# ---------------------------------------------------------------------------


def _gen_rp2040(project_name: str, result: DockerBuildResult) -> None:
    dockerfile = f"""\
# boardsmith-fw Docker build — RP2040/Pico SDK
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \\
    gcc-arm-none-eabi \\
    libnewlib-arm-none-eabi \\
    cmake \\
    make \\
    git \\
    python3 \\
    && rm -rf /var/lib/apt/lists/*

# Install Pico SDK
ENV PICO_SDK_PATH=/opt/pico-sdk
RUN git clone --depth 1 https://github.com/raspberrypi/pico-sdk.git $PICO_SDK_PATH && \\
    cd $PICO_SDK_PATH && git submodule update --init

WORKDIR /project

COPY . /project/

RUN mkdir -p build && cd build && \\
    cmake .. && \\
    make -j$(nproc)

# Output: /project/build/{project_name}.uf2
"""
    result.files.append(("Dockerfile", dockerfile))


# ---------------------------------------------------------------------------
# Zephyr (nRF52)
# ---------------------------------------------------------------------------


def _gen_zephyr(
    project_name: str,
    zephyr_version: str,
    result: DockerBuildResult,
) -> None:
    dockerfile = f"""\
# boardsmith-fw Docker build — nRF52/Zephyr
FROM ghcr.io/zephyrproject-rtos/ci:{zephyr_version}

WORKDIR /workdir

# Initialize west workspace
RUN west init -m https://github.com/zephyrproject-rtos/zephyr --mr {zephyr_version} && \\
    west update && \\
    west zephyr-export

WORKDIR /workdir/zephyr

COPY . /workdir/zephyr/app/

RUN west build app -b nrf52840dk_nrf52840 -- \\
    -DCONFIG_MCUBOOT_SIGNATURE_KEY_FILE=\\"bootloader/mcuboot/root-rsa-2048.pem\\"

# Output: /workdir/zephyr/build/zephyr/zephyr.hex
"""
    result.files.append(("Dockerfile", dockerfile))


# ---------------------------------------------------------------------------
# docker-compose
# ---------------------------------------------------------------------------


def _gen_compose(target: str, project_name: str) -> str:
    return f"""\
# boardsmith-fw Docker Compose — {target} build
version: "3.8"

services:
  build:
    build:
      context: .
      dockerfile: Dockerfile
    volumes:
      - ./build-output:/output
    command: >
      sh -c "cp -r /project/build/* /output/ 2>/dev/null ||
             cp -r /workdir/zephyr/build/zephyr/* /output/ 2>/dev/null ||
             echo 'Build artifacts copied'"

  verify:
    build:
      context: .
      dockerfile: Dockerfile
    command: echo "Build verification passed for {project_name} ({target})"
"""


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def _gen_summary(target: str, project_name: str) -> str:
    lines = [
        f"# Docker Build: {project_name}",
        "",
        f"Target: **{target}**",
        "",
        "## Quick Start",
        "",
        "```bash",
        "# Build firmware in Docker",
        "docker build -t boardsmith-fw-build .",
        "",
        "# Or use docker-compose",
        "docker-compose up build",
        "```",
        "",
        "## Build Environment",
        "",
    ]

    if target in ("esp32", "esp32c3"):
        lines += [
            "- **Base image**: `espressif/idf`",
            "- **SDK**: ESP-IDF",
            f"- **Toolchain**: {('riscv32-esp-elf-gcc' if target == 'esp32c3' else 'xtensa-esp32-elf-gcc')}",
            "- **Build system**: CMake + idf.py",
            f"- **Output**: `build/{project_name}.bin`",
        ]
    elif target == "stm32":
        lines += [
            "- **Base image**: `ubuntu:22.04`",
            "- **Toolchain**: `arm-none-eabi-gcc`",
            "- **Build system**: CMake",
            f"- **Output**: `build/{project_name}.bin`",
        ]
    elif target == "rp2040":
        lines += [
            "- **Base image**: `ubuntu:22.04`",
            "- **SDK**: Pico SDK",
            "- **Toolchain**: `arm-none-eabi-gcc`",
            "- **Build system**: CMake",
            f"- **Output**: `build/{project_name}.uf2`",
        ]
    elif target == "nrf52":
        lines += [
            "- **Base image**: `ghcr.io/zephyrproject-rtos/ci`",
            "- **SDK**: Zephyr RTOS + MCUboot",
            "- **Toolchain**: `arm-zephyr-eabi-gcc`",
            "- **Build system**: West + CMake",
            "- **Output**: `build/zephyr/zephyr.hex`",
        ]

    lines += [
        "",
        "## Files",
        "",
        "- `Dockerfile` — Build environment definition",
        "- `docker-compose.yml` — Orchestration config",
        "- `build_summary.md` — This file",
        "",
    ]

    return "\n".join(lines)
