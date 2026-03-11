# SPDX-License-Identifier: AGPL-3.0-or-later
"""Memory components — SPI Flash, I2C EEPROM, SPI SRAM."""

from __future__ import annotations

from boardsmith_fw.models.component_knowledge import (
    ComponentKnowledge,
    ElectricalRatings,
    InitStep,
    InterfaceType,
    RegisterInfo,
    TimingConstraint,
)


def _w25q128() -> ComponentKnowledge:
    """Winbond W25Q128 — 128Mbit SPI NOR Flash."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="W25Q128",
        manufacturer="Winbond",
        mpn="W25Q128JV",
        description="128Mbit (16MB) SPI NOR Flash memory",
        category="memory",
        interface=InterfaceType.SPI,
        spi_mode=0,
        registers=[
            RegisterInfo(address="0x9F", name="JEDEC_ID", description="Read JEDEC ID (returns EF 40 18)"),
            RegisterInfo(address="0x05", name="Status Register 1", description="Busy, WEL, block protect bits"),
            RegisterInfo(address="0x35", name="Status Register 2", description="QE, SRL, etc."),
            RegisterInfo(address="0x06", name="Write Enable", description="Set WEL bit before write/erase"),
            RegisterInfo(address="0x03", name="Read Data", description="Read data (24-bit address follows)"),
            RegisterInfo(address="0x02", name="Page Program", description="Program page (256 bytes max)"),
            RegisterInfo(address="0x20", name="Sector Erase", description="Erase 4KB sector"),
            RegisterInfo(address="0xD8", name="Block Erase 64K", description="Erase 64KB block"),
            RegisterInfo(address="0xC7", name="Chip Erase", description="Erase entire chip"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x9F", value="", description="Read JEDEC ID to verify chip (expect EF 40 18)"),
            InitStep(order=2, reg_addr="0x06", value="", description="Write Enable (WEL)"),
            InitStep(
                order=3, reg_addr="0x01", value="0x00",
                description="Write Status Register — clear block protect",
            ),
            InitStep(order=4, reg_addr="", value="", description="Wait for write complete", delay_ms=15),
        ],
        timing_constraints=[
            TimingConstraint(parameter="SPI clock frequency", max="133000000", unit="Hz"),
            TimingConstraint(parameter="Page program time", typical="0.7", max="3", unit="ms"),
            TimingConstraint(parameter="Sector erase time (4KB)", typical="45", max="400", unit="ms"),
            TimingConstraint(parameter="Block erase time (64KB)", typical="150", max="2000", unit="ms"),
            TimingConstraint(parameter="Chip erase time", typical="40", max="200", unit="s"),
        ],
        electrical_ratings=ElectricalRatings(
            vdd_min=2.7,
            vdd_max=3.6,
            vdd_abs_max=4.6,
            current_supply_ma=4.0,      # typical active read current
            current_supply_max_ma=25.0,  # max during page program
            temp_min_c=-40.0,
            temp_max_c=85.0,
            is_5v_tolerant=False,
        ),
        notes=[
            "Page size: 256 bytes, Sector size: 4KB, Block size: 64KB",
            "Total capacity: 16MB (128Mbit)",
            "Must send Write Enable (0x06) before every write/erase operation",
            "Poll Status Register 1 bit 0 (BUSY) after write/erase",
        ],
    )


def _at24c256() -> ComponentKnowledge:
    """Atmel/Microchip AT24C256 — 256Kbit I2C EEPROM."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="AT24C256",
        manufacturer="Microchip",
        mpn="AT24C256",
        description="256Kbit (32KB) I2C serial EEPROM",
        category="memory",
        interface=InterfaceType.I2C,
        i2c_address="0x50",
        registers=[
            RegisterInfo(address="0x0000", name="DATA", description="EEPROM data (address 0x0000-0x7FFF)"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x0000", value="", description="Read first byte to verify communication"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="1000000", unit="Hz"),
            TimingConstraint(parameter="Page write time", max="5", unit="ms"),
            TimingConstraint(parameter="Supply current (read)", typical="1", unit="mA"),
            TimingConstraint(parameter="Supply current (write)", typical="3", unit="mA"),
        ],
        notes=[
            "I2C address 0x50-0x53 (A0, A1 pins, A2 often used for WP on some variants)",
            "Page size: 64 bytes, total 32KB",
            "2-byte address for all read/write operations",
            "Must wait for write cycle (5ms max) or poll for ACK",
            "Write protection via WP pin (active low on some packages)",
        ],
    )


