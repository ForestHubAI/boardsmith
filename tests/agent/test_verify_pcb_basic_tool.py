# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for VerifyPcbBasicTool — Wave 1 implementation (Phase 12-01)."""
from __future__ import annotations
import asyncio
import datetime
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
for _pkg in ("synthesizer", "shared", "compiler"):
    _p = str(REPO_ROOT / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _run(coro):
    return asyncio.run(coro)


def _make_mock_context():
    from unittest.mock import MagicMock
    ctx = MagicMock()
    ctx.no_llm = False
    return ctx


def _make_hir(tmp_path: Path, components=None) -> str:
    """Write a minimal hir.json to tmp_path and return its path string."""
    hir_dict = {
        "version": "1.1.0",
        "source": "prompt",
        "components": components or [],
        "nets": [],
        "buses": [],
        "bus_contracts": [],
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


# Minimal KiCad schematic S-expression with two symbols (U1, R1)
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


def _make_sch(tmp_path: Path, refs: list[str]) -> str:
    """Write minimal .kicad_sch with placed symbols for each ref; return str path."""
    symbols = []
    for i, ref in enumerate(refs):
        lib_sym = "boardsmith:R" if ref.startswith("R") else "boardsmith:U"
        symbols.append(_make_symbol_instance(ref, ref, ref, x=100.0 + i * 20, lib_sym=lib_sym))
    content = _SCH_HEADER + "".join(symbols) + _SCH_FOOTER
    p = tmp_path / "test.kicad_sch"
    p.write_text(content)
    return str(p)


def _make_pcb(tmp_path: Path, refs: list[str]) -> str:
    """Write minimal .kicad_pcb with (property "Reference" "X" ...) entries for each ref; return str path."""
    footprints = []
    for ref in refs:
        footprints.append(
            f'  (footprint "boardsmith:U" (layer "F.Cu")\n'
            f'    (property "Reference" "{ref}" (at 0 0 0))\n'
            f'  )'
        )
    pcb_text = "(kicad_pcb (version 20230121)\n" + "\n".join(footprints) + "\n)\n"
    p = tmp_path / "test.kicad_pcb"
    p.write_text(pcb_text)
    return str(p)


# ---------------------------------------------------------------------------
# TestVerifyPcbBasicTool
# ---------------------------------------------------------------------------

class TestVerifyPcbBasicTool:
    def test_all_refs_present_no_violation(self, tmp_path):
        """Schematic has U1 R1, PCB has both refs → violations == []."""
        from boardsmith_hw.agent.verify_pcb_basic import VerifyPcbBasicTool
        tool = VerifyPcbBasicTool()
        hir_path = _make_hir(tmp_path)
        sch_path = _make_sch(tmp_path, refs=["U1", "R1"])
        _make_pcb(tmp_path, refs=["U1", "R1"])
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        violations = result.data["violations"]
        assert violations == [], f"Expected no violations, got: {violations}"

    def test_missing_footprint_is_warning(self, tmp_path):
        """Schematic has U1 R1, PCB only has U1 → one violation type=missing_pcb_footprint severity=warning ref=R1."""
        from boardsmith_hw.agent.verify_pcb_basic import VerifyPcbBasicTool
        tool = VerifyPcbBasicTool()
        hir_path = _make_hir(tmp_path)
        sch_path = _make_sch(tmp_path, refs=["U1", "R1"])
        _make_pcb(tmp_path, refs=["U1"])  # R1 missing from PCB
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        violations = result.data["violations"]
        missing = [v for v in violations if v["type"] == "missing_pcb_footprint"]
        assert len(missing) == 1, f"Expected 1 missing_pcb_footprint, got: {violations}"
        assert missing[0]["severity"] == "warning"
        assert missing[0]["ref"] == "R1"

    def test_no_pcb_file_skips(self, tmp_path):
        """No .kicad_pcb file in out_dir → success=True skipped=True violations==[]."""
        from boardsmith_hw.agent.verify_pcb_basic import VerifyPcbBasicTool
        tool = VerifyPcbBasicTool()
        hir_path = _make_hir(tmp_path)
        sch_path = _make_sch(tmp_path, refs=["U1", "R1"])
        # Do NOT create any .kicad_pcb file
        result = _run(tool.execute(
            {"hir_path": hir_path, "sch_path": sch_path},
            _make_mock_context(),
        ))
        assert result.success is True
        assert result.data.get("skipped") is True, f"Expected skipped=True, got: {result.data}"
        assert result.data["violations"] == []
