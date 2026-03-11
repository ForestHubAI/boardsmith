# SPDX-License-Identifier: AGPL-3.0-or-later
"""SSD1306 u8g2 → Zephyr RTOS adapter using Zephyr display driver."""
from shared.knowledge.binding_schema import CodeTemplate, LibraryAdapter

ADAPTER = LibraryAdapter(
    adapter_id="ssd1306_u8g2_zephyr_v1",
    contract_id="display_oled_v1",
    driver_option_key="u8g2",
    target_sdk="zephyr",
    capability_mappings={
        "init": CodeTemplate(
            template=(
                "const struct device *display = DEVICE_DT_GET_ANY(solomon_ssd1306fb);\n"
                "if (!device_is_ready(display)) { return -ENODEV; }\n"
                "display_blanking_off(display);  /* Wake display */"
            ),
            includes=["zephyr/device.h", "zephyr/drivers/display.h"],
            error_handling="return_code",
        ),
        "clear": CodeTemplate(
            template=(
                "struct display_buffer_descriptor buf_desc = {\n"
                "    .buf_size = 128 * 8,\n"
                "    .width = 128, .height = 64, .pitch = 128,\n"
                "};\n"
                "uint8_t buf[128 * 8] = {0};\n"
                "display_write(display, 0, 0, &buf_desc, buf);"
            ),
            includes=["zephyr/drivers/display.h"],
        ),
        "draw_text": CodeTemplate(
            template=(
                "/* Use LVGL or CFB (Character Framebuffer) for text rendering */\n"
                "cfb_framebuffer_clear(display, false);\n"
                "cfb_print(display, text, x, y);\n"
                "cfb_framebuffer_finalize(display);"
            ),
            includes=["zephyr/display/cfb.h"],
        ),
        "set_contrast": CodeTemplate(
            template=(
                "struct display_capabilities cap;\n"
                "display_get_capabilities(display, &cap);\n"
                "/* Contrast via SSD1306 command requires raw I2C; use display_set_contrast if available */\n"
                "(void)contrast;"
            ),
            includes=["zephyr/drivers/display.h"],
        ),
        "power_off": CodeTemplate(
            template="display_blanking_on(display);",
            includes=["zephyr/drivers/display.h"],
        ),
    },
    required_includes=[
        "zephyr/device.h",
        "zephyr/drivers/display.h",
        "zephyr/display/cfb.h",
        "zephyr/kernel.h",
    ],
    required_defines=["CONFIG_SSD1306=y", "CONFIG_DISPLAY=y", "CONFIG_CFB=y"],
    required_compile_flags=[],
    init_template=(
        "/* Zephyr devicetree overlay:\n"
        " * &i2c0 {\n"
        " *   ssd1306: ssd1306@3c {\n"
        " *     compatible = \"solomon,ssd1306fb\";\n"
        " *     reg = <0x3c>;\n"
        " *     width = <128>; height = <64>;\n"
        " *     segment-offset = <0>;\n"
        " *     page-offset = <0>;\n"
        " *     display-offset = <0>;\n"
        " *     multiplex-ratio = <63>;\n"
        " *     prechargep = <0x22>;\n"
        " *   };\n"
        " * };\n"
        " * prj.conf: CONFIG_SSD1306=y CONFIG_DISPLAY=y CONFIG_CFB=y\n"
        " */"
    ),
)

from shared.knowledge.adapters import register
register(ADAPTER)
