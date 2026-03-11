# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Phase 6.1: Intent Language (declarative firmware → C code)."""

from pathlib import Path

from boardsmith_fw.codegen.intent_codegen import compile_intent, compile_intent_from_file
from boardsmith_fw.models.intent_schema import IntentRead, IntentTask

FIXTURES = Path(__file__).parent.parent / "fixtures"
INTENT_YAML = FIXTURES / "board_schema_esp32" / "intent.yaml"


# ---------------------------------------------------------------------------
# IntentTask model
# ---------------------------------------------------------------------------

class TestIntentTaskModel:
    def test_every_seconds(self):
        t = IntentTask(name="read", every="5s")
        assert t.every_ms() == 5000

    def test_every_milliseconds(self):
        t = IntentTask(name="read", every="100ms")
        assert t.every_ms() == 100

    def test_every_minutes(self):
        t = IntentTask(name="read", every="1min")
        assert t.every_ms() == 60_000

    def test_every_none_returns_zero(self):
        t = IntentTask(name="read")
        assert t.every_ms() == 0

    def test_parsed_actions_string(self):
        t = IntentTask(name="log", actions=["serial.print: hello"])
        acts = t.parsed_actions()
        assert len(acts) == 1
        assert acts[0].action == "serial.print"
        assert "hello" in acts[0].args.get("text", "")

    def test_parsed_actions_dict(self):
        t = IntentTask(name="log", actions=[{"flash.append": {"device": "W25Q128JV", "data": "env"}}])
        acts = t.parsed_actions()
        assert len(acts) == 1
        assert acts[0].action == "flash.append"
        assert acts[0].args["device"] == "W25Q128JV"

    def test_parsed_actions_bare_string(self):
        t = IntentTask(name="log", actions=["serial.print"])
        acts = t.parsed_actions()
        assert acts[0].action == "serial.print"

    def test_trigger_task(self):
        t = IntentTask(name="display", trigger="read_env")
        assert t.trigger == "read_env"
        assert t.every is None


class TestIntentRead:
    def test_store_as(self):
        r = IntentRead(component="BME280", values=["temperature"], store_as="env")
        assert r.store_as == "env"

    def test_values_list(self):
        r = IntentRead(component="BME280", values=["temperature", "pressure", "humidity"])
        assert len(r.values) == 3


# ---------------------------------------------------------------------------
# compile_intent — ESP32
# ---------------------------------------------------------------------------

SIMPLE_INTENT = """
boardsmith_fw_intent: "1.0"
firmware:
  name: weather_station
  tasks:
    - name: read_env
      every: 5s
      read:
        - component: BME280
          values: [temperature, pressure, humidity]
          store_as: env
    - name: log_serial
      trigger: read_env
      actions:
        - "serial.print: T={env.temperature:.1f}C"
"""


class TestCompileIntentESP32:
    def test_returns_files(self):
        r = compile_intent(SIMPLE_INTENT, target="esp32")
        assert len(r.files) >= 1

    def test_main_intent_file_present(self):
        r = compile_intent(SIMPLE_INTENT, target="esp32")
        names = [f[0] for f in r.files]
        assert "main_intent.c" in names

    def test_summary_file_present(self):
        r = compile_intent(SIMPLE_INTENT, target="esp32")
        names = [f[0] for f in r.files]
        assert "intent_summary.md" in names

    def test_freertos_includes(self):
        r = compile_intent(SIMPLE_INTENT, target="esp32")
        main_c = dict(r.files)["main_intent.c"]
        assert "freertos/FreeRTOS.h" in main_c
        assert "freertos/task.h" in main_c

    def test_data_struct_emitted(self):
        r = compile_intent(SIMPLE_INTENT, target="esp32")
        main_c = dict(r.files)["main_intent.c"]
        assert "env_t" in main_c
        assert "float temperature" in main_c
        assert "float pressure" in main_c
        assert "float humidity" in main_c

    def test_task_function_emitted(self):
        r = compile_intent(SIMPLE_INTENT, target="esp32")
        main_c = dict(r.files)["main_intent.c"]
        assert "read_env_task" in main_c

    def test_xtaskcreate_in_app_main(self):
        r = compile_intent(SIMPLE_INTENT, target="esp32")
        main_c = dict(r.files)["main_intent.c"]
        assert "xTaskCreate" in main_c
        assert "app_main" in main_c

    def test_sensor_read_calls_emitted(self):
        r = compile_intent(SIMPLE_INTENT, target="esp32")
        main_c = dict(r.files)["main_intent.c"]
        assert "bme280_read_temperature" in main_c
        assert "bme280_read_pressure" in main_c

    def test_serial_print_action(self):
        r = compile_intent(SIMPLE_INTENT, target="esp32")
        main_c = dict(r.files)["main_intent.c"]
        assert "ESP_LOGI" in main_c

    def test_period_correct(self):
        r = compile_intent(SIMPLE_INTENT, target="esp32")
        main_c = dict(r.files)["main_intent.c"]
        assert "pdMS_TO_TICKS(5000)" in main_c

    def test_no_warnings_for_complete_intent(self):
        r = compile_intent(SIMPLE_INTENT, target="esp32")
        assert len(r.warnings) == 0

    def test_empty_intent_warns(self):
        empty_intent = """
boardsmith_fw_intent: "1.0"
firmware:
  name: empty
"""
        r = compile_intent(empty_intent, target="esp32")
        assert len(r.warnings) >= 1


