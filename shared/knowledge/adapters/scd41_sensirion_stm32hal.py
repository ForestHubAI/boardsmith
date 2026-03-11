# SPDX-License-Identifier: AGPL-3.0-or-later
"""SCD41 Sensirion embedded-common → STM32 HAL adapter."""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="scd41_sensirion_stm32hal_v1",
    contract_id="co2_sensor_v1",
    driver_option_key="sensirion_embedded",
    target_sdk="stm32hal",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "sensirion_i2c_hal_init();\n"
                "int16_t err = scd4x_wake_up();\n"
                "if (err) return err;\n"
                "scd4x_stop_periodic_measurement();\n"
                "scd4x_reinit();\n"
                "err = scd4x_start_periodic_measurement();\n"
                "HAL_Delay(5000);  /* First measurement ready in ~5s */"
            ),
            includes=["scd4x_i2c.h", "sensirion_i2c_hal.h"],
            error_handling="return_code",
        ),
        "read_co2": CodeTemplate(
            template=(
                "uint16_t co2_ppm;\n"
                "int32_t temperature_m_deg_c;\n"
                "int32_t humidity_m_percent_rh;\n"
                "bool data_ready;\n"
                "scd4x_get_data_ready_flag(&data_ready);\n"
                "if (!data_ready) return -1;\n"
                "int16_t err = scd4x_read_measurement(&co2_ppm,\n"
                "    &temperature_m_deg_c, &humidity_m_percent_rh);\n"
                "if (err) return err;\n"
                "return co2_ppm;"
            ),
            includes=["scd4x_i2c.h"],
        ),
        "read_temperature": CodeTemplate(
            template=(
                "uint16_t co2_ppm;\n"
                "int32_t temperature_m_deg_c;\n"
                "int32_t humidity_m_percent_rh;\n"
                "scd4x_read_measurement(&co2_ppm, &temperature_m_deg_c, &humidity_m_percent_rh);\n"
                "return temperature_m_deg_c / 1000.0f;"
            ),
            includes=["scd4x_i2c.h"],
        ),
        "set_altitude": CodeTemplate(
            template="scd4x_set_sensor_altitude((uint16_t)altitude_m);",
            includes=["scd4x_i2c.h"],
        ),
        "stop": CodeTemplate(
            template="scd4x_stop_periodic_measurement();",
            includes=["scd4x_i2c.h"],
        ),
    },
    required_includes=["scd4x_i2c.h", "sensirion_i2c_hal.h", "i2c.h"],
    required_defines=[],
    required_compile_flags=[],
    init_template=(
        "/* SCD41 Sensirion HAL for STM32 — implement sensirion_i2c_hal.c:\n"
        "   sensirion_i2c_hal_init():  enable hi2c1\n"
        "   sensirion_i2c_hal_read():  HAL_I2C_Master_Receive(&hi2c1, 0x62 << 1, data, count, 100)\n"
        "   sensirion_i2c_hal_write(): HAL_I2C_Master_Transmit(&hi2c1, 0x62 << 1, data, count, 100)\n"
        "   sensirion_i2c_hal_sleep_usec(): HAL_Delay(useconds / 1000 + 1)\n"
        "*/"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
