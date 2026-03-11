# SPDX-License-Identifier: AGPL-3.0-or-later
"""RP2040 — MCU Device Profile.

Data sources:
- RP2040 Datasheet (Raspberry Pi, 2024)
- RP2040 Hardware Design Guide
- Pico SDK gpio.h, hardware/clocks.h
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
    ResetCircuit,
    RoutingRule,
    SPIPattern,
    TemperatureGrade,
    UARTPattern,
    USBPattern,
    PassiveSpec,
)

# RP2040: Every GPIO has the same 4 alt functions (SIO, SPI, UART, I2C, PWM, PIO)
# The alt function assignment follows a fixed pattern based on GPIO number.

def _rp2040_gpio(num: int, pin_number: str) -> PinDefinition:
    """Generate a standard RP2040 GPIO pin with its alt functions."""
    alts = []
    # SPI: GPIO0-3=SPI0, GPIO4-7=SPI1, GPIO8-11=SPI0, GPIO12-15=SPI1, ...
    spi_idx = (num // 4) % 2
    spi_funcs = ["RX", "CSn", "SCK", "TX"]
    spi_func = spi_funcs[num % 4]
    alts.append(AltFunction(function=f"SPI{spi_idx}_{spi_func}", af_number=1))
    # UART: GPIO0-3=UART0, GPIO4-7=UART1, GPIO8-11=UART0, GPIO12-15=UART1, ...
    uart_idx = (num // 4) % 2
    uart_funcs = ["TX", "RX", "CTS", "RTS"]
    uart_func = uart_funcs[num % 4]
    alts.append(AltFunction(function=f"UART{uart_idx}_{uart_func}", af_number=2))
    # I2C: GPIO0-1=I2C0, GPIO2-3=I2C1, GPIO4-5=I2C0, GPIO6-7=I2C1, ...
    i2c_idx = (num // 2) % 2
    i2c_func = "SDA" if num % 2 == 0 else "SCL"
    alts.append(AltFunction(function=f"I2C{i2c_idx}_{i2c_func}", af_number=3, available_modes=["standard", "fast", "fast_plus"]))
    # PWM: GPIO0-1=PWM0, GPIO2-3=PWM1, ...
    pwm_idx = num // 2
    pwm_ch = "A" if num % 2 == 0 else "B"
    alts.append(AltFunction(function=f"PWM{pwm_idx % 8}_{pwm_ch}", af_number=4))
    # PIO
    alts.append(AltFunction(function="PIO0", af_number=6))
    alts.append(AltFunction(function="PIO1", af_number=7))

    return PinDefinition(
        pin_name=f"GPIO{num}",
        pin_number=pin_number,
        pin_type=PinType.gpio,
        electrical=PinElectrical(
            max_source_ma=12, max_sink_ma=12,
            has_internal_pullup=True, has_internal_pulldown=True,
            pullup_value_ohm=50000,
        ),
        alt_functions=alts,
    )


# Pin numbers for QFN-56 package (from RP2040 datasheet Table 5)
_PIN_MAP = {
    0: "2", 1: "3", 2: "4", 3: "5", 4: "6", 5: "7", 6: "8", 7: "9",
    8: "11", 9: "12", 10: "13", 11: "14", 12: "15", 13: "16", 14: "17", 15: "18",
    16: "27", 17: "28", 18: "29", 19: "30", 20: "31", 21: "32", 22: "34",
    23: "35", 24: "36", 25: "37", 26: "38", 27: "39", 28: "40", 29: "41",
}


PROFILE = MCUDeviceProfile(
    # Domain 1 — Identity
    identity=MCUIdentity(
        vendor="Raspberry Pi",
        family="RP2040",
        series="RP2040",
        mpn="RP2040",
        package="QFN-56",
        pin_count=56,
        temperature_grade=TemperatureGrade.industrial,
        lifecycle_status="active",
        datasheet_refs=[
            DatasheetRef(
                url="https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf",
                version="v1.9",
                date="2024-01-01",
            ),
            DatasheetRef(
                url="https://datasheets.raspberrypi.com/rp2040/hardware-design-with-rp2040.pdf",
                version="v1.3",
                date="2024-01-01",
            ),
        ],
    ),

    # Domain 2 — Pinout (30 GPIOs)
    pinout=MCUPinout(
        pins=[
            # Power pins
            PinDefinition(pin_name="IOVDD", pin_number="10", pin_type=PinType.power),
            PinDefinition(pin_name="IOVDD", pin_number="22", pin_type=PinType.power),
            PinDefinition(pin_name="IOVDD", pin_number="33", pin_type=PinType.power),
            PinDefinition(pin_name="IOVDD", pin_number="42", pin_type=PinType.power),
            PinDefinition(pin_name="DVDD", pin_number="23", pin_type=PinType.power),
            PinDefinition(pin_name="DVDD", pin_number="50", pin_type=PinType.power),
            PinDefinition(pin_name="USB_VDD", pin_number="48", pin_type=PinType.power),
            PinDefinition(pin_name="VREG_VIN", pin_number="44", pin_type=PinType.power),
            PinDefinition(pin_name="VREG_VOUT", pin_number="45", pin_type=PinType.power),
            PinDefinition(pin_name="ADC_AVDD", pin_number="43", pin_type=PinType.power),
            PinDefinition(pin_name="GND", pin_number="57", pin_type=PinType.ground),  # Pad
            # Reset
            PinDefinition(pin_name="RUN", pin_number="26", pin_type=PinType.reset),
            # Crystal
            PinDefinition(pin_name="XIN", pin_number="20", pin_type=PinType.osc),
            PinDefinition(pin_name="XOUT", pin_number="21", pin_type=PinType.osc),
            # USB
            PinDefinition(pin_name="USB_DM", pin_number="46", pin_type=PinType.gpio,
                alt_functions=[AltFunction(function="USB_DM")]),
            PinDefinition(pin_name="USB_DP", pin_number="47", pin_type=PinType.gpio,
                alt_functions=[AltFunction(function="USB_DP")]),
            # SWD
            PinDefinition(pin_name="SWCLK", pin_number="24", pin_type=PinType.debug),
            PinDefinition(pin_name="SWDIO", pin_number="25", pin_type=PinType.debug),
            # QSPI flash pins
            PinDefinition(pin_name="QSPI_SCLK", pin_number="52", pin_type=PinType.gpio),
            PinDefinition(pin_name="QSPI_SS", pin_number="51", pin_type=PinType.gpio),
            PinDefinition(pin_name="QSPI_SD0", pin_number="53", pin_type=PinType.gpio),
            PinDefinition(pin_name="QSPI_SD1", pin_number="55", pin_type=PinType.gpio),
            PinDefinition(pin_name="QSPI_SD2", pin_number="54", pin_type=PinType.gpio),
            PinDefinition(pin_name="QSPI_SD3", pin_number="56", pin_type=PinType.gpio),
            # GPIOs 0-29
        ] + [_rp2040_gpio(i, _PIN_MAP[i]) for i in range(30)],
        reserved_pins=[],  # RP2040 QSPI flash pins are separate from user GPIOs
        recommended_pinmaps=[
            PinMap(name="i2c0_default", mappings={"SDA": "GPIO0", "SCL": "GPIO1"}),
            PinMap(name="i2c0_alt", mappings={"SDA": "GPIO4", "SCL": "GPIO5"}),
            PinMap(name="i2c1_default", mappings={"SDA": "GPIO2", "SCL": "GPIO3"}),
            PinMap(name="spi0_default", mappings={"RX": "GPIO0", "CSn": "GPIO1", "SCK": "GPIO2", "TX": "GPIO3"}),
            PinMap(name="spi0_alt", mappings={"RX": "GPIO16", "CSn": "GPIO17", "SCK": "GPIO18", "TX": "GPIO19"}),
            PinMap(name="uart0_default", mappings={"TX": "GPIO0", "RX": "GPIO1"}),
            PinMap(name="uart1_default", mappings={"TX": "GPIO4", "RX": "GPIO5"}),
        ],
    ),

    # Domain 3 — Power
    power=MCUPowerTree(
        power_domains=[
            PowerDomain(
                name="IOVDD",
                nominal_voltage=3.3,
                allowed_range=(1.8, 3.6),
                max_current_draw_ma=100.0,
                sequencing_order=1,
                decoupling=[
                    DecouplingRule(
                        domain="IOVDD",
                        capacitors=[
                            CapSpec(value="100nF", type="X7R", package="0402", quantity=4),
                        ],
                        placement_rule="100nF within 3mm of each IOVDD pin",
                        pin_group=["IOVDD_10", "IOVDD_22", "IOVDD_33", "IOVDD_42"],
                    ),
                ],
            ),
            PowerDomain(
                name="DVDD",
                nominal_voltage=1.1,
                allowed_range=(1.0, 1.3),
                max_current_draw_ma=150.0,
                sequencing_order=2,
                decoupling=[
                    DecouplingRule(
                        domain="DVDD",
                        capacitors=[
                            CapSpec(value="100nF", type="X7R", package="0402", quantity=2),
                        ],
                        placement_rule="100nF within 3mm of each DVDD pin",
                        pin_group=["DVDD_23", "DVDD_50"],
                        notes="Core voltage — use on-chip regulator output (VREG_VOUT) or external 1.1V",
                    ),
                ],
            ),
            PowerDomain(
                name="USB_VDD",
                nominal_voltage=3.3,
                allowed_range=(3.0, 3.6),
                max_current_draw_ma=50.0,
                decoupling=[
                    DecouplingRule(
                        domain="USB_VDD",
                        capacitors=[CapSpec(value="100nF", type="X7R", package="0402")],
                        placement_rule="within 3mm of USB_VDD pin",
                    ),
                ],
            ),
            PowerDomain(
                name="ADC_AVDD",
                nominal_voltage=3.3,
                allowed_range=(3.0, 3.6),
                max_current_draw_ma=2.0,
                decoupling=[
                    DecouplingRule(
                        domain="ADC_AVDD",
                        capacitors=[
                            CapSpec(value="100nF", type="X7R", package="0402"),
                        ],
                        placement_rule="within 3mm of ADC_AVDD, after ferrite",
                        notes="Connect via ferrite bead from IOVDD for ADC noise isolation",
                    ),
                ],
            ),
        ],
        power_input_patterns=[
            PowerInputPattern(
                name="usb_5v_internal_regulator",
                input_voltage_range=(1.8, 5.5),
                recommended_regulators=[
                    RegulatorOption(
                        topology="ldo",
                        recommended_mpns=["on-chip VREG"],
                        output_voltage=1.1,
                        max_current_ma=300,
                        required_passives=[
                            PassiveSpec(
                                component_type="inductor",
                                value="3.3µH",
                                spec="shielded, DCR < 300mΩ",
                                package="0805",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    ),

    # Domain 4 — Clocking
    clock=ClockConfig(
        main_clock=ClockSource(
            type=ClockSourceType.external_xtal,
            frequency_hz=12_000_000,
            accuracy_ppm=30,
            load_capacitance_pf=15.0,
            recommended_crystals=["ABM8-12.000MHZ-B2-T"],
            required_caps=[
                CapSpec(value="15pF", type="C0G", package="0402", quantity=2),
            ],
            layout_constraints=[
                "Keep crystal within 5mm of XIN/XOUT",
                "No vias under crystal",
                "Ground plane under crystal",
            ],
            osc_pins=["XIN", "XOUT"],
        ),
        pll_config=PLLConfig(
            input_source="XOSC",
            multiplier=133,
            output_divider=1,
            max_output_hz=133_000_000,
        ),
        safe_default_mhz=12,  # Ring oscillator ~6.5MHz typ, but XOSC 12MHz after init
    ),

    # Domain 5 — Boot/Reset
    boot=BootConfig(
        reset_circuit=ResetCircuit(
            nrst_pin="RUN",
            recommended_pullup_ohm=10000,
            cap_to_gnd_nf=100,
        ),
        boot_mode_pins=[
            BootModePin(
                pin="QSPI_SS",
                normal_boot_state="high",
                pull_resistor="pull_up_10k",
                dont_use_as_gpio_until_boot=True,
                notes="Hold QSPI_SS LOW during boot to enter USB bootloader mode (BOOTSEL on Pico).",
            ),
        ],
        programming_mode_entry=[
            "Hold BOOTSEL (QSPI_SS) button LOW",
            "Assert RUN LOW briefly (or power cycle)",
            "Release RUN — MCU enters USB Mass Storage bootloader",
            "Drag-and-drop UF2 file via USB",
            "Or flash via SWD at any time",
        ],
    ),

    # Domain 6 — Debug
    debug_interfaces=[
        DebugInterface(
            protocol="SWD",
            pins={"SWCLK": "SWCLK", "SWDIO": "SWDIO"},
            recommended_connector=ConnectorSpec(
                name="ARM SWD 3-pin",
                footprint="PinHeader_1x03_P2.54mm",
                alt_footprint="TagConnect_TC2030-IDC",
                pinout={"SWCLK": 1, "GND": 2, "SWDIO": 3},
            ),
        ),
        DebugInterface(
            protocol="USB_DFU",
            pins={"DM": "USB_DM", "DP": "USB_DP"},
        ),
    ],

    # Domain 7 — Mandatory Components
    mandatory_components=[
        MandatoryComponent(
            component_type="cap",
            value="100nF",
            spec="X7R 0402",
            quantity_rule="per_vdd_pin",
            placement="within 3mm of each IOVDD/DVDD/USB_VDD pin",
            rationale="RP2040 Hardware Design Guide: 100nF per power pin",
        ),
        MandatoryComponent(
            component_type="cap",
            value="10µF",
            spec="X5R 0805 ≥10V",
            quantity_rule="one_per_board",
            placement="at IOVDD rail entry",
            rationale="Bulk decoupling for IO supply",
        ),
        MandatoryComponent(
            component_type="cap",
            value="1µF",
            spec="X7R 0402",
            quantity_rule="one_per_board",
            connectivity=NetTemplate(net_name="VREG_VOUT_DECOUPLE", connected_pins=["VREG_VOUT", "GND"]),
            placement="within 3mm of VREG_VOUT",
            rationale="On-chip regulator output decoupling (mandatory per RP2040 HW Guide)",
        ),
        MandatoryComponent(
            component_type="crystal",
            value="12MHz",
            spec="±30ppm, 15pF load",
            quantity_rule="one_per_board",
            connectivity=NetTemplate(net_name="XOSC", connected_pins=["XIN", "XOUT"]),
            placement="within 5mm of XIN/XOUT",
            rationale="External crystal for PLL reference",
        ),
        MandatoryComponent(
            component_type="resistor",
            value="1kΩ",
            spec="0402 ±5%",
            quantity_rule="one_per_board",
            connectivity=NetTemplate(net_name="USB_BOOT", connected_pins=["XIN", "GND"]),
            placement="near XIN pin",
            rationale="RP2040 HW Guide: 1kΩ between XIN and GND for crystal damping",
        ),
        MandatoryComponent(
            component_type="cap",
            value="15pF",
            spec="C0G 0402 ±5%",
            quantity_rule="per_bus",
            placement="within 2mm of XIN/XOUT",
            rationale="Crystal load capacitors (2× required)",
        ),
        MandatoryComponent(
            component_type="resistor",
            value="27Ω",
            spec="0402 ±1%",
            quantity_rule="per_bus",
            connectivity=NetTemplate(net_name="USB_SERIES", connected_pins=["USB_DP", "CONN_DP"]),
            placement="near USB pins",
            rationale="USB D+/D- series resistors (2× required)",
        ),
    ],

    # Domain 8 — IO Rules
    io_rules=IOElectricalRules(
        io_voltage_tolerance_per_domain={"IOVDD": (-0.3, 3.63)},
        max_source_current_per_pin_ma=12.0,
        max_sink_current_per_pin_ma=12.0,
        max_total_current_per_port_ma=50.0,
        adc_input_range=(0.0, 3.3),
        adc_source_impedance_max_ohm=10000,
        analog_domain_rules=[
            "ADC input range 0 to ADC_AVDD",
            "GPIO26-29 can be used as ADC inputs (ADC0-ADC3)",
            "Internal temperature sensor on ADC4",
        ],
    ),

    # Domain 9 — Peripheral Patterns
    peripheral_patterns=PeripheralPatterns(
        i2c=I2CPattern(
            pullup_value_rule="4.7kΩ for ≤100kHz, 2.2kΩ for 400kHz, 1kΩ for 1MHz",
            max_bus_capacitance_pf=400,
            recommended_pins={"SDA": ["GPIO0", "GPIO4"], "SCL": ["GPIO1", "GPIO5"]},
            max_devices_per_bus=8,
        ),
        spi=SPIPattern(
            max_freq_mhz=62,
            recommended_pins={
                "RX": ["GPIO0", "GPIO16"], "CSn": ["GPIO1", "GPIO17"],
                "SCK": ["GPIO2", "GPIO18"], "TX": ["GPIO3", "GPIO19"],
            },
        ),
        uart=UARTPattern(rx_tx_series_resistor=100),
        usb=USBPattern(
            dp_dm_series_resistor_ohm=27,
            esd_protection_ic="USBLC6-2SC6",
            connector_footprint="USB_Micro_B_Molex_105017-0001",
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
            PlacementRule(component_type="decoupling_cap", max_distance_mm=3.0, reference_pin="IOVDD"),
            PlacementRule(component_type="crystal", max_distance_mm=5.0, reference_pin="XIN"),
            PlacementRule(component_type="flash_chip", max_distance_mm=10.0, reference_pin="QSPI_SCLK"),
        ],
        stackup_recommendation="2-layer",
    ),

    # Domain 11 — Firmware
    firmware=FirmwareBinding(
        clock_tree_defaults={
            "sys_clk_mhz": 125,
            "xosc_mhz": 12,
            "pll_sys_mhz": 125,
            "pll_usb_mhz": 48,
        },
        bus_init_defaults={
            "I2C0": BusConfig(bus_type="I2C", default_speed_hz=400000, default_mode="fast"),
            "SPI0": BusConfig(bus_type="SPI", default_speed_hz=1000000, default_mode="mode_0"),
            "UART0": BusConfig(bus_type="UART", default_speed_hz=115200),
        },
        pinmux_templates={
            "I2C0_SDA": "gpio_set_function(0, GPIO_FUNC_I2C)",
            "I2C0_SCL": "gpio_set_function(1, GPIO_FUNC_I2C)",
            "SPI0_SCK": "gpio_set_function(2, GPIO_FUNC_SPI)",
        },
        bootloader_options=["usb_uf2", "swd_flash", "uart_boot"],
        sdk_framework="pico-sdk",
    ),

    # Domain 12 — Provenance
    provenance=[
        AttributeProvenance(
            source_ref="RP2040 Datasheet v1.9",
            source_type="datasheet",
            verification_status="reviewed",
            confidence_score=0.90,
            last_validated_date="2026-02-01",
            validated_against="Pico SDK v1.5.1",
        ),
        AttributeProvenance(
            source_ref="Hardware design with RP2040 v1.3",
            source_type="app_note",
            verification_status="reviewed",
            confidence_score=0.92,
        ),
    ],
)

# Register with the profile registry
from shared.knowledge.mcu_profiles import register
register(PROFILE)
