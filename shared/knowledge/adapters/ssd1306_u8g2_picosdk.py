# SPDX-License-Identifier: AGPL-3.0-or-later
"""SSD1306 u8g2 → Raspberry Pi Pico SDK adapter."""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="ssd1306_u8g2_picosdk_v1",
    contract_id="display_oled_v1",
    driver_option_key="u8g2",
    target_sdk="pico-sdk",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "u8g2_Setup_ssd1306_i2c_128x64_noname_f(&u8g2, U8G2_R0,\n"
                "    u8x8_byte_pico_hw_i2c, u8x8_pico_gpio_and_delay);\n"
                "u8g2_InitDisplay(&u8g2);\n"
                "u8g2_SetPowerSave(&u8g2, 0);"
            ),
            includes=["u8g2.h", "hardware/i2c.h"],
            error_handling="none",
        ),
        "clear": CodeTemplate(
            template="u8g2_ClearBuffer(&u8g2);",
            includes=["u8g2.h"],
        ),
        "draw_text": CodeTemplate(
            template=(
                "u8g2_SetFont(&u8g2, u8g2_font_ncenB08_tr);\n"
                "u8g2_DrawStr(&u8g2, x, y, text);\n"
                "u8g2_SendBuffer(&u8g2);"
            ),
            includes=["u8g2.h"],
        ),
        "set_contrast": CodeTemplate(
            template="u8g2_SetContrast(&u8g2, contrast);",
            includes=["u8g2.h"],
        ),
        "display_on": CodeTemplate(
            template="u8g2_SetPowerSave(&u8g2, 0);",
            includes=["u8g2.h"],
        ),
        "display_off": CodeTemplate(
            template="u8g2_SetPowerSave(&u8g2, 1);",
            includes=["u8g2.h"],
        ),
    },
    required_includes=["u8g2.h", "hardware/i2c.h", "pico/stdlib.h"],
    required_defines=["SSD1306_I2C_ADDR=0x3C"],
    required_compile_flags=[],
    init_template=(
        "/* u8g2 HAL callbacks for Raspberry Pi Pico SDK I2C */\n"
        "#define SSD1306_PICO_I2C i2c0\n"
        "static u8g2_t u8g2;\n"
        "uint8_t u8x8_byte_pico_hw_i2c(u8x8_t *u8x8, uint8_t msg, uint8_t arg_int, void *arg_ptr) {\n"
        "    static uint8_t buf[64]; static uint8_t buf_len;\n"
        "    switch (msg) {\n"
        "        case U8X8_MSG_BYTE_INIT: break;\n"
        "        case U8X8_MSG_BYTE_START_TRANSFER: buf_len = 0; break;\n"
        "        case U8X8_MSG_BYTE_SEND:\n"
        "            memcpy(buf + buf_len, arg_ptr, arg_int); buf_len += arg_int; break;\n"
        "        case U8X8_MSG_BYTE_END_TRANSFER:\n"
        "            i2c_write_blocking(SSD1306_PICO_I2C, SSD1306_I2C_ADDR, buf, buf_len, false);\n"
        "            break;\n"
        "    }\n"
        "    return 1;\n"
        "}\n"
        "uint8_t u8x8_pico_gpio_and_delay(u8x8_t *u8x8, uint8_t msg, uint8_t arg_int, void *arg_ptr) {\n"
        "    switch (msg) {\n"
        "        case U8X8_MSG_GPIO_AND_DELAY_INIT: break;\n"
        "        case U8X8_MSG_DELAY_MILLI: sleep_ms(arg_int); break;\n"
        "        case U8X8_MSG_DELAY_MICRO: sleep_us(arg_int); break;\n"
        "    }\n"
        "    return 1;\n"
        "}"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
