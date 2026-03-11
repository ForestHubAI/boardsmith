# SPDX-License-Identifier: AGPL-3.0-or-later
"""W25Q128 Generic SPI Flash → ESP-IDF adapter."""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="w25q128_generic_espidf_v1",
    contract_id="flash_storage_v1",
    driver_option_key="generic_spiflash",
    target_sdk="esp-idf",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "spi_flash_chip_t flash = {0};\n"
                "flash.spi = spi_handle;\n"
                "flash.cs_pin = cs_pin;\n"
                "gpio_set_direction(cs_pin, GPIO_MODE_OUTPUT);\n"
                "gpio_set_level(cs_pin, 1);\n"
                "uint32_t id = flash_read_jedec_id(&flash);\n"
                "return (id != 0) ? 0 : -1;"
            ),
            includes=["driver/spi_master.h", "driver/gpio.h"],
        ),
        "read": CodeTemplate(
            template=(
                "gpio_set_level(cs_pin, 0);\n"
                "uint8_t cmd[4] = {0x03, (address>>16)&0xFF, (address>>8)&0xFF, address&0xFF};\n"
                "spi_transaction_t t = {.tx_buffer=cmd, .length=32, .rx_buffer=buffer, .rxlength=length*8};\n"
                "spi_device_transmit(spi_handle, &t);\n"
                "gpio_set_level(cs_pin, 1);\n"
                "return 0;"
            ),
            includes=["driver/spi_master.h"],
        ),
        "write": CodeTemplate(
            template=(
                "/* Write Enable */\n"
                "flash_write_enable(&flash);\n"
                "/* Page Program (0x02) — max 256 bytes */\n"
                "gpio_set_level(cs_pin, 0);\n"
                "uint8_t cmd[4] = {0x02, (address>>16)&0xFF, (address>>8)&0xFF, address&0xFF};\n"
                "spi_transaction_t t = {.tx_buffer=cmd, .length=32};\n"
                "spi_device_transmit(spi_handle, &t);\n"
                "t.tx_buffer = data; t.length = length * 8;\n"
                "spi_device_transmit(spi_handle, &t);\n"
                "gpio_set_level(cs_pin, 1);\n"
                "flash_wait_busy(&flash);\n"
                "return 0;"
            ),
            includes=["driver/spi_master.h"],
        ),
        "erase_sector": CodeTemplate(
            template=(
                "flash_write_enable(&flash);\n"
                "gpio_set_level(cs_pin, 0);\n"
                "uint8_t cmd[4] = {0x20, (sector_address>>16)&0xFF, (sector_address>>8)&0xFF, sector_address&0xFF};\n"
                "spi_transaction_t t = {.tx_buffer=cmd, .length=32};\n"
                "spi_device_transmit(spi_handle, &t);\n"
                "gpio_set_level(cs_pin, 1);\n"
                "flash_wait_busy(&flash);\n"
                "return 0;"
            ),
            includes=["driver/spi_master.h"],
        ),
        "read_jedec_id": CodeTemplate(
            template=(
                "gpio_set_level(cs_pin, 0);\n"
                "uint8_t cmd = 0x9F;\n"
                "uint8_t id[3];\n"
                "spi_transaction_t t = {.tx_buffer=&cmd, .length=8, .rx_buffer=id, .rxlength=24};\n"
                "spi_device_transmit(spi_handle, &t);\n"
                "gpio_set_level(cs_pin, 1);\n"
                "return (id[0] << 16) | (id[1] << 8) | id[2];"
            ),
            includes=["driver/spi_master.h"],
        ),
    },
    required_includes=["driver/spi_master.h", "driver/gpio.h"],
    required_defines=[],
    init_template=(
        "/* Generic W25Q SPI Flash driver for ESP-IDF.\n"
        "   Uses raw SPI transactions for maximum portability.\n"
        "   Alternatively, use ESP-IDF's esp_flash API for integrated flash support. */"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
