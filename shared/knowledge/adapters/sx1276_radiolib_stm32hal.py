# SPDX-License-Identifier: AGPL-3.0-or-later
"""SX1276 RadioLib → STM32 HAL adapter (C-style wrapper).

RadioLib is a C++ library. This adapter generates a thin C-compatible
wrapper that calls RadioLib from C firmware code via extern "C" bridges.
"""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="sx1276_radiolib_stm32hal_v1",
    contract_id="lora_transceiver_v1",
    driver_option_key="radiolib",
    target_sdk="stm32hal",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "/* RadioLib STM32 HAL SPI module — initialise in C++ context */\n"
                "lora_stm32_init(SX1276_FREQ_MHZ, SX1276_SF, SX1276_BW_KHZ,\n"
                "                SX1276_CR, SX1276_SYNC_WORD, SX1276_TX_DBM);"
            ),
            includes=["lora_stm32_bridge.h"],
            error_handling="return_code",
        ),
        "transmit": CodeTemplate(
            template=(
                "return lora_stm32_transmit(payload, length);"
            ),
            includes=["lora_stm32_bridge.h"],
        ),
        "receive": CodeTemplate(
            template=(
                "return lora_stm32_receive(buf, max_len, timeout_ms);"
            ),
            includes=["lora_stm32_bridge.h"],
        ),
        "set_frequency": CodeTemplate(
            template="lora_stm32_set_frequency(freq_mhz);",
            includes=["lora_stm32_bridge.h"],
        ),
        "sleep": CodeTemplate(
            template="lora_stm32_sleep();",
            includes=["lora_stm32_bridge.h"],
        ),
    },
    required_includes=["lora_stm32_bridge.h", "spi.h"],
    required_defines=[
        "SX1276_FREQ_MHZ=868.0f",
        "SX1276_SF=7",
        "SX1276_BW_KHZ=125.0f",
        "SX1276_CR=5",
        "SX1276_SYNC_WORD=0x12",
        "SX1276_TX_DBM=14",
    ],
    required_compile_flags=["-lstdc++"],
    init_template=(
        "/* lora_stm32_bridge.cpp — C++ RadioLib wrapper for STM32 HAL SPI\n"
        " *\n"
        " * Create an STM32HalSpi wrapper class that calls HAL_SPI_Transmit/Receive,\n"
        " * then pass it to the RadioLib SX1276 constructor:\n"
        " *\n"
        " *   SX1276 radio = new Module(&stm32_spi, NSS_PIN, DIO0_PIN, RESET_PIN);\n"
        " *   int state = radio.begin(freq, bw, sf, cr, syncWord, pwr);\n"
        " *\n"
        " * See RadioLib STM32 examples at https://github.com/jgromes/RadioLib/tree/master/examples\n"
        " */"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
