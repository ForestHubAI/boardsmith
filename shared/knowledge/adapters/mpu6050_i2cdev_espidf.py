# SPDX-License-Identifier: AGPL-3.0-or-later
"""MPU6050 I2Cdevlib → ESP-IDF adapter."""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="mpu6050_i2cdev_espidf_v1",
    contract_id="imu_sensor_v1",
    driver_option_key="invensense_empl",
    target_sdk="esp-idf",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "mpu6050_handle_t mpu = mpu6050_create(I2C_NUM_0, address);\n"
                "mpu6050_config_t config = {\n"
                "    .accel_range = ACCEL_FS_SEL_2G,\n"
                "    .gyro_range = GYRO_FS_SEL_250DPS,\n"
                "};\n"
                "esp_err_t err = mpu6050_init(mpu, &config);\n"
                "return (err == ESP_OK) ? 0 : -1;"
            ),
            includes=["mpu6050.h"],
        ),
        "read_accel": CodeTemplate(
            template=(
                "mpu6050_accel_value_t accel;\n"
                "esp_err_t err = mpu6050_get_accel(mpu, &accel);\n"
                "*x = accel.accel_x; *y = accel.accel_y; *z = accel.accel_z;\n"
                "return (err == ESP_OK) ? 0 : -1;"
            ),
            includes=["mpu6050.h"],
        ),
        "read_gyro": CodeTemplate(
            template=(
                "mpu6050_gyro_value_t gyro;\n"
                "esp_err_t err = mpu6050_get_gyro(mpu, &gyro);\n"
                "*x = gyro.gyro_x; *y = gyro.gyro_y; *z = gyro.gyro_z;\n"
                "return (err == ESP_OK) ? 0 : -1;"
            ),
            includes=["mpu6050.h"],
        ),
        "read_temp": CodeTemplate(
            template=(
                "float temp;\n"
                "mpu6050_get_temp(mpu, &temp);\n"
                "return temp;"
            ),
            includes=["mpu6050.h"],
        ),
    },
    required_includes=["mpu6050.h"],
    required_defines=[],
    init_template=(
        "/* MPU6050 driver for ESP-IDF using esp-idf-lib component.\n"
        "   Add to idf_component.yml:\n"
        "   dependencies:\n"
        "     espressif/mpu6050: \"*\"\n"
        "*/"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
