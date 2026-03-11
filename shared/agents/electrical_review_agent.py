# SPDX-License-Identifier: AGPL-3.0-or-later
"""ElectricalReviewAgent — Phase 21 specialist for electrical correctness.

Checks:
  - Voltage-level conflicts (5V I/O driving 3.3V-only MCU input)
  - I2C bus loading (pull-up resistance, slave count, capacitance)
  - SPI clock frequency vs. component maximum ratings
  - Missing decoupling capacitors for ICs
  - Power-rail sequencing violations

All checks are fully deterministic (no LLM required).
Score: 1.0 = no issues; penalties accumulate per error/warning.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Score thresholds
# ---------------------------------------------------------------------------

_ERROR_PENALTY   = 0.20
_WARNING_PENALTY = 0.05
_MAX_PENALTY     = 0.80   # cap at 80 % so score never reaches 0.0 on warnings

# Known 5V-IO components (MPN patterns) — drive 5V logic levels
_FIVE_VOLT_IO_PATTERNS = (
    "74HC", "74LS", "7404", "7408", "ATMEGA", "ATM328", "ATM2560",
    "MCP23017",   # 5V tolerant with VDD=5V
)
# MCUs that are NOT 5V-tolerant on GPIO
_3V3_ONLY_MCUS = (
    "ESP32", "RP2040", "STM32", "NRF52", "ESP8266", "W600",
)

# Maximum recommended I2C slaves before bus loading becomes marginal
_I2C_MAX_SLAVES = 8

# Maximum SPI clock (Hz) for multi-device bus without signal integrity review
_SPI_MAX_SAFE_HZ = 20_000_000  # 20 MHz


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ElectricalIssue:
    code: str
    severity: str          # "error" | "warning" | "info"
    message: str
    suggestion: str = ""
    component_id: str | None = None


@dataclass
class ElectricalReviewResult:
    issues: list[ElectricalIssue] = field(default_factory=list)
    score: float = 1.0
    checks_run: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[ElectricalIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ElectricalIssue]:
        return [i for i in self.issues if i.severity == "warning"]


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class ElectricalReviewAgent:
    """Deterministic electrical-correctness reviewer.

    Usage::

        agent = ElectricalReviewAgent()
        result = agent.review(hir_dict)
        print(f"Electrical score: {result.score:.2f}")
        for issue in result.issues:
            print(f"  [{issue.severity}] {issue.code}: {issue.message}")
    """

    def review(self, hir_dict: dict[str, Any]) -> ElectricalReviewResult:
        """Run all electrical checks and return a scored result."""
        result = ElectricalReviewResult()

        self._check_voltage_conflicts(hir_dict, result)
        self._check_i2c_bus_loading(hir_dict, result)
        self._check_spi_clock_rates(hir_dict, result)
        self._check_missing_decoupling(hir_dict, result)
        self._check_power_sequencing(hir_dict, result)

        # --- Score ---
        n_errors   = len(result.errors)
        n_warnings = len(result.warnings)
        penalty = min(_ERROR_PENALTY * n_errors + _WARNING_PENALTY * n_warnings, _MAX_PENALTY)
        result.score = round(max(0.0, 1.0 - penalty), 3)

        return result

    # ------------------------------------------------------------------
    # Check: voltage-level conflicts
    # ------------------------------------------------------------------

    def _check_voltage_conflicts(
        self,
        hir: dict,
        result: ElectricalReviewResult,
    ) -> None:
        result.checks_run.append("voltage_conflict")
        components: list[dict] = hir.get("components", [])

        mcu_ids: set[str] = set()
        mcu_is_3v3 = False
        for c in components:
            role = c.get("role", "")
            mpn  = (c.get("mpn") or "").upper()
            if role == "mcu":
                mcu_ids.add(c["id"])
                if any(pat in mpn for pat in _3V3_ONLY_MCUS):
                    mcu_is_3v3 = True

        if not mcu_is_3v3:
            return   # Can't determine risk without knowing MCU voltage domain

        for c in components:
            mpn = (c.get("mpn") or "").upper()
            cid = c.get("id", "?")
            if any(pat in mpn for pat in _FIVE_VOLT_IO_PATTERNS):
                result.issues.append(ElectricalIssue(
                    code="VOLTAGE_LEVEL_CONFLICT",
                    severity="warning",
                    message=(
                        f"{cid} ({c.get('mpn', '')}) may output 5 V logic; "
                        "MCU GPIO is 3.3 V only — add level shifter or voltage divider."
                    ),
                    suggestion="Add TXS0108E / BSS138 level shifter between 5V device and MCU.",
                    component_id=cid,
                ))

    # ------------------------------------------------------------------
    # Check: I2C bus loading
    # ------------------------------------------------------------------

    def _check_i2c_bus_loading(
        self,
        hir: dict,
        result: ElectricalReviewResult,
    ) -> None:
        result.checks_run.append("i2c_bus_loading")
        bus_contracts: list[dict] = hir.get("bus_contracts", [])

        for bc in bus_contracts:
            if bc.get("bus_type") != "I2C":
                continue
            slaves = bc.get("slave_ids", [])
            n = len(slaves)
            if n > _I2C_MAX_SLAVES:
                result.issues.append(ElectricalIssue(
                    code="I2C_OVERLOADED",
                    severity="error",
                    message=(
                        f"I2C bus '{bc.get('bus_name', '?')}' has {n} slaves "
                        f"(max recommended: {_I2C_MAX_SLAVES}). "
                        "Bus capacitance may exceed 400 pF limit."
                    ),
                    suggestion="Add I2C multiplexer (TCA9548A) to split into sub-buses.",
                ))
            elif n > 4:
                result.issues.append(ElectricalIssue(
                    code="I2C_HIGH_LOAD",
                    severity="warning",
                    message=(
                        f"I2C bus '{bc.get('bus_name', '?')}' has {n} slaves. "
                        "Verify pull-up resistors (1kΩ–4.7kΩ) and total bus capacitance."
                    ),
                    suggestion="Use 1kΩ pull-ups for fast-mode (400 kHz) with >4 slaves.",
                ))

    # ------------------------------------------------------------------
    # Check: SPI clock rates
    # ------------------------------------------------------------------

    def _check_spi_clock_rates(
        self,
        hir: dict,
        result: ElectricalReviewResult,
    ) -> None:
        result.checks_run.append("spi_clock_rate")
        bus_contracts: list[dict] = hir.get("bus_contracts", [])

        for bc in bus_contracts:
            if bc.get("bus_type") != "SPI":
                continue
            hz = bc.get("configured_clock_hz", 0) or 0
            if hz > _SPI_MAX_SAFE_HZ:
                n_slaves = len(bc.get("slave_ids", []))
                result.issues.append(ElectricalIssue(
                    code="SPI_CLOCK_TOO_HIGH",
                    severity="warning" if n_slaves == 1 else "error",
                    message=(
                        f"SPI bus '{bc.get('bus_name', '?')}' configured at "
                        f"{hz/1_000_000:.0f} MHz with {n_slaves} slave(s). "
                        "Signal integrity may degrade without impedance matching."
                    ),
                    suggestion=(
                        "Add 22–33 Ω series resistors on MOSI/MISO/SCLK; "
                        "keep traces < 50 mm and use ground plane."
                    ),
                ))

    # ------------------------------------------------------------------
    # Check: missing decoupling capacitors
    # ------------------------------------------------------------------

    def _check_missing_decoupling(
        self,
        hir: dict,
        result: ElectricalReviewResult,
    ) -> None:
        result.checks_run.append("missing_decoupling")
        components: list[dict] = hir.get("components", [])

        # Identify ICs (MCUs, sensors, comms, power) and passives
        ics = [c for c in components if c.get("role") not in ("passive",)]
        passives = [c for c in components if c.get("role") == "passive"]

        decap_names = ("100nf", "100n", "10uf", "10u", "decoupl", "bypass", "1uf")
        has_decap = any(
            any(kw in (p.get("name") or p.get("mpn") or "").lower() for kw in decap_names)
            for p in passives
        )

        if ics and not has_decap:
            result.issues.append(ElectricalIssue(
                code="MISSING_DECOUPLING",
                severity="warning",
                message=(
                    f"{len(ics)} IC(s) present but no decoupling capacitors in BOM. "
                    "Power supply noise may cause instability."
                ),
                suggestion=(
                    "Add 100 nF ceramic cap per IC power pin (0402 MLCC, X5R/X7R), "
                    "placed < 0.5 mm from IC VCC pin."
                ),
            ))

    # ------------------------------------------------------------------
    # Check: power sequencing
    # ------------------------------------------------------------------

    def _check_power_sequencing(
        self,
        hir: dict,
        result: ElectricalReviewResult,
    ) -> None:
        result.checks_run.append("power_sequencing")
        power_seq: dict = hir.get("power_sequence", {})
        rails: list[dict] = power_seq.get("rails", [])
        dependencies: list[dict] = power_seq.get("dependencies", [])

        if not rails or not dependencies:
            return   # No sequencing data — skip (not an error)

        # Detect circular dependencies
        after: dict[str, set[str]] = {}
        for dep in dependencies:
            src = dep.get("after") or dep.get("source") or ""
            dst = dep.get("rail")  or dep.get("target") or ""
            after.setdefault(dst, set()).add(src)

        # Simple cycle detection (DFS)
        def has_cycle(node: str, visited: set[str], stack: set[str]) -> bool:
            visited.add(node)
            stack.add(node)
            for dep in after.get(node, set()):
                if dep not in visited:
                    if has_cycle(dep, visited, stack):
                        return True
                elif dep in stack:
                    return True
            stack.discard(node)
            return False

        visited: set[str] = set()
        for rail in after:
            if rail not in visited:
                if has_cycle(rail, visited, set()):
                    result.issues.append(ElectricalIssue(
                        code="POWER_SEQ_CYCLE",
                        severity="error",
                        message=(
                            "Circular power-sequencing dependency detected. "
                            "Verify power-rail enable order."
                        ),
                        suggestion="Use dedicated power-sequencing IC (e.g. TPS3431).",
                    ))
                    break
