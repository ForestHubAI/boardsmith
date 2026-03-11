# SPDX-License-Identifier: AGPL-3.0-or-later
"""B4. Topology Synthesizer — creates bus topology from selected components."""
from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass, field

from boardsmith_hw.component_selector import ComponentSelection, SelectedComponent

# ---------------------------------------------------------------------------
# MCU Device Profile integration (Layer 1 — Hardware Knowledge)
# ---------------------------------------------------------------------------

def _load_mcu_profile(mpn: str):
    """Try to load an MCU Device Profile from the knowledge DB.

    Returns the profile or None if not available (graceful fallback).
    """
    try:
        from shared.knowledge.mcu_profiles import get as get_mcu_profile
        return get_mcu_profile(mpn)
    except ImportError:
        return None
    except Exception:
        return None


def _pick_mcu_pins_from_profile(
    profile, bus_type: str, pin_index: int = 0,
    used_pins: set[str] | None = None,
) -> dict[str, str] | None:
    """Extract pin assignments from an MCU Device Profile.

    Uses the recommended_pinmaps from the profile instead of hardcoded tables.
    ``pin_index`` selects which of the matching pinmaps to use (0 = first UART,
    1 = second UART, etc.) so multiple UART buses get distinct pin sets.

    ``used_pins`` (optional) tracks pins already assigned to other buses.  When a
    candidate pinmap collides with used_pins the function tries the next available
    alt pinmap before falling back.

    Returns None if no suitable pinmap found (fallback to legacy logic).
    """
    if profile is None or not profile.pinout.recommended_pinmaps:
        return None

    bus_lower = bus_type.lower()
    matches = [pm for pm in profile.pinout.recommended_pinmaps if pm.name.lower().startswith(bus_lower)]

    if not matches:
        return None

    # Select the pinmap at pin_index, then check for conflicts with used_pins.
    # If conflicting, try subsequent (alt) pinmaps.
    _used = used_pins or set()
    start_idx = min(pin_index, len(matches) - 1)
    for i in range(start_idx, len(matches)):
        candidate = dict(matches[i].mappings)
        if not _used.intersection(candidate.values()):
            return candidate
    # All pinmaps conflict — fall back to last match (best effort)
    return dict(matches[-1].mappings)


def _get_reserved_pins(profile) -> set[str]:
    """Get set of reserved pin names that must NOT be used as GPIO."""
    if profile is None:
        return set()
    return {rp.pin_name for rp in profile.pinout.reserved_pins if not rp.can_use_as_gpio}


def _get_boot_strap_pins(profile) -> set[str]:
    """Get set of boot-strap pin names that should be avoided for general use."""
    if profile is None:
        return set()
    pins = set()
    for pin in profile.pinout.pins:
        if pin.boot_strap:
            pins.add(pin.pin_name)
    if profile.boot:
        for bmp in profile.boot.boot_mode_pins:
            pins.add(bmp.pin)
    return pins

log = logging.getLogger(__name__)


@dataclass
class TopologyBus:
    name: str
    bus_type: str           # "I2C" | "SPI" | "UART"
    master_id: str
    slave_ids: list[str]
    pin_assignments: dict[str, str]     # signal -> gpio name
    slave_addresses: dict[str, str]     # slave_id -> hex address


@dataclass
class TopologyPowerRail:
    name: str
    voltage_nominal: float
    voltage_min: float
    voltage_max: float


@dataclass
class PassiveComponent:
    """A passive component (resistor, capacitor) synthesized from topology rules."""
    comp_id: str
    category: str           # "resistor" | "capacitor"
    value: str              # e.g. "4.7k", "100n", "10u"
    unit: str               # "Ω" | "F"
    purpose: str            # e.g. "i2c_pullup_sda", "decoupling_vdd", "bulk_rail"
    nets: list[str]         # e.g. ["3V3", "I2C0_SDA"]
    package: str            # "0402" | "0603"
    mpn_suggestion: str     # suggested MPN for procurement
    unit_cost_usd: float


@dataclass
class VoltageRegulator:
    """An LDO voltage regulator synthesized when supply voltage > MCU VDD."""
    comp_id: str
    mpn: str                # e.g. "AMS1117-3.3" or "AP2112K-3.3TRG1"
    manufacturer: str
    input_rail: str         # e.g. "VIN_5V"
    output_rail: str        # e.g. "3V3_REG"
    input_voltage_nom: float
    output_voltage_nom: float
    max_current_ma: float
    package: str
    unit_cost_usd: float


@dataclass
class AnalogNet:
    """A point-to-point analog signal net created by circuit template instantiation."""
    name: str
    pins: list[tuple[str, str]]     # (component_id, pin_name)
    is_bus: bool = False
    is_power: bool = False


@dataclass
class SynthesizedTopology:
    components: list[SelectedComponent]
    buses: list[TopologyBus]
    power_rails: list[TopologyPowerRail]
    passives: list[PassiveComponent]
    voltage_regulators: list[VoltageRegulator]
    assumptions: list[str]
    notes: list[str] = field(default_factory=list)
    analog_nets: list[AnalogNet] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Analog circuit template helpers
# ---------------------------------------------------------------------------

# E12 resistor series mantissas (×10 gives the standard values in the first decade)
_E12_MANTISSAS = [10, 12, 15, 18, 22, 27, 33, 39, 47, 56, 68, 82]


def _nearest_e12(r_ohm: float) -> float:
    """Round a resistance value to the nearest E12 standard value."""
    if r_ohm <= 0:
        return 10.0  # fallback to 10Ω
    decade = 10.0 ** math.floor(math.log10(r_ohm))
    mantissa = r_ohm / decade
    nearest = min(_E12_MANTISSAS, key=lambda v: abs(v / 10.0 - mantissa))
    return nearest / 10.0 * decade


def _format_passive_value(value: float, unit: str) -> str:
    """Format a passive value with SI prefix (e.g. 4700 Ω → '4.7k', 1e-7 F → '100n')."""
    if unit == "Ω":
        if value >= 1e6:
            return f"{value/1e6:.3g}M"
        if value >= 1e3:
            return f"{value/1e3:.3g}k"
        return f"{value:.3g}"
    if unit == "F":
        if value >= 1e-3:
            return f"{value/1e-3:.3g}m"
        if value >= 1e-6:
            return f"{value/1e-6:.3g}u"
        if value >= 1e-9:
            return f"{value/1e-9:.3g}n"
        return f"{value/1e-12:.3g}p"
    return f"{value:.3g}"


# Module-level MPN lookup for passive components without explicit catalog entries.
# Used by _instantiate_circuit_template() (analog template resistors) and by the
# MCU mandatory-component loop in synthesize_topology().
_MANDATORY_PASSIVE_MPN: dict[tuple[str, str], str] = {
    ("cap",      "100nF"): "GRM155R71C104KA88D",
    ("cap",      "10µF"):  "GRM188R61A106KE69D",
    ("cap",      "10uF"):  "GRM188R61A106KE69D",
    ("cap",      "1µF"):   "GRM155R60J105KE19D",
    ("cap",      "1uF"):   "GRM155R60J105KE19D",
    ("cap",      "4.7µF"): "GRM188R60J475KE19D",
    ("cap",      "15pF"):  "GRM1555C1H150GA01D",
    ("cap",      "20pF"):  "GRM1555C1H200GA01D",
    ("resistor", "27Ω"):   "RC0402FR-0727RL",
    ("resistor", "33Ω"):   "RC0402FR-0733RL",
    ("resistor", "1kΩ"):   "RC0402FR-071KL",
    ("resistor", "2.2kΩ"): "RC0402FR-072K2L",
    ("resistor", "4.7kΩ"): "RC0402FR-074K7L",
    ("resistor", "10kΩ"):  "RC0402FR-0710KL",
    ("resistor", "100Ω"):  "RC0402FR-07100RL",
    ("resistor", "330Ω"):  "RC0402FR-07330RL",
    ("ferrite",  "600Ω"):  "BLM18PG601SN1D",
}


def _instantiate_circuit_template(
    template_id: str,
    opamp_comp_id: str,
    prefix: str,
    params: dict[str, float],
    input_net: str,
    output_net: str,
) -> tuple[list[PassiveComponent], list[AnalogNet]]:
    """Instantiate a circuit template: resolve formulas, create PassiveComponents + AnalogNets.

    Args:
        template_id:  CircuitTemplate.id to instantiate (e.g. "noninverting_amp")
        opamp_comp_id: component_id of the op-amp/comparator in the HIR (e.g. "U_MCP6002")
        prefix:       unique prefix for generated net/comp names (e.g. "OPAMP0")
        params:       template parameters dict (e.g. {"gain": 3.3, "R_in": 10000.0})
        input_net:    external net name for the IN+ node (e.g. "SENSOR_VOUT")
        output_net:   external net name for the OUT node (e.g. "ADC_CH0")

    Returns:
        (passives, analog_nets) — both lists can be empty on template error.
    """
    try:
        from knowledge.circuit_templates import CircuitTemplateLibrary
    except ImportError:
        return [], []

    lib = CircuitTemplateLibrary()
    template = lib.get(template_id)
    if template is None:
        log.warning("B4 analog: circuit template '%s' not found — skipping", template_id)
        return [], []

    passives: list[PassiveComponent] = []
    analog_nets: list[AnalogNet] = []

    # Evaluate passive recipes
    _passive_idx: dict[str, int] = {}
    for recipe in template.passive_recipes:
        try:
            value_f = float(eval(recipe.value_expr, {"__builtins__": {}}, {**params, "math": math}))  # noqa: S307
        except Exception as exc:
            log.warning("B4 analog: formula eval failed for %s.%s: %s", template_id, recipe.comp_id_key, exc)
            continue

        if recipe.category == "resistor":
            value_f = _nearest_e12(value_f)

        comp_id = f"{prefix}_{recipe.comp_id_key}"
        net_names = [t.format(prefix=prefix) for t in recipe.nets_template]
        _val_str = _format_passive_value(value_f, recipe.unit)
        # Use recipe mpn_hint if available; otherwise fall back to the same
        # catalog lookup used for mandatory MCU passives (e.g. "10kΩ" resistor
        # → "RC0402FR-0710KL").  Prevents empty-MPN rows in the BOM.
        # Note: _format_passive_value returns "10k" not "10kΩ" — append unit
        # to match the key format in _MANDATORY_PASSIVE_MPN ("10kΩ", "1µF" etc).
        _cat_key = "cap" if recipe.category == "capacitor" else recipe.category[:8] if recipe.category else ""
        _val_with_unit = _val_str + recipe.unit  # e.g. "10k" + "Ω" = "10kΩ"
        _mpn_fallback = _MANDATORY_PASSIVE_MPN.get((_cat_key, _val_with_unit),
                        _MANDATORY_PASSIVE_MPN.get((_cat_key, _val_str), ""))
        passives.append(PassiveComponent(
            comp_id=comp_id,
            category=recipe.category,
            value=_val_str,
            unit=recipe.unit,
            purpose=f"{template_id}_{recipe.comp_id_key}",
            nets=net_names,
            package=recipe.package,
            mpn_suggestion=recipe.mpn_hint or _mpn_fallback,
            unit_cost_usd=0.01,
        ))

    # Evaluate net templates
    for net_tmpl in template.net_templates:
        raw_name = net_tmpl.name_template.format(prefix=prefix)
        # Remap {prefix}_IN → external input_net, {prefix}_OUT → external output_net
        if raw_name == f"{prefix}_IN":
            net_name = input_net
        elif raw_name == f"{prefix}_OUT":
            net_name = output_net
        else:
            net_name = raw_name

        pins: list[tuple[str, str]] = []
        for role_key, pin_name in net_tmpl.pins:
            if role_key == "opamp":
                cid = opamp_comp_id
            else:
                cid = f"{prefix}_{role_key}"
            pins.append((cid, pin_name))

        analog_nets.append(AnalogNet(name=net_name, pins=pins))

    return passives, analog_nets


def _default_params_for_template(template_id: str) -> dict[str, float]:
    """Return parameter defaults from the template definition.

    Falls back to a broad set of common defaults if the template cannot be loaded.
    """
    try:
        from knowledge.circuit_templates import CircuitTemplateLibrary
        lib = CircuitTemplateLibrary()
        tmpl = lib.get(template_id)
        if tmpl:
            defaults: dict[str, float] = {}
            for name, spec in tmpl.parameters.items():
                try:
                    defaults[name] = float(spec.get("default", 1.0))
                except (TypeError, ValueError):
                    defaults[name] = 1.0
            return defaults
    except ImportError:
        pass
    # Broad fallback covering all built-in template parameter names
    return {
        "gain": 2.0, "gain_mag": 2.0, "R_in": 10000.0,
        "R1": 10000.0, "R2": 10000.0,
        "threshold_v": 1.65, "vcc_v": 3.3,
        "R_hyst": 100000.0, "R_pull": 10000.0,
        "R": 10000.0, "C": 1e-7,
        "f_c": 100.0,
    }


def _infer_template_id(comp: SelectedComponent, prompt_lower: str) -> str:
    """Infer the best circuit template ID for an analog component."""
    # Comparator/Schmitt-trigger keywords → comparator templates
    if any(kw in prompt_lower for kw in ("schmitt", "hysteresis", "hysterese", "zero-crossing")):
        return "comparator_hysteresis"
    if any(kw in prompt_lower for kw in ("comparator", "komparator", "nulldurchgang", "threshold", "schwellwert")):
        return "comparator_fixed"
    # Voltage follower / buffer
    if any(kw in prompt_lower for kw in ("follower", "spannungsfolger", "unity gain", "buffer amplifier", "buffer")):
        return "voltage_follower"
    # Non-inverting MUST be checked before inverting (substring order matters)
    if any(kw in prompt_lower for kw in ("nichtinvertierend", "non-inverting", "noninverting")):
        return "noninverting_amp"
    # Inverting amplifier
    if any(kw in prompt_lower for kw in ("inverting", "invertierend")):
        return "inverting_amp"
    # Non-inverting amplifier — default for op-amp keyword
    return "noninverting_amp"


