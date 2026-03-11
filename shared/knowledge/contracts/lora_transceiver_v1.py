# SPDX-License-Identifier: AGPL-3.0-or-later
"""lora_transceiver_v1 — Logical Driver Contract.

Covers: SX1276, SX1262, RFM95W, and similar LoRa transceivers.
"""
from shared.knowledge.binding_schema import (
    Capability,
    FunctionSignature,
    LogicalDriverContract,
    Parameter,
)

CONTRACT = LogicalDriverContract(
    contract_id="lora_transceiver_v1",
    contract_version="1.0.0",
    category="comms",
    description="LoRa radio transceiver for long-range low-power communication",
    capabilities=[
        Capability(
            name="init",
            description="Initialize the radio module",
            return_type="int",
            parameters=[
                Parameter(name="spi_handle", type="void*"),
                Parameter(name="cs_pin", type="uint8_t"),
                Parameter(name="reset_pin", type="uint8_t"),
                Parameter(name="dio0_pin", type="uint8_t"),
            ],
            required=True,
        ),
        Capability(
            name="set_frequency",
            description="Set carrier frequency in Hz",
            return_type="int",
            parameters=[
                Parameter(name="frequency_hz", type="uint32_t", description="e.g. 868000000 for 868MHz"),
            ],
            required=True,
        ),
        Capability(
            name="send",
            description="Send a packet",
            return_type="int",
            parameters=[
                Parameter(name="data", type="const uint8_t*"),
                Parameter(name="length", type="uint8_t"),
            ],
            required=True,
        ),
        Capability(
            name="receive",
            description="Receive a packet (blocking or with timeout)",
            return_type="int",
            parameters=[
                Parameter(name="buffer", type="uint8_t*"),
                Parameter(name="max_length", type="uint8_t"),
                Parameter(name="timeout_ms", type="uint32_t", default="5000"),
            ],
            required=True,
        ),
        Capability(
            name="sleep",
            description="Put radio into low-power sleep mode",
            return_type="int",
            required=True,
        ),
        Capability(
            name="set_spreading_factor",
            description="Set LoRa spreading factor (6-12)",
            return_type="int",
            parameters=[
                Parameter(name="sf", type="uint8_t", description="6-12"),
            ],
            required=False,
        ),
        Capability(
            name="set_bandwidth",
            description="Set LoRa bandwidth in Hz",
            return_type="int",
            parameters=[
                Parameter(name="bw_hz", type="uint32_t", description="e.g. 125000"),
            ],
            required=False,
        ),
        Capability(
            name="set_tx_power",
            description="Set transmit power in dBm",
            return_type="int",
            parameters=[
                Parameter(name="power_dbm", type="int8_t"),
            ],
            required=False,
        ),
        Capability(
            name="get_rssi",
            description="Get RSSI of last received packet",
            return_type="int16_t",
            required=False,
        ),
    ],
    init_signature=FunctionSignature(
        name="lora_init",
        parameters=[
            Parameter(name="spi_handle", type="void*"),
            Parameter(name="cs_pin", type="uint8_t"),
            Parameter(name="reset_pin", type="uint8_t"),
            Parameter(name="dio0_pin", type="uint8_t"),
        ],
        return_type="int",
    ),
)

from shared.knowledge.contracts import register_contract
register_contract(CONTRACT)
