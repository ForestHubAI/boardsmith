# SPDX-License-Identifier: AGPL-3.0-or-later
"""co2_sensor_v1 — Logical Driver Contract.

Covers: SCD41, SCD30, MH-Z19, and similar CO2 sensors.
"""
from shared.knowledge.binding_schema import (
    Capability,
    FunctionSignature,
    LogicalDriverContract,
    Parameter,
)

CONTRACT = LogicalDriverContract(
    contract_id="co2_sensor_v1",
    contract_version="1.0.0",
    category="sensor",
    description="CO2 concentration sensor with optional temperature/humidity",
    capabilities=[
        Capability(
            name="init",
            description="Initialize the CO2 sensor",
            return_type="int",
            parameters=[
                Parameter(name="bus_handle", type="void*"),
                Parameter(name="address", type="uint8_t", default="0x62"),
            ],
            required=True,
        ),
        Capability(
            name="start_measurement",
            description="Start periodic measurement",
            return_type="int",
            required=True,
        ),
        Capability(
            name="read_co2",
            description="Read CO2 concentration in ppm",
            return_type="uint16_t",
            required=True,
        ),
        Capability(
            name="read_temperature",
            description="Read temperature in degrees Celsius",
            return_type="float",
            required=False,
        ),
        Capability(
            name="read_humidity",
            description="Read relative humidity in percent",
            return_type="float",
            required=False,
        ),
        Capability(
            name="stop_measurement",
            description="Stop periodic measurement for low power",
            return_type="int",
            required=False,
        ),
        Capability(
            name="set_altitude",
            description="Set altitude compensation in meters",
            return_type="int",
            parameters=[
                Parameter(name="altitude_m", type="uint16_t"),
            ],
            required=False,
        ),
    ],
    init_signature=FunctionSignature(
        name="co2_init",
        parameters=[
            Parameter(name="bus_handle", type="void*"),
            Parameter(name="address", type="uint8_t", default="0x62"),
        ],
        return_type="int",
    ),
)

from shared.knowledge.contracts import register_contract
register_contract(CONTRACT)
