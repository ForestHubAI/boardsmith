# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for VerifyConnectivityTool — Wave 1 implementation."""
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


def _make_sch(tmp_path: Path, content: str, name: str = "test.kicad_sch") -> str:
    """Write a .kicad_sch to tmp_path and return its path string."""
    p = tmp_path / name
    p.write_text(content)
    return str(p)


# Minimal schematic content builders

def _empty_sch() -> str:
    return "(kicad_sch (version 20230121) (generator boardsmith))\n"


def _sch_with_net_labels(*labels: str) -> str:
    """Build a schematic with named net labels (simulating signal nets)."""
    lines = [
        "(kicad_sch (version 20230121) (generator boardsmith)",
        '  (uuid "a1d8ec55-c66f-40ea-99bb-48ca70021231")',
    ]
    for i, label in enumerate(labels):
        x = 100.0 + i * 10
        lines.append(f'  (label "{label}" (at {x} 100.0 0))')
    lines.append(")\n")
    return "\n".join(lines)


def _sch_with_input_pin_and_no_net(x_pin: float = 100.0, y_pin: float = 100.0) -> str:
    """Build a schematic with one IC that has an unconnected input pin.

    The pin is placed at (x_pin, y_pin) in the schematic. No wire connects it.
    """
    return f"""\
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
        (pin input line (at 0 0 0) (length 0)
          (name "FLOATING_IN" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27)))))
      )
    )
  )
  (symbol (lib_id "boardsmith:U") (at {x_pin} {y_pin} 0) (unit 1) (in_bom yes) (on_board yes)
    (uuid "00000000-0000-0000-0000-000000000001")
    (property "Reference" "U1" (at {x_pin} {y_pin} 0)
      (effects (font (size 1.27 1.27)) (justify left)))
    (property "Value" "TestIC" (at {x_pin} {y_pin} 0)
      (effects (font (size 1.27 1.27)) (justify left)))
    (property "MPN" "TEST-IC" (at {x_pin} {y_pin} 0)
      (effects (font (size 1.27 1.27)) hide))
    (instances (project "boardsmith"
      (path "/a1d8ec55-c66f-40ea-99bb-48ca70021231" (reference "U1") (unit 1))
    ))
  )
)
"""


def _sch_with_input_pin_and_no_connect(x_nc: float = 100.0, y_nc: float = 100.0) -> str:
    """Same as above but with a (no_connect (at X Y)) marker in the schematic."""
    base = _sch_with_input_pin_and_no_net(x_pin=100.0, y_pin=100.0)
    # Insert no_connect marker before the final closing paren
    nc_line = f'  (no_connect (at {x_nc} {y_nc}))\n'
    # Replace the last line ")\n" with no_connect + ")\n"
    return base.rstrip().rstrip(")") + "\n" + nc_line + ")\n"


def _sch_with_output_pin_and_no_net() -> str:
    """Schematic with one IC that has an unconnected OUTPUT pin (should not flag)."""
    return """\
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
        (pin output line (at 0 0 0) (length 0)
          (name "OUT" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27)))))
      )
    )
  )
  (symbol (lib_id "boardsmith:U") (at 100.0 100.0 0) (unit 1) (in_bom yes) (on_board yes)
    (uuid "00000000-0000-0000-0000-000000000001")
    (property "Reference" "U1" (at 100.0 100.0 0)
      (effects (font (size 1.27 1.27)) (justify left)))
    (property "Value" "TestIC" (at 100.0 100.0 0)
      (effects (font (size 1.27 1.27)) (justify left)))
    (property "MPN" "TEST-IC" (at 100.0 100.0 0)
      (effects (font (size 1.27 1.27)) hide))
    (instances (project "boardsmith"
      (path "/a1d8ec55-c66f-40ea-99bb-48ca70021231" (reference "U1") (unit 1))
    ))
  )
)
"""


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


def _spi_bus_contract() -> dict:
    return {
        "bus_name": "SPI_1",
        "bus_type": "SPI",
        "master_id": "U1",
        "slave_ids": ["U2"],
        "configured_clock_hz": 1000000,
        "pin_assignments": {},
        "slave_addresses": {},
    }


def _hir_mcu() -> dict:
    return {
        "id": "U1", "name": "ESP32", "role": "mcu", "mpn": "ESP32-WROOM-32",
        "interface_types": ["I2C"], "pins": [],
        "provenance": {"source_type": "builtin_db", "confidence": 0.9, "evidence": []},
    }


# ---------------------------------------------------------------------------
# Tests: TestVerifyConnectivityTool
# ---------------------------------------------------------------------------

class TestVerifyConnectivityTool:
    def test_returns_violations_list(self, tmp_path):
        from boardsmith_hw.agent.verify_connectivity import VerifyConnectivityTool
        tool = VerifyConnectivityTool()
        hir_path = _make_hir(tmp_path, components=[_hir_mcu()])
        sch_path = _make_sch(tmp_path, _empty_sch())
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        assert "violations" in result.data
        assert isinstance(result.data["violations"], list)

    def test_no_bus_contracts_no_violations(self, tmp_path):
        from boardsmith_hw.agent.verify_connectivity import VerifyConnectivityTool
        tool = VerifyConnectivityTool()
        # HIR with no bus_contracts → no bus violations
        hir_path = _make_hir(tmp_path, components=[_hir_mcu()], bus_contracts=[])
        sch_path = _make_sch(tmp_path, _empty_sch())
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        bus_viols = [v for v in result.data["violations"] if v["type"] == "missing_bus_net"]
        assert bus_viols == []


