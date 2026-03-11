# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for _load_kicad_pads() and its integration into _make_pads().

All tests run without a real KiCad installation — library files are mocked.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../synthesizer'))

from unittest.mock import patch, MagicMock
from boardsmith_hw.pcb_layout_engine import PcbLayoutEngine


# ---------------------------------------------------------------------------
# Minimal .kicad_mod fixture text
# ---------------------------------------------------------------------------

MINIMAL_KICAD_MOD = """
(footprint "TestFP"
  (pad "1" smd rect (at 1.0 2.0) (size 1.5 0.9) (layers "F.Cu" "F.Paste" "F.Mask"))
  (pad "2" smd rect (at -1.0 2.0) (size 1.5 0.9) (layers "F.Cu" "F.Paste" "F.Mask"))
  (pad "" np_thru_hole circle (at 0.0 0.0) (size 0.7 0.7) (drill 0.7) (layers "*.Cu"))
)
"""

# Fixture with only 1 smd pad + 1 np_thru_hole — for skip test
ONE_SMD_ONE_MECH = """
(footprint "TestFP2"
  (pad "1" smd rect (at 1.0 2.0) (size 1.5 0.9) (layers "F.Cu" "F.Paste" "F.Mask"))
  (pad "" np_thru_hole circle (at 0.0 0.0) (size 0.7 0.7) (drill 0.7) (layers "*.Cu"))
)
"""

# Fixture with pad "1" for net-injection test
NET_INJECT_MOD = """
(footprint "NetInjectFP"
  (pad "1" smd rect (at 1.0 2.0) (size 1.5 0.9) (layers "F.Cu" "F.Paste" "F.Mask"))
)
"""

# Fixture with pad "99" — unknown pad number, no matching pin
DNC_PAD_MOD = """
(footprint "DncFP"
  (pad "99" smd rect (at 1.0 2.0) (size 1.5 0.9) (layers "F.Cu" "F.Paste" "F.Mask"))
)
"""


def _make_engine() -> PcbLayoutEngine:
    return PcbLayoutEngine()


# ---------------------------------------------------------------------------
# Test 1 — returns real pad strings when .kicad_mod file exists
# ---------------------------------------------------------------------------

def test_load_kicad_pads_returns_pads():
    engine = _make_engine()
    with patch('pathlib.Path.is_file', return_value=True), \
         patch('pathlib.Path.read_text', return_value=MINIMAL_KICAD_MOD):
        result = engine._load_kicad_pads(
            fp_ref='TestLib:TestFP',
            pins=[],
            nets=[],
            comp_id='U1',
            pin_net_map=None,
        )
    # Only the 2 smd pads should be returned (np_thru_hole excluded)
    assert result is not None
    assert len(result) == 2
    for pad_str in result:
        assert pad_str.startswith('    (pad')


# ---------------------------------------------------------------------------
# Test 2 — returns None when library file is absent
# ---------------------------------------------------------------------------

def test_load_kicad_pads_library_not_found_returns_none():
    engine = _make_engine()
    with patch('pathlib.Path.is_file', return_value=False):
        result = engine._load_kicad_pads(
            fp_ref='TestLib:TestFP',
            pins=[],
            nets=[],
            comp_id='U1',
            pin_net_map=None,
        )
    assert result is None


# ---------------------------------------------------------------------------
# Test 3 — np_thru_hole pads are silently skipped
# ---------------------------------------------------------------------------

def test_load_kicad_pads_np_thru_hole_skipped():
    engine = _make_engine()
    with patch('pathlib.Path.is_file', return_value=True), \
         patch('pathlib.Path.read_text', return_value=ONE_SMD_ONE_MECH):
        result = engine._load_kicad_pads(
            fp_ref='TestLib:TestFP2',
            pins=[],
            nets=[],
            comp_id='U1',
            pin_net_map=None,
        )
    assert result is not None
    assert len(result) == 1, f"Expected 1 smd pad, got {len(result)}"


# ---------------------------------------------------------------------------
# Test 4 — pad with matching pin number receives net injection
# ---------------------------------------------------------------------------

def test_load_kicad_pads_net_injected():
    engine = _make_engine()
    pins = [{"number": "1", "name": "GND"}]
    nets = [(1, "GND")]
    with patch('pathlib.Path.is_file', return_value=True), \
         patch('pathlib.Path.read_text', return_value=NET_INJECT_MOD):
        result = engine._load_kicad_pads(
            fp_ref='TestLib:NetInjectFP',
            pins=pins,
            nets=nets,
            comp_id='U1',
            pin_net_map=None,
        )
    assert result is not None
    assert len(result) == 1
    assert '(net ' in result[0], f"Expected net injection in: {result[0]}"


# ---------------------------------------------------------------------------
# Test 5 — DNC pad (not in pin_by_num) emits no (net ...) attribute
# ---------------------------------------------------------------------------

def test_load_kicad_pads_dnc_pad_no_net():
    engine = _make_engine()
    # pin_by_num is empty — pad "99" has no matching pin
    with patch('pathlib.Path.is_file', return_value=True), \
         patch('pathlib.Path.read_text', return_value=DNC_PAD_MOD):
        result = engine._load_kicad_pads(
            fp_ref='TestLib:DncFP',
            pins=[],
            nets=[],
            comp_id='U1',
            pin_net_map=None,
        )
    assert result is not None
    assert len(result) == 1
    assert '(net ' not in result[0], f"Unexpected net injection for DNC pad: {result[0]}"


# ---------------------------------------------------------------------------
# Test 6 — _make_pads() returns library pads when _load_kicad_pads succeeds
# ---------------------------------------------------------------------------

def test_make_pads_uses_kicad_library_when_available():
    engine = _make_engine()
    with patch.object(engine, '_load_kicad_pads', return_value=["FAKE_PAD"]):
        result = engine._make_pads(
            pins=[],
            body_w=5.0,
            body_h=5.0,
            nets=[],
            role='ic',
            comp_id='U1',
            fp_ref='SomeLib:SomeFP',
        )
    assert result == ["FAKE_PAD"]


# ---------------------------------------------------------------------------
# Test 7 — _make_pads() falls back to algorithmic generators when no library
# ---------------------------------------------------------------------------

def test_make_pads_falls_back_when_library_unavailable():
    engine = _make_engine()
    with patch.object(engine, '_load_kicad_pads', return_value=None):
        result = engine._make_pads(
            pins=[],
            body_w=5.0,
            body_h=5.0,
            nets=[],
            role='ic',
            comp_id='U1',
            fp_ref='Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',
        )
    # Algorithmic fallback must produce a non-empty list
    assert isinstance(result, list)
    assert len(result) > 0
