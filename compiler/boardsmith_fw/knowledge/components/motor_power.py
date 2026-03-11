# SPDX-License-Identifier: AGPL-3.0-or-later
"""Motor drivers and power management components."""

from __future__ import annotations

from boardsmith_fw.models.component_knowledge import (
    ComponentKnowledge,
    InitStep,
    InterfaceType,
    RegisterField,
    RegisterInfo,
    TimingConstraint,
)


def _drv8825() -> ComponentKnowledge:
    """Texas Instruments DRV8825 — Stepper motor driver."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="DRV8825",
        manufacturer="Texas Instruments",
        mpn="DRV8825",
        description="Bipolar stepper motor driver, 2.5A, 45V, up to 1/32 microstepping",
        category="motor_driver",
        interface=InterfaceType.GPIO,
        registers=[],  # GPIO-controlled, no register interface
        init_sequence=[
            InitStep(order=1, reg_addr="", value="", description="Set nRESET high (enable driver)"),
            InitStep(order=2, reg_addr="", value="", description="Set nSLEEP high (wake driver)"),
            InitStep(order=3, reg_addr="", value="", description="Wait for charge pump", delay_ms=2),
            InitStep(order=4, reg_addr="", value="", description="Configure M0/M1/M2 for microstepping mode"),
            InitStep(order=5, reg_addr="", value="", description="Set DIR pin for direction"),
            InitStep(order=6, reg_addr="", value="", description="Pulse STEP pin (rising edge = one step)"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="Step pulse (STEP high)", min="1.9", unit="us"),
            TimingConstraint(parameter="Step pulse (STEP low)", min="1.9", unit="us"),
            TimingConstraint(parameter="Direction setup time", min="650", unit="ns"),
            TimingConstraint(parameter="Wake-up time (nSLEEP)", max="1.7", unit="ms"),
            TimingConstraint(parameter="Supply current (per coil)", max="2500", unit="mA"),
        ],
        notes=[
            "Microstepping: M0/M1/M2 = 000→full, 001→half, 010→1/4, 011→1/8, 100→1/16, 101→1/32",
            "VREF sets current limit: I_max = VREF / (5 * R_sense)",
            "nFAULT output: low on overcurrent, thermal shutdown, or undervoltage",
            "ENABLE pin: active low (low = outputs enabled)",
        ],
    )


def _a4988() -> ComponentKnowledge:
    """Allegro A4988 — Stepper motor driver."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="A4988",
        manufacturer="Allegro MicroSystems",
        mpn="A4988",
        description="DMOS microstepping bipolar stepper motor driver, 2A, 35V",
        category="motor_driver",
        interface=InterfaceType.GPIO,
        registers=[],
        init_sequence=[
            InitStep(order=1, reg_addr="", value="", description="Set nRESET high"),
            InitStep(order=2, reg_addr="", value="", description="Set nSLEEP high"),
            InitStep(order=3, reg_addr="", value="", description="Wait for charge pump", delay_ms=1),
            InitStep(order=4, reg_addr="", value="", description="Configure MS1/MS2/MS3 for microstepping"),
            InitStep(order=5, reg_addr="", value="", description="Pulse STEP pin for motion"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="Step pulse (STEP high)", min="1", unit="us"),
            TimingConstraint(parameter="Step pulse (STEP low)", min="1", unit="us"),
            TimingConstraint(parameter="Direction setup time", min="200", unit="ns"),
            TimingConstraint(parameter="Wake-up time", max="1", unit="ms"),
            TimingConstraint(parameter="Supply current (per coil)", max="2000", unit="mA"),
        ],
        notes=[
            "Microstepping: MS1/MS2/MS3 = 000→full, 100→half, 010→1/4, 110→1/8, 111→1/16",
            "Current limit: I_TripMax = VREF / (8 * R_sense)",
            "Pinout compatible with DRV8825 on most breakout boards",
            "Thermal shutdown at 165C junction temperature",
        ],
    )


