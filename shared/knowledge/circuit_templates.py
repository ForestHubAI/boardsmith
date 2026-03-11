# SPDX-License-Identifier: AGPL-3.0-or-later
"""Analog & mixed-signal circuit template library.

Each CircuitTemplate is a parameterisable subcircuit block that the topology
synthesizer can instantiate when a prompt mentions a matching keyword.  The
library covers common analog signal-conditioning patterns (op-amp stages,
filters, comparators, voltage dividers) plus generic discrete blocks.

Usage::

    lib = CircuitTemplateLibrary()
    templates = lib.find_by_keyword("verstärker")   # -> [noninverting_amp, ...]
    t = lib.get("noninverting_amp")
    # -> CircuitTemplate(...)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PassiveRecipe:
    """Describes how to calculate one passive component's value from parameters.

    ``value_expr`` is a Python expression evaluated with the template parameters
    in scope (e.g. ``"R_in * (gain - 1)"``).  The result is in SI units
    (ohms / farads) and is rounded to the nearest E12 value by the instantiator
    for resistors.

    ``nets_template`` is a 2-element list of net-name templates that map to
    passive pins 1 and 2 respectively.  Use ``{prefix}`` as a placeholder for
    the instance prefix (e.g. ``"OPAMP0"``).
    """
    comp_id_key: str          # e.g. "R_f"  → instance ID becomes "{prefix}_R_f"
    category: str             # "resistor" | "capacitor"
    value_expr: str           # Python expression yielding Ω or F
    unit: str                 # "Ω" | "F"
    nets_template: list[str]  # 2 net names; {prefix} is substituted at instantiation
    package: str = "0402"
    mpn_hint: str = ""        # Optional MPN hint (e.g. specific cap dielectric)


@dataclass
class NetTemplate:
    """Describes one signal net in the template.

    ``pins`` is a list of (component_role_key, pin_name) pairs.
    ``component_role_key`` is either ``"opamp"`` (for the active device) or
    the ``comp_id_key`` of a passive recipe (e.g. ``"R_f"``).
    """
    name_template: str                    # e.g. "{prefix}_FB"
    is_bus: bool = False
    is_power: bool = False
    pins: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class CircuitTemplate:
    """A parameterisable analog/discrete subcircuit block."""
    id: str                              # unique slug, e.g. "noninverting_amp"
    name: str                            # human-readable, e.g. "Non-Inverting Amplifier"
    description: str
    circuit_type: str                    # "analog" | "digital" | "power"
    keywords: list[str]                  # lower-case trigger words
    required_component_roles: list[str]  # e.g. ["opamp"] — what active device is needed
    parameters: dict[str, dict[str, Any]]  # {"gain": {"type": "float", "default": 2.0}}
    passive_recipes: list[PassiveRecipe]
    net_templates: list[NetTemplate]
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Built-in template definitions
# ---------------------------------------------------------------------------

_TEMPLATES: list[CircuitTemplate] = [

    # ------------------------------------------------------------------
    # 1. Non-Inverting Amplifier
    #    OUT = IN × Gain   (Gain ≥ 1)
    #    R_f = R_in × (Gain − 1)
    # ------------------------------------------------------------------
    CircuitTemplate(
        id="noninverting_amp",
        name="Non-Inverting Amplifier",
        description=(
            "Op-amp non-inverting stage.  Output voltage = Input × Gain "
            "(Gain ≥ 1).  Feedback network: R_f from OUT to IN−, R_in from "
            "IN− to GND.  Gain = 1 + R_f/R_in."
        ),
        circuit_type="analog",
        keywords=[
            "amplifier", "verstärker", "non-inverting", "nichtinvertierend",
            "noninverting", "op-amp", "opamp", "op amp",
            "gain", "verstärkung", "signal conditioning", "signalaufbereitung",
            "verstärker schaltung", "op-amp schaltung",
        ],
        required_component_roles=["opamp"],
        parameters={
            "gain": {"type": "float", "default": 2.0, "min": 1.001,
                     "description": "Voltage gain (≥1)"},
            "R_in": {"type": "float", "default": 10000.0,
                     "description": "Input resistor to GND in ohms (sets impedance)"},
        },
        passive_recipes=[
            PassiveRecipe(
                comp_id_key="R_in",
                category="resistor",
                value_expr="R_in",
                unit="Ω",
                nets_template=["{prefix}_FB", "GND"],
                package="0402",
            ),
            PassiveRecipe(
                comp_id_key="R_f",
                category="resistor",
                value_expr="R_in * (gain - 1)",
                unit="Ω",
                nets_template=["{prefix}_OUT", "{prefix}_FB"],
                package="0402",
            ),
        ],
        net_templates=[
            NetTemplate("{prefix}_IN",  pins=[("opamp", "IN+")]),
            NetTemplate("{prefix}_FB",  pins=[("opamp", "IN-"), ("R_f", "2"), ("R_in", "1")]),
            NetTemplate("{prefix}_OUT", pins=[("opamp", "OUT"),  ("R_f", "1")]),
        ],
        notes=[
            "Connect {prefix}_IN to sensor output / signal source",
            "Connect {prefix}_OUT to MCU ADC input",
            "V+ → +3V3, V− → GND (single-supply operation)",
        ],
    ),

    # ------------------------------------------------------------------
    # 2. Inverting Amplifier
    #    OUT = −IN × |Gain|
    #    R_f = R_in × |Gain|
    # ------------------------------------------------------------------
    CircuitTemplate(
        id="inverting_amp",
        name="Inverting Amplifier",
        description=(
            "Op-amp inverting stage.  Output inverts and scales the input.  "
            "Gain magnitude = R_f / R_in.  IN+ is biased to mid-supply for "
            "single-supply operation."
        ),
        circuit_type="analog",
        keywords=[
            "inverting amplifier", "invertierender verstärker",
            "inv amp", "invertierender op-amp", "inverting op-amp",
            "invertieren", "phase inversion", "phasenumkehr",
        ],
        required_component_roles=["opamp"],
        parameters={
            "gain_mag": {"type": "float", "default": 2.0, "min": 0.01,
                         "description": "Magnitude of voltage gain"},
            "R_in": {"type": "float", "default": 10000.0,
                     "description": "Input resistor in ohms"},
        },
        passive_recipes=[
            PassiveRecipe(
                comp_id_key="R_in",
                category="resistor",
                value_expr="R_in",
                unit="Ω",
                nets_template=["{prefix}_IN", "{prefix}_SUM"],
                package="0402",
            ),
            PassiveRecipe(
                comp_id_key="R_f",
                category="resistor",
                value_expr="R_in * gain_mag",
                unit="Ω",
                nets_template=["{prefix}_OUT", "{prefix}_SUM"],
                package="0402",
            ),
            # Bias resistor for IN+ — R_bias = R_in || R_f
            PassiveRecipe(
                comp_id_key="R_bias",
                category="resistor",
                value_expr="(R_in * R_in * gain_mag) / (R_in + R_in * gain_mag)",
                unit="Ω",
                nets_template=["{prefix}_BIAS", "GND"],
                package="0402",
            ),
        ],
        net_templates=[
            NetTemplate("{prefix}_IN",   pins=[("R_in", "1")]),
            NetTemplate("{prefix}_SUM",  pins=[("opamp", "IN-"), ("R_f", "2"), ("R_in", "2")]),
            NetTemplate("{prefix}_OUT",  pins=[("opamp", "OUT"), ("R_f", "1")]),
            NetTemplate("{prefix}_BIAS", pins=[("opamp", "IN+"), ("R_bias", "1")]),
        ],
        notes=[
            "Signal inverted at output — ensure ADC can handle phase-inverted signal",
            "R_bias connects IN+ to mid-supply reference for single-supply operation",
        ],
    ),

    # ------------------------------------------------------------------
    # 3. Voltage Follower / Buffer
    #    OUT = IN (unity gain, high-Z input, low-Z output)
    # ------------------------------------------------------------------
    CircuitTemplate(
        id="voltage_follower",
        name="Voltage Follower (Buffer)",
        description=(
            "Op-amp unity-gain buffer.  High input impedance, low output "
            "impedance.  Isolates signal source from load.  No passives needed."
        ),
        circuit_type="analog",
        keywords=[
            "voltage follower", "spannungsfolger", "follower", "buffer",
            "unity gain", "impedanz wandler", "impedance converter",
            "puffer", "entkopplung", "isolation buffer",
        ],
        required_component_roles=["opamp"],
        parameters={},  # No parameters — unity gain, no feedback network
        passive_recipes=[],
        net_templates=[
            NetTemplate("{prefix}_IN",  pins=[("opamp", "IN+")]),
            NetTemplate("{prefix}_OUT", pins=[("opamp", "OUT"), ("opamp", "IN-")]),
        ],
        notes=[
            "IN− is connected directly to OUT (100% feedback → unity gain)",
            "V+ → +3V3, V− → GND (single-supply)",
        ],
    ),

    # ------------------------------------------------------------------
    # 4. 1st-Order Passive RC Low-Pass Filter
    #    f_c = 1 / (2π × R × C)
    # ------------------------------------------------------------------
    CircuitTemplate(
        id="rc_lowpass",
        name="RC Low-Pass Filter (1st order)",
        description=(
            "Passive first-order RC low-pass filter.  Attenuates signals "
            "above the cut-off frequency f_c = 1/(2π·R·C).  Typically placed "
            "before an ADC input."
        ),
        circuit_type="analog",
        keywords=[
            "low-pass filter", "lowpass filter", "tiefpass", "tiefpassfilter",
            "low pass", "lp filter", "rc filter", "anti-aliasing",
            "antialiasing", "adc filter", "rauschunterdrückung",
        ],
        required_component_roles=[],  # Passive-only — no active device needed
        parameters={
            "cutoff_hz": {"type": "float", "default": 1000.0, "min": 1.0,
                          "description": "Cut-off frequency in Hz (-3 dB)"},
            "R": {"type": "float", "default": 10000.0,
                  "description": "Filter resistor in ohms (sets impedance)"},
        },
        passive_recipes=[
            PassiveRecipe(
                comp_id_key="R_lp",
                category="resistor",
                value_expr="R",
                unit="Ω",
                nets_template=["{prefix}_IN", "{prefix}_MID"],
                package="0402",
            ),
            PassiveRecipe(
                comp_id_key="C_lp",
                category="capacitor",
                # C = 1 / (2π × f_c × R)
                value_expr="1 / (2 * 3.14159265 * cutoff_hz * R)",
                unit="F",
                nets_template=["{prefix}_MID", "GND"],
                package="0402",
                mpn_hint="X7R dielectric recommended",
            ),
        ],
        net_templates=[
            NetTemplate("{prefix}_IN",  pins=[("R_lp", "1")]),
            NetTemplate("{prefix}_MID", pins=[("R_lp", "2"), ("C_lp", "1")]),
            NetTemplate("{prefix}_OUT", pins=[("C_lp", "1")]),  # same as MID
        ],
        notes=[
            "Connect {prefix}_IN to signal source, {prefix}_OUT/MID to ADC input",
            "Increase R to reduce power consumption; decrease R for lower source impedance",
        ],
    ),

    # ------------------------------------------------------------------
    # 5. 1st-Order Passive RC High-Pass Filter
    #    f_c = 1 / (2π × R × C)
    # ------------------------------------------------------------------
    CircuitTemplate(
        id="rc_highpass",
        name="RC High-Pass Filter (1st order)",
        description=(
            "Passive first-order RC high-pass filter.  Attenuates signals "
            "below the cut-off frequency and blocks DC.  "
            "f_c = 1/(2π·R·C)."
        ),
        circuit_type="analog",
        keywords=[
            "high-pass filter", "highpass filter", "hochpass", "hochpassfilter",
            "high pass", "hp filter", "dc blocking", "ac coupling",
            "gleichspannung sperren",
        ],
        required_component_roles=[],
        parameters={
            "cutoff_hz": {"type": "float", "default": 100.0, "min": 0.01,
                          "description": "Cut-off frequency in Hz (-3 dB)"},
            "R": {"type": "float", "default": 10000.0,
                  "description": "Filter resistor in ohms"},
        },
        passive_recipes=[
            PassiveRecipe(
                comp_id_key="C_hp",
                category="capacitor",
                value_expr="1 / (2 * 3.14159265 * cutoff_hz * R)",
                unit="F",
                nets_template=["{prefix}_IN", "{prefix}_MID"],
                package="0402",
                mpn_hint="X7R or C0G dielectric",
            ),
            PassiveRecipe(
                comp_id_key="R_hp",
                category="resistor",
                value_expr="R",
                unit="Ω",
                nets_template=["{prefix}_MID", "GND"],
                package="0402",
            ),
        ],
        net_templates=[
            NetTemplate("{prefix}_IN",  pins=[("C_hp", "1")]),
            NetTemplate("{prefix}_MID", pins=[("C_hp", "2"), ("R_hp", "1")]),
            NetTemplate("{prefix}_OUT", pins=[("R_hp", "1")]),  # same as MID
        ],
        notes=[
            "Blocks DC component; passes AC above f_c",
            "Typically used for AC-coupled audio or vibration signals",
        ],
    ),

    # ------------------------------------------------------------------
    # 6. Comparator with Fixed Threshold (voltage divider reference)
    #    Threshold = VCC × R2 / (R1 + R2)
    #    Open-collector output → pull-up to VCC required
    # ------------------------------------------------------------------
    CircuitTemplate(
        id="comparator_fixed",
        name="Comparator with Fixed Threshold",
        description=(
            "Comparator with a fixed voltage divider reference.  "
            "Output goes LOW (open-collector) when IN+ > Vthreshold.  "
            "Pull-up resistor required on output.  "
            "Vthreshold = VCC × R2/(R1+R2)."
        ),
        circuit_type="analog",
        keywords=[
            "comparator", "komparator", "comparator circuit",
            "threshold", "schwellwert", "schwellwertschalter",
            "limit detector", "grenzwertdetektor", "level detector",
            "spannungsvergleich", "zero crossing", "nulldurchgang",
        ],
        required_component_roles=["comparator"],
        parameters={
            "threshold_v": {"type": "float", "default": 1.65,
                            "description": "Threshold voltage in V"},
            "vcc_v": {"type": "float", "default": 3.3,
                      "description": "Supply voltage for divider calculation"},
            "R1": {"type": "float", "default": 10000.0,
                   "description": "Upper divider resistor in ohms"},
        },
        passive_recipes=[
            # R1: VCC → divider mid
            PassiveRecipe(
                comp_id_key="R_div1",
                category="resistor",
                value_expr="R1",
                unit="Ω",
                nets_template=["{prefix}_VCC_REF", "{prefix}_REF"],
                package="0402",
            ),
            # R2 = R1 × Vth / (VCC − Vth)
            PassiveRecipe(
                comp_id_key="R_div2",
                category="resistor",
                value_expr="R1 * threshold_v / (vcc_v - threshold_v)",
                unit="Ω",
                nets_template=["{prefix}_REF", "GND"],
                package="0402",
            ),
            # Pull-up on open-collector output
            PassiveRecipe(
                comp_id_key="R_pull",
                category="resistor",
                value_expr="10000.0",
                unit="Ω",
                nets_template=["{prefix}_PULL_VCC", "{prefix}_OUT"],
                package="0402",
            ),
        ],
        net_templates=[
            NetTemplate("{prefix}_IN",       pins=[("comparator", "IN+")]),
            NetTemplate("{prefix}_REF",      pins=[("comparator", "IN-"), ("R_div1", "2"), ("R_div2", "1")]),
            NetTemplate("{prefix}_OUT",      pins=[("comparator", "OUT"), ("R_pull", "2")]),
            NetTemplate("{prefix}_VCC_REF",  pins=[("R_div1", "1")]),
            NetTemplate("{prefix}_PULL_VCC", pins=[("R_pull", "1")]),
        ],
        notes=[
            "Connect {prefix}_VCC_REF and {prefix}_PULL_VCC to +3V3",
            "Connect {prefix}_IN to the signal to compare",
            "{prefix}_OUT is active-LOW (0V when IN+ > Vthreshold)",
        ],
    ),

    # ------------------------------------------------------------------
    # 7. Comparator with Hysteresis (Schmitt Trigger)
    #    Adds positive feedback resistor R_hyst for noise immunity
    # ------------------------------------------------------------------
    CircuitTemplate(
        id="comparator_hysteresis",
        name="Schmitt Trigger (Comparator + Hysteresis)",
        description=(
            "Comparator with positive feedback for hysteresis (Schmitt trigger "
            "behaviour).  Eliminates output chatter near the threshold.  "
            "R_hyst added from output to IN+ for hysteresis band."
        ),
        circuit_type="analog",
        keywords=[
            "schmitt trigger", "schmitt", "hysteresis", "hysterese",
            "noise immunity", "entprellung", "debounce",
            "chatter", "flattern", "stable switching",
            "positive feedback", "positiver gegenkopplungswiderstand",
        ],
        required_component_roles=["comparator"],
        parameters={
            "threshold_v": {"type": "float", "default": 1.65,
                            "description": "Centre threshold voltage in V"},
            "vcc_v": {"type": "float", "default": 3.3,
                      "description": "Supply voltage"},
            "R1": {"type": "float", "default": 10000.0,
                   "description": "Upper divider resistor in ohms"},
            "hysteresis_pct": {"type": "float", "default": 10.0,
                               "description": "Hysteresis as % of VCC"},
        },
        passive_recipes=[
            PassiveRecipe(
                comp_id_key="R_div1",
                category="resistor",
                value_expr="R1",
                unit="Ω",
                nets_template=["{prefix}_VCC_REF", "{prefix}_REF"],
                package="0402",
            ),
            PassiveRecipe(
                comp_id_key="R_div2",
                category="resistor",
                value_expr="R1 * threshold_v / (vcc_v - threshold_v)",
                unit="Ω",
                nets_template=["{prefix}_REF", "GND"],
                package="0402",
            ),
            # Hysteresis: R_hyst = VCC / (hysteresis_pct/100 × VCC / R_divider_parallel)
            # Simplified: R_hyst ≈ R1 * 100 / hysteresis_pct
            PassiveRecipe(
                comp_id_key="R_hyst",
                category="resistor",
                value_expr="R1 * 100.0 / hysteresis_pct",
                unit="Ω",
                nets_template=["{prefix}_OUT", "{prefix}_REF"],
                package="0402",
            ),
            PassiveRecipe(
                comp_id_key="R_pull",
                category="resistor",
                value_expr="10000.0",
                unit="Ω",
                nets_template=["{prefix}_PULL_VCC", "{prefix}_OUT"],
                package="0402",
            ),
        ],
        net_templates=[
            NetTemplate("{prefix}_IN",       pins=[("comparator", "IN+")]),
            NetTemplate("{prefix}_REF",      pins=[("comparator", "IN-"), ("R_div1", "2"),
                                                   ("R_div2", "1"), ("R_hyst", "2")]),
            NetTemplate("{prefix}_OUT",      pins=[("comparator", "OUT"), ("R_pull", "2"),
                                                   ("R_hyst", "1")]),
            NetTemplate("{prefix}_VCC_REF",  pins=[("R_div1", "1")]),
            NetTemplate("{prefix}_PULL_VCC", pins=[("R_pull", "1")]),
        ],
        notes=[
            "Positive feedback from OUT → REF node creates hysteresis band",
            "Increase R_hyst for narrower hysteresis, decrease for wider",
        ],
    ),

    # ------------------------------------------------------------------
    # 8. Voltage Divider (resistive attenuator)
    #    Vout = Vin × R2 / (R1 + R2)
    # ------------------------------------------------------------------
    CircuitTemplate(
        id="voltage_divider",
        name="Voltage Divider",
        description=(
            "Resistive voltage divider.  Scales down Vin to Vout.  "
            "Vout = Vin × R2 / (R1 + R2).  "
            "No active components needed."
        ),
        circuit_type="analog",
        keywords=[
            "voltage divider", "spannungsteiler", "divider", "attenuator",
            "abschwächer", "teiler", "scale down", "herunterteilen",
            "resistive divider", "widerstandsteiler",
        ],
        required_component_roles=[],
        parameters={
            "ratio": {"type": "float", "default": 0.5, "min": 0.001, "max": 0.999,
                      "description": "Output/Input voltage ratio (0 < ratio < 1)"},
            "R_total": {"type": "float", "default": 20000.0,
                        "description": "Total series resistance in ohms (R1+R2)"},
        },
        passive_recipes=[
            # R1 = R_total × (1 - ratio)
            PassiveRecipe(
                comp_id_key="R1",
                category="resistor",
                value_expr="R_total * (1 - ratio)",
                unit="Ω",
                nets_template=["{prefix}_IN", "{prefix}_OUT"],
                package="0402",
            ),
            # R2 = R_total × ratio
            PassiveRecipe(
                comp_id_key="R2",
                category="resistor",
                value_expr="R_total * ratio",
                unit="Ω",
                nets_template=["{prefix}_OUT", "GND"],
                package="0402",
            ),
        ],
        net_templates=[
            NetTemplate("{prefix}_IN",  pins=[("R1", "1")]),
            NetTemplate("{prefix}_OUT", pins=[("R1", "2"), ("R2", "1")]),
        ],
        notes=[
            "Vout = Vin × ratio",
            "Load impedance should be ≥10× R_total to avoid ratio error",
        ],
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class CircuitTemplateLibrary:
    """Library of analog/mixed-signal circuit templates."""

    def __init__(self, templates: list[CircuitTemplate] | None = None) -> None:
        self._templates = templates if templates is not None else list(_TEMPLATES)
        self._by_id: dict[str, CircuitTemplate] = {t.id: t for t in self._templates}

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, template_id: str) -> CircuitTemplate | None:
        """Return a template by exact ID, or None."""
        return self._by_id.get(template_id)

    def find_by_keyword(self, text: str) -> list[CircuitTemplate]:
        """Return templates whose keywords appear in ``text`` (case-insensitive).

        Results are ordered by number of keyword matches (most specific first).
        """
        low = text.lower()
        scored: list[tuple[int, CircuitTemplate]] = []
        for t in self._templates:
            hits = sum(1 for kw in t.keywords if kw in low)
            if hits:
                scored.append((hits, t))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored]

    def find_by_circuit_type(self, circuit_type: str) -> list[CircuitTemplate]:
        """Return all templates of a given circuit_type (e.g. 'analog')."""
        return [t for t in self._templates if t.circuit_type == circuit_type]

    def all_templates(self) -> list[CircuitTemplate]:
        """Return all registered templates."""
        return list(self._templates)
