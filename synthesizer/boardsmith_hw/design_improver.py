# SPDX-License-Identifier: AGPL-3.0-or-later
"""Design Improver — applies DesignReviewAgent feedback to a HIR dict.

Implements targeted, deterministic improvements based on structured issue codes
from the DesignReviewResult. The improver never touches issues it does not
understand — unknown issue codes are silently skipped.

Usage:
    improver = DesignImprover()
    updated_hir, applied = improver.apply(hir_dict, review_result)
    # applied: list[str] — codes that were resolved
"""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class ImprovementResult:
    """Result of one improvement pass."""

    hir_dict: dict[str, Any]
    applied: list[str] = field(default_factory=list)    # issue codes resolved
    skipped: list[str] = field(default_factory=list)    # issue codes skipped
    assumptions: list[str] = field(default_factory=list)


class DesignImprover:
    """Apply DesignReviewAgent issue codes back to a HIR dict.

    Strategies implemented:
      - OVERCURRENT   → upgrade regulator to next-higher-capacity LDO
      - I2C_ADDRESS_CONFLICT → delegate to ConstraintRefiner (existing logic)
      - EOL_COMPONENT → swap to first in-production alternative from knowledge DB
      - HIGH_BOM_COST → log only (user decision required)
    """

    def apply(
        self,
        hir_dict: dict[str, Any],
        review_result: Any,  # DesignReviewResult — avoid circular import
    ) -> ImprovementResult:
        """Apply improvements for all fixable issues in review_result.

        Args:
            hir_dict:      Original HIR dict (not modified in-place).
            review_result: DesignReviewResult from DesignReviewAgent.

        Returns:
            ImprovementResult with updated HIR and lists of applied/skipped codes.
        """
        updated = copy.deepcopy(hir_dict)
        applied: list[str] = []
        skipped: list[str] = []
        assumptions: list[str] = []

        for issue in review_result.issues:
            if issue.severity not in ("error", "warning"):
                continue

            handler = self._HANDLERS.get(issue.code)
            if handler is None:
                log.debug("No handler for issue code %s — skipping", issue.code)
                skipped.append(issue.code)
                continue

            try:
                changed, note = handler(self, updated, issue)
                if changed:
                    applied.append(issue.code)
                    if note:
                        assumptions.append(note)
                    log.info("Applied fix for %s: %s", issue.code, note)
                else:
                    skipped.append(issue.code)
            except Exception as exc:
                log.warning("Fix for %s failed: %s", issue.code, exc)
                skipped.append(issue.code)

        # Re-run constraint refiner on the updated HIR if there were changes
        if applied:
            updated = self._refine(updated, assumptions)

        return ImprovementResult(
            hir_dict=updated,
            applied=applied,
            skipped=skipped,
            assumptions=assumptions,
        )

    # ------------------------------------------------------------------
    # Fix handlers
    # ------------------------------------------------------------------

    def _fix_overcurrent(
        self, hir_dict: dict[str, Any], issue: Any
    ) -> tuple[bool, str]:
        """Replace the power regulator with a higher-capacity one."""
        comps = hir_dict.get("components", [])

        # Find the regulator component by role
        reg_comp: dict | None = None
        for c in comps:
            role = c.get("role", "").lower()
            mpn = c.get("mpn", "").lower()
            if role == "power" or any(kw in mpn for kw in ("ams1117", "ap2112", "mcp1700")):
                reg_comp = c
                break

        if reg_comp is None:
            return False, ""

        current_mpn = reg_comp.get("mpn", "")
        # Upgrade path: MCP1700 (250mA) → AP2112K (600mA) → AMS1117 (800mA)
        UPGRADE_PATH = ["MCP1700-3302E", "AP2112K-3.3TRG1", "AMS1117-3.3"]
        try:
            idx = next(
                i for i, m in enumerate(UPGRADE_PATH)
                if m.lower() in current_mpn.lower()
            )
        except StopIteration:
            idx = -1

        if idx >= len(UPGRADE_PATH) - 1:
            # Already at AMS1117 — nothing bigger in our library
            return False, ""

        new_mpn = UPGRADE_PATH[idx + 1]
        reg_comp["mpn"] = new_mpn
        reg_comp["name"] = f"{new_mpn} LDO Voltage Regulator (upgraded)"

        # Update capabilities
        caps = reg_comp.setdefault("capabilities", {})
        _CAPACITIES = {"MCP1700-3302E": 250.0, "AP2112K-3.3TRG1": 600.0, "AMS1117-3.3": 800.0}
        caps["output_current_max_ma"] = _CAPACITIES[new_mpn]

        return True, f"Upgraded regulator {current_mpn} → {new_mpn} for higher current capacity"

    def _fix_eol_component(
        self, hir_dict: dict[str, Any], issue: Any
    ) -> tuple[bool, str]:
        """Swap an EOL component with the first active alternative in the DB."""
        mpn_to_fix = issue.component_id or ""
        if not mpn_to_fix:
            return False, ""

        try:
            from knowledge.components import COMPONENTS, find_by_mpn
        except ImportError:
            return False, ""

        original = find_by_mpn(mpn_to_fix)
        if not original:
            return False, ""

        orig_cat = original.get("category", "")
        orig_sub = original.get("sub_type", "")

        # Find active replacement in same category/sub_type
        replacement: dict | None = None
        for c in COMPONENTS:
            if c.get("mpn") == mpn_to_fix:
                continue
            if c.get("category") != orig_cat:
                continue
            if orig_sub and c.get("sub_type") != orig_sub:
                continue
            if c.get("status", "active") == "active":
                replacement = c
                break

        if not replacement:
            return False, ""

        comps = hir_dict.get("components", [])
        for comp in comps:
            if comp.get("mpn") == mpn_to_fix or comp.get("id") == mpn_to_fix:
                comp["mpn"] = replacement["mpn"]
                comp["name"] = replacement.get("name", replacement["mpn"])
                comp["unit_cost_usd"] = replacement.get("unit_cost_usd", comp.get("unit_cost_usd"))
                return True, f"Swapped EOL {mpn_to_fix} → {replacement['mpn']}"

        return False, ""

    def _fix_i2c_conflict(
        self, hir_dict: dict[str, Any], issue: Any
    ) -> tuple[bool, str]:
        """Delegate I2C address conflict fix to ConstraintRefiner."""
        try:
            from boardsmith_hw.constraint_refiner import ConstraintRefiner
            from shared.models.hir import HIR
        except ImportError:
            return False, ""

        try:
            hir = HIR(**hir_dict)
        except Exception:
            return False, ""

        refiner = ConstraintRefiner(max_iterations=1, use_llm=False)
        result = refiner.refine(hir)
        if result.resolved:
            hir_dict.update(result.hir)
            return True, f"ConstraintRefiner resolved: {', '.join(result.resolved)}"
        return False, ""

    # ------------------------------------------------------------------
    # Dispatch table
    # ------------------------------------------------------------------

    _HANDLERS: dict[str, Any] = {
        "OVERCURRENT": _fix_overcurrent,
        "EOL_COMPONENT": _fix_eol_component,
        "I2C_ADDRESS_CONFLICT": _fix_i2c_conflict,
        # HIGH_BOM_COST, MISSING_INIT_CONTRACT, etc. → no auto-fix
    }

    # ------------------------------------------------------------------
    # Post-fix refinement
    # ------------------------------------------------------------------

    def _refine(
        self, hir_dict: dict[str, Any], assumptions: list[str]
    ) -> dict[str, Any]:
        """Run a light constraint check after improvements."""
        try:
            from boardsmith_hw.hir_validator import validate_hir_dict
            report = validate_hir_dict(hir_dict)
            if not report.is_valid:
                log.warning(
                    "Post-improvement validation: %d errors remain",
                    len([d for d in report.diagnostics if d.status == "FAIL"]),
                )
        except ImportError:
            pass
        hir_dict.setdefault("metadata", {})
        hir_dict["metadata"]["improvement_assumptions"] = assumptions
        return hir_dict