# Default ESP32 I2C pin assignments
_ESP32_I2C_PINS = {"SDA": "21", "SCL": "22"}
_ESP32_SPI_PINS = {"MOSI": "23", "MISO": "19", "SCK": "18"}
_ESP32_CS_START = 5     # CS pin starts here and increments (legacy, used as fallback)

# ESP32-S3 has different default pin assignments
_ESP32S3_I2C_PINS = {"SDA": "8", "SCL": "9"}
_ESP32S3_SPI_PINS = {"MOSI": "11", "MISO": "13", "SCK": "12"}
_ESP32S3_UART_PINS = {"TX": "TXD0", "RX": "RXD0"}

# Default STM32 pins
_STM32_I2C_PINS = {"SDA": "PB7", "SCL": "PB6"}
_STM32_SPI_PINS = {"MOSI": "PA7", "MISO": "PA6", "SCK": "PA5"}

# MCU-specific SPI CS pin lists (in priority order, up to 4 CS pins per MCU)
# These are real GPIO names matching the MCU's KiCad symbol pins.
_MCU_CS_PINS: dict[str, list[str]] = {
    "ESP32-WROOM-32":    ["IO5",  "IO15", "IO2",  "IO0"],
    "ESP32-C3-WROOM-02": ["IO3",  "IO2",  "IO4",  "IO5"],
    "ESP32-S3-WROOM-1":  ["IO10", "IO3",  "IO4",  "IO5"],
    "STM32F103C8T6":     ["PA4",  "PB12", "PB0",  "PA3"],
    "STM32F405RGT6":     ["PA4",  "PA15", "PE3",  "PB12"],
    "STM32G431CBU6":     ["PA4",  "PB12", "PB0",  "PA3"],
    "STM32F746ZGT6":     ["PA4",  "PB12", "PE11", "PG10"],
    "STM32H743VIT6":     ["PA4",  "PB12", "PE11", "PG10"],
    "LPC55S69JBD100":    ["PIO1_1","PIO0_13","PIO0_14","PIO0_15"],
    "MIMXRT1062DVJ6A":   ["GPIO_SD_B0_01","GPIO_AD_B0_00","GPIO_AD_B0_01","GPIO_AD_B0_04"],
    "RP2040":            ["GP9",  "GP17", "GP13", "GP21"],
    "nRF52840":          ["P0.29","P0.28","P0.04","P0.05"],
}

# Default RP2040 pins
_RP2040_I2C_PINS = {"SDA": "GP4", "SCL": "GP5"}
_RP2040_SPI_PINS = {"MOSI": "GP19", "MISO": "GP16", "SCK": "GP18"}

# Default nRF52840 pins
_NRF52_I2C_PINS = {"SDA": "P0.26", "SCL": "P0.27"}
_NRF52_SPI_PINS = {"MOSI": "P0.23", "MISO": "P0.24", "SCK": "P0.25"}

# Default UART pins per MCU family
_ESP32_UART_PINS = {"TX": "17", "RX": "16"}
_STM32_UART_PINS = {"TX": "PA9", "RX": "PA10"}
_RP2040_UART_PINS = {"TX": "GP0", "RX": "GP1"}
_NRF52_UART_PINS = {"TX": "P0.06", "RX": "P0.08"}

# Default CAN pins per MCU family
_STM32_CAN_PINS = {"TX": "PA12", "RX": "PA11"}
_ESP32_CAN_PINS = {"TX": "21", "RX": "22"}  # ESP32 TWAI
_RP2040_CAN_PINS = {"TX": "GP0", "RX": "GP1"}  # external CAN transceiver


def _pick_mcu_pins(mcu_mpn: str, bus_type: str, use_llm: bool = False,
                   mcu_profile=None, pin_index: int = 0,
                   used_pins: set[str] | None = None) -> dict[str, str]:
    # --- Layer 1: Try MCU Device Profile first (data-driven) ---
    profile_pins = _pick_mcu_pins_from_profile(mcu_profile, bus_type, pin_index, used_pins)
    if profile_pins:
        log.debug("B4 pin assignment from MCU profile for %s %s[%d]: %s", mcu_mpn, bus_type, pin_index, profile_pins)
        return profile_pins

    # --- Legacy hardcoded fallback ---
    # UART entries may be a list so different UART buses get distinct pins.
    # Other bus types remain single-dict (no multi-instance conflict expected).
    mpn_low = mcu_mpn.lower()
    pin_tables = {
        # More specific entries first — "esp32-s3" must precede "esp32"
        "esp32-s3": {"I2C": _ESP32S3_I2C_PINS, "SPI": _ESP32S3_SPI_PINS, "UART": _ESP32S3_UART_PINS},
        "esp32": {"I2C": _ESP32_I2C_PINS, "SPI": _ESP32_SPI_PINS, "UART": _ESP32_UART_PINS, "CAN": _ESP32_CAN_PINS},
        "stm32": {
            "I2C": _STM32_I2C_PINS, "SPI": _STM32_SPI_PINS, "CAN": _STM32_CAN_PINS,
            # USART1 (PA9/PA10) for uart0, USART2 (PA2/PA3) for uart1
            "UART": [_STM32_UART_PINS, {"TX": "PA2", "RX": "PA3"}],
        },
        "rp2040": {"I2C": _RP2040_I2C_PINS, "SPI": _RP2040_SPI_PINS, "UART": _RP2040_UART_PINS, "CAN": _RP2040_CAN_PINS},
        "nrf52": {"I2C": _NRF52_I2C_PINS, "SPI": _NRF52_SPI_PINS, "UART": _NRF52_UART_PINS},
        # NXP LPC55 uses Flexcomm-based pin mux; use typical dev-board defaults
        "lpc55": {
            "I2C": {"SDA": "PIO1_5", "SCL": "PIO1_4"},
            "SPI": {"MOSI": "PIO1_3", "MISO": "PIO1_2", "SCK": "PIO0_26"},
            # USART0 (PIO0_0/1) for uart0, USART1 (PIO0_8/9) for uart1
            "UART": [{"TX": "PIO0_0", "RX": "PIO0_1"}, {"TX": "PIO0_8", "RX": "PIO0_9"}],
        },
        # NXP i.MX RT uses LPI2C/LPSPI/LPUART peripheral blocks
        "imxrt": {
            "I2C": {"SDA": "GPIO_AD_B0_03", "SCL": "GPIO_AD_B0_02"},
            "SPI": {"MOSI": "GPIO_SD_B0_02", "MISO": "GPIO_SD_B0_03", "SCK": "GPIO_SD_B0_00"},
            # LPUART1 (GPIO_AD_B0_12/13) for uart0, LPUART3 (GPIO_B0_04/05) for uart1
            "UART": [
                {"TX": "GPIO_AD_B0_12", "RX": "GPIO_AD_B0_13"},
                {"TX": "GPIO_B0_04",    "RX": "GPIO_B0_05"},
            ],
            "CAN": {"TX": "GPIO_AD_B1_08", "RX": "GPIO_AD_B1_09"},
        },
    }
    for family, tables in pin_tables.items():
        if family in mpn_low or (family == "stm32" and "f103" in mpn_low):
            if bus_type in tables:
                entry = tables[bus_type]
                if isinstance(entry, list):
                    idx = min(pin_index, len(entry) - 1)
                    return dict(entry[idx])
                return dict(entry)
            break

    # Unknown MCU — try LLM for real pin names
    if use_llm:
        llm_pins = _llm_suggest_pins(mcu_mpn, bus_type)
        if llm_pins:
            log.debug("B4 LLM pin suggestion for %s %s: %s", mcu_mpn, bus_type, llm_pins)
            return llm_pins
    # Generic fallback per bus type
    _generic_fallback = {
        "I2C": {"SDA": "GPIO_SDA", "SCL": "GPIO_SCL"},
        "SPI": {"MOSI": "GPIO_MOSI", "MISO": "GPIO_MISO", "SCK": "GPIO_SCK"},
        "UART": {"TX": "GPIO_TX", "RX": "GPIO_RX"},
        "CAN": {"TX": "GPIO_CAN_TX", "RX": "GPIO_CAN_RX"},
        "USB": {"DP": "GPIO_USB_DP", "DM": "GPIO_USB_DM"},
    }
    return _generic_fallback.get(bus_type, {"SDA": "GPIO_SDA", "SCL": "GPIO_SCL"})


def _allocate_i2c_addresses(slaves: list[SelectedComponent]) -> dict[str, str]:
    """Assign I2C addresses, detecting and resolving conflicts."""
    used: set[str] = set()
    assignments: dict[str, str] = {}

    for s in slaves:
        addrs = s.known_i2c_addresses
        if not addrs:
            # No known address — assign placeholder
            assignments[s.mpn] = "0x00"  # Will be flagged by validator
            continue

        allocated = False
        for addr in addrs:
            low = addr.lower()
            if low not in used:
                used.add(low)
                assignments[s.mpn] = addr
                allocated = True
                break

        if not allocated:
            # All known addresses conflict — use first and let validator catch it
            assignments[s.mpn] = addrs[0]

    return assignments


# ---------------------------------------------------------------------------
# Phase 22.1 — Alt-Function Validation
# ---------------------------------------------------------------------------

def _validate_pin_alt_function(profile, gpio: str, function: str) -> bool:
    """Check if a GPIO pin actually supports the requested alt-function.

    Looks up *gpio* in the profile's pin list and checks whether any of
    its ``alt_functions`` match *function*.  The comparison is
    case-insensitive so that ``I2C0_SDA`` matches ``i2c0_sda``.

    Returns ``True`` if the pin supports the function (or if the profile
    has no information about this pin — we don't want to false-alarm on
    pins the profile simply doesn't list).  Returns ``False`` only when
    the pin IS listed but the function is NOT among its alt_functions.
    """
    if profile is None:
        return True  # no profile → cannot validate, assume OK

    func_upper = function.upper()
    for pin_def in profile.pinout.pins:
        if pin_def.pin_name.upper() == gpio.upper():
            # Pin found — check alt_functions
            for af in pin_def.alt_functions:
                if af.function.upper() == func_upper:
                    return True
            # Pin found but function not listed
            return False
    # Pin not in profile (e.g. power/GND pin, or profile incomplete) — OK
    return True


# Map of (bus_type, signal_name) → regex patterns that match acceptable
# alt-function names across MCU families.
# Examples:
#   I2C + SDA  →  I2C0_SDA, I2C1_SDA, …
#   SPI + MOSI →  SPI1_MOSI, SPI2_MOSI, FSPI_MOSI, …
#   SPI + CLK  →  SPI1_SCK, SPI2_CLK, FSPI_CLK, …
#   SPI + CS   →  SPI1_NSS, SPI2_CS0, FSPI_CS0, …
#   UART + TX  →  U0TXD, USART1_TX, UART0_TX, …
#   UART + RX  →  U0RXD, USART1_RX, UART0_RX, …

_SIGNAL_TO_FUNCTION_PATTERNS: dict[tuple[str, str], re.Pattern[str]] = {
    # I2C
    ("I2C", "SDA"):  re.compile(r"I2C\d*_SDA", re.IGNORECASE),
    ("I2C", "SCL"):  re.compile(r"I2C\d*_SCL", re.IGNORECASE),
    # SPI
    ("SPI", "MOSI"): re.compile(r"(F?SPI\d*_MOSI|SPI\d*_TX)", re.IGNORECASE),
    ("SPI", "MISO"): re.compile(r"(F?SPI\d*_MISO|SPI\d*_RX)", re.IGNORECASE),
    ("SPI", "CLK"):  re.compile(r"F?SPI\d*_(CLK|SCK)", re.IGNORECASE),
    ("SPI", "SCK"):  re.compile(r"F?SPI\d*_(CLK|SCK)", re.IGNORECASE),
    ("SPI", "CS"):   re.compile(r"(F?SPI\d*_(CS\d*|NSS)|SUBSPICS\d*)", re.IGNORECASE),
    # UART
    ("UART", "TX"):  re.compile(r"(U\d*TXD|U?S?ART\d*_TX|UART\d*_TX)", re.IGNORECASE),
    ("UART", "RX"):  re.compile(r"(U\d*RXD|U?S?ART\d*_RX|UART\d*_RX)", re.IGNORECASE),
    # CAN
    ("CAN", "TX"):   re.compile(r"(FDCAN\d*_TX|CAN\d*_TX)", re.IGNORECASE),
    ("CAN", "RX"):   re.compile(r"(FDCAN\d*_RX|CAN\d*_RX)", re.IGNORECASE),
    # USB
    ("USB", "DP"):   re.compile(r"USB_D\+|USB_DP", re.IGNORECASE),
    ("USB", "DM"):   re.compile(r"USB_D-|USB_DM", re.IGNORECASE),
    ("USB", "D+"):   re.compile(r"USB_D\+|USB_DP", re.IGNORECASE),
    ("USB", "D-"):   re.compile(r"USB_D-|USB_DM", re.IGNORECASE),
}


def _expected_function_for_signal(bus_type: str, signal: str) -> str | None:
    """Return the expected alt-function pattern key for a bus signal.

    For per-slave CS signals (e.g. ``CS_U_BME280``), the base signal is ``CS``.
    Returns the matching alt-function name from the pin's alt_functions list,
    or ``None`` if no mapping is known for this signal.
    """
    bus_upper = bus_type.upper()
    sig_upper = signal.upper()

    # Normalise per-slave CS lines: "CS_U_BME280" → "CS"
    if sig_upper.startswith("CS_"):
        sig_upper = "CS"

    pattern = _SIGNAL_TO_FUNCTION_PATTERNS.get((bus_upper, sig_upper))
    if pattern is None:
        return None
    return pattern.pattern  # return the pattern string for diagnostics


