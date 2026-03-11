# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Phase 6.5 — Safety Templates (IEC 61508)."""

from boardsmith_fw.codegen.safety_codegen import (
    HeapConfig,
    SafetyCodegenResult,
    SafetyConfig,
    StackConfig,
    WatchdogConfig,
    generate_safety,
)

# -----------------------------------------------------------------------
# Config model tests
# -----------------------------------------------------------------------


class TestSafetyConfig:
    def test_default_config(self):
        cfg = SafetyConfig()
        assert cfg.watchdog.enabled is True
        assert cfg.watchdog.timeout_ms == 5000
        assert cfg.stack.enabled is True
        assert cfg.stack.min_free_bytes == 256
        assert cfg.heap.enabled is True
        assert cfg.heap.low_watermark_bytes == 4096

    def test_custom_watchdog(self):
        cfg = SafetyConfig(watchdog=WatchdogConfig(timeout_ms=3000, panic_on_trigger=False))
        assert cfg.watchdog.timeout_ms == 3000
        assert cfg.watchdog.panic_on_trigger is False

    def test_stack_paint_pattern(self):
        cfg = SafetyConfig(stack=StackConfig(paint_pattern=0xCAFEBABE))
        assert cfg.stack.paint_pattern == 0xCAFEBABE

    def test_all_disabled(self):
        cfg = SafetyConfig(
            watchdog=WatchdogConfig(enabled=False),
            stack=StackConfig(enabled=False),
            heap=HeapConfig(enabled=False),
        )
        assert cfg.watchdog.enabled is False
        assert cfg.stack.enabled is False
        assert cfg.heap.enabled is False


# -----------------------------------------------------------------------
# ESP32 / FreeRTOS
# -----------------------------------------------------------------------


class TestEsp32Safety:
    def test_generates_two_plus_summary(self):
        r = generate_safety(target="esp32")
        names = [f[0] for f in r.files]
        assert "main/safety_config.h" in names
        assert "main/safety_monitor.c" in names
        assert "safety_summary.md" in names

    def test_header_defines(self):
        r = generate_safety(target="esp32")
        header = dict(r.files)["main/safety_config.h"]
        assert "SAFETY_WDT_ENABLED" in header
        assert "SAFETY_WDT_TIMEOUT_MS" in header
        assert "SAFETY_STACK_MIN_FREE" in header
        assert "SAFETY_HEAP_LOW_WATER" in header
        assert "#ifndef SAFETY_CONFIG_H" in header

    def test_header_custom_values(self):
        cfg = SafetyConfig(
            watchdog=WatchdogConfig(timeout_ms=2000),
            stack=StackConfig(min_free_bytes=512),
            heap=HeapConfig(low_watermark_bytes=8192),
        )
        r = generate_safety(target="esp32", config=cfg)
        header = dict(r.files)["main/safety_config.h"]
        assert "2000" in header
        assert "512" in header
        assert "8192" in header

    def test_impl_includes_task_wdt(self):
        r = generate_safety(target="esp32")
        impl = dict(r.files)["main/safety_monitor.c"]
        assert "esp_task_wdt_init" in impl
        assert "esp_task_wdt_add" in impl
        assert "esp_task_wdt_reset" in impl

    def test_impl_stack_overflow_hook(self):
        r = generate_safety(target="esp32")
        impl = dict(r.files)["main/safety_monitor.c"]
        assert "vApplicationStackOverflowHook" in impl
        assert "STACK OVERFLOW" in impl

    def test_impl_stack_high_watermark(self):
        r = generate_safety(target="esp32")
        impl = dict(r.files)["main/safety_monitor.c"]
        assert "uxTaskGetStackHighWaterMark" in impl
        assert "SAFETY_STACK_MIN_FREE" in impl

    def test_impl_heap_monitoring(self):
        r = generate_safety(target="esp32")
        impl = dict(r.files)["main/safety_monitor.c"]
        assert "esp_get_free_heap_size" in impl
        assert "SAFETY_HEAP_LOW_WATER" in impl

    def test_impl_safety_init(self):
        r = generate_safety(target="esp32")
        impl = dict(r.files)["main/safety_monitor.c"]
        assert "void safety_init(void)" in impl
        assert "safety_monitor_task" in impl
        assert "xTaskCreate" in impl

    def test_impl_wdt_feed(self):
        r = generate_safety(target="esp32")
        impl = dict(r.files)["main/safety_monitor.c"]
        assert "void safety_wdt_feed(void)" in impl
        assert "esp_task_wdt_reset" in impl

    def test_disabled_watchdog_omits_init(self):
        cfg = SafetyConfig(watchdog=WatchdogConfig(enabled=False))
        r = generate_safety(target="esp32", config=cfg)
        header = dict(r.files)["main/safety_config.h"]
        assert "SAFETY_WDT_ENABLED       0" in header

    def test_freertos_includes(self):
        r = generate_safety(target="esp32")
        impl = dict(r.files)["main/safety_monitor.c"]
        assert "freertos/FreeRTOS.h" in impl
        assert "freertos/task.h" in impl
        assert "esp_log.h" in impl


