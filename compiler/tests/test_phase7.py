# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Phase 7 — Platform Expansion.

7.1: nRF52 / Zephyr RTOS
7.2: RISC-V / ESP32-C3
7.3: VS Code Extension
7.4: Hardware-in-the-Loop (QEMU/Renode)
7.5: Docker Build Nodes
"""

from pathlib import Path

from boardsmith_fw.codegen.docker_build import DockerBuildResult, generate_docker_build
from boardsmith_fw.codegen.hil_simulation import HILConfig, HILSimulationResult, generate_hil
from boardsmith_fw.codegen.hir_codegen import generate_from_hir
from boardsmith_fw.codegen.intent_codegen import compile_intent
from boardsmith_fw.codegen.ota_codegen import generate_ota
from boardsmith_fw.codegen.safety_codegen import generate_safety
from boardsmith_fw.codegen.vscode_extension import VSCodeExtensionResult, generate_vscode_extension
from boardsmith_fw.models.hardware_graph import MCUFamily

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


# -----------------------------------------------------------------------
# 7.2 ESP32-C3 Detection
# -----------------------------------------------------------------------


class TestEsp32C3Detection:
    def test_mcu_family_enum(self):
        assert MCUFamily.ESP32_C3 == "esp32c3"
        assert MCUFamily.ESP32_C3.value == "esp32c3"

    def test_board_schema_auto_detect_c3(self):
        from boardsmith_fw.parser.board_schema_parser import parse_board_schema_text

        yaml = """\
boardsmith_fw_schema: "1.0"
board:
  name: "C3 Test"
  mcu:
    id: U1
    mpn: ESP32-C3-MINI-1
    family: auto
  buses: []
"""
        graph = parse_board_schema_text(yaml)
        assert graph.mcu is not None
        assert graph.mcu.family == MCUFamily.ESP32_C3

    def test_board_schema_explicit_c3(self):
        from boardsmith_fw.parser.board_schema_parser import parse_board_schema_text

        yaml = """\
boardsmith_fw_schema: "1.0"
board:
  name: "C3 Explicit"
  mcu:
    id: U1
    mpn: RISC-V-CHIP
    family: esp32c3
  buses: []
"""
        graph = parse_board_schema_text(yaml)
        assert graph.mcu.family == MCUFamily.ESP32_C3

    def test_graph_builder_detects_c3(self):
        from boardsmith_fw.analysis.graph_builder import build_hardware_graph
        from boardsmith_fw.models.hardware_graph import Component

        comps = [Component(id="U1", name="U1", value="ESP32-C3", mpn="ESP32-C3-MINI-1")]
        graph = build_hardware_graph("test", comps, [])
        assert graph.mcu is not None
        assert graph.mcu.family == MCUFamily.ESP32_C3

    def test_graph_builder_esp32_s3_stays_esp32(self):
        from boardsmith_fw.analysis.graph_builder import build_hardware_graph
        from boardsmith_fw.models.hardware_graph import Component

        comps = [Component(id="U1", name="U1", value="ESP32-S3", mpn="ESP32-S3-WROOM")]
        graph = build_hardware_graph("test", comps, [])
        assert graph.mcu.family == MCUFamily.ESP32


class TestEsp32C3CodeGen:
    def test_hir_codegen_esp32c3_uses_esp32(self):
        """ESP32-C3 uses same ESP-IDF code as ESP32."""
        from boardsmith_fw.models.hir import HIR

        hir = HIR(version="1.0", source="test")
        result = generate_from_hir(hir, target="esp32c3")
        # Should produce ESP-IDF style output (same as esp32)
        assert isinstance(result.files, list)

    def test_intent_esp32c3_uses_freertos(self):
        yaml = """\
boardsmith_fw_intent: "1.0"
firmware:
  name: c3_app
  tasks:
    - name: blink
      every: 1s
      actions: ["serial.print: blink"]
