# SPDX-License-Identifier: AGPL-3.0-or-later
"""SSD1306 U8g2 → ESP-IDF adapter."""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="ssd1306_u8g2_espidf_v1",
    contract_id="display_oled_v1",
    driver_option_key="u8g2",
    target_sdk="esp-idf",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "u8g2_t u8g2;\n"
                "u8g2_Setup_ssd1306_i2c_128x64_noname_f(&u8g2, U8G2_R0, u8x8_byte_hw_i2c_esp32, u8x8_gpio_and_delay_esp32);\n"
                "u8g2_SetI2CAddress(&u8g2, address << 1);\n"
                "u8g2_InitDisplay(&u8g2);\n"
                "u8g2_SetPowerSave(&u8g2, 0);"
            ),
            includes=["u8g2.h"],
        ),
        "clear": CodeTemplate(
            template="u8g2_ClearBuffer(&u8g2);",
            includes=["u8g2.h"],
        ),
        "draw_pixel": CodeTemplate(
            template="u8g2_DrawPixel(&u8g2, x, y);",
            includes=["u8g2.h"],
        ),
        "draw_text": CodeTemplate(
            template=(
                "u8g2_SetFont(&u8g2, u8g2_font_ncenB08_tr);\n"
                "u8g2_DrawStr(&u8g2, x, y, text);"
            ),
            includes=["u8g2.h"],
        ),
        "refresh": CodeTemplate(
            template="u8g2_SendBuffer(&u8g2);",
            includes=["u8g2.h"],
        ),
        "set_contrast": CodeTemplate(
            template="u8g2_SetContrast(&u8g2, contrast);",
            includes=["u8g2.h"],
        ),
        "set_display_on": CodeTemplate(
            template="u8g2_SetPowerSave(&u8g2, on ? 0 : 1);",
            includes=["u8g2.h"],
        ),
    },
    required_includes=["u8g2.h"],
    required_defines=[],
    init_template=(
        "/* U8g2 I2C HAL for ESP-IDF — implement u8x8_byte_hw_i2c_esp32 and\n"
        "   u8x8_gpio_and_delay_esp32 callbacks using ESP-IDF I2C driver.\n"
        "   See: https://github.com/olikraus/u8g2/wiki/Porting-to-new-MCU-platform */"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
