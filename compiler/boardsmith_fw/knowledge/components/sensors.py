# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sensor components — temperature, pressure, IMU, distance, light, ADC."""

from __future__ import annotations

from boardsmith_fw.models.component_knowledge import (
    ComponentKnowledge,
    ElectricalRatings,
    InitStep,
    InterfaceType,
    RegisterField,
    RegisterInfo,
    TimingConstraint,
)

# ---------------------------------------------------------------------------
# Environmental sensors
# ---------------------------------------------------------------------------

def _bme280() -> ComponentKnowledge:
    """Bosch BME280 — Temperature, Pressure, Humidity sensor (I2C/SPI)."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="BME280",
        manufacturer="Bosch Sensortec",
        mpn="BME280",
        description="Digital humidity, pressure and temperature sensor",
        category="sensor",
        interface=InterfaceType.I2C,
        i2c_address="0x76",
        spi_mode=0,
        registers=[
            RegisterInfo(address="0xD0", name="chip_id", description="Chip ID register, returns 0x60"),
            RegisterInfo(address="0xE0", name="reset", description="Soft reset, write 0xB6"),
            RegisterInfo(
                address="0xF2", name="ctrl_hum", description="Humidity oversampling",
                fields=[
                    RegisterField(name="osrs_h", bits="2:0", description="Humidity oversampling", default_value="000"),
                ],
            ),
            RegisterInfo(
                address="0xF4", name="ctrl_meas", description="Pressure/Temperature oversampling + mode",
                fields=[
                    RegisterField(
                        name="osrs_t", bits="7:5", description="Temperature oversampling",
                        default_value="001",
                    ),
                    RegisterField(name="osrs_p", bits="4:2", description="Pressure oversampling", default_value="001"),
                    RegisterField(
                        name="mode", bits="1:0",
                        description="Sensor mode (00=sleep, 01/10=forced, 11=normal)",
                        default_value="00",
                    ),
                ],
            ),
            RegisterInfo(
                address="0xF5", name="config", description="Rate, filter, SPI interface",
                fields=[
                    RegisterField(name="t_sb", bits="7:5", description="Standby time", default_value="000"),
                    RegisterField(name="filter", bits="4:2", description="IIR filter coefficient", default_value="000"),
                    RegisterField(name="spi3w_en", bits="0", description="SPI 3-wire enable", default_value="0"),
                ],
            ),
            RegisterInfo(address="0xF7", name="press_msb", description="Pressure data [19:12]"),
            RegisterInfo(address="0xF8", name="press_lsb", description="Pressure data [11:4]"),
            RegisterInfo(address="0xF9", name="press_xlsb", description="Pressure data [3:0]"),
            RegisterInfo(address="0xFA", name="temp_msb", description="Temperature data [19:12]"),
            RegisterInfo(address="0xFB", name="temp_lsb", description="Temperature data [11:4]"),
            RegisterInfo(address="0xFC", name="temp_xlsb", description="Temperature data [3:0]"),
            RegisterInfo(address="0xFD", name="hum_msb", description="Humidity data [15:8]"),
            RegisterInfo(address="0xFE", name="hum_lsb", description="Humidity data [7:0]"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0xE0", value="0xB6", description="Soft reset"),
            InitStep(order=2, reg_addr="", value="", description="Wait for reset", delay_ms=10),
            InitStep(order=3, reg_addr="0xF2", value="0x01", description="Humidity oversampling x1"),
            InitStep(order=4, reg_addr="0xF4", value="0x27", description="Temp OS x1, Press OS x1, Normal mode"),
            InitStep(order=5, reg_addr="0xF5", value="0xA0", description="Standby 1000ms, filter off"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="3400000", unit="Hz"),
            TimingConstraint(parameter="Startup time", max="2", unit="ms"),
            TimingConstraint(parameter="Measurement time (typical)", typical="8", unit="ms"),
        ],
        electrical_ratings=ElectricalRatings(
            vdd_min=1.71,
            vdd_max=3.6,
            vdd_abs_max=4.25,
            io_voltage_min=1.71,
            io_voltage_max=3.6,
            current_supply_ma=0.34,    # typical at 1 Hz weather monitoring
            current_supply_max_ma=1.8,
            temp_min_c=-40.0,
            temp_max_c=85.0,
            is_5v_tolerant=False,
        ),
        notes=[
            "I2C address is 0x76 (SDO=GND) or 0x77 (SDO=VDD)",
            "Calibration data in registers 0x88-0xA1 and 0xE1-0xE7 must be read for compensation",
            "Burst read registers 0xF7-0xFE for all sensor data (8 bytes)",
        ],
    )


def _bme680() -> ComponentKnowledge:
    """Bosch BME680 — Temperature, Pressure, Humidity + VOC gas sensor."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="BME680",
        manufacturer="Bosch Sensortec",
        mpn="BME680",
        description="Environmental sensor with temperature, pressure, humidity and VOC gas",
        category="sensor",
        interface=InterfaceType.I2C,
        i2c_address="0x76",
        spi_mode=0,
        registers=[
            RegisterInfo(address="0xD0", name="chip_id", description="Chip ID register, returns 0x61"),
            RegisterInfo(address="0xE0", name="reset", description="Soft reset, write 0xB6"),
            RegisterInfo(address="0x72", name="ctrl_hum", description="Humidity oversampling"),
            RegisterInfo(address="0x74", name="ctrl_meas", description="Pressure/Temperature OS + mode"),
            RegisterInfo(address="0x75", name="config", description="IIR filter, SPI config"),
            RegisterInfo(address="0x71", name="ctrl_gas_1", description="Gas sensor run, heater set-point"),
            RegisterInfo(address="0x64", name="gas_wait_0", description="Gas wait time, heater profile 0"),
            RegisterInfo(address="0x5A", name="res_heat_0", description="Heater resistance, profile 0"),
            RegisterInfo(address="0x1F", name="press_msb", description="Pressure data [19:12]"),
            RegisterInfo(address="0x22", name="temp_msb", description="Temperature data [19:12]"),
            RegisterInfo(address="0x25", name="hum_msb", description="Humidity data [15:8]"),
            RegisterInfo(address="0x2A", name="gas_r_msb", description="Gas resistance [9:2]"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0xE0", value="0xB6", description="Soft reset"),
            InitStep(order=2, reg_addr="", value="", description="Wait for reset", delay_ms=10),
            InitStep(order=3, reg_addr="0x72", value="0x01", description="Humidity oversampling x1"),
            InitStep(order=4, reg_addr="0x74", value="0x27", description="Temp OS x1, Press OS x1, Forced mode"),
            InitStep(order=5, reg_addr="0x75", value="0x00", description="IIR filter off"),
            InitStep(order=6, reg_addr="0x5A", value="0x73", description="Configure heater resistance 300C"),
            InitStep(order=7, reg_addr="0x64", value="0x59", description="Configure gas wait 100ms"),
            InitStep(order=8, reg_addr="0x71", value="0x10", description="Enable gas measurement, profile 0"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="3400000", unit="Hz"),
            TimingConstraint(parameter="Startup time", max="2", unit="ms"),
            TimingConstraint(parameter="Gas measurement time", typical="150", unit="ms"),
        ],
        notes=[
            "I2C address is 0x76 (SDO=GND) or 0x77 (SDO=VDD)",
            "Gas sensor requires heater calibration data from registers 0xE1-0xEE",
            "Use forced mode: set mode, wait, read, repeat",
        ],
    )


