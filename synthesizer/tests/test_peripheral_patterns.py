# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the Peripheral Pattern Library."""
import pytest

from boardsmith_hw.peripheral_patterns import (
    i2c_pullup_value,
    i2c_pullup_from_profile,
    spi_passives_from_profile,
    uart_passives_from_profile,
    can_passives_from_profile,
    usb_passives_from_profile,
    synthesize_bus_pattern_passives,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeBus:
    def __init__(self, name, bus_type, pin_assignments):
        self.name = name
        self.bus_type = bus_type
        self.pin_assignments = pin_assignments


def make_uid():
    counter = {}
    def uid(prefix):
        counter[prefix] = counter.get(prefix, 0) + 1
        return f"T_{prefix}{counter[prefix]}"
    return uid


# ---------------------------------------------------------------------------
# I2C Pullup Tests
# ---------------------------------------------------------------------------

class TestI2CPullup:
    def test_standard_mode(self):
        assert i2c_pullup_value(100_000) == "10k"

    def test_fast_mode(self):
        assert i2c_pullup_value(400_000) == "4.7k"

    def test_fast_mode_plus(self):
        assert i2c_pullup_value(1_000_000) == "2.2k"

    def test_high_capacitance_lowers_value(self):
        # At 400kHz with 200pF bus, needs lower resistor
        val = i2c_pullup_value(400_000, bus_cap_pf=200.0)
        assert val in ("1k", "2.2k")

    def test_no_profile(self):
        assert i2c_pullup_from_profile(None) == "4.7k"


# ---------------------------------------------------------------------------
# SPI Pattern Tests
# ---------------------------------------------------------------------------

class TestSPIPattern:
    def test_generates_sck_series_resistor(self):
        bus = FakeBus("spi0", "SPI", {"MOSI": "11", "MISO": "13", "SCK": "12"})
        passives = spi_passives_from_profile(None, bus, "3V3", make_uid())
        sck = [p for p in passives if "sck_series" in p.purpose]
        assert len(sck) == 1
        assert sck[0].value == "33"

    def test_generates_cs_pullup(self):
        bus = FakeBus("spi0", "SPI", {
            "MOSI": "11", "SCK": "12",
            "CS_DEV1": "5", "CS_DEV2": "15",
        })
        passives = spi_passives_from_profile(None, bus, "3V3", make_uid())
        cs_pullups = [p for p in passives if "cs_pullup" in p.purpose]
        assert len(cs_pullups) == 2

    def test_no_cs_no_pullup(self):
        bus = FakeBus("spi0", "SPI", {"MOSI": "11", "MISO": "13", "SCK": "12"})
        passives = spi_passives_from_profile(None, bus, "3V3", make_uid())
        cs_pullups = [p for p in passives if "cs_pullup" in p.purpose]
        assert len(cs_pullups) == 0


# ---------------------------------------------------------------------------
# UART Pattern Tests
# ---------------------------------------------------------------------------

class TestUARTPattern:
    def test_generates_tx_rx_series(self):
        bus = FakeBus("uart0", "UART", {"TX": "17", "RX": "16"})
        passives = uart_passives_from_profile(None, bus, make_uid())
        assert len(passives) == 2
        assert any("tx_series" in p.purpose for p in passives)
        assert any("rx_series" in p.purpose for p in passives)
        assert passives[0].value == "470"

    def test_tx_only(self):
        bus = FakeBus("uart0", "UART", {"TX": "17"})
        passives = uart_passives_from_profile(None, bus, make_uid())
        assert len(passives) == 1


# ---------------------------------------------------------------------------
# CAN Pattern Tests
# ---------------------------------------------------------------------------

class TestCANPattern:
    def test_generates_termination(self):
        bus = FakeBus("can0", "CAN", {"TX": "PA12", "RX": "PA11"})
        passives = can_passives_from_profile(None, bus, make_uid())
        assert len(passives) == 1
        assert passives[0].value == "120"
        assert "termination" in passives[0].purpose


# ---------------------------------------------------------------------------
# USB Pattern Tests
# ---------------------------------------------------------------------------

class TestUSBPattern:
    def test_generates_dp_dm_series_and_esd(self):
        bus = FakeBus("usb0", "USB", {"DP": "20", "DM": "19"})
        passives = usb_passives_from_profile(None, bus, make_uid())
        assert len(passives) == 3
        dp = [p for p in passives if "dp_series" in p.purpose]
        dm = [p for p in passives if "dm_series" in p.purpose]
        esd = [p for p in passives if "esd" in p.purpose]
        assert len(dp) == 1 and dp[0].value == "27"
        assert len(dm) == 1 and dm[0].value == "27"
        assert len(esd) == 1 and esd[0].value == "USBLC6-2SC6"


# ---------------------------------------------------------------------------
# Master Dispatcher Tests
# ---------------------------------------------------------------------------

class TestSynthesizeBusPatterns:
    def test_spi_bus_gets_patterns(self):
        buses = [FakeBus("spi0", "SPI", {"SCK": "12", "CS_DEV": "5"})]
        assumptions = []
        passives = synthesize_bus_pattern_passives(
            buses, None, "3V3", make_uid(), assumptions
        )
        assert len(passives) >= 2  # SCK series + CS pullup
        assert any("SPI pattern" in a for a in assumptions)

    def test_i2c_bus_no_extra_passives(self):
        buses = [FakeBus("i2c0", "I2C", {"SDA": "21", "SCL": "22"})]
        assumptions = []
        passives = synthesize_bus_pattern_passives(
            buses, None, "3V3", make_uid(), assumptions
        )
        # I2C pullups are handled by _synthesize_passives, not here
        assert len(passives) == 0

    def test_multiple_bus_types(self):
        buses = [
            FakeBus("spi0", "SPI", {"SCK": "12", "CS_X": "5"}),
            FakeBus("uart0", "UART", {"TX": "17", "RX": "16"}),
        ]
        assumptions = []
        passives = synthesize_bus_pattern_passives(
            buses, None, "3V3", make_uid(), assumptions
        )
        spi_parts = [p for p in passives if "spi" in p.purpose]
        uart_parts = [p for p in passives if "uart" in p.purpose]
        assert len(spi_parts) >= 2
        assert len(uart_parts) == 2