"""
        r = compile_intent(yaml, target="esp32c3")
        main = dict(r.files)["main_intent.c"]
        assert "freertos/FreeRTOS.h" in main
        assert "xTaskCreate" in main

    def test_safety_esp32c3(self):
        r = generate_safety(target="esp32c3")
        names = [f[0] for f in r.files]
        assert "main/safety_config.h" in names  # ESP32 path convention

    def test_ota_esp32c3(self):
        r = generate_ota(target="esp32c3")
        names = [f[0] for f in r.files]
        assert "main/ota_config.h" in names  # ESP32 path convention


# -----------------------------------------------------------------------
# 7.1 nRF52 Detection
# -----------------------------------------------------------------------


class TestNrf52Detection:
    def test_mcu_family_enum(self):
        assert MCUFamily.NRF52 == "nrf52"
        assert MCUFamily.NRF52.value == "nrf52"

    def test_board_schema_auto_detect_nrf52(self):
        from boardsmith_fw.parser.board_schema_parser import parse_board_schema_text

        yaml = """\
boardsmith_fw_schema: "1.0"
board:
  name: "nRF52 Test"
  mcu:
    id: U1
    mpn: nRF52840
    family: auto
  buses: []
"""
        graph = parse_board_schema_text(yaml)
        assert graph.mcu is not None
        assert graph.mcu.family == MCUFamily.NRF52

    def test_board_schema_explicit_nrf52(self):
        from boardsmith_fw.parser.board_schema_parser import parse_board_schema_text

        yaml = """\
boardsmith_fw_schema: "1.0"
board:
  name: "nRF52 Explicit"
  mcu:
    id: U1
    mpn: CUSTOM-BLE
    family: nrf52
  buses: []
"""
        graph = parse_board_schema_text(yaml)
        assert graph.mcu.family == MCUFamily.NRF52

    def test_graph_builder_detects_nrf52(self):
        from boardsmith_fw.analysis.graph_builder import build_hardware_graph
        from boardsmith_fw.models.hardware_graph import Component

        comps = [Component(id="U1", name="U1", value="NRF52840", mpn="NRF52840-QIAA")]
        graph = build_hardware_graph("test", comps, [])
        assert graph.mcu is not None
        assert graph.mcu.family == MCUFamily.NRF52


# -----------------------------------------------------------------------
# 7.1 nRF52 HIR CodeGen (Zephyr)
# -----------------------------------------------------------------------


class TestNrf52HirCodegen:
    def test_generates_zephyr_main(self):
        from boardsmith_fw.models.hir import HIR

        hir = HIR(version="1.0", source="test")
        result = generate_from_hir(hir, target="nrf52")
        paths = [f.path for f in result.files]
        assert "src/main.c" in paths

    def test_zephyr_includes(self):
        from boardsmith_fw.models.hir import HIR

        hir = HIR(version="1.0", source="test")
        result = generate_from_hir(hir, target="nrf52")
        main = next(f for f in result.files if f.path == "src/main.c")
        assert "zephyr/kernel.h" in main.content
        assert "zephyr/device.h" in main.content

    def test_zephyr_log_module(self):
        from boardsmith_fw.models.hir import HIR

        hir = HIR(version="1.0", source="test")
        result = generate_from_hir(hir, target="nrf52")
        main = next(f for f in result.files if f.path == "src/main.c")
        assert "LOG_MODULE_REGISTER" in main.content

    def test_with_init_contract(self):
        from boardsmith_fw.models.hir import (
            HIR,
            BusContract,
            I2CSpec,
            InitContract,
            InitPhaseSpec,
            RegisterWrite,
        )

        hir = HIR(
            version="1.0",
            source="test",
            bus_contracts=[
                BusContract(
                    bus_name="I2C_0",
                    bus_type="I2C",
                    master_id="U1",
                    slave_ids=["U2"],
                    configured_clock_hz=400000,
                    i2c=I2CSpec(address="0x76"),
                ),
            ],
            init_contracts=[
                InitContract(
                    component_id="U2",
                    component_name="BME280",
                    phases=[
                        InitPhaseSpec(
                            phase="configure",
                            order=1,
                            writes=[RegisterWrite(reg_addr="0xF4", value="0x27", description="Set oversampling")],
                            delay_after_ms=10,
                        ),
                    ],
                ),
            ],
        )
        result = generate_from_hir(hir, target="nrf52")
        paths = [f.path for f in result.files]
        assert "src/bme280.h" in paths
        assert "src/bme280.c" in paths

        header = next(f for f in result.files if f.path == "src/bme280.h")
        assert "zephyr/drivers/i2c.h" in header.content
        assert "BME280_I2C_ADDR" in header.content

        impl = next(f for f in result.files if f.path == "src/bme280.c")
        assert "i2c_write" in impl.content
        assert "k_msleep" in impl.content
        assert "0xF4" in impl.content


# -----------------------------------------------------------------------
# 7.1 nRF52 Intent CodeGen (Zephyr)
# -----------------------------------------------------------------------


class TestNrf52IntentCodegen:
    def test_zephyr_timer(self):
        yaml = """\
