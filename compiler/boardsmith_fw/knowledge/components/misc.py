# SPDX-License-Identifier: AGPL-3.0-or-later
"""Miscellaneous components — RTC, GPIO expanders, DAC, I2C mux."""

from __future__ import annotations

from boardsmith_fw.models.component_knowledge import (
    ComponentKnowledge,
    InitStep,
    InterfaceType,
    RegisterField,
    RegisterInfo,
    TimingConstraint,
)

# ---------------------------------------------------------------------------
# Real-Time Clocks
# ---------------------------------------------------------------------------

def _ds3231() -> ComponentKnowledge:
    """Maxim DS3231 — Extremely accurate I2C RTC with TCXO."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="DS3231",
        manufacturer="Maxim Integrated",
        mpn="DS3231",
        description="Extremely accurate I2C-integrated RTC/TCXO/Crystal, +/- 2ppm",
        category="rtc",
        interface=InterfaceType.I2C,
        i2c_address="0x68",
        registers=[
            RegisterInfo(address="0x00", name="SECONDS", description="Seconds (BCD, 00-59)"),
            RegisterInfo(address="0x01", name="MINUTES", description="Minutes (BCD, 00-59)"),
            RegisterInfo(address="0x02", name="HOURS", description="Hours (BCD, 1-12+AM/PM or 00-23)"),
            RegisterInfo(address="0x03", name="DAY", description="Day of week (1-7)"),
            RegisterInfo(address="0x04", name="DATE", description="Date (BCD, 01-31)"),
            RegisterInfo(address="0x05", name="MONTH_CENTURY", description="Month (BCD) + century bit"),
            RegisterInfo(address="0x06", name="YEAR", description="Year (BCD, 00-99)"),
            RegisterInfo(address="0x07", name="ALARM1_SECONDS", description="Alarm 1 seconds"),
            RegisterInfo(address="0x0B", name="ALARM2_MINUTES", description="Alarm 2 minutes"),
            RegisterInfo(address="0x0E", name="CONTROL", description="Control register",
                         fields=[
                             RegisterField(name="EOSC", bits="7", description="Enable oscillator (active low)"),
                             RegisterField(name="BBSQW", bits="6", description="Battery-backed square wave"),
                             RegisterField(name="CONV", bits="5", description="Convert temperature"),
                             RegisterField(name="INTCN", bits="2", description="Interrupt control"),
                             RegisterField(name="A2IE", bits="1", description="Alarm 2 interrupt enable"),
                             RegisterField(name="A1IE", bits="0", description="Alarm 1 interrupt enable"),
                         ]),
            RegisterInfo(address="0x0F", name="STATUS", description="Status register",
                         fields=[
                             RegisterField(name="OSF", bits="7", description="Oscillator stop flag"),
                             RegisterField(name="BSY", bits="2", description="Busy (temp conversion)"),
                             RegisterField(name="A2F", bits="1", description="Alarm 2 flag"),
                             RegisterField(name="A1F", bits="0", description="Alarm 1 flag"),
                         ]),
            RegisterInfo(address="0x11", name="TEMP_MSB", description="Temperature integer part"),
            RegisterInfo(address="0x12", name="TEMP_LSB", description="Temperature fraction (0.25C resolution)"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x0F", value="", description="Read status — check OSF (oscillator stop flag)"),
            InitStep(order=2, reg_addr="0x0E", value="0x00", description="Enable oscillator, disable alarms/SQW"),
            InitStep(order=3, reg_addr="0x0F", value="0x00", description="Clear OSF and alarm flags"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="Supply current (active)", typical="200", unit="uA"),
            TimingConstraint(parameter="Supply current (battery)", typical="3", unit="uA"),
            TimingConstraint(parameter="Temperature conversion time", typical="125", unit="ms"),
        ],
        notes=[
            "Fixed I2C address 0x68",
            "BCD encoding for all time registers",
            "Built-in temperature-compensated crystal: +/- 2ppm (0 to 40C)",
            "Battery backup: CR2032 on VBAT pin, auto-switchover",
            "32kHz output and SQW/INT output pins",
        ],
    )


def _pcf8563() -> ComponentKnowledge:
    """NXP PCF8563 — Low-power I2C RTC."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="PCF8563",
        manufacturer="NXP",
        mpn="PCF8563",
        description="Real-time clock/calendar with low power consumption",
        category="rtc",
        interface=InterfaceType.I2C,
        i2c_address="0x51",
        registers=[
            RegisterInfo(address="0x00", name="CONTROL_1", description="Control/status 1 (TEST1, STOP, etc.)"),
            RegisterInfo(address="0x01", name="CONTROL_2", description="Control/status 2 (TI/TP, alarm flags)"),
            RegisterInfo(address="0x02", name="VL_SECONDS", description="Seconds + VL (voltage low) flag"),
            RegisterInfo(address="0x03", name="MINUTES", description="Minutes (BCD)"),
            RegisterInfo(address="0x04", name="HOURS", description="Hours (BCD, 24h format)"),
            RegisterInfo(address="0x05", name="DAYS", description="Days (BCD)"),
            RegisterInfo(address="0x06", name="WEEKDAYS", description="Weekdays (0-6)"),
            RegisterInfo(address="0x07", name="MONTHS", description="Months + century (BCD)"),
            RegisterInfo(address="0x08", name="YEARS", description="Years (BCD, 00-99)"),
            RegisterInfo(address="0x09", name="MINUTE_ALARM", description="Minute alarm"),
            RegisterInfo(address="0x0C", name="CLKOUT_CONTROL", description="CLKOUT frequency control"),
            RegisterInfo(address="0x0D", name="TIMER_CONTROL", description="Timer control"),
            RegisterInfo(address="0x0E", name="TIMER", description="Timer countdown value"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x00", value="0x00", description="Normal mode (not stopped, no test)"),
            InitStep(order=2, reg_addr="0x01", value="0x00", description="Disable alarms and timer interrupts"),
            InitStep(order=3, reg_addr="0x0C", value="0x00", description="Disable CLKOUT"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="Supply current (active)", typical="250", unit="nA"),
            TimingConstraint(parameter="Supply current (battery backup)", typical="150", unit="nA"),
        ],
        notes=[
            "Fixed I2C address 0x51",
            "BCD encoding for all time registers",
            "VL flag in seconds register: set when voltage drops below threshold",
            "Ultra-low power: 250nA typical, ideal for battery-backed applications",
            "INT pin for alarm and timer output",
        ],
    )


