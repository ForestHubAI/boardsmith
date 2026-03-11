# SPDX-License-Identifier: AGPL-3.0-or-later
"""Peripheral Pattern Library — formalized bus pattern rules.

Encodes the electrical best-practices for each bus type:
  - I2C: pull-up resistor sizing from bus capacitance + speed
  - SPI: CS pull-ups, SCK series resistors, max freq enforcement
  - UART: TX/RX series resistors, level shifter selection
  - CAN: termination resistor, transceiver selection
  - USB: D+/D- series resistors, ESD protection IC insertion

Each pattern function returns a list of PassiveComponents (or extra components)
to be inserted into the topology by the synthesizer.

When an MCU Device Profile with PeripheralPatterns (Domain 9) is available,
the pattern values (resistor sizes, recommended ICs) are taken from the profile.
Otherwise, sensible defaults are used.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# I2C Pattern — Pull-up resistor sizing
# ---------------------------------------------------------------------------

def i2c_pullup_value(speed_hz: int = 100_000, bus_cap_pf: float = 50.0) -> str:
    """Compute recommended I2C pull-up value.

    Rule of thumb:
      R_pull = t_rise / (0.8473 × C_bus)
    Where t_rise is the maximum rise time per I2C spec:
      Standard mode (100 kHz): 1000 ns
      Fast mode (400 kHz):      300 ns
      Fast mode+ (1 MHz):       120 ns
    """
    if speed_hz >= 1_000_000:
        t_rise_ns = 120.0
    elif speed_hz >= 400_000:
        t_rise_ns = 300.0
    else:
        t_rise_ns = 1000.0

    if bus_cap_pf <= 0:
        bus_cap_pf = 50.0

    r_ohm = (t_rise_ns * 1e-9) / (0.8473 * bus_cap_pf * 1e-12)

    # Snap to standard E12 values
    if r_ohm >= 8200:
        return "10k"
    elif r_ohm >= 3900:
        return "4.7k"
    elif r_ohm >= 1800:
        return "2.2k"
    else:
        return "1k"


def i2c_pullup_from_profile(profile, bus_name: str = "i2c0") -> str:
    """Extract I2C pull-up value from MCU profile if available."""
    if profile is None:
        return "4.7k"
    if profile.peripheral_patterns and profile.peripheral_patterns.i2c:
        rule = profile.peripheral_patterns.i2c.pullup_value_rule
        if rule:
            # Parse first value from rule like "4.7kΩ for ≤100kHz, 2.2kΩ for 400kHz"
            # Default to 4.7k for standard mode
            if "2.2k" in rule and "400" in rule:
                return "2.2k"  # Fast mode default from profile
            return "4.7k"
    return "4.7k"


# ---------------------------------------------------------------------------
# SPI Pattern — CS pull-up + SCK series resistor
# ---------------------------------------------------------------------------

def spi_passives_from_profile(profile, bus, reg_rail: str, uid_fn):
    """Generate SPI pattern passives from MCU profile.

    Returns list of PassiveComponents for:
    - CS pull-up resistors (10kΩ per CS line) — keeps slaves deselected during boot
    - SCK series resistor (33Ω) — reduces EMI and ringing on clock line
    """
    from boardsmith_hw.topology_synthesizer import PassiveComponent

    passives = []

    spi_pattern = None
    if profile and profile.peripheral_patterns:
        spi_pattern = profile.peripheral_patterns.spi

    # SCK series resistor
    sck_r = 33  # default
    if spi_pattern and spi_pattern.series_resistor_sck_ohm:
        sck_r = spi_pattern.series_resistor_sck_ohm

    sck_pin = bus.pin_assignments.get("SCK", bus.pin_assignments.get("CLK", ""))
    if sck_pin:
        passives.append(PassiveComponent(
            comp_id=uid_fn("R"),
            category="resistor",
            value=str(sck_r),
            unit="Ω",
            purpose=f"spi_sck_series_{bus.name}",
            nets=[f"{bus.name.upper()}_SCK_MCU", f"{bus.name.upper()}_SCK"],
            package="0402",
            mpn_suggestion=f"RC0402FR-07{sck_r}RL",
            unit_cost_usd=0.01,
        ))

    # CS pull-ups — keep slave CS high (deselected) during MCU boot
    cs_pullup = True
    if spi_pattern is not None:
        cs_pullup = spi_pattern.cs_pullup

    if cs_pullup:
        for pin_name, pin_val in bus.pin_assignments.items():
            if pin_name.startswith("CS_"):
                slave_id = pin_name[3:]  # Remove "CS_" prefix
                passives.append(PassiveComponent(
                    comp_id=uid_fn("R"),
                    category="resistor",
                    value="10k",
                    unit="Ω",
                    purpose=f"spi_cs_pullup_{slave_id}",
                    nets=[reg_rail, f"{bus.name.upper()}_{pin_name}"],
                    package="0402",
                    mpn_suggestion="RC0402FR-0710KL",
                    unit_cost_usd=0.01,
                ))

    return passives


# ---------------------------------------------------------------------------
# UART Pattern — TX/RX series resistors
# ---------------------------------------------------------------------------

def uart_passives_from_profile(profile, bus, uid_fn):
    """Generate UART pattern passives from MCU profile.

    Returns list of PassiveComponents for:
    - TX series resistor — current limiting, protects against bus contention
    - RX series resistor — ESD/overcurrent protection on input
    """
    from boardsmith_hw.topology_synthesizer import PassiveComponent

    passives = []

    uart_pattern = None
    if profile and profile.peripheral_patterns:
        uart_pattern = profile.peripheral_patterns.uart

    series_r = 470  # default: 470Ω
    if uart_pattern and uart_pattern.rx_tx_series_resistor:
        series_r = uart_pattern.rx_tx_series_resistor

    tx_pin = bus.pin_assignments.get("TX", "")
    rx_pin = bus.pin_assignments.get("RX", "")

    if tx_pin:
        passives.append(PassiveComponent(
            comp_id=uid_fn("R"),
            category="resistor",
            value=str(series_r),
            unit="Ω",
            purpose=f"uart_tx_series_{bus.name}",
            nets=[f"{bus.name}_TX_MCU", f"{bus.name}_TX"],
            package="0402",
            mpn_suggestion=f"RC0402FR-07{series_r}RL",
            unit_cost_usd=0.01,
        ))

    if rx_pin:
        passives.append(PassiveComponent(
            comp_id=uid_fn("R"),
            category="resistor",
            value=str(series_r),
            unit="Ω",
            purpose=f"uart_rx_series_{bus.name}",
            nets=[f"{bus.name}_RX_MCU", f"{bus.name}_RX"],
            package="0402",
            mpn_suggestion=f"RC0402FR-07{series_r}RL",
            unit_cost_usd=0.01,
        ))

    return passives


# ---------------------------------------------------------------------------
# CAN Pattern — Termination resistor
# ---------------------------------------------------------------------------

def can_passives_from_profile(profile, bus, uid_fn):
    """Generate CAN pattern passives from MCU profile.

    Returns list of PassiveComponents for:
    - 120Ω termination resistor across CANH / CANL
    """
    from boardsmith_hw.topology_synthesizer import PassiveComponent

    passives = []

    can_pattern = None
    if profile and profile.peripheral_patterns:
        can_pattern = profile.peripheral_patterns.can

    term_r = 120  # CAN standard: 120Ω
    if can_pattern and can_pattern.termination_resistor_ohm:
        term_r = can_pattern.termination_resistor_ohm

    passives.append(PassiveComponent(
        comp_id=uid_fn("R"),
        category="resistor",
        value=str(term_r),
        unit="Ω",
        purpose=f"can_termination_{bus.name}",
        nets=[f"{bus.name.upper()}_CANH", f"{bus.name.upper()}_CANL"],
        package="0402",
        mpn_suggestion="RC0402FR-07120RL",
        unit_cost_usd=0.01,
    ))

    return passives


# ---------------------------------------------------------------------------
# USB Pattern — D+/D- series resistors + ESD protection
# ---------------------------------------------------------------------------

def usb_passives_from_profile(profile, bus, uid_fn):
    """Generate USB pattern passives from MCU profile.

    Returns list of PassiveComponents for:
    - D+ series resistor (27Ω) — impedance matching for USB 2.0
    - D- series resistor (27Ω) — impedance matching for USB 2.0
    - ESD protection IC (USBLC6-2SC6) — placed on VBUS/D+/D- lines
    """
    from boardsmith_hw.topology_synthesizer import PassiveComponent

    passives = []

    usb_pattern = None
    if profile and profile.peripheral_patterns:
        usb_pattern = profile.peripheral_patterns.usb

    series_r = 27  # USB 2.0 standard: 27Ω
    if usb_pattern and usb_pattern.dp_dm_series_resistor_ohm:
        series_r = usb_pattern.dp_dm_series_resistor_ohm

    # D+ series resistor
    passives.append(PassiveComponent(
        comp_id=uid_fn("R"),
        category="resistor",
        value=str(series_r),
        unit="Ω",
        purpose=f"usb_dp_series_{bus.name}",
        nets=[f"{bus.name.upper()}_DP_MCU", f"{bus.name.upper()}_DP"],
        package="0402",
        mpn_suggestion="RC0402FR-0727RL",
        unit_cost_usd=0.01,
    ))

    # D- series resistor
    passives.append(PassiveComponent(
        comp_id=uid_fn("R"),
        category="resistor",
        value=str(series_r),
        unit="Ω",
        purpose=f"usb_dm_series_{bus.name}",
        nets=[f"{bus.name.upper()}_DM_MCU", f"{bus.name.upper()}_DM"],
        package="0402",
        mpn_suggestion="RC0402FR-0727RL",
        unit_cost_usd=0.01,
    ))

    # ESD protection IC
    esd_ic = "USBLC6-2SC6"
    if usb_pattern and usb_pattern.esd_protection_ic:
        esd_ic = usb_pattern.esd_protection_ic

    passives.append(PassiveComponent(
        comp_id=uid_fn("U"),
        category="esd_protection",
        value=esd_ic,
        unit="",
        purpose=f"usb_esd_{bus.name}",
        nets=[f"{bus.name.upper()}_DP", f"{bus.name.upper()}_DM", "GND", "VBUS"],
        package="SOT-23-6",
        mpn_suggestion=esd_ic,
        unit_cost_usd=0.15,
    ))

    return passives


# ---------------------------------------------------------------------------
# Master dispatcher — synthesize all bus-pattern passives
# ---------------------------------------------------------------------------

def synthesize_bus_pattern_passives(
    buses,
    mcu_profile,
    reg_rail: str,
    uid_fn,
    assumptions: list[str],
) -> list:
    """Generate all bus-pattern passives for the given topology buses.

    Uses MCU profile PeripheralPatterns when available, falls back to defaults.
    """
    from boardsmith_hw.topology_synthesizer import PassiveComponent

    passives: list[PassiveComponent] = []

    for bus in buses:
        if bus.bus_type == "SPI":
            spi_p = spi_passives_from_profile(mcu_profile, bus, reg_rail, uid_fn)
            if spi_p:
                passives.extend(spi_p)
                assumptions.append(
                    f"SPI pattern ({bus.name}): SCK series resistor + "
                    f"{sum(1 for p in spi_p if 'cs_pullup' in p.purpose)} CS pull-up(s)"
                )

        elif bus.bus_type == "UART":
            uart_p = uart_passives_from_profile(mcu_profile, bus, uid_fn)
            if uart_p:
                passives.extend(uart_p)
                log.info(
                    "B4 UART pattern (%s): TX/RX series resistors (%sΩ)",
                    bus.name, uart_p[0].value,
                )

        elif bus.bus_type == "CAN":
            can_p = can_passives_from_profile(mcu_profile, bus, uid_fn)
            if can_p:
                passives.extend(can_p)
                log.info(
                    "B4 CAN pattern (%s): %sΩ termination resistor",
                    bus.name, can_p[0].value,
                )

        elif bus.bus_type == "USB":
            usb_p = usb_passives_from_profile(mcu_profile, bus, uid_fn)
            if usb_p:
                passives.extend(usb_p)
                esd_parts = [p for p in usb_p if p.category == "esd_protection"]
                esd_name = esd_parts[0].value if esd_parts else "none"
                assumptions.append(
                    f"USB pattern ({bus.name}): D+/D- series resistors + "
                    f"ESD protection ({esd_name})"
                )

        # I2C pull-ups are already handled in _synthesize_passives
        # but we enhance with profile-driven values
        elif bus.bus_type == "I2C":
            # Profile-aware I2C pull-up value (replaces hardcoded 4.7k)
            pullup = i2c_pullup_from_profile(mcu_profile, bus.name)
            if pullup != "4.7k":
                assumptions.append(
                    f"I2C pattern ({bus.name}): profile-recommended "
                    f"pull-up {pullup} (instead of default 4.7kΩ)"
                )

    return passives
