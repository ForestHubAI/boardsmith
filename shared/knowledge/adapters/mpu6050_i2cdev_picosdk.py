# SPDX-License-Identifier: AGPL-3.0-or-later
"""MPU6050 direct register access → Raspberry Pi Pico SDK adapter."""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="mpu6050_i2cdev_picosdk_v1",
    contract_id="imu_sensor_v1",
    driver_option_key="direct_registers",
    target_sdk="pico-sdk",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "/* Wake MPU-6050: write 0x00 to PWR_MGMT_1 */\n"
                "uint8_t init_seq[] = {0x6B, 0x00};\n"
                "i2c_write_blocking(MPU6050_PICO_I2C, MPU6050_ADDR, init_seq, 2, false);\n"
                "/* Full-scale gyro ±250 dps */\n"
                "uint8_t gyro_seq[] = {0x1B, 0x00};\n"
                "i2c_write_blocking(MPU6050_PICO_I2C, MPU6050_ADDR, gyro_seq, 2, false);\n"
                "/* Full-scale accel ±2g */\n"
                "uint8_t accel_seq[] = {0x1C, 0x00};\n"
                "i2c_write_blocking(MPU6050_PICO_I2C, MPU6050_ADDR, accel_seq, 2, false);"
            ),
            includes=["hardware/i2c.h"],
            error_handling="none",
        ),
        "read_accel": CodeTemplate(
            template=(
                "uint8_t reg = 0x3B;\n"
                "uint8_t raw[6];\n"
                "i2c_write_blocking(MPU6050_PICO_I2C, MPU6050_ADDR, &reg, 1, true);\n"
                "i2c_read_blocking(MPU6050_PICO_I2C, MPU6050_ADDR, raw, 6, false);\n"
                "*x = ((int16_t)(raw[0] << 8 | raw[1])) / 16384.0f;\n"
                "*y = ((int16_t)(raw[2] << 8 | raw[3])) / 16384.0f;\n"
                "*z = ((int16_t)(raw[4] << 8 | raw[5])) / 16384.0f;"
            ),
            includes=["hardware/i2c.h"],
        ),
        "read_gyro": CodeTemplate(
            template=(
                "uint8_t reg = 0x43;\n"
                "uint8_t raw[6];\n"
                "i2c_write_blocking(MPU6050_PICO_I2C, MPU6050_ADDR, &reg, 1, true);\n"
                "i2c_read_blocking(MPU6050_PICO_I2C, MPU6050_ADDR, raw, 6, false);\n"
                "*x = ((int16_t)(raw[0] << 8 | raw[1])) / 131.0f;\n"
                "*y = ((int16_t)(raw[2] << 8 | raw[3])) / 131.0f;\n"
                "*z = ((int16_t)(raw[4] << 8 | raw[5])) / 131.0f;"
            ),
            includes=["hardware/i2c.h"],
        ),
        "read_temp": CodeTemplate(
            template=(
                "uint8_t reg = 0x41;\n"
                "uint8_t raw[2];\n"
                "i2c_write_blocking(MPU6050_PICO_I2C, MPU6050_ADDR, &reg, 1, true);\n"
                "i2c_read_blocking(MPU6050_PICO_I2C, MPU6050_ADDR, raw, 2, false);\n"
                "int16_t raw_temp = (int16_t)(raw[0] << 8 | raw[1]);\n"
                "return raw_temp / 340.0f + 36.53f;"
            ),
            includes=["hardware/i2c.h"],
        ),
    },
    required_includes=["hardware/i2c.h", "pico/stdlib.h"],
    required_defines=["MPU6050_ADDR=0x68", "MPU6050_PICO_I2C=i2c0"],
    required_compile_flags=[],
    init_template=(
        "#ifndef MPU6050_ADDR\n"
        "#define MPU6050_ADDR 0x68  /* AD0 = GND; use 0x69 if AD0 = 3V3 */\n"
        "#endif\n"
        "#ifndef MPU6050_PICO_I2C\n"
        "#define MPU6050_PICO_I2C i2c0\n"
        "#endif"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
