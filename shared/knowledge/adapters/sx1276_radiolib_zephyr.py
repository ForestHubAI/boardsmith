# SPDX-License-Identifier: AGPL-3.0-or-later
"""SX1276 RadioLib → Zephyr RTOS adapter using LoRaWAN subsystem or RadioLib."""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="sx1276_radiolib_zephyr_v1",
    contract_id="lora_transceiver_v1",
    driver_option_key="radiolib",
    target_sdk="zephyr",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "const struct device *lora_dev = DEVICE_DT_GET_ANY(semtech_sx1276);\n"
                "if (!device_is_ready(lora_dev)) { return -ENODEV; }\n"
                "struct lora_modem_config cfg = {\n"
                "    .frequency = 868000000,\n"
                "    .bandwidth = BW_125_KHZ,\n"
                "    .datarate = SF_7,\n"
                "    .preamble_len = 8,\n"
                "    .coding_rate = CR_4_5,\n"
                "    .tx_power = 14,\n"
                "    .tx = true,\n"
                "};\n"
                "int rc = lora_config(lora_dev, &cfg);\n"
                "if (rc != 0) { return rc; }\n"
                "return 0;"
            ),
            includes=["zephyr/device.h", "zephyr/drivers/lora.h"],
            error_handling="return_code",
        ),
        "transmit": CodeTemplate(
            template=(
                "int rc = lora_send(lora_dev, (uint8_t *)payload, payload_len);\n"
                "return rc;"
            ),
            includes=["zephyr/drivers/lora.h"],
        ),
        "receive": CodeTemplate(
            template=(
                "int16_t rssi;\n"
                "int8_t snr;\n"
                "int len = lora_recv(lora_dev, buf, max_len, K_FOREVER, &rssi, &snr);\n"
                "if (len < 0) { return len; }\n"
                "*rssi_out = rssi;\n"
                "*snr_out = snr;\n"
                "return len;"
            ),
            includes=["zephyr/drivers/lora.h"],
        ),
        "set_frequency": CodeTemplate(
            template=(
                "struct lora_modem_config cfg = {.frequency = freq_hz, .tx = false};\n"
                "lora_config(lora_dev, &cfg);"
            ),
            includes=["zephyr/drivers/lora.h"],
        ),
        "set_tx_power": CodeTemplate(
            template=(
                "struct lora_modem_config cfg = {.tx_power = power_dbm, .tx = true};\n"
                "lora_config(lora_dev, &cfg);"
            ),
            includes=["zephyr/drivers/lora.h"],
        ),
        "sleep": CodeTemplate(
            template=(
                "struct lora_modem_config cfg = {.tx = false};\n"
                "lora_config(lora_dev, &cfg);  /* Zephyr driver handles sleep mode */"
            ),
            includes=["zephyr/drivers/lora.h"],
        ),
    },
    required_includes=[
        "zephyr/device.h",
        "zephyr/drivers/lora.h",
        "zephyr/drivers/spi.h",
        "zephyr/kernel.h",
    ],
    required_defines=["CONFIG_LORA=y", "CONFIG_LORA_SX1276=y", "CONFIG_SPI=y"],
    required_compile_flags=[],
    init_template=(
        "/* Zephyr devicetree overlay:\n"
        " * &spi1 {\n"
        " *   sx1276: sx1276@0 {\n"
        " *     compatible = \"semtech,sx1276\";\n"
        " *     reg = <0>;\n"
        " *     spi-max-frequency = <1000000>;\n"
        " *     reset-gpios = <&gpio0 3 GPIO_ACTIVE_LOW>;\n"
        " *     dio-gpios = <&gpio0 27 GPIO_ACTIVE_HIGH>,  /* DIO0 */\n"
        " *                 <&gpio0 26 GPIO_ACTIVE_HIGH>;  /* DIO1 */\n"
        " *     power-amplifier-output = \"rfo\";  /* or \"pa-boost\" */\n"
        " *   };\n"
        " * };\n"
        " * prj.conf: CONFIG_LORA=y CONFIG_LORA_SX1276=y CONFIG_SPI=y\n"
        " */"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