def _pin_has_matching_alt(profile, gpio: str, bus_type: str, signal: str) -> bool:
    """Check whether *gpio* has an alt-function matching the bus signal.

    Returns True if:
    - profile is None (cannot check)
    - the pin is not found in the profile (incomplete profile)
    - the signal has no known mapping (e.g. exotic signals)
    - the pin has a matching alt-function
    """
    if profile is None:
        return True

    bus_upper = bus_type.upper()
    sig_upper = signal.upper()
    if sig_upper.startswith("CS_"):
        sig_upper = "CS"

    pattern = _SIGNAL_TO_FUNCTION_PATTERNS.get((bus_upper, sig_upper))
    if pattern is None:
        return True  # no known mapping for this signal — skip

    # Find the pin in the profile
    for pin_def in profile.pinout.pins:
        if pin_def.pin_name.upper() == gpio.upper():
            for af in pin_def.alt_functions:
                if pattern.fullmatch(af.function):
                    return True
            # Pin found but no matching alt-function
            return False

    # Pin not in profile — assume OK
    return True


def _validate_all_pin_assignments(
    profile, buses: list[TopologyBus], assumptions: list[str]
) -> None:
    """Validate that every pin assignment matches a real alt-function on the MCU.

    Iterates over all buses and their ``pin_assignments``.  For each
    (signal, gpio) pair, checks whether the GPIO's alt-function list
    includes the expected function.  Mismatches are appended to
    *assumptions* as warnings.

    Silently skips when *profile* is ``None``.
    """
    if profile is None:
        return

    for bus in buses:
        for signal, gpio in bus.pin_assignments.items():
            if not _pin_has_matching_alt(profile, gpio, bus.bus_type, signal):
                msg = (
                    f"ALT-FUNCTION WARNING: {gpio} assigned as {bus.name}:{signal} "
                    f"but profile shows no matching alt-function for "
                    f"{bus.bus_type}/{signal}"
                )
                log.warning("B4 pin validation: %s", msg)
                assumptions.append(msg)


# ---------------------------------------------------------------------------
# Phase 22.2 — Pinmux-Conflict Detection
# ---------------------------------------------------------------------------

def _detect_pinmux_conflicts(
    buses: list[TopologyBus], assumptions: list[str]
) -> None:
    """Detect GPIO pins assigned to more than one signal across all buses.

    Builds a mapping of each GPIO pin → list of (bus_name, signal_name).
    If any GPIO appears more than once, an ERROR assumption is appended.
    """
    pin_usage: dict[str, list[tuple[str, str]]] = {}

    for bus in buses:
        for signal, gpio in bus.pin_assignments.items():
            key = gpio.upper()
            pin_usage.setdefault(key, []).append((bus.name, signal))

    for gpio_upper, usages in sorted(pin_usage.items()):
        if len(usages) > 1:
            parts = " and ".join(f"{bus_name}:{sig}" for bus_name, sig in usages)
            msg = f"PINMUX CONFLICT: {gpio_upper} assigned to both {parts}"
            log.warning("B4 pinmux: %s", msg)
            assumptions.append(msg)


# ---------------------------------------------------------------------------
# Phase 22.3 — Boot/Reset circuit generation
# ---------------------------------------------------------------------------

def _synthesize_boot_reset_circuit(
    mcu_profile,
    passives: list[PassiveComponent],
    assumptions: list[str],
    regulated_rail: str,
) -> None:
    """Generate boot/reset pull resistors + filter cap from MCU profile data.

    Reads Domain 5 (BootConfig) from the MCU Device Profile:
    - Reset circuit: pull-up resistor + filter cap on NRST/EN pin
    - Boot mode pins: pull-up/pull-down resistors for normal boot

    Modifies passives and assumptions in-place.
    """
    if mcu_profile is None or mcu_profile.boot is None:
        return

    boot = mcu_profile.boot
    _counter: dict[str, int] = {}

    def _uid(prefix: str) -> str:
        _counter[prefix] = _counter.get(prefix, 0) + 1
        return f"BOOT_{prefix}{_counter[prefix]}"

    # --- Reset circuit: pull-up on NRST/EN + filter cap ---
    rst = boot.reset_circuit
    if rst.recommended_pullup_ohm:
        val = f"{rst.recommended_pullup_ohm / 1000:.3g}k" if rst.recommended_pullup_ohm >= 1000 else str(rst.recommended_pullup_ohm)
        passives.append(PassiveComponent(
            comp_id=_uid("R"),
            category="resistor",
            value=val,
            unit="Ω",
            purpose=f"reset_pullup_{rst.nrst_pin}",
            nets=[regulated_rail, f"NET_{rst.nrst_pin}"],
            package="0402",
            mpn_suggestion="RC0402FR-0710KL",
            unit_cost_usd=0.01,
        ))
        assumptions.append(
            f"Phase 22.3: Reset pull-up {val}Ω on {rst.nrst_pin} (from MCU profile)"
        )

    if rst.cap_to_gnd_nf:
        val = f"{rst.cap_to_gnd_nf:.3g}n" if rst.cap_to_gnd_nf < 1000 else f"{rst.cap_to_gnd_nf / 1000:.3g}u"
        passives.append(PassiveComponent(
            comp_id=_uid("C"),
            category="capacitor",
            value=val,
            unit="F",
            purpose=f"reset_filter_{rst.nrst_pin}",
            nets=[f"NET_{rst.nrst_pin}", "GND"],
            package="0402",
            mpn_suggestion="GRM155R71C104KA88D",
            unit_cost_usd=0.02,
        ))

    # --- Boot mode pins: pull resistors for normal boot ---
    for bmp in boot.boot_mode_pins:
        if "pull_down" in bmp.pull_resistor:
            r_val = "10k"
            nets = [f"NET_{bmp.pin}", "GND"]
            desc = f"boot_pulldown_{bmp.pin}"
        elif "pull_up" in bmp.pull_resistor:
            r_val = "10k"
            nets = [regulated_rail, f"NET_{bmp.pin}"]
            desc = f"boot_pullup_{bmp.pin}"
        else:
            continue

        passives.append(PassiveComponent(
            comp_id=_uid("R"),
            category="resistor",
            value=r_val,
            unit="Ω",
            purpose=desc,
            nets=nets,
            package="0402",
            mpn_suggestion="RC0402FR-0710KL",
            unit_cost_usd=0.01,
        ))
        assumptions.append(
            f"Phase 22.3: Boot pin {bmp.pin} → {r_val} {bmp.pull_resistor} "
            f"for {bmp.normal_boot_state} normal boot"
        )


# ---------------------------------------------------------------------------
# Phase 22.4 — Crystal + Load-Caps generation
# ---------------------------------------------------------------------------

def _synthesize_clock_circuit(
    mcu_profile,
    passives: list[PassiveComponent],
    all_components: list[SelectedComponent],
    assumptions: list[str],
    mcu_mpn: str = "",
    raw_prompt: str = "",
) -> None:
    """Generate crystal oscillator + load capacitors from MCU profile or legacy defaults.

    Layer 1 — MCU Device Profile (data-driven):
    - Reads Domain 4 (ClockConfig): if main_clock.type == external_xtal → add crystal + 2× load caps
    - Load cap values from profile (load_capacitance_pf) or formula

    Layer 2 — Legacy fallback (for MCUs without profiles):
    - STM32 bare-die MCUs → 8 MHz crystal + 2× 20 pF load caps (HSE default)
    - RP2040 → 12 MHz crystal + 2× 20 pF (always needs external crystal)
    - ATmega → 16 MHz crystal + 2× 22 pF (when prompt mentions "16 MHz Quarz")
    - nRF52 → 32 MHz crystal + 2× 12 pF (HFXO required for BLE)

    Modifies passives and assumptions in-place.
    """
    freq_mhz: float | None = None
    c_load_pf: float = 20.0
    osc_pins = ["OSC_IN", "OSC_OUT"]
    source_label = "MCU profile"

    if mcu_profile is not None and mcu_profile.clock is not None:
        clk = mcu_profile.clock.main_clock
        # Only generate crystal for external_xtal clock sources
        if clk.type.value != "external_xtal":
            return
        freq_mhz = clk.frequency_hz / 1e6
        c_load_pf = clk.load_capacitance_pf if clk.load_capacitance_pf else 20.0
        osc_pins = clk.osc_pins if clk.osc_pins else ["OSC_IN", "OSC_OUT"]
        source_label = "MCU profile"
    else:
        # --- Legacy fallback: infer crystal from MCU family ---
        mpn_low = mcu_mpn.lower()
        prompt_low = raw_prompt.lower()

        # STM32 bare-die MCUs require external HSE crystal (8 MHz default)
        if any(f in mpn_low for f in ("stm32f1", "stm32f4", "stm32f7", "stm32h7",
                                       "stm32g4", "stm32l4", "stm32f0")):
            # Check prompt for explicit crystal frequency override (e.g. "12MHz Crystal")
            _prompt_mhz = re.search(
                r"(\d+(?:[.,]\d+)?)\s*mhz\s*(?:crystal|quarz|xtal|oszillator|oscillator)",
                prompt_low,
            )
            if not _prompt_mhz:
                # Also match "externem 12MHz" pattern (no crystal keyword after)
                _prompt_mhz = re.search(r"externem\s+(\d+(?:[.,]\d+)?)\s*mhz", prompt_low)
            if _prompt_mhz:
                freq_mhz = float(_prompt_mhz.group(1).replace(",", "."))
                source_label = "prompt-specified crystal frequency"
            else:
                freq_mhz = 8.0
                source_label = "legacy fallback (STM32 HSE)"
            c_load_pf = 20.0
            osc_pins = ["OSC_IN", "OSC_OUT"]

        # RP2040 always requires 12 MHz external crystal for PLL
        elif "rp2040" in mpn_low:
            freq_mhz = 12.0
            c_load_pf = 15.0
            osc_pins = ["XIN", "XOUT"]
            source_label = "legacy fallback (RP2040)"

        # ATmega with "16 MHz Quarz" or "16MHz" in prompt
        elif "atmega" in mpn_low and ("16" in prompt_low and ("mhz" in prompt_low or "quarz" in prompt_low)):
            freq_mhz = 16.0
            c_load_pf = 22.0
            osc_pins = ["XTAL1", "XTAL2"]
            source_label = "legacy fallback (ATmega 16MHz)"

        # nRF52 requires 32 MHz HFXO for BLE radio
        elif "nrf52" in mpn_low:
            freq_mhz = 32.0
            c_load_pf = 12.0
            osc_pins = ["XC1", "XC2"]
            source_label = "legacy fallback (nRF52 HFXO)"

    if freq_mhz is None:
        return  # No crystal needed or unknown MCU

    _counter: dict[str, int] = {}

    def _uid(prefix: str) -> str:
        _counter[prefix] = _counter.get(prefix, 0) + 1
        return f"CLK_{prefix}{_counter[prefix]}"

    # --- Crystal oscillator ---
    crystal_value = f"{freq_mhz:.3g}MHz"

    passives.append(PassiveComponent(
        comp_id=_uid("Y"),
        category="crystal",
        value=crystal_value,
        unit="",
        purpose=f"main_crystal_{freq_mhz:.0f}mhz",
        nets=[f"NET_{osc_pins[0]}", f"NET_{osc_pins[1]}"] if len(osc_pins) >= 2 else ["OSC_IN", "OSC_OUT"],
        package="HC-49S",
        mpn_suggestion=f"HC49-{freq_mhz:.0f}MHZ",
        unit_cost_usd=0.25,
    ))

    # --- Load capacitors ---
    c_stray_pf = 5.0
    c_actual_pf = max(2 * (c_load_pf - c_stray_pf), 6.0)
    c_val = f"{c_actual_pf:.3g}p"

    for osc_pin in osc_pins[:2]:
        passives.append(PassiveComponent(
            comp_id=_uid("C"),
            category="capacitor",
            value=c_val,
            unit="F",
            purpose=f"crystal_load_cap_{osc_pin}",
            nets=[f"NET_{osc_pin}", "GND"],
            package="0402",
            mpn_suggestion="GRM1555C1H120GA01D",
            unit_cost_usd=0.02,
        ))

    assumptions.append(
        f"Phase 22.4: Crystal {crystal_value} + 2× {c_val}F load caps "
        f"(C_load={c_load_pf:.0f}pF, C_stray={c_stray_pf:.0f}pF) from {source_label}"
    )


# ---------------------------------------------------------------------------
# Phase 22.5 — Level-Shifter bei Voltage-Mismatch
# ---------------------------------------------------------------------------

