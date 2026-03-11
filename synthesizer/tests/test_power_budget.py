# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for boardsmith_hw.power_budget (Phase 17 power design module)."""
from __future__ import annotations

import pytest

from boardsmith_hw.power_budget import (
    DEFAULT_SAFETY_MARGIN,
    ComponentLoad,
    PowerBudget,
    RailBudget,
    calculate_power_budget,
    _estimate_current,
    _pick_regulated_rail,
)


# ---------------------------------------------------------------------------
# Fixtures — minimal HIR dicts
# ---------------------------------------------------------------------------

def _make_hir(
    components: list[dict],
    power_sequence: dict | None = None,
) -> dict:
    return {
        "version": "1.1.0",
        "components": components,
        "power_sequence": power_sequence or {},
        "bus_contracts": [],
        "nets": [],
    }


ESP32_COMP = {
    "id": "ESP32_WROOM_32",
    "mpn": "ESP32-WROOM-32",
    "role": "mcu",
    "electrical_ratings": {"current_draw_max_ma": 240.0},
}

BME280_COMP = {
    "id": "BME280",
    "mpn": "BME280",
    "role": "sensor",
    "electrical_ratings": {"current_draw_max_ma": 3.6},
}

SSD1306_COMP = {
    "id": "SSD1306",
    "mpn": "SSD1306",
    "role": "display",
    # no electrical_ratings → fallback
}

LDO_COMP = {
    "id": "AMS1117_3V3",
    "mpn": "AMS1117-3.3",
    "role": "power",
    "output_rail": "3V3",
    "capabilities": {"output_current_max_ma": 800.0},
}

POWER_SEQUENCE_WITH_RAIL = {
    "rails": [
        {"name": "3V3", "voltage": {"nominal": 3.3}},
    ]
}


# ---------------------------------------------------------------------------
# Unit tests — RailBudget properties
# ---------------------------------------------------------------------------

class TestRailBudgetProperties:
    def _make_rail(self, total_ma: float, max_ma: float | None, margin: float = 0.20) -> RailBudget:
        return RailBudget(
            rail_name="3V3",
            supply_voltage=3.3,
            total_load_ma=total_ma,
            regulator_mpn="AMS1117-3.3" if max_ma else None,
            regulator_max_ma=max_ma,
            safety_margin=margin,
            loads=[],
        )

    def test_passes_when_no_regulator(self):
        """No regulator → always passes (no constraint)."""
        rail = self._make_rail(500.0, None)
        assert rail.passes is True

    def test_passes_when_load_fits_with_margin(self):
        """200 mA load × 1.20 = 240 mA ≤ 800 mA → passes."""
        rail = self._make_rail(200.0, 800.0)
        assert rail.passes is True

    def test_fails_when_load_exceeds_capacity(self):
        """700 mA × 1.20 = 840 mA > 800 mA → fails."""
        rail = self._make_rail(700.0, 800.0)
        assert rail.passes is False

    def test_margin_ma(self):
        rail = self._make_rail(100.0, 800.0)
        assert rail.margin_ma == pytest.approx(700.0)

    def test_margin_pct(self):
        rail = self._make_rail(400.0, 800.0)
        # margin = 400 mA → 50 %
        assert rail.margin_pct == pytest.approx(50.0)

    def test_margin_none_without_regulator(self):
        rail = self._make_rail(100.0, None)
        assert rail.margin_ma is None
        assert rail.margin_pct is None

    def test_utilisation_pct(self):
        rail = self._make_rail(200.0, 800.0)
        assert rail.utilisation_pct == pytest.approx(25.0)

    def test_utilisation_none_without_regulator(self):
        rail = self._make_rail(100.0, None)
        assert rail.utilisation_pct is None


# ---------------------------------------------------------------------------
# Unit tests — PowerBudget
# ---------------------------------------------------------------------------