# ---------------------------------------------------------------------------
# GPIO Expanders
# ---------------------------------------------------------------------------

def _mcp23017() -> ComponentKnowledge:
    """Microchip MCP23017 — 16-bit I/O expander (I2C)."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="MCP23017",
        manufacturer="Microchip",
        mpn="MCP23017",
        description="16-bit I/O expander with I2C interface (2 ports of 8 bits)",
        category="io_expander",
        interface=InterfaceType.I2C,
        i2c_address="0x20",
        registers=[
            RegisterInfo(address="0x00", name="IODIRA", description="Port A direction (1=input, 0=output)"),
            RegisterInfo(address="0x01", name="IODIRB", description="Port B direction"),
            RegisterInfo(address="0x02", name="IPOLA", description="Port A input polarity"),
            RegisterInfo(address="0x04", name="GPINTENA", description="Port A interrupt-on-change enable"),
            RegisterInfo(address="0x06", name="DEFVALA", description="Port A default compare value"),
            RegisterInfo(address="0x08", name="INTCONA", description="Port A interrupt control"),
            RegisterInfo(address="0x0A", name="IOCON", description="I/O control register",
                         fields=[
                             RegisterField(name="BANK", bits="7", description="Bank addressing mode"),
                             RegisterField(name="MIRROR", bits="6", description="INT pin mirror"),
                             RegisterField(name="SEQOP", bits="5", description="Sequential operation mode"),
                             RegisterField(name="ODR", bits="2", description="INT pin open-drain"),
                         ]),
            RegisterInfo(address="0x0C", name="GPPUA", description="Port A pull-up resistors (100k)"),
            RegisterInfo(address="0x0D", name="GPPUB", description="Port B pull-up resistors"),
            RegisterInfo(address="0x12", name="GPIOA", description="Port A pin values"),
            RegisterInfo(address="0x13", name="GPIOB", description="Port B pin values"),
            RegisterInfo(address="0x14", name="OLATA", description="Port A output latch"),
            RegisterInfo(address="0x15", name="OLATB", description="Port B output latch"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x0A", value="0x20", description="IOCON: sequential operation disabled"),
            InitStep(order=2, reg_addr="0x00", value="0xFF", description="Port A all inputs"),
            InitStep(order=3, reg_addr="0x01", value="0xFF", description="Port B all inputs"),
            InitStep(order=4, reg_addr="0x0C", value="0xFF", description="Port A pull-ups enabled"),
            InitStep(order=5, reg_addr="0x0D", value="0xFF", description="Port B pull-ups enabled"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="1700000", unit="Hz"),
            TimingConstraint(parameter="Supply current (standby)", typical="1", unit="uA"),
            TimingConstraint(parameter="Output current (per pin)", max="25", unit="mA"),
            TimingConstraint(parameter="Output current (total PORTA)", max="125", unit="mA"),
        ],
        notes=[
            "I2C address 0x20-0x27 (A0-A2 pins)",
            "16 GPIO pins in 2 ports (A and B) of 8 pins each",
            "Two interrupt outputs (INTA, INTB) can be mirrored",
            "Internal 100k pull-up resistors per pin",
            "BANK=0 (default): paired register addressing, BANK=1: separated",
        ],
    )


def _pcf8574() -> ComponentKnowledge:
    """NXP PCF8574 — 8-bit I/O expander (I2C)."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="PCF8574",
        manufacturer="NXP",
        mpn="PCF8574",
        description="Remote 8-bit I/O expander for I2C bus",
        category="io_expander",
        interface=InterfaceType.I2C,
        i2c_address="0x20",
        registers=[
            RegisterInfo(address="0x00", name="PORT", description="8-bit quasi-bidirectional I/O port"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x00", value="0xFF", description="Set all pins high (input mode)"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="100000", unit="Hz"),
            TimingConstraint(parameter="Supply current (static)", typical="2.5", unit="uA"),
            TimingConstraint(parameter="Output current (sink)", max="25", unit="mA"),
        ],
        notes=[
            "I2C address 0x20-0x27 (A0-A2 pins), PCF8574A: 0x38-0x3F",
            "Quasi-bidirectional: write 1 to read, write 0 to output low",
            "Single register — write 1 byte to set port, read 1 byte to read port",
            "INT output (active low) on any input change",
            "Commonly used as I2C backpack for HD44780 LCD displays",
        ],
    )