def _detect_voltage_mismatch_and_insert_levelshifter(
    mcu: SelectedComponent,
    sensors: list[SelectedComponent],
    buses: list[TopologyBus],
    all_components: list[SelectedComponent],
    passives: list[PassiveComponent],
    assumptions: list[str],
    regulated_rail: str,
) -> None:
    """Detect 3.3V↔5V voltage mismatches and add level-shifter notes/passives.

    For each sensor on a bus:
    - Check if MCU io_voltage_nominal differs from sensor io_voltage_nominal
    - If mismatch detected (>0.5V difference), log a warning
    - For single-signal mismatches, add BSS138 MOSFET pull-up resistors
    - For multi-signal buses, recommend TXS0102/TXB0104

    Modifies passives and assumptions in-place.
    """
    mcu_ratings = mcu.raw.get("electrical_ratings", {})
    mcu_vio = mcu_ratings.get("io_voltage_nominal", 3.3)
    mcu_5v_tolerant = mcu_ratings.get("is_5v_tolerant", False)

    _counter: dict[str, int] = {}

    def _uid(prefix: str) -> str:
        _counter[prefix] = _counter.get(prefix, 0) + 1
        return f"LS_{prefix}{_counter[prefix]}"

    for sensor in sensors:
        s_ratings = sensor.raw.get("electrical_ratings", {})
        s_vio = s_ratings.get("io_voltage_nominal", 3.3)

        # Skip passive bus connectors (e.g. CONN-RS485-2PIN) whose io_voltage_nominal
        # is 0.0 — they are purely passive and have no logic voltage requirement.
        if s_vio == 0.0:
            continue

        if abs(mcu_vio - s_vio) <= 0.5:
            continue

        if s_vio > mcu_vio and mcu_5v_tolerant:
            assumptions.append(
                f"Phase 22.5: {sensor.mpn} operates at {s_vio}V but MCU is 5V-tolerant — no level-shifter needed"
            )
            continue

        sensor_id = _comp_id(sensor)
        sensor_bus = None
        for bus in buses:
            if sensor_id in bus.slave_ids:
                sensor_bus = bus
                break

        if sensor_bus and sensor_bus.bus_type in ("I2C", "SPI"):
            signal_count = len([k for k in sensor_bus.pin_assignments if not k.startswith("CS_")])
            shifter = "TXS0102" if signal_count <= 2 else "TXB0104"
            assumptions.append(
                f"Phase 22.5: VOLTAGE MISMATCH — {sensor.mpn} ({s_vio}V) on "
                f"{sensor_bus.name} ({sensor_bus.bus_type}) with MCU ({mcu_vio}V). "
                f"Insert {shifter} level-shifter between {mcu_vio}V and {s_vio}V rails."
            )
            log.warning(
                "B4 voltage mismatch: %s (%.1fV) ↔ MCU (%.1fV) on %s — recommend %s",
                sensor.mpn, s_vio, mcu_vio, sensor_bus.name, shifter,
            )
        else:
            # BSS138 N-Channel MOSFET level-shifter circuit:
            # drain-side pull-up to high-voltage rail, source-side pull-up to low-voltage rail
            _ls_sig = f"LS_{sensor.mpn.replace('-', '_')}_SIG"
            for rail_name, rail_v in [(regulated_rail, mcu_vio), ("5V", s_vio)]:
                passives.append(PassiveComponent(
                    comp_id=_uid("R"),
                    category="resistor",
                    value="10k",
                    unit="Ω",
                    purpose=f"levelshift_pullup_{sensor.mpn}_{rail_v:.1f}V",
                    nets=[rail_name, _ls_sig],
                    package="0402",
                    mpn_suggestion="RC0402FR-0710KL",
                    unit_cost_usd=0.01,
                ))
            # Add BSS138 MOSFET to BOM as a SelectedComponent
            _bss138_id = f"Q_LS_{sensor.mpn.replace('-', '_')}"
            if not any(c.mpn == "BSS138" for c in all_components):
                all_components.append(SelectedComponent(
                    mpn="BSS138",
                    manufacturer="ON Semiconductor",
                    name="BSS138 N-Channel MOSFET Level Shifter",
                    category="discrete",
                    interface_types=["GPIO"],
                    role="other",
                    known_i2c_addresses=[],
                    init_contract_coverage=False,
                    unit_cost_usd=0.05,
                    score=0.95,
                    raw={
                        "mpn": "BSS138",
                        "manufacturer": "ON Semiconductor",
                        "name": "BSS138 N-Channel MOSFET Level Shifter",
                        "category": "discrete",
                        "interface_types": ["GPIO"],
                    },
                ))
            assumptions.append(
                f"Phase 22.5: VOLTAGE MISMATCH — {sensor.mpn} ({s_vio}V) with MCU ({mcu_vio}V). "
                f"BSS138 level-shifter + 2× 10k pull-ups added."
            )


# ---------------------------------------------------------------------------
# Phase 22.7 — Debug-Header + Test-Points
# ---------------------------------------------------------------------------

def _synthesize_debug_header(
    mcu_profile,
    mcu: SelectedComponent,
    all_components: list[SelectedComponent],
    passives: list[PassiveComponent],
    assumptions: list[str],
) -> None:
    """Generate debug header and test-point info from MCU profile.

    Reads Domain 6 (DebugInterface) from the MCU Device Profile:
    - Adds SWD 2×5 header for Cortex-M MCUs (STM32, nRF52, RP2040)
    - Adds UART header for ESP32
    - Adds test-points on critical nets (+3V3, GND, SDA, SCL)

    Modifies assumptions and all_components in-place with debug header info.
    """
    mpn_lower = mcu.mpn.lower()

    # Determine MCU family for debug connector selection
    _is_cortex_m = (
        "stm32" in mpn_lower
        or "nrf52" in mpn_lower
        or "lpc" in mpn_lower
        or "samd" in mpn_lower
        or "rp2040" in mpn_lower
    )
    _is_esp32 = "esp32" in mpn_lower

    # Already have a debug header in the BOM? (avoid duplicates)
    _existing_debug_mpns = {c.mpn for c in all_components}
    _swd_mpn = "CONN-SWD-2x5"

    if mcu_profile and mcu_profile.debug_interfaces:
        dbg = mcu_profile.debug_interfaces[0]
        pin_desc = ", ".join(f"{k}={v}" for k, v in dbg.pins.items())
        connector_name = dbg.recommended_connector.name if dbg.recommended_connector else "standard header"
        log.info(
            "B4 debug header: %s (%s), connector: %s",
            dbg.protocol, pin_desc, connector_name,
        )
        # Profile says SWD → force SWD connector creation below
        if dbg.protocol.upper() in ("SWD", "SWD+SWO"):
            _is_cortex_m = True
    elif _is_cortex_m:
        log.info("B4 debug header: SWD 2×5 1.27mm (SWDIO, SWCLK, GND, VTref, NRST)")
    elif _is_esp32:
        log.info("B4 debug header: UART (TXD0, RXD0, GND) via USB-to-Serial")

    # Add physical SWD connector component for Cortex-M MCUs
    if _is_cortex_m and _swd_mpn not in _existing_debug_mpns:
        all_components.append(SelectedComponent(
            mpn=_swd_mpn,
            manufacturer="Generic",
            name="ARM SWD 2x5 1.27mm Debug Header",
            category="connector",
            interface_types=["SWD"],
            role="connector",
            known_i2c_addresses=[],
            init_contract_coverage=True,
            unit_cost_usd=0.50,
            score=0.95,
            raw={
                "mpn": _swd_mpn,
                "manufacturer": "Generic",
                "name": "ARM SWD 2x5 1.27mm Debug Header",
                "category": "connector",
                "interface_types": ["SWD"],
            },
        ))
        log.info("B4 debug header: SWD 2×5 1.27mm connector (%s) added to BOM", _swd_mpn)

    test_point_nets = ["+3V3", "GND"]
    for comp in all_components:
        ifaces = {i.upper() for i in comp.raw.get("interface_types", [])}
        if "I2C" in ifaces:
            test_point_nets.extend(["SDA", "SCL"])
            break

    tp_nets = list(dict.fromkeys(test_point_nets))
    log.info("B4 test-points recommended on: %s", ", ".join(tp_nets))


def _synthesize_battery_charger_circuit(
    all_components: list,
    passives: list,
    assumptions: list,
) -> None:
    """Add TP4056 support circuit: battery connector, R_PROG, VCC note.

    Called when TP4056 Li-Ion charger IC is present in the component list.

    TP4056 circuit requirements:
      - PROG pin (pin 2): 2kΩ to GND sets charge current to ~600mA (I=1200/R_kΩ mA)
      - BAT pin (pin 5): connects to VBAT net (battery positive terminal)
      - VCC pin (pin 4): MUST connect to 5V_VBUS — NOT 3V3 LDO output
      - Battery connector: JST-PH 2-pin (B2B-PH-K-S), standard LiPo pack connector
    """
    has_tp4056 = any(
        getattr(c, "mpn", "").upper() == "TP4056"
        for c in all_components
    )
    if not has_tp4056:
        return

    # --- R_PROG: 2kΩ from PROG pin to GND ---
    passives.append(PassiveComponent(
        comp_id="R_PROG1",
        category="resistor",
        value="2k",
        unit="Ω",
        purpose="tp4056_prog_resistor",
        nets=["TP4056_PROG", "GND"],
        package="0402",
        mpn_suggestion="RC0402FR-072KL",
        unit_cost_usd=0.01,
    ))

    # --- JST-PH battery connector ---
    # Only add if not already present (avoid duplicates)
    already_has_jst = any(
        getattr(c, "mpn", "") in ("B2B-PH-K-S", "JST-PH-2P")
        for c in all_components
    )
    if not already_has_jst:
        try:
            bat_conn = SelectedComponent(
                mpn="B2B-PH-K-S",
                manufacturer="JST",
                name="JST-PH 2-Pin Battery Connector",
                category="connector",
                interface_types=[],
                role="battery_connector",
                known_i2c_addresses=[],
                init_contract_coverage=False,
                unit_cost_usd=0.15,
                score=1.0,
                raw={
                    "mpn": "B2B-PH-K-S",
                    "manufacturer": "JST",
                    "category": "connector",
                    "package": "THT-2PIN",
                    "pin_count": 2,
                    "description": "JST-PH 2-pin LiPo battery connector",
                },
            )
            all_components.append(bat_conn)
        except Exception:
            pass  # Graceful — connector is best-effort

    # --- VCC note: TP4056 needs 5V_VBUS ---
    assumptions.append(
        "TP4056 VCC/VIN (pin 4) must connect to 5V_VBUS — "
        "NOT the 3V3 LDO output. Charge circuit will not function at 3.3V."
    )

    log.debug("battery_charger: R_PROG(2kΩ) + JST-PH connector added for TP4056")


