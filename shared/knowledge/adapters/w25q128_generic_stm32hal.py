# SPDX-License-Identifier: AGPL-3.0-or-later
"""W25Q128 generic SPI flash → STM32 HAL adapter."""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="w25q128_generic_stm32hal_v1",
    contract_id="flash_storage_v1",
    driver_option_key="generic_spi",
    target_sdk="stm32hal",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "/* CS high (deselect flash) */\n"
                "HAL_GPIO_WritePin(FLASH_CS_GPIO_Port, FLASH_CS_Pin, GPIO_PIN_SET);\n"
                "/* Read JEDEC ID to verify device */\n"
                "uint8_t cmd = 0x9F;\n"
                "uint8_t jedec[3];\n"
                "HAL_GPIO_WritePin(FLASH_CS_GPIO_Port, FLASH_CS_Pin, GPIO_PIN_RESET);\n"
                "HAL_SPI_Transmit(&hspi1, &cmd, 1, 100);\n"
                "HAL_SPI_Receive(&hspi1, jedec, 3, 100);\n"
                "HAL_GPIO_WritePin(FLASH_CS_GPIO_Port, FLASH_CS_Pin, GPIO_PIN_SET);\n"
                "/* jedec[0]=0xEF (Winbond), jedec[1]=0x40, jedec[2]=0x18 (128Mbit) */"
            ),
            includes=["spi.h", "gpio.h"],
            error_handling="none",
        ),
        "read": CodeTemplate(
            template=(
                "uint8_t cmd[4] = {0x03, (addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF};\n"
                "HAL_GPIO_WritePin(FLASH_CS_GPIO_Port, FLASH_CS_Pin, GPIO_PIN_RESET);\n"
                "HAL_SPI_Transmit(&hspi1, cmd, 4, 100);\n"
                "HAL_SPI_Receive(&hspi1, buf, len, 1000);\n"
                "HAL_GPIO_WritePin(FLASH_CS_GPIO_Port, FLASH_CS_Pin, GPIO_PIN_SET);"
            ),
            includes=["spi.h"],
        ),
        "write_enable": CodeTemplate(
            template=(
                "uint8_t cmd = 0x06;\n"
                "HAL_GPIO_WritePin(FLASH_CS_GPIO_Port, FLASH_CS_Pin, GPIO_PIN_RESET);\n"
                "HAL_SPI_Transmit(&hspi1, &cmd, 1, 100);\n"
                "HAL_GPIO_WritePin(FLASH_CS_GPIO_Port, FLASH_CS_Pin, GPIO_PIN_SET);"
            ),
            includes=["spi.h"],
        ),
        "page_program": CodeTemplate(
            template=(
                "uint8_t cmd[4] = {0x02, (addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF};\n"
                "HAL_GPIO_WritePin(FLASH_CS_GPIO_Port, FLASH_CS_Pin, GPIO_PIN_RESET);\n"
                "HAL_SPI_Transmit(&hspi1, cmd, 4, 100);\n"
                "HAL_SPI_Transmit(&hspi1, data, len, 1000);\n"
                "HAL_GPIO_WritePin(FLASH_CS_GPIO_Port, FLASH_CS_Pin, GPIO_PIN_SET);\n"
                "HAL_Delay(3);  /* Page program time ~3ms */"
            ),
            includes=["spi.h"],
        ),
        "sector_erase": CodeTemplate(
            template=(
                "uint8_t cmd[4] = {0x20, (addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF};\n"
                "HAL_GPIO_WritePin(FLASH_CS_GPIO_Port, FLASH_CS_Pin, GPIO_PIN_RESET);\n"
                "HAL_SPI_Transmit(&hspi1, cmd, 4, 100);\n"
                "HAL_GPIO_WritePin(FLASH_CS_GPIO_Port, FLASH_CS_Pin, GPIO_PIN_SET);\n"
                "HAL_Delay(400);  /* Sector erase time up to 400ms */"
            ),
            includes=["spi.h"],
        ),
    },
    required_includes=["spi.h", "gpio.h"],
    required_defines=[
        "FLASH_CS_GPIO_Port=GPIOA",
        "FLASH_CS_Pin=GPIO_PIN_4",
    ],
    required_compile_flags=[],
    init_template=(
        "/* W25Q128 SPI: configure hspi1 for Mode 0 or 3, 8-bit, up to 104 MHz.\n"
        "   CS pin must be configured as GPIO Output (HAL GPIO, not hardware NSS).\n"
        "   Adjust FLASH_CS_GPIO_Port and FLASH_CS_Pin to match your schematic. */"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
