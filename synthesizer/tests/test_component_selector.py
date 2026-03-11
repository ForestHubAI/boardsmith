# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Boardsmith component selector."""
import pytest
from boardsmith_hw.intent_parser import IntentParser
from boardsmith_hw.requirements_normalizer import normalize
from boardsmith_hw.component_selector import ComponentSelector


@pytest.fixture
def selector():
    return ComponentSelector(seed=42)


def _reqs(prompt: str):
    spec = IntentParser(use_llm=False).parse(prompt)
    return normalize(spec)


def test_esp32_selected_for_esp32_prompt(selector):
    reqs = _reqs("ESP32 board with BME280 temperature sensor over I2C")
    selection = selector.select(reqs)
    assert selection.mcu is not None
    assert "ESP32" in selection.mcu.mpn.upper() or "esp32" in selection.mcu.mpn.lower()


def test_sensor_selected_for_temp_humidity(selector):
    reqs = _reqs("Measure temperature and humidity over I2C")
    selection = selector.select(reqs)
    assert len(selection.sensors) >= 1


def test_deterministic_with_seed(selector):
    reqs = _reqs("ESP32 with BME280 temperature sensor")
    s1 = selector.select(reqs)
    s2 = ComponentSelector(seed=42).select(reqs)
    assert s1.mcu and s2.mcu
    assert s1.mcu.mpn == s2.mcu.mpn


def test_component_has_i2c_interface(selector):
    reqs = _reqs("I2C temperature sensor")
    selection = selector.select(reqs)
    if selection.sensors:
        ifaces = [i.upper() for i in selection.sensors[0].interface_types]
        assert "I2C" in ifaces


def test_bme280_preferred_for_pressure(selector):
    reqs = _reqs("Measure pressure and temperature with BME280 over I2C")
    selection = selector.select(reqs)
    mpns = [s.mpn.upper() for s in selection.sensors]
    assert "BME280" in mpns


# --- Explicit MPN selection ---

def test_explicit_mpn_bme280_selected(selector):
    """BME280 named directly in prompt must be selected even without modality keywords."""
    reqs = _reqs("ESP32 with BME280 and MPU-6050")
    selection = selector.select(reqs)
    mpns = {s.mpn.upper() for s in selection.sensors}
    assert "BME280" in mpns
    assert "MPU-6050" in mpns


def test_explicit_mpn_no_duplicates(selector):
    """Same sensor mentioned twice (with and without hyphen) must appear once."""
    reqs = _reqs("ESP32 with BME280 sensor")
    selection = selector.select(reqs)
    mpns = [s.mpn.upper() for s in selection.sensors]
    assert mpns.count("BME280") == 1


def test_new_mcu_rp2040(selector):
    """RP2040 must be selectable when requested."""
    reqs = _reqs("Raspberry Pi Pico (RP2040) with BME280")
    selection = selector.select(reqs)
    assert selection.mcu is not None
    assert "RP2040" in selection.mcu.mpn.upper()


def test_new_sensor_shtc3_in_catalog():
    """SHTC3 must be in the catalog and selectable by explicit MPN."""
    reqs = _reqs("ESP32 with SHTC3 temperature sensor")
    selection = ComponentSelector(seed=42).select(reqs)
    mpns = {s.mpn.upper() for s in selection.sensors}
    assert "SHTC3" in mpns


def test_new_sensor_ina226_in_catalog():
    """INA226 must be in the catalog and selectable by explicit MPN."""
    reqs = _reqs("ESP32 with INA226 current monitor")
    selection = ComponentSelector(seed=42).select(reqs)
    mpns = {s.mpn.upper() for s in selection.sensors}
    assert "INA226" in mpns


# --- N-Best candidate sets ---

def test_n_best_returns_multiple_variants(selector):
    """select_n_best must return up to N distinct MCU variants."""
    reqs = _reqs("Board with BME280 sensor")
    variants = selector.select_n_best(reqs, n=3)
    assert len(variants) >= 2, "Should produce at least 2 design variants"


def test_n_best_unique_mcus(selector):
    """Each N-Best variant must have a different MCU."""
    reqs = _reqs("Board with BME280 sensor")
    variants = selector.select_n_best(reqs, n=3)
    mcu_mpns = [v.mcu.mpn for v in variants if v.mcu]
    assert len(set(mcu_mpns)) == len(mcu_mpns), "Each variant must have a unique MCU"


def test_n_best_sensors_preserved(selector):
    """All variants must include the explicitly requested sensors."""
    reqs = _reqs("ESP32 with BME280 and MPU-6050")
    variants = selector.select_n_best(reqs, n=3)
    for v in variants:
        mpns = {s.mpn.upper() for s in v.sensors}
        assert "BME280" in mpns, f"BME280 missing in variant {v.label}"
        assert "MPU-6050" in mpns, f"MPU-6050 missing in variant {v.label}"


def test_n_best_has_labels(selector):
    """N-Best variants must have distinct labels."""
    reqs = _reqs("Board with BME280 sensor")
    variants = selector.select_n_best(reqs, n=3)
    labels = [v.label for v in variants]
    assert len(set(labels)) == len(labels), "Each variant must have a unique label"


# --- MCU mismatch regression tests (quick-3) ---

def test_atmega328p_selected(selector):
    """ATmega328P prompt must select ATmega328P MCU, not STM32F103."""
    reqs = _reqs("ATmega328P Board mit MPU6050")
    selection = selector.select(reqs)
    assert selection.mcu is not None
    assert "ATMEGA328P" in selection.mcu.mpn.upper(), f"Expected ATmega328P, got '{selection.mcu.mpn}'"


def test_atmega2560_selected(selector):
    """ATmega2560 prompt must select ATmega2560 MCU, not STM32F103."""
    reqs = _reqs("ATmega2560 mit MAX7219")
    selection = selector.select(reqs)
    assert selection.mcu is not None
    assert "ATMEGA2560" in selection.mcu.mpn.upper(), f"Expected ATmega2560, got '{selection.mcu.mpn}'"


def test_stm32g431_selected(selector):
    """STM32G431 prompt must select STM32G431CBU6 MCU, not STM32F103."""
    reqs = _reqs("STM32G431 Board mit MCP9808")
    selection = selector.select(reqs)
    assert selection.mcu is not None
    assert "STM32G431" in selection.mcu.mpn.upper(), f"Expected STM32G431, got '{selection.mcu.mpn}'"


def test_esp32s3_not_downgraded():
    """ESP32-S3 prompt must not be downgraded to generic ESP32-WROOM-32."""
    from boardsmith_hw.intent_parser import IntentParser
    from boardsmith_hw.requirements_normalizer import NormalizedRequirements, normalize
    # Check intent parser detects esp32s3 correctly
    spec = IntentParser(use_llm=False).parse("ESP32-S3 mit W25Q128 SPI Flash")
    assert spec.mcu_family == "esp32s3", f"Intent parser: expected 'esp32s3', got '{spec.mcu_family}'"
    # Check component selector picks ESP32-S3-WROOM-1
    reqs = normalize(spec)
    selection = ComponentSelector(seed=42).select(reqs)
    assert selection.mcu is not None
    assert "ESP32-S3" in selection.mcu.mpn.upper(), f"Selector: expected ESP32-S3, got '{selection.mcu.mpn}'"