def _sht31() -> ComponentKnowledge:
    """Sensirion SHT31 — High-accuracy temperature and humidity sensor."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="SHT31",
        manufacturer="Sensirion",
        mpn="SHT31-DIS",
        description="High-accuracy digital temperature and humidity sensor",
        category="sensor",
        interface=InterfaceType.I2C,
        i2c_address="0x44",
        registers=[
            RegisterInfo(address="0x2400", name="measure_high", description="Single-shot, high repeat, clk stretch"),
            RegisterInfo(address="0x240B", name="measure_med", description="Single shot, medium repeatability"),
            RegisterInfo(address="0x2416", name="measure_low", description="Single shot, low repeatability"),
            RegisterInfo(address="0x2032", name="periodic_1hz", description="Periodic 1Hz, high repeatability"),
            RegisterInfo(address="0x30A2", name="soft_reset", description="Soft reset command"),
            RegisterInfo(address="0x3041", name="heater_enable", description="Enable internal heater"),
            RegisterInfo(address="0x3066", name="heater_disable", description="Disable internal heater"),
            RegisterInfo(address="0xF32D", name="status", description="Read status register"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x30A2", value="", description="Soft reset"),
            InitStep(order=2, reg_addr="", value="", description="Wait for reset", delay_ms=2),
            InitStep(order=3, reg_addr="0x2400", value="", description="Start single-shot, high repeatability"),
            InitStep(order=4, reg_addr="", value="", description="Wait for measurement", delay_ms=16),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="1000000", unit="Hz"),
            TimingConstraint(parameter="Measurement time (high rep)", typical="12.5", max="15", unit="ms"),
            TimingConstraint(parameter="Startup time", max="1", unit="ms"),
            TimingConstraint(parameter="Supply current (measuring)", typical="600", unit="uA"),
        ],
        notes=[
            "I2C address is 0x44 (ADDR=low) or 0x45 (ADDR=high)",
            "16-bit commands, MSB first, CRC-8 checksum on data",
            "Temperature range -40 to 125 C, accuracy +/- 0.3 C",
            "Humidity range 0-100% RH, accuracy +/- 2% RH",
        ],
    )


def _aht20() -> ComponentKnowledge:
    """Aosong AHT20 — Low-cost temperature and humidity sensor."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="AHT20",
        manufacturer="Aosong",
        mpn="AHT20",
        description="Low-cost digital temperature and humidity sensor",
        category="sensor",
        interface=InterfaceType.I2C,
        i2c_address="0x38",
        registers=[
            RegisterInfo(address="0xBE", name="initialize", description="Initialize sensor calibration"),
            RegisterInfo(address="0xAC", name="trigger_measure", description="Trigger measurement (0x33, 0x00)"),
            RegisterInfo(address="0xBA", name="soft_reset", description="Soft reset"),
            RegisterInfo(address="0x71", name="status", description="Read status byte (bit 3=calibrated, bit 7=busy)"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="", value="", description="Wait for power-on", delay_ms=40),
            InitStep(order=2, reg_addr="0x71", value="", description="Check status — verify bit 3 (calibrated) is set"),
            InitStep(order=3, reg_addr="0xBE", value="0x08,0x00", description="Initialize calibration if needed"),
            InitStep(order=4, reg_addr="", value="", description="Wait for calibration", delay_ms=10),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="Measurement time", typical="75", max="80", unit="ms"),
            TimingConstraint(parameter="Power-on time", max="40", unit="ms"),
        ],
        notes=[
            "Fixed I2C address 0x38 — only one per bus",
            "CRC-8 checksum on measurement data",
            "Temperature accuracy +/- 0.3 C, humidity +/- 2% RH",
        ],
    )


