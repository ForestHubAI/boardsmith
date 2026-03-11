# SPDX-License-Identifier: AGPL-3.0-or-later
"""BME280 Bosch Official → ESP-IDF adapter."""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="bme280_bosch_espidf_v1",
    contract_id="temperature_sensor_v1",
    driver_option_key="bosch_official",
    target_sdk="esp-idf",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "struct bme280_dev dev = {0};\n"
                "dev.intf = BME280_I2C_INTF;\n"
                "dev.read = user_i2c_read;\n"
                "dev.write = user_i2c_write;\n"
                "dev.delay_us = user_delay_us;\n"
                "dev.intf_ptr = &i2c_addr;\n"
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
                "return comp_data.pressure / 100.0;  /* Pa → hPa */"
            ),
            includes=["bme280.h"],
        ),
        "set_mode": CodeTemplate(
            template="bme280_set_sensor_mode(mode, &dev);",
            includes=["bme280.h"],
        ),
    },
    required_includes=["bme280.h", "bme280_defs.h"],
    required_defines=["BME280_FLOAT_ENABLE"],
    required_compile_flags=[],
    init_template=(
        "/* BME280 I2C HAL callbacks for ESP-IDF */\n"
        "static int8_t user_i2c_read(uint8_t reg_addr, uint8_t *data, uint32_t len, void *intf_ptr) {\n"
        "    uint8_t addr = *(uint8_t*)intf_ptr;\n"
        "    return (i2c_master_write_read_device(I2C_NUM_0, addr, &reg_addr, 1, data, len, pdMS_TO_TICKS(100)) == ESP_OK) ? 0 : -1;\n"
        "}\n"
        "static int8_t user_i2c_write(uint8_t reg_addr, const uint8_t *data, uint32_t len, void *intf_ptr) {\n"
        "    uint8_t addr = *(uint8_t*)intf_ptr;\n"
        "    uint8_t buf[64]; buf[0] = reg_addr; memcpy(buf+1, data, len);\n"
        "    return (i2c_master_write_to_device(I2C_NUM_0, addr, buf, len+1, pdMS_TO_TICKS(100)) == ESP_OK) ? 0 : -1;\n"
        "}\n"
        "static void user_delay_us(uint32_t period, void *intf_ptr) {\n"
        "    vTaskDelay(pdMS_TO_TICKS((period / 1000) + 1));\n"
        "}"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
