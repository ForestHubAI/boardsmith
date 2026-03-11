# SPDX-License-Identifier: AGPL-3.0-or-later
"""B2. Requirements Normalizer — converts vague statements to typed ranges."""
from __future__ import annotations

from dataclasses import dataclass, field

from boardsmith_hw.intent_parser import RequirementsSpec


@dataclass
class NormalizedRequirements:
    raw: RequirementsSpec
    supply_voltage_range: tuple[float, float] = (3.0, 3.6)  # (min, max)
    temperature_range: tuple[float, float] = (-40.0, 85.0)
    max_cost_usd: float | None = None
    mcu_family: str = "esp32"
    required_interfaces: list[str] = field(default_factory=list)
    sensing_modalities: list[str] = field(default_factory=list)
    sensor_mpns: list[str] = field(default_factory=list)       # explicit MPNs from prompt
    actuation_modalities: list[str] = field(default_factory=list)
    functional_goals: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    confidence: float = 0.75


_VOLTAGE_DEFAULTS: dict[str | None, tuple[float, float]] = {
    "3.3": (3.0, 3.6),
    "5.0": (4.5, 5.5),
    "5": (4.5, 5.5),
    None: (3.0, 3.6),
}


def normalize(spec: RequirementsSpec) -> NormalizedRequirements:
    """Convert RequirementsSpec to typed, ranged NormalizedRequirements."""
    # Voltage range
    v = spec.supply_voltage
    if v is None:
        v_range = (3.0, 3.6)
    elif v <= 3.6:
        v_range = (2.7, 3.6)
    else:
        v_range = (4.5, 5.5)

    # Temperature range
    t_min = spec.temp_min_c if spec.temp_min_c is not None else -40.0
    t_max = spec.temp_max_c if spec.temp_max_c is not None else 85.0

    # MCU family — LLM may return a list for dual-MCU designs; pick first
    mcu = spec.mcu_family or "esp32"
    if isinstance(mcu, list):
        mcu = mcu[0] if mcu else "esp32"

    # Interfaces — ensure I2C if sensors requested (by modality or explicit MPN)
    interfaces = list(spec.required_interfaces)
    if (spec.sensing_modalities or spec.sensor_mpns) and "I2C" not in interfaces and "SPI" not in interfaces:
        interfaces.append("I2C")

    # Confidence — average of per-field confidence (skip 0.0 values which mean
    # "not specified/not applicable", not "uncertain"), penalize unresolved
    cf = spec.confidence_per_field
    specified = {k: v for k, v in cf.items() if v > 0}
    base_conf = sum(specified.values()) / len(specified) if specified else 0.7
    unresolved_penalty = 0.05 * len(spec.unresolved)
    confidence = round(max(0.1, min(1.0, base_conf - unresolved_penalty)), 4)

    return NormalizedRequirements(
        raw=spec,
        supply_voltage_range=v_range,
        temperature_range=(t_min, t_max),
        max_cost_usd=spec.max_unit_cost_usd,
        mcu_family=mcu,
        required_interfaces=interfaces,
        sensing_modalities=spec.sensing_modalities,
        sensor_mpns=spec.sensor_mpns,
        actuation_modalities=spec.actuation_modalities,
        functional_goals=spec.functional_goals,
        unresolved=spec.unresolved,
        confidence=confidence,
    )
