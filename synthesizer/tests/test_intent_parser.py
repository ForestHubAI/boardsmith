# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Boardsmith intent parser (rule-based mode)."""
import pytest
from boardsmith_hw.intent_parser import IntentParser


@pytest.fixture
def parser():
    return IntentParser(use_llm=False)


def test_temperature_humidity_pressure(parser):
    spec = parser.parse("I want to measure temperature, humidity and pressure with a BME280 on ESP32 over I2C")
    assert "temperature" in spec.sensing_modalities
    assert "humidity" in spec.sensing_modalities
    assert "pressure" in spec.sensing_modalities
    assert "I2C" in spec.required_interfaces
    assert spec.mcu_family == "esp32"


def test_motion_imu(parser):
    spec = parser.parse("Use an MPU-6050 IMU to measure accelerometer and gyroscope data")
    assert "motion" in spec.sensing_modalities


def test_distance_sensor(parser):
    spec = parser.parse("I need a ToF distance sensor to detect objects")
    assert "distance" in spec.sensing_modalities


def test_default_mcu_fallback(parser):
    spec = parser.parse("Measure temperature")
    assert spec.mcu_family is not None  # Should default to esp32


def test_esp32_detected(parser):
    spec = parser.parse("ESP32 board with I2C sensors")
    assert spec.mcu_family == "esp32"


def test_unresolved_when_no_sensing(parser):
    spec = parser.parse("Build me a circuit")
    assert len(spec.unresolved) > 0


def test_voltage_33v_detected(parser):
    spec = parser.parse("3.3V sensor board with I2C")
    assert spec.supply_voltage == 3.3


def test_i2c_default_for_sensors(parser):
    spec = parser.parse("Read temperature from a sensor")
    assert "I2C" in spec.required_interfaces


# --- Explicit MPN detection ---

def test_explicit_mpn_bme280_detected(parser):
    spec = parser.parse("ESP32 with BME280 sensor")
    assert "BME280" in spec.sensor_mpns


def test_explicit_mpn_mpu6050_canonical(parser):
    """Both 'MPU-6050' and 'MPU6050' forms should produce one canonical entry."""
    spec = parser.parse("board with MPU-6050 and MPU6050")
    assert spec.sensor_mpns.count("MPU-6050") == 1


def test_explicit_mpn_multiple(parser):
    spec = parser.parse("ESP32 with BME280, VL53L0X and INA226")
    assert "BME280" in spec.sensor_mpns
    assert "VL53L0X" in spec.sensor_mpns
    assert "INA226" in spec.sensor_mpns


def test_rp2040_family_detection(parser):
    spec = parser.parse("Raspberry Pi Pico RP2040 project")
    assert spec.mcu_family == "rp2040"


def test_nrf52_family_detection(parser):
    spec = parser.parse("nRF52840 BLE sensor node")
    assert spec.mcu_family == "nrf52"


def test_i2c_default_added_for_explicit_mpn(parser):
    """Explicit sensor MPN alone (without modality keyword) should still default to I2C."""
    spec = parser.parse("ESP32 with SHTC3")
    assert "I2C" in spec.required_interfaces


# --- MCU mismatch regression tests (quick-3) ---

def test_atmega328p_detected(parser):
    """ATmega328P prompt must map to 'atmega' family, not the default 'esp32'."""
    spec = parser.parse("ATmega328P Board mit MPU6050 und 2 Status LEDs, 16 MHz Quarz")
    assert spec.mcu_family == "atmega", f"Expected 'atmega', got '{spec.mcu_family}'"


def test_atmega2560_detected(parser):
    """ATmega2560 prompt must map to 'mega' family."""
    spec = parser.parse("ATmega2560 mit MAX7219 LED Matrix Treiber")
    assert spec.mcu_family == "mega", f"Expected 'mega', got '{spec.mcu_family}'"


def test_stm32g431_detected(parser):
    """STM32G431 prompt must map to 'stm32g4' family."""
    spec = parser.parse("STM32G431 Board mit MCP9808")
    assert spec.mcu_family == "stm32g4", f"Expected 'stm32g4', got '{spec.mcu_family}'"
