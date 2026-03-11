# SPDX-License-Identifier: AGPL-3.0-or-later
"""W25Q128 Flash → Zephyr RTOS adapter using Zephyr flash/SPI driver."""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="w25q128_generic_zephyr_v1",
    contract_id="flash_storage_v1",
    driver_option_key="generic_spi",
    target_sdk="zephyr",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "const struct device *flash_dev = DEVICE_DT_GET_ANY(jedec_spi_nor);\n"
                "if (!device_is_ready(flash_dev)) { return -ENODEV; }\n"
                "/* W25Q128 Zephyr flash driver auto-configures via DTS */"
            ),
            includes=["zephyr/device.h", "zephyr/drivers/flash.h"],
            error_handling="return_code",
        ),
        "read": CodeTemplate(
            template=(
                "int rc = flash_read(flash_dev, offset, buf, len);\n"
                "if (rc != 0) { return rc; }\n"
                "return len;"
            ),
            includes=["zephyr/drivers/flash.h"],
        ),
        "write": CodeTemplate(
            template=(
                "/* W25Q128 page size = 256 bytes; write must be within a page */\n"
                "int rc = flash_write(flash_dev, offset, buf, len);\n"
                "if (rc != 0) { return rc; }\n"
                "return len;"
            ),
            includes=["zephyr/drivers/flash.h"],
        ),
        "erase_sector": CodeTemplate(
            template=(
                "/* Erase 4096-byte sector containing addr */\n"
                "uint32_t sector_addr = addr & ~0xFFFU;\n"
                "int rc = flash_erase(flash_dev, sector_addr, 4096);\n"
                "return rc;"
            ),
            includes=["zephyr/drivers/flash.h"],
        ),
        "chip_erase": CodeTemplate(
            template=(
                "/* Bulk erase 16MB (takes ~30 seconds) */\n"
                "int rc = flash_erase(flash_dev, 0, 16 * 1024 * 1024);\n"
                "return rc;"
            ),
            includes=["zephyr/drivers/flash.h"],
        ),
        "get_status": CodeTemplate(
            template=(
                "/* Flash ready when no write/erase in progress — checked by driver */\n"
                "return flash_get_parameters(flash_dev) != NULL ? 0 : -ENODEV;"
            ),
            includes=["zephyr/drivers/flash.h"],
        ),
    },
    required_includes=[
        "zephyr/device.h",
        "zephyr/drivers/flash.h",
        "zephyr/drivers/spi.h",
        "zephyr/kernel.h",
    ],
    required_defines=["CONFIG_FLASH=y", "CONFIG_SPI=y", "CONFIG_SPI_NOR=y"],
    required_compile_flags=[],
    init_template=(
        "/* Zephyr devicetree overlay:\n"
        " * &spi0 {\n"
        " *   w25q128: w25q128@0 {\n"
        " *     compatible = \"jedec,spi-nor\";\n"
        " *     reg = <0>;\n"
        " *     spi-max-frequency = <104000000>;\n"
        " *     size = <DT_SIZE_M(16)>;\n"
        " *     jedec-id = [ef 40 18];\n"
        " *     has-dpd; t-enter-dpd = <3000>; t-exit-dpd = <30000>;\n"
        " *   };\n"
        " * };\n"
        " * prj.conf: CONFIG_FLASH=y CONFIG_SPI_NOR=y CONFIG_SPI=y\n"
        " */"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
