# SPDX-License-Identifier: AGPL-3.0-or-later
"""BME280 Bosch Official → STM32 HAL adapter.

Phase 24.1 / DB-5: STM32 HAL adapter — enables deterministic (no-LLM)
firmware generation for BME280 on all STM32 targets.

Uses Bosch BME280 official API with HAL_I2C_Mem_Read/Write callbacks —
compatible with all STM32 HAL versions (F0, F1, F4, L4, etc.)
"""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="bme280_bosch_stm32hal_v1",
    contract_id="temperature_sensor_v1",
    driver_option_key="bosch_official",
    target_sdk="stm32hal",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "struct bme280_dev dev = {0};\n"
                "dev.intf = BME280_I2C_INTF;\n"
                "dev.read = bme280_stm32_i2c_read;\n"
                "dev.write = bme280_stm32_i2c_write;\n"
                "dev.delay_us = bme280_stm32_delay_us;\n"
                "dev.intf_ptr = &hi2c1;\n"
                "int8_t rslt = bme280_init(&dev);\n"
                "if (rslt != BME280_OK) return rslt;\n"
                "dev.settings.osr_h = BME280_OVERSAMPLING_1X;\n"
                "dev.settings.osr_p = BME280_OVERSAMPLING_16X;\n"
                "dev.settings.osr_t = BME280_OVERSAMPLING_2X;\n"
                "dev.settings.filter = BME280_FILTER_COEFF_16;\n"
                "dev.settings.standby_time = BME280_STANDBY_TIME_62_5_MS;\n"
                "rslt = bme280_set_sensor_settings(BME280_ALL_SETTINGS_SEL, &dev);\n"
                "rslt = bme280_set_sensor_mode(BME280_NORMAL_MODE, &dev);"
            ),
            includes=["bme280.h", "bme280_defs.h"],
            error_handling="return_code",
        ),
        "read_temperature": CodeTemplate(
            template=(
                "struct bme280_data comp_data;\n"
                "bme280_get_sensor_data(BME280_ALL, &comp_data, &dev);\n"
                "return comp_data.temperature;"
            ),
            includes=["bme280.h"],
        ),
        "read_humidity": CodeTemplate(
            template=(
                "struct bme280_data comp_data;\n"
                "bme280_get_sensor_data(BME280_ALL, &comp_data, &dev);\n"
                "return comp_data.humidity;"
            ),
            includes=["bme280.h"],
        ),
        "read_pressure": CodeTemplate(
            template=(
                "struct bme280_data comp_data;\n"
                "bme280_get_sensor_data(BME280_ALL, &comp_data, &dev);\n"
                "return comp_data.pressure / 100.0f;  /* Pa → hPa */"
            ),
            includes=["bme280.h"],
        ),
        "set_mode": CodeTemplate(
            template="bme280_set_sensor_mode(mode, &dev);",
            includes=["bme280.h"],
        ),
    },
    required_includes=["bme280.h", "bme280_defs.h", "i2c.h"],
    required_defines=["BME280_FLOAT_ENABLE"],
    required_compile_flags=[],
    init_template=(
        "/* BME280 I2C HAL callbacks for STM32 HAL */\n"
        "static int8_t bme280_stm32_i2c_read(uint8_t reg_addr, uint8_t *data, uint32_t len, void *intf_ptr) {\n"
        "    I2C_HandleTypeDef *hi2c = (I2C_HandleTypeDef *)intf_ptr;\n"
        "    return (HAL_I2C_Mem_Read(hi2c, BME280_I2C_ADDR_PRIM << 1, reg_addr, I2C_MEMADD_SIZE_8BIT,\n"
        "                             data, len, HAL_MAX_DELAY) == HAL_OK) ? 0 : -1;\n"
        "}\n"
        "static int8_t bme280_stm32_i2c_write(uint8_t reg_addr, const uint8_t *data, uint32_t len, void *intf_ptr) {\n"
        "    I2C_HandleTypeDef *hi2c = (I2C_HandleTypeDef *)intf_ptr;\n"
        "    uint8_t buf[64]; buf[0] = reg_addr; memcpy(buf + 1, data, len);\n"
        "    return (HAL_I2C_Master_Transmit(hi2c, BME280_I2C_ADDR_PRIM << 1, buf, len + 1,\n"
        "                                   HAL_MAX_DELAY) == HAL_OK) ? 0 : -1;\n"
        "}\n"
        "static void bme280_stm32_delay_us(uint32_t period, void *intf_ptr) {\n"
        "    HAL_Delay((period / 1000) + 1);  /* ms precision */"
        "\n}"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
