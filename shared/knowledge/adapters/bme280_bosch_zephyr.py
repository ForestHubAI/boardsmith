# SPDX-License-Identifier: AGPL-3.0-or-later
"""BME280 Bosch Official → Zephyr RTOS adapter (nRF52840, STM32, ESP32 with Zephyr)."""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="bme280_bosch_zephyr_v1",
    contract_id="temperature_sensor_v1",
    driver_option_key="bosch_official",
    target_sdk="zephyr",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "const struct device *bme280_dev = DEVICE_DT_GET_ANY(bosch_bme280);\n"
                "if (!device_is_ready(bme280_dev)) { return -ENODEV; }\n"
                "/* BME280 Zephyr driver auto-configures via DT node */"
            ),
            includes=["zephyr/device.h", "zephyr/drivers/sensor.h"],
            error_handling="return_code",
        ),
        "read_temperature": CodeTemplate(
            template=(
                "struct sensor_value temp;\n"
                "sensor_sample_fetch(bme280_dev);\n"
                "sensor_channel_get(bme280_dev, SENSOR_CHAN_AMBIENT_TEMP, &temp);\n"
                "return sensor_value_to_double(&temp);"
            ),
            includes=["zephyr/drivers/sensor.h"],
        ),
        "read_humidity": CodeTemplate(
            template=(
                "struct sensor_value hum;\n"
                "sensor_sample_fetch(bme280_dev);\n"
                "sensor_channel_get(bme280_dev, SENSOR_CHAN_HUMIDITY, &hum);\n"
                "return sensor_value_to_double(&hum);"
            ),
            includes=["zephyr/drivers/sensor.h"],
        ),
        "read_pressure": CodeTemplate(
            template=(
                "struct sensor_value press;\n"
                "sensor_sample_fetch(bme280_dev);\n"
                "sensor_channel_get(bme280_dev, SENSOR_CHAN_PRESS, &press);\n"
                "return sensor_value_to_double(&press) / 1000.0;  /* Pa → kPa */"
            ),
            includes=["zephyr/drivers/sensor.h"],
        ),
        "set_mode": CodeTemplate(
            template="/* Zephyr BME280 driver manages power mode automatically */",
            includes=[],
        ),
    },
    required_includes=[
        "zephyr/device.h",
        "zephyr/drivers/sensor.h",
        "zephyr/kernel.h",
    ],
    required_defines=["CONFIG_BME280=y", "CONFIG_I2C=y"],
    required_compile_flags=[],
    init_template=(
        "/* Zephyr devicetree overlay (boards/your_board.overlay):\n"
        " * &i2c0 {\n"
        " *   bme280: bme280@76 {\n"
        " *     compatible = \"bosch,bme280\";\n"
        " *     reg = <0x76>;\n"
        " *   };\n"
        " * };\n"
        " * prj.conf: CONFIG_BME280=y CONFIG_SENSOR=y\n"
        " */"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
