# SPDX-License-Identifier: AGPL-3.0-or-later
"""ESP32-S3-WROOM-1-N16R8 — MCU Device Profile.

Data sources:
- ESP32-S3 Datasheet v1.3 (Espressif, 2024)
- ESP32-S3-WROOM-1 Module Datasheet v1.4
- ESP-IDF v5.2 GPIO signal map (soc/esp32s3/include/soc/gpio_sig_map.h)
"""
from __future__ import annotations

from shared.knowledge.mcu_profile_schema import (
    AltFunction,
    AttributeProvenance,
    BootConfig,
    BootModePin,
    BusConfig,
    CapSpec,
    ClockConfig,
    ClockSource,
    ClockSourceType,
    ConnectorSpec,
    DatasheetRef,
    DebugInterface,
    DecouplingRule,
    FirmwareBinding,
    I2CPattern,
    IOElectricalRules,
    KeepoutZone,
    LayoutConstraints,
    MCUDeviceProfile,
    MCUIdentity,
    MCUPinout,
    MCUPowerTree,
    MandatoryComponent,
    NetTemplate,
    PeripheralPatterns,
    PinDefinition,
    PinElectrical,
    PinMap,
    PinType,
    PlacementRule,
    PowerDomain,
    PowerInputPattern,
    ProtectionSpec,
    RFPattern,
    RegulatorOption,
    ReservedPin,
    ResetCircuit,
    RoutingRule,
    SPIPattern,
    TemperatureGrade,
    UARTPattern,
    USBPattern,
)

# ---------------------------------------------------------------------------
# Build the profile
# ---------------------------------------------------------------------------

