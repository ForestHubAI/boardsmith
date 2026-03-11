# SPDX-License-Identifier: AGPL-3.0-or-later
"""ComponentKnowledge — structured info extracted from datasheets."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class InterfaceType(str, Enum):
    I2C = "I2C"
    SPI = "SPI"
    UART = "UART"
    GPIO = "GPIO"
    ADC = "ADC"
    PWM = "PWM"
    ANALOG = "ANALOG"
    OTHER = "OTHER"


class RegisterField(BaseModel):
    name: str
    bits: str
    description: str
    default_value: str = ""


class RegisterInfo(BaseModel):
    address: str
    name: str
    description: str = ""
    fields: list[RegisterField] = Field(default_factory=list)


class InitStep(BaseModel):
    model_config = {"populate_by_name": True}

    order: int
    reg_addr: str = Field(default="", alias="register")
    value: str = ""
    description: str = ""
    delay_ms: Optional[int] = None


class TimingConstraint(BaseModel):
    parameter: str
    min: str = ""
    typical: str = ""
    max: str = ""
    unit: str = ""


class PinInfo(BaseModel):
    name: str
    number: str
    function: str
    electrical_type: str


class ExtractedSections(BaseModel):
    pinout: Optional[str] = None
    register_map: Optional[str] = None
    init_sequence: Optional[str] = None
    timing: Optional[str] = None
    application_circuit: Optional[str] = None


class ElectricalRatings(BaseModel):
    """Operating and absolute maximum electrical ratings from datasheet."""
    vdd_min: Optional[float] = None        # V — minimum supply voltage
    vdd_max: Optional[float] = None        # V — maximum supply voltage
    vdd_abs_max: Optional[float] = None    # V — absolute maximum (damage threshold)
    io_voltage_min: Optional[float] = None # V — minimum IO / logic level
    io_voltage_max: Optional[float] = None # V — maximum IO / logic level
    current_supply_ma: Optional[float] = None   # mA — typical supply current
    current_supply_max_ma: Optional[float] = None  # mA — max supply current
    temp_min_c: Optional[float] = None     # °C — minimum operating temperature
    temp_max_c: Optional[float] = None     # °C — maximum operating temperature
    is_5v_tolerant: bool = False           # IO pins tolerate 5 V when VDD < 5 V


class ComponentKnowledge(BaseModel):
    version: str = "1.0.0"
    component_id: str
    name: str
    manufacturer: str = ""
    mpn: str = ""
    description: str = ""
    category: str = "unknown"
    interface: InterfaceType = InterfaceType.OTHER
    i2c_address: Optional[str] = None
    spi_mode: Optional[int] = None
    pins: list[PinInfo] = Field(default_factory=list)
    registers: list[RegisterInfo] = Field(default_factory=list)
    init_sequence: list[InitStep] = Field(default_factory=list)
    timing_constraints: list[TimingConstraint] = Field(default_factory=list)
    electrical_ratings: Optional[ElectricalRatings] = None
    datasheet_url: Optional[str] = None
    datasheet_local_path: Optional[str] = None
    extracted_sections: ExtractedSections = Field(default_factory=ExtractedSections)
    notes: list[str] = Field(default_factory=list)