def _at24c32() -> ComponentKnowledge:
    """Atmel/Microchip AT24C32 — 32Kbit I2C EEPROM."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="AT24C32",
        manufacturer="Microchip",
        mpn="AT24C32",
        description="32Kbit (4KB) I2C serial EEPROM",
        category="memory",
        interface=InterfaceType.I2C,
        i2c_address="0x57",
        registers=[
            RegisterInfo(address="0x0000", name="DATA", description="EEPROM data (address 0x0000-0x0FFF)"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x0000", value="", description="Read first byte to verify communication"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="Page write time", max="10", unit="ms"),
            TimingConstraint(parameter="Supply current (read)", typical="1", unit="mA"),
        ],
        notes=[
            "I2C address 0x50-0x57 (A0-A2 pins), 0x57 common with DS3231 RTC modules",
            "Page size: 32 bytes, total 4KB",
            "2-byte address (even though <256 pages)",
            "Often paired with DS3231 RTC on breakout boards",
        ],
    )


def _spi_sram_23lc1024() -> ComponentKnowledge:
    """Microchip 23LC1024 — 1Mbit SPI SRAM."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="23LC1024",
        manufacturer="Microchip",
        mpn="23LC1024",
        description="1Mbit (128KB) SPI serial SRAM",
        category="memory",
        interface=InterfaceType.SPI,
        spi_mode=0,
        registers=[
            RegisterInfo(address="0x03", name="READ", description="Read data (24-bit address)"),
            RegisterInfo(address="0x02", name="WRITE", description="Write data (24-bit address)"),
            RegisterInfo(address="0x05", name="RDMR", description="Read mode register"),
            RegisterInfo(address="0x01", name="WRMR", description="Write mode register"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x01", value="0x00", description="Set byte mode (sequential also available)"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="SPI clock frequency", max="20000000", unit="Hz"),
            TimingConstraint(parameter="Supply current (active)", typical="3", unit="mA"),
            TimingConstraint(parameter="Supply current (standby)", typical="4", unit="uA"),
        ],
        notes=[
            "No write cycle delay — SRAM is instant read/write",
            "3 modes: byte (0x00), page (0x80), sequential (0x40)",
            "24-bit address (0x00000-0x1FFFF for 128KB)",
            "Unlimited write endurance (volatile — loses data on power off)",
        ],
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTRY: dict[str, callable] = {
    "W25Q128": _w25q128,
    "W25Q128JV": _w25q128,
    "W25Q64": _w25q128,  # same command set, different capacity
    "W25Q32": _w25q128,
    "W25Q16": _w25q128,
    "W25Q256": _w25q128,  # same command set, 4-byte address mode available
    "AT24C256": _at24c256,
    "AT24C256C": _at24c256,
    "AT24C128": _at24c256,  # same interface, smaller capacity
    "AT24C512": _at24c256,  # same interface, larger capacity
    "AT24C32": _at24c32,
    "AT24C64": _at24c32,  # same page size, larger
    "24LC32": _at24c32,  # Microchip branding
    "24LC256": _at24c256,
    "23LC1024": _spi_sram_23lc1024,
    "23LC512": _spi_sram_23lc1024,  # smaller, same interface
    "23K256": _spi_sram_23lc1024,
}
