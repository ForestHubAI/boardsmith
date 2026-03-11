# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canonical component schema — shared TypedDicts for both compiler and synthesizer."""
from __future__ import annotations

from typing import Any, TypedDict


class ElectricalRatings(TypedDict, total=False):
    vdd_min: float
    vdd_max: float
    io_voltage_min: float
    io_voltage_max: float
    io_voltage_nominal: float
    is_5v_tolerant: bool
    logic_high_min: float
    logic_low_max: float
    current_draw_typical_ma: float
    current_draw_max_ma: float
    abs_max_voltage: float
    temp_min_c: float
    temp_max_c: float
    drive_strength_ma: float
    input_capacitance_pf: float
    sleep_current_ua: float        # deep-sleep / shutdown current
    quiescent_current_ua: float    # no-load quiescent current (power ICs)


class TimingCaps(TypedDict, total=False):
    i2c_max_clock_hz: int
    i2c_modes: list[str]       # ["standard", "fast", "fast_plus", "high_speed"]
    spi_max_clock_hz: int
    spi_modes: list[int]       # CPOL/CPHA modes 0-3
    uart_max_baud: int
    gpio_max_freq_hz: int


class InitContractTemplate(TypedDict, total=False):
    phases: list[dict]


class EdaBinding(TypedDict, total=False):
    """EDA tool binding quality metadata.

    Tracks the verification status of symbol/footprint/pinmap bindings
    for each component. Used as quality gate: only 'verified' components
    are allowed in production designs.
    """
    symbol_lib: str              # "boardsmith_symbols" | "kicad_default" | "jlcpcb"
    footprint_lib: str           # "boardsmith_footprints" | "kicad_default"
    pinmap_verified: bool        # Pinmap checked against datasheet?
    footprint_variants: list[str]  # ["QFN-28", "TQFP-32"] — alternative packages
    pinmap_hash: str             # SHA256 of pinmap for drift detection
    quality_state: str           # "unverified" | "validated" | "verified"
    last_verified: str           # ISO 8601 date


class SubstituteInfo(TypedDict, total=False):
    """Component substitution/lifecycle metadata.

    Enables the agent to find drop-in replacements and assess supply risk.
    """
    approved_substitutes: list[str]   # MPNs that are drop-in replacements
    class_substitutes: list[str]      # Category-based (e.g. "any_3.3v_ldo_800ma")
    drop_in_constraint: str           # "drop-in" | "needs-reroute" | "needs-redesign"
    supply_risk_score: int            # 1 (safe, multi-source) – 5 (single-source, EOL risk)
    lifecycle_status: str             # "active" | "nrnd" | "eol" | "obsolete"
    second_sources: list[str]         # Alternative manufacturers


class ComponentEntry(TypedDict, total=False):
    mpn: str
    manufacturer: str
    name: str
    category: str              # "mcu" | "sensor" | "display" | "actuator" | "memory" | "power" | "comms" | "other"
    sub_type: str              # within-category classifier, e.g. "ldo" | "imu" | "oled" | "usb-uart"
    family: str                # Component family, e.g. "AMS1117", "STM32F1" — for grouping variants
    series: str                # Marketing series, e.g. "ESP32-WROOM", "BME280" — for search
    interface_types: list[str]
    package: str
    mounting: str              # "smd" | "tht" | "module"
    pin_count: int
    description: str
    electrical_ratings: ElectricalRatings
    timing_caps: TimingCaps
    known_i2c_addresses: list[str]   # hex strings e.g. ["0x76", "0x77"]
    i2c_address_selectable: bool
    init_contract_coverage: bool     # True if init_contract_template is provided
    init_contract_template: InitContractTemplate
    unit_cost_usd: float
    tags: list[str]
    datasheet_url: str
    status: str                # "active" | "nrnd" | "obsolete"
    capabilities: dict[str, Any]     # category-specific structured specs (JSON blob in SQLite)
    library_support: list[str]       # ["arduino", "micropython", "circuitpython", "esp-idf", ...]
    tier: str                        # "community" | "enterprise" — controls CE/EE availability
    eda_binding: EdaBinding            # EDA symbol/footprint verification state
    substitute_info: SubstituteInfo    # Lifecycle & substitute metadata
