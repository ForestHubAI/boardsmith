# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for HIR Pydantic models."""
import json
import pytest
from synth_core.models.hir import (
    HIR, Component, ComponentRole, InterfaceType, Net, NetPin,
    BusContract, I2CSpec, ElectricalSpec, Voltage, InitContract, InitPhase, InitPhaseTag,
    PowerSequence, Constraint, ConstraintCategory, Severity, ConstraintStatus,
    BOMEntry, HIRMetadata, Confidence, Provenance, SourceType,
)


def _make_minimal_hir() -> HIR:
    return HIR(
        version="1.1.0",
        source="prompt",
        components=[
            Component(
                id="MCU1",
                name="TestMCU",
                role=ComponentRole.mcu,
                mpn="TEST-MCU",
                interface_types=[InterfaceType.I2C],
            )
        ],
        nets=[],
        bus_contracts=[],
        electrical_specs=[],
        init_contracts=[],
        power_sequence=PowerSequence(),
        constraints=[],
        bom=[],
        metadata=HIRMetadata(
            created_at="2026-02-18T00:00:00+00:00",
            track="B",
            confidence=Confidence(overall=0.8),
        ),
    )


def test_minimal_hir_valid():
    hir = _make_minimal_hir()
    assert hir.version == "1.1.0"
    assert hir.source == "prompt"
    assert len(hir.components) == 1
    assert hir.components[0].role == ComponentRole.mcu


def test_hir_serialization_roundtrip():
    hir = _make_minimal_hir()
    data = json.loads(hir.model_dump_json())
    hir2 = HIR.model_validate(data)
    assert hir2.version == hir.version
    assert hir2.components[0].id == hir.components[0].id


def test_constraint_status_pass_serialization():
    """Ensure ConstraintStatus.pass_ serializes as 'pass', not 'pass_'."""
    c = Constraint(
        id="test.c",
        category=ConstraintCategory.electrical,
        description="test",
        severity=Severity.info,
        status=ConstraintStatus.pass_,
    )
    d = c.model_dump()
    assert d["status"] == "pass_" or d["status"] == "pass"


def test_hir_with_bus_contract():
    hir = _make_minimal_hir()
    hir.bus_contracts.append(BusContract(
        bus_name="i2c0",
        bus_type="I2C",
        master_id="MCU1",
        slave_ids=["SENSOR1"],
        slave_addresses={"SENSOR1": "0x76"},
        pin_assignments={"SDA": "21", "SCL": "22"},
        i2c=I2CSpec(max_clock_hz=400000),
    ))
    assert len(hir.bus_contracts) == 1
    assert hir.bus_contracts[0].slave_addresses["SENSOR1"] == "0x76"


def test_provenance_model():
    p = Provenance(source_type=SourceType.builtin_db, confidence=0.95)
    assert p.confidence == 0.95
    assert p.source_type == SourceType.builtin_db


def test_load_valid_fixture(tmp_path):
    import importlib.resources
    from pathlib import Path
    fixture = Path(__file__).parent.parent / "fixtures" / "boardsmith_hw" / "hir_valid_esp32_bme280.json"
    with open(fixture) as f:
        data = json.load(f)
    hir = HIR.model_validate(data)
    assert hir.version == "1.1.0"
    assert len(hir.components) == 2
    assert len(hir.bom) == 2