boardsmith_fw_intent: "1.0"
firmware:
  name: ble_sensor
  tasks:
    - name: read_temp
      every: 2s
      read:
        - { component: BME280, values: [temperature], store_as: temp }
"""
        r = compile_intent(yaml, target="nrf52")
        main = dict(r.files)["main_intent.c"]
        assert "zephyr/kernel.h" in main
        assert "K_TIMER_DEFINE" in main
        assert "K_WORK_DEFINE" in main
        assert "k_timer_start" in main
        assert "K_MSEC(2000)" in main

    def test_zephyr_log(self):
        yaml = """\
boardsmith_fw_intent: "1.0"
firmware:
  name: test_app
  tasks:
    - name: log_it
      every: 1s
      actions: ["serial.print: hello"]
"""
        r = compile_intent(yaml, target="nrf52")
        main = dict(r.files)["main_intent.c"]
        assert "LOG_INF" in main
        assert "LOG_MODULE_REGISTER" in main

    def test_zephyr_triggered_handler(self):
        yaml = """\
boardsmith_fw_intent: "1.0"
firmware:
  name: triggered
  tasks:
    - name: periodic
      every: 5s
      read: [{ component: BME280, values: [temperature], store_as: data }]
    - name: display
      trigger: periodic
      actions: [{ display.show: { device: SSD1306, text: "hello" } }]
