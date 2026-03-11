# SPDX-License-Identifier: AGPL-3.0-or-later
"""DB-6: Zephyr adapter tests — all 6 contracts × Zephyr SDK."""
from __future__ import annotations

import sys
from pathlib import Path
import pytest

_REPO = Path(__file__).parent.parent.parent
for p in [str(_REPO / "shared"), str(_REPO)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import shared.knowledge.adapters as adapter_registry


class TestZephyrAdapterLoading:
    def test_all_6_zephyr_adapters_registered(self):
        all_adapters = adapter_registry.get_all()
        zephyr = [a for a in all_adapters.values() if a.target_sdk == "zephyr"]
        assert len(zephyr) >= 6, f"Expected ≥6 Zephyr adapters, got {len(zephyr)}"

    def test_zephyr_adapter_ids(self):
        expected = [
            "bme280_bosch_zephyr_v1",
            "mpu6050_i2cdev_zephyr_v1",
            "ssd1306_u8g2_zephyr_v1",
            "scd41_sensirion_zephyr_v1",
            "w25q128_generic_zephyr_v1",
            "sx1276_radiolib_zephyr_v1",
        ]
        all_ids = set(adapter_registry.get_all().keys())
        for aid in expected:
            assert aid in all_ids, f"Missing Zephyr adapter: {aid}"

    def test_all_sdks_present(self):
        all_adapters = adapter_registry.get_all()
        sdks = {a.target_sdk for a in all_adapters.values()}
        assert "esp-idf" in sdks
        assert "stm32hal" in sdks
        assert "pico-sdk" in sdks
        assert "zephyr" in sdks

    def test_total_adapter_count(self):
        # DB-5: 15, DB-6: +6 Zephyr = 21
        assert len(adapter_registry.get_all()) >= 21


class TestZephyrContractCoverage:
    ALL_CONTRACTS = [
        "temperature_sensor_v1",
        "imu_sensor_v1",
        "display_oled_v1",
        "co2_sensor_v1",
        "flash_storage_v1",
        "lora_transceiver_v1",
    ]

    def test_all_6_contracts_covered_by_zephyr(self):
        for contract in self.ALL_CONTRACTS:
            adapters = adapter_registry.find_for_contract(contract, target_sdk="zephyr")
            assert len(adapters) >= 1, f"No Zephyr adapter for contract: {contract}"

    def test_find_for_contract_filters_by_sdk(self):
        bme280_zephyr = adapter_registry.find_for_contract(
            "temperature_sensor_v1", target_sdk="zephyr"
        )
        assert len(bme280_zephyr) >= 1
        for a in bme280_zephyr:
            assert a.target_sdk == "zephyr"


class TestZephyrAdapterSchemaIntegrity:
    def _get_zephyr_adapters(self):
        return [a for a in adapter_registry.get_all().values() if a.target_sdk == "zephyr"]

    def test_all_have_valid_adapter_id(self):
        for a in self._get_zephyr_adapters():
            assert a.adapter_id.endswith("_zephyr_v1"), f"Bad adapter_id: {a.adapter_id}"

    def test_all_have_contract_id(self):
        for a in self._get_zephyr_adapters():
            assert a.contract_id, f"{a.adapter_id} missing contract_id"

    def test_all_have_capability_mappings(self):
        for a in self._get_zephyr_adapters():
            assert a.capability_mappings, f"{a.adapter_id} has no capability_mappings"
            assert "init" in a.capability_mappings, f"{a.adapter_id} missing 'init' mapping"

    def test_all_have_required_includes(self):
        for a in self._get_zephyr_adapters():
            assert a.required_includes, f"{a.adapter_id} has no required_includes"

    def test_all_have_init_template(self):
        for a in self._get_zephyr_adapters():
            assert a.init_template, f"{a.adapter_id} has no init_template"

    def test_all_have_required_defines(self):
        for a in self._get_zephyr_adapters():
            assert a.required_defines, f"{a.adapter_id} has no required_defines"

    def test_zephyr_includes_use_zephyr_prefix(self):
        for a in self._get_zephyr_adapters():
            zephyr_includes = [i for i in a.required_includes if "zephyr" in i]
            assert len(zephyr_includes) >= 1, (
                f"{a.adapter_id} has no zephyr/ includes in required_includes"
            )

    def test_zephyr_defines_use_config(self):
        for a in self._get_zephyr_adapters():
            config_defines = [d for d in a.required_defines if d.startswith("CONFIG_")]
            assert len(config_defines) >= 1, (
                f"{a.adapter_id} has no CONFIG_ defines"
            )


class TestZephyrAdapterSpecific:
    def test_bme280_zephyr_uses_sensor_api(self):
        a = adapter_registry.get("bme280_bosch_zephyr_v1")
        assert a is not None
        init_code = a.capability_mappings["init"].template
        assert "sensor_sample_fetch" in a.capability_mappings.get(
            "read_temperature", a.capability_mappings["init"]
        ).template or "DEVICE_DT_GET" in init_code
        assert "DEVICE_DT_GET" in init_code or "device_is_ready" in init_code

    def test_mpu6050_zephyr_uses_sensor_channels(self):
        a = adapter_registry.get("mpu6050_i2cdev_zephyr_v1")
        assert a is not None
        accel_code = a.capability_mappings["read_accel"].template
        assert "SENSOR_CHAN_ACCEL" in accel_code
        gyro_code = a.capability_mappings["read_gyro"].template
        assert "SENSOR_CHAN_GYRO" in gyro_code

    def test_ssd1306_zephyr_uses_display_api(self):
        a = adapter_registry.get("ssd1306_u8g2_zephyr_v1")
        assert a is not None
        init_code = a.capability_mappings["init"].template
        assert "display_blanking" in init_code or "DEVICE_DT_GET" in init_code

    def test_scd41_zephyr_uses_k_msleep(self):
        a = adapter_registry.get("scd41_sensirion_zephyr_v1")
        assert a is not None
        init_code = a.capability_mappings["init"].template
        assert "k_msleep" in init_code

    def test_w25q128_zephyr_uses_flash_api(self):
        a = adapter_registry.get("w25q128_generic_zephyr_v1")
        assert a is not None
        read_code = a.capability_mappings["read"].template
        assert "flash_read" in read_code
        write_code = a.capability_mappings["write"].template
        assert "flash_write" in write_code
        erase_code = a.capability_mappings["erase_sector"].template
        assert "flash_erase" in erase_code

    def test_sx1276_zephyr_uses_lora_driver(self):
        a = adapter_registry.get("sx1276_radiolib_zephyr_v1")
        assert a is not None
        init_code = a.capability_mappings["init"].template
        assert "lora_config" in init_code
        tx_code = a.capability_mappings["transmit"].template
        assert "lora_send" in tx_code
        rx_code = a.capability_mappings["receive"].template
        assert "lora_recv" in rx_code

    def test_zephyr_init_templates_have_devicetree_comments(self):
        """All Zephyr adapters should include DTS overlay guidance."""
        adapter_ids = [
            "bme280_bosch_zephyr_v1",
            "mpu6050_i2cdev_zephyr_v1",
            "ssd1306_u8g2_zephyr_v1",
            "scd41_sensirion_zephyr_v1",
            "w25q128_generic_zephyr_v1",
            "sx1276_radiolib_zephyr_v1",
        ]
        for aid in adapter_ids:
            a = adapter_registry.get(aid)
            assert a is not None
            template = a.init_template
            assert "prj.conf" in template or "DT" in template or "overlay" in template, (
                f"{aid} init_template should mention prj.conf or DTS"
            )
