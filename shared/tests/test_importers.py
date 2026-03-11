# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Phase F — SDK Parsers, License Matrix, and Profile Diff.

Covers:
  - STM32CubeMX XML Parser → MCUProfile
  - ESP-IDF Header Parser → Pin-Tables
  - Pico SDK Header Parser → Alt-Functions
  - SPDX License Compatibility Matrix
  - Profile Diff-Validation
"""
from __future__ import annotations

import pytest

from shared.knowledge.mcu_profile_schema import (
    MCUDeviceProfile,
    PinType,
)


# ===================================================================
# STM32CubeMX XML Parser Tests
# ===================================================================

# Minimal CubeMX-style XML for testing
CUBEMX_SAMPLE_XML = """\
<Mcu RefName="STM32G431CBUx" Family="STM32G4" Line="STM32G4x1"
     Package="UFQFPN48" IONb="48" ClockTree="STM32G4">
  <Pin Name="VDD" Position="1" Type="Power">
  </Pin>
  <Pin Name="VSS" Position="23" Type="Power">
  </Pin>
  <Pin Name="NRST" Position="7" Type="Reset">
  </Pin>
  <Pin Name="BOOT0" Position="44" Type="Boot">
  </Pin>
  <Pin Name="PF0-OSC_IN" Position="5" Type="I/O">
    <Signal Name="RCC_OSC_IN" />
  </Pin>
  <Pin Name="PF1-OSC_OUT" Position="6" Type="I/O">
    <Signal Name="RCC_OSC_OUT" />
  </Pin>
  <Pin Name="PA0" Position="10" Type="I/O">
    <Signal Name="TIM2_CH1" IOModes="GPIO_AF1_TIM2" />
    <Signal Name="USART2_CTS" IOModes="GPIO_AF7_USART2" />
    <Signal Name="ADC1_IN1" />
  </Pin>
  <Pin Name="PA5" Position="15" Type="I/O">
    <Signal Name="SPI1_SCK" IOModes="GPIO_AF5_SPI1" />
    <Signal Name="TIM2_CH1" IOModes="GPIO_AF1_TIM2" />
    <Signal Name="DAC1_OUT2" />
  </Pin>
  <Pin Name="PA6" Position="16" Type="I/O">
    <Signal Name="SPI1_MISO" IOModes="GPIO_AF5_SPI1" />
  </Pin>
  <Pin Name="PA7" Position="17" Type="I/O">
    <Signal Name="SPI1_MOSI" IOModes="GPIO_AF5_SPI1" />
  </Pin>
  <Pin Name="PA9" Position="30" Type="I/O">
    <Signal Name="USART1_TX" IOModes="GPIO_AF7_USART1" />
    <Signal Name="I2C2_SCL" IOModes="GPIO_AF4_I2C2" />
  </Pin>
  <Pin Name="PA10" Position="31" Type="I/O">
    <Signal Name="USART1_RX" IOModes="GPIO_AF7_USART1" />
    <Signal Name="I2C2_SDA" IOModes="GPIO_AF4_I2C2" />
  </Pin>
  <Pin Name="PA11" Position="32" Type="I/O">
    <Signal Name="USB_DM" />
    <Signal Name="FDCAN1_RX" IOModes="GPIO_AF9_FDCAN1" />
  </Pin>
  <Pin Name="PA12" Position="33" Type="I/O">
    <Signal Name="USB_DP" />
    <Signal Name="FDCAN1_TX" IOModes="GPIO_AF9_FDCAN1" />
  </Pin>
  <Pin Name="PA13" Position="34" Type="I/O">
    <Signal Name="SWDIO" />
  </Pin>
  <Pin Name="PA14" Position="37" Type="I/O">
    <Signal Name="SWCLK" />
  </Pin>
  <Pin Name="PB6" Position="42" Type="I/O">
    <Signal Name="I2C1_SCL" IOModes="GPIO_AF4_I2C1" />
    <Signal Name="USART1_TX" IOModes="GPIO_AF7_USART1" />
  </Pin>
  <Pin Name="PB7" Position="43" Type="I/O">
    <Signal Name="I2C1_SDA" IOModes="GPIO_AF4_I2C1" />
    <Signal Name="USART1_RX" IOModes="GPIO_AF7_USART1" />
  </Pin>
  <IP Name="I2C1" InstanceName="I2C1" Version="i2c_v2_1" />
  <IP Name="I2C2" InstanceName="I2C2" Version="i2c_v2_1" />
  <IP Name="SPI1" InstanceName="SPI1" Version="spi_v2_2" />
  <IP Name="USART1" InstanceName="USART1" Version="usart_v2_1" />
  <IP Name="FDCAN1" InstanceName="FDCAN1" Version="fdcan_v1_1" />
  <IP Name="USB" InstanceName="USB" Version="usb_v1_0" />
