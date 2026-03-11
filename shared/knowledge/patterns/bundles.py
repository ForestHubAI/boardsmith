# SPDX-License-Identifier: AGPL-3.0-or-later
"""DB-3: Pattern Bundles — pre-defined pattern combinations for common use-cases."""
from __future__ import annotations

from shared.knowledge.patterns.pattern_schema import PatternBundle

BUNDLES: list[PatternBundle] = [

    PatternBundle(
        bundle_id="usb_devboard",
        name="USB Development Board",
        description=(
            "Standard pattern set for a USB-powered MCU development board. "
            "Covers USB ESD protection, LDO bypass, MCU decoupling, "
            "crystal load caps, and reset circuit."
        ),
        pattern_ids=[
            "usb_esd_protection_v1",   # 1. Protect USB D+/D−
            "ldo_bypass_v1",            # 2. Input/output caps for 3.3V LDO
            "decoupling_per_pin_v1",    # 3. 100nF per MCU VDD + 10µF bulk
            "crystal_load_v1",          # 4. Load caps for MCU crystal
            "reset_circuit_v1",         # 5. NRST pull-up + filter cap
        ],
        trigger="has_usb == True and board_type == 'devboard'",
        notes=[
            "Apply in order: protection first, then power, then timing.",
            "Add i2c_pullup_v1 if I2C peripherals are present.",
        ],
    ),

    PatternBundle(
        bundle_id="industrial_24v_input",
        name="Industrial 24V Input Conditioning",
        description=(
            "Pattern set for industrial equipment powered from 24V DC rails. "
            "Covers input protection (TVS + polyfuse), reverse polarity (P-FET), "
            "buck converter to 5V, MCU decoupling, and reset."
        ),
        pattern_ids=[
            "tvs_input_protection_v1",  # 1. TVS clamp + polyfuse on 24V input
            "reverse_polarity_v1",      # 2. P-FET reverse polarity
            "buck_converter_v1",         # 3. 24V → 5V or 3.3V buck
            "ldo_bypass_v1",            # 4. LDO bypass if further regulation needed
            "decoupling_per_pin_v1",    # 5. MCU decoupling
            "reset_circuit_v1",         # 6. Reset circuit
        ],
        trigger="v_supply > 12.0 and environment == 'industrial'",
        notes=[
            "Size TVS for 30V standoff (SMBJ30A or equivalent).",
            "Choose polyfuse trip current 10–20% above max continuous load.",
            "Use an industrial-grade (AEC-Q rated) buck converter for -40 to 85°C.",
        ],
    ),

    PatternBundle(
        bundle_id="battery_sensor_node",
        name="Battery-Powered Sensor Node",
        description=(
            "Pattern set for a low-power, battery-powered IoT sensor node. "
            "Covers LDO bypass, I2C pull-ups, MCU decoupling, "
            "crystal load caps, and reset."
        ),
        pattern_ids=[
            "ldo_bypass_v1",            # 1. Bypass caps for LDO (e.g. AMS1117 or AP2112K)
            "i2c_pullup_v1",            # 2. Pull-ups for sensor I2C bus
            "decoupling_per_pin_v1",    # 3. MCU decoupling (100nF + 10µF per domain)
            "crystal_load_v1",          # 4. Crystal load caps
            "reset_circuit_v1",         # 5. Reset circuit
        ],
        trigger="power_source == 'battery' and category == 'sensor'",
        notes=[
            "Use low-dropout LDO (e.g. AP2112K-3.3) for best battery life.",
            "Increase I2C pullup to 10kΩ to reduce static current.",
            "Consider 32.768 kHz crystal for low-power RTC; use crystal_load_v1 for both crystals.",
        ],
    ),
]