class TestPowerBudget:
    def _make_budget(self, rails: list[RailBudget]) -> PowerBudget:
        return PowerBudget(rails=rails, safety_margin=DEFAULT_SAFETY_MARGIN)

    def test_passes_all_rails_ok(self):
        r1 = RailBudget("3V3", 3.3, 100.0, "AMS1117-3.3", 800.0, 0.20)
        r2 = RailBudget("5V", 5.0, 50.0, None, None, 0.20)
        b = self._make_budget([r1, r2])
        assert b.passes is True

    def test_fails_if_any_rail_over_current(self):
        r_ok = RailBudget("5V", 5.0, 50.0, None, None, 0.20)
        r_fail = RailBudget("3V3", 3.3, 700.0, "AMS1117-3.3", 800.0, 0.20)
        b = self._make_budget([r_ok, r_fail])
        assert b.passes is False

    def test_total_load_ma_sums_rails(self):
        r1 = RailBudget("3V3", 3.3, 200.0, "AMS1117-3.3", 800.0, 0.20)
        r2 = RailBudget("5V", 5.0, 100.0, None, None, 0.20)
        b = self._make_budget([r1, r2])
        assert b.total_load_ma == pytest.approx(300.0)

    def test_get_rail_found(self):
        r = RailBudget("3V3", 3.3, 100.0, "AMS1117-3.3", 800.0, 0.20)
        b = self._make_budget([r])
        found = b.get_rail("3V3")
        assert found is r

    def test_get_rail_not_found_returns_none(self):
        b = self._make_budget([])
        assert b.get_rail("VBAT") is None

    def test_summary_lines_non_empty(self):
        r = RailBudget("3V3", 3.3, 200.0, "AMS1117-3.3", 800.0, 0.20)
        b = self._make_budget([r])
        lines = b.summary_lines()
        assert lines
        assert "3V3" in lines[0]
        assert "OK" in lines[0]

    def test_summary_lines_shows_over_current(self):
        r = RailBudget("3V3", 3.3, 700.0, "AMS1117-3.3", 800.0, 0.20)
        b = self._make_budget([r])
        lines = b.summary_lines()
        assert "OVER-CURRENT" in lines[0]


# ---------------------------------------------------------------------------
# Unit tests — _estimate_current
# ---------------------------------------------------------------------------

class TestEstimateCurrent:
    def test_uses_explicit_electrical_ratings(self):
        comp = {"mpn": "ESP32", "role": "mcu",
                "electrical_ratings": {"current_draw_max_ma": 999.0}}
        ma, src = _estimate_current(comp)
        assert ma == pytest.approx(999.0)
        assert src == "datasheet"

    def test_uses_capabilities_fallback(self):
        comp = {"mpn": "CUSTOM_IC", "role": "sensor",
                "capabilities": {"current_draw_max_ma": 42.0}}
        ma, src = _estimate_current(comp)
        assert ma == pytest.approx(42.0)
        assert src == "datasheet"

    def test_mpn_keyword_esp32(self):
        comp = {"mpn": "ESP32-WROOM-32", "role": "mcu"}
        ma, src = _estimate_current(comp)
        assert ma == pytest.approx(240.0)
        assert src == "fallback_mpn"

    def test_mpn_keyword_bme280(self):
        comp = {"mpn": "BME280", "role": "sensor"}
        ma, src = _estimate_current(comp)
        assert ma == pytest.approx(3.6)
        assert src == "fallback_mpn"

    def test_role_fallback_mcu(self):
        comp = {"mpn": "UNKNOWN_MCU_XYZ", "role": "mcu"}
        ma, src = _estimate_current(comp)
        assert ma == pytest.approx(100.0)
        assert src == "fallback_role"

    def test_role_fallback_sensor(self):
        comp = {"mpn": "UNKNOWN_SENSOR_XYZ", "role": "sensor"}
        ma, src = _estimate_current(comp)
        assert ma == pytest.approx(5.0)
        assert src == "fallback_role"

    def test_role_fallback_other(self):
        comp = {"mpn": "SOME_PART", "role": "other"}
        ma, src = _estimate_current(comp)
        assert ma == pytest.approx(10.0)
        assert src == "fallback_role"


# ---------------------------------------------------------------------------
# Unit tests — _pick_regulated_rail
# ---------------------------------------------------------------------------

class TestPickRegulatedRail:
    def test_picks_3v3_class_rail(self):
        rails = {"3V3": 3.3, "VIN_5V": 5.0}
        assert _pick_regulated_rail(rails) == "3V3"

    def test_picks_rail_at_3v0_boundary(self):
        rails = {"VREG": 3.0}
        assert _pick_regulated_rail(rails) == "VREG"

    def test_picks_rail_at_3v6_boundary(self):
        rails = {"VOUT": 3.6}
        assert _pick_regulated_rail(rails) == "VOUT"

    def test_falls_back_to_first_rail_when_no_3v3(self):
        rails = {"5V": 5.0, "12V": 12.0}
        result = _pick_regulated_rail(rails)
        assert result in rails

    def test_fallback_3v3_on_empty(self):
        assert _pick_regulated_rail({}) == "3V3"


