# SPDX-License-Identifier: AGPL-3.0-or-later
"""flash_storage_v1 — Logical Driver Contract.

Covers: W25Q128, W25Q64, AT25SF128, IS25LP128, and similar SPI NOR flash.
"""
from shared.knowledge.binding_schema import (
    Capability,
    FunctionSignature,
    LogicalDriverContract,
    Parameter,
)

CONTRACT = LogicalDriverContract(
    contract_id="flash_storage_v1",
    contract_version="1.0.0",
    category="storage",
    description="SPI NOR flash storage with sector-based access",
    capabilities=[
        Capability(
            name="init",
            description="Initialize the flash and read JEDEC ID",
            return_type="int",
            parameters=[
                Parameter(name="spi_handle", type="void*"),
                Parameter(name="cs_pin", type="uint8_t"),
            ],
            required=True,
        ),
        Capability(
            name="read",
            description="Read data from flash",
            return_type="int",
            parameters=[
                Parameter(name="address", type="uint32_t"),
                Parameter(name="buffer", type="uint8_t*"),
                Parameter(name="length", type="uint32_t"),
            ],
            required=True,
        ),
        Capability(
            name="write",
            description="Write data to flash (page program, max 256 bytes)",
            return_type="int",
            parameters=[
                Parameter(name="address", type="uint32_t"),
                Parameter(name="data", type="const uint8_t*"),
                Parameter(name="length", type="uint32_t"),
            ],
            required=True,
        ),
        Capability(
            name="erase_sector",
            description="Erase a 4KB sector",
            return_type="int",
            parameters=[
                Parameter(name="sector_address", type="uint32_t"),
            ],
            required=True,
        ),
        Capability(
            name="erase_block",
            description="Erase a 64KB block",
            return_type="int",
            parameters=[
                Parameter(name="block_address", type="uint32_t"),
            ],
            required=False,
        ),
        Capability(
            name="erase_chip",
            description="Erase entire flash chip",
            return_type="int",
            required=False,
        ),
        Capability(
            name="read_jedec_id",
            description="Read JEDEC manufacturer/device ID",
            return_type="uint32_t",
            required=False,
        ),
    ],
    init_signature=FunctionSignature(
        name="flash_init",
        parameters=[
            Parameter(name="spi_handle", type="void*"),
            Parameter(name="cs_pin", type="uint8_t"),
        ],
        return_type="int",
    ),
)

from shared.knowledge.contracts import register_contract
register_contract(CONTRACT)
