# SPDX-License-Identifier: AGPL-3.0-or-later
"""temperature_sensor_v1 — Logical Driver Contract.

Covers: BME280, BMP390, AHT20, SHT31, and similar environment sensors.
"""
from shared.knowledge.binding_schema import (
    Capability,
    FunctionSignature,
    LogicalDriverContract,
    Parameter,
)

CONTRACT = LogicalDriverContract(
    contract_id="temperature_sensor_v1",
    contract_version="1.0.0",
    category="sensor",
    description="Temperature/humidity/pressure environment sensor contract",
    capabilities=[
        Capability(
            name="init",
            description="Initialize the sensor with default settings",
            return_type="int",
            parameters=[
                Parameter(name="bus_handle", type="void*", description="I2C/SPI bus handle"),
                Parameter(name="address", type="uint8_t", description="I2C address", default="0x76"),
            ],
            required=True,
        ),
        Capability(
            name="read_temperature",
            description="Read temperature in degrees Celsius",
            return_type="float",
            required=True,
        ),
        Capability(
            name="read_humidity",
            description="Read relative humidity in percent (0-100)",
            return_type="float",
            required=False,
        ),
        Capability(
            name="read_pressure",
            description="Read atmospheric pressure in hPa",
            return_type="float",
            required=False,
        ),
        Capability(
            name="set_mode",
            description="Set power mode (sleep, forced, normal)",
            return_type="int",
            parameters=[
                Parameter(name="mode", type="uint8_t", description="0=sleep, 1=forced, 3=normal"),
            ],
            required=False,
        ),
    ],
    init_signature=FunctionSignature(
        name="sensor_init",
        parameters=[
            Parameter(name="bus_handle", type="void*"),
            Parameter(name="address", type="uint8_t", default="0x76"),
        ],
        return_type="int",
    ),
    deinit_signature=FunctionSignature(
        name="sensor_deinit",
        return_type="int",
    ),
)

from shared.knowledge.contracts import register_contract
register_contract(CONTRACT)