def _mcp9808() -> ComponentKnowledge:
    """Microchip MCP9808 — High-accuracy digital temperature sensor."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="MCP9808",
        manufacturer="Microchip",
        mpn="MCP9808",
        description="High-accuracy (+/- 0.25C) digital temperature sensor",
        category="sensor",
        interface=InterfaceType.I2C,
        i2c_address="0x18",
        registers=[
            RegisterInfo(address="0x01", name="config", description="Configuration register",
                         fields=[
                             RegisterField(name="t_hyst", bits="10:9", description="Hysteresis", default_value="00"),
                             RegisterField(name="shdn", bits="8", description="Shutdown mode", default_value="0"),
                         ]),
            RegisterInfo(address="0x02", name="t_upper", description="Alert upper boundary"),
            RegisterInfo(address="0x03", name="t_lower", description="Alert lower boundary"),
            RegisterInfo(address="0x04", name="t_crit", description="Critical temperature"),
            RegisterInfo(address="0x05", name="t_ambient", description="Ambient temperature register"),
            RegisterInfo(address="0x06", name="manuf_id", description="Manufacturer ID (returns 0x0054)"),
            RegisterInfo(address="0x07", name="device_id", description="Device ID (returns 0x0400)"),
            RegisterInfo(address="0x08", name="resolution", description="Resolution (0-3, default 3 = 0.0625C)"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x06", value="", description="Read manufacturer ID to verify (expect 0x0054)"),
            InitStep(order=2, reg_addr="0x08", value="0x03", description="Configure resolution 0.0625C"),
            InitStep(order=3, reg_addr="0x01", value="0x0000", description="Enable continuous conversion"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="Conversion time (0.0625C)", typical="250", unit="ms"),
            TimingConstraint(parameter="Supply current (typical)", typical="200", unit="uA"),
        ],
        notes=[
            "I2C address 0x18-0x1F (A0-A2 pins)",
            "Temperature accuracy +/- 0.25C from -40 to +125C",
            "Ambient temperature register: upper 4 bits = sign+flags, lower 12 = temp * 16",
        ],
    )


# ---------------------------------------------------------------------------
# Inertial / Motion sensors
# ---------------------------------------------------------------------------

def _mpu6050() -> ComponentKnowledge:
    """InvenSense MPU-6050 — 6-axis accelerometer + gyroscope."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="MPU6050",
        manufacturer="InvenSense (TDK)",
        mpn="MPU-6050",
        description="6-axis MEMS accelerometer and gyroscope",
        category="sensor",
        interface=InterfaceType.I2C,
        i2c_address="0x68",
        registers=[
            RegisterInfo(address="0x19", name="SMPLRT_DIV", description="Sample rate divider"),
            RegisterInfo(address="0x1A", name="CONFIG", description="DLPF and ext sync config"),
            RegisterInfo(address="0x1B", name="GYRO_CONFIG", description="Gyroscope full-scale range",
                         fields=[
                             RegisterField(name="FS_SEL", bits="4:3", description="0=250, 1=500, 2=1000, 3=2000 dps"),
                         ]),
            RegisterInfo(address="0x1C", name="ACCEL_CONFIG", description="Accelerometer full-scale range",
                         fields=[
                             RegisterField(name="AFS_SEL", bits="4:3", description="0=2g, 1=4g, 2=8g, 3=16g"),
                         ]),
            RegisterInfo(address="0x38", name="INT_ENABLE", description="Interrupt enable"),
            RegisterInfo(address="0x3B", name="ACCEL_XOUT_H", description="Accel X high byte"),
            RegisterInfo(address="0x41", name="TEMP_OUT_H", description="Temperature high byte"),
            RegisterInfo(address="0x43", name="GYRO_XOUT_H", description="Gyro X high byte"),
            RegisterInfo(address="0x6B", name="PWR_MGMT_1", description="Power management 1",
                         fields=[
                             RegisterField(name="DEVICE_RESET", bits="7", description="Reset all registers"),
                             RegisterField(name="SLEEP", bits="6", description="Sleep mode"),
                             RegisterField(name="CLKSEL", bits="2:0", description="Clock source select"),
                         ]),
            RegisterInfo(address="0x75", name="WHO_AM_I", description="Device ID register, returns 0x68"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x6B", value="0x80", description="Reset device"),
            InitStep(order=2, reg_addr="", value="", description="Wait for reset", delay_ms=100),
            InitStep(order=3, reg_addr="0x6B", value="0x01", description="Wake up, PLL with X gyro reference"),
            InitStep(order=4, reg_addr="0x1B", value="0x08", description="Gyroscope FS=500 dps"),
            InitStep(order=5, reg_addr="0x1C", value="0x08", description="Accelerometer FS=4g"),
            InitStep(order=6, reg_addr="0x19", value="0x07", description="Sample rate 1kHz / (1+7) = 125Hz"),
            InitStep(order=7, reg_addr="0x1A", value="0x03", description="DLPF bandwidth 44Hz"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="Gyro startup time", max="30", unit="ms"),
            TimingConstraint(parameter="Accel startup time", max="20", unit="ms"),
            TimingConstraint(parameter="Supply current (all axes)", typical="3.8", unit="mA"),
        ],
        notes=[
            "I2C address 0x68 (AD0=low) or 0x69 (AD0=high)",
            "Burst read from 0x3B for 14 bytes: accel(6) + temp(2) + gyro(6)",
            "Digital Low Pass Filter configured via CONFIG register",
            "Temperature: (raw / 340.0) + 36.53 degrees C",
        ],
    )


def _adxl345() -> ComponentKnowledge:
    """Analog Devices ADXL345 — 3-axis digital accelerometer."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="ADXL345",
        manufacturer="Analog Devices",
        mpn="ADXL345",
        description="3-axis digital accelerometer, 13-bit resolution, +/- 16g",
        category="sensor",
        interface=InterfaceType.I2C,
        i2c_address="0x53",
        spi_mode=3,
        registers=[
            RegisterInfo(address="0x00", name="DEVID", description="Device ID, returns 0xE5"),
            RegisterInfo(address="0x2C", name="BW_RATE", description="Data rate and power mode"),
            RegisterInfo(address="0x2D", name="POWER_CTL", description="Power control",
                         fields=[
                             RegisterField(name="Measure", bits="3", description="1=measurement mode"),
                             RegisterField(name="Sleep", bits="2", description="1=sleep mode"),
                         ]),
            RegisterInfo(address="0x2E", name="INT_ENABLE", description="Interrupt enable"),
            RegisterInfo(address="0x31", name="DATA_FORMAT", description="Data format (range, justify)",
                         fields=[
                             RegisterField(name="FULL_RES", bits="3", description="Full resolution mode"),
                             RegisterField(name="Range", bits="1:0", description="0=2g, 1=4g, 2=8g, 3=16g"),
                         ]),
            RegisterInfo(address="0x32", name="DATAX0", description="X-axis data 0 (LSB)"),
            RegisterInfo(address="0x33", name="DATAX1", description="X-axis data 1 (MSB)"),
            RegisterInfo(address="0x34", name="DATAY0", description="Y-axis data 0 (LSB)"),
            RegisterInfo(address="0x36", name="DATAZ0", description="Z-axis data 0 (LSB)"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x00", value="", description="Read DEVID to verify (expect 0xE5)"),
            InitStep(order=2, reg_addr="0x31", value="0x0B", description="Full resolution, +/- 16g range"),
            InitStep(order=3, reg_addr="0x2C", value="0x0A", description="Data rate 100Hz"),
            InitStep(order=4, reg_addr="0x2D", value="0x08", description="Enable measurement mode"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="SPI clock frequency", max="5000000", unit="Hz"),
            TimingConstraint(parameter="Startup time", max="1.4", unit="ms"),
            TimingConstraint(parameter="Supply current (measuring)", typical="140", unit="uA"),
        ],
        notes=[
            "I2C address 0x53 (ALT ADDRESS=low) or 0x1D (ALT ADDRESS=high)",
            "Also supports 3- and 4-wire SPI (mode 3)",
            "Burst read 6 bytes from 0x32 for X/Y/Z data",
        ],
    )


def _lis3dh() -> ComponentKnowledge:
    """STMicroelectronics LIS3DH — 3-axis MEMS accelerometer."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="LIS3DH",
        manufacturer="STMicroelectronics",
        mpn="LIS3DH",
        description="Ultra-low-power 3-axis accelerometer",
        category="sensor",
        interface=InterfaceType.I2C,
        i2c_address="0x18",
        spi_mode=3,
        registers=[
            RegisterInfo(address="0x0F", name="WHO_AM_I", description="Device ID, returns 0x33"),
            RegisterInfo(address="0x20", name="CTRL_REG1", description="Data rate, low-power, axis enable",
                         fields=[
                             RegisterField(name="ODR", bits="7:4", description="Output data rate"),
                             RegisterField(name="LPen", bits="3", description="Low-power enable"),
                             RegisterField(name="Zen", bits="2", description="Z-axis enable"),
                             RegisterField(name="Yen", bits="1", description="Y-axis enable"),
                             RegisterField(name="Xen", bits="0", description="X-axis enable"),
                         ]),
            RegisterInfo(address="0x21", name="CTRL_REG2", description="High-pass filter config"),
            RegisterInfo(address="0x22", name="CTRL_REG3", description="Interrupt config"),
            RegisterInfo(address="0x23", name="CTRL_REG4", description="Full-scale, BDU, endian",
                         fields=[
                             RegisterField(name="BDU", bits="7", description="Block data update"),
                             RegisterField(name="FS", bits="5:4", description="0=2g, 1=4g, 2=8g, 3=16g"),
                         ]),
            RegisterInfo(address="0x28", name="OUT_X_L", description="X-axis output low byte"),
            RegisterInfo(address="0x29", name="OUT_X_H", description="X-axis output high byte"),
            RegisterInfo(address="0x2A", name="OUT_Y_L", description="Y-axis output low byte"),
            RegisterInfo(address="0x2C", name="OUT_Z_L", description="Z-axis output low byte"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x0F", value="", description="Read WHO_AM_I to verify (expect 0x33)"),
            InitStep(order=2, reg_addr="0x20", value="0x57", description="100Hz, normal mode, all axes enabled"),
            InitStep(order=3, reg_addr="0x23", value="0x88", description="BDU enabled, +/- 2g, high resolution"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="SPI clock frequency", max="10000000", unit="Hz"),
            TimingConstraint(parameter="Turn-on time", max="5", unit="ms"),
            TimingConstraint(parameter="Supply current (normal 50Hz)", typical="11", unit="uA"),
        ],
        notes=[
            "I2C address 0x18 (SDO=GND) or 0x19 (SDO=VDD)",
            "Set bit 7 of sub-address for multi-byte read (auto-increment)",
            "Ultra-low power: 2uA in low-power mode at 1Hz",
        ],
    )


