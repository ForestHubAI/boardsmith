# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression tests: ERC pin definition fixes (quick task 6).

Tests verify that the 4 symbol_map corrections and the kicad_exporter
+5V PWR_FLAG sentinel produce ERC-clean schematics for L04/L09/S03/S08/S10.
All tests run under BOARDSMITH_NO_LLM=1.
"""
from __future__ import annotations
import os
os.environ.setdefault("BOARDSMITH_NO_LLM", "1")

from synth_core.knowledge.symbol_map import SYMBOL_MAP


def _get_pin(mpn: str, pin_name: str):
    sym = SYMBOL_MAP.get(mpn)
    if sym is None:
        return None
    for p in sym.pins:
        if p.name == pin_name:
            return p
    return None


def test_lan8720a_nrst_uppercase():
    """LAN8720A pin 15 must be NRST (uppercase N) so it connects to CONN-SWD-2x5 NRST."""
    pin = _get_pin("LAN8720A", "NRST")
    assert pin is not None, "LAN8720A must have pin named 'NRST' (not 'nRST')"
    assert pin.number == "15"
    assert pin.type == "input"


def test_lan8720a_no_nrst_lowercase():
    """Confirm old 'nRST' name is gone."""
    pin = _get_pin("LAN8720A", "nRST")
    assert pin is None, "LAN8720A must not have pin 'nRST' — use 'NRST' instead"


def test_spv1040_vout_passive():
    """SPV1040 VOUT must be passive (not power_out) to avoid pin_to_pin conflict with LDO."""
    pin = _get_pin("SPV1040", "VOUT")
    assert pin is not None, "SPV1040 must have VOUT pin"
    assert pin.type == "passive", (
        f"SPV1040 VOUT must be 'passive' (was 'power_out'), got: {pin.type}"
    )


def test_atmega2560_has_io5():
    """ATmega2560-16AU must have IO5/PD5 pin so HIR CS assignments can connect."""
    sym = SYMBOL_MAP.get("ATmega2560-16AU")
    assert sym is not None
    pin_names = {p.name for p in sym.pins}
    # Accept either "IO5/PD5" or "IO5" or similar
    has_io5 = any("IO5" in name for name in pin_names)
    assert has_io5, (
        f"ATmega2560-16AU must have an IO5 pin. Got: {sorted(pin_names)}"
    )


def test_lpc55s69_has_pio1_1():
    """LPC55S69JBD100 must have PIO1_1 pin so HIR CS assignments can connect."""
    sym = SYMBOL_MAP.get("LPC55S69JBD100")
    assert sym is not None
    pin_names = {p.name for p in sym.pins}
    assert "PIO1_1" in pin_names, (
        f"LPC55S69JBD100 must have PIO1_1 pin. Got: {sorted(pin_names)}"
    )


# ---------------------------------------------------------------------------
# kicad_exporter: +5V PWR_FLAG sentinel
# ---------------------------------------------------------------------------

def _make_5v_hir():
    """Minimal HIR: ATmega328P MCU + decoupling caps on 5V net (no LDO -> +5V not driven)."""
    return {
        "components": [
            {"id": "MCU1", "mpn": "ATmega328P-AU", "role": "mcu",
             "name": "ATmega328P", "manufacturer": "Microchip",
             "interface_types": [], "pins": []},
            {"id": "C1", "mpn": "GRM155R71C104KA88D", "role": "passive",
             "name": "100nF cap", "manufacturer": "Murata",
             "interface_types": [], "pins": []},
        ],
        "nets": [
            {"name": "5V", "pins": [{"component_id": "C1", "pin_name": "1"}],
             "is_bus": False, "is_power": False},
            {"name": "GND", "pins": [{"component_id": "C1", "pin_name": "2"}],
             "is_bus": False, "is_power": True},
        ],
    }


def test_pwr_flag_5v_sentinel_placed(tmp_path):
    """HIR with 5V net (no power_in pins mapping to +5V) must get +5V PWR_FLAG."""
    from boardsmith_hw.kicad_exporter import export_kicad_sch

    sch = tmp_path / "test.kicad_sch"
    export_kicad_sch(_make_5v_hir(), sch, use_llm=False, add_pwr_flag=True)
    content = sch.read_text()

    # A PWR_FLAG with Value "+5V" must exist
    assert '+5V' in content, "No +5V symbol found in schematic"
    assert 'PWR_FLAG' in content, "No PWR_FLAG found in schematic"
    # Count flags — should have one for +5V (in addition to +3V3 and GND from MCU)
    flag_values = []
    import re
    for m in re.finditer(r'lib_id ".*?PWR_FLAG".*?Value" "([^"]+)"', content, re.DOTALL):
        flag_values.append(m.group(1))
    assert "+5V" in flag_values, f"No PWR_FLAG with Value +5V found. Flags: {flag_values}"


def test_pwr_flag_5v_no_duplicate(tmp_path):
    """If a component's power_in already drives +5V (via extended scan), no duplicate flag."""
    from boardsmith_hw.kicad_exporter import export_kicad_sch

    # HIR where there is no 5V net at all
    hir = {
        "components": [
            {"id": "MCU1", "mpn": "ATmega328P-AU", "role": "mcu",
             "name": "ATmega328P", "manufacturer": "Microchip",
             "interface_types": [], "pins": []},
        ],
        "nets": [
            {"name": "GND", "pins": [], "is_bus": False, "is_power": True},
        ],
    }
    sch = tmp_path / "test_nodup.kicad_sch"
    export_kicad_sch(hir, sch, use_llm=False, add_pwr_flag=True)
    content = sch.read_text()
    import re
    flag_values = []
    for m in re.finditer(r'lib_id ".*?PWR_FLAG".*?Value" "([^"]+)"', content, re.DOTALL):
        flag_values.append(m.group(1))
    # Without a 5V net in HIR, no +5V PWR_FLAG should appear
    assert flag_values.count("+5V") == 0, f"Spurious +5V PWR_FLAG placed when no 5V net in HIR: {flag_values}"