# ---------------------------------------------------------------------------
# DAC / Analog output
# ---------------------------------------------------------------------------

def _mcp4725() -> ComponentKnowledge:
    """Microchip MCP4725 — 12-bit DAC (I2C)."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="MCP4725",
        manufacturer="Microchip",
        mpn="MCP4725",
        description="12-bit single-channel DAC with I2C interface and EEPROM",
        category="dac",
        interface=InterfaceType.I2C,
        i2c_address="0x60",
        registers=[
            RegisterInfo(address="0x00", name="DAC_REG", description="DAC register (fast mode: 2 bytes)"),
            RegisterInfo(address="0x40", name="DAC_WRITE", description="Write DAC register (3 bytes)"),
            RegisterInfo(address="0x60", name="DAC_EEPROM", description="Write DAC register + EEPROM (3 bytes)"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x40", value="0x00,0x00", description="Set DAC output to 0V"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="3400000", unit="Hz"),
            TimingConstraint(parameter="Settling time (0 to VDD)", typical="6", unit="us"),
            TimingConstraint(parameter="EEPROM write time", max="25", unit="ms"),
            TimingConstraint(parameter="Supply current", typical="210", unit="uA"),
        ],
        notes=[
            "I2C address 0x60 or 0x61 (A0 pin), some variants 0x62/0x63",
            "Fast mode: write 2 bytes [0PPD DDDD DDDD DDDD] (P=power-down, D=12-bit data)",
            "EEPROM stores power-on default value (survives power cycle)",
            "Output voltage: V_OUT = V_DD * D / 4096",
        ],
    )


# ---------------------------------------------------------------------------
# I2C Multiplexer
# ---------------------------------------------------------------------------

def _tca9548a() -> ComponentKnowledge:
    """Texas Instruments TCA9548A — 8-channel I2C multiplexer."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="TCA9548A",
        manufacturer="Texas Instruments",
        mpn="TCA9548A",
        description="Low-voltage 8-channel I2C switch with reset",
        category="i2c_mux",
        interface=InterfaceType.I2C,
        i2c_address="0x70",
        registers=[
            RegisterInfo(address="0x00", name="CONTROL", description="Channel select (bit per channel, bit 0=ch0)"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x00", value="0x00", description="Disable all channels"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="Supply current", typical="0.3", unit="uA"),
            TimingConstraint(parameter="Switch on resistance", typical="4", unit="ohm"),
        ],
        notes=[
            "I2C address 0x70-0x77 (A0-A2 pins)",
            "8 downstream I2C buses — allows same-address devices on different channels",
            "Multiple channels can be active simultaneously (bitwise OR)",
            "RESET pin (active low) disconnects all channels",
            "Level-translating: each channel can run at different voltage",
        ],
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTRY: dict[str, callable] = {
    # RTC
    "DS3231": _ds3231,
    "DS3231M": _ds3231,
    "DS3231SN": _ds3231,
    "PCF8563": _pcf8563,
    "PCF8563T": _pcf8563,
    # GPIO Expanders
    "MCP23017": _mcp23017,
    "MCP23S17": _mcp23017,  # SPI variant, same registers
    "MCP23008": _mcp23017,  # 8-bit variant, subset of registers
    "PCF8574": _pcf8574,
    "PCF8574A": _pcf8574,
    "PCF8575": _pcf8574,  # 16-bit variant, same concept
    # DAC
    "MCP4725": _mcp4725,
    "MCP4726": _mcp4725,  # similar, with VREF options
    # I2C Mux
    "TCA9548A": _tca9548a,
    "TCA9548": _tca9548a,
    "PCA9548A": _tca9548a,  # NXP equivalent
}