# -----------------------------------------------------------------------
# STM32 / HAL
# -----------------------------------------------------------------------


class TestStm32Safety:
    def test_generates_files(self):
        r = generate_safety(target="stm32")
        names = [f[0] for f in r.files]
        assert "Src/safety_config.h" in names
        assert "Src/safety_monitor.c" in names
        assert "safety_summary.md" in names

    def test_header_has_paint_pattern(self):
        r = generate_safety(target="stm32")
        header = dict(r.files)["Src/safety_config.h"]
        assert "SAFETY_STACK_PAINT" in header
        assert "0xDEADBEEF" in header

    def test_impl_iwdg(self):
        r = generate_safety(target="stm32")
        impl = dict(r.files)["Src/safety_monitor.c"]
        assert "IWDG_HandleTypeDef" in impl
        assert "HAL_IWDG_Init" in impl
        assert "HAL_IWDG_Refresh" in impl

    def test_impl_safety_check_function(self):
        r = generate_safety(target="stm32")
        impl = dict(r.files)["Src/safety_monitor.c"]
        assert "void safety_check(uint32_t now_ms)" in impl
        assert "stack_check_free" in impl

    def test_impl_stack_painting(self):
        r = generate_safety(target="stm32")
        impl = dict(r.files)["Src/safety_monitor.c"]
        assert "SAFETY_STACK_PAINT" in impl
        assert "_estack" in impl
        assert "free_words" in impl

    def test_impl_error_handler_on_stack_low(self):
        r = generate_safety(target="stm32")
        impl = dict(r.files)["Src/safety_monitor.c"]
        assert "Error_Handler()" in impl

    def test_stm32_hal_include(self):
        r = generate_safety(target="stm32")
        impl = dict(r.files)["Src/safety_monitor.c"]
        assert "stm32f4xx_hal.h" in impl

    def test_iwdg_reload_calculation(self):
        cfg = SafetyConfig(watchdog=WatchdogConfig(timeout_ms=2000))
        r = generate_safety(target="stm32", config=cfg)
        impl = dict(r.files)["Src/safety_monitor.c"]
        # 2000ms * 500 / 1000 = 1000
        assert "1000" in impl


# -----------------------------------------------------------------------
# RP2040 / Pico SDK
# -----------------------------------------------------------------------