def _bno055() -> ComponentKnowledge:
    """Bosch BNO055 — 9-axis absolute orientation sensor."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="BNO055",
        manufacturer="Bosch Sensortec",
        mpn="BNO055",
        description="9-axis absolute orientation sensor with built-in sensor fusion",
        category="sensor",
        interface=InterfaceType.I2C,
        i2c_address="0x28",
        registers=[
            RegisterInfo(address="0x00", name="CHIP_ID", description="Chip ID, returns 0xA0"),
            RegisterInfo(address="0x07", name="PAGE_ID", description="Page select (0 or 1)"),
            RegisterInfo(address="0x08", name="ACCEL_DATA_X_LSB", description="Accel X low byte"),
            RegisterInfo(address="0x1A", name="EULER_H_LSB", description="Euler heading low byte"),
            RegisterInfo(address="0x20", name="QUATERNION_DATA_W_LSB", description="Quaternion W low byte"),
            RegisterInfo(address="0x34", name="CALIB_STAT", description="Calibration status (sys/gyro/accel/mag)"),
            RegisterInfo(address="0x35", name="SYS_STATUS", description="System status"),
            RegisterInfo(address="0x3D", name="OPR_MODE", description="Operating mode",
                         fields=[
                             RegisterField(name="mode", bits="3:0", description="0x00=CONFIG, 0x0C=NDOF"),
                         ]),
            RegisterInfo(address="0x3E", name="PWR_MODE", description="Power mode (normal/low/suspend)"),
            RegisterInfo(address="0x3F", name="SYS_TRIGGER", description="System trigger (reset, self-test)"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x3F", value="0x20", description="Reset system"),
            InitStep(order=2, reg_addr="", value="", description="Wait for reset", delay_ms=650),
            InitStep(order=3, reg_addr="0x3E", value="0x00", description="Normal power mode"),
            InitStep(order=4, reg_addr="0x07", value="0x00", description="Select page 0"),
            InitStep(order=5, reg_addr="0x3F", value="0x00", description="Clear triggers, use internal oscillator"),
            InitStep(order=6, reg_addr="0x3D", value="0x0C", description="NDOF fusion mode"),
            InitStep(order=7, reg_addr="", value="", description="Wait for mode switch", delay_ms=20),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="Reset time", max="650", unit="ms"),
            TimingConstraint(parameter="Config to any mode", max="19", unit="ms"),
            TimingConstraint(parameter="Supply current (NDOF)", typical="12.3", unit="mA"),
        ],
        notes=[
            "I2C address 0x28 (COM3=low) or 0x29 (COM3=high)",
            "Built-in sensor fusion: outputs quaternion, Euler angles, linear accel, gravity",
            "Calibration status: each sensor 0-3, 3=fully calibrated",
            "NDOF mode: 100Hz fusion output rate",
        ],
    )


def _lsm6dso() -> ComponentKnowledge:
    """STMicroelectronics LSM6DSO — 6-axis IMU (accel + gyro)."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="LSM6DSO",
        manufacturer="STMicroelectronics",
        mpn="LSM6DSO",
        description="iNEMO 6-axis IMU with machine learning core",
        category="sensor",
        interface=InterfaceType.I2C,
        i2c_address="0x6A",
        spi_mode=3,
        registers=[
            RegisterInfo(address="0x0F", name="WHO_AM_I", description="Device ID, returns 0x6C"),
            RegisterInfo(address="0x10", name="CTRL1_XL", description="Accel ODR and full-scale",
                         fields=[
                             RegisterField(name="ODR_XL", bits="7:4", description="Accel output data rate"),
                             RegisterField(name="FS_XL", bits="3:2", description="0=2g, 1=16g, 2=4g, 3=8g"),
                         ]),
            RegisterInfo(address="0x11", name="CTRL2_G", description="Gyro ODR and full-scale",
                         fields=[
                             RegisterField(name="ODR_G", bits="7:4", description="Gyro output data rate"),
                             RegisterField(name="FS_G", bits="3:2", description="0=250, 1=500, 2=1000, 3=2000 dps"),
                         ]),
            RegisterInfo(address="0x12", name="CTRL3_C", description="Control register 3",
                         fields=[
                             RegisterField(name="BDU", bits="6", description="Block data update"),
                             RegisterField(name="IF_INC", bits="2", description="Auto-increment address"),
                             RegisterField(name="SW_RESET", bits="0", description="Software reset"),
                         ]),
            RegisterInfo(address="0x20", name="OUT_TEMP_L", description="Temperature output low byte"),
            RegisterInfo(address="0x22", name="OUTX_L_G", description="Gyro X low byte"),
            RegisterInfo(address="0x28", name="OUTX_L_A", description="Accel X low byte"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x12", value="0x01", description="Software reset"),
            InitStep(order=2, reg_addr="", value="", description="Wait for reset", delay_ms=10),
            InitStep(order=3, reg_addr="0x12", value="0x44", description="BDU enabled, auto-increment"),
            InitStep(order=4, reg_addr="0x10", value="0x40", description="Accel 104Hz, +/- 2g"),
            InitStep(order=5, reg_addr="0x11", value="0x40", description="Gyro 104Hz, 250 dps"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="SPI clock frequency", max="10000000", unit="Hz"),
            TimingConstraint(parameter="Startup time", max="10", unit="ms"),
            TimingConstraint(parameter="Supply current (accel+gyro)", typical="0.55", unit="mA"),
        ],
        notes=[
            "I2C address 0x6A (SDO/SA0=low) or 0x6B (SDO/SA0=high)",
            "Machine learning core for on-device gesture/activity recognition",
            "Burst read 12 bytes from 0x22 (gyro) or 0x28 (accel) for all axes",
        ],
    )