# ---------------------------------------------------------------------------
# compile_intent — STM32
# ---------------------------------------------------------------------------

class TestCompileIntentSTM32:
    def test_stm32_includes(self):
        r = compile_intent(SIMPLE_INTENT, target="stm32")
        main_c = dict(r.files)["main_intent.c"]
        assert "stm32" in main_c.lower()
        assert "HAL" in main_c

    def test_super_loop_structure(self):
        r = compile_intent(SIMPLE_INTENT, target="stm32")
        main_c = dict(r.files)["main_intent.c"]
        assert "for (;;)" in main_c
        assert "HAL_GetTick" in main_c

    def test_stm32_serial_action(self):
        r = compile_intent(SIMPLE_INTENT, target="stm32")
        main_c = dict(r.files)["main_intent.c"]
        assert "HAL_UART_Transmit" in main_c


# ---------------------------------------------------------------------------
# compile_intent — RP2040
# ---------------------------------------------------------------------------

class TestCompileIntentRP2040:
    def test_pico_includes(self):
        r = compile_intent(SIMPLE_INTENT, target="rp2040")
        main_c = dict(r.files)["main_intent.c"]
        assert "pico/stdlib.h" in main_c

    def test_repeating_timer(self):
        r = compile_intent(SIMPLE_INTENT, target="rp2040")
        main_c = dict(r.files)["main_intent.c"]
        assert "repeating_timer" in main_c
        assert "add_repeating_timer_ms" in main_c

    def test_pico_printf(self):
        r = compile_intent(SIMPLE_INTENT, target="rp2040")
        main_c = dict(r.files)["main_intent.c"]
        assert "printf" in main_c


# ---------------------------------------------------------------------------
# Multiple actions
# ---------------------------------------------------------------------------

MULTI_ACTION_INTENT = """
boardsmith_fw_intent: "1.0"
firmware:
  name: data_logger
  tasks:
    - name: sample
      every: 10s
      read:
        - component: BME280
          values: [temperature, pressure]
          store_as: sample
      actions:
        - flash.append:
            device: W25Q128JV
            data: sample
            format: binary
        - "serial.print: logged"
"""


class TestMultipleActions:
    def test_flash_append_emitted(self):
        r = compile_intent(MULTI_ACTION_INTENT, target="esp32")
        main_c = dict(r.files)["main_intent.c"]
        assert "flash_append" in main_c

    def test_serial_print_emitted(self):
        r = compile_intent(MULTI_ACTION_INTENT, target="esp32")
        main_c = dict(r.files)["main_intent.c"]
        assert "ESP_LOGI" in main_c

    def test_ten_second_period(self):
        r = compile_intent(MULTI_ACTION_INTENT, target="esp32")
        main_c = dict(r.files)["main_intent.c"]
        assert "pdMS_TO_TICKS(10000)" in main_c


# ---------------------------------------------------------------------------
# Intent summary markdown
# ---------------------------------------------------------------------------

class TestIntentSummary:
    def test_summary_contains_task_name(self):
        r = compile_intent(SIMPLE_INTENT, target="esp32")
        summary = dict(r.files)["intent_summary.md"]
        assert "read_env" in summary

    def test_summary_contains_period(self):
        r = compile_intent(SIMPLE_INTENT, target="esp32")
        summary = dict(r.files)["intent_summary.md"]
        assert "5s" in summary

    def test_summary_contains_component(self):
        r = compile_intent(SIMPLE_INTENT, target="esp32")
        summary = dict(r.files)["intent_summary.md"]
        assert "BME280" in summary


# ---------------------------------------------------------------------------
# Fixture file
# ---------------------------------------------------------------------------

class TestIntentFixture:
    def test_fixture_compiles_esp32(self):
        r = compile_intent_from_file(INTENT_YAML, target="esp32")
        assert len(r.files) == 2
        main_c = dict(r.files)["main_intent.c"]
        assert "weather_station" in main_c
        assert "read_env_task" in main_c
        assert "read_interval_log_task" in main_c

    def test_fixture_compiles_stm32(self):
        r = compile_intent_from_file(INTENT_YAML, target="stm32")
        main_c = dict(r.files)["main_intent.c"]
        assert "weather_station" in main_c
        assert "HAL" in main_c

    def test_fixture_compiles_rp2040(self):
        r = compile_intent_from_file(INTENT_YAML, target="rp2040")
        main_c = dict(r.files)["main_intent.c"]
        assert "weather_station" in main_c
        assert "pico" in main_c

    def test_fixture_no_warnings(self):
        r = compile_intent_from_file(INTENT_YAML, target="esp32")
        assert len(r.warnings) == 0
