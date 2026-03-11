# SPDX-License-Identifier: AGPL-3.0-or-later
"""ComponentQualityAgent — Phase 21 specialist for component availability & cost.

Checks:
  - JLCPCB part availability (basic vs. extended parts library)
  - EOL / NRND (Not Recommended for New Designs) markers in MPN
  - BOM cost estimation (unit price tiers)
  - Package suitability for hand assembly vs. machine assembly
  - Alternative component suggestions when issues are found

All checks are fully deterministic (no LLM required).
Score: 1.0 = all components readily available and well-priced.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JLCPCB basic-parts library (a representative subset of the ~40k basic parts)
# These parts have no assembly surcharge at JLCPCB.
# ---------------------------------------------------------------------------

_JLCPCB_BASIC_MPN_PATTERNS = (
    # Passives
    "RC0402", "RC0603", "RC0805",           # generic resistors
    "CC0402", "CC0603", "CC0805",           # generic capacitors
    "CL05", "CL10", "GCM", "GRM",          # Samsung / Murata MLCCs
    # Logic
    "74HC", "74HCT", "SN74",
    # Regulators
    "AMS1117", "XC6206", "ME6211", "LM3940",
    # Common sensors
    "BME280", "BME680", "MPU6050", "MPU9250",
    # Common MCUs
    "ESP32", "RP2040", "STM32F103",
    # Common displays/comms
    "SSD1306", "SX1276", "CC1101",
)

# EOL/NRND markers in MPN or description (case-insensitive substrings)
_EOL_MARKERS = ("eol", "nrnd", "obsolete", "discontinued", "not recommended")

# Package patterns that need machine-pick-and-place (not hand-solderable)
_MACHINE_ONLY_PACKAGES = ("BGA", "WLCSP", "FCBGA", "DSBGA")
# Packages that are hand-solderable
_HAND_SOLDERABLE_PACKAGES = ("DIP", "SOP", "SOIC", "TSSOP", "QFN", "SOT")

# Unit price bands (USD, rough JLCPCB estimates for 10 pcs)
_PRICE_BANDS: list[tuple[str, float]] = [
    ("basic_passive", 0.01),
    ("basic_ic",      0.50),
    ("sensor",        2.00),
    ("mcu",           3.00),
    ("rf_module",     5.00),
    ("specialty",    15.00),
]

_ROLE_TO_PRICE_BAND: dict[str, str] = {
    "passive":   "basic_passive",
    "power":     "basic_ic",
    "sensor":    "sensor",
    "mcu":       "mcu",
    "comms":     "rf_module",
}

_WARN_BOM_COST_USD = 50.00    # warn if estimated BOM > $50
_ERROR_BOM_COST_USD = 200.00  # error if estimated BOM > $200

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ComponentQualityIssue:
    code: str
    severity: str           # "error" | "warning" | "info"
    message: str
    suggestion: str = ""
    component_id: str | None = None
    alternative_mpn: str | None = None


@dataclass
class ComponentQualityResult:
    issues: list[ComponentQualityIssue] = field(default_factory=list)
    score: float = 1.0
    estimated_bom_usd: float = 0.0
    checks_run: list[str] = field(default_factory=list)
    jlcpcb_basic_count: int = 0
    jlcpcb_extended_count: int = 0

    @property
    def errors(self) -> list[ComponentQualityIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ComponentQualityIssue]:
        return [i for i in self.issues if i.severity == "warning"]


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class ComponentQualityAgent:
    """Deterministic component availability and cost reviewer.

    Usage::

        agent = ComponentQualityAgent()
        result = agent.review(hir_dict)
        print(f"Component quality score: {result.score:.2f}")
        print(f"Estimated BOM cost: ${result.estimated_bom_usd:.2f}")
    """

    def review(self, hir_dict: dict[str, Any]) -> ComponentQualityResult:
        """Run all quality checks and return a scored result."""
        result = ComponentQualityResult()
        components: list[dict] = hir_dict.get("components", [])

        self._check_jlcpcb_availability(components, result)
        self._check_eol_status(components, result)
        self._check_package_suitability(components, result)
        self._estimate_bom_cost(components, hir_dict, result)

        # --- Score ---
        n_errors   = len(result.errors)
        n_warnings = len(result.warnings)
        penalty = min(0.25 * n_errors + 0.05 * n_warnings, 0.80)
        result.score = round(max(0.0, 1.0 - penalty), 3)

        return result

    # ------------------------------------------------------------------
    # Check: JLCPCB availability
    # ------------------------------------------------------------------

    def _check_jlcpcb_availability(
        self,
        components: list[dict],
        result: ComponentQualityResult,
    ) -> None:
        result.checks_run.append("jlcpcb_availability")
        for c in components:
            mpn = (c.get("mpn") or "").upper()
            cid = c.get("id", "?")
            is_basic = any(pat.upper() in mpn for pat in _JLCPCB_BASIC_MPN_PATTERNS)
            if is_basic:
                result.jlcpcb_basic_count += 1
            else:
                result.jlcpcb_extended_count += 1
                # Only warn for ICs — passives are almost always available
                if c.get("role") not in ("passive",):
                    result.issues.append(ComponentQualityIssue(
                        code="JLCPCB_EXTENDED_PART",
                        severity="info",
                        message=(
                            f"{cid} ({c.get('mpn', '?')}) is likely an extended "
                            "JLCPCB part (extra assembly fee ~$3 per unique part)."
                        ),
                        suggestion=(
                            "Check https://jlcpcb.com/parts for availability; "
                            "consider a basic-library alternative if cost-sensitive."
                        ),
                        component_id=cid,
                    ))

    # ------------------------------------------------------------------
    # Check: EOL/NRND
    # ------------------------------------------------------------------

    def _check_eol_status(
        self,
        components: list[dict],
        result: ComponentQualityResult,
    ) -> None:
        result.checks_run.append("eol_status")
        for c in components:
            cid  = c.get("id", "?")
            text = " ".join(filter(None, [
                c.get("mpn", ""),
                c.get("name", ""),
                c.get("description", ""),
            ])).lower()
            if any(marker in text for marker in _EOL_MARKERS):
                result.issues.append(ComponentQualityIssue(
                    code="EOL_COMPONENT",
                    severity="warning",
                    message=(
                        f"{cid} ({c.get('mpn', '?')}) appears to be EOL or "
                        "NRND. Long-term availability is at risk."
                    ),
                    suggestion=(
                        "Select an actively sold replacement from the same family "
                        "or an equivalent from a different manufacturer."
                    ),
                    component_id=cid,
                ))

    # ------------------------------------------------------------------
    # Check: package suitability
    # ------------------------------------------------------------------

    def _check_package_suitability(
        self,
        components: list[dict],
        result: ComponentQualityResult,
    ) -> None:
        result.checks_run.append("package_suitability")
        for c in components:
            cid = c.get("id", "?")
            pkg = (
                c.get("package")
                or c.get("footprint", "")
                or ""
            ).upper()
            if any(pat in pkg for pat in _MACHINE_ONLY_PACKAGES):
                result.issues.append(ComponentQualityIssue(
                    code="MACHINE_ONLY_PACKAGE",
                    severity="warning",
                    message=(
                        f"{cid} uses {pkg} package which requires machine assembly "
                        "(no hand-soldering). Prototype cost will be higher."
                    ),
                    suggestion=(
                        "For prototyping, prefer QFN, SOIC or DIP variants. "
                        "BGA/WLCSP are fine for production but expensive in small runs."
                    ),
                    component_id=cid,
                ))

    # ------------------------------------------------------------------
    # Estimate: BOM cost
    # ------------------------------------------------------------------

    def _estimate_bom_cost(
        self,
        components: list[dict],
        hir: dict,
        result: ComponentQualityResult,
    ) -> None:
        result.checks_run.append("bom_cost_estimate")

        # If BOM entries carry a unit_price field, use it; otherwise estimate
        bom: list[dict] = hir.get("bom", [])
        bom_by_id = {b.get("component_id", b.get("id", "")): b for b in bom}

        total = 0.0
        for c in components:
            cid  = c.get("id", "?")
            bom_entry = bom_by_id.get(cid, {})
            unit_price = bom_entry.get("unit_price") or bom_entry.get("price")
            qty        = bom_entry.get("qty") or bom_entry.get("quantity", 1)
            if unit_price is not None:
                total += float(unit_price) * float(qty)
            else:
                # Estimate from role
                role = c.get("role", "sensor")
                band_name = _ROLE_TO_PRICE_BAND.get(role, "sensor")
                price = next(
                    (p for n, p in _PRICE_BANDS if n == band_name),
                    2.00,
                )
                total += price

        result.estimated_bom_usd = round(total, 2)

        if total > _ERROR_BOM_COST_USD:
            result.issues.append(ComponentQualityIssue(
                code="BOM_COST_HIGH",
                severity="error",
                message=(
                    f"Estimated BOM cost ${total:.2f} exceeds ${_ERROR_BOM_COST_USD:.0f} "
                    "threshold. Review component selection for cost optimisation."
                ),
                suggestion=(
                    "Replace specialty ICs with lower-cost equivalents; "
                    "consolidate sensors (e.g. BME680 = temp+humidity+pressure+gas)."
                ),
            ))
        elif total > _WARN_BOM_COST_USD:
            result.issues.append(ComponentQualityIssue(
                code="BOM_COST_ELEVATED",
                severity="warning",
                message=(
                    f"Estimated BOM cost ${total:.2f} is above ${_WARN_BOM_COST_USD:.0f}. "
                    "Check for cheaper alternatives."
                ),
                suggestion=(
                    "Use JLCPCB basic-library parts where possible; "
                    "compare AliExpress pricing for volume orders."
                ),
            ))