PROFILE = MCUDeviceProfile(
    # Domain 1 — Identity
    identity=MCUIdentity(
        vendor="Espressif",
        family="ESP32-S3",
        series="ESP32-S3-WROOM-1",
        mpn="ESP32-S3-WROOM-1-N16R8",
        package="SMD module",
        pin_count=44,
        temperature_grade=TemperatureGrade.industrial,
        lifecycle_status="active",
        datasheet_refs=[
            DatasheetRef(
                url="https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf",
                version="v1.3",
                date="2024-03-01",
            ),
            DatasheetRef(
                url="https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf",
                version="v1.4",
                date="2024-05-01",
            ),
        ],
    ),

    # Domain 2 — Pinout (key GPIO pins — module exposes 36 GPIOs)
    pinout=MCUPinout(
        pins=[
            # Power pins
            PinDefinition(pin_name="3V3", pin_number="2", pin_type=PinType.power),
            PinDefinition(pin_name="GND", pin_number="1", pin_type=PinType.ground),
            # EN / Reset
            PinDefinition(pin_name="EN", pin_number="3", pin_type=PinType.reset),
            # Boot strap pin
            PinDefinition(
                pin_name="GPIO0", pin_number="27", pin_type=PinType.gpio,
                boot_strap=True, default_state="pull_up",
                electrical=PinElectrical(
                    max_source_ma=40, max_sink_ma=28,
                    has_internal_pullup=True, has_internal_pulldown=True,
                ),
                alt_functions=[
                    AltFunction(function="ADC1_CH0"),
                    AltFunction(function="RTC_GPIO0"),
                ],
            ),
            PinDefinition(
                pin_name="GPIO1", pin_number="39", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="ADC1_CH1"),
                    AltFunction(function="TOUCH1"),
                ],
            ),
            PinDefinition(
                pin_name="GPIO2", pin_number="38", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="ADC1_CH2"),
                    AltFunction(function="TOUCH2"),
                ],
            ),
            # I2C default pins
            PinDefinition(
                pin_name="GPIO8", pin_number="12", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="I2C0_SDA", available_modes=["standard", "fast", "fast_plus"]),
                    AltFunction(function="SUBSPICS1"),
                ],
            ),
            PinDefinition(
                pin_name="GPIO9", pin_number="11", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="I2C0_SCL", available_modes=["standard", "fast", "fast_plus"]),
                    AltFunction(function="FSPIHD"),
                ],
            ),
            # SPI default pins (FSPI)
            PinDefinition(
                pin_name="GPIO10", pin_number="10", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="FSPI_CS0"),
                    AltFunction(function="SPI2_CS0"),
                ],
            ),
            PinDefinition(
                pin_name="GPIO11", pin_number="9", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="FSPI_MOSI"),
                    AltFunction(function="SPI2_MOSI"),
                ],
            ),
            PinDefinition(
                pin_name="GPIO12", pin_number="8", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="FSPI_CLK"),
                    AltFunction(function="SPI2_CLK"),
                ],
            ),
            PinDefinition(
                pin_name="GPIO13", pin_number="7", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="FSPI_MISO"),
                    AltFunction(function="SPI2_MISO"),
                ],
            ),
            # UART0 default (console)
            PinDefinition(
                pin_name="GPIO43", pin_number="37", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[AltFunction(function="U0TXD")],
            ),
            PinDefinition(
                pin_name="GPIO44", pin_number="36", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[AltFunction(function="U0RXD")],
            ),
            # USB D+/D-
            PinDefinition(
                pin_name="GPIO19", pin_number="20", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28),
                alt_functions=[AltFunction(function="USB_D-")],
            ),
            PinDefinition(
                pin_name="GPIO20", pin_number="19", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28),
                alt_functions=[AltFunction(function="USB_D+")],
            ),
            # General purpose GPIOs
            PinDefinition(
                pin_name="GPIO3", pin_number="37", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[AltFunction(function="ADC1_CH3"), AltFunction(function="TOUCH3")],
            ),
            PinDefinition(
                pin_name="GPIO4", pin_number="36", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[AltFunction(function="ADC1_CH4"), AltFunction(function="TOUCH4")],
            ),
            PinDefinition(
                pin_name="GPIO5", pin_number="35", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[AltFunction(function="ADC1_CH5"), AltFunction(function="TOUCH5")],
            ),
            PinDefinition(
                pin_name="GPIO6", pin_number="34", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[AltFunction(function="ADC1_CH6"), AltFunction(function="TOUCH6")],
            ),
            PinDefinition(
                pin_name="GPIO7", pin_number="33", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[AltFunction(function="ADC1_CH7"), AltFunction(function="TOUCH7")],
            ),
            PinDefinition(
                pin_name="GPIO14", pin_number="6", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[AltFunction(function="ADC2_CH3"), AltFunction(function="TOUCH14")],
            ),
            PinDefinition(
                pin_name="GPIO15", pin_number="5", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[AltFunction(function="ADC2_CH4"), AltFunction(function="XTAL_32K_P")],
            ),
            PinDefinition(
                pin_name="GPIO16", pin_number="4", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[AltFunction(function="ADC2_CH5"), AltFunction(function="XTAL_32K_N")],
            ),
            PinDefinition(
                pin_name="GPIO17", pin_number="21", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[AltFunction(function="ADC2_CH6")],
            ),
            PinDefinition(
                pin_name="GPIO18", pin_number="22", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[AltFunction(function="ADC2_CH7")],
            ),
            PinDefinition(
                pin_name="GPIO21", pin_number="23", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[AltFunction(function="I2C1_SDA", available_modes=["standard", "fast"])],
            ),
            PinDefinition(
                pin_name="GPIO38", pin_number="28", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[AltFunction(function="FSPIWP"), AltFunction(function="RGB_LED")],
            ),
            PinDefinition(
                pin_name="GPIO39", pin_number="29", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[AltFunction(function="MTCK"), AltFunction(function="JTAG_TCK")],
            ),
            PinDefinition(
                pin_name="GPIO40", pin_number="30", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[AltFunction(function="MTDO"), AltFunction(function="JTAG_TDO")],
            ),
            PinDefinition(
                pin_name="GPIO41", pin_number="31", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[AltFunction(function="MTDI"), AltFunction(function="JTAG_TDI")],
            ),
            PinDefinition(
                pin_name="GPIO42", pin_number="32", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=40, max_sink_ma=28, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[AltFunction(function="MTMS"), AltFunction(function="JTAG_TMS")],
            ),
        ],
        reserved_pins=[
            ReservedPin(pin_name="GPIO26", reason="PSRAM (Octal SPI CS)", can_use_as_gpio=False),
            ReservedPin(pin_name="GPIO27", reason="PSRAM (Octal SPI CLK)", can_use_as_gpio=False),
            ReservedPin(pin_name="GPIO28", reason="PSRAM (Octal SPI D4)", can_use_as_gpio=False),
            ReservedPin(pin_name="GPIO29", reason="PSRAM (Octal SPI D5)", can_use_as_gpio=False),
            ReservedPin(pin_name="GPIO30", reason="PSRAM (Octal SPI D6)", can_use_as_gpio=False),
            ReservedPin(pin_name="GPIO31", reason="PSRAM (Octal SPI D7)", can_use_as_gpio=False),
            ReservedPin(pin_name="GPIO32", reason="PSRAM (Octal SPI DQS)", can_use_as_gpio=False),
            ReservedPin(pin_name="GPIO33", reason="Flash (SPI CS)", can_use_as_gpio=False),
            ReservedPin(pin_name="GPIO34", reason="Flash (SPI CLK)", can_use_as_gpio=False),
            ReservedPin(pin_name="GPIO35", reason="Flash (SPI D0)", can_use_as_gpio=False),
            ReservedPin(pin_name="GPIO36", reason="Flash (SPI D1)", can_use_as_gpio=False),
            ReservedPin(pin_name="GPIO37", reason="Flash (SPI D2)", can_use_as_gpio=False),
        ],
        recommended_pinmaps=[
            PinMap(name="i2c_default", mappings={"SDA": "GPIO8", "SCL": "GPIO9"}),
            PinMap(name="i2c_alt", mappings={"SDA": "GPIO21", "SCL": "GPIO17"}),
            PinMap(name="spi_default", mappings={"CS": "GPIO10", "MOSI": "GPIO11", "CLK": "GPIO12", "MISO": "GPIO13"}),
            PinMap(name="uart_console", mappings={"TX": "GPIO43", "RX": "GPIO44"}),
            PinMap(name="usb_otg", mappings={"D-": "GPIO19", "D+": "GPIO20"}),
        ],
    ),

    # Domain 3 — Power
    power=MCUPowerTree(
        power_domains=[
            PowerDomain(
                name="VDD3P3",
                nominal_voltage=3.3,
                allowed_range=(3.0, 3.6),
                max_current_draw_ma=500.0,
                sequencing_order=1,
                decoupling=[
                    DecouplingRule(
                        domain="VDD3P3",
                        capacitors=[
                            CapSpec(value="100nF", type="X7R", package="0402", quantity=6),
                            CapSpec(value="10µF", type="X5R", package="0805", quantity=1),
                        ],
                        placement_rule="100nF within 3mm of each VDD pin; 10µF at rail entry",
                        pin_group=["VDD3P3_1", "VDD3P3_2", "VDD3P3_3", "VDD3P3_4", "VDD3P3_5", "VDD3P3_6"],
                        notes="One 100nF per VDD pin + 10µF bulk per 3V3 rail",
                    ),
                ],
                connected_pin_groups=["VDD3P3_1", "VDD3P3_2", "VDD3P3_3", "VDD3P3_4", "VDD3P3_5", "VDD3P3_6"],
            ),
            PowerDomain(
                name="VDD3P3_RTC",
                nominal_voltage=3.3,
                allowed_range=(3.0, 3.6),
                max_current_draw_ma=50.0,
                sequencing_order=1,
                decoupling=[
                    DecouplingRule(
                        domain="VDD3P3_RTC",
                        capacitors=[CapSpec(value="100nF", type="X7R", package="0402")],
                        placement_rule="within 3mm of VDD3P3_RTC pin",
                    ),
                ],
            ),
            PowerDomain(
                name="VDDA",
                nominal_voltage=3.3,
                allowed_range=(3.0, 3.6),
                max_current_draw_ma=50.0,
                sequencing_order=1,
                decoupling=[
                    DecouplingRule(
                        domain="VDDA",
                        capacitors=[
                            CapSpec(value="1µF", type="X7R", package="0402"),
                        ],
                        placement_rule="within 3mm of VDDA pin, after ferrite bead",
                        notes="VDDA must have ferrite bead (10Ω @ 100MHz) + 1µF for analog domain isolation",
                    ),
                ],
            ),
        ],
        power_input_patterns=[
            PowerInputPattern(
                name="usb_5v",
                input_voltage_range=(4.5, 5.5),
                recommended_regulators=[
                    RegulatorOption(
                        topology="ldo",
                        recommended_mpns=["AP2112K-3.3", "AMS1117-3.3"],
                        output_voltage=3.3,
                        max_current_ma=600,
                        dropout_voltage=0.25,
                    ),
                ],
                mandatory_protection=[
                    ProtectionSpec(
                        component_type="tvs",
                        recommended_mpns=["USBLC6-2SC6"],
                        notes="ESD protection on USB D+/D- lines",
                    ),
                ],
            ),
            PowerInputPattern(
                name="lipo_3v7",
                input_voltage_range=(3.0, 4.2),
                recommended_regulators=[
                    RegulatorOption(
                        topology="ldo",
                        recommended_mpns=["AP2112K-3.3", "RT9193-33"],
                        output_voltage=3.3,
                        max_current_ma=600,
                        dropout_voltage=0.25,
                    ),
                ],
            ),
        ],
    ),

    # Domain 4 — Clocking
    clock=ClockConfig(
        main_clock=ClockSource(
            type=ClockSourceType.external_xtal,
            frequency_hz=40_000_000,
            accuracy_ppm=10,
            load_capacitance_pf=10.0,
            recommended_crystals=["ABS07-120-40.000MHZ-T"],
            required_caps=[
                CapSpec(value="10pF", type="C0G", package="0402", quantity=2),
            ],
            layout_constraints=[
                "Keep crystal within 5mm of XTAL pins",
                "No vias under crystal",
                "Guard ring around crystal",
            ],
            osc_pins=["XTAL_P", "XTAL_N"],
        ),
        rtc_clock=ClockSource(
            type=ClockSourceType.external_xtal,
            frequency_hz=32_768,
            accuracy_ppm=20,
            load_capacitance_pf=7.0,
            osc_pins=["XTAL_32K_P", "XTAL_32K_N"],
            required_caps=[
                CapSpec(value="6.8pF", type="C0G", package="0402", quantity=2),
            ],
            layout_constraints=["Keep within 3mm of GPIO15/GPIO16"],
        ),
        safe_default_mhz=40,
    ),

    # Domain 5 — Boot/Reset
    boot=BootConfig(
        reset_circuit=ResetCircuit(
            nrst_pin="EN",
            recommended_pullup_ohm=10000,
            cap_to_gnd_nf=100,
        ),
        boot_mode_pins=[
            BootModePin(
                pin="GPIO0",
                normal_boot_state="high",
                pull_resistor="pull_up_10k",
                dont_use_as_gpio_until_boot=True,
                notes="Hold LOW during reset for UART bootloader. Internal pull-up, but external 10k recommended for reliable boot.",
            ),
            BootModePin(
                pin="GPIO46",
                normal_boot_state="low",
                pull_resistor="pull_down_10k",
                dont_use_as_gpio_until_boot=True,
                notes="Must be LOW for SPI boot (default). HIGH selects download boot. Has internal pull-down.",
            ),
        ],
        programming_mode_entry=[
            "Hold GPIO0 LOW",
            "Assert EN LOW for 100ms",
            "Release EN",
            "Wait 50ms",
            "Release GPIO0",
            "Upload firmware via UART0 (GPIO43/GPIO44) or USB (GPIO19/GPIO20)",
        ],
    ),

    # Domain 6 — Debug
    debug_interfaces=[
        DebugInterface(
            protocol="JTAG",
            pins={
                "TCK": "GPIO39",
                "TDO": "GPIO40",
                "TDI": "GPIO41",
                "TMS": "GPIO42",
            },
            recommended_connector=ConnectorSpec(
                name="ARM JTAG 2x5 1.27mm",
                footprint="PinHeader_2x05_P1.27mm_Vertical",
                alt_footprint="TagConnect_TC2050",
                pinout={"TCK": 4, "TDO": 6, "TDI": 8, "TMS": 2, "GND": 3, "VTref": 1},
            ),
        ),
        DebugInterface(
            protocol="USB_DFU",
            pins={"D-": "GPIO19", "D+": "GPIO20"},
        ),
        DebugInterface(
            protocol="UART_bootloader",
            pins={"TX": "GPIO43", "RX": "GPIO44"},
        ),
    ],

    # Domain 7 — Mandatory Components
    mandatory_components=[
        MandatoryComponent(
            component_type="cap",
            value="100nF",
            spec="X7R 0402 ±10%",
            quantity_rule="per_vdd_pin",
            connectivity=NetTemplate(net_name="VDD_BYPASS", connected_pins=["VDD_x", "GND"]),
            placement="within 3mm of each VDD pin",
            rationale="ESP32-S3 Datasheet Section 4.2: 100nF ceramic per VDD pin",
        ),
        MandatoryComponent(
            component_type="cap",
            value="10µF",
            spec="X5R 0805 ≥10V",
            quantity_rule="per_rail",
            placement="at 3V3 rail entry point",
            rationale="Bulk decoupling for 3.3V main rail",
        ),
        MandatoryComponent(
            component_type="resistor",
            value="10kΩ",
            spec="0402 ±1%",
            quantity_rule="one_per_board",
            connectivity=NetTemplate(net_name="EN_PULLUP", connected_pins=["EN", "VDD3P3"]),
            placement="near EN pin",
            rationale="EN pin pull-up for reliable reset. Datasheet Section 2.4.",
        ),
        MandatoryComponent(
            component_type="cap",
            value="100nF",
            spec="X7R 0402",
            quantity_rule="one_per_board",
            connectivity=NetTemplate(net_name="EN_FILTER", connected_pins=["EN", "GND"]),
            placement="near EN pin",
            rationale="RC filter on EN pin for noise immunity",
        ),
        MandatoryComponent(
            component_type="crystal",
            value="40MHz",
            spec="±10ppm, 10pF load",
            quantity_rule="one_per_board",
            connectivity=NetTemplate(net_name="XTAL_MAIN", connected_pins=["XTAL_P", "XTAL_N"]),
            placement="within 5mm of XTAL pins",
            rationale="Main oscillator. Module variant has crystal on-module (verify MPN).",
        ),
        MandatoryComponent(
            component_type="cap",
            value="10pF",
            spec="C0G 0402 ±5%",
            quantity_rule="per_bus",
            placement="within 2mm of XTAL pins",
            rationale="Crystal load capacitors (2× required)",
        ),
        MandatoryComponent(
            component_type="ferrite",
            value="10Ω@100MHz",
            spec="0402 ferrite bead",
            quantity_rule="one_per_board",
            connectivity=NetTemplate(net_name="VDDA_FILTER", connected_pins=["VDD3P3_RAIL", "VDDA"]),
            placement="between 3V3 rail and VDDA pin",
            rationale="Analog domain isolation per ESP32-S3 HW Design Guide",
        ),
        MandatoryComponent(
            component_type="cap",
            value="1µF",
            spec="X7R 0402",
            quantity_rule="one_per_board",
            connectivity=NetTemplate(net_name="VDDA_DECOUPLE", connected_pins=["VDDA", "GND"]),
            placement="within 3mm of VDDA pin, after ferrite",
            rationale="VDDA decoupling after ferrite bead",
        ),
    ],

    # Domain 8 — IO Rules
    io_rules=IOElectricalRules(
        io_voltage_tolerance_per_domain={"VDD3P3": (0.0, 3.6)},
        max_source_current_per_pin_ma=40.0,
        max_sink_current_per_pin_ma=28.0,
        max_total_current_per_port_ma=1200.0,
        adc_input_range=(0.0, 3.1),
        adc_source_impedance_max_ohm=10000,
        adc_sampling_cap_pf=3.0,
        analog_domain_rules=[
            "VDDA must have ferrite bead + separate 1µF decoupling",
            "ADC input range 0–3.1V (11dB attenuation)",
            "ADC2 not usable when Wi-Fi active",
        ],
        esd_rating_hbm_v=2000,
    ),

    # Domain 9 — Peripheral Patterns
    peripheral_patterns=PeripheralPatterns(
        i2c=I2CPattern(
            pullup_value_rule="4.7kΩ for ≤100kHz, 2.2kΩ for 400kHz, 1kΩ for 1MHz",
            pullup_formula="R = t_rise / (0.8473 × C_bus)",
            max_bus_capacitance_pf=400,
            recommended_pins={"SDA": ["GPIO8", "GPIO21"], "SCL": ["GPIO9", "GPIO17"]},
            max_devices_per_bus=8,
        ),
        spi=SPIPattern(
            series_resistor_sck_ohm=33,
            cs_pullup=True,
            max_freq_mhz=80,
            recommended_pins={
                "CS": ["GPIO10"], "MOSI": ["GPIO11"],
                "CLK": ["GPIO12"], "MISO": ["GPIO13"],
            },
        ),
        uart=UARTPattern(
            recommended_level_shifter="TXB0104",
            rx_tx_series_resistor=470,
        ),
        usb=USBPattern(
            dp_dm_series_resistor_ohm=27,
            esd_protection_ic="USBLC6-2SC6",
            connector_footprint="USB_C_Receptacle_HRO_TYPE-C-31-M-12",
            vbus_protection="Schottky + Polyfuse 500mA",
        ),
        rf=RFPattern(
            keepout_zone_mm=15.0,
            matching_network="Module-internal (on-module antenna)",
            ground_plane_requirement="Solid ground plane under module, no copper in antenna keepout zone",
        ),
    ),

    # Domain 10 — Layout
    layout=LayoutConstraints(
        keepout_zones=[
            KeepoutZone(
                name="RF antenna",
                type="no_copper",
                area_mm=(15.0, 10.0),
                side="top",
            ),
            KeepoutZone(
                name="Crystal area",
                type="no_via",
                area_mm=(8.0, 5.0),
                side="top",
            ),
        ],
        routing_constraints=[
            RoutingRule(net_class="usb_dp_dm", trace_width_mm=0.2, impedance_ohm=90.0, differential_pair=True, length_match_mm=0.15),
            RoutingRule(net_class="power_3v3", trace_width_mm=0.4),
            RoutingRule(net_class="signal", trace_width_mm=0.15),
        ],
        placement_constraints=[
            PlacementRule(component_type="decoupling_cap", max_distance_mm=3.0, reference_pin="VDD"),
            PlacementRule(component_type="crystal", max_distance_mm=5.0, reference_pin="XTAL_P"),
        ],
        stackup_recommendation="2-layer",
    ),

    # Domain 11 — Firmware
    firmware=FirmwareBinding(
        clock_tree_defaults={
            "cpu_freq_mhz": 240,
            "apb_freq_mhz": 80,
            "xtal_freq_mhz": 40,
        },
        bus_init_defaults={
            "I2C0": BusConfig(bus_type="I2C", default_speed_hz=400000, default_mode="fast"),
            "SPI2": BusConfig(bus_type="SPI", default_speed_hz=10000000, default_mode="mode_0"),
            "UART0": BusConfig(bus_type="UART", default_speed_hz=115200),
        },
        pinmux_templates={
            "I2C0_SDA": "gpio_set_function(GPIO_NUM_8, I2C0_SDA)",
            "I2C0_SCL": "gpio_set_function(GPIO_NUM_9, I2C0_SCL)",
            "SPI2_CS": "gpio_set_function(GPIO_NUM_10, FSPI_CS0)",
        },
        bootloader_options=["uart_boot", "usb_dfu", "jtag_flash"],
        sdk_framework="esp-idf",
    ),

    # Domain 12 — Provenance
    provenance=[
        AttributeProvenance(
            source_ref="ESP32-S3 Datasheet v1.3",
            source_type="datasheet",
            verification_status="reviewed",
            confidence_score=0.90,
            last_validated_date="2026-02-01",
            validated_against="ESP-IDF v5.2",
        ),
        AttributeProvenance(
            source_ref="ESP32-S3 Hardware Design Guidelines v1.2",
            source_type="app_note",
            verification_status="reviewed",
            confidence_score=0.92,
        ),
    ],
)

# Register with the profile registry
from shared.knowledge.mcu_profiles import register
register(PROFILE)
