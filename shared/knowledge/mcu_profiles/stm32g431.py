# SPDX-License-Identifier: AGPL-3.0-or-later
"""STM32G431CBU6 — MCU Device Profile.

Data sources:
- STM32G431xx Datasheet DS12589 Rev 5 (ST, 2023)
- STM32G4 Reference Manual RM0440 Rev 8
- STM32CubeMX v6.11 GPIO/Pin database
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
    LayoutConstraints,
    MCUDeviceProfile,
    MCUIdentity,
    MCUPinout,
    MCUPowerTree,
    MandatoryComponent,
    NetTemplate,
    PLLConfig,
    PeripheralPatterns,
    PinDefinition,
    PinElectrical,
    PinMap,
    PinType,
    PlacementRule,
    PowerDomain,
    PowerInputPattern,
    ProtectionSpec,
    RegulatorOption,
    ReservedPin,
    ResetCircuit,
    RoutingRule,
    SPIPattern,
    TemperatureGrade,
    UARTPattern,
    USBPattern,
    CANPattern,
)

PROFILE = MCUDeviceProfile(
    # Domain 1 — Identity
    identity=MCUIdentity(
        vendor="STMicroelectronics",
        family="STM32G4",
        series="STM32G431",
        mpn="STM32G431CBU6",
        package="UFQFPN48",
        pin_count=48,
        temperature_grade=TemperatureGrade.industrial,
        lifecycle_status="active",
        datasheet_refs=[
            DatasheetRef(
                url="https://www.st.com/resource/en/datasheet/stm32g431cb.pdf",
                version="DS12589 Rev 5",
                date="2023-06-01",
            ),
        ],
    ),

    # Domain 2 — Pinout (key pins for UFQFPN48 package)
    pinout=MCUPinout(
        pins=[
            # Power pins
            PinDefinition(pin_name="VDD", pin_number="1", pin_type=PinType.power),
            PinDefinition(pin_name="VDD", pin_number="24", pin_type=PinType.power),
            PinDefinition(pin_name="VDD", pin_number="36", pin_type=PinType.power),
            PinDefinition(pin_name="VDD", pin_number="48", pin_type=PinType.power),
            PinDefinition(pin_name="VDDA", pin_number="9", pin_type=PinType.power),
            PinDefinition(pin_name="VBAT", pin_number="1", pin_type=PinType.power),
            PinDefinition(pin_name="VSS", pin_number="23", pin_type=PinType.ground),
            PinDefinition(pin_name="VSSA", pin_number="8", pin_type=PinType.ground),
            # Reset
            PinDefinition(pin_name="NRST", pin_number="7", pin_type=PinType.reset),
            # Boot
            PinDefinition(
                pin_name="BOOT0", pin_number="44", pin_type=PinType.boot,
                boot_strap=True, default_state="pull_down",
            ),
            # OSC pins
            PinDefinition(pin_name="PF0-OSC_IN", pin_number="5", pin_type=PinType.osc,
                alt_functions=[AltFunction(function="RCC_OSC_IN")]),
            PinDefinition(pin_name="PF1-OSC_OUT", pin_number="6", pin_type=PinType.osc,
                alt_functions=[AltFunction(function="RCC_OSC_OUT")]),
            # Port A — GPIO + Alt Functions
            PinDefinition(
                pin_name="PA0", pin_number="10", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="TIM2_CH1", af_number=1),
                    AltFunction(function="USART2_CTS", af_number=7),
                    AltFunction(function="COMP1_OUT", af_number=8),
                    AltFunction(function="ADC1_IN1"),
                ],
            ),
            PinDefinition(
                pin_name="PA1", pin_number="11", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="TIM2_CH2", af_number=1),
                    AltFunction(function="USART2_RTS", af_number=7),
                    AltFunction(function="ADC1_IN2"),
                ],
            ),
            PinDefinition(
                pin_name="PA2", pin_number="12", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="TIM2_CH3", af_number=1),
                    AltFunction(function="USART2_TX", af_number=7),
                    AltFunction(function="LPUART1_TX", af_number=12),
                    AltFunction(function="ADC1_IN3"),
                ],
            ),
            PinDefinition(
                pin_name="PA3", pin_number="13", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="TIM2_CH4", af_number=1),
                    AltFunction(function="USART2_RX", af_number=7),
                    AltFunction(function="LPUART1_RX", af_number=12),
                    AltFunction(function="ADC1_IN4"),
                ],
            ),
            PinDefinition(
                pin_name="PA4", pin_number="14", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="SPI1_NSS", af_number=5),
                    AltFunction(function="SPI3_NSS", af_number=6),
                    AltFunction(function="DAC1_OUT1"),
                    AltFunction(function="ADC2_IN17"),
                ],
            ),
            PinDefinition(
                pin_name="PA5", pin_number="15", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="SPI1_SCK", af_number=5),
                    AltFunction(function="TIM2_CH1", af_number=1),
                    AltFunction(function="DAC1_OUT2"),
                    AltFunction(function="ADC2_IN13"),
                ],
            ),
            PinDefinition(
                pin_name="PA6", pin_number="16", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="SPI1_MISO", af_number=5),
                    AltFunction(function="TIM3_CH1", af_number=2),
                    AltFunction(function="ADC2_IN3"),
                ],
            ),
            PinDefinition(
                pin_name="PA7", pin_number="17", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="SPI1_MOSI", af_number=5),
                    AltFunction(function="TIM3_CH2", af_number=2),
                    AltFunction(function="ADC2_IN4"),
                ],
            ),
            # PA8-PA15
            PinDefinition(
                pin_name="PA8", pin_number="29", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="TIM1_CH1", af_number=6),
                    AltFunction(function="USART1_CK", af_number=7),
                    AltFunction(function="MCO"),
                ],
            ),
            PinDefinition(
                pin_name="PA9", pin_number="30", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="TIM1_CH2", af_number=6),
                    AltFunction(function="USART1_TX", af_number=7),
                    AltFunction(function="I2C2_SCL", af_number=4, available_modes=["standard", "fast", "fast_plus"]),
                ],
            ),
            PinDefinition(
                pin_name="PA10", pin_number="31", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="TIM1_CH3", af_number=6),
                    AltFunction(function="USART1_RX", af_number=7),
                    AltFunction(function="I2C2_SDA", af_number=4, available_modes=["standard", "fast", "fast_plus"]),
                ],
            ),
            PinDefinition(
                pin_name="PA11", pin_number="32", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="USB_DM"),
                    AltFunction(function="TIM1_CH4", af_number=11),
                    AltFunction(function="FDCAN1_RX", af_number=9),
                ],
            ),
            PinDefinition(
                pin_name="PA12", pin_number="33", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="USB_DP"),
                    AltFunction(function="TIM1_ETR", af_number=11),
                    AltFunction(function="FDCAN1_TX", af_number=9),
                ],
            ),
            # SWD debug pins
            PinDefinition(
                pin_name="PA13", pin_number="34", pin_type=PinType.debug,
                alt_functions=[AltFunction(function="SWDIO", af_number=0)],
            ),
            PinDefinition(
                pin_name="PA14", pin_number="37", pin_type=PinType.debug,
                alt_functions=[AltFunction(function="SWCLK", af_number=0)],
            ),
            PinDefinition(
                pin_name="PA15", pin_number="38", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="SPI1_NSS", af_number=5),
                    AltFunction(function="SPI3_NSS", af_number=6),
                    AltFunction(function="TIM2_CH1", af_number=1),
                    AltFunction(function="JTDI", af_number=0),
                ],
            ),
            # Port B key pins
            PinDefinition(
                pin_name="PB3", pin_number="39", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="SPI1_SCK", af_number=5),
                    AltFunction(function="SPI3_SCK", af_number=6),
                    AltFunction(function="USART2_TX", af_number=7),
                    AltFunction(function="JTDO-TRACESWO", af_number=0),
                ],
            ),
            PinDefinition(
                pin_name="PB4", pin_number="40", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="SPI1_MISO", af_number=5),
                    AltFunction(function="SPI3_MISO", af_number=6),
                    AltFunction(function="USART2_RX", af_number=7),
                    AltFunction(function="JTRST", af_number=0),
                ],
            ),
            PinDefinition(
                pin_name="PB5", pin_number="41", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="SPI1_MOSI", af_number=5),
                    AltFunction(function="SPI3_MOSI", af_number=6),
                    AltFunction(function="I2C1_SMBA", af_number=4),
                ],
            ),
            PinDefinition(
                pin_name="PB6", pin_number="42", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="I2C1_SCL", af_number=4, available_modes=["standard", "fast", "fast_plus"]),
                    AltFunction(function="USART1_TX", af_number=7),
                    AltFunction(function="TIM4_CH1", af_number=2),
                ],
            ),
            PinDefinition(
                pin_name="PB7", pin_number="43", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="I2C1_SDA", af_number=4, available_modes=["standard", "fast", "fast_plus"]),
                    AltFunction(function="USART1_RX", af_number=7),
                    AltFunction(function="TIM4_CH2", af_number=2),
                ],
            ),
            PinDefinition(
                pin_name="PB8", pin_number="45", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="I2C1_SCL", af_number=4),
                    AltFunction(function="FDCAN1_RX", af_number=9),
                    AltFunction(function="TIM4_CH3", af_number=2),
                ],
            ),
            PinDefinition(
                pin_name="PB9", pin_number="46", pin_type=PinType.gpio,
                electrical=PinElectrical(max_source_ma=20, max_sink_ma=20, is_5v_tolerant=True, has_internal_pullup=True, has_internal_pulldown=True),
                alt_functions=[
                    AltFunction(function="I2C1_SDA", af_number=4),
                    AltFunction(function="FDCAN1_TX", af_number=9),
                    AltFunction(function="TIM4_CH4", af_number=2),
                ],
            ),
        ],
        reserved_pins=[
            ReservedPin(pin_name="PA13", reason="SWD (SWDIO) — debug", can_use_as_gpio=False),
            ReservedPin(pin_name="PA14", reason="SWD (SWCLK) — debug", can_use_as_gpio=False),
        ],
        recommended_pinmaps=[
            PinMap(name="i2c1_default", mappings={"SCL": "PB6", "SDA": "PB7"}),
            PinMap(name="i2c2_default", mappings={"SCL": "PA9", "SDA": "PA10"}),
            PinMap(name="spi1_default", mappings={"SCK": "PA5", "MISO": "PA6", "MOSI": "PA7", "NSS": "PA4"}),
            PinMap(name="spi1_alt", mappings={"SCK": "PB3", "MISO": "PB4", "MOSI": "PB5", "NSS": "PA15"}),
            PinMap(name="usart1_default", mappings={"TX": "PA9", "RX": "PA10"}),
            PinMap(name="usart2_default", mappings={"TX": "PA2", "RX": "PA3"}),
            PinMap(name="fdcan1_default", mappings={"TX": "PA12", "RX": "PA11"}),
            PinMap(name="fdcan1_alt", mappings={"TX": "PB9", "RX": "PB8"}),
            PinMap(name="usb_default", mappings={"DM": "PA11", "DP": "PA12"}),
        ],
    ),

    # Domain 3 — Power
    power=MCUPowerTree(
        power_domains=[
            PowerDomain(
                name="VDD",
                nominal_voltage=3.3,
                allowed_range=(1.71, 3.6),
                max_current_draw_ma=150.0,
                sequencing_order=1,
                decoupling=[
                    DecouplingRule(
                        domain="VDD",
                        capacitors=[
                            CapSpec(value="100nF", type="X7R", package="0402", quantity=4),
                            CapSpec(value="4.7µF", type="X5R", package="0805", quantity=1),
                        ],
                        placement_rule="100nF within 3mm of each VDD pin; 4.7µF at rail entry",
                        pin_group=["VDD_1", "VDD_24", "VDD_36", "VDD_48"],
                        notes="One 100nF per VDD pin + 4.7µF bulk",
                    ),
                ],
            ),
            PowerDomain(
                name="VDDA",
                nominal_voltage=3.3,
                allowed_range=(1.62, 3.6),
                max_current_draw_ma=20.0,
                sequencing_order=1,
                decoupling=[
                    DecouplingRule(
                        domain="VDDA",
                        capacitors=[
                            CapSpec(value="1µF", type="X7R", package="0402"),
                            CapSpec(value="10nF", type="C0G", package="0402"),
                        ],
                        placement_rule="within 3mm of VDDA pin, after ferrite bead",
                        notes="Analog domain: ferrite + 1µF + 10nF per AN4488",
                    ),
                ],
            ),
            PowerDomain(
                name="VBAT",
                nominal_voltage=3.3,
                allowed_range=(1.55, 3.6),
                max_current_draw_ma=1.0,
                decoupling=[
                    DecouplingRule(
                        domain="VBAT",
                        capacitors=[CapSpec(value="100nF", type="X7R", package="0402")],
                        placement_rule="within 3mm of VBAT pin",
                        notes="VBAT decoupling; connect to VDD if no battery backup",
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
                        recommended_mpns=["AP2112K-3.3", "AMS1117-3.3", "LD1117S33TR"],
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
            frequency_hz=8_000_000,
            accuracy_ppm=20,
            load_capacitance_pf=20.0,
            recommended_crystals=["ABM8-8.000MHZ-B2-T"],
            required_caps=[
                CapSpec(value="20pF", type="C0G", package="0402", quantity=2),
            ],
            layout_constraints=[
                "Keep crystal within 5mm of PF0/PF1",
                "No routing under crystal",
                "Ground guard traces recommended",
            ],
            osc_pins=["PF0-OSC_IN", "PF1-OSC_OUT"],
        ),
        rtc_clock=ClockSource(
            type=ClockSourceType.external_xtal,
            frequency_hz=32_768,
            accuracy_ppm=20,
            load_capacitance_pf=6.8,
            osc_pins=["PC14-OSC32_IN", "PC15-OSC32_OUT"],
            required_caps=[
                CapSpec(value="6.8pF", type="C0G", package="0402", quantity=2),
            ],
        ),
        pll_config=PLLConfig(
            input_source="HSE",
            input_divider=2,
            multiplier=85,
            output_divider=2,
            max_output_hz=170_000_000,
        ),
        safe_default_mhz=16,  # HSI16 internal RC
    ),

    # Domain 5 — Boot/Reset
    boot=BootConfig(
        reset_circuit=ResetCircuit(
            nrst_pin="NRST",
            recommended_pullup_ohm=10000,
            cap_to_gnd_nf=100,
            supervisor_ic="STM6315",
        ),
        boot_mode_pins=[
            BootModePin(
                pin="BOOT0",
                normal_boot_state="low",
                pull_resistor="pull_down_10k",
                notes="LOW=boot from Flash (normal). HIGH=boot from System Memory (bootloader). Pin 44.",
            ),
        ],
        programming_mode_entry=[
            "Set BOOT0 HIGH (connect to VDD via 10k or jumper)",
            "Assert NRST LOW for 10ms",
            "Release NRST",
            "MCU boots into System Bootloader",
            "Flash via USART or USB DFU",
            "Set BOOT0 LOW and reset for normal boot",
        ],
    ),

    # Domain 6 — Debug
    debug_interfaces=[
        DebugInterface(
            protocol="SWD",
            pins={"SWDIO": "PA13", "SWCLK": "PA14", "SWO": "PB3", "NRST": "NRST"},
            recommended_connector=ConnectorSpec(
                name="ARM SWD 2x5 1.27mm",
                footprint="PinHeader_2x05_P1.27mm_Vertical",
                alt_footprint="TagConnect_TC2050-IDC",
                pinout={"VTref": 1, "SWDIO": 2, "GND": 3, "SWCLK": 4, "GND2": 5, "SWO": 6, "NC": 7, "NC2": 8, "GND3": 9, "NRST": 10},
            ),
            pin_protection=[
                ProtectionSpec(
                    component_type="resistor",
                    notes="Optional: 100Ω series resistors on SWDIO/SWCLK for ESD protection",
                ),
            ],
        ),
        DebugInterface(
            protocol="UART_bootloader",
            pins={"TX": "PA9", "RX": "PA10"},
        ),
        DebugInterface(
            protocol="USB_DFU",
            pins={"DM": "PA11", "DP": "PA12"},
        ),
    ],

    # Domain 7 — Mandatory Components
    mandatory_components=[
        MandatoryComponent(
            component_type="cap",
            value="100nF",
            spec="X7R 0402 ±10%",
            quantity_rule="per_vdd_pin",
            placement="within 3mm of each VDD pin",
            rationale="AN4488: 100nF ceramic per VDD pin",
        ),
        MandatoryComponent(
            component_type="cap",
            value="4.7µF",
            spec="X5R 0805 ≥10V",
            quantity_rule="per_rail",
            placement="at 3V3 rail entry",
            rationale="Bulk decoupling for VDD rail",
        ),
        MandatoryComponent(
            component_type="cap",
            value="1µF",
            spec="X7R 0402",
            quantity_rule="one_per_board",
            connectivity=NetTemplate(net_name="VDDA_DECOUPLE", connected_pins=["VDDA", "VSSA"]),
            placement="within 3mm of VDDA, after ferrite",
            rationale="AN4488: VDDA requires ferrite + 1µF + 10nF",
        ),
        MandatoryComponent(
            component_type="cap",
            value="10nF",
            spec="C0G 0402",
            quantity_rule="one_per_board",
            connectivity=NetTemplate(net_name="VDDA_HF_DECOUPLE", connected_pins=["VDDA", "VSSA"]),
            placement="within 2mm of VDDA, closest to pin",
            rationale="HF decoupling for ADC accuracy",
        ),
        MandatoryComponent(
            component_type="ferrite",
            value="600Ω@100MHz",
            spec="0402 ferrite bead",
            quantity_rule="one_per_board",
            connectivity=NetTemplate(net_name="VDDA_FILTER", connected_pins=["VDD_RAIL", "VDDA"]),
            placement="between VDD rail and VDDA",
            rationale="Analog domain isolation per AN4488",
        ),
        MandatoryComponent(
            component_type="cap",
            value="100nF",
            spec="X7R 0402",
            quantity_rule="one_per_board",
            connectivity=NetTemplate(net_name="VBAT_DECOUPLE", connected_pins=["VBAT", "VSS"]),
            placement="within 3mm of VBAT",
            rationale="VBAT decoupling (connect VBAT to VDD if no battery)",
        ),
        MandatoryComponent(
            component_type="resistor",
            value="10kΩ",
            spec="0402 ±1%",
            quantity_rule="one_per_board",
            connectivity=NetTemplate(net_name="BOOT0_PULLDOWN", connected_pins=["BOOT0", "VSS"]),
            placement="near BOOT0 pin",
            rationale="Ensure boot from Flash by default",
        ),
        MandatoryComponent(
            component_type="cap",
            value="100nF",
            spec="X7R 0402",
            quantity_rule="one_per_board",
            connectivity=NetTemplate(net_name="NRST_FILTER", connected_pins=["NRST", "VSS"]),
            placement="near NRST pin",
            rationale="Reset filtering capacitor per AN4488",
        ),
    ],

    # Domain 8 — IO Rules
    io_rules=IOElectricalRules(
        io_voltage_tolerance_per_domain={"VDD": (0.0, 3.6), "5V_TOLERANT": (-0.3, 5.5)},
        max_source_current_per_pin_ma=20.0,
        max_sink_current_per_pin_ma=20.0,
        max_total_current_per_port_ma=100.0,
        adc_input_range=(0.0, 3.6),
        adc_source_impedance_max_ohm=50000,
        adc_sampling_cap_pf=5.0,
        analog_domain_rules=[
            "VDDA must have ferrite bead + 1µF + 10nF decoupling",
            "VDDA ≥ 1.62V for ADC operation",
            "ADC input range 0 to VDDA",
            "Do not exceed VDDA on analog inputs",
        ],
        esd_rating_hbm_v=2000,
    ),

    # Domain 9 — Peripheral Patterns
    peripheral_patterns=PeripheralPatterns(
        i2c=I2CPattern(
            pullup_value_rule="4.7kΩ for ≤100kHz, 2.2kΩ for 400kHz, 1kΩ for 1MHz (Fast Mode Plus)",
            max_bus_capacitance_pf=400,
            recommended_pins={"SCL": ["PB6", "PA9"], "SDA": ["PB7", "PA10"]},
            max_devices_per_bus=8,
        ),
        spi=SPIPattern(
            max_freq_mhz=42,
            recommended_pins={
                "SCK": ["PA5", "PB3"], "MISO": ["PA6", "PB4"],
                "MOSI": ["PA7", "PB5"], "NSS": ["PA4", "PA15"],
            },
        ),
        uart=UARTPattern(rx_tx_series_resistor=100),
        can=CANPattern(
            requires_transceiver=True,
            recommended_transceivers=["SN65HVD230", "MCP2551", "TJA1051"],
            termination_resistor_ohm=120,
        ),
        usb=USBPattern(
            dp_dm_series_resistor_ohm=27,
            esd_protection_ic="USBLC6-2SC6",
            connector_footprint="USB_C_Receptacle_HRO_TYPE-C-31-M-12",
        ),
    ),

    # Domain 10 — Layout
    layout=LayoutConstraints(
        routing_constraints=[
            RoutingRule(net_class="usb_dp_dm", trace_width_mm=0.2, impedance_ohm=90.0, differential_pair=True, length_match_mm=0.15),
            RoutingRule(net_class="power", trace_width_mm=0.3),
            RoutingRule(net_class="signal", trace_width_mm=0.15),
        ],
        placement_constraints=[
            PlacementRule(component_type="decoupling_cap", max_distance_mm=3.0, reference_pin="VDD"),
            PlacementRule(component_type="crystal", max_distance_mm=5.0, reference_pin="PF0-OSC_IN"),
        ],
        stackup_recommendation="2-layer",
    ),

    # Domain 11 — Firmware
    firmware=FirmwareBinding(
        clock_tree_defaults={
            "sysclk_mhz": 170,
            "hclk_mhz": 170,
            "apb1_mhz": 170,
            "apb2_mhz": 170,
            "hse_mhz": 8,
            "pll_source": "HSE",
            "pll_m": 2,
            "pll_n": 85,
            "pll_r": 2,
        },
        bus_init_defaults={
            "I2C1": BusConfig(bus_type="I2C", default_speed_hz=400000, default_mode="fast"),
            "SPI1": BusConfig(bus_type="SPI", default_speed_hz=10000000, default_mode="mode_0"),
            "USART1": BusConfig(bus_type="UART", default_speed_hz=115200),
            "USART2": BusConfig(bus_type="UART", default_speed_hz=115200),
            "FDCAN1": BusConfig(bus_type="CAN", default_speed_hz=500000),
        },
        pinmux_templates={
            "I2C1_SCL": "HAL_GPIO_Init(GPIOB, &(GPIO_InitTypeDef){.Pin=GPIO_PIN_6, .Mode=GPIO_MODE_AF_OD, .Pull=GPIO_NOPULL, .Speed=GPIO_SPEED_FREQ_HIGH, .Alternate=GPIO_AF4_I2C1})",
            "I2C1_SDA": "HAL_GPIO_Init(GPIOB, &(GPIO_InitTypeDef){.Pin=GPIO_PIN_7, .Mode=GPIO_MODE_AF_OD, .Pull=GPIO_NOPULL, .Speed=GPIO_SPEED_FREQ_HIGH, .Alternate=GPIO_AF4_I2C1})",
            "SPI1_SCK": "HAL_GPIO_Init(GPIOA, &(GPIO_InitTypeDef){.Pin=GPIO_PIN_5, .Mode=GPIO_MODE_AF_PP, .Pull=GPIO_NOPULL, .Speed=GPIO_SPEED_FREQ_VERY_HIGH, .Alternate=GPIO_AF5_SPI1})",
        },
        bootloader_options=["uart_boot", "usb_dfu", "swd_flash"],
        sdk_framework="stm32hal",
    ),

    # Domain 12 — Provenance
    provenance=[
        AttributeProvenance(
            source_ref="STM32G431xx Datasheet DS12589 Rev 5",
            source_type="datasheet",
            verification_status="reviewed",
            confidence_score=0.92,
            last_validated_date="2026-02-01",
            validated_against="STM32CubeMX v6.11",
        ),
        AttributeProvenance(
            source_ref="AN4488 — Getting started with STM32G4 hardware design",
            source_type="app_note",
            verification_status="reviewed",
            confidence_score=0.90,
        ),
    ],
)

# Register with the profile registry
from shared.knowledge.mcu_profiles import register
register(PROFILE)
