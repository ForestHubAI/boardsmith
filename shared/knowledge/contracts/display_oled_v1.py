# SPDX-License-Identifier: AGPL-3.0-or-later
"""display_oled_v1 — Logical Driver Contract.

Covers: SSD1306, SH1106, SSD1309, and similar OLED displays.
"""
from shared.knowledge.binding_schema import (
    Capability,
    FunctionSignature,
    LogicalDriverContract,
    Parameter,
)

CONTRACT = LogicalDriverContract(
    contract_id="display_oled_v1",
    contract_version="1.0.0",
    category="display",
    description="OLED display driver with basic graphics primitives",
    capabilities=[
        Capability(
            name="init",
            description="Initialize the display",
            return_type="int",
            parameters=[
                Parameter(name="bus_handle", type="void*"),
                Parameter(name="address", type="uint8_t", default="0x3C"),
                Parameter(name="width", type="uint16_t", default="128"),
                Parameter(name="height", type="uint16_t", default="64"),
            ],
            required=True,
        ),
        Capability(
            name="clear",
            description="Clear the display buffer",
            return_type="void",
            required=True,
        ),
        Capability(
            name="draw_pixel",
            description="Set a single pixel",
            return_type="void",
            parameters=[
                Parameter(name="x", type="uint16_t"),
                Parameter(name="y", type="uint16_t"),
                Parameter(name="color", type="uint8_t", default="1"),
            ],
            required=True,
        ),
        Capability(
            name="draw_text",
            description="Draw a text string at position",
            return_type="void",
            parameters=[
                Parameter(name="x", type="uint16_t"),
                Parameter(name="y", type="uint16_t"),
                Parameter(name="text", type="const char*"),
            ],
            required=True,
        ),
        Capability(
            name="refresh",
            description="Send buffer to display (flush)",
            return_type="void",
            required=True,
        ),
        Capability(
            name="set_contrast",
            description="Set display contrast (0-255)",
            return_type="void",
            parameters=[
                Parameter(name="contrast", type="uint8_t"),
            ],
            required=False,
        ),
        Capability(
            name="set_display_on",
            description="Turn display on or off",
            return_type="void",
            parameters=[
                Parameter(name="on", type="bool"),
            ],
            required=False,
        ),
    ],
    init_signature=FunctionSignature(
        name="display_init",
        parameters=[
            Parameter(name="bus_handle", type="void*"),
            Parameter(name="address", type="uint8_t", default="0x3C"),
        ],
        return_type="int",
    ),
)

from shared.knowledge.contracts import register_contract
register_contract(CONTRACT)