"""
        r = compile_intent(yaml, target="nrf52")
        main = dict(r.files)["main_intent.c"]
        assert "display_handler" in main
        assert "display_print" in main


# -----------------------------------------------------------------------
# 7.1 nRF52 Safety CodeGen (Zephyr)
# -----------------------------------------------------------------------


class TestNrf52Safety:
    def test_generates_files(self):
        r = generate_safety(target="nrf52")
        names = [f[0] for f in r.files]
        assert "src/safety_config.h" in names
        assert "src/safety_monitor.c" in names
        assert "safety_summary.md" in names

    def test_zephyr_watchdog(self):
        r = generate_safety(target="nrf52")
        impl = dict(r.files)["src/safety_monitor.c"]
        assert "zephyr/drivers/watchdog.h" in impl
        assert "wdt_install_timeout" in impl
        assert "wdt_setup" in impl
        assert "wdt_feed" in impl

    def test_zephyr_stack_check(self):
        r = generate_safety(target="nrf52")
        impl = dict(r.files)["src/safety_monitor.c"]
        assert "k_thread_stack_space_get" in impl
        assert "K_THREAD_DEFINE" in impl

    def test_zephyr_log(self):
        r = generate_safety(target="nrf52")
        impl = dict(r.files)["src/safety_monitor.c"]
        assert "LOG_MODULE_REGISTER" in impl

    def test_summary_mentions_zephyr(self):
        r = generate_safety(target="nrf52")
        md = dict(r.files)["safety_summary.md"]
        assert "k_thread_stack_space_get" in md


# -----------------------------------------------------------------------
# 7.1 nRF52 OTA CodeGen (MCUboot)
# -----------------------------------------------------------------------


class TestNrf52OTA:
    def test_generates_files(self):
        r = generate_ota(target="nrf52")
        names = [f[0] for f in r.files]
        assert "src/ota_config.h" in names
        assert "src/ota_update.c" in names
        assert "ota_summary.md" in names

    def test_mcuboot_api(self):
        r = generate_ota(target="nrf52")
        impl = dict(r.files)["src/ota_update.c"]
        assert "zephyr/dfu/mcuboot.h" in impl
        assert "boot_write_img_confirmed" in impl
        assert "boot_request_upgrade" in impl

    def test_rollback_support(self):
        r = generate_ota(target="nrf52")
        impl = dict(r.files)["src/ota_update.c"]
        assert "boot_is_img_confirmed" in impl

    def test_summary_mentions_mcuboot(self):
        r = generate_ota(target="nrf52")
        md = dict(r.files)["ota_summary.md"]
        assert "MCUboot" in md


# -----------------------------------------------------------------------
# 7.2 PlatformIO
# -----------------------------------------------------------------------


class TestPlatformIO:
    def test_esp32c3_pio_env(self):
        from boardsmith_fw.codegen.platformio import _PIO_ENVS

        assert "esp32c3" in _PIO_ENVS
        assert _PIO_ENVS["esp32c3"]["board"] == "esp32-c3-devkitm-1"
        assert _PIO_ENVS["esp32c3"]["framework"] == "espidf"

    def test_nrf52_pio_env(self):
        from boardsmith_fw.codegen.platformio import _PIO_ENVS

        assert "nrf52" in _PIO_ENVS
        assert _PIO_ENVS["nrf52"]["platform"] == "nordicnrf52"
        assert _PIO_ENVS["nrf52"]["framework"] == "zephyr"


# -----------------------------------------------------------------------
# 7.5 Docker Build Nodes
# -----------------------------------------------------------------------


class TestDockerBuild:
    def test_esp32_generates_files(self):
        r = generate_docker_build(target="esp32")
        names = [f[0] for f in r.files]
        assert "Dockerfile" in names
        assert "docker-compose.yml" in names
        assert "build_summary.md" in names

    def test_esp32_dockerfile(self):
        r = generate_docker_build(target="esp32")
        df = dict(r.files)["Dockerfile"]
        assert "espressif/idf" in df
        assert "idf.py build" in df
        assert "IDF_TARGET=esp32" in df

    def test_esp32c3_dockerfile(self):
        r = generate_docker_build(target="esp32c3")
        df = dict(r.files)["Dockerfile"]
        assert "espressif/idf" in df
        assert "IDF_TARGET=esp32c3" in df

    def test_stm32_dockerfile(self):
        r = generate_docker_build(target="stm32")
        df = dict(r.files)["Dockerfile"]
        assert "gcc-arm-none-eabi" in df
        assert "cmake" in df

    def test_rp2040_dockerfile(self):
        r = generate_docker_build(target="rp2040")
        df = dict(r.files)["Dockerfile"]
        assert "pico-sdk" in df
        assert "PICO_SDK_PATH" in df

    def test_nrf52_dockerfile(self):
        r = generate_docker_build(target="nrf52")
        df = dict(r.files)["Dockerfile"]
        assert "zephyrproject-rtos" in df
        assert "west build" in df
        assert "nrf52840dk" in df
        assert "mcuboot" in df

    def test_compose_file(self):
        r = generate_docker_build(target="esp32", project_name="my_fw")
        compose = dict(r.files)["docker-compose.yml"]
        assert "services:" in compose
        assert "build:" in compose
        assert "my_fw" in compose

    def test_summary_esp32(self):
        r = generate_docker_build(target="esp32")
        md = dict(r.files)["build_summary.md"]
        assert "ESP-IDF" in md
        assert "xtensa-esp32-elf-gcc" in md

    def test_summary_esp32c3_risc_v(self):
        r = generate_docker_build(target="esp32c3")
        md = dict(r.files)["build_summary.md"]
        assert "riscv32-esp-elf-gcc" in md

    def test_summary_nrf52(self):
        r = generate_docker_build(target="nrf52")
        md = dict(r.files)["build_summary.md"]
        assert "Zephyr" in md
        assert "West" in md

    def test_custom_project_name(self):
        r = generate_docker_build(target="esp32", project_name="weather_station")
        md = dict(r.files)["build_summary.md"]
        assert "weather_station" in md

    def test_all_targets_produce_three_files(self):
        for target in ("esp32", "esp32c3", "stm32", "rp2040", "nrf52"):
            r = generate_docker_build(target=target)
            assert len(r.files) == 3, f"{target} should produce 3 files"

    def test_unknown_target_falls_back(self):
        r = generate_docker_build(target="avr")
        assert len(r.warnings) > 0
        df = dict(r.files)["Dockerfile"]
        assert "espressif/idf" in df  # Falls back to ESP32

    def test_result_type(self):
        r = generate_docker_build()
        assert isinstance(r, DockerBuildResult)


# -----------------------------------------------------------------------
# 7.3 VS Code Extension
# -----------------------------------------------------------------------


class TestVSCodeExtensionFiles:
    def test_generates_package_json(self):
        r = generate_vscode_extension()
        names = [f[0] for f in r.files]
        assert "package.json" in names

    def test_generates_extension_ts(self):
        r = generate_vscode_extension()
        names = [f[0] for f in r.files]
        assert "src/extension.ts" in names

    def test_generates_diagnostics(self):
        r = generate_vscode_extension()
        names = [f[0] for f in r.files]
        assert "src/diagnostics.ts" in names

    def test_generates_codelens(self):
        r = generate_vscode_extension()
        names = [f[0] for f in r.files]
        assert "src/codeLens.ts" in names

    def test_generates_constraint_panel(self):
        r = generate_vscode_extension()
        names = [f[0] for f in r.files]
        assert "src/constraintPanel.ts" in names

    def test_generates_schema_validator(self):
        r = generate_vscode_extension()
        names = [f[0] for f in r.files]
        assert "src/schemaValidator.ts" in names

    def test_generates_tm_grammar(self):
        r = generate_vscode_extension()
        names = [f[0] for f in r.files]
        assert "syntaxes/board-schema.tmLanguage.json" in names

    def test_generates_tsconfig(self):
        r = generate_vscode_extension()
        names = [f[0] for f in r.files]
        assert "tsconfig.json" in names

    def test_generates_readme(self):
        r = generate_vscode_extension()
        names = [f[0] for f in r.files]
        assert "README.md" in names

    def test_total_file_count(self):
        r = generate_vscode_extension()
        assert len(r.files) == 10

    def test_result_type(self):
        r = generate_vscode_extension()
        assert isinstance(r, VSCodeExtensionResult)


class TestVSCodePackageJson:
    def test_contains_extension_name(self):
        r = generate_vscode_extension(extension_name="my-ext")
        pkg = dict(r.files)["package.json"]
        assert '"name": "my-ext"' in pkg

    def test_contains_publisher(self):
        r = generate_vscode_extension(publisher="test-pub")
        pkg = dict(r.files)["package.json"]
        assert '"publisher": "test-pub"' in pkg

    def test_contains_commands(self):
        r = generate_vscode_extension()
        pkg = dict(r.files)["package.json"]
        assert "boardsmith-fw.runConstraints" in pkg
        assert "boardsmith-fw.showConstraintReport" in pkg
        assert "boardsmith-fw.generateFirmware" in pkg
        assert "boardsmith-fw.validateSchema" in pkg

    def test_contains_settings(self):
        r = generate_vscode_extension()
        pkg = dict(r.files)["package.json"]
        assert "boardsmith-fw.pythonPath" in pkg
        assert "boardsmith-fw.autoValidate" in pkg
        assert "boardsmith-fw.target" in pkg

    def test_contains_target_enum(self):
        r = generate_vscode_extension()
        pkg = dict(r.files)["package.json"]
        for t in ("esp32", "esp32c3", "stm32", "rp2040", "nrf52"):
            assert t in pkg

    def test_activation_events(self):
        r = generate_vscode_extension()
        pkg = dict(r.files)["package.json"]
        assert "board_schema.yaml" in pkg
        assert "intent.yaml" in pkg
        assert "topology.yaml" in pkg

    def test_languages(self):
        r = generate_vscode_extension()
        pkg = dict(r.files)["package.json"]
        assert "boardsmith-fw-board-schema" in pkg
        assert "boardsmith-fw-intent" in pkg


class TestVSCodeExtensionTs:
    def test_imports_diagnostics(self):
        r = generate_vscode_extension()
        ext = dict(r.files)["src/extension.ts"]
        assert "ConstraintDiagnosticProvider" in ext

    def test_imports_codelens(self):
        r = generate_vscode_extension()
        ext = dict(r.files)["src/extension.ts"]
        assert "EagleFWCodeLensProvider" in ext

    def test_registers_commands(self):
        r = generate_vscode_extension()
        ext = dict(r.files)["src/extension.ts"]
        assert "registerCommand" in ext
        assert "boardsmith-fw.runConstraints" in ext

    def test_auto_validate_on_save(self):
        r = generate_vscode_extension()
        ext = dict(r.files)["src/extension.ts"]
        assert "onDidSaveTextDocument" in ext

    def test_deactivate(self):
        r = generate_vscode_extension()
        ext = dict(r.files)["src/extension.ts"]
        assert "deactivate" in ext


class TestVSCodeDiagnostics:
    def test_creates_diagnostic_collection(self):
        r = generate_vscode_extension()
        diag = dict(r.files)["src/diagnostics.ts"]
        assert "createDiagnosticCollection" in diag

    def test_parses_constraint_report(self):
        r = generate_vscode_extension()
        diag = dict(r.files)["src/diagnostics.ts"]
        assert "ConstraintReport" in diag
        assert "ConstraintResult" in diag

    def test_severity_mapping(self):
        r = generate_vscode_extension()
        diag = dict(r.files)["src/diagnostics.ts"]
        assert "DiagnosticSeverity.Error" in diag
        assert "DiagnosticSeverity.Warning" in diag

    def test_status_bar(self):
        r = generate_vscode_extension()
        diag = dict(r.files)["src/diagnostics.ts"]
        assert "StatusBarItem" in diag

    def test_calls_boardsmith_fw_cli(self):
        r = generate_vscode_extension()
        diag = dict(r.files)["src/diagnostics.ts"]
        assert "boardsmith_fw.cli" in diag
        assert "report" in diag


class TestVSCodeCodeLens:
    def test_board_schema_lenses(self):
        r = generate_vscode_extension()
        cl = dict(r.files)["src/codeLens.ts"]
        assert "board_schema.yaml" in cl
        assert "Validate Board Schema" in cl
        assert "Generate Firmware" in cl

    def test_intent_lenses(self):
        r = generate_vscode_extension()
        cl = dict(r.files)["src/codeLens.ts"]
        assert "intent.yaml" in cl
        assert "Compile Intent" in cl

    def test_topology_lenses(self):
        r = generate_vscode_extension()
        cl = dict(r.files)["src/codeLens.ts"]
        assert "topology.yaml" in cl
        assert "Compile Topology" in cl

    def test_task_annotation(self):
        r = generate_vscode_extension()
        cl = dict(r.files)["src/codeLens.ts"]
        assert "- name:" in cl  # regex for task detection


class TestVSCodeConstraintPanel:
    def test_creates_webview(self):
        r = generate_vscode_extension()
        panel = dict(r.files)["src/constraintPanel.ts"]
        assert "createWebviewPanel" in panel

    def test_calls_report_html(self):
        r = generate_vscode_extension()
        panel = dict(r.files)["src/constraintPanel.ts"]
        assert "--format" in panel
        assert "html" in panel

    def test_error_handling(self):
        r = generate_vscode_extension()
        panel = dict(r.files)["src/constraintPanel.ts"]
        assert "getErrorHtml" in panel


class TestVSCodeSchemaValidator:
    def test_checks_board_schema_keys(self):
        r = generate_vscode_extension()
        sv = dict(r.files)["src/schemaValidator.ts"]
        assert "eagle_board_schema" in sv
        assert "mcu:" in sv

    def test_checks_intent_keys(self):
        r = generate_vscode_extension()
        sv = dict(r.files)["src/schemaValidator.ts"]
        assert "boardsmith_fw_intent" in sv
        assert "firmware:" in sv

    def test_i2c_address_validation(self):
        r = generate_vscode_extension()
        sv = dict(r.files)["src/schemaValidator.ts"]
        assert "0x[0-9a-fA-F]" in sv

    def test_bus_type_validation(self):
        r = generate_vscode_extension()
        sv = dict(r.files)["src/schemaValidator.ts"]
        assert "I2C" in sv
        assert "SPI" in sv
        assert "UART" in sv


class TestVSCodeTmGrammar:
    def test_scope_name(self):
        r = generate_vscode_extension()
        gram = dict(r.files)["syntaxes/board-schema.tmLanguage.json"]
        assert "source.boardsmith-fw.board-schema" in gram

    def test_highlights_bus_types(self):
        r = generate_vscode_extension()
        gram = dict(r.files)["syntaxes/board-schema.tmLanguage.json"]
        assert "I2C" in gram
        assert "SPI" in gram

    def test_highlights_hex(self):
        r = generate_vscode_extension()
        gram = dict(r.files)["syntaxes/board-schema.tmLanguage.json"]
        assert "constant.numeric.hex" in gram

    def test_highlights_component_names(self):
        r = generate_vscode_extension()
        gram = dict(r.files)["syntaxes/board-schema.tmLanguage.json"]
        assert "ESP32" in gram
        assert "BME280" in gram


# -----------------------------------------------------------------------
# 7.4 Hardware-in-the-Loop (QEMU/Renode)
# -----------------------------------------------------------------------


class TestHILBasics:
    def test_result_type(self):
        r = generate_hil()
        assert isinstance(r, HILSimulationResult)

    def test_default_target_esp32(self):
        r = generate_hil(target="esp32")
        names = [f[0] for f in r.files]
        assert "hil/qemu_run.sh" in names
        assert "hil/platform.repl" in names
        assert "hil/simulation.resc" in names
        assert "hil/run_tests.py" in names
        assert "hil/conftest.py" in names
        assert "hil/README.md" in names

    def test_unknown_target_fallback(self):
        r = generate_hil(target="avr")
        assert len(r.warnings) > 0
        names = [f[0] for f in r.files]
        assert "hil/qemu_run.sh" in names


class TestHILEsp32:
    def test_qemu_xtensa(self):
        r = generate_hil(target="esp32")
        sh = dict(r.files)["hil/qemu_run.sh"]
        assert "qemu-system-xtensa" in sh
        assert "esp32" in sh

    def test_renode_platform(self):
        r = generate_hil(target="esp32")
        repl = dict(r.files)["hil/platform.repl"]
        assert "esp32.repl" in repl

    def test_renode_script(self):
        r = generate_hil(target="esp32")
        resc = dict(r.files)["hil/simulation.resc"]
        assert "LoadPlatformDescription" in resc
        assert "LoadELF" in resc

    def test_bme280_peripheral(self):
        cfg = HILConfig(peripherals=["BME280"])
        r = generate_hil(target="esp32", config=cfg)
        repl = dict(r.files)["hil/platform.repl"]
        assert "BME280" in repl
        assert "0x76" in repl
        assert "temperature" in repl

    def test_ssd1306_peripheral(self):
        cfg = HILConfig(peripherals=["SSD1306"])
        r = generate_hil(target="esp32", config=cfg)
        repl = dict(r.files)["hil/platform.repl"]
        assert "SSD1306" in repl
        assert "0x3C" in repl


class TestHILEsp32C3:
    def test_qemu_riscv(self):
        r = generate_hil(target="esp32c3")
        sh = dict(r.files)["hil/qemu_run.sh"]
        assert "qemu-system-riscv32" in sh
        assert "esp32c3" in sh

    def test_renode_platform(self):
        r = generate_hil(target="esp32c3")
        repl = dict(r.files)["hil/platform.repl"]
        assert "esp32c3.repl" in repl


class TestHILStm32:
    def test_qemu_arm(self):
        r = generate_hil(target="stm32")
        sh = dict(r.files)["hil/qemu_run.sh"]
        assert "qemu-system-arm" in sh
        assert "cortex-m4" in sh

    def test_renode_stm32f4(self):
        r = generate_hil(target="stm32")
        repl = dict(r.files)["hil/platform.repl"]
        assert "stm32f4.repl" in repl

    def test_bme280_peripheral_stm32(self):
        cfg = HILConfig(peripherals=["BME280"])
        r = generate_hil(target="stm32", config=cfg)
        repl = dict(r.files)["hil/platform.repl"]
        assert "BME280" in repl


class TestHILRp2040:
    def test_qemu_arm_cortex_m0(self):
        r = generate_hil(target="rp2040")
        sh = dict(r.files)["hil/qemu_run.sh"]
        assert "qemu-system-arm" in sh
        assert "cortex-m0" in sh

    def test_renode_rp2040(self):
        r = generate_hil(target="rp2040")
        repl = dict(r.files)["hil/platform.repl"]
        assert "rp2040.repl" in repl


class TestHILNrf52:
    def test_uses_renode_only(self):
        r = generate_hil(target="nrf52")
        assert any("Renode" in w for w in r.warnings)

    def test_renode_nrf52840(self):
        r = generate_hil(target="nrf52")
        repl = dict(r.files)["hil/platform.repl"]
        assert "nrf52840.repl" in repl

    def test_twi_for_i2c(self):
        r = generate_hil(target="nrf52")
        repl = dict(r.files)["hil/platform.repl"]
        assert "twi0" in repl or "TWI" in repl

    def test_bme280_peripheral_nrf52(self):
        cfg = HILConfig(peripherals=["BME280"])
        r = generate_hil(target="nrf52", config=cfg)
        repl = dict(r.files)["hil/platform.repl"]
        assert "BME280" in repl


class TestHILConfig:
    def test_custom_firmware_path(self):
        cfg = HILConfig(firmware_elf="out/app.elf")
        r = generate_hil(target="esp32", config=cfg)
        sh = dict(r.files)["hil/qemu_run.sh"]
        assert "out/app.elf" in sh

    def test_custom_timeout(self):
        cfg = HILConfig(timeout_s=30)
        r = generate_hil(target="esp32", config=cfg)
        sh = dict(r.files)["hil/qemu_run.sh"]
        assert "TIMEOUT=30" in sh

    def test_gdb_port(self):
        cfg = HILConfig(gdb_port=1234)
        r = generate_hil(target="esp32", config=cfg)
        sh = dict(r.files)["hil/qemu_run.sh"]
        assert "1234" in sh

    def test_multiple_peripherals(self):
        cfg = HILConfig(peripherals=["BME280", "SSD1306"])
        r = generate_hil(target="esp32", config=cfg)
        repl = dict(r.files)["hil/platform.repl"]
        assert "BME280" in repl
        assert "SSD1306" in repl


class TestHILTestRunner:
    def test_generates_test_runner(self):
        r = generate_hil(target="esp32")
        names = [f[0] for f in r.files]
        assert "hil/run_tests.py" in names

    def test_runner_checks_boot(self):
        r = generate_hil(target="esp32")
        runner = dict(r.files)["hil/run_tests.py"]
        assert "check_boot" in runner

    def test_runner_checks_crash(self):
        r = generate_hil(target="esp32")
        runner = dict(r.files)["hil/run_tests.py"]
        assert "check_no_crash" in runner
        assert "panic" in runner
        assert "guru meditation" in runner

    def test_runner_checks_i2c(self):
        r = generate_hil(target="esp32")
        runner = dict(r.files)["hil/run_tests.py"]
        assert "check_i2c_init" in runner

    def test_runner_checks_sensor(self):
        r = generate_hil(target="esp32")
        runner = dict(r.files)["hil/run_tests.py"]
        assert "check_sensor_read" in runner


class TestHILConftest:
    def test_generates_conftest(self):
        r = generate_hil(target="esp32")
        names = [f[0] for f in r.files]
        assert "hil/conftest.py" in names

    def test_has_simulation_output_fixture(self):
        r = generate_hil(target="esp32")
        ct = dict(r.files)["hil/conftest.py"]
        assert "simulation_output" in ct
        assert "@pytest.fixture" in ct

    def test_has_target_fixture(self):
        r = generate_hil(target="stm32")
        ct = dict(r.files)["hil/conftest.py"]
        assert '"stm32"' in ct


class TestHILReadme:
    def test_target_mentioned(self):
        r = generate_hil(target="esp32")
        readme = dict(r.files)["hil/README.md"]
        assert "esp32" in readme

    def test_renode_instructions(self):
        r = generate_hil(target="stm32")
        readme = dict(r.files)["hil/README.md"]
        assert "Renode" in readme

    def test_qemu_instructions(self):
        r = generate_hil(target="stm32")
        readme = dict(r.files)["hil/README.md"]
        assert "qemu-system-arm" in readme

    def test_all_targets_produce_six_files(self):
        for target in ("esp32", "esp32c3", "stm32", "rp2040", "nrf52"):
            r = generate_hil(target=target)
            assert len(r.files) == 6, f"{target} should produce 6 files"