</Mcu>
"""


class TestCubeMXParser:
    def test_parse_xml_string(self):
        from shared.knowledge.importers.cubemx_parser import parse_cubemx_xml_string
        profile = parse_cubemx_xml_string(CUBEMX_SAMPLE_XML, "test_sample")
        assert isinstance(profile, MCUDeviceProfile)
        assert profile.identity.vendor == "STMicroelectronics"
        assert profile.identity.family == "STM32G4"

    def test_pin_count(self):
        from shared.knowledge.importers.cubemx_parser import parse_cubemx_xml_string
        profile = parse_cubemx_xml_string(CUBEMX_SAMPLE_XML)
        assert len(profile.pinout.pins) >= 16  # We have 16 pins in the sample

    def test_pin_types_classified(self):
        from shared.knowledge.importers.cubemx_parser import parse_cubemx_xml_string
        profile = parse_cubemx_xml_string(CUBEMX_SAMPLE_XML)
        pin_types = {p.pin_name: p.pin_type for p in profile.pinout.pins}
        assert pin_types["VDD"] == PinType.power
        assert pin_types["VSS"] == PinType.ground
        assert pin_types["NRST"] == PinType.reset
        assert pin_types["BOOT0"] == PinType.boot

    def test_debug_pins_detected(self):
        from shared.knowledge.importers.cubemx_parser import parse_cubemx_xml_string
        profile = parse_cubemx_xml_string(CUBEMX_SAMPLE_XML)
        pin_types = {p.pin_name: p.pin_type for p in profile.pinout.pins}
        assert pin_types["PA13"] == PinType.debug
        assert pin_types["PA14"] == PinType.debug

    def test_osc_pins_detected(self):
        from shared.knowledge.importers.cubemx_parser import parse_cubemx_xml_string
        profile = parse_cubemx_xml_string(CUBEMX_SAMPLE_XML)
        pin_types = {p.pin_name: p.pin_type for p in profile.pinout.pins}
        assert pin_types["PF0-OSC_IN"] == PinType.osc
        assert pin_types["PF1-OSC_OUT"] == PinType.osc

    def test_alt_functions_extracted(self):
        from shared.knowledge.importers.cubemx_parser import parse_cubemx_xml_string
        profile = parse_cubemx_xml_string(CUBEMX_SAMPLE_XML)
        pa0 = next(p for p in profile.pinout.pins if p.pin_name == "PA0")
        af_names = {af.function for af in pa0.alt_functions}
        assert "TIM2_CH1" in af_names
        assert "USART2_CTS" in af_names
        assert "ADC1_IN1" in af_names

    def test_af_number_extracted(self):
        from shared.knowledge.importers.cubemx_parser import parse_cubemx_xml_string
        profile = parse_cubemx_xml_string(CUBEMX_SAMPLE_XML)
        pa0 = next(p for p in profile.pinout.pins if p.pin_name == "PA0")
        tim_af = next(af for af in pa0.alt_functions if af.function == "TIM2_CH1")
        assert tim_af.af_number == 1

    def test_reserved_pins_include_debug(self):
        from shared.knowledge.importers.cubemx_parser import parse_cubemx_xml_string
        profile = parse_cubemx_xml_string(CUBEMX_SAMPLE_XML)
        reserved_names = {r.pin_name for r in profile.pinout.reserved_pins}
        assert "PA13" in reserved_names
        assert "PA14" in reserved_names

    def test_recommended_pinmaps_generated(self):
        from shared.knowledge.importers.cubemx_parser import parse_cubemx_xml_string
        profile = parse_cubemx_xml_string(CUBEMX_SAMPLE_XML)
        pinmap_names = {pm.name for pm in profile.pinout.recommended_pinmaps}
        # Should find I2C, SPI, USART pinmaps
        assert any("i2c" in n for n in pinmap_names)
        assert any("spi" in n for n in pinmap_names)

    def test_peripheral_patterns_from_ips(self):
        from shared.knowledge.importers.cubemx_parser import parse_cubemx_xml_string
        profile = parse_cubemx_xml_string(CUBEMX_SAMPLE_XML)
        assert profile.peripheral_patterns is not None
        assert profile.peripheral_patterns.i2c is not None
        assert profile.peripheral_patterns.spi is not None
        assert profile.peripheral_patterns.uart is not None
        assert profile.peripheral_patterns.can is not None
        assert profile.peripheral_patterns.usb is not None

    def test_power_domains_from_pins(self):
        from shared.knowledge.importers.cubemx_parser import parse_cubemx_xml_string
        profile = parse_cubemx_xml_string(CUBEMX_SAMPLE_XML)
        domain_names = {d.name for d in profile.power.power_domains}
        assert "VDD" in domain_names

    def test_firmware_binding_generated(self):
        from shared.knowledge.importers.cubemx_parser import parse_cubemx_xml_string
        profile = parse_cubemx_xml_string(CUBEMX_SAMPLE_XML)
        assert profile.firmware.sdk_framework == "stm32hal"
        assert len(profile.firmware.bus_init_defaults) > 0

    def test_provenance_tracked(self):
        from shared.knowledge.importers.cubemx_parser import parse_cubemx_xml_string
        profile = parse_cubemx_xml_string(CUBEMX_SAMPLE_XML, "test_file.xml")
        assert len(profile.provenance) == 1
        assert "test_file.xml" in profile.provenance[0].source_ref
        assert profile.provenance[0].verification_status == "auto_imported"

    def test_mpn_x_suffix_normalized(self):
        from shared.knowledge.importers.cubemx_parser import parse_cubemx_xml_string
        profile = parse_cubemx_xml_string(CUBEMX_SAMPLE_XML)
        # STM32G431CBUx → STM32G431CBU6
        assert profile.identity.mpn.endswith("6")


# ===================================================================
# ESP-IDF Header Parser Tests
# ===================================================================

ESP_GPIO_SIG_MAP = """\
#define I2CEXT0_SCL_IN_IDX      17
#define I2CEXT0_SDA_IN_IDX      18
#define I2CEXT0_SCL_OUT_IDX     17
#define I2CEXT0_SDA_OUT_IDX     18
#define SPI3_CLK_IN_IDX         19
#define SPI3_MISO_IN_IDX        20
#define SPI3_MOSI_OUT_IDX       21
#define U0TXD_OUT_IDX           14
#define U0RXD_IN_IDX            14
#define U1TXD_OUT_IDX           17
#define U1RXD_IN_IDX            18
#define USB_SERIAL_JTAG_DP_OUT_IDX  120
#define USB_SERIAL_JTAG_DM_OUT_IDX  121
"""

ESP_SOC_CAPS = """\
#define SOC_GPIO_PIN_COUNT          49
#define SOC_I2C_NUM                 2
#define SOC_SPI_PERIPH_NUM          3
#define SOC_UART_NUM                3
#define SOC_USB_OTG_SUPPORTED       1
#define SOC_WIFI_SUPPORTED          1
"""


class TestESPIDFParser:
    def test_parse_header_string(self):
        from shared.knowledge.importers.espidf_parser import parse_espidf_header_string
        profile = parse_espidf_header_string(ESP_GPIO_SIG_MAP, ESP_SOC_CAPS, "ESP32-S3")
        assert isinstance(profile, MCUDeviceProfile)
        assert profile.identity.vendor == "Espressif"

    def test_gpio_count_from_soc_caps(self):
        from shared.knowledge.importers.espidf_parser import parse_espidf_header_string
        profile = parse_espidf_header_string(ESP_GPIO_SIG_MAP, ESP_SOC_CAPS, "ESP32-S3")
        assert len(profile.pinout.pins) == 49

    def test_signal_map_parsed(self):
        from shared.knowledge.importers.espidf_parser import _parse_gpio_sig_map
        signals = _parse_gpio_sig_map(ESP_GPIO_SIG_MAP)
        sig_names = {s.signal_name for s in signals}
        assert "I2CEXT0_SCL" in sig_names
        assert "SPI3_CLK" in sig_names
        assert "U0TXD" in sig_names

    def test_soc_caps_parsed(self):
        from shared.knowledge.importers.espidf_parser import _parse_soc_caps
        caps = _parse_soc_caps(ESP_SOC_CAPS)
        assert caps["SOC_GPIO_PIN_COUNT"] == 49
        assert caps["SOC_I2C_NUM"] == 2
        assert caps["SOC_SPI_PERIPH_NUM"] == 3

    def test_reserved_gpios_for_s3(self):
        from shared.knowledge.importers.espidf_parser import parse_espidf_header_string
        profile = parse_espidf_header_string(ESP_GPIO_SIG_MAP, ESP_SOC_CAPS, "ESP32-S3")
        reserved_names = {r.pin_name for r in profile.pinout.reserved_pins}
        # ESP32-S3 reserves GPIO26-32 for PSRAM
        assert "GPIO26" in reserved_names
        assert "GPIO27" in reserved_names

    def test_strap_pins_marked(self):
        from shared.knowledge.importers.espidf_parser import parse_espidf_header_string
        profile = parse_espidf_header_string(ESP_GPIO_SIG_MAP, ESP_SOC_CAPS, "ESP32-S3")
        gpio0 = next(p for p in profile.pinout.pins if p.pin_name == "GPIO0")
        assert gpio0.boot_strap is True

    def test_recommended_pinmaps_s3(self):
        from shared.knowledge.importers.espidf_parser import parse_espidf_header_string
        profile = parse_espidf_header_string(ESP_GPIO_SIG_MAP, ESP_SOC_CAPS, "ESP32-S3")
        pinmap_names = {pm.name for pm in profile.pinout.recommended_pinmaps}
        assert "i2c0_default" in pinmap_names
        assert "uart0_default" in pinmap_names
        assert "usb_default" in pinmap_names

    def test_peripheral_patterns_from_caps(self):
        from shared.knowledge.importers.espidf_parser import parse_espidf_header_string
        profile = parse_espidf_header_string(ESP_GPIO_SIG_MAP, ESP_SOC_CAPS, "ESP32-S3")
        assert profile.peripheral_patterns.i2c is not None
        assert profile.peripheral_patterns.spi is not None
        assert profile.peripheral_patterns.usb is not None
        assert profile.peripheral_patterns.rf is not None

    def test_esp32c3_variant(self):
        from shared.knowledge.importers.espidf_parser import parse_espidf_header_string
        profile = parse_espidf_header_string("", "", "ESP32-C3")
        assert len(profile.pinout.pins) == 22
        assert profile.identity.family == "ESP32-C3"


# ===================================================================
# Pico SDK Header Parser Tests
# ===================================================================

class TestPicoSDKParser:
    def test_parse_from_table(self):
        from shared.knowledge.importers.picosdk_parser import parse_picosdk_from_table
        profile = parse_picosdk_from_table()
        assert isinstance(profile, MCUDeviceProfile)
        assert profile.identity.vendor == "Raspberry Pi"
        assert profile.identity.family == "RP2040"

    def test_gpio_count(self):
        from shared.knowledge.importers.picosdk_parser import parse_picosdk_from_table
        profile = parse_picosdk_from_table()
        assert len(profile.pinout.pins) == 30

    def test_alt_functions_per_pin(self):
        from shared.knowledge.importers.picosdk_parser import parse_picosdk_from_table
        profile = parse_picosdk_from_table()
        gp0 = next(p for p in profile.pinout.pins if p.pin_name == "GPIO0")
        af_names = {af.function for af in gp0.alt_functions}
        assert "SPI0_RX" in af_names
        assert "UART0_TX" in af_names
        assert "I2C0_SDA" in af_names
        assert "PWM0_A" in af_names

    def test_af_number_is_slot(self):
        from shared.knowledge.importers.picosdk_parser import parse_picosdk_from_table
        profile = parse_picosdk_from_table()
        gp0 = next(p for p in profile.pinout.pins if p.pin_name == "GPIO0")
        spi_af = next(af for af in gp0.alt_functions if af.function == "SPI0_RX")
        assert spi_af.af_number == 1  # SPI is function slot 1

    def test_adc_on_gpio26_29(self):
        from shared.knowledge.importers.picosdk_parser import parse_picosdk_from_table
        profile = parse_picosdk_from_table()
        gp26 = next(p for p in profile.pinout.pins if p.pin_name == "GPIO26")
        af_names = {af.function for af in gp26.alt_functions}
        assert "ADC0" in af_names

    def test_recommended_pinmaps(self):
        from shared.knowledge.importers.picosdk_parser import parse_picosdk_from_table
        profile = parse_picosdk_from_table()
        pinmap_names = {pm.name for pm in profile.pinout.recommended_pinmaps}
        assert "i2c0_default" in pinmap_names
        assert "spi0_default" in pinmap_names
        assert "uart0_default" in pinmap_names

    def test_power_domains(self):
        from shared.knowledge.importers.picosdk_parser import parse_picosdk_from_table
        profile = parse_picosdk_from_table()
        domain_names = {d.name for d in profile.power.power_domains}
        assert "IOVDD" in domain_names
        assert "DVDD" in domain_names

    def test_peripheral_patterns(self):
        from shared.knowledge.importers.picosdk_parser import parse_picosdk_from_table
        profile = parse_picosdk_from_table()
        assert profile.peripheral_patterns.i2c is not None
        assert profile.peripheral_patterns.spi is not None
        assert profile.peripheral_patterns.usb is not None

    def test_firmware_binding(self):
        from shared.knowledge.importers.picosdk_parser import parse_picosdk_from_table
        profile = parse_picosdk_from_table()
        assert profile.firmware.sdk_framework == "pico-sdk"
        assert "I2C0" in profile.firmware.bus_init_defaults
        assert "SPI0" in profile.firmware.bus_init_defaults

    def test_boot_config(self):
        from shared.knowledge.importers.picosdk_parser import parse_picosdk_from_table
        profile = parse_picosdk_from_table()
        assert profile.boot.reset_circuit.nrst_pin == "RUN"
        assert len(profile.boot.boot_mode_pins) == 1
        assert profile.boot.boot_mode_pins[0].pin == "BOOTSEL"

    def test_custom_function_table(self):
        from shared.knowledge.importers.picosdk_parser import parse_picosdk_from_table
        custom = {
            0: {1: "SPI0_RX", 2: "UART0_TX"},
            1: {1: "SPI0_CSn", 2: "UART0_RX"},
        }
        profile = parse_picosdk_from_table(custom)
        # Should still have 30 GPIOs (default count)
        assert len(profile.pinout.pins) == 30


# ===================================================================
# License Compatibility Matrix Tests
# ===================================================================

class TestLicenseMatrix:
    def test_mit_compatible(self):
        from shared.knowledge.importers.license_matrix import check_license_compatibility
        result = check_license_compatibility("MIT", "source_embed")
        assert result.allowed is True
        assert result.level.value == "compatible"

    def test_bsd_compatible(self):
        from shared.knowledge.importers.license_matrix import check_license_compatibility
        result = check_license_compatibility("BSD-3-Clause", "source_embed")
        assert result.allowed is True

    def test_apache_compatible(self):
        from shared.knowledge.importers.license_matrix import check_license_compatibility
        result = check_license_compatibility("Apache-2.0", "source_embed")
        assert result.allowed is True

    def test_lgpl_source_embed_blocked(self):
        from shared.knowledge.importers.license_matrix import check_license_compatibility
        result = check_license_compatibility("LGPL-3.0-only", "source_embed")
        assert result.allowed is False
        assert result.level.value == "conditional"

    def test_lgpl_package_manager_ok(self):
        from shared.knowledge.importers.license_matrix import check_license_compatibility
        result = check_license_compatibility("LGPL-3.0-only", "package_manager")
        assert result.allowed is True

    def test_gpl_source_embed_blocked(self):
        from shared.knowledge.importers.license_matrix import check_license_compatibility
        result = check_license_compatibility("GPL-3.0-only", "source_embed")
        assert result.allowed is False
        assert result.level.value == "copyleft_warning"

    def test_gpl_wrapper_only_ok(self):
        from shared.knowledge.importers.license_matrix import check_license_compatibility
        result = check_license_compatibility("GPL-3.0-only", "wrapper_only")
        assert result.allowed is True

    def test_proprietary_blocked(self):
        from shared.knowledge.importers.license_matrix import check_license_compatibility
        result = check_license_compatibility("Proprietary", "source_embed")
        assert result.allowed is False
        assert result.level.value == "incompatible"

    def test_proprietary_wrapper_only_ok(self):
        from shared.knowledge.importers.license_matrix import check_license_compatibility
        result = check_license_compatibility("Proprietary", "wrapper_only")
        assert result.allowed is True

    def test_agpl_same_license_compatible(self):
        from shared.knowledge.importers.license_matrix import check_license_compatibility
        result = check_license_compatibility("AGPL-3.0-only", "source_embed")
        assert result.allowed is True
        assert result.level.value == "compatible"

    def test_normalize_alias_mit(self):
        from shared.knowledge.importers.license_matrix import normalize_spdx_id
        assert normalize_spdx_id("MIT") == "MIT"

    def test_normalize_alias_apache(self):
        from shared.knowledge.importers.license_matrix import normalize_spdx_id
        assert normalize_spdx_id("Apache 2.0") == "Apache-2.0"

    def test_normalize_alias_gpl(self):
        from shared.knowledge.importers.license_matrix import normalize_spdx_id
        assert normalize_spdx_id("GPL-3") == "GPL-3.0-only"

    def test_normalize_alias_lgpl(self):
        from shared.knowledge.importers.license_matrix import normalize_spdx_id
        assert normalize_spdx_id("LGPL-2.1") == "LGPL-2.1-only"

    def test_unknown_license_treated_incompatible(self):
        from shared.knowledge.importers.license_matrix import get_compatibility_level, CompatibilityLevel
        level = get_compatibility_level("SomeRandomLicense-1.0")
        assert level == CompatibilityLevel.incompatible

    def test_get_all_known_licenses(self):
        from shared.knowledge.importers.license_matrix import get_all_known_licenses
        all_licenses = get_all_known_licenses()
        assert "MIT" in all_licenses
        assert "Apache-2.0" in all_licenses
        assert len(all_licenses) >= 20

    def test_mpl_conditional(self):
        from shared.knowledge.importers.license_matrix import check_license_compatibility
        result = check_license_compatibility("MPL-2.0", "source_embed")
        assert result.level.value == "conditional"

    def test_result_has_message(self):
        from shared.knowledge.importers.license_matrix import check_license_compatibility
        result = check_license_compatibility("MIT", "source_embed")
        assert len(result.message) > 0
        assert result.action == "green"


# ===================================================================
# Profile Diff-Validation Tests
# ===================================================================

class TestProfileDiff:
    def _make_profile(self, mpn="TEST-MCU", pins=None, domains=None):
        from shared.knowledge.mcu_profile_schema import (
            MCUDeviceProfile, MCUIdentity, MCUPinout, MCUPowerTree,
            PinDefinition, PinElectrical, PinType, AltFunction,
            PowerDomain, ClockConfig, ClockSource, ClockSourceType,
            BootConfig, ResetCircuit,
        )
        if pins is None:
            pins = [
                PinDefinition(
                    pin_name="PA0", pin_number="10", pin_type=PinType.gpio,
                    alt_functions=[
                        AltFunction(function="TIM2_CH1"),
                        AltFunction(function="USART2_CTS"),
                    ],
                ),
                PinDefinition(
                    pin_name="PA1", pin_number="11", pin_type=PinType.gpio,
                    alt_functions=[AltFunction(function="TIM2_CH2")],
                ),
                PinDefinition(
                    pin_name="VDD", pin_number="1", pin_type=PinType.power),
            ]
        if domains is None:
            domains = [
                PowerDomain(name="VDD", nominal_voltage=3.3,
                            allowed_range=(3.0, 3.6), max_current_draw_ma=150),
            ]
        return MCUDeviceProfile(
            identity=MCUIdentity(
                vendor="Test", family="TEST", series="TEST",
                mpn=mpn, package="QFP", pin_count=48,
            ),
            pinout=MCUPinout(pins=pins),
            power=MCUPowerTree(power_domains=domains),
            clock=ClockConfig(
                main_clock=ClockSource(
                    type=ClockSourceType.internal_rc,
                    frequency_hz=16_000_000,
                ),
                safe_default_mhz=16,
            ),
            boot=BootConfig(reset_circuit=ResetCircuit(nrst_pin="NRST")),
        )

    def test_identical_profiles_no_diff(self):
        from shared.knowledge.importers.profile_diff import diff_profiles
        p = self._make_profile()
        report = diff_profiles(p, p)
        assert report.pins_matching == 3
        assert report.pins_differing == 0
        assert report.pins_added == 0
        assert report.pins_removed == 0

    def test_added_pin_detected(self):
        from shared.knowledge.importers.profile_diff import diff_profiles
        from shared.knowledge.mcu_profile_schema import PinDefinition, PinType
        existing = self._make_profile()
        imported_pins = list(existing.pinout.pins) + [
            PinDefinition(pin_name="PA2", pin_number="12", pin_type=PinType.gpio),
        ]
        imported = self._make_profile(pins=imported_pins)
        report = diff_profiles(imported, existing)
        assert report.pins_added == 1

    def test_removed_pin_detected(self):
        from shared.knowledge.importers.profile_diff import diff_profiles
        existing = self._make_profile()
        imported = self._make_profile(pins=existing.pinout.pins[:2])  # Remove VDD
        report = diff_profiles(imported, existing)
        assert report.pins_removed == 1

    def test_alt_function_added(self):
        from shared.knowledge.importers.profile_diff import diff_profiles
        from shared.knowledge.mcu_profile_schema import PinDefinition, PinType, AltFunction
        existing = self._make_profile()
        new_pin = PinDefinition(
            pin_name="PA0", pin_number="10", pin_type=PinType.gpio,
            alt_functions=[
                AltFunction(function="TIM2_CH1"),
                AltFunction(function="USART2_CTS"),
                AltFunction(function="NEW_FUNCTION"),
            ],
        )
        imported = self._make_profile(pins=[new_pin] + existing.pinout.pins[1:])
        report = diff_profiles(imported, existing)
        assert report.alt_functions_added == 1

    def test_alt_function_removed(self):
        from shared.knowledge.importers.profile_diff import diff_profiles
        from shared.knowledge.mcu_profile_schema import PinDefinition, PinType, AltFunction
        existing = self._make_profile()
        # PA0 with only one alt function (missing USART2_CTS)
        reduced_pin = PinDefinition(
            pin_name="PA0", pin_number="10", pin_type=PinType.gpio,
            alt_functions=[AltFunction(function="TIM2_CH1")],
        )
        imported = self._make_profile(pins=[reduced_pin] + existing.pinout.pins[1:])
        report = diff_profiles(imported, existing)
        assert report.alt_functions_removed == 1

    def test_power_domain_voltage_mismatch_is_error(self):
        from shared.knowledge.importers.profile_diff import diff_profiles, DiffSeverity
        from shared.knowledge.mcu_profile_schema import PowerDomain
        existing = self._make_profile()
        wrong_domain = [PowerDomain(
            name="VDD", nominal_voltage=1.8,  # Wrong voltage!
            allowed_range=(1.7, 1.9), max_current_draw_ma=100,
        )]
        imported = self._make_profile(domains=wrong_domain)
        report = diff_profiles(imported, existing)
        assert report.has_errors
        errors = [e for e in report.entries if e.severity == DiffSeverity.error]
        assert len(errors) >= 1

    def test_match_score(self):
        from shared.knowledge.importers.profile_diff import diff_profiles
        p = self._make_profile()
        report = diff_profiles(p, p)
        assert report.match_score == 1.0

    def test_summary_text(self):
        from shared.knowledge.importers.profile_diff import diff_profiles
        p = self._make_profile()
        report = diff_profiles(p, p)
        assert "3 pins match" in report.summary

    def test_validate_import_new_profile(self):
        from shared.knowledge.importers.profile_diff import validate_import
        p = self._make_profile()
        ok, reason = validate_import(p)
        assert ok is True
        assert "New profile" in reason

    def test_validate_import_missing_mpn(self):
        from shared.knowledge.importers.profile_diff import validate_import
        p = self._make_profile(mpn="")
        ok, reason = validate_import(p)
        assert ok is False
        assert "MPN" in reason

    def test_validate_import_against_existing(self):
        from shared.knowledge.importers.profile_diff import validate_import
        p = self._make_profile()
        ok, reason = validate_import(p, p)
        assert ok is True


# ===================================================================
# Integration: Cross-validate imported vs existing hand-curated
# ===================================================================

class TestCrossValidation:
    def test_cubemx_vs_existing_stm32g431(self):
        """Cross-validate CubeMX import against hand-curated STM32G431 profile."""
        from shared.knowledge.importers.cubemx_parser import parse_cubemx_xml_string
        from shared.knowledge.importers.profile_diff import diff_profiles

        imported = parse_cubemx_xml_string(CUBEMX_SAMPLE_XML)

        # Load existing hand-curated profile
        from shared.knowledge.mcu_profiles import get as get_profile
        existing = get_profile("STM32G431CBU6")
        if existing is None:
            pytest.skip("Hand-curated STM32G431CBU6 profile not available")

        report = diff_profiles(imported, existing)
        # The imported sample is small (16 pins), so lots of existing pins won't match
        # But the ones that are there should be structurally valid
        assert report.pins_matching + report.pins_differing > 0

    def test_pico_import_matches_existing(self):
        """Cross-validate Pico SDK import against hand-curated RP2040 profile."""
        from shared.knowledge.importers.picosdk_parser import parse_picosdk_from_table
        from shared.knowledge.importers.profile_diff import diff_profiles

        imported = parse_picosdk_from_table()

        from shared.knowledge.mcu_profiles import get as get_profile
        existing = get_profile("RP2040")
        if existing is None:
            pytest.skip("Hand-curated RP2040 profile not available")

        report = diff_profiles(imported, existing)
        # Pins with same names should be found (may differ in alt functions)
        assert report.pins_matching + report.pins_differing >= 20
