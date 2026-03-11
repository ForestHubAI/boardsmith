# SPDX-License-Identifier: AGPL-3.0-or-later
"""SX1276 RadioLib → ESP-IDF adapter."""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="sx1276_radiolib_espidf_v1",
    contract_id="lora_transceiver_v1",
    driver_option_key="radiolib",
    target_sdk="esp-idf",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "Module* mod = new Module(cs_pin, dio0_pin, reset_pin, -1, spi_handle);\n"
                "SX1276 radio = new Module(mod);\n"
                "int state = radio.begin();\n"
                "return (state == RADIOLIB_ERR_NONE) ? 0 : state;"
            ),
            includes=["RadioLib.h"],
        ),
        "set_frequency": CodeTemplate(
            template="return radio.setFrequency(frequency_hz / 1e6);",
            includes=["RadioLib.h"],
        ),
        "send": CodeTemplate(
            template=(
                "int state = radio.transmit(data, length);\n"
                "return (state == RADIOLIB_ERR_NONE) ? 0 : state;"
            ),
            includes=["RadioLib.h"],
        ),
        "receive": CodeTemplate(
            template=(
                "int state = radio.receive(buffer, max_length);\n"
                "return (state == RADIOLIB_ERR_NONE) ? radio.getPacketLength() : state;"
            ),
            includes=["RadioLib.h"],
        ),
        "sleep": CodeTemplate(
            template="return radio.sleep();",
            includes=["RadioLib.h"],
        ),
        "set_spreading_factor": CodeTemplate(
            template="return radio.setSpreadingFactor(sf);",
            includes=["RadioLib.h"],
        ),
        "set_bandwidth": CodeTemplate(
            template="return radio.setBandwidth(bw_hz / 1000.0);",
            includes=["RadioLib.h"],
        ),
        "set_tx_power": CodeTemplate(
            template="return radio.setOutputPower(power_dbm);",
            includes=["RadioLib.h"],
        ),
        "get_rssi": CodeTemplate(
            template="return (int16_t)radio.getRSSI();",
            includes=["RadioLib.h"],
        ),
    },
    required_includes=["RadioLib.h"],
    required_defines=[],
    init_template=(
        "/* RadioLib for ESP-IDF.\n"
        "   RadioLib supports ESP-IDF natively via its HAL abstraction layer.\n"
        "   Use EspHal for ESP-IDF integration.\n"
        "   See: https://github.com/jgromes/RadioLib/wiki/ESP-IDF */"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
