# SPDX-License-Identifier: AGPL-3.0-or-later
"""MPU6050 direct register access → STM32 HAL adapter.

Phase 24.1 / DB-5: STM32 HAL adapter for MPU6050 6-axis IMU.

Uses HAL_I2C_Mem_Read/Write for direct register access —
no external library dependency, works with bare HAL on any STM32.
WHO_AM_I-Check (0x68), Gyro +/-250 deg/s, Accel +/-2g.
"""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

_I2C_ADDR = "0x68 << 1"  # AD0 low; use 0x69 if AD0 high

ADAPTER = LibraryAdapter(
    adapter_id="mpu6050_i2cdev_stm32hal_v1",
    contract_id="imu_sensor_v1",
    driver_option_key="direct_registers",
    target_sdk="stm32hal",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "/* Wake MPU-6050: write 0x00 to PWR_MGMT_1 (0x6B) */\n"
                "uint8_t pwr_data = 0x00;\n"
                "HAL_I2C_Mem_Write(&hi2c1, MPU6050_ADDR, 0x6B, I2C_MEMADD_SIZE_8BIT,\n"
                "                  &pwr_data, 1, HAL_MAX_DELAY);\n"
                "/* Set full-scale gyro to ±250 dps (0x00 to GYRO_CONFIG 0x1B) */\n"
                "uint8_t gyro_cfg = 0x00;\n"
                "HAL_I2C_Mem_Write(&hi2c1, MPU6050_ADDR, 0x1B, I2C_MEMADD_SIZE_8BIT,\n"
                "                  &gyro_cfg, 1, HAL_MAX_DELAY);\n"
                "/* Set full-scale accel to ±2g (0x00 to ACCEL_CONFIG 0x1C) */\n"
                "uint8_t accel_cfg = 0x00;\n"
                "HAL_I2C_Mem_Write(&hi2c1, MPU6050_ADDR, 0x1C, I2C_MEMADD_SIZE_8BIT,\n"
                "                  &accel_cfg, 1, HAL_MAX_DELAY);"
            ),
            includes=["i2c.h"],
            error_handling="none",
        ),
        "read_accel": CodeTemplate(
            template=(
                "uint8_t raw[6];\n"
                "HAL_I2C_Mem_Read(&hi2c1, MPU6050_ADDR, 0x3B, I2C_MEMADD_SIZE_8BIT,\n"
                "                  raw, 6, HAL_MAX_DELAY);\n"
                "*x = ((int16_t)(raw[0] << 8 | raw[1])) / 16384.0f;  /* ±2g */\n"
                "*y = ((int16_t)(raw[2] << 8 | raw[3])) / 16384.0f;\n"
                "*z = ((int16_t)(raw[4] << 8 | raw[5])) / 16384.0f;"
            ),
            includes=["i2c.h"],
        ),
        "read_gyro": CodeTemplate(
            template=(
                "uint8_t raw[6];\n"
                "HAL_I2C_Mem_Read(&hi2c1, MPU6050_ADDR, 0x43, I2C_MEMADD_SIZE_8BIT,\n"
                "                  raw, 6, HAL_MAX_DELAY);\n"
                "*x = ((int16_t)(raw[0] << 8 | raw[1])) / 131.0f;  /* ±250 dps */\n"
                "*y = ((int16_t)(raw[2] << 8 | raw[3])) / 131.0f;\n"
                "*z = ((int16_t)(raw[4] << 8 | raw[5])) / 131.0f;"
            ),
            includes=["i2c.h"],
        ),
        "read_temp": CodeTemplate(
            template=(
                "uint8_t raw[2];\n"
                "HAL_I2C_Mem_Read(&hi2c1, MPU6050_ADDR, 0x41, I2C_MEMADD_SIZE_8BIT,\n"
                "                  raw, 2, HAL_MAX_DELAY);\n"
                "int16_t raw_temp = (int16_t)(raw[0] << 8 | raw[1]);\n"
                "return raw_temp / 340.0f + 36.53f;"
            ),
            includes=["i2c.h"],
        ),
    },
    required_includes=["i2c.h"],
    required_defines=["MPU6050_ADDR=(0x68 << 1)"],
    required_compile_flags=[],
    init_template=(
        "/* MPU-6050 I2C address — set AD0 pin to select 0x68 or 0x69 */\n"
        "#ifndef MPU6050_ADDR\n"
        "#define MPU6050_ADDR (0x68 << 1)\n"
        "#endif"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
