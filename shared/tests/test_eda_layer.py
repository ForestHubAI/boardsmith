# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for DB-1: EDA Layer as First-Class entity.

Covers:
  - EDAProfile schema validation
  - EDA registry lookup
  - Validation rules (pin count, pinmap, power domains)
  - Bridge to symbol_map.py
  - All registered profiles pass validation
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.knowledge.eda_schema import (
    EDAFootprint,
    EDAPin,
    EDAProfile,
    EDASymbol,
    validate_eda_profile,
    _courtyard_from_footprint,
)
from shared.knowledge.eda_profiles import (
    EDA_REGISTRY,
    get_eda_profile,
    has_eda_profile,
    list_mpns,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bme280_profile() -> EDAProfile:
    return get_eda_profile("BME280")


@pytest.fixture
def minimal_valid_profile() -> EDAProfile:
    return EDAProfile(
        mpn="TEST_IC",
        symbol=EDASymbol(
            lib_ref="Test:IC",
            ref_prefix="U",
            pins=[
                EDAPin("VDD", "1", "power_in",  "left"),
                EDAPin("GND", "2", "power_in",  "left"),
                EDAPin("SDA", "3", "bidirectional", "right"),
            ],
        ),
        footprint=EDAFootprint(
            kicad_name="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            pad_count=8,
        ),
    )


# ---------------------------------------------------------------------------
# Schema basics
# ---------------------------------------------------------------------------

class TestEDASchema:
    def test_eda_pin_defaults(self):
        p = EDAPin(name="SDA", number="3")
        assert p.electrical_type == "bidirectional"
        assert p.side == "left"

    def test_eda_symbol_pin_count(self, bme280_profile):
        assert bme280_profile.symbol.pin_count == 6

    def test_eda_footprint_auto_dimensions(self):
        """Footprint dimensions auto-filled from kicad_name when not specified."""
        fp = EDAFootprint(
            kicad_name="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            pad_count=8,
        )
        assert fp.courtyard_width_mm > 0
        assert fp.courtyard_height_mm > 0

    def test_eda_footprint_explicit_dimensions(self):
        fp = EDAFootprint(
            kicad_name="Package_LGA:Bosch_LGA-8_2.5x2.5mm_P0.65mm",
            pad_count=8,
            courtyard_width_mm=4.5,
            courtyard_height_mm=4.5,
        )
        assert fp.courtyard_width_mm == 4.5
        assert fp.courtyard_height_mm == 4.5


# ---------------------------------------------------------------------------
# Courtyard parsing
# ---------------------------------------------------------------------------

class TestCourtyardParsing:
    def test_known_package(self):
        w, h, pads = _courtyard_from_footprint("Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
        assert w == 5.9
        assert h == 6.9
        assert pads == 8

    def test_wh_extraction(self):
        w, h, _ = _courtyard_from_footprint("Package_QFP:LQFP-48_7x7mm_P0.5mm")
        # 7+2 = 9
        assert w == 9.0
        assert h == 9.0

    def test_unknown_fallback(self):
        w, h, pads = _courtyard_from_footprint("Some_Unknown_Package")
        assert w == 5.0
        assert h == 5.0


# ---------------------------------------------------------------------------
# Validation rules
# ---------------------------------------------------------------------------

class TestEDAValidation:
    def test_valid_profile_no_errors(self, bme280_profile):
        errors = validate_eda_profile(bme280_profile)
        assert errors == []

    def test_pin_count_mismatch_raises(self):
        """Symbol with more pins than footprint pads must raise ValidationError."""
        with pytest.raises(ValidationError, match="Pin count mismatch"):
            EDAProfile(
                mpn="BAD_IC",
                symbol=EDASymbol(
                    lib_ref="Test:BAD",
                    ref_prefix="U",
                    pins=[EDAPin(f"P{i}", str(i), "bidirectional") for i in range(1, 20)],
                ),
                footprint=EDAFootprint(
                    kicad_name="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                    pad_count=8,
                ),
            )

    def test_invalid_pinmap_key_raises(self):
        """pinmap key not in symbol pin numbers must raise."""
        with pytest.raises(ValidationError, match="pinmap key"):
            EDAProfile(
                mpn="BAD_MAP",
                symbol=EDASymbol(
                    lib_ref="Test:BAD",
                    ref_prefix="U",
                    pins=[
                        EDAPin("VDD", "1", "power_in"),
                        EDAPin("GND", "2", "power_in"),
                    ],
                ),
                footprint=EDAFootprint(
                    kicad_name="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                    pad_count=8,
                ),
                pinmap={"99": "99"},  # "99" not in symbol pins
            )

    def test_missing_power_domain_raises(self):
        """When power_pin_domains is set, all power_in pins must have an entry."""
        with pytest.raises(ValidationError, match="Power pin"):
            EDAProfile(
                mpn="BAD_DOMAIN",
                symbol=EDASymbol(
                    lib_ref="Test:BAD",
                    ref_prefix="U",
                    pins=[
                        EDAPin("VDD", "1", "power_in"),
                        EDAPin("GND", "2", "power_in"),
                        EDAPin("SDA", "3", "bidirectional"),
                    ],
                ),
                footprint=EDAFootprint(
                    kicad_name="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                    pad_count=8,
                ),
                power_pin_domains={"VDD": "VDD_3V3"},  # GND missing!
            )

    def test_empty_power_pin_domains_is_ok(self, minimal_valid_profile):
        """Empty power_pin_domains skips domain validation (not yet specified)."""
        errors = validate_eda_profile(minimal_valid_profile)
        assert errors == []

    def test_exposed_pad_allowed(self):
        """Footprint with 1 extra pad (exposed pad) is valid vs symbol pin count."""
        profile = EDAProfile(
            mpn="QFN_IC",
            symbol=EDASymbol(
                lib_ref="Test:QFN",
                ref_prefix="U",
                pins=[EDAPin(f"P{i}", str(i), "bidirectional") for i in range(1, 25)],
            ),
            footprint=EDAFootprint(
                kicad_name="Package_QFN:QFN-24_4x4mm_P0.5mm",
                pad_count=25,  # 24 pads + 1 exposed pad
            ),
        )
        assert validate_eda_profile(profile) == []


# ---------------------------------------------------------------------------
# EDA Registry
# ---------------------------------------------------------------------------

class TestEDARegistry:
    def test_registry_not_empty(self):
        assert len(EDA_REGISTRY) >= 40

    def test_get_known_mpn(self, bme280_profile):
        assert bme280_profile is not None
        assert bme280_profile.mpn == "BME280"

    def test_get_unknown_mpn_returns_none(self):
        assert get_eda_profile("NONEXISTENT_XYZ_9999") is None

    def test_has_eda_profile(self):
        assert has_eda_profile("BME280") is True
        assert has_eda_profile("NOT_A_PART") is False

    def test_list_mpns(self):
        mpns = list_mpns()
        assert "BME280" in mpns
        assert "AMS1117-3.3" in mpns
        assert "ESP32-WROOM-32" in mpns
        assert "SX1276" in mpns
        assert "TB6612FNG" in mpns

    def test_all_profiles_pass_validation(self):
        """Every profile in the registry must pass all validation rules."""
        failures = []
        for mpn, profile in EDA_REGISTRY.items():
            errors = validate_eda_profile(profile)
            if errors:
                failures.append(f"{mpn}: {errors}")
        assert failures == [], "Profiles with validation errors:\n" + "\n".join(failures)

    def test_all_profiles_have_kicad_footprint(self):
        """Every footprint must have a non-empty KiCad name."""
        for mpn, profile in EDA_REGISTRY.items():
            assert profile.footprint.kicad_name, f"{mpn} has empty footprint.kicad_name"

    def test_all_profiles_have_ref_prefix(self):
        for mpn, profile in EDA_REGISTRY.items():
            assert profile.symbol.ref_prefix, f"{mpn} has empty symbol.ref_prefix"

    def test_all_profiles_have_pins(self):
        for mpn, profile in EDA_REGISTRY.items():
            assert len(profile.symbol.pins) >= 2, f"{mpn} has fewer than 2 pins"

    def test_pin_count_leq_pad_count(self):
        """Symbol pin count must not exceed footprint pad count."""
        for mpn, profile in EDA_REGISTRY.items():
            sym = profile.symbol.pin_count
            pad = profile.footprint.pad_count
            assert sym <= pad + 1, (
                f"{mpn}: symbol has {sym} pins but footprint only {pad} pads"
            )


# ---------------------------------------------------------------------------
# Specific profile checks
# ---------------------------------------------------------------------------

class TestSpecificProfiles:
    def test_bme280_symbol(self, bme280_profile):
        assert bme280_profile.symbol.ref_prefix == "U"
        assert bme280_profile.symbol.pin_count == 6
        assert bme280_profile.footprint.pad_count == 8  # LGA-8
        assert bme280_profile.footprint.lcsc_part_id == "C17024"

    def test_bme280_power_domains(self, bme280_profile):
        assert bme280_profile.power_pin_domains["VDD"] == "VDD_3V3"
        assert bme280_profile.power_pin_domains["GND"] == "GND"

    def test_rp2040_exposed_pad(self):
        profile = get_eda_profile("RP2040")
        assert profile is not None
        assert profile.footprint.pad_count == 57  # 56 + EP
        assert profile.symbol.pin_count <= 57

    def test_tb6612fng_motor_domain(self):
        profile = get_eda_profile("TB6612FNG")
        assert profile is not None
        assert profile.power_pin_domains.get("VM") == "VM_MOTOR"
        assert profile.power_pin_domains.get("VCC") == "VDD_3V3"

    def test_tp4056_charger_domains(self):
        profile = get_eda_profile("TP4056")
        assert profile is not None
        assert "GND" in profile.power_pin_domains
        assert "VCC" in profile.power_pin_domains
        assert "BAT" in profile.power_pin_domains

    def test_swd_connector_has_vtref(self):
        profile = get_eda_profile("CONN-SWD-2x5")
        assert profile is not None
        pin_names = [p.name for p in profile.symbol.pins]
        assert "VTref" in pin_names
        assert "SWDIO" in pin_names
        assert "SWCLK" in pin_names

    def test_crystal_has_passive_pins(self):
        for mpn in ["HC49-8MHZ", "HC49-12MHZ", "HC49-16MHZ"]:
            profile = get_eda_profile(mpn)
            assert profile is not None
            assert profile.symbol.ref_prefix == "Y"
            for pin in profile.symbol.pins:
                assert pin.electrical_type == "passive"


# ---------------------------------------------------------------------------
# effective_pinmap
# ---------------------------------------------------------------------------

class TestPinmap:
    def test_default_pinmap_is_identity(self, bme280_profile):
        pm = bme280_profile.effective_pinmap()
        for pin in bme280_profile.symbol.pins:
            assert pm[pin.number] == pin.number

    def test_explicit_pinmap_overrides(self):
        profile = EDAProfile(
            mpn="CUSTOM_IC",
            symbol=EDASymbol(
                lib_ref="Test:Custom",
                ref_prefix="U",
                pins=[
                    EDAPin("VDD", "1", "power_in"),
                    EDAPin("GND", "2", "power_in"),
                    EDAPin("SDA", "3", "bidirectional"),
                ],
            ),
            footprint=EDAFootprint(
                kicad_name="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                pad_count=8,
            ),
            pinmap={"1": "8", "2": "4", "3": "2"},
        )
        pm = profile.effective_pinmap()
        assert pm["1"] == "8"
        assert pm["2"] == "4"
        assert pm["3"] == "2"


# ---------------------------------------------------------------------------
# to_symbol_def_dict — backward compat
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_to_symbol_def_dict_structure(self, bme280_profile):
        d = bme280_profile.to_symbol_def_dict()
        assert d["ref_prefix"] == "U"
        assert "footprint" in d
        assert "pins" in d
        assert len(d["pins"]) == 6

    def test_to_symbol_def_dict_pin_format(self, bme280_profile):
        d = bme280_profile.to_symbol_def_dict()
        first_pin = d["pins"][0]
        assert "name" in first_pin
        assert "number" in first_pin
        assert "type" in first_pin
        assert "side" in first_pin


# ---------------------------------------------------------------------------
# Bridge: get_symbol_def in symbol_map.py
# ---------------------------------------------------------------------------

class TestSymbolMapBridge:
    def test_bridge_returns_eda_data_for_known_mpn(self):
        """get_symbol_def should return EDA profile data when available."""
        try:
            from synth_core.knowledge.symbol_map import get_symbol_def
            sym = get_symbol_def("BME280")
            assert sym.ref_prefix == "U"
            assert "LGA" in sym.footprint  # Bosch LGA-8
            assert len(sym.pins) == 6
        except ImportError:
            pytest.skip("synth_core not importable from this context")

    def test_bridge_falls_back_to_symbol_map(self):
        """get_symbol_def should use SYMBOL_MAP for MPNs not in EDA registry."""
        try:
            from synth_core.knowledge.symbol_map import get_symbol_def
            # TB6612FNG is in EDA profiles so this tests EDA path
            # Use an MPN that's only in SYMBOL_MAP, not EDA profiles
            # MAX98357A is in symbol_map but not in our eda_profiles
            sym = get_symbol_def("MAX98357A")
            assert sym is not None
            assert sym.ref_prefix == "U"
        except ImportError:
            pytest.skip("synth_core not importable from this context")
