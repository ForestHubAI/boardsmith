# SPDX-License-Identifier: AGPL-3.0-or-later
"""HIR constraint solver and validator — Compiler oracle for Boardsmith iteration."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from synth_core.models.hir import (
    HIR, Constraint, ConstraintCategory, Severity, ConstraintStatus, Provenance, SourceType,
)

_SCHEMA_PATH = Path(__file__).parent.parent.parent / "schemas" / "hir" / "v1.1.0" / "hir.schema.json"

_INF_PROV = Provenance(source_type=SourceType.inference, confidence=1.0)


def _c(
    id_: str,
    category: ConstraintCategory,
    description: str,
    severity: Severity,
    status: ConstraintStatus,
    details: str | None = None,
    affected: list[str] | None = None,
    fixes: list[str] | None = None,
    path: str | None = None,
) -> Constraint:
    return Constraint(
        id=id_,
        category=category,
        description=description,
        severity=severity,
        status=status,
        details=details,
        affected_components=affected or [],
        suggested_fixes=fixes or [],
        path=path,
        provenance=_INF_PROV,
    )


def solve_constraints(hir: HIR) -> list[Constraint]:
    """Run all deterministic constraint checks and return results."""
    results: list[Constraint] = []

    # Build index
    comp_by_id = {c.id: c for c in hir.components}
    elec_by_id = {e.component_id: e for e in hir.electrical_specs}

    # ------------------------------------------------------------------
    # 1. I2C address conflict detection
    # ------------------------------------------------------------------
    for bc in hir.bus_contracts:
        if bc.bus_type.upper() != "I2C":
            continue
        addr_to_slaves: dict[str, list[str]] = {}
        for sid, addr in bc.slave_addresses.items():
            addr_to_slaves.setdefault(addr.lower(), []).append(sid)
        for addr, sids in addr_to_slaves.items():
            if len(sids) > 1:
                results.append(_c(
                    f"i2c_addr.{bc.bus_name}.conflict",
                    ConstraintCategory.protocol,
                    f"I2C address conflict on bus '{bc.bus_name}': {addr} used by {', '.join(sids)}",
                    Severity.error,
                    ConstraintStatus.fail,
                    details=f"Components {sids} share address {addr}",
                    affected=sids,
                    fixes=[
                        "Change address pin (ADO/SDO) on one device if selectable",
                        "Insert I2C multiplexer (e.g. TCA9548A)",
                        "Move one device to a separate I2C bus",
                    ],
                    path=f"$.bus_contracts[bus_name={bc.bus_name}].slave_addresses",
                ))
            else:
                cid = sids[0]
                results.append(_c(
                    f"i2c_addr.{bc.bus_name}.{cid}.ok",
                    ConstraintCategory.protocol,
                    f"I2C address {addr} on bus '{bc.bus_name}' for '{cid}' is unique",
                    Severity.info,
                    ConstraintStatus.pass_,
                    affected=[cid],
                ))

    # ------------------------------------------------------------------
    # 2. Voltage compatibility
    # ------------------------------------------------------------------
    for bc in hir.bus_contracts:
        master_elec = elec_by_id.get(bc.master_id)
        if not master_elec:
            continue
        master_io_nom = master_elec.io_voltage.nominal if master_elec.io_voltage else None
        if master_io_nom is None:
            continue

        for sid in bc.slave_ids:
            slave_elec = elec_by_id.get(sid)
            if not slave_elec or not slave_elec.supply_voltage:
                # Missing knowledge
                results.append(_c(
                    f"voltage.{sid}.unknown",
                    ConstraintCategory.electrical,
                    f"Voltage ratings for '{sid}' are unknown",
                    Severity.warning,
                    ConstraintStatus.unknown,
                    affected=[sid],
                    fixes=["Add component to knowledge DB or provide explicit electrical_specs"],
                ))
                continue

            slave_vdd_min = slave_elec.supply_voltage.min or slave_elec.supply_voltage.nominal
            slave_vdd_max = slave_elec.supply_voltage.max or slave_elec.supply_voltage.nominal
            is_5v_tol = slave_elec.is_5v_tolerant or False

            # Check if master drives 3.3V into a 3.3V-only slave when master is 5V
            if master_io_nom > 3.4 and slave_vdd_max <= 3.6 and not is_5v_tol:
                results.append(_c(
                    f"voltage.level.{bc.master_id}.{sid}",
                    ConstraintCategory.electrical,
                    f"Voltage mismatch: master '{bc.master_id}' ({master_io_nom}V IO) → slave '{sid}' (max {slave_vdd_max}V)",
                    Severity.error,
                    ConstraintStatus.fail,
                    affected=[bc.master_id, sid],
                    fixes=[
                        "Add level shifter (e.g. TXS0102) between master and slave",
                        "Use 3.3V MCU variant",
                    ],
                ))
            else:
                results.append(_c(
                    f"voltage.level.{bc.master_id}.{sid}.ok",
                    ConstraintCategory.electrical,
                    f"Voltage levels compatible: '{bc.master_id}' → '{sid}'",
                    Severity.info,
                    ConstraintStatus.pass_,
                    affected=[bc.master_id, sid],
                ))

    # ------------------------------------------------------------------
    # 3. Clock speed compatibility
    # ------------------------------------------------------------------
    for bc in hir.bus_contracts:
        if bc.configured_clock_hz is None:
            continue

        bt = bc.bus_type.upper()
        for sid in bc.slave_ids:
            slave_comp = comp_by_id.get(sid)
            if not slave_comp:
                continue
            # Check via bus_contract's protocol sub-object
            max_clock = None
            if bt == "I2C" and bc.i2c:
                max_clock = bc.i2c.max_clock_hz
            elif bt == "SPI" and bc.spi:
                max_clock = bc.spi.max_clock_hz

            if max_clock and bc.configured_clock_hz > max_clock:
                results.append(_c(
                    f"timing.clock.{bc.bus_name}.{sid}",
                    ConstraintCategory.timing,
                    f"Configured clock {bc.configured_clock_hz}Hz exceeds max {max_clock}Hz for '{sid}' on bus '{bc.bus_name}'",
                    Severity.error,
                    ConstraintStatus.fail,
                    affected=[sid],
                    fixes=[f"Reduce clock to <= {max_clock}Hz"],
                    path=f"$.bus_contracts[bus_name={bc.bus_name}].configured_clock_hz",
                ))

    # ------------------------------------------------------------------
    # 4. Init contract coverage
    # ------------------------------------------------------------------
    init_ids = {ic.component_id for ic in hir.init_contracts}
    for bc in hir.bus_contracts:
        for sid in bc.slave_ids:
            if sid not in init_ids:
                results.append(_c(
                    f"knowledge.init.{sid}.missing",
                    ConstraintCategory.knowledge,
                    f"No init_contract found for peripheral '{sid}'",
                    Severity.warning,
                    ConstraintStatus.unknown,
                    affected=[sid],
                    fixes=["Add init_contract for this component in the HIR or knowledge DB"],
                ))
            else:
                results.append(_c(
                    f"knowledge.init.{sid}.ok",
                    ConstraintCategory.knowledge,
                    f"Init contract present for '{sid}'",
                    Severity.info,
                    ConstraintStatus.pass_,
                    affected=[sid],
                ))

    # ------------------------------------------------------------------
    # 5. SPI chip-select conflict detection
    # ------------------------------------------------------------------
    for bc in hir.bus_contracts:
        if bc.bus_type.upper() != "SPI":
            continue
        # Collect chip-select assignments: look for "CS" / "SS" key in
        # pin_assignments ("CS" -> gpio_name) or in bus.pin_assignments
        cs_pins: dict[str, str] = {}  # slave_id -> CS gpio
        for sid in bc.slave_ids:
            # First: look for slave-specific CS key (e.g. CS_SX1276, as assigned by topology synthesizer)
            cs_key_specific = f"CS_{sid}".upper()
            for sig, gpio in bc.pin_assignments.items():
                if sig.upper() == cs_key_specific:
                    cs_pins[sid] = gpio
                    break
            else:
                # Fallback: generic CS/SS/NSS/NCS key (single-slave or manually specified buses)
                for sig, gpio in bc.pin_assignments.items():
                    if sig.upper() in ("CS", "SS", "NSS", "NCS"):
                        cs_pins.setdefault(sid, gpio)
                        break
        # Check for shared CS gpio (multiple slaves mapped to same pin)
        gpio_to_slaves: dict[str, list[str]] = {}
        for sid, gpio in cs_pins.items():
            gpio_to_slaves.setdefault(gpio, []).append(sid)
        for gpio, sids in gpio_to_slaves.items():
            if len(sids) > 1:
                results.append(_c(
                    f"spi.cs.{bc.bus_name}.conflict",
                    ConstraintCategory.protocol,
                    f"SPI CS conflict on bus '{bc.bus_name}': GPIO '{gpio}' shared by {', '.join(sids)}",
                    Severity.error,
                    ConstraintStatus.fail,
                    details=f"Components {sids} share the same chip-select pin '{gpio}'",
                    affected=sids,
                    fixes=[
                        "Assign a unique GPIO pin as chip-select for each SPI slave",
                        "Use a CS decoder / demultiplexer (e.g. 74HC138)",
                    ],
                    path=f"$.bus_contracts[bus_name={bc.bus_name}].pin_assignments",
                ))

        # Verify that every SPI slave has a dedicated CS pin assigned
        slaves_without_cs = [sid for sid in bc.slave_ids if sid not in cs_pins]
        for sid in slaves_without_cs:
            results.append(_c(
                f"spi.cs.{bc.bus_name}.{sid}.missing",
                ConstraintCategory.protocol,
                f"SPI slave '{sid}' on bus '{bc.bus_name}' has no chip-select (CS) pin assigned",
                Severity.warning,
                ConstraintStatus.unknown,
                affected=[sid, bc.master_id],
                fixes=[
                    f"Add a CS pin assignment for '{sid}' in the bus contract pin_assignments",
                    "Verify the HIR topology synthesizer assigns unique CS GPIOs per SPI slave",
                ],
                path=f"$.bus_contracts[bus_name={bc.bus_name}].pin_assignments",
            ))

        # Pass: no CS conflicts and all slaves have CS
        if not slaves_without_cs and not any(len(v) > 1 for v in gpio_to_slaves.values()):
            for sid in bc.slave_ids:
                results.append(_c(
                    f"spi.cs.{bc.bus_name}.{sid}.ok",
                    ConstraintCategory.protocol,
                    f"SPI chip-select for '{sid}' on bus '{bc.bus_name}' is unique",
                    Severity.info,
                    ConstraintStatus.pass_,
                    affected=[sid],
                ))

    # ------------------------------------------------------------------
    # 6. BOM completeness (Boardsmith only)
    # ------------------------------------------------------------------
    if hir.metadata.track == "B":
        bom_cids = {b.component_id for b in hir.bom}
        active_ids = [c.id for c in hir.components if c.role.value in ("mcu", "sensor", "actuator", "comms", "memory")]
        missing_bom = [cid for cid in active_ids if cid not in bom_cids]
        if missing_bom:
            results.append(_c(
                "bom.incomplete",
                ConstraintCategory.topology,
                f"BOM missing entries for active components: {missing_bom}",
                Severity.warning,
                ConstraintStatus.fail,
                affected=missing_bom,
                fixes=["Add BOM entries for all active components"],
            ))
        else:
            results.append(_c(
                "bom.complete",
                ConstraintCategory.topology,
                "BOM covers all active components",
                Severity.info,
                ConstraintStatus.pass_,
            ))

    return results


class DiagnosticsReport:
    """Machine-readable diagnostics result from validate_hir."""

    TOOL_VERSION = "0.6.0"

    def __init__(self, constraints: list[Constraint], hir_version: str = "1.1.0") -> None:
        self.constraints = constraints
        self.hir_version = hir_version

    @property
    def valid(self) -> bool:
        return not any(
            c.severity == Severity.error and c.status == ConstraintStatus.fail
            for c in self.constraints
        )

    def to_dict(self) -> dict:
        errors = sum(1 for c in self.constraints if c.severity == Severity.error and c.status == ConstraintStatus.fail)
        warnings = sum(1 for c in self.constraints if c.severity == Severity.warning)
        info = sum(1 for c in self.constraints if c.severity == Severity.info)
        unknown = sum(1 for c in self.constraints if c.status == ConstraintStatus.unknown)

        diags = []
        for c in self.constraints:
            d = {
                "id": c.id,
                "category": c.category.value,
                "severity": c.severity.value,
                "status": c.status.value if c.status.value != "pass_" else "pass",
                "message": c.description,
            }
            if c.path:
                d["path"] = c.path
            if c.affected_components:
                d["affected_components"] = c.affected_components
            if c.suggested_fixes:
                d["suggested_fixes"] = c.suggested_fixes
            if c.details:
                d["details"] = c.details
            if c.provenance:
                d["provenance"] = {
                    "source_type": c.provenance.source_type.value,
                    "confidence": c.provenance.confidence,
                }
            diags.append(d)

        return {
            "tool": "boardsmith-fw",
            "version": self.TOOL_VERSION,
            "hir_version": self.hir_version,
            "valid": self.valid,
            "summary": {
                "total": len(self.constraints),
                "errors": errors,
                "warnings": warnings,
                "info": info,
                "unknown": unknown,
            },
            "diagnostics": diags,
        }


def validate_hir(hir: HIR, validate_schema: bool = True) -> DiagnosticsReport:
    """Full HIR validation: JSON Schema + semantic constraints."""
    constraints: list[Constraint] = []

    # --- JSON schema validation ---
    if validate_schema and _SCHEMA_PATH.exists():
        with open(_SCHEMA_PATH) as f:
            schema = json.load(f)
        hir_dict = json.loads(hir.model_dump_json(exclude_none=True))
        # Fix pass_ -> pass
        for c in hir_dict.get("constraints", []):
            if c.get("status") == "pass_":
                c["status"] = "pass"
        try:
            jsonschema.validate(instance=hir_dict, schema=schema)
        except jsonschema.ValidationError as e:
            constraints.append(_c(
                "schema.validation.fail",
                ConstraintCategory.topology,
                f"HIR JSON schema validation failed: {e.message}",
                Severity.error,
                ConstraintStatus.fail,
                path=str(e.json_path) if hasattr(e, "json_path") else None,
            ))
        else:
            constraints.append(_c(
                "schema.validation.ok",
                ConstraintCategory.topology,
                "HIR JSON schema validation passed",
                Severity.info,
                ConstraintStatus.pass_,
            ))

    # --- Semantic constraints ---
    constraints.extend(solve_constraints(hir))

    return DiagnosticsReport(constraints=constraints, hir_version=hir.version)
