# SPDX-License-Identifier: AGPL-3.0-or-later
"""MPU-6050 → Zephyr RTOS adapter using Zephyr sensor driver."""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="mpu6050_i2cdev_zephyr_v1",
    contract_id="imu_sensor_v1",
    driver_option_key="i2cdev",
    target_sdk="zephyr",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "const struct device *mpu6050_dev = DEVICE_DT_GET_ANY(invensense_mpu6050);\n"
                "if (!device_is_ready(mpu6050_dev)) { return -ENODEV; }\n"
                "/* Zephyr MPU6050 driver initializes via DTS configuration */"
            ),
            includes=["zephyr/device.h", "zephyr/drivers/sensor.h"],
            error_handling="return_code",
        ),
        "read_accel": CodeTemplate(
            template=(
                "struct sensor_value accel[3];\n"
                "sensor_sample_fetch_chan(mpu6050_dev, SENSOR_CHAN_ACCEL_XYZ);\n"
                "sensor_channel_get(mpu6050_dev, SENSOR_CHAN_ACCEL_X, &accel[0]);\n"
                "sensor_channel_get(mpu6050_dev, SENSOR_CHAN_ACCEL_Y, &accel[1]);\n"
                "sensor_channel_get(mpu6050_dev, SENSOR_CHAN_ACCEL_Z, &accel[2]);\n"
                "ax = sensor_value_to_double(&accel[0]);\n"
                "ay = sensor_value_to_double(&accel[1]);\n"
                "az = sensor_value_to_double(&accel[2]);"
            ),
            includes=["zephyr/drivers/sensor.h"],
        ),
        "read_gyro": CodeTemplate(
            template=(
                "struct sensor_value gyro[3];\n"
                "sensor_sample_fetch_chan(mpu6050_dev, SENSOR_CHAN_GYRO_XYZ);\n"
                "sensor_channel_get(mpu6050_dev, SENSOR_CHAN_GYRO_X, &gyro[0]);\n"
                "sensor_channel_get(mpu6050_dev, SENSOR_CHAN_GYRO_Y, &gyro[1]);\n"
                "sensor_channel_get(mpu6050_dev, SENSOR_CHAN_GYRO_Z, &gyro[2]);\n"
                "gx = sensor_value_to_double(&gyro[0]);\n"
                "gy = sensor_value_to_double(&gyro[1]);\n"
                "gz = sensor_value_to_double(&gyro[2]);"
            ),
            includes=["zephyr/drivers/sensor.h"],
        ),
        "set_accel_range": CodeTemplate(
            template=(
                "struct sensor_value range = {.val1 = range_g, .val2 = 0};\n"
                "sensor_attr_set(mpu6050_dev, SENSOR_CHAN_ACCEL_XYZ,\n"
                "                SENSOR_ATTR_FULL_SCALE, &range);"
            ),
            includes=["zephyr/drivers/sensor.h"],
        ),
        "set_gyro_range": CodeTemplate(
            template=(
                "struct sensor_value range = {.val1 = range_dps, .val2 = 0};\n"
                "sensor_attr_set(mpu6050_dev, SENSOR_CHAN_GYRO_XYZ,\n"
                "                SENSOR_ATTR_FULL_SCALE, &range);"
            ),
            includes=["zephyr/drivers/sensor.h"],
        ),
    },
    required_includes=[
        "zephyr/device.h",
        "zephyr/drivers/sensor.h",
        "zephyr/kernel.h",
    ],
    required_defines=["CONFIG_MPU6050=y", "CONFIG_I2C=y", "CONFIG_SENSOR=y"],
    required_compile_flags=[],
    init_template=(
        "/* Zephyr devicetree overlay:\n"
        " * &i2c0 {\n"
        " *   mpu6050: mpu6050@68 {\n"
        " *     compatible = \"invensense,mpu6050\";\n"
        " *     reg = <0x68>;\n"
        " *     int-gpios = <&gpio0 11 GPIO_ACTIVE_HIGH>;\n"
        " *   };\n"
        " * };\n"
        " * prj.conf: CONFIG_MPU6050=y CONFIG_SENSOR=y\n"
        " */"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