def synthesize_topology(
    selection: ComponentSelection,
    supply_voltage_v: float | None = None,
    use_llm: bool = True,
    raw_prompt: str = "",
) -> SynthesizedTopology:
    """Build bus topology from component selection.

    Args:
        selection: Selected MCU + sensors.
        supply_voltage_v: Intended supply voltage (e.g. 5.0 for USB power).
                          When > MCU VDD_MAX, a voltage regulator is auto-added.
        use_llm: If True, use LLM for interface selection and unknown MCU pins.
                 Falls back to hardcoded rules when LLM is unavailable or skips.
    """
    assumptions = list(selection.assumptions)
    buses: list[TopologyBus] = []

    if selection.mcu is None:
        return SynthesizedTopology(
            components=[], buses=[], power_rails=[], passives=[],
            voltage_regulators=[],
            assumptions=assumptions + ["No MCU — cannot synthesize topology"],
        )

    mcu = selection.mcu
    sensors = list(selection.sensors)

    # --- Load MCU Device Profile (Layer 1 Hardware Knowledge) ---
    mcu_profile = _load_mcu_profile(mcu.mpn)
    if mcu_profile:
        log.info("B4: Loaded MCU Device Profile for %s (%d pins, %d power domains)",
                 mcu.mpn, len(mcu_profile.pinout.pins), len(mcu_profile.power.power_domains))
    reserved_pins = _get_reserved_pins(mcu_profile)
    boot_strap_pins = _get_boot_strap_pins(mcu_profile)

    # --- Detect and duplicate components when prompt requests multiple instances ---
    # e.g. "zwei H-Bridge Motor-Treibern" → add a second TB6612FNG instance.
    # Detected keywords (German + English) for "two" motor drivers.
    _TWO_MOTOR_KEYWORDS = (
        "zwei h-bridge", "zwei motor", "2x h-bridge", "2 h-bridge",
        "two h-bridge", "two motor driver", "dual motor driver",
    )
    _MOTOR_DRIVER_MPNS = frozenset(("TB6612FNG", "DRV8833", "L298N", "TB6600"))
    _raw_prompt_lower = raw_prompt.lower()
    if any(kw in _raw_prompt_lower for kw in _TWO_MOTOR_KEYWORDS):
        motor_drivers = [s for s in sensors if s.mpn in _MOTOR_DRIVER_MPNS]
        if len(motor_drivers) == 1:
            import copy as _copy
            dup = _copy.copy(motor_drivers[0])
            dup.instance_idx = 1
            sensors.append(dup)
            assumptions.append(
                f"Prompt requests 2× H-Bridge motor drivers — "
                f"added second instance of {motor_drivers[0].mpn} (comp_id={_comp_id(dup)})"
            )

    all_components = [mcu] + sensors

    # Group sensors by preferred interface
    # LLM-boost: when sensor supports both I2C and SPI, ask LLM which to use.
    i2c_slaves: list[SelectedComponent] = []
    spi_slaves: list[SelectedComponent] = []
    uart_devices: list[SelectedComponent] = []
    can_devices: list[SelectedComponent] = []

    def _sensor_prefers_uart(comp: SelectedComponent, prompt_lo: str) -> bool:
        """Return True if a multi-interface component should use UART.

        GPS/GNSS modules, SIM/LTE modems, and Bluetooth modules primarily
        communicate over UART.  When a prompt mentions one of these components
        together with 'UART', or the component's tags include 'gps/gnss/sim/lte',
        force UART assignment even though the component also supports I2C/SPI.
        """
        tags = {t.lower() for t in (comp.raw or {}).get("tags", [])}
        mpn_lo = comp.mpn.lower()
        name_lo = comp.name.lower()
        # GPS/GNSS modules → always UART (NMEA sentences)
        if tags & {"gps", "gnss"} or any(k in mpn_lo for k in ["neo-m", "neo-6", "neo-7", "neo-8", "ublox", "l76", "l86", "sam-m"]):
            return True
        # SIM / LTE / cellular modules → always UART (AT commands)
        if tags & {"sim", "lte", "cellular"} or any(k in mpn_lo for k in ["sim7", "sim8", "a76", "bg96", "ec2"]):
            return True
        # Prompt explicitly says "UART" next to the component name
        if "uart" in prompt_lo and comp.mpn.lower() in prompt_lo:
            return True
        return False

    # Interface sets that don't use a bus — connect via GPIO/direct wiring only
    _GPIO_LIKE = {"GPIO", "PWM", "ADC", "DAC", "I2S", "ANALOG_IN", "ANALOG_OUT", "OTHER"}
    # Component categories that never go on an I2C/SPI bus
    _BUS_BYPASS_CATEGORIES = {"actuator", "connector", "power", "diode"}

    for sensor in sensors:
        ifaces_set = {i.upper() for i in sensor.interface_types}
        has_i2c = "I2C" in ifaces_set
        has_spi = "SPI" in ifaces_set
        has_uart = "UART" in ifaces_set or "RS485" in ifaces_set
        has_can = "CAN" in ifaces_set
        # Connectors with a serial bus interface (UART, I2C, SPI, CAN) must
        # NOT be bypassed — they need to be wired to the MCU via a bus.
        _has_serial_bus = has_i2c or has_spi or has_uart or has_can
        is_gpio_only = (
            ifaces_set.issubset(_GPIO_LIKE)
            or (sensor.category in _BUS_BYPASS_CATEGORIES and not _has_serial_bus)
            or not sensor.interface_types  # no interface info → passive-like, no bus
        )

        if is_gpio_only:
            # GPIO / actuator / connector — no bus assignment.
            # Component stays in all_components for decoupling cap + actuator-passive synthesis.
            pass
        elif has_uart and not has_i2c and not has_spi:
            # Skip passive RS485 bus connectors (io_voltage_nominal == 0.0).
            # These are physical bus terminals (A/B screw terminals) that connect
            # to the RS485 transceiver's A/B differential output via net-label
            # auto-connect — they must NOT consume an MCU UART port.
            # Also skip UART header connectors (category='connector') — e.g.
            # CONN-UART-4PIN is a pass-through header that auto-wires via
            # by_name (pin.name="TX"/"RX") and must NOT consume a dedicated
            # MCU UART port, which would create spurious multi-UART buses and
            # dangling uart1_TX_MCU net labels.
            _s_vio = sensor.raw.get("electrical_ratings", {}).get("io_voltage_nominal", 3.3)
            if _s_vio > 0.0 and sensor.category != "connector":
                uart_devices.append(sensor)
        elif has_uart and (has_i2c or has_spi) and _sensor_prefers_uart(sensor, _raw_prompt_lower):
            # GPS/GNSS modules, SIM modules, etc. should use UART even if they also support I2C/SPI
            uart_devices.append(sensor)
            log.info("%s: forced to UART (preferred interface for %s)", sensor.mpn, sensor.category)
        elif has_can and not has_i2c and not has_spi:
            can_devices.append(sensor)
        elif has_i2c and has_spi and use_llm:
            # Both interfaces available — ask LLM
            suggested = _llm_suggest_interface(mcu.mpn, sensor.mpn, sensor.name, list(ifaces_set))
            if suggested == "SPI":
                spi_slaves.append(sensor)
                assumptions.append(f"{sensor.mpn}: LLM recommended SPI over I2C")
            else:
                i2c_slaves.append(sensor)
                if suggested == "I2C":
                    assumptions.append(f"{sensor.mpn}: LLM recommended I2C over SPI")
        elif has_i2c:
            i2c_slaves.append(sensor)
        elif has_spi:
            spi_slaves.append(sensor)
        else:
            i2c_slaves.append(sensor)  # default for unknown bus IC
            assumptions.append(f"{sensor.mpn}: no known interface, defaulting to I2C")

    # Global set of GPIO pins already assigned to a bus — passed to
    # _pick_mcu_pins so profile-based pin selection automatically skips
    # conflicting default pinmaps and uses alt pins instead.
    _assigned_pins: set[str] = set()

    # --- I2C bus ---
    if i2c_slaves:
        i2c_pins = _pick_mcu_pins(mcu.mpn, "I2C", use_llm=use_llm,
                                   mcu_profile=mcu_profile, used_pins=_assigned_pins)
        _assigned_pins.update(i2c_pins.values())
        slave_ids = [_comp_id(s) for s in i2c_slaves]
        addr_map_by_mpn = _allocate_i2c_addresses(i2c_slaves)
        # Re-key by component_id
        addr_by_cid = {_comp_id(s): addr_map_by_mpn.get(s.mpn, "0x00") for s in i2c_slaves}

        buses.append(TopologyBus(
            name="i2c0",
            bus_type="I2C",
            master_id=_comp_id(mcu),
            slave_ids=slave_ids,
            pin_assignments=i2c_pins,
            slave_addresses=addr_by_cid,
        ))

    # --- SPI bus ---
    if spi_slaves:
        spi_pins = _pick_mcu_pins(mcu.mpn, "SPI", use_llm=use_llm,
                                   mcu_profile=mcu_profile, used_pins=_assigned_pins)
        # Remove NSS from profile-provided pins — CS is managed separately per slave.
        spi_pins.pop("NSS", None)
        _assigned_pins.update(spi_pins.values())
        slave_ids = [_comp_id(s) for s in spi_slaves]
        # Use MCU-specific CS GPIO names (proper pin names, not integers).
        # Falls back to "IO<n>" numbering for unknown MCUs.
        _cs_pool = _MCU_CS_PINS.get(mcu.mpn, [f"IO{_ESP32_CS_START + i}" for i in range(4)])
        _used_spi_pins = set(spi_pins.values()) | _assigned_pins
        for cs_idx, s in enumerate(spi_slaves):
            cs_gpio = _cs_pool[cs_idx] if cs_idx < len(_cs_pool) else f"IO{_ESP32_CS_START + cs_idx}"
            # Skip pins already used by SPI data lines or other buses
            while cs_gpio in _used_spi_pins and cs_idx + 1 < len(_cs_pool):
                cs_idx += 1
                cs_gpio = _cs_pool[cs_idx] if cs_idx < len(_cs_pool) else f"IO{_ESP32_CS_START + cs_idx}"
            spi_pins[f"CS_{_comp_id(s)}"] = cs_gpio
            _used_spi_pins.add(cs_gpio)
            _assigned_pins.add(cs_gpio)

        buses.append(TopologyBus(
            name="spi0",
            bus_type="SPI",
            master_id=_comp_id(mcu),
            slave_ids=slave_ids,
            pin_assignments=spi_pins,
            slave_addresses={},
        ))

    # --- UART bus ---
    for uart_idx, uart_dev in enumerate(uart_devices):
        uart_name = f"uart{uart_idx}"
        uart_pins = _pick_mcu_pins(mcu.mpn, "UART", use_llm=use_llm,
                                    mcu_profile=mcu_profile, pin_index=uart_idx,
                                    used_pins=_assigned_pins)
        _assigned_pins.update(uart_pins.values())
        buses.append(TopologyBus(
            name=uart_name,
            bus_type="UART",
            master_id=_comp_id(mcu),
            slave_ids=[_comp_id(uart_dev)],
            pin_assignments=uart_pins,
            slave_addresses={},
        ))

    # --- CAN bus ---
    if can_devices:
        can_pins = _pick_mcu_pins(mcu.mpn, "CAN", use_llm=use_llm,
                                   mcu_profile=mcu_profile, used_pins=_assigned_pins)
        _assigned_pins.update(can_pins.values())
        buses.append(TopologyBus(
            name="can0",
            bus_type="CAN",
            master_id=_comp_id(mcu),
            slave_ids=[_comp_id(d) for d in can_devices],
            pin_assignments=can_pins,
            slave_addresses={},
        ))

    # --- GPIO sensor data wiring (1-Wire, single-wire sensors) ---
    # Sensors with interface_types == ["GPIO"] (e.g. DS18B20) need their
    # data pin connected to an MCU GPIO.  We create an AnalogNet for each.
    _GPIO_SENSOR_DATA_PINS: dict[str, str] = {
        "DS18B20": "DQ",
        "DHT11": "DATA",  "DHT22": "DATA",  "AM2302": "DATA",
        "WS2812B": "DI",  "SK6812": "DI",
    }
    _MCU_GPIO_POOL: dict[str, list[str]] = {
        "rp2040":    ["GP13", "GP21", "GP9", "GP10", "GP11", "GP12", "GP14"],
        "esp32-c3":  ["3", "4", "5", "6", "7", "8", "9"],
        "esp32-s3":  ["38", "39", "40", "41", "42"],
        "esp32":     ["25", "26", "27", "32", "33"],
        "stm32":     ["PA0", "PA1", "PA2", "PA3", "PA4"],
        "nrf52":     ["P0.02", "P0.03", "P0.04", "P0.05"],
    }
    _gpio_pool = _MCU_GPIO_POOL.get(mcu.mpn.lower().split("-")[0].split("_")[0], ["GPIO0", "GPIO1", "GPIO2"])
    _gpio_alloc_idx = 0
    _gpio_data_nets: list[AnalogNet] = []
    _gpio_onewire_nets: list[tuple[str, str]] = []  # (comp_id, net_name) for deferred 4.7k pullups
    for sensor in sensors:
        if sensor.category in ("actuator", "connector", "power", "diode"):
            continue
        ifaces_set = {i.upper() for i in sensor.interface_types}
        if not ifaces_set.issubset({"GPIO", "PWM", "ADC", "DAC", "I2S"}):
            continue  # already on a serial bus
        data_pin = _GPIO_SENSOR_DATA_PINS.get(sensor.mpn.upper())
        if not data_pin:
            data_pin = _GPIO_SENSOR_DATA_PINS.get(sensor.mpn)
        if not data_pin:
            continue  # unknown sensor — skip
        if _gpio_alloc_idx >= len(_gpio_pool):
            continue  # no more GPIOs available
        mcu_gpio = _gpio_pool[_gpio_alloc_idx]
        _gpio_alloc_idx += 1
        cid = _comp_id(sensor)
        net_name = f"GPIO_{cid}_{data_pin}"
        _gpio_data_nets.append(AnalogNet(
            name=net_name,
            pins=[(_comp_id(mcu), mcu_gpio), (cid, data_pin)],
            is_bus=False,
            is_power=False,
        ))
        assumptions.append(
            f"GPIO wiring: {sensor.mpn} pin {data_pin} → MCU {mcu_gpio} (net {net_name})"
        )

        # Collect 1-Wire sensors for deferred pull-up generation (after 'passives' is defined)
        # DS18B20, DS18S20, DHT11/22 have open-drain DQ/DATA lines → need 4.7 kΩ pull-up
        _ONE_WIRE_SENSORS = frozenset({"DS18B20", "DS18S20", "DS18B20+", "DHT11", "DHT22", "AM2302"})
        if sensor.mpn.upper() in {s.upper() for s in _ONE_WIRE_SENSORS} and data_pin in ("DQ", "DATA"):
            _gpio_onewire_nets.append((cid, net_name))

    # --- Voltage Regulator (when supply > MCU VDD_MAX) ---
    mcu_ratings = mcu.raw.get("electrical_ratings", {})
    vdd_nom = mcu_ratings.get("io_voltage_nominal", 3.3)
    vdd_min = mcu_ratings.get("vdd_min", 3.0)
    vdd_max = mcu_ratings.get("vdd_max", 3.6)

    voltage_regulators: list[VoltageRegulator] = []
    regulated_rail_name = "3V3" if vdd_nom <= 3.6 else "5V"

    prompt_lower = raw_prompt.lower()

    if supply_voltage_v is not None and supply_voltage_v > vdd_max:
        load_ma = _estimate_total_current_ma(all_components)

        # Detect whether a 5 V intermediate rail is needed:
        #   - supply > 6 V  (makes sense to have a 5 V stage)
        #   - prompt explicitly mentions "5v" or "5 volt"
        #   - MCU target is 3.3 V (cascade: supply→5V→3.3V)
        needs_5v_rail = (
            supply_voltage_v >= 6.0
            and ("5v" in prompt_lower or "5 volt" in prompt_lower)
            and vdd_nom <= 3.6
        )

        if needs_5v_rail:
            # --- Cascade: supply → 5V (AMS1117-5.0) → 3.3V (AMS1117-3.3) ---
            reg_5v, th_note_5v = _synthesize_voltage_regulator(
                supply_voltage_v, 5.0, load_ma, comp_id="U_LDO1"
            )
            # For the 5V→3.3V stage, use only 3.3V-capable parts at the 5V load
            reg_33, th_note_33 = _synthesize_voltage_regulator(
                5.0, vdd_nom, load_ma, comp_id="U_LDO2"
            )
            voltage_regulators.extend([reg_5v, reg_33])
            regulated_rail_name = reg_33.output_rail
            assumptions.append(
                f"5V intermediate rail: {supply_voltage_v:.0f}V → {reg_5v.mpn} → 5V_REG "
                f"→ {reg_33.mpn} → 3V3_REG (cascade for prompt-specified 5V logic rail)"
            )
            if th_note_5v:
                assumptions.append(th_note_5v)
            if th_note_33:
                assumptions.append(th_note_33)
        else:
            # --- Single regulator: supply → MCU VDD directly ---
            reg, th_note = _synthesize_voltage_regulator(
                supply_voltage_v, vdd_nom, load_ma, comp_id="U_LDO1"
            )
            voltage_regulators.append(reg)
            regulated_rail_name = reg.output_rail
            assumptions.append(
                f"Supply {supply_voltage_v:.1f}V > MCU VDD_MAX {vdd_max:.1f}V — "
                f"adding {reg.mpn} LDO ({reg.max_current_ma:.0f}mA capacity, "
                f"est. load {load_ma:.0f}mA) on {reg.input_rail}→{reg.output_rail}"
            )
            if th_note:
                assumptions.append(th_note)

    # --- Optional 1.8V rail (when prompt explicitly requests it) ---
    # Note: do NOT require voltage_regulators to be non-empty — the ESP32
    # module has an onboard 3.3V regulator so no external LDO is generated,
    # but a 1.8V rail still needs a discrete LDO.  regulated_rail_name
    # defaults to "3V3" in that case, which is the correct input rail.
    if re.search(r"1[,.]8\s*[vV]", raw_prompt):
        _1v8_rail_names = {r.output_rail for r in voltage_regulators}
        if "1V8_REG" not in _1v8_rail_names:
            _1v8_reg = VoltageRegulator(
                comp_id="U_LDO_1V8",
                mpn="MCP1700-1802E",
                manufacturer="Microchip",
                input_rail=regulated_rail_name,
                output_rail="1V8_REG",
                input_voltage_nom=3.3,
                output_voltage_nom=1.8,
                max_current_ma=250.0,
                package="SOT-23-3",
                unit_cost_usd=0.35,
            )
            voltage_regulators.append(_1v8_reg)
            assumptions.append(
                f"1.8V domain: {regulated_rail_name} → MCP1700-1802E → 1V8_REG "
                f"(prompt-specified 1.8V voltage domain, 250mA capacity)"
            )

    # --- Power rails ---
    power_rails: list[TopologyPowerRail] = []
    if voltage_regulators:
        # Always add the raw supply rail (e.g. VIN_12V)
        first_reg = voltage_regulators[0]
        power_rails.append(TopologyPowerRail(
            name=first_reg.input_rail,
            voltage_nominal=supply_voltage_v,         # type: ignore[arg-type]
            voltage_min=supply_voltage_v * 0.9,       # type: ignore[arg-type]
            voltage_max=supply_voltage_v * 1.1,       # type: ignore[arg-type]
        ))
        # Add intermediate rails (e.g. 5V_REG when cascading)
        for reg in voltage_regulators[:-1]:
            power_rails.append(TopologyPowerRail(
                name=reg.output_rail,
                voltage_nominal=reg.output_voltage_nom,
                voltage_min=reg.output_voltage_nom * 0.95,
                voltage_max=reg.output_voltage_nom * 1.05,
            ))
    power_rails.append(TopologyPowerRail(
        name=regulated_rail_name,
        voltage_nominal=vdd_nom,
        voltage_min=vdd_min,
        voltage_max=vdd_max,
    ))

    # --- Phase 22.1: Validate pin alt-functions against MCU profile ---
    _validate_all_pin_assignments(mcu_profile, buses, assumptions)

    # --- Phase 22.2: Detect pinmux conflicts (same GPIO used twice) ---
    _detect_pinmux_conflicts(buses, assumptions)

    passives = _synthesize_passives(buses, power_rails, all_components, voltage_regulators, mcu_profile=mcu_profile)

    # --- 1-Wire pull-up resistors (4.7 kΩ) for DS18B20 / DHT sensors ---
    # The DQ/DATA line is open-drain and requires an external pull-up to VDD.
    # Standard value per DS18B20 datasheet: 4.7 kΩ for parasitic power,
    # acceptable up to ~10 kΩ for short buses.  We use 4.7 kΩ (E12 standard).
    for _ow_cid, _ow_net in _gpio_onewire_nets:
        passives.append(PassiveComponent(
            comp_id=f"OW_PU_{_ow_cid}",
            category="resistor",
            value="4.7k",
            unit="Ω",
            purpose=f"onewire_pullup_{_ow_cid}",
            nets=[regulated_rail_name, _ow_net],
            package="0402",
            mpn_suggestion="RC0402FR-074K7L",
            unit_cost_usd=0.01,
        ))
        log.info("1-Wire pull-up: 4.7 kΩ added on %s (open-drain bus, DS18B20 requirement)", _ow_net)

    # --- Phase 22.3: Boot/Reset circuit generation ---
    _synthesize_boot_reset_circuit(mcu_profile, passives, assumptions, regulated_rail_name)

    # --- Phase 22.3b: QSPI Boot Flash (RP2040, i.MX RT, etc.) ---
    # MCUs that cannot boot from internal flash REQUIRE an external QSPI/SPI NOR flash.
    _BOOT_FLASH_MCUS = {"rp2040": "W25Q16JVSSIQ", "imxrt": "IS25WP064AJBLE"}
    _existing_mpns_lower = {c.mpn.lower() for c in all_components}
    _has_flash = any("w25q" in m or "flash" in m or "is25" in m or "at25" in m
                     for m in _existing_mpns_lower)
    if not _has_flash:
        for _boot_family, _boot_flash_mpn in _BOOT_FLASH_MCUS.items():
            if _boot_family in mcu.mpn.lower():
                _flash_sizes = {"W25Q16JVSSIQ": "16Mbit", "IS25WP064AJBLE": "64Mbit"}
                _flash_desc = f"{_boot_flash_mpn} {_flash_sizes.get(_boot_flash_mpn, '')} QSPI NOR Boot Flash"
                all_components.append(SelectedComponent(
                    mpn=_boot_flash_mpn,
                    manufacturer="Winbond" if "W25Q" in _boot_flash_mpn else "ISSI",
                    name=_flash_desc,
                    category="memory",
                    interface_types=["SPI"],
                    role="memory",
                    known_i2c_addresses=[],
                    init_contract_coverage=True,
                    unit_cost_usd=0.30,
                    score=0.95,
                    raw={
                        "mpn": _boot_flash_mpn,
                        "manufacturer": "Winbond" if "W25Q" in _boot_flash_mpn else "ISSI",
                        "name": _flash_desc,
                        "category": "memory",
                        "interface_types": ["SPI"],
                        "electrical_ratings": {
                            "io_voltage_nominal": 3.3,
                            "vdd_min": 2.7,
                            "vdd_max": 3.6,
                        },
                    },
                ))
                # Add QSPI bus
                _qspi_pins = _pick_mcu_pins(mcu.mpn, "SPI", use_llm=use_llm,
                                             mcu_profile=mcu_profile, pin_index=0,
                                             used_pins=_assigned_pins)
                if _qspi_pins:
                    _flash_comp_id = _boot_flash_mpn.replace("-", "_")
                    # Assign CS pin for the boot flash so the validator sees it
                    _cs_key = f"CS_{_flash_comp_id}"
                    if _cs_key not in _qspi_pins:
                        # Use NSS from profile if available, otherwise pick a free GPIO
                        _cs_gpio = _qspi_pins.pop("NSS", None) or _qspi_pins.pop("CS", None)
                        if _cs_gpio is None:
                            # RP2040: GP17 (SPI0 CSn = "GP17/CS" symbol pin pad 28)
                            # i.MX RT1062: GPIO_SD_B0_01 (pin 20, actual QSPI CS GPIO)
                            _cs_gpio = "GP17" if "rp2040" in mcu.mpn.lower() else "GPIO_SD_B0_01"
                        _qspi_pins[_cs_key] = _cs_gpio
                    _assigned_pins.update(_qspi_pins.values())
                    buses.append(TopologyBus(
                        name="qspi_boot",
                        bus_type="SPI",
                        master_id=_comp_id(mcu),
                        slave_ids=[_flash_comp_id],
                        pin_assignments=_qspi_pins,
                        slave_addresses={},
                    ))
                assumptions.append(
                    f"Phase 22.3b: {_boot_flash_mpn} QSPI boot flash added — "
                    f"{mcu.mpn} requires external flash for XIP boot"
                )
                log.info("Boot flash: %s added for %s (mandatory for XIP boot)", _boot_flash_mpn, mcu.mpn)
                break

    # --- Phase 22.4: Crystal + Load-Caps generation ---
    _synthesize_clock_circuit(mcu_profile, passives, all_components, assumptions,
                              mcu_mpn=mcu.mpn, raw_prompt=raw_prompt)

    # --- Phase 22.5: Level-Shifter detection + insertion ---
    _detect_voltage_mismatch_and_insert_levelshifter(
        mcu, sensors, buses, all_components, passives, assumptions, regulated_rail_name,
    )

    # --- Phase 22.7: Debug-Header + Test-Points ---
    _synthesize_debug_header(mcu_profile, mcu, all_components, passives, assumptions)

    # --- RF Antenna Connector — add U.FL when an RF transceiver is in the BOM ---
    # SX1276, SX1278, SX1262, RFM95W, CC1101, CC2500 all need an external antenna.
    # A U.FL connector (CONN-ANT-UFL) provides the coaxial footprint on the PCB.
    _RF_MPNS = frozenset({
        "SX1276", "SX1278", "SX1262", "SX1261", "SX1280",
        "RFM95W", "RFM96W", "RFM98W", "RFM69W", "RFM69HW",
        "CC1101", "CC1200", "CC2500",
        "nRF24L01", "nRF24L01+",
    })
    _ant_mpn = "CONN-ANT-UFL"
    _existing_mpns = {c.mpn for c in all_components}
    _has_rf = any(c.mpn.upper() in {m.upper() for m in _RF_MPNS} for c in all_components)
    if _has_rf and _ant_mpn not in _existing_mpns:
        all_components.append(SelectedComponent(
            mpn=_ant_mpn,
            manufacturer="Hirose",
            name="U.FL RF Antenna Connector (50Ω)",
            category="connector",
            interface_types=["RF"],
            role="connector",
            known_i2c_addresses=[],
            init_contract_coverage=True,
            unit_cost_usd=0.25,
            score=0.95,
            raw={
                "mpn": _ant_mpn,
                "manufacturer": "Hirose",
                "name": "U.FL RF Antenna Connector (50Ω)",
                "category": "connector",
                "interface_types": ["RF"],
            },
        ))
        log.info("RF antenna: added U.FL connector (%s) to BOM — connect 50Ω antenna/cable", _ant_mpn)

    # --- Peripheral Pattern Library: SPI/UART/CAN/USB bus-specific passives ---
    from boardsmith_hw.peripheral_patterns import synthesize_bus_pattern_passives
    _bp_counter: dict[str, int] = {}
    def _uid_bp(prefix: str) -> str:
        _bp_counter[prefix] = _bp_counter.get(prefix, 0) + 1
        return f"BP_{prefix}{_bp_counter[prefix]}"

    bus_pattern_passives = synthesize_bus_pattern_passives(
        buses=buses,
        mcu_profile=mcu_profile,
        reg_rail=regulated_rail_name,
        uid_fn=_uid_bp,
        assumptions=assumptions,
    )
    passives.extend(bus_pattern_passives)

    # --- Battery charger circuit (TP4056) ---
    _synthesize_battery_charger_circuit(all_components, passives, assumptions)

    # --- USB-C CC pull-down resistors (5.1 kΩ) ---
    # A USB-C connector in device/sink mode requires 5.1 kΩ pull-downs on CC1
    # and CC2 to GND so the host port identifies this as a 5V/900 mA device.
    # Without these resistors the host won't supply power (VBUS stays off).
    _usbc_conn_ids = [
        c for c in all_components if c.mpn == "USB-C-CONN"
    ]
    if _usbc_conn_ids:
        _cc_counter: dict[str, int] = {}
        def _uid_cc(prefix: str) -> str:
            _cc_counter[prefix] = _cc_counter.get(prefix, 0) + 1
            return f"CC_{prefix}{_cc_counter[prefix]}"
        _conn_id = _usbc_conn_ids[0].mpn.replace("-", "_")
        for _cc_pin in ("CC1", "CC2"):
            passives.append(PassiveComponent(
                comp_id=_uid_cc("R"),
                category="resistor",
                value="5.1k",
                unit="Ω",
                purpose=f"usbc_{_cc_pin.lower()}_pulldown",
                nets=[f"USB_C_CONN_{_cc_pin}", "GND"],
                package="0402",
                mpn_suggestion="RC0402FR-075K1L",
                unit_cost_usd=0.01,
            ))
        log.debug("USB-C: 5.1 kΩ CC1+CC2 pull-downs added (device/sink mode)")

    # --- MCU Profile: add mandatory components (boot-strap resistors, VDDA ferrite, etc.) ---
    if mcu_profile:
        _counter_mc: dict[str, int] = {}
        def _uid_mc(prefix: str) -> str:
            _counter_mc[prefix] = _counter_mc.get(prefix, 0) + 1
            return f"MC_{prefix}{_counter_mc[prefix]}"

        for mc in mcu_profile.mandatory_components:
            # Skip components already covered by generic decoupling (100nF, 10µF)
            if mc.component_type == "cap" and mc.value in ("100nF", "10µF", "10uF") and mc.quantity_rule in ("per_vdd_pin", "per_rail", "one_per_board"):
                continue  # Already handled by generic decoupling / bulk cap logic
            # Skip crystal + crystal load caps — already handled by _synthesize_clock_circuit (Phase 22.4)
            if mc.component_type == "crystal":
                continue
            if mc.component_type == "cap" and "crystal" in (mc.rationale or "").lower():
                continue

            category = mc.component_type
            if category in ("crystal", "ferrite"):
                category = "capacitor"  # Represented as passives in topology
            nets = [regulated_rail_name, "GND"]
            if mc.connectivity:
                nets = [mc.connectivity.net_name, "GND"]

            mpn = _MANDATORY_PASSIVE_MPN.get((mc.component_type, mc.value), "")

            passives.append(PassiveComponent(
                comp_id=_uid_mc("R" if mc.component_type == "resistor" else "C" if mc.component_type in ("cap", "ferrite") else "X"),
                category=mc.component_type,
                value=mc.value,
                unit="Ω" if mc.component_type == "resistor" else "F" if mc.component_type in ("cap", "ferrite") else "",
                purpose=f"mcu_mandatory_{mc.rationale[:40].replace(' ', '_')}" if mc.rationale else f"mcu_mandatory_{mc.component_type}",
                nets=nets,
                package=mc.spec.split()[-1] if mc.spec and any(p in mc.spec for p in ("0402", "0603", "0805")) else "0402",
                mpn_suggestion=mpn,
                unit_cost_usd=0.02,
            ))
        assumptions.append(f"MCU profile: {len(mcu_profile.mandatory_components)} mandatory components applied from {mcu_profile.identity.mpn} Device Profile")

    # --- MCU Profile: add debug header info as assumption ---
    if mcu_profile and mcu_profile.debug_interfaces:
        dbg = mcu_profile.debug_interfaces[0]
        pin_desc = ", ".join(f"{k}={v}" for k, v in dbg.pins.items())
        assumptions.append(f"Debug interface: {dbg.protocol} ({pin_desc})")
        if dbg.recommended_connector:
            assumptions.append(f"Debug connector: {dbg.recommended_connector.name} ({dbg.recommended_connector.footprint})")

    # --- MCU Profile: reserved pin warnings ---
    if reserved_pins:
        assumptions.append(f"Reserved pins (do not use as GPIO): {', '.join(sorted(reserved_pins)[:8])}{'...' if len(reserved_pins) > 8 else ''}")
    if boot_strap_pins:
        assumptions.append(f"Boot-strap pins (avoid for general I/O): {', '.join(sorted(boot_strap_pins))}")

    # --- Analog circuit templates ---
    # For each analog component (op-amp, comparator, voltage reference), instantiate
    # the best-fit circuit template, generating passive feedback networks and signal nets.
    analog_nets: list[AnalogNet] = []
    opamp_idx = 0
    for comp in sensors:
        if comp.category.lower() != "analog":
            continue
        cid = _comp_id(comp)
        template_id = _infer_template_id(comp, prompt_lower)
        # Seed parameters from template defaults so all required names are present
        params = _default_params_for_template(template_id)
        in_net = f"ANALOG_IN{opamp_idx}"
        out_net = f"ANALOG_OUT{opamp_idx}"
        a_passives, a_nets = _instantiate_circuit_template(
            template_id, cid, f"OPAMP{opamp_idx}", params, in_net, out_net,
        )
        passives.extend(a_passives)
        analog_nets.extend(a_nets)
        opamp_idx += 1
        assumptions.append(
            f"Analog template '{template_id}' instantiated for {comp.mpn} (prefix=OPAMP{opamp_idx - 1})"
        )

    # --- Split assumptions into real assumptions (penalised) vs informational
    # notes (displayed in the report but NOT counted for confidence penalty).
    # Profile-derived entries and standard peripheral patterns are deterministic
    # and should not penalise confidence.
    _NOTE_PREFIXES = (
        "Phase 22.3:",       # reset / boot from MCU profile
        "Phase 22.3b:",      # QSPI boot flash (required for RP2040)
        "Phase 22.4:",       # crystal from MCU profile
        "MCU profile:",      # mandatory components applied
        "Debug interface:",  # SWD / JTAG info
        "Debug connector:",  # debug header info
        "Reserved pins",     # profile info
        "Boot-strap pins",   # profile info
        "I2C pattern",       # standard peripheral pattern
        "SPI pattern",       # standard peripheral pattern
    )
    real_assumptions: list[str] = []
    notes: list[str] = []
    for a in assumptions:
        if any(a.startswith(pfx) for pfx in _NOTE_PREFIXES):
            notes.append(a)
        else:
            real_assumptions.append(a)

    return SynthesizedTopology(
        components=all_components,
        buses=buses,
        power_rails=power_rails,
        passives=passives,
        voltage_regulators=voltage_regulators,
        assumptions=real_assumptions,
        notes=notes,
        analog_nets=analog_nets + _gpio_data_nets,
    )


