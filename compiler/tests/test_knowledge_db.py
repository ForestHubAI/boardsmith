# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the expanded built-in knowledge database (50+ components)."""

import pytest

from boardsmith_fw.knowledge.builtin_db import (
    count_unique_components,
    list_builtin_mpns,
    list_categories,
    lookup_builtin,
)
from boardsmith_fw.models.component_knowledge import InterfaceType

# ---------------------------------------------------------------------------
# Scale & coverage tests
# ---------------------------------------------------------------------------


class TestDBScale:
    def test_at_least_100_mpn_entries(self):
        mpns = list_builtin_mpns()
        assert len(mpns) >= 100

    def test_at_least_45_unique_components(self):
        assert count_unique_components() >= 45

    def test_all_categories_populated(self):
        cats = list_categories()
        for name, count in cats.items():
            assert count >= 4, f"Category {name} has only {count} entries"

    def test_every_registry_entry_returns_valid_knowledge(self):
        for mpn in list_builtin_mpns():
            k = lookup_builtin(mpn)
            assert k is not None, f"lookup_builtin({mpn!r}) returned None"
            assert k.name, f"{mpn}: empty name"
            assert k.category != "unknown", f"{mpn}: category is unknown"


# ---------------------------------------------------------------------------
# Sensor tests
# ---------------------------------------------------------------------------


class TestSensors:
    @pytest.mark.parametrize("mpn,addr,interface", [
        ("BME280", "0x76", InterfaceType.I2C),
        ("BME680", "0x76", InterfaceType.I2C),
        ("SHT31", "0x44", InterfaceType.I2C),
        ("AHT20", "0x38", InterfaceType.I2C),
        ("MCP9808", "0x18", InterfaceType.I2C),
        ("MPU6050", "0x68", InterfaceType.I2C),
        ("ADXL345", "0x53", InterfaceType.I2C),
        ("LIS3DH", "0x18", InterfaceType.I2C),
        ("BNO055", "0x28", InterfaceType.I2C),
        ("LSM6DSO", "0x6A", InterfaceType.I2C),
        ("VL53L0X", "0x29", InterfaceType.I2C),
        ("APDS9960", "0x39", InterfaceType.I2C),
        ("TSL2561", "0x39", InterfaceType.I2C),
        ("BH1750", "0x23", InterfaceType.I2C),
        ("MAX30102", "0x57", InterfaceType.I2C),
        ("INA219", "0x40", InterfaceType.I2C),
        ("INA226", "0x40", InterfaceType.I2C),
        ("ADS1115", "0x48", InterfaceType.I2C),
    ])
    def test_i2c_sensor_address(self, mpn, addr, interface):
        k = lookup_builtin(mpn)
        assert k is not None
        assert k.i2c_address == addr
        assert k.interface == interface

    @pytest.mark.parametrize("mpn", [
        "DS18B20", "DHT22", "HX711",
    ])
    def test_gpio_sensor(self, mpn):
        k = lookup_builtin(mpn)
        assert k is not None
        assert k.interface == InterfaceType.GPIO

    def test_bme680_has_gas_registers(self):
        k = lookup_builtin("BME680")
        reg_names = {r.name for r in k.registers}
        assert "ctrl_gas_1" in reg_names
        assert "gas_r_msb" in reg_names

    def test_mpu6050_who_am_i(self):
        k = lookup_builtin("MPU6050")
        who = next(r for r in k.registers if r.name == "WHO_AM_I")
        assert who.address == "0x75"

    def test_ads1115_config_fields(self):
        k = lookup_builtin("ADS1115")
        config = next(r for r in k.registers if r.name == "CONFIG")
        field_names = {f.name for f in config.fields}
        assert "MUX" in field_names
        assert "PGA" in field_names


# ---------------------------------------------------------------------------
# Display tests
# ---------------------------------------------------------------------------


class TestDisplays:
    @pytest.mark.parametrize("mpn", [
        "SSD1306", "SH1106", "HT16K33",
    ])
    def test_i2c_display(self, mpn):
        k = lookup_builtin(mpn)
        assert k is not None
        assert k.interface == InterfaceType.I2C
        assert k.category == "display"

    @pytest.mark.parametrize("mpn", [
        "ST7735", "ST7789", "ILI9341", "MAX7219",
    ])
    def test_spi_display(self, mpn):
        k = lookup_builtin(mpn)
        assert k is not None
        assert k.interface == InterfaceType.SPI

    def test_ssd1306_has_full_init(self):
        k = lookup_builtin("SSD1306")
        assert len(k.init_sequence) >= 10
        # Must turn on charge pump
        descs = [s.description.lower() for s in k.init_sequence]
        assert any("charge pump" in d for d in descs)
        # Must end with display ON
        assert any("display on" in d for d in descs)

    def test_max7219_digit_registers(self):
        k = lookup_builtin("MAX7219")
        reg_names = {r.name for r in k.registers}
        assert "DIGIT_0" in reg_names
        assert "SHUTDOWN" in reg_names
        assert "INTENSITY" in reg_names


# ---------------------------------------------------------------------------
# Communication tests
# ---------------------------------------------------------------------------


