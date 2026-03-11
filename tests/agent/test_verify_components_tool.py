# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for VerifyComponentsTool — Wave 1 implementation."""
from __future__ import annotations
import asyncio
import json
import datetime
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler"):
    _p = str(REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

FIXTURES = Path(__file__).parent / "fixtures"


def _make_mock_context():
    ctx = MagicMock()
    ctx.no_llm = False
    return ctx


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Minimal KiCad schematic builders
# ---------------------------------------------------------------------------

_SCH_HEADER = """\
(kicad_sch (version 20230121) (generator boardsmith)
  (uuid "a1d8ec55-c66f-40ea-99bb-48ca70021231")
  (paper "A4")
  (lib_symbols
    (symbol "boardsmith:U" (pin_names (offset 0)) (in_bom yes) (on_board yes)
      (property "Reference" "U" (at 0 1.016 0)
        (effects (font (size 1.27 1.27)) (justify left)))
      (property "Value" "U" (at 0 -1.016 0)
        (effects (font (size 1.27 1.27)) (justify left)))
      (symbol "U_1_1"
        (pin input line (at -2.54 0 0) (length 0)
          (name "IN" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27)))))
        (pin output line (at 2.54 0 180) (length 0)
          (name "OUT" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27)))))
      )
    )
    (symbol "boardsmith:C" (pin_names (offset 0)) (in_bom yes) (on_board yes)
      (property "Reference" "C" (at 0 1.016 0)
        (effects (font (size 1.27 1.27)) (justify left)))
      (property "Value" "C" (at 0 -1.016 0)
        (effects (font (size 1.27 1.27)) (justify left)))
      (symbol "C_1_1"
        (pin passive line (at 0 1.016 270) (length 0)
          (name "~" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 0 -1.016 90) (length 0)
          (name "~" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27)))))
      )
    )
    (symbol "boardsmith:R" (pin_names (offset 0)) (in_bom yes) (on_board yes)
      (property "Reference" "R" (at 0 1.016 0)
        (effects (font (size 1.27 1.27)) (justify left)))
      (property "Value" "R" (at 0 -1.016 0)
        (effects (font (size 1.27 1.27)) (justify left)))
      (symbol "R_1_1"
        (pin passive line (at -1.016 0 0) (length 0)
          (name "~" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 1.016 0 180) (length 0)
          (name "~" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27)))))
      )
    )
  )
"""

_SCH_FOOTER = ")\n"


def _make_symbol_instance(ref: str, value: str, mpn: str, x: float = 100.0, y: float = 100.0,
                           lib_sym: str = "boardsmith:U") -> str:
    """Return a placed symbol S-expression string."""
    return f"""\
  (symbol (lib_id "{lib_sym}") (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes)
    (uuid "00000000-0000-0000-0000-{ref.lower().replace(' ', '0'):0>12s}")
    (property "Reference" "{ref}" (at {x} {y} 0)
      (effects (font (size 1.27 1.27)) (justify left)))
    (property "Value" "{value}" (at {x} {y} 0)
      (effects (font (size 1.27 1.27)) (justify left)))
    (property "MPN" "{mpn}" (at {x} {y} 0)
      (effects (font (size 1.27 1.27)) hide))
    (instances (project "boardsmith"
      (path "/a1d8ec55-c66f-40ea-99bb-48ca70021231" (reference "{ref}") (unit 1))
    ))
  )
"""


def _make_hir(tmp_path: Path, components=None, bus_contracts=None) -> str:
    """Write a minimal hir.json to tmp_path and return its path string."""
    hir_dict = {
        "version": "1.1.0",
        "source": "prompt",
        "components": components or [],
        "nets": [],
        "buses": [],
        "bus_contracts": bus_contracts or [],
        "electrical_specs": [],
        "init_contracts": [],
        "power_sequence": {"rails": [], "dependencies": []},
        "constraints": [],
        "bom": [],
        "metadata": {
            "created_at": datetime.datetime.utcnow().isoformat(),
            "track": "B",
            "confidence": {"overall": 0.9, "subscores": None, "explanations": []},
            "assumptions": [],
            "session_id": None,
        },
    }
    p = tmp_path / "hir.json"
    p.write_text(json.dumps(hir_dict))
    return str(p)


def _make_sch(tmp_path: Path, symbols: list[str] | None = None) -> str:
    """Write a minimal .kicad_sch to tmp_path and return its path string."""
    body = "".join(symbols or [])
    content = _SCH_HEADER + body + _SCH_FOOTER
    p = tmp_path / "test.kicad_sch"
    p.write_text(content)
    return str(p)


# HIR component dicts

def _hir_mcu(mpn: str = "ESP32-WROOM-32") -> dict:
    return {
        "id": "U1", "name": "ESP32", "role": "mcu", "mpn": mpn,
        "interface_types": [], "pins": [],
        "provenance": {"source_type": "builtin_db", "confidence": 0.9, "evidence": []},
    }


def _hir_sensor(mpn: str = "BME280") -> dict:
    return {
        "id": "U2", "name": "BME280", "role": "sensor", "mpn": mpn,
        "interface_types": [], "pins": [],
        "provenance": {"source_type": "builtin_db", "confidence": 0.9, "evidence": []},
    }


def _i2c_bus_contract() -> dict:
    return {
        "bus_name": "I2C_1",
        "bus_type": "I2C",
        "master_id": "U1",
        "slave_ids": ["U2"],
        "configured_clock_hz": 400000,
        "pin_assignments": {"SDA": "GPIO21", "SCL": "GPIO22"},
        "slave_addresses": {},
    }


# ---------------------------------------------------------------------------
# Tests: TestVerifyComponentsTool
# ---------------------------------------------------------------------------

class TestVerifyComponentsTool:
    def test_returns_violations_list(self, tmp_path):
        from boardsmith_hw.agent.verify_components import VerifyComponentsTool
        tool = VerifyComponentsTool()
        hir_path = _make_hir(tmp_path, components=[_hir_mcu()])
        # Schematic with no components — ESP32 will be missing → violation
        sch_path = _make_sch(tmp_path)
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        assert "violations" in result.data
        assert isinstance(result.data["violations"], list)

    def test_component_present_no_violation(self, tmp_path):
        from boardsmith_hw.agent.verify_components import VerifyComponentsTool
        tool = VerifyComponentsTool()
        hir_path = _make_hir(tmp_path, components=[_hir_mcu("ESP32-WROOM-32")])
        # Schematic has U1 with MPN "ESP32-WROOM-32"
        symbols = [_make_symbol_instance("U1", "ESP32", "ESP32-WROOM-32")]
        sch_path = _make_sch(tmp_path, symbols)
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        placement_viols = [
            v for v in result.data["violations"]
            if v["type"] == "missing_component"
        ]
        assert placement_viols == [], f"Unexpected violations: {placement_viols}"

    def test_missing_component_is_error(self, tmp_path):
        from boardsmith_hw.agent.verify_components import VerifyComponentsTool
        tool = VerifyComponentsTool()
        # HIR has ESP32 but schematic is empty
        hir_path = _make_hir(tmp_path, components=[_hir_mcu("ESP32-WROOM-32")])
        sch_path = _make_sch(tmp_path)
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        missing = [v for v in result.data["violations"] if v["type"] == "missing_component"]
        assert len(missing) == 1
        assert missing[0]["severity"] == "error"
        assert missing[0]["type"] == "missing_component"

    def test_hir_not_found_returns_failure(self, tmp_path):
        from boardsmith_hw.agent.verify_components import VerifyComponentsTool
        tool = VerifyComponentsTool()
        sch_path = _make_sch(tmp_path)
        result = _run(tool.execute(
            {"hir_path": str(tmp_path / "nonexistent_hir.json"), "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is False
        assert result.error is not None


# ---------------------------------------------------------------------------
# Tests: TestDecouplingCapCheck
# ---------------------------------------------------------------------------

class TestDecouplingCapCheck:
    def test_missing_cap_is_warning(self, tmp_path):
        from boardsmith_hw.agent.verify_components import VerifyComponentsTool
        tool = VerifyComponentsTool()
        # HIR has MCU, schematic has MCU but no 100n cap
        hir_path = _make_hir(tmp_path, components=[_hir_mcu("ESP32-WROOM-32")])
        symbols = [_make_symbol_instance("U1", "ESP32", "ESP32-WROOM-32")]
        sch_path = _make_sch(tmp_path, symbols)
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        cap_viols = [v for v in result.data["violations"] if v["type"] == "missing_decoupling_cap"]
        assert len(cap_viols) == 1
        assert cap_viols[0]["severity"] == "warning"

    def test_cap_present_no_violation(self, tmp_path):
        from boardsmith_hw.agent.verify_components import VerifyComponentsTool
        tool = VerifyComponentsTool()
        # HIR has MCU; schematic has MCU + 100n cap passive
        hir_path = _make_hir(tmp_path, components=[_hir_mcu("ESP32-WROOM-32")])
        symbols = [
            _make_symbol_instance("U1", "ESP32", "ESP32-WROOM-32"),
            # C1 with Value "100n" — parser uses MPN property first, then Value
            # Use "100n" as MPN so the tool finds it via gc.mpn
            _make_symbol_instance("C1", "100n", "100n", x=120.0, lib_sym="boardsmith:C"),
        ]
        sch_path = _make_sch(tmp_path, symbols)
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        cap_viols = [v for v in result.data["violations"] if v["type"] == "missing_decoupling_cap"]
        assert cap_viols == [], f"Unexpected cap violations: {cap_viols}"


# ---------------------------------------------------------------------------
# Tests: TestI2CPullupCheck
# ---------------------------------------------------------------------------

class TestI2CPullupCheck:
    def test_missing_pullup_is_warning(self, tmp_path):
        from boardsmith_hw.agent.verify_components import VerifyComponentsTool
        tool = VerifyComponentsTool()
        # HIR has I2C bus contract, schematic has no 4.7k resistors
        hir_path = _make_hir(
            tmp_path,
            components=[_hir_mcu("ESP32-WROOM-32"), _hir_sensor("BME280")],
            bus_contracts=[_i2c_bus_contract()],
        )
        symbols = [
            _make_symbol_instance("U1", "ESP32", "ESP32-WROOM-32"),
            _make_symbol_instance("U2", "BME280", "BME280", x=120.0),
        ]
        sch_path = _make_sch(tmp_path, symbols)
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        pullup_viols = [v for v in result.data["violations"] if v["type"] == "missing_i2c_pullup"]
        assert len(pullup_viols) == 1
        assert pullup_viols[0]["severity"] == "warning"

    def test_pullup_present_no_violation(self, tmp_path):
        from boardsmith_hw.agent.verify_components import VerifyComponentsTool
        tool = VerifyComponentsTool()
        # HIR has I2C bus contract; schematic has a 4.7k resistor
        hir_path = _make_hir(
            tmp_path,
            components=[_hir_mcu("ESP32-WROOM-32"), _hir_sensor("BME280")],
            bus_contracts=[_i2c_bus_contract()],
        )
        symbols = [
            _make_symbol_instance("U1", "ESP32", "ESP32-WROOM-32"),
            _make_symbol_instance("U2", "BME280", "BME280", x=120.0),
            # R1 with MPN "4.7k" — passive, parser infers role="passive" via 'R' prefix
            _make_symbol_instance("R1", "4.7k", "4.7k", x=140.0, lib_sym="boardsmith:R"),
        ]
        sch_path = _make_sch(tmp_path, symbols)
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        pullup_viols = [v for v in result.data["violations"] if v["type"] == "missing_i2c_pullup"]
        assert pullup_viols == [], f"Unexpected pullup violations: {pullup_viols}"