# ---------------------------------------------------------------------------
# Distance / Proximity / Light sensors
# ---------------------------------------------------------------------------

def _vl53l0x() -> ComponentKnowledge:
    """STMicroelectronics VL53L0X — Time-of-Flight distance sensor."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="VL53L0X",
        manufacturer="STMicroelectronics",
        mpn="VL53L0X",
        description="Time-of-Flight ranging sensor, up to 2m",
        category="sensor",
        interface=InterfaceType.I2C,
        i2c_address="0x29",
        registers=[
            RegisterInfo(address="0xC0", name="MODEL_ID", description="Model ID, returns 0xEE"),
            RegisterInfo(address="0xC1", name="MODEL_ID_2", description="Model ID byte 2"),
            RegisterInfo(address="0xC2", name="MODULE_TYPE", description="Module type"),
            RegisterInfo(address="0x00", name="SYSRANGE_START", description="Start range (0x01=single, 0x02=cont)"),
            RegisterInfo(address="0x01", name="SYSTEM_SEQUENCE_CONFIG", description="Sequence step enables"),
            RegisterInfo(address="0x0A", name="SYSTEM_INTERRUPT_CONFIG_GPIO", description="Interrupt config"),
            RegisterInfo(address="0x13", name="RESULT_INTERRUPT_STATUS", description="Interrupt status"),
            RegisterInfo(address="0x14", name="RESULT_RANGE_STATUS", description="Range status + distance (16-bit)"),
            RegisterInfo(address="0x8A", name="I2C_SLAVE_DEVICE_ADDRESS", description="Programmable I2C address"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0xC0", value="", description="Read model ID to verify (expect 0xEE)"),
            InitStep(order=2, reg_addr="", value="", description="Wait for boot", delay_ms=2),
            InitStep(order=3, reg_addr="0x88", value="0x00", description="Configure VHV init"),
            InitStep(order=4, reg_addr="0x80", value="0x01", description="Start data init sequence"),
            InitStep(order=5, reg_addr="0x00", value="0x01", description="Start single ranging"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="Ranging time (default)", typical="30", unit="ms"),
            TimingConstraint(parameter="Boot time", max="1.2", unit="ms"),
            TimingConstraint(parameter="Supply current (ranging)", typical="19", unit="mA"),
        ],
        notes=[
            "Default I2C address 0x29, programmable via register 0x8A",
            "XSHUT pin for hardware standby and multi-sensor I2C address assignment",
            "Range: up to 2m (long distance mode), typical 1.2m indoor",
            "Complex init sequence — use vendor API (VL53L0X_DataInit) for production",
        ],
    )


def _apds9960() -> ComponentKnowledge:
    """Broadcom APDS-9960 — Gesture, proximity, ambient light, color sensor."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="APDS9960",
        manufacturer="Broadcom",
        mpn="APDS-9960",
        description="Digital proximity, ambient light, RGB and gesture sensor",
        category="sensor",
        interface=InterfaceType.I2C,
        i2c_address="0x39",
        registers=[
            RegisterInfo(address="0x80", name="ENABLE", description="Enable states and interrupts",
                         fields=[
                             RegisterField(name="GEN", bits="6", description="Gesture enable"),
                             RegisterField(name="PIEN", bits="5", description="Proximity interrupt enable"),
                             RegisterField(name="AIEN", bits="4", description="ALS interrupt enable"),
                             RegisterField(name="PEN", bits="2", description="Proximity detect enable"),
                             RegisterField(name="AEN", bits="1", description="ALS enable"),
                             RegisterField(name="PON", bits="0", description="Power ON"),
                         ]),
            RegisterInfo(address="0x81", name="ATIME", description="ALS ADC integration time"),
            RegisterInfo(address="0x83", name="WTIME", description="Wait time"),
            RegisterInfo(address="0x8E", name="PPULSE", description="Proximity pulse count and length"),
            RegisterInfo(address="0x8F", name="CONTROL", description="Gain control",
                         fields=[
                             RegisterField(name="LDRIVE", bits="7:6", description="LED drive strength"),
                             RegisterField(name="PGAIN", bits="3:2", description="Proximity gain"),
                             RegisterField(name="AGAIN", bits="1:0", description="ALS gain"),
                         ]),
            RegisterInfo(address="0x92", name="ID", description="Device ID, returns 0xAB"),
            RegisterInfo(address="0x93", name="STATUS", description="Device status"),
            RegisterInfo(address="0x94", name="CDATAL", description="Clear channel data low byte"),
            RegisterInfo(address="0x9C", name="PDATA", description="Proximity data"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x92", value="", description="Read ID to verify (expect 0xAB)"),
            InitStep(order=2, reg_addr="0x80", value="0x00", description="Disable all features"),
            InitStep(order=3, reg_addr="0x81", value="0xDB", description="ALS integration 103ms"),
            InitStep(order=4, reg_addr="0x8E", value="0x87", description="Proximity: 16us, 8 pulses"),
            InitStep(order=5, reg_addr="0x8F", value="0x01", description="Proximity gain 2x, ALS gain 4x"),
            InitStep(order=6, reg_addr="0x80", value="0x07", description="Enable PON + ALS + proximity"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="Power-on time", max="5.7", unit="ms"),
            TimingConstraint(parameter="Supply current (all active)", typical="4.5", unit="mA"),
        ],
        notes=[
            "Fixed I2C address 0x39",
            "Gesture detection requires reading FIFO data registers 0xFC-0xFF",
            "ALS/Color: 4 channels (clear, red, green, blue) 16-bit each",
        ],
    )


