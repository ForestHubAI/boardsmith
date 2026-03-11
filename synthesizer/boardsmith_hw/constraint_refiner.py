# SPDX-License-Identifier: AGPL-3.0-or-later
"""B6. Constraint Refiner — iterative HIR refinement using Track A validator."""
from __future__ import annotations

import copy
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from synth_core.api.compiler import validate_hir_dict
from synth_core.hir_bridge.validator import DiagnosticsReport
from synth_core.models.hir import HIR

log = logging.getLogger(__name__)


@dataclass
class RefinementResult:
    hir: dict[str, Any]
    report: DiagnosticsReport
    iterations: int
    resolved: list[str] = field(default_factory=list)
    unresolvable: list[str] = field(default_factory=list)
    llm_boosted: bool = False


class ConstraintRefiner:
    """Applies ranked fix strategies to resolve HIR constraint failures.

    Two-phase approach:
      1. Hardcoded fixes (fast, deterministic): I2C address conflict, voltage mismatch.
      2. LLM-boost phase: if hardcoded fixes are exhausted and use_llm=True, asks the
         LLM for a structured fix, applies it to a copy, re-validates, and accepts only
         if the constraint solver passes. "LLM schlägt vor, Solver validiert."
    """

    def __init__(self, max_iterations: int = 5, use_llm: bool = True) -> None:
        self.max_iterations = max_iterations
        self._use_llm = use_llm

    def refine(self, hir: HIR) -> RefinementResult:
        """Run validation loop, applying fixes until valid or exhausted.

        Phase 1: hardcoded fixes (deterministic).
        Phase 2: LLM-boost — when hardcoded fixes can't make progress,
                 ask the LLM for a fix, apply to a copy, validate;
                 accept only if the solver agrees.
        """
        hir_dict = self._to_dict(hir)
        resolved: list[str] = []
        unresolvable: list[str] = []
        llm_boosted = False

        for i in range(self.max_iterations):
            report = validate_hir_dict(hir_dict)
            errors = [d for d in report.constraints
                      if d.severity.value == "error" and d.status.value == "fail"]

            if not errors:
                break

            any_fixed = False
            for err in errors:
                fixed = self._apply_fix(hir_dict, err)
                if fixed:
                    resolved.append(err.id)
                    any_fixed = True
                else:
                    if err.id not in unresolvable:
                        unresolvable.append(err.id)

            if not any_fixed:
                # --- LLM-Boost Phase ---
                # Hardcoded fixes exhausted; try LLM for still-unresolvable errors.
                if self._use_llm:
                    remaining = [err for err in errors if err.id in unresolvable]
                    llm_any = False
                    for err in remaining:
                        if self._llm_suggest_and_apply(hir_dict, err):
                            resolved.append(f"{err.id}(llm)")
                            unresolvable.remove(err.id)
                            llm_any = True
                            llm_boosted = True
                            log.debug("B6 LLM-boost resolved %s", err.id)
                    if llm_any:
                        continue  # Re-validate after LLM fixes
                break

        final_report = validate_hir_dict(hir_dict)
        return RefinementResult(
            hir=hir_dict,
            report=final_report,
            iterations=i + 1,
            resolved=resolved,
            unresolvable=unresolvable,
            llm_boosted=llm_boosted,
        )

    def _to_dict(self, hir: HIR) -> dict[str, Any]:
        import json
        d = json.loads(hir.model_dump_json())
        # Normalize status pass_ → pass
        for c in d.get("constraints", []):
            if c.get("status") == "pass_":
                c["status"] = "pass"
        return d

    def _apply_fix(self, hir_dict: dict[str, Any], constraint: Any) -> bool:
        """Attempt to auto-fix a single constraint failure. Returns True if fixed."""
        cid = constraint.id

        # --- I2C address conflict ---
        if "i2c_addr" in cid and "conflict" in cid:
            return self._fix_i2c_conflict(hir_dict, constraint)

        # --- Voltage mismatch ---
        if "voltage.level" in cid:
            return self._fix_voltage_mismatch(hir_dict, constraint)

        return False

    def _fix_i2c_conflict(self, hir_dict: dict[str, Any], constraint: Any) -> bool:
        """Try to resolve I2C address conflict.

        Strategy 1: Switch to an alternate address (hardware address pins).
        Strategy 2: Insert a TCA9548A I2C multiplexer and route conflicting
                    slaves to separate channels.
        """
        from synth_core.api.compiler import list_components

        affected = constraint.affected_components
        if len(affected) < 2:
            return False

        bus_name = self._extract_bus_name(constraint.id)
        for bc in hir_dict.get("bus_contracts", []):
            if bc.get("bus_name") != bus_name:
                continue

            slave_addrs = bc.get("slave_addresses", {})
            addr_to_slaves: dict[str, list[str]] = {}
            for sid, addr in slave_addrs.items():
                addr_to_slaves.setdefault(addr.lower(), []).append(sid)

            for addr, sids in addr_to_slaves.items():
                if len(sids) < 2:
                    continue

                # --- Strategy 1: Alternate address ---
                for sid in sids[1:]:
                    comp_mpn = self._get_mpn_for_id(hir_dict, sid)
                    if comp_mpn:
                        for c in list_components():
                            if c.get("mpn", "").upper() == comp_mpn.upper():
                                all_addrs = [a.lower() for a in c.get("known_i2c_addresses", [])]
                                used = set(v.lower() for v in slave_addrs.values())
                                for alt in all_addrs:
                                    if alt not in used:
                                        slave_addrs[sid] = alt
                                        return True

                # --- Strategy 2: Insert TCA9548A I2C Mux ---
                if self._insert_i2c_mux(hir_dict, bc, bus_name, sids):
                    return True

            break
        return False

    def _insert_i2c_mux(
        self,
        hir_dict: dict[str, Any],
        main_bc: dict[str, Any],
        bus_name: str,
        conflicting_sids: list[str],
    ) -> bool:
        """Insert a TCA9548A I2C mux and route each conflicting slave to its own channel.

        Modifies hir_dict in-place:
        - Adds TCA9548A component + BOM entry
        - Adds TCA9548A as slave on the existing bus (at 0x70)
        - Creates sub-buses i2c0_ch0, i2c0_ch1, … for each conflicting slave
        - Moves conflicting slaves off the main bus onto their sub-buses
        """
        from synth_core.api.compiler import list_components

        mux_id = "TCA9548A_MUX1"
        mux_addr = "0x70"

        # Avoid double-insertion
        if any(c.get("id") == mux_id for c in hir_dict.get("components", [])):
            return False

        # Look up TCA9548A in catalog
        mux_entry = next(
            (c for c in list_components() if c.get("mpn", "").upper() == "TCA9548A"),
            None,
        )
        if mux_entry is None:
            return False

        # 1. Add TCA9548A component
        hir_dict.setdefault("components", []).append({
            "id": mux_id,
            "name": "TCA9548A 1-to-8 I2C Mux (auto-inserted for address conflict)",
            "role": "comms",
            "mpn": "TCA9548A",
            "manufacturer": "Texas Instruments",
            "interface_types": ["I2C"],
            "provenance": {"source_type": "inference", "confidence": 0.90, "evidence": []},
        })

        # 2. Add TCA9548A to BOM
        existing_line_ids = {e.get("line_id", "") for e in hir_dict.get("bom", [])}
        mux_line_id = "MX001"
        while mux_line_id in existing_line_ids:
            mux_line_id = f"MX{int(mux_line_id[2:]) + 1:03d}"
        hir_dict.setdefault("bom", []).append({
            "line_id": mux_line_id,
            "component_id": mux_id,
            "mpn": "TCA9548A",
            "manufacturer": "Texas Instruments",
            "description": "I2C Mux — auto-added to resolve unresolvable address conflict",
            "qty": 1.0,
            "unit_cost_estimate": 0.95,
            "provenance": {"source_type": "inference", "confidence": 0.90, "evidence": []},
        })

        # 3. Add TCA9548A as slave on the main bus
        for bus in hir_dict.get("buses", []):
            if bus.get("name") == bus_name:
                bus.setdefault("slave_component_ids", []).append(mux_id)
                break
        main_bc.setdefault("slave_addresses", {})[mux_id] = mux_addr

        # 4. Save addresses before removing, then remove from main bus + bus contract
        slave_addrs = main_bc.get("slave_addresses", {})
        saved_addrs = {sid: slave_addrs.get(sid, "0x00") for sid in conflicting_sids}
        for sid in conflicting_sids:
            for bus in hir_dict.get("buses", []):
                if bus.get("name") == bus_name and sid in bus.get("slave_component_ids", []):
                    bus["slave_component_ids"].remove(sid)
            slave_addrs.pop(sid, None)

        # 5. Create sub-buses + bus contracts for each conflicting slave
        master_id = main_bc.get("master_id", "")
        for ch_idx, sid in enumerate(conflicting_sids):
            ch_name = f"{bus_name}_mux_ch{ch_idx}"
            sid_addr = saved_addrs.get(sid, "0x00")

            hir_dict.setdefault("buses", []).append({
                "name": ch_name,
                "type": "I2C",
                "master_component_id": mux_id,
                "slave_component_ids": [sid],
            })
            hir_dict.setdefault("bus_contracts", []).append({
                "bus_name": ch_name,
                "bus_type": "I2C",
                "master_id": mux_id,
                "slave_ids": [sid],
                "configured_clock_hz": 400000,
                "pin_assignments": {"SDA": f"SD{ch_idx}", "SCL": f"SC{ch_idx}"},
                "slave_addresses": {sid: sid_addr},
                "i2c": {"max_clock_hz": 400000, "address_bits": 7},
                "provenance": {"source_type": "inference", "confidence": 0.85, "evidence": []},
            })

        # 6. Record in metadata assumptions
        msg = (
            f"I2C address conflict on {bus_name}: inserted TCA9548A mux (addr {mux_addr}). "
            f"Slaves {conflicting_sids} routed to channels "
            f"{[f'{bus_name}_mux_ch{i}' for i in range(len(conflicting_sids))]}."
        )
        hir_dict.setdefault("metadata", {}).setdefault("assumptions", []).append(msg)
        return True

    # ------------------------------------------------------------------
    # LLM-Boost: ask LLM for a fix → validate copy → apply if solver agrees
    # ------------------------------------------------------------------

    def _llm_suggest_and_apply(self, hir_dict: dict[str, Any], constraint: Any) -> bool:
        """Ask LLM to propose a structured fix for a constraint failure.

        1. Build a minimal prompt with constraint info + HIR summary.
        2. Parse LLM JSON response into an action dict.
        3. Apply the fix to a *copy* of hir_dict.
        4. Re-validate the copy with the constraint solver.
        5. Only update hir_dict in-place when the solver passes.
        Returns True if a valid fix was found and applied.
        """
        try:
            from llm.gateway import get_default_gateway
            from llm.types import TaskType

            gateway = get_default_gateway()
            if not gateway.is_llm_available():
                return False
        except ImportError:
            return False

        # Build constraint description
        constraint_info = {
            "id": constraint.id,
            "severity": constraint.severity.value,
            "message": getattr(constraint, "message", str(constraint.id)),
            "affected_components": getattr(constraint, "affected_components", []),
        }

        # Minimal HIR context (avoid huge prompts)
        hir_summary = {
            "buses": [
                {"name": b.get("name"), "type": b.get("type"),
                 "slave_ids": b.get("slave_component_ids", [])}
                for b in hir_dict.get("buses", [])
            ],
            "bus_contracts": [
                {"bus_name": bc.get("bus_name"), "bus_type": bc.get("bus_type"),
                 "clock_hz": bc.get("configured_clock_hz"),
                 "slave_addresses": bc.get("slave_addresses", {})}
                for bc in hir_dict.get("bus_contracts", [])
            ],
            "components": [
                {"id": c["id"], "mpn": c.get("mpn"), "role": c.get("role")}
                for c in hir_dict.get("components", [])
            ],
        }

        resp = None
        try:
            resp = gateway.complete_sync(
                task=TaskType.COMPONENT_SUGGEST,
                messages=[{"role": "user", "content": (
                    "I have a hardware constraint failure in an embedded design HIR.\n\n"
                    f"Constraint failure:\n{json.dumps(constraint_info, indent=2)}\n\n"
                    f"HIR summary:\n{json.dumps(hir_summary, indent=2)}\n\n"
                    "Suggest ONE fix. Return ONLY a JSON object with one of these actions:\n"
                    '{"action": "reduce_clock_hz", "bus_name": "i2c0", "new_clock_hz": 100000}\n'
                    '{"action": "change_i2c_address", "component_id": "BME280_U1", "new_address": "0x77"}\n'
                    '{"action": "document_only", "note": "requires level shifter"}\n'
                    '{"action": "none"}\n'
                    "Return ONLY valid JSON, nothing else."
                )}],
                temperature=0.0,
                max_tokens=200,
            )
        except Exception:
            return False

        if resp is None or resp.skipped or not resp.content:
            return False

        # Parse JSON from response
        match = re.search(r'\{[^}]+\}', resp.content, re.DOTALL)
        if not match:
            return False

        try:
            fix = json.loads(match.group())
        except Exception:
            return False

        action = fix.get("action", "none")
        if action in ("none", "document_only"):
            if action == "document_only" and fix.get("note"):
                hir_dict.setdefault("metadata", {}).setdefault("assumptions", []).append(
                    f"LLM note on {constraint.id}: {fix['note']}"
                )
            return False

        # Apply to a copy first
        hir_copy = copy.deepcopy(hir_dict)
        if not self._apply_llm_action(hir_copy, fix):
            return False

        # Re-validate the copy
        new_report = validate_hir_dict(hir_copy)
        still_failing = any(
            d.id == constraint.id and d.status.value == "fail"
            for d in new_report.constraints
        )
        if still_failing:
            return False

        # Solver accepts → apply to real hir_dict
        self._apply_llm_action(hir_dict, fix)
        hir_dict.setdefault("metadata", {}).setdefault("assumptions", []).append(
            f"LLM-fix applied for {constraint.id}: action={action}"
        )
        return True

    def _apply_llm_action(self, hir_dict: dict[str, Any], fix: dict[str, Any]) -> bool:
        """Apply a structured LLM fix action to hir_dict in-place."""
        action = fix.get("action")

        if action == "reduce_clock_hz":
            bus_name = fix.get("bus_name", "")
            new_clock = int(fix.get("new_clock_hz", 100_000))
            for bc in hir_dict.get("bus_contracts", []):
                if bc.get("bus_name") == bus_name:
                    bc["configured_clock_hz"] = new_clock
                    return True
            return False

        if action == "change_i2c_address":
            comp_id = fix.get("component_id", "")
            new_addr = str(fix.get("new_address", ""))
            if not comp_id or not new_addr:
                return False
            for bc in hir_dict.get("bus_contracts", []):
                addrs: dict[str, str] = bc.get("slave_addresses", {})
                if comp_id in addrs:
                    addrs[comp_id] = new_addr
                    return True
            return False

        return False

    @staticmethod
    def _get_known_addr(hir_dict: dict[str, Any], component_id: str) -> str | None:
        """Look up the first known I2C address for a component from all bus contracts."""
        for bc in hir_dict.get("bus_contracts", []):
            addr = bc.get("slave_addresses", {}).get(component_id)
            if addr:
                return addr
        return None

    def _fix_voltage_mismatch(self, hir_dict: dict[str, Any], constraint: Any) -> bool:
        """Record voltage mismatch as an assumption (can't auto-fix without HW change)."""
        msg = f"Auto-fix not possible for {constraint.id}: requires level shifter or MCU change"
        assumptions = hir_dict.get("metadata", {}).get("assumptions", [])
        if msg not in assumptions:
            assumptions.append(msg)
            hir_dict.setdefault("metadata", {})["assumptions"] = assumptions
        return False  # Still fails, but documented

    @staticmethod
    def _extract_bus_name(constraint_id: str) -> str:
        # Constraint IDs have format: "i2c_addr.<bus_name>.conflict"
        # or "i2c_addr.<bus_name>.<component_id>.ok"
        parts = constraint_id.split(".")
        if len(parts) >= 2:
            return parts[1]
        return ""

    @staticmethod
    def _get_mpn_for_id(hir_dict: dict[str, Any], component_id: str) -> str | None:
        for c in hir_dict.get("components", []):
            if c.get("id") == component_id:
                return c.get("mpn")
        return None
