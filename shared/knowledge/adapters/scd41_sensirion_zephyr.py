# SPDX-License-Identifier: AGPL-3.0-or-later
"""SCD41 Sensirion → Zephyr RTOS adapter using Zephyr I2C + sensirion-embedded-common."""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="scd41_sensirion_zephyr_v1",
    contract_id="co2_sensor_v1",
    driver_option_key="sensirion_embedded",
    target_sdk="zephyr",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "const struct device *i2c_dev = DEVICE_DT_GET(DT_NODELABEL(i2c0));\n"
                "if (!device_is_ready(i2c_dev)) { return -ENODEV; }\n"
                "sensirion_i2c_init();\n"
                "int16_t err = scd4x_wake_up();\n"
                "err |= scd4x_stop_periodic_measurement();\n"
                "err |= scd4x_reinit();\n"
                "if (err != 0) { return -EIO; }\n"
                "err = scd4x_start_periodic_measurement();\n"
                "if (err != 0) { return -EIO; }\n"
                "k_msleep(5000);  /* First measurement takes ~5s */"
            ),
            includes=["scd4x_i2c.h", "sensirion_common.h", "zephyr/drivers/i2c.h"],
            error_handling="return_code",
        ),
        "read_co2": CodeTemplate(
            template=(
                "uint16_t co2_ppm;\n"
                "int32_t temperature, humidity;\n"
                "bool data_ready = false;\n"
                "int16_t err = scd4x_get_data_ready_flag(&data_ready);\n"
                "if (err || !data_ready) { return -EAGAIN; }\n"
                "err = scd4x_read_measurement(&co2_ppm, &temperature, &humidity);\n"
                "if (err || co2_ppm == 0) { return -EIO; }\n"
                "return co2_ppm;"
            ),
            includes=["scd4x_i2c.h"],
        ),
        "read_temperature": CodeTemplate(
            template=(
                "uint16_t co2_ppm;\n"
                "int32_t temperature, humidity;\n"
                "scd4x_get_data_ready_flag(NULL);\n"
                "scd4x_read_measurement(&co2_ppm, &temperature, &humidity);\n"
                "return temperature / 1000.0f;"
            ),
            includes=["scd4x_i2c.h"],
        ),
        "read_humidity": CodeTemplate(
            template=(
                "uint16_t co2_ppm;\n"
                "int32_t temperature, humidity;\n"
                "scd4x_get_data_ready_flag(NULL);\n"
                "scd4x_read_measurement(&co2_ppm, &temperature, &humidity);\n"
                "return humidity / 1000.0f;"
            ),
            includes=["scd4x_i2c.h"],
        ),
        "stop": CodeTemplate(
            template="scd4x_stop_periodic_measurement();",
            includes=["scd4x_i2c.h"],
        ),
    },
    required_includes=[
        "scd4x_i2c.h",
        "sensirion_common.h",
        "sensirion_i2c_hal.h",
        "zephyr/drivers/i2c.h",
        "zephyr/kernel.h",
    ],
    required_defines=["CONFIG_I2C=y", "SCD4X_I2C_ADDR=0x62"],
    required_compile_flags=["-DSENSIRION_ZEPHYR"],
    init_template=(
        "/* Zephyr HAL for sensirion-embedded-common:\n"
        " * Implement sensirion_i2c_hal.h using Zephyr i2c_write_read_dt().\n"
        " * i2c_write: i2c_write(dev, buf, len, SCD4X_I2C_ADDR)\n"
        " * i2c_read:  i2c_read(dev, buf, len, SCD4X_I2C_ADDR)\n"
        " * delay_ms:  k_msleep(ms)\n"
        " * prj.conf: CONFIG_I2C=y CONFIG_NEWLIB_LIBC=y\n"
        " */"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
