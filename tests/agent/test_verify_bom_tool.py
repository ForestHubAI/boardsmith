# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for VerifyBomTool — Wave 1 implementation (Phase 12-01)."""
from __future__ import annotations
import asyncio
import csv
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


def _make_bom_csv(tmp_path: Path, rows: list[dict]) -> str:
    """Write bom.csv with header Qty,MPN,Description,Manufacturer,UnitCost_USD,ComponentID; return str path."""
    p = tmp_path / "bom.csv"
    fieldnames = ["Qty", "MPN", "Description", "Manufacturer", "UnitCost_USD", "ComponentID"]
    with open(p, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    return str(p)


def _hir_component(ref: str, mpn: str, name: str = None) -> dict:
    return {
        "id": ref,
        "name": name or ref,
        "role": "mcu",
        "mpn": mpn,
        "interface_types": [],
        "pins": [],
        "provenance": {"source_type": "builtin_db", "confidence": 0.9, "evidence": []},
    }


# ---------------------------------------------------------------------------
# TestVerifyBomTool
# ---------------------------------------------------------------------------

class TestVerifyBomTool:
    def test_component_present_no_violation(self, tmp_path):
        """HIR has U1 (ESP32-WROOM-32), bom.csv has row ComponentID=U1 MPN=ESP32-WROOM-32 → violations == []."""
        from boardsmith_hw.agent.verify_bom import VerifyBomTool
        tool = VerifyBomTool()
        hir_path = _make_hir(tmp_path, components=[_hir_component("U1", "ESP32-WROOM-32")])
        _make_bom_csv(tmp_path, rows=[
            {"Qty": "1", "MPN": "ESP32-WROOM-32", "Description": "ESP32 Module",
             "Manufacturer": "Espressif", "UnitCost_USD": "3.50", "ComponentID": "U1"},
        ])
        result = _run(tool.execute({"hir_path": hir_path}, _make_mock_context()))
        assert result.success is True
        assert result.data["violations"] == [], f"Expected no violations, got: {result.data['violations']}"

    def test_missing_bom_row_is_error(self, tmp_path):
        """HIR has U1, bom.csv is empty → one violation type=missing_bom_row severity=error ref=U1."""
        from boardsmith_hw.agent.verify_bom import VerifyBomTool
        tool = VerifyBomTool()
        hir_path = _make_hir(tmp_path, components=[_hir_component("U1", "ESP32-WROOM-32")])
        _make_bom_csv(tmp_path, rows=[])  # empty bom
        result = _run(tool.execute({"hir_path": hir_path}, _make_mock_context()))
        assert result.success is True
        violations = result.data["violations"]
        missing = [v for v in violations if v["type"] == "missing_bom_row"]
        assert len(missing) == 1, f"Expected 1 missing_bom_row, got: {violations}"
        assert missing[0]["severity"] == "error"
        assert missing[0]["ref"] == "U1"

    def test_mpn_mismatch_is_warning(self, tmp_path):
        """HIR has U1 MPN=ESP32-WROOM-32, bom.csv has U1 with MPN=ESP32-WROOM-33 → one violation type=mpn_mismatch severity=warning."""
        from boardsmith_hw.agent.verify_bom import VerifyBomTool
        tool = VerifyBomTool()
        hir_path = _make_hir(tmp_path, components=[_hir_component("U1", "ESP32-WROOM-32")])
        _make_bom_csv(tmp_path, rows=[
            {"Qty": "1", "MPN": "ESP32-WROOM-33", "Description": "ESP32 Module",
             "Manufacturer": "Espressif", "UnitCost_USD": "3.50", "ComponentID": "U1"},
        ])
        result = _run(tool.execute({"hir_path": hir_path}, _make_mock_context()))
        assert result.success is True
        violations = result.data["violations"]
        mismatches = [v for v in violations if v["type"] == "mpn_mismatch"]
        assert len(mismatches) == 1, f"Expected 1 mpn_mismatch, got: {violations}"
        assert mismatches[0]["severity"] == "warning"

    def test_missing_csv_returns_failure(self, tmp_path):
        """hir.json exists, bom.csv absent → result.success is False."""
        from boardsmith_hw.agent.verify_bom import VerifyBomTool
        tool = VerifyBomTool()
        hir_path = _make_hir(tmp_path, components=[_hir_component("U1", "ESP32-WROOM-32")])
        # Do NOT create bom.csv
        result = _run(tool.execute({"hir_path": hir_path}, _make_mock_context()))
        assert result.success is False, "Expected success=False when bom.csv is missing"

    def test_empty_mpn_no_mismatch(self, tmp_path):
        """HIR has U1 MPN=ESP32-WROOM-32, bom.csv has U1 with MPN='' → violations == [] (no mpn_mismatch)."""
        from boardsmith_hw.agent.verify_bom import VerifyBomTool
        tool = VerifyBomTool()
        hir_path = _make_hir(tmp_path, components=[_hir_component("U1", "ESP32-WROOM-32")])
        _make_bom_csv(tmp_path, rows=[
            {"Qty": "1", "MPN": "", "Description": "ESP32 Module",
             "Manufacturer": "Espressif", "UnitCost_USD": "3.50", "ComponentID": "U1"},
        ])
        result = _run(tool.execute({"hir_path": hir_path}, _make_mock_context()))
        assert result.success is True
        violations = result.data["violations"]
        mismatches = [v for v in violations if v["type"] == "mpn_mismatch"]
        assert mismatches == [], f"Expected no mpn_mismatch when bom MPN is empty, got: {violations}"

    def test_registered_in_default_registry(self):
        """get_default_registry().get('verify_bom') is not None."""
        from tools.registry import get_default_registry
        registry = get_default_registry()
        tool = registry.get("verify_bom")
        assert tool is not None, "verify_bom not found in default registry"