# ---------------------------------------------------------------------------
# Integration tests — calculate_power_budget
# ---------------------------------------------------------------------------

class TestCalculatePowerBudget:
    def test_basic_budget_passes(self):
        """ESP32 + BME280 on 3V3 (800 mA LDO) must pass."""
        hir = _make_hir([ESP32_COMP, BME280_COMP, LDO_COMP], POWER_SEQUENCE_WITH_RAIL)
        budget = calculate_power_budget(hir)
        rail = budget.get_rail("3V3")
        assert rail is not None
        assert rail.total_load_ma == pytest.approx(243.6)  # 240 + 3.6
        assert rail.regulator_max_ma == pytest.approx(800.0)
        assert budget.passes is True

    def test_excludes_passive_and_power_roles(self):
        """Components with role='passive' or 'power' must not contribute to load."""
        passive_comp = {"id": "R1", "mpn": "RC0402", "role": "passive",
                        "electrical_ratings": {"current_draw_max_ma": 999.0}}
        hir = _make_hir([ESP32_COMP, LDO_COMP, passive_comp], POWER_SEQUENCE_WITH_RAIL)
        budget = calculate_power_budget(hir)
        rail = budget.get_rail("3V3")
        assert rail is not None
        # Only ESP32 load (240 mA), not passive (999) or power (LDO)
        assert rail.total_load_ma == pytest.approx(240.0)

    def test_overcurrent_detected(self):
        """Design exceeding regulator capacity must fail."""
        low_ldo = {
            "id": "SMALL_LDO",
            "mpn": "MCP1700-3302E",
            "role": "power",
            "output_rail": "3V3",
            "capabilities": {"output_current_max_ma": 250.0},
        }
        # ESP32 alone needs 240 mA × 1.20 = 288 mA > 250 mA → fail
        hir = _make_hir([ESP32_COMP, low_ldo], POWER_SEQUENCE_WITH_RAIL)
        budget = calculate_power_budget(hir)
        assert budget.passes is False

    def test_fallback_display_mpn(self):
        """SSD1306 (no electrical_ratings) must use fallback_mpn (9 mA)."""
        hir = _make_hir([SSD1306_COMP, LDO_COMP], POWER_SEQUENCE_WITH_RAIL)
        budget = calculate_power_budget(hir)
        rail = budget.get_rail("3V3")
        assert rail is not None
        assert rail.total_load_ma == pytest.approx(9.0)  # ssd1306 fallback

    def test_rail_from_power_sequence(self):
        """Rails must be populated from hir power_sequence when present."""
        hir = _make_hir([ESP32_COMP, LDO_COMP], POWER_SEQUENCE_WITH_RAIL)
        budget = calculate_power_budget(hir)
        names = [r.rail_name for r in budget.rails]
        assert "3V3" in names

    def test_degenerate_no_rails(self):
        """When no rail info, a synthetic 3V3 rail must be created."""
        hir = _make_hir([ESP32_COMP])  # no LDO, no power_sequence
        budget = calculate_power_budget(hir)
        assert len(budget.rails) >= 1
        assert budget.rails[0].rail_name == "3V3"

    def test_custom_safety_margin(self):
        """Custom safety margin must override default."""
        hir = _make_hir([ESP32_COMP, LDO_COMP], POWER_SEQUENCE_WITH_RAIL)
        budget = calculate_power_budget(hir, safety_margin=0.0)
        rail = budget.get_rail("3V3")
        assert rail is not None
        assert rail.safety_margin == pytest.approx(0.0)
        # 240 mA × 1.0 = 240 mA ≤ 800 mA → passes
        assert budget.passes is True

    def test_topology_voltage_regulator_used(self):
        """Topology VoltageRegulator objects must populate regulator_max_ma."""
        from dataclasses import dataclass

        @dataclass
        class _FakeReg:
            output_rail: str
            mpn: str
            max_current_ma: float
            input_voltage_nom: float

        class _FakeTopology:
            voltage_regulators = [_FakeReg("3V3", "AMS1117-3.3", 800.0, 5.0)]
            power_rails = []

        hir = _make_hir([ESP32_COMP], POWER_SEQUENCE_WITH_RAIL)
        budget = calculate_power_budget(hir, topology=_FakeTopology())
        rail = budget.get_rail("3V3")
        assert rail is not None
        assert rail.regulator_mpn == "AMS1117-3.3"
        assert rail.regulator_max_ma == pytest.approx(800.0)