class TestRp2040Safety:
    def test_generates_files(self):
        r = generate_safety(target="rp2040")
        names = [f[0] for f in r.files]
        assert "safety_config.h" in names
        assert "safety_monitor.c" in names
        assert "safety_summary.md" in names

    def test_header_defines(self):
        r = generate_safety(target="rp2040")
        header = dict(r.files)["safety_config.h"]
        assert "SAFETY_WDT_ENABLED" in header
        assert "SAFETY_STACK_PAINT" in header
        assert "void safety_check(void)" in header

    def test_impl_watchdog_enable(self):
        r = generate_safety(target="rp2040")
        impl = dict(r.files)["safety_monitor.c"]
        assert "watchdog_enable" in impl
        assert "SAFETY_WDT_TIMEOUT_MS" in impl

    def test_impl_watchdog_update(self):
        r = generate_safety(target="rp2040")
        impl = dict(r.files)["safety_monitor.c"]
        assert "watchdog_update" in impl

    def test_impl_stack_painting(self):
        r = generate_safety(target="rp2040")
        impl = dict(r.files)["safety_monitor.c"]
        assert "__StackBottom" in impl
        assert "SAFETY_STACK_PAINT" in impl
        assert "stack_check_free" in impl

    def test_impl_pico_sdk_includes(self):
        r = generate_safety(target="rp2040")
        impl = dict(r.files)["safety_monitor.c"]
        assert "pico/stdlib.h" in impl
        assert "hardware/watchdog.h" in impl

    def test_impl_time_function(self):
        r = generate_safety(target="rp2040")
        impl = dict(r.files)["safety_monitor.c"]
        assert "to_ms_since_boot" in impl

    def test_impl_safety_init(self):
        r = generate_safety(target="rp2040")
        impl = dict(r.files)["safety_monitor.c"]
        assert "void safety_init(void)" in impl

    def test_printf_output(self):
        r = generate_safety(target="rp2040")
        impl = dict(r.files)["safety_monitor.c"]
        assert "printf" in impl


# -----------------------------------------------------------------------
# Summary markdown
# -----------------------------------------------------------------------


class TestSafetySummary:
    def test_contains_sections(self):
        r = generate_safety(target="esp32")
        md = dict(r.files)["safety_summary.md"]
        assert "## Watchdog" in md
        assert "## Stack Overflow Detection" in md
        assert "## Heap Monitoring" in md
        assert "## IEC 61508 Coverage" in md

    def test_esp32_method(self):
        r = generate_safety(target="esp32")
        md = dict(r.files)["safety_summary.md"]
        assert "uxTaskGetStackHighWaterMark" in md
        assert "esp_get_free_heap_size" in md

    def test_stm32_method(self):
        r = generate_safety(target="stm32")
        md = dict(r.files)["safety_summary.md"]
        assert "Stack painting" in md

    def test_rp2040_method(self):
        r = generate_safety(target="rp2040")
        md = dict(r.files)["safety_summary.md"]
        assert "Stack painting" in md

    def test_target_in_summary(self):
        for target in ("esp32", "stm32", "rp2040"):
            r = generate_safety(target=target)
            md = dict(r.files)["safety_summary.md"]
            assert f"**{target}**" in md

    def test_custom_values_in_summary(self):
        cfg = SafetyConfig(
            watchdog=WatchdogConfig(timeout_ms=3000),
            heap=HeapConfig(low_watermark_bytes=8192),
        )
        r = generate_safety(target="esp32", config=cfg)
        md = dict(r.files)["safety_summary.md"]
        assert "3000ms" in md
        assert "8192" in md


# -----------------------------------------------------------------------
# Cross-target consistency
# -----------------------------------------------------------------------


class TestCrossTarget:
    def test_all_targets_produce_three_files(self):
        for target in ("esp32", "stm32", "rp2040"):
            r = generate_safety(target=target)
            assert len(r.files) == 3, f"{target} should produce 3 files"

    def test_all_targets_have_safety_init(self):
        for target in ("esp32", "stm32", "rp2040"):
            r = generate_safety(target=target)
            files = dict(r.files)
            # Find the .c file
            c_files = [v for k, v in files.items() if k.endswith(".c")]
            assert any("safety_init" in c for c in c_files), f"{target} missing safety_init"

    def test_all_targets_have_wdt_feed(self):
        for target in ("esp32", "stm32", "rp2040"):
            r = generate_safety(target=target)
            files = dict(r.files)
            c_files = [v for k, v in files.items() if k.endswith(".c")]
            assert any("safety_wdt_feed" in c for c in c_files), f"{target} missing wdt_feed"

    def test_default_target_is_esp32(self):
        r = generate_safety()
        names = [f[0] for f in r.files]
        assert "main/safety_config.h" in names  # ESP32 path convention

    def test_result_type(self):
        r = generate_safety()
        assert isinstance(r, SafetyCodegenResult)
        assert isinstance(r.files, list)
        assert isinstance(r.warnings, list)