# ---------------------------------------------------------------------------
# Voltage regulator selection
# ---------------------------------------------------------------------------

# LDO library — ordered by max_current_ma ascending so the smallest
# adequate part is selected first (minimises cost/size).
_LDO_LIBRARY = [
    # MCP1700-3302E: 250 mA, ultra-low quiescent (1.6 µA) — ideal for battery IoT
    {
        "mpn": "MCP1700-3302E",
        "manufacturer": "Microchip",
        "output_v": 3.3,
        "max_input_v": 6.0,
        "max_current_ma": 250.0,
        "dropout_v": 0.178,
        "package": "SOT-23-3",
        "unit_cost_usd": 0.50,
    },
    # AP2112K-3.3TRG1: 600 mA, low dropout (300 mV), low noise — good for RF
    {
        "mpn": "AP2112K-3.3TRG1",
        "manufacturer": "Diodes Inc",
        "output_v": 3.3,
        "max_input_v": 6.0,
        "max_current_ma": 600.0,
        "dropout_v": 0.3,
        "package": "SOT-25",
        "unit_cost_usd": 0.25,
    },
    # AMS1117-3.3: 800 mA, 1.2 V dropout — ubiquitous dev-board regulator
    {
        "mpn": "AMS1117-3.3",
        "manufacturer": "Advanced Monolithic Systems",
        "output_v": 3.3,
        "max_input_v": 15.0,
        "max_current_ma": 800.0,
        "dropout_v": 1.2,
        "package": "SOT-223",
        "unit_cost_usd": 0.30,
    },
    # AMS1117-5.0: 800 mA 5V output — used as 12V→5V intermediate rail LDO
    # Accepts up to 15 V input (suited for 12 V motor supply systems).
    {
        "mpn": "AMS1117-5.0",
        "manufacturer": "Advanced Monolithic Systems",
        "output_v": 5.0,
        "max_input_v": 15.0,
        "max_current_ma": 800.0,
        "dropout_v": 1.2,
        "package": "SOT-223",
        "unit_cost_usd": 0.30,
    },
    # LM2940CT-3.3: 1 A, 26 V max input — suited for 24 V industrial supplies
    # Low dropout (~0.5 V at 1 A), TO-220 package, robust reverse-battery protection.
    {
        "mpn": "LM2940CT-3.3",
        "manufacturer": "Texas Instruments",
        "output_v": 3.3,
        "max_input_v": 26.0,
        "max_current_ma": 1000.0,
        "dropout_v": 0.5,
        "package": "TO-220",
        "unit_cost_usd": 1.20,
    },
]

