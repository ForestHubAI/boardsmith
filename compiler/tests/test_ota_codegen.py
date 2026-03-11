# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Phase 6.4 — OTA Update Scaffolding."""

from boardsmith_fw.codegen.ota_codegen import (
    OTACodegenResult,
    OTAConfig,
    generate_ota,
)

# -----------------------------------------------------------------------
# Config model tests
# -----------------------------------------------------------------------


class TestOTAConfig:
    def test_default_config(self):
        cfg = OTAConfig()
        assert cfg.server_url == "https://firmware.example.com/ota"
        assert cfg.check_interval_s == 3600
        assert cfg.max_retries == 3
        assert cfg.verify_signature is True
        assert cfg.rollback_enabled is True
        assert cfg.firmware_version == "1.0.0"

    def test_custom_config(self):
        cfg = OTAConfig(
            server_url="https://my.server/fw",
            check_interval_s=600,
            max_retries=5,
            firmware_version="2.1.0",
        )
        assert cfg.server_url == "https://my.server/fw"
        assert cfg.check_interval_s == 600
        assert cfg.max_retries == 5
        assert cfg.firmware_version == "2.1.0"


# -----------------------------------------------------------------------
# ESP32 / esp_https_ota
# -----------------------------------------------------------------------


class TestEsp32OTA:
    def test_generates_files(self):
        r = generate_ota(target="esp32")
        names = [f[0] for f in r.files]
        assert "main/ota_config.h" in names
        assert "main/ota_update.c" in names
        assert "ota_summary.md" in names

    def test_header_defines(self):
        r = generate_ota(target="esp32")
        header = dict(r.files)["main/ota_config.h"]
        assert "OTA_SERVER_URL" in header
        assert "OTA_CHECK_INTERVAL_S" in header
        assert "OTA_MAX_RETRIES" in header
        assert "OTA_FW_VERSION" in header
        assert "OTA_VERIFY_SIGNATURE" in header
        assert "OTA_ROLLBACK_ENABLED" in header
        assert "#ifndef OTA_CONFIG_H" in header

    def test_header_custom_url(self):
        cfg = OTAConfig(server_url="https://my.ota.io/esp32")
        r = generate_ota(target="esp32", config=cfg)
        header = dict(r.files)["main/ota_config.h"]
        assert "my.ota.io/esp32" in header

    def test_impl_esp_https_ota(self):
        r = generate_ota(target="esp32")
        impl = dict(r.files)["main/ota_update.c"]
        assert "esp_https_ota" in impl
        assert "esp_http_client_config_t" in impl

    def test_impl_rollback(self):
        r = generate_ota(target="esp32")
        impl = dict(r.files)["main/ota_update.c"]
        assert "esp_ota_mark_app_valid_cancel_rollback" in impl
        assert "ESP_OTA_IMG_PENDING_VERIFY" in impl

    def test_impl_retry_loop(self):
        r = generate_ota(target="esp32")
        impl = dict(r.files)["main/ota_update.c"]
        assert "OTA_MAX_RETRIES" in impl
        assert "attempt" in impl

    def test_impl_ota_task(self):
        r = generate_ota(target="esp32")
        impl = dict(r.files)["main/ota_update.c"]
        assert "ota_task" in impl
        assert "xTaskCreate" in impl
        assert "OTA_CHECK_INTERVAL_S" in impl

    def test_impl_restart_on_success(self):
        r = generate_ota(target="esp32")
        impl = dict(r.files)["main/ota_update.c"]
        assert "esp_restart" in impl

    def test_impl_freertos_includes(self):
        r = generate_ota(target="esp32")
        impl = dict(r.files)["main/ota_update.c"]
        assert "freertos/FreeRTOS.h" in impl
        assert "freertos/task.h" in impl

    def test_impl_ota_init(self):
        r = generate_ota(target="esp32")
        impl = dict(r.files)["main/ota_update.c"]
        assert "void ota_init(void)" in impl
        assert "OTA_FW_VERSION" in impl


# -----------------------------------------------------------------------
# STM32 / HAL flash
# -----------------------------------------------------------------------


class TestStm32OTA:
    def test_generates_files(self):
        r = generate_ota(target="stm32")
        names = [f[0] for f in r.files]
        assert "Src/ota_config.h" in names
        assert "Src/ota_update.c" in names
        assert "ota_summary.md" in names

    def test_header_flash_layout(self):
        r = generate_ota(target="stm32")
        header = dict(r.files)["Src/ota_config.h"]
        assert "OTA_APP_ADDR" in header
        assert "0x08020000" in header
        assert "OTA_APP_SIZE" in header

    def test_header_error_enum(self):
        r = generate_ota(target="stm32")
        header = dict(r.files)["Src/ota_config.h"]
        assert "ota_err_t" in header
        assert "OTA_OK" in header
        assert "OTA_ERR_WRITE" in header
        assert "OTA_ERR_VERIFY" in header

    def test_impl_hal_flash(self):
        r = generate_ota(target="stm32")
        impl = dict(r.files)["Src/ota_update.c"]
        assert "HAL_FLASH_Unlock" in impl
        assert "HAL_FLASH_Program" in impl
        assert "HAL_FLASH_Lock" in impl

    def test_impl_erase(self):
        r = generate_ota(target="stm32")
        impl = dict(r.files)["Src/ota_update.c"]
        assert "HAL_FLASHEx_Erase" in impl
        assert "FLASH_EraseInitTypeDef" in impl

    def test_impl_write_chunk(self):
        r = generate_ota(target="stm32")
        impl = dict(r.files)["Src/ota_update.c"]
        assert "ota_write_chunk" in impl
        assert "OTA_APP_ADDR" in impl

    def test_impl_finish_and_reboot(self):
        r = generate_ota(target="stm32")
        impl = dict(r.files)["Src/ota_update.c"]
        assert "ota_finish_and_reboot" in impl
        assert "HAL_NVIC_SystemReset" in impl

    def test_impl_verify_check(self):
        r = generate_ota(target="stm32")
        impl = dict(r.files)["Src/ota_update.c"]
        assert "0xFFFFFFFF" in impl
        assert "OTA_ERR_VERIFY" in impl

    def test_stm32_hal_include(self):
        r = generate_ota(target="stm32")
        impl = dict(r.files)["Src/ota_update.c"]
        assert "stm32f4xx_hal.h" in impl