def _tsl2561() -> ComponentKnowledge:
    """AMS/TAOS TSL2561 — Light-to-digital converter."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="TSL2561",
        manufacturer="AMS",
        mpn="TSL2561",
        description="Light-to-digital converter, lux range 0.1 to 40000",
        category="sensor",
        interface=InterfaceType.I2C,
        i2c_address="0x39",
        registers=[
            RegisterInfo(address="0x00", name="CONTROL", description="Power on/off (write 0x03 to power on)"),
            RegisterInfo(address="0x01", name="TIMING", description="Integration time and gain",
                         fields=[
                             RegisterField(name="GAIN", bits="4", description="0=1x, 1=16x"),
                             RegisterField(name="INTEG", bits="1:0", description="0=13.7ms, 1=101ms, 2=402ms"),
                         ]),
            RegisterInfo(address="0x06", name="INT_CONTROL", description="Interrupt control"),
            RegisterInfo(address="0x0A", name="ID", description="Part number and revision"),
            RegisterInfo(address="0x0C", name="DATA0LOW", description="ADC channel 0 low byte (visible+IR)"),
            RegisterInfo(address="0x0D", name="DATA0HIGH", description="ADC channel 0 high byte"),
            RegisterInfo(address="0x0E", name="DATA1LOW", description="ADC channel 1 low byte (IR only)"),
            RegisterInfo(address="0x0F", name="DATA1HIGH", description="ADC channel 1 high byte"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x80", value="0x03", description="Power ON (command bit + control register)"),
            InitStep(order=2, reg_addr="0x81", value="0x02", description="Configure 402ms integration, 1x gain"),
            InitStep(order=3, reg_addr="", value="", description="Wait for first integration", delay_ms=410),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="Integration time (402ms)", typical="402", unit="ms"),
            TimingConstraint(parameter="Supply current (active)", typical="0.24", unit="mA"),
        ],
        notes=[
            "I2C address: 0x29 (ADDR=GND), 0x39 (ADDR=float), 0x49 (ADDR=VDD)",
            "Command register: set bit 7 (0x80) for all register accesses",
            "Lux calculation requires both CH0 (visible+IR) and CH1 (IR) readings",
        ],
    )


def _bh1750() -> ComponentKnowledge:
    """Rohm BH1750 — Ambient light sensor."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="BH1750",
        manufacturer="Rohm",
        mpn="BH1750FVI",
        description="Digital ambient light sensor, 1 to 65535 lux",
        category="sensor",
        interface=InterfaceType.I2C,
        i2c_address="0x23",
        registers=[
            RegisterInfo(address="0x00", name="POWER_DOWN", description="Power down command"),
            RegisterInfo(address="0x01", name="POWER_ON", description="Power on command"),
            RegisterInfo(address="0x07", name="RESET", description="Reset data register"),
            RegisterInfo(address="0x10", name="CONT_H_RES", description="Continuous high resolution mode (1 lux)"),
            RegisterInfo(address="0x11", name="CONT_H_RES2", description="Continuous high resolution mode 2 (0.5 lux)"),
            RegisterInfo(address="0x20", name="ONE_H_RES", description="One-time high resolution mode"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x01", value="", description="Power on"),
            InitStep(order=2, reg_addr="0x07", value="", description="Reset data register"),
            InitStep(order=3, reg_addr="0x10", value="", description="Start continuous high-resolution mode"),
            InitStep(order=4, reg_addr="", value="", description="Wait for first measurement", delay_ms=180),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="Measurement time (H-res)", typical="120", max="180", unit="ms"),
            TimingConstraint(parameter="Supply current (measuring)", typical="120", unit="uA"),
        ],
        notes=[
            "I2C address 0x23 (ADDR=low) or 0x5C (ADDR=high)",
            "Command-based interface: no traditional register map",
            "Read 2 bytes for measurement result, lux = raw / 1.2",
        ],
    )


def _max30102() -> ComponentKnowledge:
    """Maxim MAX30102 — Pulse oximeter and heart-rate sensor."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="MAX30102",
        manufacturer="Maxim Integrated",
        mpn="MAX30102",
        description="Pulse oximetry and heart-rate monitor biosensor",
        category="sensor",
        interface=InterfaceType.I2C,
        i2c_address="0x57",
        registers=[
            RegisterInfo(address="0x00", name="INT_STATUS_1", description="Interrupt status 1"),
            RegisterInfo(address="0x01", name="INT_STATUS_2", description="Interrupt status 2"),
            RegisterInfo(address="0x02", name="INT_ENABLE_1", description="Interrupt enable 1"),
            RegisterInfo(address="0x04", name="FIFO_WR_PTR", description="FIFO write pointer"),
            RegisterInfo(address="0x05", name="FIFO_OVF_CTR", description="FIFO overflow counter"),
            RegisterInfo(address="0x06", name="FIFO_RD_PTR", description="FIFO read pointer"),
            RegisterInfo(address="0x07", name="FIFO_DATA", description="FIFO data register"),
            RegisterInfo(address="0x08", name="FIFO_CONFIG", description="FIFO configuration"),
            RegisterInfo(address="0x09", name="MODE_CONFIG", description="Mode configuration",
                         fields=[
                             RegisterField(name="SHDN", bits="7", description="Shutdown control"),
                             RegisterField(name="RESET", bits="6", description="Reset control"),
                             RegisterField(name="MODE", bits="2:0", description="0x02=Red 0x03=Red+IR 0x07=MultiLED"),
                         ]),
            RegisterInfo(address="0x0A", name="SPO2_CONFIG", description="SpO2 configuration"),
            RegisterInfo(address="0x0C", name="LED1_PA", description="LED1 (Red) pulse amplitude"),
            RegisterInfo(address="0x0D", name="LED2_PA", description="LED2 (IR) pulse amplitude"),
            RegisterInfo(address="0xFE", name="REV_ID", description="Revision ID"),
            RegisterInfo(address="0xFF", name="PART_ID", description="Part ID, returns 0x15"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x09", value="0x40", description="Reset device"),
            InitStep(order=2, reg_addr="", value="", description="Wait for reset", delay_ms=10),
            InitStep(order=3, reg_addr="0x02", value="0xC0", description="Enable FIFO almost-full + data IRQ"),
            InitStep(order=4, reg_addr="0x08", value="0x4F", description="FIFO config: SMP_AVE=4, rollover enable"),
            InitStep(order=5, reg_addr="0x09", value="0x03", description="SpO2 mode (Red + IR)"),
            InitStep(order=6, reg_addr="0x0A", value="0x27", description="SpO2: 411us, ADC range 4096, 100 SPS"),
            InitStep(order=7, reg_addr="0x0C", value="0x24", description="Red LED current 7.2mA"),
            InitStep(order=8, reg_addr="0x0D", value="0x24", description="IR LED current 7.2mA"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="Power-up time", max="1", unit="ms"),
            TimingConstraint(parameter="Supply current (SpO2)", typical="600", unit="uA"),
        ],
        notes=[
            "Fixed I2C address 0x57",
            "FIFO: each sample = 3 bytes per LED (18-bit ADC), read in bursts",
            "SpO2 calculation requires Red/IR ratio algorithm",
        ],
    )


# ---------------------------------------------------------------------------
# Current / Power / ADC sensors
# ---------------------------------------------------------------------------

def _ina219() -> ComponentKnowledge:
    """Texas Instruments INA219 — Bidirectional current/power monitor."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="INA219",
        manufacturer="Texas Instruments",
        mpn="INA219",
        description="High-side current/power monitor with I2C interface",
        category="sensor",
        interface=InterfaceType.I2C,
        i2c_address="0x40",
        registers=[
            RegisterInfo(address="0x00", name="CONFIG", description="Configuration register",
                         fields=[
                             RegisterField(name="RST", bits="15", description="Reset bit"),
                             RegisterField(name="BRNG", bits="13", description="Bus voltage range (0=16V, 1=32V)"),
                             RegisterField(name="PG", bits="12:11", description="PGA gain /1 /2 /4 /8"),
                             RegisterField(name="BADC", bits="10:7", description="Bus ADC resolution/averaging"),
                             RegisterField(name="SADC", bits="6:3", description="Shunt ADC resolution/averaging"),
                             RegisterField(name="MODE", bits="2:0", description="Operating mode"),
                         ]),
            RegisterInfo(address="0x01", name="SHUNT_VOLTAGE", description="Shunt voltage (LSB = 10uV)"),
            RegisterInfo(address="0x02", name="BUS_VOLTAGE", description="Bus voltage (LSB = 4mV, bits 15:3)"),
            RegisterInfo(address="0x03", name="POWER", description="Power = current * bus_voltage"),
            RegisterInfo(address="0x04", name="CURRENT", description="Current (requires calibration)"),
            RegisterInfo(address="0x05", name="CALIBRATION", description="Calibration register"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x00", value="0x8000", description="Reset device"),
            InitStep(order=2, reg_addr="", value="", description="Wait for reset", delay_ms=1),
            InitStep(order=3, reg_addr="0x05", value="0x1000", description="Calibrate for 0.1ohm shunt, 3.2A max"),
            InitStep(order=4, reg_addr="0x00", value="0x399F",
                     description="32V range, /8 gain, 12-bit, continuous shunt+bus"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="2560000", unit="Hz"),
            TimingConstraint(parameter="Conversion time (12-bit)", typical="532", unit="us"),
            TimingConstraint(parameter="Supply current", typical="1", unit="mA"),
        ],
        notes=[
            "I2C address set by A0/A1 pins: 0x40-0x4F (16 addresses)",
            "Calibration: CAL = trunc(0.04096 / (current_LSB * R_shunt))",
            "Bus voltage register: shift right 3 bits, multiply by 4mV",
        ],
    )