# Safety margin applied during LDO current selection (20 %).
_LDO_SAFETY_MARGIN = 0.20


def _estimate_total_current_ma(components: list[SelectedComponent]) -> float:
    """Estimate total max current draw (mA) across all active components.

    Uses ``electrical_ratings.current_draw_max_ma`` when available, then
    falls back to MPN keywords and role-based estimates.
    """
    # MPN-keyword → logic-supply current (mA).
    # Motor drivers are listed here so their MOTOR OUTPUT current (from the KB's
    # current_draw_max_ma) is NOT used — only the VCC logic supply current matters.
    _MPN_FALLBACKS: dict[str, float] = {
        "esp32": 240.0, "esp32c3": 150.0, "rp2040": 25.0,
        "stm32": 50.0, "nrf52": 15.0,
        "bme280": 3.6, "bmp280": 2.8, "aht20": 0.3, "mpu6050": 3.9,
        "ssd1306": 9.0, "sx1276": 120.0, "nrf24": 115.0,
        # Motor drivers — use VCC logic current only (motor output current is on VM rail)
        "tb6612": 100.0, "drv8833": 80.0, "l298": 120.0,
    }
    _ROLE_FALLBACKS: dict[str, float] = {
        "mcu": 100.0, "sensor": 5.0, "display": 20.0,
        "comms": 50.0, "actuator": 200.0,
    }
    total = 0.0
    for comp in components:
        mpn_low = comp.mpn.lower()
        # MPN-keyword overrides come FIRST — this ensures motor drivers use their
        # logic-supply current estimate rather than the KB motor-sink current.
        matched = False
        for kw, ma in _MPN_FALLBACKS.items():
            if kw in mpn_low:
                total += ma
                matched = True
                break
        if matched:
            continue
        # Explicit KB value (skip for components handled above)
        ratings = comp.raw.get("electrical_ratings", {})
        explicit = ratings.get("current_draw_max_ma")
        if explicit is not None:
            try:
                total += float(explicit)
                continue
            except (TypeError, ValueError):
                pass
        # Role-based fallback
        total += _ROLE_FALLBACKS.get(comp.role.lower(), 10.0)
    return total


_LDO_THERMAL_LIMIT_W = 2.0   # Max allowable LDO dissipation before a note is added


def _synthesize_voltage_regulator(
    supply_v: float,
    target_v: float,
    load_current_ma: float = 0.0,
    comp_id: str = "U_LDO1",
) -> tuple["VoltageRegulator", str | None]:
    """Choose the smallest adequate LDO for supply_v → target_v at load_current_ma.

    Selection criteria (all must pass):
      1. supply_v ≤ LDO max_input_v
      2. (supply_v − dropout_v) ≥ target_v  (no under-voltage at output)
      3. LDO output_v matches target_v (±5 %)
      4. LDO max_current_ma ≥ load_current_ma × (1 + safety_margin)

    Returns (VoltageRegulator, thermal_note | None).
    thermal_note is set when estimated P_diss > _LDO_THERMAL_LIMIT_W.
    """
    required_ma = load_current_ma * (1.0 + _LDO_SAFETY_MARGIN) if load_current_ma > 0 else 0.0

    for ldo in _LDO_LIBRARY:
        # Require output voltage match within 5 %
        if abs(ldo["output_v"] - target_v) > target_v * 0.05:
            continue
        voltage_ok = (
            supply_v <= ldo["max_input_v"]
            and (supply_v - ldo["dropout_v"]) >= target_v
        )
        current_ok = ldo["max_current_ma"] >= required_ma
        if voltage_ok and current_ok:
            thermal_note = None
            p_diss = (supply_v - target_v) * (load_current_ma / 1000.0)
            if p_diss > _LDO_THERMAL_LIMIT_W:
                thermal_note = (
                    f"Thermal warning: {ldo['mpn']} dissipates "
                    f"{p_diss:.1f}W ({supply_v:.0f}V→{target_v:.1f}V @ {load_current_ma:.0f}mA) "
                    f"— consider a switching regulator"
                )
            return VoltageRegulator(
                comp_id=comp_id,
                mpn=ldo["mpn"],
                manufacturer=ldo["manufacturer"],
                input_rail=f"VIN_{int(supply_v)}V",
                output_rail="3V3_REG" if abs(target_v - 3.3) < 0.1 else f"V{target_v:.0f}V_REG",
                input_voltage_nom=supply_v,
                output_voltage_nom=target_v,
                max_current_ma=ldo["max_current_ma"],
                package=ldo["package"],
                unit_cost_usd=ldo["unit_cost_usd"],
            ), thermal_note
    # Ultimate fallback — pick nearest fixed-voltage AMS1117 variant.
    # For supply voltages that exceed every LDO's max_input_v, emit a clear
    # safety warning so designers know to replace this part.
    _max_library_vin = max(ldo["max_input_v"] for ldo in _LDO_LIBRARY)
    _vin_overage = supply_v > _max_library_vin
    _is_5v_target = abs(target_v - 5.0) < 0.3
    fallback_mpn = "AMS1117-5.0" if _is_5v_target else "AMS1117-3.3"
    fallback_out_v = 5.0 if _is_5v_target else 3.3
    fallback_rail = "V5V_REG" if _is_5v_target else "3V3_REG"
    p_diss = (supply_v - fallback_out_v) * (load_current_ma / 1000.0)
    thermal_note = None
    if _vin_overage:
        thermal_note = (
            f"SAFETY WARNING: {fallback_mpn} max input is "
            f"{next(l['max_input_v'] for l in _LDO_LIBRARY if l['mpn'] == fallback_mpn):.0f}V "
            f"but supply is {supply_v:.0f}V — replace with a buck converter "
            f"(e.g. TPS54360) or cascade regulator before production"
        )
    elif p_diss > _LDO_THERMAL_LIMIT_W:
        thermal_note = (
            f"Thermal warning: {fallback_mpn} fallback dissipates "
            f"{p_diss:.1f}W ({supply_v:.0f}V→{fallback_out_v:.1f}V @ {load_current_ma:.0f}mA) "
            f"— consider a switching regulator"
        )
    return VoltageRegulator(
        comp_id=comp_id,
        mpn=fallback_mpn,
        manufacturer="Advanced Monolithic Systems",
        input_rail=f"VIN_{int(supply_v)}V",
        output_rail=fallback_rail,
        input_voltage_nom=supply_v,
        output_voltage_nom=fallback_out_v,
        max_current_ma=800.0,
        package="SOT-223",
        unit_cost_usd=0.30,
    ), thermal_note


# ---------------------------------------------------------------------------
# DB-3 Pattern Library integration — formula-based passive sizing
# ---------------------------------------------------------------------------

def _pattern_i2c_pullup_value(n_slaves: int) -> tuple[str, str]:
    """Use Pattern Library i2c_pullup_v1 to calculate I2C pullup value.

    Returns (value_str, mpn_suggestion) or falls back to ("4.7k", default_mpn).
    n_slaves is used to estimate bus capacitance (each device adds ~10pF).
    """
    try:
        from shared.knowledge.patterns import get_pattern
        pattern = get_pattern("i2c_pullup_v1")
        if pattern is None:
            return "4.7k", "RC0402FR-074K7L"
        # Estimate C_bus: 100pF base + 10pF per slave
        c_bus_pf = 100.0 + max(0, n_slaves - 1) * 10.0
        params = pattern.resolve_parameters({"C_bus_pf": c_bus_pf, "t_rise_ns": 300.0})
        r_ohm = float(eval(  # noqa: S307 — controlled expression from trusted pattern data
            "t_rise_ns*1e-9 / (0.8473 * C_bus_pf*1e-12)",
            {"__builtins__": {}},
            params,
        ))
        r_e12 = _nearest_e12(r_ohm)
        val_str = _format_passive_value(r_e12, "Ω")
        # Pick closest standard MPN
        if r_e12 <= 1500:
            mpn = "RC0402FR-071KL"
        elif r_e12 <= 2700:
            mpn = "RC0402FR-072K2L"
        elif r_e12 <= 5600:
            mpn = "RC0402FR-074K7L"
        else:
            mpn = "RC0402FR-0710KL"
        return val_str, mpn
    except Exception:
        return "4.7k", "RC0402FR-074K7L"


# ---------------------------------------------------------------------------
# Passive synthesis
# ---------------------------------------------------------------------------