# -----------------------------------------------------------------------
# RP2040 / Pico SDK
# -----------------------------------------------------------------------


class TestRp2040OTA:
    def test_generates_files(self):
        r = generate_ota(target="rp2040")
        names = [f[0] for f in r.files]
        assert "ota_config.h" in names
        assert "ota_update.c" in names
        assert "ota_summary.md" in names

    def test_header_flash_layout(self):
        r = generate_ota(target="rp2040")
        header = dict(r.files)["ota_config.h"]
        assert "OTA_FLASH_OFFSET" in header
        assert "OTA_MAX_SIZE" in header
        assert "OTA_SECTOR_SIZE" in header

    def test_header_error_enum(self):
        r = generate_ota(target="rp2040")
        header = dict(r.files)["ota_config.h"]
        assert "ota_err_t" in header
        assert "OTA_ERR_SIZE" in header

    def test_impl_flash_range_program(self):
        r = generate_ota(target="rp2040")
        impl = dict(r.files)["ota_update.c"]
        assert "flash_range_program" in impl
        assert "flash_range_erase" in impl

    def test_impl_watchdog_reboot(self):
        r = generate_ota(target="rp2040")
        impl = dict(r.files)["ota_update.c"]
        assert "watchdog_reboot" in impl

    def test_impl_size_check(self):
        r = generate_ota(target="rp2040")
        impl = dict(r.files)["ota_update.c"]
        assert "OTA_MAX_SIZE" in impl
        assert "OTA_ERR_SIZE" in impl

    def test_impl_xip_base(self):
        r = generate_ota(target="rp2040")
        impl = dict(r.files)["ota_update.c"]
        assert "XIP_BASE" in impl

    def test_impl_pico_includes(self):
        r = generate_ota(target="rp2040")
        impl = dict(r.files)["ota_update.c"]
        assert "pico/stdlib.h" in impl
        assert "hardware/flash.h" in impl
        assert "hardware/watchdog.h" in impl


# -----------------------------------------------------------------------
# Summary markdown
# -----------------------------------------------------------------------


class TestOTASummary:
    def test_contains_target(self):
        for target in ("esp32", "stm32", "rp2040"):
            r = generate_ota(target=target)
            md = dict(r.files)["ota_summary.md"]
            assert f"**{target}**" in md

    def test_esp32_dual_bank(self):
        r = generate_ota(target="esp32")
        md = dict(r.files)["ota_summary.md"]
        assert "esp_https_ota" in md
        assert "Dual-Bank" in md

    def test_stm32_single_bank(self):
        r = generate_ota(target="stm32")
        md = dict(r.files)["ota_summary.md"]
        assert "Single-Bank" in md
        assert "HAL flash" in md

    def test_rp2040_flash(self):
        r = generate_ota(target="rp2040")
        md = dict(r.files)["ota_summary.md"]
        assert "flash_range_program" in md

    def test_version_in_summary(self):
        cfg = OTAConfig(firmware_version="3.2.1")
        r = generate_ota(target="esp32", config=cfg)
        md = dict(r.files)["ota_summary.md"]
        assert "3.2.1" in md

    def test_files_listed(self):
        for target in ("esp32", "stm32", "rp2040"):
            r = generate_ota(target=target)
            md = dict(r.files)["ota_summary.md"]
            assert "ota_config.h" in md
            assert "ota_update.c" in md


# -----------------------------------------------------------------------
# Cross-target consistency
# -----------------------------------------------------------------------


class TestOTACrossTarget:
    def test_all_targets_produce_three_files(self):
        for target in ("esp32", "stm32", "rp2040"):
            r = generate_ota(target=target)
            assert len(r.files) == 3, f"{target} should produce 3 files"

    def test_all_targets_have_ota_init(self):
        for target in ("esp32", "stm32", "rp2040"):
            r = generate_ota(target=target)
            files = dict(r.files)
            c_files = [v for k, v in files.items() if k.endswith(".c")]
            assert any("ota_init" in c for c in c_files), f"{target} missing ota_init"

    def test_default_target_is_esp32(self):
        r = generate_ota()
        names = [f[0] for f in r.files]
        assert "main/ota_config.h" in names

    def test_result_type(self):
        r = generate_ota()
        assert isinstance(r, OTACodegenResult)