def _ina226() -> ComponentKnowledge:
    """Texas Instruments INA226 — High-precision current/power monitor."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="INA226",
        manufacturer="Texas Instruments",
        mpn="INA226",
        description="High-precision bidirectional current/power monitor, 36V, 2.5uV LSB",
        category="sensor",
        interface=InterfaceType.I2C,
        i2c_address="0x40",
        registers=[
            RegisterInfo(address="0x00", name="CONFIG", description="Configuration (avg, conversion time, mode)"),
            RegisterInfo(address="0x01", name="SHUNT_VOLTAGE", description="Shunt voltage (LSB = 2.5uV)"),
            RegisterInfo(address="0x02", name="BUS_VOLTAGE", description="Bus voltage (LSB = 1.25mV)"),
            RegisterInfo(address="0x03", name="POWER", description="Power register"),
            RegisterInfo(address="0x04", name="CURRENT", description="Current register"),
            RegisterInfo(address="0x05", name="CALIBRATION", description="Calibration register"),
            RegisterInfo(address="0xFE", name="MANUFACTURER_ID", description="Manufacturer ID, returns 0x5449"),
            RegisterInfo(address="0xFF", name="DIE_ID", description="Die ID, returns 0x2260"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x00", value="0x8000", description="Reset device"),
            InitStep(order=2, reg_addr="", value="", description="Wait for reset", delay_ms=1),
            InitStep(order=3, reg_addr="0xFE", value="", description="Read manufacturer ID (expect 0x5449)"),
            InitStep(order=4, reg_addr="0x05", value="0x0A00", description="Calibration for 0.01 ohm shunt"),
            InitStep(order=5, reg_addr="0x00", value="0x4527",
                     description="Average 16 samples, 1.1ms conversion, continuous"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="2560000", unit="Hz"),
            TimingConstraint(parameter="Conversion time (1.1ms)", typical="1.1", unit="ms"),
            TimingConstraint(parameter="Supply current", typical="330", unit="uA"),
        ],
        notes=[
            "I2C address set by A0/A1 pins: 0x40-0x4F",
            "36V common-mode range, shunt voltage LSB = 2.5uV",
            "Alert pin for over/under current/voltage thresholds",
        ],
    )


def _ads1115() -> ComponentKnowledge:
    """Texas Instruments ADS1115 — 16-bit 4-channel ADC."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="ADS1115",
        manufacturer="Texas Instruments",
        mpn="ADS1115",
        description="16-bit 4-channel delta-sigma ADC with PGA",
        category="sensor",
        interface=InterfaceType.I2C,
        i2c_address="0x48",
        registers=[
            RegisterInfo(address="0x00", name="CONVERSION", description="Conversion result register"),
            RegisterInfo(address="0x01", name="CONFIG", description="Configuration register",
                         fields=[
                             RegisterField(name="OS", bits="15", description="Operational status / single-shot start"),
                             RegisterField(name="MUX", bits="14:12", description="Input mux (100=AIN0, 101=AIN1...)"),
                             RegisterField(name="PGA", bits="11:9", description="Gain (010=2.048V, 001=4.096V)"),
                             RegisterField(name="MODE", bits="8", description="0=continuous, 1=single-shot"),
                             RegisterField(name="DR", bits="7:5", description="Data rate (100=128SPS)"),
                         ]),
            RegisterInfo(address="0x02", name="LO_THRESH", description="Low threshold for comparator"),
            RegisterInfo(address="0x03", name="HI_THRESH", description="High threshold for comparator"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x01", value="0xC583",
                     description="AIN0 single-ended, +/-2.048V, single-shot, 128SPS"),
            InitStep(order=2, reg_addr="", value="", description="Wait for conversion", delay_ms=8),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="3400000", unit="Hz"),
            TimingConstraint(parameter="Conversion time (128SPS)", typical="7.8", unit="ms"),
            TimingConstraint(parameter="Supply current", typical="150", unit="uA"),
        ],
        notes=[
            "I2C address: 0x48 (ADDR=GND), 0x49 (ADDR=VDD), 0x4A (ADDR=SDA), 0x4B (ADDR=SCL)",
            "PGA ranges: 6.144V, 4.096V, 2.048V, 1.024V, 0.512V, 0.256V",
            "Single-ended (4 ch) or differential (2 pairs) input modes",
            "ALERT/RDY pin for conversion-ready interrupt",
        ],
    )


# ---------------------------------------------------------------------------
# Temperature-only sensors (GPIO/1-Wire)
# ---------------------------------------------------------------------------

