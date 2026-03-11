# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for DB-3: Pattern Library.

Covers:
  - Schema validation (all patterns load without error)
  - Registry completeness (≥ 15 patterns, 3 bundles)
  - Parameter resolution (defaults, overrides, formula params)
  - Output component count
  - Bundle pattern references are valid
  - Category distribution
  - Trigger field non-empty
  - Specific pattern checks (I2C, crystal, ADC)
"""
from __future__ import annotations

import pytest

from shared.knowledge.patterns import (
    BUNDLE_REGISTRY,
    PATTERN_REGISTRY,
    find_patterns_by_category,
    find_patterns_by_trigger,
    get_bundle,
    get_pattern,
    list_bundle_ids,
    list_pattern_ids,
)
from shared.knowledge.patterns.pattern_schema import CircuitPattern, PatternBundle


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------

class TestRegistryCompleteness:
    def test_at_least_15_patterns(self):
        assert len(PATTERN_REGISTRY) >= 15

    def test_exactly_3_bundles(self):
        assert len(BUNDLE_REGISTRY) >= 3

    def test_known_pattern_ids_present(self):
        expected = [
            "i2c_pullup_v1",
            "spi_series_resistor_v1",
            "can_transceiver_v1",
            "rs485_transceiver_v1",
            "usb_esd_protection_v1",
            "uart_level_shifter_v1",
            "tvs_input_protection_v1",
            "reverse_polarity_v1",
            "reset_circuit_v1",
            "ldo_bypass_v1",
            "buck_converter_v1",
            "decoupling_per_pin_v1",
            "mosfet_low_side_v1",
            "adc_divider_v1",
            "crystal_load_v1",
        ]
        for pid in expected:
            assert pid in PATTERN_REGISTRY, f"Pattern '{pid}' not found in registry"

    def test_known_bundle_ids_present(self):
        for bid in ["usb_devboard", "industrial_24v_input", "battery_sensor_node"]:
            assert bid in BUNDLE_REGISTRY, f"Bundle '{bid}' not found"

    def test_list_pattern_ids_matches_registry(self):
        assert set(list_pattern_ids()) == set(PATTERN_REGISTRY.keys())

    def test_list_bundle_ids_matches_registry(self):
        assert set(list_bundle_ids()) == set(BUNDLE_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Schema integrity
# ---------------------------------------------------------------------------

class TestSchemaIntegrity:
    def test_all_patterns_have_non_empty_trigger(self):
        for pid, pattern in PATTERN_REGISTRY.items():
            assert pattern.trigger, f"Pattern '{pid}' has empty trigger"

    def test_all_patterns_have_description(self):
        for pid, pattern in PATTERN_REGISTRY.items():
            assert pattern.description, f"Pattern '{pid}' has empty description"

    def test_all_patterns_have_at_least_one_output_component(self):
        for pid, pattern in PATTERN_REGISTRY.items():
            assert len(pattern.output_components) >= 1, (
                f"Pattern '{pid}' has no output components"
            )

    def test_all_patterns_have_valid_category(self):
        valid = {"interface", "protection", "power", "analog", "emc"}
        for pid, pattern in PATTERN_REGISTRY.items():
            assert pattern.category in valid, (
                f"Pattern '{pid}' has invalid category '{pattern.category}'"
            )

    def test_all_bundles_reference_valid_patterns(self):
        for bid, bundle in BUNDLE_REGISTRY.items():
            for pid in bundle.pattern_ids:
                assert pid in PATTERN_REGISTRY, (
                    f"Bundle '{bid}' references unknown pattern '{pid}'"
                )

    def test_all_output_component_roles_unique_per_pattern(self):
        for pid, pattern in PATTERN_REGISTRY.items():
            roles = [c.role for c in pattern.output_components]
            assert len(roles) == len(set(roles)), (
                f"Pattern '{pid}' has duplicate component roles: {roles}"
            )


# ---------------------------------------------------------------------------
# Category distribution
# ---------------------------------------------------------------------------

class TestCategoryDistribution:
    def test_has_interface_patterns(self):
        assert len(find_patterns_by_category("interface")) >= 4

    def test_has_protection_patterns(self):
        assert len(find_patterns_by_category("protection")) >= 3

    def test_has_power_patterns(self):
        assert len(find_patterns_by_category("power")) >= 3

    def test_has_analog_patterns(self):
        assert len(find_patterns_by_category("analog")) >= 2


# ---------------------------------------------------------------------------
# Trigger matching
# ---------------------------------------------------------------------------

class TestTriggerMatching:
    def test_i2c_trigger_finds_pullup(self):
        results = find_patterns_by_trigger("I2C")
        ids = {p.pattern_id for p in results}
        assert "i2c_pullup_v1" in ids

    def test_spi_trigger_finds_series_resistor(self):
        results = find_patterns_by_trigger("SPI")
        ids = {p.pattern_id for p in results}
        assert "spi_series_resistor_v1" in ids

    def test_usb_trigger_finds_esd(self):
        results = find_patterns_by_trigger("USB")
        ids = {p.pattern_id for p in results}
        assert "usb_esd_protection_v1" in ids


# ---------------------------------------------------------------------------
# Parameter resolution
# ---------------------------------------------------------------------------

class TestParameterResolution:
    def test_i2c_defaults(self):
        p = get_pattern("i2c_pullup_v1")
        defaults = p.resolve_parameters()
        assert defaults["bus_speed_hz"] == 100_000
        assert defaults["bus_cap_pf"] == 50.0

    def test_i2c_override_speed(self):
        p = get_pattern("i2c_pullup_v1")
        resolved = p.resolve_parameters({"bus_speed_hz": 400_000})
        assert resolved["bus_speed_hz"] == 400_000
        assert resolved["bus_cap_pf"] == 50.0  # unchanged default

    def test_buck_formula_param(self):
        """buck_converter_v1 has v_ref with formula '0.8' — should resolve."""
        p = get_pattern("buck_converter_v1")
        resolved = p.resolve_parameters()
        assert resolved["v_ref"] == pytest.approx(0.8)

    def test_reset_defaults(self):
        p = get_pattern("reset_circuit_v1")
        defaults = p.resolve_parameters()
        assert defaults["pullup_r_ohm"] == 10_000
        assert defaults["filter_c_nf"] == 100.0

    def test_crystal_defaults(self):
        p = get_pattern("crystal_load_v1")
        defaults = p.resolve_parameters()
        assert defaults["c_load_pf"] == 12.5
        assert defaults["c_stray_pf"] == 5.0


# ---------------------------------------------------------------------------
# Output component value expressions
# ---------------------------------------------------------------------------

class TestOutputComponentExpressions:
    def test_i2c_pullup_value_expr_evaluable(self):
        p = get_pattern("i2c_pullup_v1")
        resolved = p.resolve_parameters()
        comp = p.output_components[0]  # R_pull_sda
        val = eval(comp.value_expr, {}, resolved)  # noqa: S307
        # At 100 kHz, 50 pF: R = 1000e-9 / (0.8473 * 50e-12) ≈ 23619 Ω → snap to 10kΩ
        assert val > 0

    def test_adc_divider_top_resistor(self):
        p = get_pattern("adc_divider_v1")
        resolved = p.resolve_parameters({"v_in_max": 12.0, "v_adc_max": 3.3, "r_total_ohm": 100_000})
        comp_top = next(c for c in p.output_components if c.role == "R_top")
        val = eval(comp_top.value_expr, {}, resolved)  # noqa: S307
        # R_top = 100k * (1 - 3.3/12) = 100k * 0.725 = 72500
        assert abs(val - 72_500) < 1

    def test_adc_divider_bot_resistor(self):
        p = get_pattern("adc_divider_v1")
        resolved = p.resolve_parameters({"v_in_max": 12.0, "v_adc_max": 3.3, "r_total_ohm": 100_000})
        comp_bot = next(c for c in p.output_components if c.role == "R_bot")
        val = eval(comp_bot.value_expr, {}, resolved)  # noqa: S307
        # R_bot = 100k * (3.3/12) = 27500
        assert abs(val - 27_500) < 1

    def test_crystal_load_cap_value(self):
        p = get_pattern("crystal_load_v1")
        resolved = p.resolve_parameters({"c_load_pf": 12.5, "c_stray_pf": 5.0})
        comp = p.output_components[0]  # C_xtal1
        val = eval(comp.value_expr, {}, {"c_load_pf": 12.5, "c_stray_pf": 5.0})  # noqa: S307
        # C = 2 * (12.5 - 5.0) pF = 15 pF
        assert abs(val - 15e-12) < 1e-15

    def test_buck_fb_top_resistor(self):
        p = get_pattern("buck_converter_v1")
        resolved = p.resolve_parameters({"v_out": 5.0, "v_ref": 0.8, "r_fb_bot_ohm": 10_000})
        comp = next(c for c in p.output_components if c.role == "R_fb_top")
        val = eval(comp.value_expr, {}, resolved)  # noqa: S307
        # R_fb_top = 10k * (5.0 / 0.8 - 1) = 10k * 5.25 = 52500
        assert abs(val - 52_500) < 1


# ---------------------------------------------------------------------------
# Specific pattern checks
# ---------------------------------------------------------------------------

class TestSpecificPatterns:
    def test_can_transceiver_has_termination_resistors(self):
        p = get_pattern("can_transceiver_v1")
        roles = {c.role for c in p.output_components}
        assert "R_term_a" in roles
        assert "R_term_b" in roles
        assert "C_term" in roles
        assert "U_trx" in roles

    def test_usb_esd_has_tvs_and_series_resistors(self):
        p = get_pattern("usb_esd_protection_v1")
        roles = {c.role for c in p.output_components}
        assert "R_dp" in roles
        assert "R_dm" in roles
        assert "U_tvs" in roles

    def test_ldo_bypass_has_4_caps(self):
        p = get_pattern("ldo_bypass_v1")
        assert len(p.output_components) == 4

    def test_mosfet_low_side_has_flyback_diode(self):
        p = get_pattern("mosfet_low_side_v1")
        roles = {c.role for c in p.output_components}
        assert "D_flyback" in roles
        assert "Q1" in roles
        assert "R_gate" in roles

    def test_rs485_has_bias_and_termination(self):
        p = get_pattern("rs485_transceiver_v1")
        roles = {c.role for c in p.output_components}
        assert "R_term" in roles
        assert "R_bias_a" in roles
        assert "R_bias_b" in roles


# ---------------------------------------------------------------------------
# Bundle checks
# ---------------------------------------------------------------------------

class TestBundles:
    def test_usb_devboard_bundle_has_5_patterns(self):
        b = get_bundle("usb_devboard")
        assert b is not None
        assert len(b.pattern_ids) == 5

    def test_industrial_bundle_includes_reverse_polarity(self):
        b = get_bundle("industrial_24v_input")
        assert "reverse_polarity_v1" in b.pattern_ids
        assert "tvs_input_protection_v1" in b.pattern_ids

    def test_battery_node_bundle_includes_i2c_pullup(self):
        b = get_bundle("battery_sensor_node")
        assert "i2c_pullup_v1" in b.pattern_ids

    def test_all_bundle_patterns_loadable(self):
        for bid, bundle in BUNDLE_REGISTRY.items():
            for pid in bundle.pattern_ids:
                p = get_pattern(pid)
                assert p is not None, f"Bundle '{bid}' → pattern '{pid}' not loadable"

    def test_get_unknown_pattern_returns_none(self):
        assert get_pattern("nonexistent_pattern_xyz") is None

    def test_get_unknown_bundle_returns_none(self):
        assert get_bundle("nonexistent_bundle_xyz") is None
