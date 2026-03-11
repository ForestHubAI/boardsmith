# SPDX-License-Identifier: AGPL-3.0-or-later
"""SCD41 Sensirion Official → ESP-IDF adapter."""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="scd41_sensirion_espidf_v1",
    contract_id="co2_sensor_v1",
    driver_option_key="sensirion_official",
    target_sdk="esp-idf",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "sensirion_i2c_hal_init();\n"
                "scd4x_wake_up();\n"
                "scd4x_stop_periodic_measurement();\n"
                "scd4x_reinit();\n"
                "uint16_t serial_0, serial_1, serial_2;\n"
                "int16_t err = scd4x_get_serial_number(&serial_0, &serial_1, &serial_2);\n"
                "return (err == 0) ? 0 : -1;"
            ),
            includes=["scd4x_i2c.h", "sensirion_common.h", "sensirion_i2c_hal.h"],
        ),
        "start_measurement": CodeTemplate(
            template="return scd4x_start_periodic_measurement();",
            includes=["scd4x_i2c.h"],
        ),
        "read_co2": CodeTemplate(
            template=(
                "uint16_t co2;\n"
                "int32_t temperature, humidity;\n"
                "bool data_ready = false;\n"
                "scd4x_get_data_ready_flag(&data_ready);\n"
                "if (!data_ready) return 0;\n"
                "scd4x_read_measurement(&co2, &temperature, &humidity);\n"
                "return co2;"
            ),
            includes=["scd4x_i2c.h"],
        ),
        "read_temperature": CodeTemplate(
            template=(
                "uint16_t co2;\n"
                "int32_t temperature, humidity;\n"
                "scd4x_read_measurement(&co2, &temperature, &humidity);\n"
                "return temperature / 1000.0f;"
            ),
            includes=["scd4x_i2c.h"],
        ),
        "read_humidity": CodeTemplate(
            template=(
                "uint16_t co2;\n"
                "int32_t temperature, humidity;\n"
                "scd4x_read_measurement(&co2, &temperature, &humidity);\n"
                "return humidity / 1000.0f;"
            ),
            includes=["scd4x_i2c.h"],
        ),
        "stop_measurement": CodeTemplate(
            template="return scd4x_stop_periodic_measurement();",
            includes=["scd4x_i2c.h"],
        ),
        "set_altitude": CodeTemplate(
            template="return scd4x_set_sensor_altitude(altitude_m);",
            includes=["scd4x_i2c.h"],
        ),
    },
    required_includes=["scd4x_i2c.h", "sensirion_common.h", "sensirion_i2c_hal.h"],
    required_defines=[],
    init_template=(
        "/* Sensirion SCD4x I2C driver for ESP-IDF.\n"
        "   Implement sensirion_i2c_hal.c with ESP-IDF I2C driver calls.\n"
        "   See: https://github.com/Sensirion/embedded-i2c-scd4x */"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