def _ds18b20() -> ComponentKnowledge:
    """Maxim DS18B20 — 1-Wire digital temperature sensor."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="DS18B20",
        manufacturer="Maxim Integrated",
        mpn="DS18B20",
        description="Programmable resolution 1-Wire digital thermometer, -55 to +125C",
        category="sensor",
        interface=InterfaceType.GPIO,
        registers=[
            RegisterInfo(address="0x44", name="CONVERT_T", description="Initiate temperature conversion"),
            RegisterInfo(address="0xBE", name="READ_SCRATCHPAD", description="Read 9 bytes: temp, TH, TL, config, CRC"),
            RegisterInfo(address="0x4E", name="WRITE_SCRATCHPAD", description="Write TH, TL, config (3 bytes)"),
            RegisterInfo(address="0x48", name="COPY_SCRATCHPAD", description="Copy scratchpad to EEPROM"),
            RegisterInfo(address="0xCC", name="SKIP_ROM", description="Address all devices on bus"),
            RegisterInfo(address="0x33", name="READ_ROM", description="Read 64-bit ROM code"),
            RegisterInfo(address="0x55", name="MATCH_ROM", description="Address specific device"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="", value="", description="Reset pulse (480us low, wait 60us)"),
            InitStep(order=2, reg_addr="0xCC", value="", description="Skip ROM (single device)"),
            InitStep(order=3, reg_addr="0x44", value="", description="Start temperature conversion"),
            InitStep(order=4, reg_addr="", value="", description="Wait for conversion", delay_ms=750),
            InitStep(order=5, reg_addr="0xCC", value="", description="Skip ROM"),
            InitStep(order=6, reg_addr="0xBE", value="", description="Read scratchpad (9 bytes)"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="Conversion time (12-bit)", max="750", unit="ms"),
            TimingConstraint(parameter="Conversion time (9-bit)", max="94", unit="ms"),
            TimingConstraint(parameter="Supply current (active)", typical="1", max="1.5", unit="mA"),
        ],
        notes=[
            "1-Wire protocol: requires 4.7k pull-up resistor on data line",
            "Parasitic power mode: powered through data line",
            "Temperature: raw_value * 0.0625 degrees C (12-bit default)",
            "Multiple sensors on same 1-Wire bus, each with unique 64-bit ROM",
        ],
    )


def _dht22() -> ComponentKnowledge:
    """Aosong DHT22/AM2302 — Temperature and humidity sensor (single-wire)."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="DHT22",
        manufacturer="Aosong",
        mpn="AM2302",
        description="Digital temperature and humidity sensor, single-wire protocol",
        category="sensor",
        interface=InterfaceType.GPIO,
        registers=[],  # proprietary single-wire protocol
        init_sequence=[
            InitStep(order=1, reg_addr="", value="", description="Pull data line low for 1-10ms (start signal)"),
            InitStep(order=2, reg_addr="", value="", description="Release line, wait for sensor response (20-40us)"),
            InitStep(order=3, reg_addr="", value="", description="Read 40 bits: 16b humid + 16b temp + 8b csum"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="Sampling period", min="2000", unit="ms"),
            TimingConstraint(parameter="Power-on time", max="1000", unit="ms"),
            TimingConstraint(parameter="Supply current", typical="1.5", unit="mA"),
        ],
        notes=[
            "Requires 4.7k-10k pull-up resistor on data line",
            "Minimum 2 second interval between readings",
            "Temperature: -40 to 80C, +/- 0.5C accuracy",
            "Humidity: 0-99.9% RH, +/- 2% accuracy",
            "5V tolerant but works at 3.3V (shorter cable runs)",
        ],
    )


def _hx711() -> ComponentKnowledge:
    """Avia Semiconductor HX711 — 24-bit ADC for load cells."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="HX711",
        manufacturer="Avia Semiconductor",
        mpn="HX711",
        description="24-bit ADC for weigh scales and load cells",
        category="sensor",
        interface=InterfaceType.GPIO,
        registers=[],  # custom serial protocol (DOUT/SCK)
        init_sequence=[
            InitStep(order=1, reg_addr="", value="", description="Wait for power-on", delay_ms=400),
            InitStep(order=2, reg_addr="", value="", description="Wait for DOUT to go low (data ready)"),
            InitStep(order=3, reg_addr="", value="", description="Clock 25 pulses on SCK to read + set gain=128 ch.A"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="Output data rate", typical="10", unit="Hz"),
            TimingConstraint(parameter="Output data rate (80Hz)", typical="80", unit="Hz"),
            TimingConstraint(parameter="Power-on settling", max="400", unit="ms"),
            TimingConstraint(parameter="Supply current", typical="1.5", unit="mA"),
        ],
        notes=[
            "2-wire interface: DOUT (data), PD_SCK (clock), not standard SPI",
            "24 clock pulses = read data, 25th = gain 128 ch.A, 26th = gain 32 ch.B, 27th = gain 64 ch.A",
            "Channel A: gain 128 or 64, Channel B: gain 32",
            "Power down: hold SCK high for >60us",
        ],
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTRY: dict[str, callable] = {
    # Environmental
    "BME280": _bme280,
    "BMP280": _bme280,  # same registers minus humidity, chip_id 0x58
    "BME680": _bme680,
    "BME688": _bme680,  # pin-compatible successor
    "SHT31": _sht31,
    "SHT31-DIS": _sht31,
    "SHT30": _sht31,  # lower accuracy variant, same interface
    "SHT35": _sht31,  # higher accuracy variant, same interface
    "AHT20": _aht20,
    "AHT21": _aht20,  # same interface
    "MCP9808": _mcp9808,
    # IMU / Motion
    "MPU6050": _mpu6050,
    "MPU-6050": _mpu6050,
    "MPU6500": _mpu6050,  # similar register set
    "ADXL345": _adxl345,
    "ADXL343": _adxl345,  # pin-compatible
    "LIS3DH": _lis3dh,
    "LIS3DHTR": _lis3dh,
    "BNO055": _bno055,
    "LSM6DSO": _lsm6dso,
    "LSM6DS3": _lsm6dso,  # similar register set
    "LSM6DSOX": _lsm6dso,
    # Distance / Proximity / Light
    "VL53L0X": _vl53l0x,
    "VL53L1X": _vl53l0x,  # similar API, different tuning
    "APDS9960": _apds9960,
    "APDS-9960": _apds9960,
    "TSL2561": _tsl2561,
    "TSL2591": _tsl2561,  # similar interface, higher dynamic range
    "BH1750": _bh1750,
    "BH1750FVI": _bh1750,
    "MAX30102": _max30102,
    "MAX30105": _max30102,  # adds green LED, same base registers
    # Current / Power / ADC
    "INA219": _ina219,
    "INA226": _ina226,
    "ADS1115": _ads1115,
    "ADS1015": _ads1115,  # 12-bit variant, same registers
    # Temperature (GPIO)
    "DS18B20": _ds18b20,
    "DS18S20": _ds18b20,  # older, 9-bit fixed
    "DHT22": _dht22,
    "AM2302": _dht22,
    "DHT11": _dht22,  # lower accuracy, same protocol
    "HX711": _hx711,
}