def _synthesize_passives(
    buses: list[TopologyBus],
    power_rails: list[TopologyPowerRail],
    active_components: list[SelectedComponent],
    voltage_regulators: list[VoltageRegulator] | None = None,
    mcu_profile=None,
) -> list[PassiveComponent]:
    """Derive required passives from topology:
    - I2C pull-up resistors (4.7 kΩ) on SDA + SCL per I2C bus
    - 100 nF decoupling cap per active IC power pin
    - 10 µF bulk cap per power rail
    - LDO bypass caps: 10 µF input + 10 µF + 100 nF output
    """
    passives: list[PassiveComponent] = []
    counter: dict[str, int] = {}

    def _uid(prefix: str) -> str:
        counter[prefix] = counter.get(prefix, 0) + 1
        return f"{prefix}{counter[prefix]}"

    # Regulated rail name (first non-VIN rail)
    reg_rail = next(
        (pr.name for pr in power_rails if not pr.name.startswith("VIN")),
        power_rails[0].name if power_rails else "3V3",
    )

    # --- I2C pull-up resistors ---
    i2c_buses = [b for b in buses if b.bus_type == "I2C"]
    for bus in i2c_buses:
        # Profile-aware pull-up value (Layer 1: MCU profile → Layer 2: Pattern Library → fallback)
        pullup_val = "4.7k"
        pullup_mpn = "RC0402FR-074K7L"
        if mcu_profile:
            from boardsmith_hw.peripheral_patterns import i2c_pullup_from_profile
            pullup_val = i2c_pullup_from_profile(mcu_profile, bus.name)
            if pullup_val == "2.2k":
                pullup_mpn = "RC0402FR-072K2L"
            elif pullup_val == "1k":
                pullup_mpn = "RC0402FR-071KL"
            elif pullup_val == "10k":
                pullup_mpn = "RC0402FR-0710KL"
        else:
            # DB-3: Pattern Library formula — R = t_rise / (0.8473 × C_bus)
            n_slaves = len(bus.slave_ids)
            pullup_val, pullup_mpn = _pattern_i2c_pullup_value(n_slaves)
        sda_net = f"{bus.name}_SDA"
        scl_net = f"{bus.name}_SCL"
        passives.append(PassiveComponent(
            comp_id=_uid("R"),
            category="resistor",
            value=pullup_val,
            unit="Ω",
            purpose=f"i2c_pullup_sda_{bus.name}",
            nets=[reg_rail, sda_net],
            package="0402",
            mpn_suggestion=pullup_mpn,
            unit_cost_usd=0.01,
        ))
        passives.append(PassiveComponent(
            comp_id=_uid("R"),
            category="resistor",
            value=pullup_val,
            unit="Ω",
            purpose=f"i2c_pullup_scl_{bus.name}",
            nets=[reg_rail, scl_net],
            package="0402",
            mpn_suggestion=pullup_mpn,
            unit_cost_usd=0.01,
        ))

    # --- 100 nF decoupling caps per active IC ---
    for comp in active_components:
        passives.append(PassiveComponent(
            comp_id=_uid("C"),
            category="capacitor",
            value="100n",
            unit="F",
            purpose=f"decoupling_vdd_{comp.mpn.replace('-', '_')}",
            nets=[reg_rail, "GND"],
            package="0402",
            mpn_suggestion="GRM155R71C104KA88D",  # Murata 100nF 16V X7R 0402
            unit_cost_usd=0.02,
        ))

    # --- 10 µF bulk cap per power rail ---
    for rail in power_rails:
        passives.append(PassiveComponent(
            comp_id=_uid("C"),
            category="capacitor",
            value="10u",
            unit="F",
            purpose=f"bulk_cap_{rail.name}",
            nets=[rail.name, "GND"],
            package="0603",
            mpn_suggestion="GRM188R61A106KE69D",  # Murata 10µF 10V X5R 0603
            unit_cost_usd=0.05,
        ))

    # --- LDO bypass caps (input + output) ---
    for reg in (voltage_regulators or []):
        # Input bypass: 10 µF bulk
        passives.append(PassiveComponent(
            comp_id=_uid("C"),
            category="capacitor",
            value="10u",
            unit="F",
            purpose=f"ldo_input_cap_{reg.comp_id}",
            nets=[reg.input_rail, "GND"],
            package="0603",
            mpn_suggestion="GRM188R61A106KE69D",
            unit_cost_usd=0.05,
        ))
        # Output bypass: 10 µF bulk + 100 nF noise decoupling
        passives.append(PassiveComponent(
            comp_id=_uid("C"),
            category="capacitor",
            value="10u",
            unit="F",
            purpose=f"ldo_output_bulk_{reg.comp_id}",
            nets=[reg.output_rail, "GND"],
            package="0603",
            mpn_suggestion="GRM188R61A106KE69D",
            unit_cost_usd=0.05,
        ))
        passives.append(PassiveComponent(
            comp_id=_uid("C"),
            category="capacitor",
            value="100n",
            unit="F",
            purpose=f"ldo_output_noise_{reg.comp_id}",
            nets=[reg.output_rail, "GND"],
            package="0402",
            mpn_suggestion="GRM155R71C104KA88D",
            unit_cost_usd=0.02,
        ))

    # --- Discrete actuator passives ---
    # LED series resistor: 330 Ω limits current to ~10 mA from 3.3 V (Vf ≈ 2.1 V)
    # Transistor base resistor: 1 kΩ limits base current for clean switching at 3.3 V GPIO
    # Button pull-up: 10 kΩ pull-up to VCC for debounce-friendly GPIO input
    for comp in active_components:
        tags = [t.lower() for t in comp.raw.get("tags", [])]
        if "led" in tags:
            passives.append(PassiveComponent(
                comp_id=_uid("R"),
                category="resistor",
                value="330",
                unit="Ω",
                purpose=f"led_series_{comp.mpn.replace('-', '_').replace(' ', '_')}",
                nets=[reg_rail, f"LED_{comp.mpn.replace('-', '_').upper()}_A"],
                package="0402",
                mpn_suggestion="RC0402FR-07330RL",   # Yageo 330 Ω 1 % 0402
                unit_cost_usd=0.01,
            ))
        # BJT base resistor — only for NPN/PNP BJTs, NOT for MOSFETs
        if ("npn" in tags or "pnp" in tags) and "mosfet" not in tags and "nmos" not in tags:
            passives.append(PassiveComponent(
                comp_id=_uid("R"),
                category="resistor",
                value="1k",
                unit="Ω",
                purpose=f"transistor_base_{comp.mpn.replace('-', '_').replace(' ', '_')}",
                nets=["GPIO_PWM", f"BJT_{comp.mpn.replace('-', '_').upper()}_B"],
                package="0402",
                mpn_suggestion="RC0402FR-071KL",     # Yageo 1 kΩ 1 % 0402
                unit_cost_usd=0.01,
            ))
        if "button" in tags or "taster" in tags:
            passives.append(PassiveComponent(
                comp_id=_uid("R"),
                category="resistor",
                value="10k",
                unit="Ω",
                purpose=f"button_pullup_{comp.mpn.replace('-', '_').replace(' ', '_')}",
                nets=[reg_rail, f"BTN_{comp.mpn.replace('-', '_').upper()}_IN"],
                package="0402",
                mpn_suggestion="RC0402FR-0710KL",    # Yageo 10 kΩ 1 % 0402
                unit_cost_usd=0.01,
            ))
        if "mosfet" in tags or "nmos" in tags or ("motor" in tags and "n-channel" in tags):
            # Gate resistor: 100 Ω limits gate charge current, prevents ringing
            passives.append(PassiveComponent(
                comp_id=_uid("R"),
                category="resistor",
                value="100",
                unit="Ω",
                purpose=f"mosfet_gate_{comp.mpn.replace('-', '_').replace(' ', '_')}",
                nets=["GPIO_PWM", f"MOSFET_{comp.mpn.replace('-', '_').upper()}_G"],
                package="0402",
                mpn_suggestion="RC0402FR-07100RL",   # Yageo 100 Ω 1 % 0402
                unit_cost_usd=0.01,
            ))
            # Flyback diode: 1N4007 across inductive load (motor)
            passives.append(PassiveComponent(
                comp_id=_uid("D"),
                category="diode",
                value="1N4007",
                unit="",
                purpose=f"flyback_{comp.mpn.replace('-', '_').replace(' ', '_')}",
                nets=["GND", "MOTOR_+"],
                package="DO-41",
                mpn_suggestion="1N4007",
                unit_cost_usd=0.05,
            ))
        # INA226 / INA219 current sense shunt: 0.1 Ω, 1%, 2W in 2512 package
        # Placed in series with the high-side current path (SHUNT_IN+ → SHUNT_IN-)
        mpn_lo = comp.mpn.lower()
        if "ina226" in mpn_lo or "ina219" in mpn_lo or ("current" in tags and "monitor" in tags):
            passives.append(PassiveComponent(
                comp_id=_uid("R"),
                category="resistor",
                value="0.1",
                unit="Ω",
                purpose=f"shunt_{comp.mpn.replace('-', '_').replace(' ', '_')}",
                nets=["SHUNT_IN+", "SHUNT_IN-"],
                package="2512",           # High-power package (2W continuous)
                mpn_suggestion="WSL25120L000FEA",  # Vishay 0.1 Ω 1% 2W 2512
                unit_cost_usd=0.30,
            ))
        # RS485 transceiver: 120 Ω termination resistor across A/B lines
        # Exclude digital isolators (ADUM, ISO, Si86xx) — they carry RS485 tag
        # but are NOT transceivers and don't connect to the differential bus.
        _is_isolator = "isolator" in tags or any(kw in mpn_lo for kw in ["adum", "iso7", "si86"])
        if not _is_isolator and ("rs485" in tags or any(kw in mpn_lo for kw in ["max485", "max3485", "sn65hvd", "sp3485"])):
            passives.append(PassiveComponent(
                comp_id=_uid("R"),
                category="resistor",
                value="120",
                unit="Ω",
                purpose=f"rs485_term_{comp.mpn.replace('-', '_').replace(' ', '_')}",
                nets=["RS485_A", "RS485_B"],
                package="0402",
                mpn_suggestion="RC0402FR-07120RL",   # Yageo 120 Ω 1% 0402
                unit_cost_usd=0.01,
            ))

    return passives


# ---------------------------------------------------------------------------
# LLM helpers (B4 boost — graceful fallback on any error)
# ---------------------------------------------------------------------------

def _llm_suggest_interface(
    mcu_mpn: str,
    sensor_mpn: str,
    sensor_name: str,
    supported_ifaces: list[str],
) -> str | None:
    """Ask LLM which bus interface is best for this sensor+MCU combo.

    Returns "I2C", "SPI", or None (skip/error → caller uses default).
    """
    try:
        from llm.gateway import get_default_gateway
        from llm.types import TaskType

        gateway = get_default_gateway()
        if not gateway.is_llm_available():
            return None

        iface_list = "/".join(supported_ifaces)
        resp = gateway.complete_sync(
            task=TaskType.COMPONENT_SUGGEST,
            messages=[{"role": "user", "content": (
                f"MCU: {mcu_mpn}\n"
                f"Sensor: {sensor_mpn} ({sensor_name})\n"
                f"Supported interfaces: {iface_list}\n\n"
                "Which bus interface should this sensor use in a typical embedded design? "
                "Reply with ONLY the interface name: I2C or SPI. No explanation."
            )}],
            temperature=0.0,
            max_tokens=10,
        )
        if resp.skipped or not resp.content:
            return None
        content = resp.content.strip().upper()
        for iface in supported_ifaces:
            if iface.upper() in content:
                return iface.upper()
        return None
    except Exception:
        return None


def _llm_suggest_pins(mcu_mpn: str, bus_type: str) -> dict[str, str] | None:
    """Ask LLM for typical GPIO pin assignments for an unknown MCU.

    Returns a dict like {"SDA": "GPIO14", "SCL": "GPIO15"} or None on failure.
    """
    try:
        from llm.gateway import get_default_gateway
        from llm.types import TaskType

        gateway = get_default_gateway()
        if not gateway.is_llm_available():
            return None

        if bus_type == "I2C":
            signals = "SDA, SCL"
            example = '{"SDA": "GPIO14", "SCL": "GPIO15"}'
            required = {"SDA", "SCL"}
        else:
            signals = "MOSI, MISO, SCK"
            example = '{"MOSI": "GPIO11", "MISO": "GPIO12", "SCK": "GPIO13"}'
            required = {"MOSI", "MISO", "SCK"}

        resp = gateway.complete_sync(
            task=TaskType.COMPONENT_SUGGEST,
            messages=[{"role": "user", "content": (
                f"MCU: {mcu_mpn}\n"
                f"Bus type: {bus_type} — signals needed: {signals}\n\n"
                f"Return ONLY a JSON object with the typical default {bus_type} GPIO pin "
                f"names for this MCU. Example: {example}\n"
                "Return ONLY valid JSON, nothing else."
            )}],
            temperature=0.0,
            max_tokens=80,
        )
        if resp.skipped or not resp.content:
            return None

        match = re.search(r'\{[^}]+\}', resp.content, re.DOTALL)
        if not match:
            return None

        pins: dict[str, str] = json.loads(match.group())
        # Normalise SCLK → SCK
        if "SCLK" in pins and "SCK" not in pins:
            pins["SCK"] = pins.pop("SCLK")
        # Validate required keys present
        if not required.issubset(pins.keys()):
            return None
        return {k: str(v) for k, v in pins.items()}

    except Exception:
        return None


def _comp_id(c: SelectedComponent) -> str:
    """Derive a stable component ID from MPN.

    For duplicate components (instance_idx > 0), append a numeric suffix
    so two instances of the same MPN get different IDs (e.g. TB6612FNG_2).
    """
    base = c.mpn.replace("-", "_").replace(" ", "_").upper()
    return f"{base}_{c.instance_idx + 1}" if c.instance_idx > 0 else base

