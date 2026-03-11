# SPDX-License-Identifier: AGPL-3.0-or-later
"""BME280 Bosch Official → Raspberry Pi Pico SDK adapter."""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="bme280_bosch_picosdk_v1",
    contract_id="temperature_sensor_v1",
    driver_option_key="bosch_official",
    target_sdk="pico-sdk",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "struct bme280_dev dev = {0};\n"
                "dev.intf = BME280_I2C_INTF;\n"
                "dev.read = bme280_pico_i2c_read;\n"
                "dev.write = bme280_pico_i2c_write;\n"
                "dev.delay_us = bme280_pico_delay_us;\n"
                "dev.intf_ptr = NULL;\n"
                "int8_t rslt = bme280_init(&dev);\n"
                "if (rslt != BME280_OK) return rslt;\n"
                "dev.settings.osr_h = BME280_OVERSAMPLING_1X;\n"
                "dev.settings.osr_p = BME280_OVERSAMPLING_16X;\n"
                "dev.settings.osr_t = BME280_OVERSAMPLING_2X;\n"
                "dev.settings.filter = BME280_FILTER_COEFF_16;\n"
                "rslt = bme280_set_sensor_settings(BME280_ALL_SETTINGS_SEL, &dev);\n"
                "rslt = bme280_set_sensor_mode(BME280_NORMAL_MODE, &dev);"
            ),
            includes=["bme280.h", "hardware/i2c.h"],
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
                "return comp_data.pressure / 100.0f;"
            ),
            includes=["bme280.h"],
        ),
        "set_mode": CodeTemplate(
            template="bme280_set_sensor_mode(mode, &dev);",
            includes=["bme280.h"],
        ),
    },
    required_includes=["bme280.h", "bme280_defs.h", "hardware/i2c.h", "pico/stdlib.h"],
    required_defines=["BME280_FLOAT_ENABLE", "BME280_I2C_ADDR_PRIM=0x76"],
    required_compile_flags=[],
    init_template=(
        "/* BME280 I2C callbacks for Raspberry Pi Pico SDK */\n"
        "#define BME280_PICO_I2C i2c0\n"
        "static int8_t bme280_pico_i2c_read(uint8_t reg_addr, uint8_t *data, uint32_t len, void *intf_ptr) {\n"
        "    i2c_write_blocking(BME280_PICO_I2C, BME280_I2C_ADDR_PRIM, &reg_addr, 1, true);\n"
        "    i2c_read_blocking(BME280_PICO_I2C, BME280_I2C_ADDR_PRIM, data, len, false);\n"
        "    return 0;\n"
        "}\n"
        "static int8_t bme280_pico_i2c_write(uint8_t reg_addr, const uint8_t *data, uint32_t len, void *intf_ptr) {\n"
        "    uint8_t buf[64]; buf[0] = reg_addr; memcpy(buf + 1, data, len);\n"
        "    i2c_write_blocking(BME280_PICO_I2C, BME280_I2C_ADDR_PRIM, buf, len + 1, false);\n"
        "    return 0;\n"
        "}\n"
        "static void bme280_pico_delay_us(uint32_t period, void *intf_ptr) {\n"
        "    sleep_us(period);\n"
        "}"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
