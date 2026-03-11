# SPDX-License-Identifier: AGPL-3.0-or-later
"""imu_sensor_v1 — Logical Driver Contract.

Covers: MPU6050, LSM6DS3, ICM-42688, and similar IMU sensors.
"""
from shared.knowledge.binding_schema import (
    Capability,
    FunctionSignature,
    LogicalDriverContract,
    Parameter,
)

CONTRACT = LogicalDriverContract(
    contract_id="imu_sensor_v1",
    contract_version="1.0.0",
    category="sensor",
    description="Inertial Measurement Unit (accelerometer + gyroscope) contract",
    capabilities=[
        Capability(
            name="init",
            description="Initialize the IMU with default settings",
            return_type="int",
            parameters=[
                Parameter(name="bus_handle", type="void*"),
                Parameter(name="address", type="uint8_t", default="0x68"),
            ],
            required=True,
        ),
        Capability(
            name="read_accel",
            description="Read 3-axis acceleration in g (returns x, y, z via pointer)",
            return_type="int",
            parameters=[
                Parameter(name="x", type="float*"),
                Parameter(name="y", type="float*"),
                Parameter(name="z", type="float*"),
            ],
            required=True,
        ),
        Capability(
            name="read_gyro",
            description="Read 3-axis angular velocity in deg/s",
            return_type="int",
            parameters=[
                Parameter(name="x", type="float*"),
                Parameter(name="y", type="float*"),
                Parameter(name="z", type="float*"),
            ],
            required=True,
        ),
        Capability(
            name="read_temp",
            description="Read die temperature in degrees Celsius",
            return_type="float",
            required=False,
        ),
        Capability(
            name="set_accel_range",
            description="Set accelerometer full-scale range",
            return_type="int",
            parameters=[
                Parameter(name="range_g", type="uint8_t", description="2, 4, 8, or 16"),
            ],
            required=False,
        ),
        Capability(
            name="set_gyro_range",
            description="Set gyroscope full-scale range",
            return_type="int",
            parameters=[
                Parameter(name="range_dps", type="uint16_t", description="250, 500, 1000, or 2000"),
            ],
            required=False,
        ),
    ],
    init_signature=FunctionSignature(
        name="imu_init",
        parameters=[
            Parameter(name="bus_handle", type="void*"),
            Parameter(name="address", type="uint8_t", default="0x68"),
        ],
        return_type="int",
    ),
)

from shared.knowledge.contracts import register_contract
register_contract(CONTRACT)
