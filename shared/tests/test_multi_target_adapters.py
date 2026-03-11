# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for DB-5: Multi-Target Adapters (STM32 HAL + Pico-SDK).

Covers:
  - Registry completeness: ≥ 6 STM32 HAL adapters, ≥ 3 Pico-SDK adapters
  - All contracts covered by at least one STM32 HAL adapter
  - All adapters have non-empty init_template
  - All adapters have required_includes
  - Capability mappings for key contracts
  - find_for_contract() correctly filters by target_sdk
"""
from __future__ import annotations

import pytest

from shared.knowledge.adapters import find_for_contract, get, get_all


# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------

class TestAdapterRegistryLoading:
    def test_adapter_registry_not_empty(self):
        assert len(get_all()) >= 6  # original 6 ESP-IDF

    def test_stm32hal_adapters_count(self):
        stm32_adapters = [a for a in get_all().values() if a.target_sdk == "stm32hal"]
        assert len(stm32_adapters) >= 6, (
            f"Expected ≥6 STM32 HAL adapters, found {len(stm32_adapters)}"
        )

    def test_picosdk_adapters_count(self):
        pico_adapters = [a for a in get_all().values() if a.target_sdk == "pico-sdk"]
        assert len(pico_adapters) >= 3, (
            f"Expected ≥3 Pico-SDK adapters, found {len(pico_adapters)}"
        )

    def test_espidf_adapters_still_present(self):
        espidf = [a for a in get_all().values() if a.target_sdk == "esp-idf"]
        assert len(espidf) >= 6


# ---------------------------------------------------------------------------
# Contract coverage by target SDK
# ---------------------------------------------------------------------------

class TestContractCoverage:
    ALL_CONTRACTS = [
        "temperature_sensor_v1",
        "imu_sensor_v1",
        "co2_sensor_v1",
        "display_oled_v1",
        "lora_transceiver_v1",
        "flash_storage_v1",
    ]

    def test_all_contracts_have_espidf_adapter(self):
        for contract_id in self.ALL_CONTRACTS:
            adapters = find_for_contract(contract_id, "esp-idf")
            assert adapters, f"No ESP-IDF adapter for contract '{contract_id}'"

    def test_all_contracts_have_stm32hal_adapter(self):
        for contract_id in self.ALL_CONTRACTS:
            adapters = find_for_contract(contract_id, "stm32hal")
            assert adapters, f"No STM32 HAL adapter for contract '{contract_id}'"

    def test_temperature_sensor_has_picosdk(self):
        assert find_for_contract("temperature_sensor_v1", "pico-sdk")

    def test_imu_sensor_has_picosdk(self):
        assert find_for_contract("imu_sensor_v1", "pico-sdk")

    def test_display_oled_has_picosdk(self):
        assert find_for_contract("display_oled_v1", "pico-sdk")


# ---------------------------------------------------------------------------
# Adapter schema integrity
# ---------------------------------------------------------------------------

class TestAdapterSchemaIntegrity:
    def test_all_adapters_have_adapter_id(self):
        for aid, adapter in get_all().items():
            assert adapter.adapter_id, f"Adapter '{aid}' has empty adapter_id"
            assert adapter.adapter_id == aid

    def test_all_adapters_have_contract_id(self):
        for aid, adapter in get_all().items():
            assert adapter.contract_id, f"Adapter '{aid}' has empty contract_id"

    def test_all_adapters_have_target_sdk(self):
        for aid, adapter in get_all().items():
            assert adapter.target_sdk in ("esp-idf", "stm32hal", "pico-sdk", "zephyr"), (
                f"Adapter '{aid}' has unknown target_sdk '{adapter.target_sdk}'"
            )

    def test_all_adapters_have_init_template(self):
        for aid, adapter in get_all().items():
            assert adapter.init_template is not None, (
                f"Adapter '{aid}' has None init_template"
            )

    def test_all_adapters_have_capability_mappings(self):
        for aid, adapter in get_all().items():
            assert adapter.capability_mappings, (
                f"Adapter '{aid}' has empty capability_mappings"
            )

    def test_all_adapters_have_required_includes(self):
        for aid, adapter in get_all().items():
            assert adapter.required_includes is not None, (
                f"Adapter '{aid}' has None required_includes"
            )


# ---------------------------------------------------------------------------
# Specific STM32 HAL adapter checks
# ---------------------------------------------------------------------------

class TestSTM32HALAdapters:
    def test_bme280_stm32hal_has_init_capability(self):
        a = get("bme280_bosch_stm32hal_v1")
        assert a is not None
        assert "init" in a.capability_mappings
        assert "read_temperature" in a.capability_mappings
        assert "read_humidity" in a.capability_mappings
        assert "read_pressure" in a.capability_mappings

    def test_bme280_stm32hal_includes_i2c_header(self):
        a = get("bme280_bosch_stm32hal_v1")
        includes_str = " ".join(a.required_includes)
        assert "i2c.h" in includes_str

    def test_bme280_stm32hal_init_uses_hal_api(self):
        a = get("bme280_bosch_stm32hal_v1")
        assert "HAL_I2C" in a.init_template

    def test_mpu6050_stm32hal_has_accel_and_gyro(self):
        a = get("mpu6050_i2cdev_stm32hal_v1")
        assert a is not None
        assert "read_accel" in a.capability_mappings
        assert "read_gyro" in a.capability_mappings

    def test_mpu6050_stm32hal_uses_mem_read(self):
        a = get("mpu6050_i2cdev_stm32hal_v1")
        init_code = a.capability_mappings["init"].template
        assert "HAL_I2C_Mem_Write" in init_code

    def test_ssd1306_stm32hal_has_display_ops(self):
        a = get("ssd1306_u8g2_stm32hal_v1")
        assert a is not None
        assert "init" in a.capability_mappings
        assert "clear" in a.capability_mappings
        assert "draw_text" in a.capability_mappings

    def test_scd41_stm32hal_has_co2_read(self):
        a = get("scd41_sensirion_stm32hal_v1")
        assert a is not None
        assert "read_co2" in a.capability_mappings

    def test_w25q128_stm32hal_has_flash_ops(self):
        a = get("w25q128_generic_stm32hal_v1")
        assert a is not None
        assert "read" in a.capability_mappings
        assert "page_program" in a.capability_mappings
        assert "sector_erase" in a.capability_mappings

    def test_sx1276_stm32hal_has_lora_ops(self):
        a = get("sx1276_radiolib_stm32hal_v1")
        assert a is not None
        assert "transmit" in a.capability_mappings
        assert "receive" in a.capability_mappings


# ---------------------------------------------------------------------------
# Specific Pico-SDK adapter checks
# ---------------------------------------------------------------------------

class TestPicoSDKAdapters:
    def test_bme280_picosdk_uses_pico_api(self):
        a = get("bme280_bosch_picosdk_v1")
        assert a is not None
        assert "i2c_write_blocking" in a.init_template
        assert "i2c_read_blocking" in a.init_template
        assert "sleep_us" in a.init_template

    def test_bme280_picosdk_includes_hardware_i2c(self):
        a = get("bme280_bosch_picosdk_v1")
        includes_str = " ".join(a.required_includes)
        assert "hardware/i2c.h" in includes_str

    def test_mpu6050_picosdk_uses_pico_i2c(self):
        a = get("mpu6050_i2cdev_picosdk_v1")
        assert a is not None
        read_accel = a.capability_mappings["read_accel"].template
        assert "i2c_write_blocking" in read_accel
        assert "i2c_read_blocking" in read_accel

    def test_ssd1306_picosdk_uses_sleep_ms(self):
        a = get("ssd1306_u8g2_picosdk_v1")
        assert a is not None
        assert "sleep_ms" in a.init_template


# ---------------------------------------------------------------------------
# find_for_contract filtering
# ---------------------------------------------------------------------------

class TestFindForContract:
    def test_find_for_contract_no_sdk_filter_returns_all(self):
        all_adapters = find_for_contract("temperature_sensor_v1")
        sdks = {a.target_sdk for a in all_adapters}
        assert "esp-idf" in sdks
        assert "stm32hal" in sdks
        assert "pico-sdk" in sdks

    def test_find_for_contract_stm32_only(self):
        stm32 = find_for_contract("temperature_sensor_v1", "stm32hal")
        assert all(a.target_sdk == "stm32hal" for a in stm32)
        assert len(stm32) == 1  # exactly one STM32 HAL adapter for BME280

    def test_find_for_contract_pico_only(self):
        pico = find_for_contract("imu_sensor_v1", "pico-sdk")
        assert all(a.target_sdk == "pico-sdk" for a in pico)
        assert len(pico) == 1

    def test_find_for_unknown_contract_returns_empty(self):
        assert find_for_contract("unknown_contract_xyz", "stm32hal") == []