# ---------------------------------------------------------------------------
# Tests: TestBusNetCheck
# ---------------------------------------------------------------------------

class TestBusNetCheck:
    def test_i2c_nets_present_no_violation(self, tmp_path):
        from boardsmith_hw.agent.verify_connectivity import VerifyConnectivityTool
        tool = VerifyConnectivityTool()
        hir_path = _make_hir(
            tmp_path, components=[_hir_mcu()], bus_contracts=[_i2c_bus_contract()]
        )
        # Schematic has SDA and SCL net labels
        sch_path = _make_sch(tmp_path, _sch_with_net_labels("SDA", "SCL"))
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        bus_viols = [v for v in result.data["violations"] if v["type"] == "missing_bus_net"]
        assert bus_viols == [], f"Unexpected violations: {bus_viols}"

    def test_missing_sda_is_error(self, tmp_path):
        from boardsmith_hw.agent.verify_connectivity import VerifyConnectivityTool
        tool = VerifyConnectivityTool()
        hir_path = _make_hir(
            tmp_path, components=[_hir_mcu()], bus_contracts=[_i2c_bus_contract()]
        )
        # Schematic has SCL but NOT SDA
        sch_path = _make_sch(tmp_path, _sch_with_net_labels("SCL"))
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        sda_viols = [
            v for v in result.data["violations"]
            if v["type"] == "missing_bus_net" and "SDA" in v["message"]
        ]
        assert len(sda_viols) == 1
        assert sda_viols[0]["severity"] == "error"

    def test_missing_scl_is_error(self, tmp_path):
        from boardsmith_hw.agent.verify_connectivity import VerifyConnectivityTool
        tool = VerifyConnectivityTool()
        hir_path = _make_hir(
            tmp_path, components=[_hir_mcu()], bus_contracts=[_i2c_bus_contract()]
        )
        # Schematic has SDA but NOT SCL
        sch_path = _make_sch(tmp_path, _sch_with_net_labels("SDA"))
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        scl_viols = [
            v for v in result.data["violations"]
            if v["type"] == "missing_bus_net" and "SCL" in v["message"]
        ]
        assert len(scl_viols) == 1
        assert scl_viols[0]["severity"] == "error"

    def test_spi_nets_checked(self, tmp_path):
        from boardsmith_hw.agent.verify_connectivity import VerifyConnectivityTool
        tool = VerifyConnectivityTool()
        hir_path = _make_hir(
            tmp_path, components=[_hir_mcu()], bus_contracts=[_spi_bus_contract()]
        )
        # Schematic has MOSI, MISO, SCLK — SCLK also covers "SCK" substring check
        sch_path = _make_sch(tmp_path, _sch_with_net_labels("MOSI", "MISO", "SCLK"))
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        bus_viols = [v for v in result.data["violations"] if v["type"] == "missing_bus_net"]
        assert bus_viols == [], f"Unexpected SPI violations: {bus_viols}"


# ---------------------------------------------------------------------------
# Tests: TestFloatingPinCheck
# ---------------------------------------------------------------------------

class TestFloatingPinCheck:
    def test_floating_input_is_warning(self, tmp_path):
        from boardsmith_hw.agent.verify_connectivity import VerifyConnectivityTool
        tool = VerifyConnectivityTool()
        hir_path = _make_hir(tmp_path)
        # Schematic with an unconnected input pin, no no_connect markers
        sch_path = _make_sch(tmp_path, _sch_with_input_pin_and_no_net())
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        float_viols = [
            v for v in result.data["violations"] if v["type"] == "floating_input_pin"
        ]
        assert len(float_viols) >= 1
        assert float_viols[0]["severity"] == "warning"

    def test_noconnect_suppresses_violation(self, tmp_path):
        from boardsmith_hw.agent.verify_connectivity import VerifyConnectivityTool
        tool = VerifyConnectivityTool()
        hir_path = _make_hir(tmp_path)
        # Same unconnected input pin BUT schematic has a (no_connect (at X Y)) marker
        # Per our implementation: if ANY no_connect marker exists, suppress all floating-pin
        # violations to avoid false positives (since GraphPin has no coordinates).
        sch_path = _make_sch(tmp_path, _sch_with_input_pin_and_no_connect(x_nc=100.0, y_nc=100.0))
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        float_viols = [
            v for v in result.data["violations"] if v["type"] == "floating_input_pin"
        ]
        # no_connect markers suppress floating-pin violations (conservative behavior)
        assert float_viols == [], f"Expected no violations, got: {float_viols}"

    def test_output_pin_not_floating(self, tmp_path):
        from boardsmith_hw.agent.verify_connectivity import VerifyConnectivityTool
        tool = VerifyConnectivityTool()
        hir_path = _make_hir(tmp_path)
        # Schematic with an unconnected OUTPUT pin — should NOT be flagged
        sch_path = _make_sch(tmp_path, _sch_with_output_pin_and_no_net())
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        float_viols = [
            v for v in result.data["violations"] if v["type"] == "floating_input_pin"
        ]
        assert float_viols == [], f"Output pin should not trigger floating violation"