class TestComms:
    def test_sx1276_lora_registers(self):
        k = lookup_builtin("SX1276")
        assert k is not None
        assert k.interface == InterfaceType.SPI
        reg_names = {r.name for r in k.registers}
        assert "RegOpMode" in reg_names
        assert "RegVersion" in reg_names

    def test_rfm95w_is_sx1276(self):
        rfm = lookup_builtin("RFM95W")
        sx = lookup_builtin("SX1276")
        assert rfm is not None
        assert rfm.name == sx.name

    def test_nrf24l01_config(self):
        k = lookup_builtin("NRF24L01")
        assert k is not None
        config = next(r for r in k.registers if r.name == "CONFIG")
        field_names = {f.name for f in config.fields}
        assert "PWR_UP" in field_names
        assert "PRIM_RX" in field_names

    def test_mcp2515_can_controller(self):
        k = lookup_builtin("MCP2515")
        assert k is not None
        assert k.category == "can_controller"
        assert len(k.init_sequence) >= 5

    def test_w5500_hardwired_tcp(self):
        k = lookup_builtin("W5500")
        assert k is not None
        reg_names = {r.name for r in k.registers}
        assert "VERSIONR" in reg_names


# ---------------------------------------------------------------------------
# Memory tests
# ---------------------------------------------------------------------------


class TestMemory:
    def test_w25q128_spi_flash(self):
        k = lookup_builtin("W25Q128")
        assert k.interface == InterfaceType.SPI
        assert k.spi_mode == 0

    def test_at24c256_eeprom(self):
        k = lookup_builtin("AT24C256")
        assert k is not None
        assert k.interface == InterfaceType.I2C
        assert k.i2c_address == "0x50"

    def test_spi_sram_23lc1024(self):
        k = lookup_builtin("23LC1024")
        assert k is not None
        assert k.interface == InterfaceType.SPI
        assert k.category == "memory"

    def test_prefix_match_w25q128jvsiq(self):
        k = lookup_builtin("W25Q128JVSIQ")
        assert k is not None
        assert k.name == "W25Q128"


# ---------------------------------------------------------------------------
# Motor / Power tests
# ---------------------------------------------------------------------------


class TestMotorPower:
    def test_drv8825_stepper(self):
        k = lookup_builtin("DRV8825")
        assert k is not None
        assert k.interface == InterfaceType.GPIO
        assert k.category == "motor_driver"
        assert len(k.timing_constraints) >= 3

    def test_pca9685_pwm_driver(self):
        k = lookup_builtin("PCA9685")
        assert k is not None
        assert k.interface == InterfaceType.I2C
        assert k.i2c_address == "0x40"
        # Must have prescaler register
        reg_names = {r.name for r in k.registers}
        assert "PRE_SCALE" in reg_names


# ---------------------------------------------------------------------------
# Misc tests
# ---------------------------------------------------------------------------


class TestMisc:
    def test_ds3231_rtc(self):
        k = lookup_builtin("DS3231")
        assert k is not None
        assert k.interface == InterfaceType.I2C
        assert k.i2c_address == "0x68"
        assert k.category == "rtc"
        # Must have time registers
        reg_names = {r.name for r in k.registers}
        assert "SECONDS" in reg_names
        assert "CONTROL" in reg_names

    def test_mcp23017_io_expander(self):
        k = lookup_builtin("MCP23017")
        assert k is not None
        assert k.i2c_address == "0x20"
        reg_names = {r.name for r in k.registers}
        assert "GPIOA" in reg_names
        assert "GPIOB" in reg_names

    def test_mcp4725_dac(self):
        k = lookup_builtin("MCP4725")
        assert k is not None
        assert k.category == "dac"

    def test_tca9548a_i2c_mux(self):
        k = lookup_builtin("TCA9548A")
        assert k is not None
        assert k.category == "i2c_mux"
        assert k.i2c_address == "0x70"


# ---------------------------------------------------------------------------
# Data quality tests
# ---------------------------------------------------------------------------


class TestDataQuality:
    def test_all_components_have_init_sequence(self):
        """Every component (except pure GPIO) should have init steps."""
        seen = set()
        for mpn in list_builtin_mpns():
            k = lookup_builtin(mpn)
            if k.name in seen:
                continue
            seen.add(k.name)
            assert len(k.init_sequence) >= 1, (
                f"{k.name}: missing init_sequence"
            )

    def test_all_components_have_timing(self):
        """Every component should have at least one timing constraint."""
        seen = set()
        for mpn in list_builtin_mpns():
            k = lookup_builtin(mpn)
            if k.name in seen:
                continue
            seen.add(k.name)
            assert len(k.timing_constraints) >= 1, (
                f"{k.name}: missing timing_constraints"
            )

    def test_i2c_components_have_address(self):
        """Every I2C component must have an i2c_address."""
        seen = set()
        for mpn in list_builtin_mpns():
            k = lookup_builtin(mpn)
            if k.name in seen:
                continue
            seen.add(k.name)
            if k.interface == InterfaceType.I2C:
                assert k.i2c_address, f"{k.name}: I2C but no address"
                assert k.i2c_address.startswith("0x"), (
                    f"{k.name}: address should start with 0x"
                )

    def test_spi_components_have_spi_mode(self):
        """SPI components should have spi_mode set."""
        seen = set()
        for mpn in list_builtin_mpns():
            k = lookup_builtin(mpn)
            if k.name in seen:
                continue
            seen.add(k.name)
            if k.interface == InterfaceType.SPI:
                assert k.spi_mode is not None, (
                    f"{k.name}: SPI but no spi_mode"
                )

    def test_no_duplicate_register_addresses_per_component(self):
        """Within one component, register addresses should be unique."""
        seen = set()
        for mpn in list_builtin_mpns():
            k = lookup_builtin(mpn)
            if k.name in seen:
                continue
            seen.add(k.name)
            if not k.registers:
                continue
            # Some components use same address for different commands (e.g. SPI Flash)
            # but shouldn't have exact same addr+name combo
            pairs = [(r.address, r.name) for r in k.registers]
            assert len(pairs) == len(set(pairs)), (
                f"{k.name}: duplicate register addr+name"
            )