def _pca9685() -> ComponentKnowledge:
    """NXP PCA9685 — 16-channel 12-bit PWM/LED driver (I2C)."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="PCA9685",
        manufacturer="NXP",
        mpn="PCA9685",
        description="16-channel, 12-bit PWM I2C LED/servo controller",
        category="pwm_driver",
        interface=InterfaceType.I2C,
        i2c_address="0x40",
        registers=[
            RegisterInfo(address="0x00", name="MODE1", description="Mode register 1",
                         fields=[
                             RegisterField(name="RESTART", bits="7", description="Restart"),
                             RegisterField(name="AI", bits="5", description="Auto-increment"),
                             RegisterField(name="SLEEP", bits="4", description="Sleep mode"),
                         ]),
            RegisterInfo(address="0x01", name="MODE2", description="Mode register 2"),
            RegisterInfo(address="0x06", name="LED0_ON_L", description="LED0 output ON low byte"),
            RegisterInfo(address="0x07", name="LED0_ON_H", description="LED0 output ON high byte"),
            RegisterInfo(address="0x08", name="LED0_OFF_L", description="LED0 output OFF low byte"),
            RegisterInfo(address="0x09", name="LED0_OFF_H", description="LED0 output OFF high byte"),
            RegisterInfo(address="0xFA", name="ALL_LED_ON_L", description="All LED ON low byte"),
            RegisterInfo(address="0xFE", name="PRE_SCALE", description="PWM frequency prescaler"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x00", value="0x10", description="Sleep mode (req'd to set prescaler)"),
            InitStep(order=2, reg_addr="0xFE", value="0x79", description="Set prescaler for 50Hz (servos)"),
            InitStep(order=3, reg_addr="0x00", value="0x20", description="Wake up, auto-increment enabled"),
            InitStep(order=4, reg_addr="", value="", description="Wait for oscillator", delay_ms=1),
            InitStep(order=5, reg_addr="0x00", value="0xA0", description="Restart, auto-increment"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="1000000", unit="Hz"),
            TimingConstraint(parameter="Oscillator startup", max="500", unit="us"),
            TimingConstraint(parameter="Supply current (all LED off)", typical="6", unit="mA"),
            TimingConstraint(parameter="Output current (per pin)", max="25", unit="mA"),
        ],
        notes=[
            "I2C address 0x40-0x7F (A0-A5 pins, 62 addresses)",
            "PWM frequency: prescale = round(25MHz / (4096 * freq)) - 1",
            "For servos: 50Hz, ON=~100-500 (1-2ms pulse width)",
            "Each channel: 4 registers (ON_L, ON_H, OFF_L, OFF_H), 12-bit resolution",
            "OE (Output Enable) pin: active low",
        ],
    )


def _tb6612fng() -> ComponentKnowledge:
    """Toshiba TB6612FNG — Dual DC motor driver."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="TB6612FNG",
        manufacturer="Toshiba",
        mpn="TB6612FNG",
        description="Dual H-bridge DC motor driver, 1.2A continuous, 3.2A peak",
        category="motor_driver",
        interface=InterfaceType.GPIO,
        registers=[],
        init_sequence=[
            InitStep(order=1, reg_addr="", value="", description="Set STBY pin high (enable driver)"),
            InitStep(order=2, reg_addr="", value="", description="Set AIN1/AIN2 for Motor A direction"),
            InitStep(order=3, reg_addr="", value="", description="Apply PWM to PWMA for Motor A speed"),
            InitStep(order=4, reg_addr="", value="", description="Set BIN1/BIN2 for Motor B direction"),
            InitStep(order=5, reg_addr="", value="", description="Apply PWM to PWMB for Motor B speed"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="PWM frequency", max="100000", unit="Hz"),
            TimingConstraint(parameter="Continuous output current", max="1200", unit="mA"),
            TimingConstraint(parameter="Peak output current", max="3200", unit="mA"),
            TimingConstraint(parameter="Supply current (standby)", typical="1", unit="uA"),
        ],
        notes=[
            "2 H-bridge channels: Motor A (AIN1/AIN2/PWMA) and Motor B (BIN1/BIN2/PWMB)",
            "STBY pin: low = standby, high = operate",
            "Truth table: IN1=H,IN2=L → CW; IN1=L,IN2=H → CCW; IN1=IN2 → brake/stop",
            "VM: motor power (4.5-13.5V), VCC: logic power (2.7-5.5V)",
        ],
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTRY: dict[str, callable] = {
    "DRV8825": _drv8825,
    "A4988": _a4988,
    "PCA9685": _pca9685,
    "TB6612FNG": _tb6612fng,
    "TB6612": _tb6612fng,
}
