# SPDX-License-Identifier: AGPL-3.0-or-later
"""Clarification Agents — Proactive questioning before and during synthesis.

Two agents that ask targeted questions instead of silently making assumptions:

  RequirementsClarificationAgent
      Runs BEFORE B1.  Analyses the raw prompt for gaps that have high
      impact on synthesis (power source, RF band, environment, budget).
      Injects answers back into the prompt as structured context.

  ComponentChallengeAgent
      Runs AFTER B3 (ComponentSelector), BEFORE B4 (TopologySynthesizer).
      Challenges component choices when genuine trade-offs exist:
      RF band mismatch, battery-hostile LDOs, significant cost alternatives.

Both agents are controlled by ClarificationMode:

  none    → silent, no questions (CI/automation, --no-llm implies this)
  single  → max 1 round per agent (default)
  auto    → keep asking until confident or 3 rounds maximum

IO is abstracted via ClarificationIO so the CLI implementation can be
swapped for a Web or API callback later without touching agent logic.

Usage (CLI)::

    from agents.clarification_agent import (
        ClarificationMode,
        CLIClarificationIO,
        RequirementsClarificationAgent,
        ComponentChallengeAgent,
    )
    from rich.console import Console

    io = CLIClarificationIO(Console())

    # Before B1:
    agent = RequirementsClarificationAgent(
        mode=ClarificationMode.SINGLE, io=io, llm_gateway=gateway
    )
    enriched_prompt, _ = await agent.clarify(prompt)

    # After B3:
    challenge = ComponentChallengeAgent(mode=ClarificationMode.SINGLE, io=io)
    selection = challenge.challenge(selection, reqs)
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mode
# ---------------------------------------------------------------------------

class ClarificationMode(str, Enum):
    """How aggressively the clarification agents ask questions."""

    NONE = "none"       # Never ask — silent assumptions (CI/automation)
    SINGLE = "single"   # Ask once, integrate answers, continue (default)
    AUTO = "auto"       # Keep asking until prompt is clear (max 3 rounds)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ClarificationQuestion:
    """A single question for the user."""

    field: str          # Internal field name, e.g. "power_source"
    question: str       # Human-readable question (German)
    context: str        # Why this matters for synthesis
    options: list[str] = field(default_factory=list)  # Optional choices


@dataclass
class ClarificationResult:
    """Result of one clarification pass."""

    enriched_prompt: str
    answered_questions: list[str]  # "field: answer" strings
    rounds: int


# ---------------------------------------------------------------------------
# IO abstraction
# ---------------------------------------------------------------------------

class ClarificationIO(ABC):
    """Abstract I/O for clarification questions.

    Subclass this for CLI, Web, API-callback, etc.
    """

    @abstractmethod
    def ask(self, questions: list[ClarificationQuestion]) -> list[str]:
        """Present questions to the user and return their answers."""


class CLIClarificationIO(ClarificationIO):
    """CLI implementation using Rich console + stdin input()."""

    def __init__(self, console: Any = None) -> None:
        if console is None:
            from rich.console import Console
            console = Console()
        self._console = console

    def ask(self, questions: list[ClarificationQuestion]) -> list[str]:
        from rich.panel import Panel

        self._console.print()
        self._console.print(Panel.fit(
            f"[bold yellow]Klärung erforderlich — {len(questions)} Frage(n)[/]\n"
            "[dim]Beantworte kurz, damit die Synthese optimal läuft.[/]",
            border_style="yellow",
        ))

        answers: list[str] = []
        for i, q in enumerate(questions, 1):
            self._console.print(f"\n[bold]{i}. {q.question}[/]")
            if q.context:
                self._console.print(f"   [dim]{q.context}[/]")
            if q.options:
                for j, opt in enumerate(q.options, 1):
                    self._console.print(f"   [cyan]{j}.[/] {opt}")
                self._console.print("   [dim](Zahl oder freier Text)[/]")
            else:
                self._console.print("   [dim]Antwort:[/]")

            try:
                raw = input("   > ").strip()
            except (EOFError, KeyboardInterrupt):
                raw = ""

            # Resolve numeric input to option text
            if q.options and raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(q.options):
                    raw = q.options[idx]

            answers.append(raw)

        self._console.print()
        return answers


class SilentClarificationIO(ClarificationIO):
    """No-op IO — always returns empty answers.  Used when mode=NONE."""

    def ask(self, questions: list[ClarificationQuestion]) -> list[str]:
        return ["" for _ in questions]


# ---------------------------------------------------------------------------
# RequirementsClarificationAgent
# ---------------------------------------------------------------------------

_REQUIREMENTS_SYSTEM_PROMPT = """\
Du bist ein Hardware-Anforderungsanalyst für das Boardsmith-System.

Analysiere den folgenden Hardware-Prompt und identifiziere kritische Lücken,
die VOR der Synthese geklärt werden müssen.

Frage NUR nach Informationen, die:
1. Direkt die Bauteilauswahl oder Topologie beeinflussen
2. NICHT bereits im Prompt spezifiziert sind
3. Keinen sicheren Default haben (z.B. RF-Band beeinflusst Hardwarekonfiguration)

Felder mit hohem Impact (priorisiere diese):
- power_source: USB / LiPo / AA-Batterien / Netzteil → LDO-Auswahl, Quiescent-Strom
- rf_band: 868 MHz (EU) / 915 MHz (US) → LoRa/RF Hardware-Konfiguration
- environment: Indoor / Outdoor (IP-Rating?) → Temperaturbereich, Schutzklasse
- budget_usd: < $20 / $20-$50 / > $50 → Bauteilqualität, Alternativen

Antworte ausschließlich im JSON-Format:
{
  "questions": [
    {
      "field": "power_source",
      "question": "Welche Stromversorgung ist geplant?",
      "context": "Beeinflusst LDO-Auswahl — bei Batterie ist Quiescent-Strom kritisch",
      "options": ["USB (5V)", "LiPo Batterie (3.7V)", "3x AA (4.5V)", "Netzteil (12V)"]
    }
  ],
  "confidence": 0.4,
  "clear_enough": false
}

Wenn der Prompt bereits ausreichend klar ist: {"questions": [], "confidence": 0.9, "clear_enough": true}

Maximum 3 Fragen. Keine Fragen zu MCU-Typ, Sensor-Varianten oder Pin-Details —
das löst die Synthese selbst.
"""


class RequirementsClarificationAgent:
    """Clarifies ambiguous hardware prompts before B1 runs.

    Calls the LLM to identify high-impact gaps, asks the user via IO,
    then injects the answers back into the prompt as structured context.
    """

    MAX_AUTO_ROUNDS = 3
    CONFIDENCE_THRESHOLD = 0.80

    def __init__(
        self,
        mode: ClarificationMode,
        io: ClarificationIO,
        llm_gateway: Any = None,
    ) -> None:
        self.mode = mode
        self.io = io
        self._llm = llm_gateway

    async def clarify(self, prompt: str) -> tuple[str, list[str]]:
        """Return (enriched_prompt, list_of_answered_qa_strings).

        enriched_prompt is the original prompt with a "Präzisierungen:" block
        appended containing the user's answers.
        """
        if self.mode == ClarificationMode.NONE or self._llm is None:
            return prompt, []

        max_rounds = 1 if self.mode == ClarificationMode.SINGLE else self.MAX_AUTO_ROUNDS
        current_prompt = prompt
        all_answered: list[str] = []

        for _ in range(max_rounds):
            questions = await self._generate_questions(current_prompt)
            if not questions:
                break

            answers = self.io.ask(questions)
            pairs = [
                f"{q.field}: {a}"
                for q, a in zip(questions, answers)
                if a.strip()
            ]
            all_answered.extend(pairs)
            current_prompt = self._inject_answers(current_prompt, questions, answers)

            if self.mode == ClarificationMode.SINGLE:
                break

            # AUTO mode: re-check confidence
            if await self._check_clear(current_prompt):
                break

        return current_prompt, all_answered

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _generate_questions(
        self, prompt: str
    ) -> list[ClarificationQuestion]:
        """Ask LLM to identify clarification gaps; return question list."""
        try:
            from llm.types import Message, TaskType

            response = await self._llm.complete(
                task=TaskType.CLARIFICATION,
                messages=[Message(role="user", content=prompt)],
                system=_REQUIREMENTS_SYSTEM_PROMPT,
                max_tokens=512,
            )

            if response.skipped or not response.content.strip():
                return []

            data = _parse_json_response(response.content)
            if data.get("clear_enough", True):
                return []

            questions = []
            for q in data.get("questions", [])[:3]:
                questions.append(ClarificationQuestion(
                    field=q.get("field", "unknown"),
                    question=q.get("question", ""),
                    context=q.get("context", ""),
                    options=q.get("options", []),
                ))
            return questions

        except Exception as exc:
            log.debug("RequirementsClarificationAgent LLM call failed: %s", exc)
            return []

    async def _check_clear(self, prompt: str) -> bool:
        """Return True if the prompt is now considered sufficiently clear."""
        try:
            from llm.types import Message, TaskType

            response = await self._llm.complete(
                task=TaskType.CLARIFICATION,
                messages=[Message(role="user", content=prompt)],
                system=_REQUIREMENTS_SYSTEM_PROMPT,
                max_tokens=256,
            )
            if response.skipped:
                return True
            data = _parse_json_response(response.content)
            confidence = data.get("confidence", 0.5)
            return bool(data.get("clear_enough", False)) or confidence >= self.CONFIDENCE_THRESHOLD
        except Exception:
            return True  # Fail-safe: don't loop endlessly

    @staticmethod
    def _inject_answers(
        prompt: str,
        questions: list[ClarificationQuestion],
        answers: list[str],
    ) -> str:
        """Append answered questions as structured context to the prompt."""
        lines = ["\n\nPräzisierungen (vom Nutzer bestätigt):"]
        for q, a in zip(questions, answers):
            if a.strip():
                lines.append(f"- {q.question.rstrip('?')}: {a}")
        if len(lines) == 1:
            return prompt  # No answers given
        return prompt + "\n".join(lines)


# ---------------------------------------------------------------------------
# ComponentChallengeAgent
# ---------------------------------------------------------------------------

# LDOs where quiescent current is high enough to matter for battery designs.
# quiescent_ma: approximate worst-case Iq in mA
_BATTERY_HOSTILE_LDOS: dict[str, float] = {
    "AMS1117": 5.0,   # 5 mA typical Iq
    "LM1117": 5.0,
    "LM7805": 8.0,
    "LM7833": 5.0,
}

# Known cheaper alternatives for common sensors.
# Maps MPN → (alternative_mpn, alt_cost_usd, note)
_SENSOR_ALTERNATIVES: dict[str, tuple[str, float, str]] = {
    "SCD41": ("SCD40", 12.00, "±40 ppm statt ±30 ppm CO₂-Genauigkeit"),
    "BME680": ("BME280", 3.50, "Kein VOC-Sensor, dafür deutlich günstiger"),
    "SHTC3": ("AHT20", 1.20, "Sehr ähnliche Genauigkeit"),
}

# RF components that require a specific frequency band configuration.
_RF_COMPONENTS: set[str] = {"SX1276", "SX1278", "RFM95W", "RFM96W", "SX1261", "SX1262"}

# 26.5 — Known 5V-logic components that will trigger automatic level-shifter
# insertion in B4 when combined with a 3.3V MCU (ESP32, STM32, RP2040, nRF52).
# vdd_min_v: minimum supply voltage required (> 3.6V → 5V component)
_FIVE_VOLT_COMPONENTS: dict[str, float] = {
    "HC-SR04":   4.5,   # Ultrasonic distance — 5V trigger/echo
    "HD44780":   4.5,   # LCD controller — 5V data lines
    "ULN2003":   5.0,   # Darlington array — 5V input threshold
    "L298N":     5.0,   # H-Bridge — 5V logic
    "MAX232":    5.0,   # RS-232 transceiver
    "MCP23017":  1.8,   # GPIO expander — actually 1.8–5.5V (OK with 3.3V)
}

# MCU families that run at 3.3V (potential mismatch with 5V sensors)
_LOW_VOLTAGE_MCU_FAMILIES: set[str] = {
    "ESP32", "ESP32S3", "ESP32C3", "STM32", "RP2040", "NRF52", "SAMD21"
}


class ComponentChallengeAgent:
    """Challenges B3 component choices when genuine trade-offs exist.

    Runs after ComponentSelector (B3), before TopologySynthesizer (B4).
    Uses deterministic heuristics — no LLM needed for issue detection.
    Questions are only generated when there is a real, actionable trade-off.
    """

    def __init__(
        self,
        mode: ClarificationMode,
        io: ClarificationIO,
    ) -> None:
        self.mode = mode
        self.io = io

    def challenge(
        self,
        selection: Any,   # ComponentSelection
        reqs: Any,        # NormalizedRequirements
    ) -> Any:
        """Return (potentially updated) ComponentSelection.

        Asks the user about:
          1. RF band if an RF component was selected without a region
          2. Battery-hostile LDOs if power source is unknown or battery
          3. Significantly cheaper sensor alternatives
        """
        if self.mode == ClarificationMode.NONE:
            return selection

        questions = self._build_questions(selection, reqs)
        if not questions:
            return selection

        answers = self.io.ask(questions)
        return self._apply_answers(selection, reqs, questions, answers)

    # ------------------------------------------------------------------
    # Internal: question generation
    # ------------------------------------------------------------------

    def _build_questions(
        self, selection: Any, reqs: Any
    ) -> list[ClarificationQuestion]:
        questions: list[ClarificationQuestion] = []

        # 1. RF band check
        rf_q = self._check_rf_band(selection, reqs)
        if rf_q:
            questions.append(rf_q)

        # 2. Battery-hostile LDO check
        ldo_q = self._check_battery_ldo(selection, reqs)
        if ldo_q:
            questions.append(ldo_q)

        # 3. Sensor cost alternatives
        cost_q = self._check_sensor_cost(selection, reqs)
        if cost_q:
            questions.append(cost_q)

        # 4. 26.5 — Level-shifter voltage mismatch (proactive, before B4 auto-inserts)
        ls_q = self._check_voltage_mismatch(selection, reqs)
        if ls_q:
            questions.append(ls_q)

        return questions[:3]  # never more than 3

    def _check_rf_band(
        self, selection: Any, reqs: Any
    ) -> ClarificationQuestion | None:
        """Ask about LoRa/RF band if not specified."""
        all_components = [selection.mcu] + list(selection.sensors) if selection.mcu else list(selection.sensors)
        rf_found = any(
            getattr(c, "mpn", "").upper() in _RF_COMPONENTS or
            any(rf in getattr(c, "mpn", "").upper() for rf in ("LORA", "SX12", "RFM9"))
            for c in all_components if c is not None
        )
        if not rf_found:
            return None

        # Check if band is already known from reqs
        raw = getattr(reqs, "raw", None)
        if raw and getattr(raw, "rf_band", None):
            return None

        return ClarificationQuestion(
            field="rf_band",
            question="In welcher Region wird das Gerät eingesetzt?",
            context="Bestimmt die LoRa-Frequenz — falsche Konfiguration ist gesetzlich unzulässig",
            options=["Europa (868 MHz)", "USA/Kanada (915 MHz)", "Asien (923 MHz)", "Ich konfiguriere selbst"],
        )

    def _check_battery_ldo(
        self, selection: Any, reqs: Any
    ) -> ClarificationQuestion | None:
        """Ask about battery if a high-quiescent LDO was selected."""
        all_components = [selection.mcu] + list(selection.sensors) if selection.mcu else list(selection.sensors)
        hostile_ldo: str | None = None
        hostile_iq: float = 0.0

        for comp in all_components:
            if comp is None:
                continue
            mpn = getattr(comp, "mpn", "").upper()
            for ldo_mpn, iq in _BATTERY_HOSTILE_LDOS.items():
                if ldo_mpn in mpn:
                    hostile_ldo = ldo_mpn
                    hostile_iq = iq
                    break

        if not hostile_ldo:
            return None

        # Check if power source is already known from reqs
        raw = getattr(reqs, "raw", None)
        if raw:
            power_src = getattr(raw, "power_source", None)
            if power_src and "usb" in str(power_src).lower():
                return None  # USB → high Iq is fine

        return ClarificationQuestion(
            field="power_source",
            question="Wird das Gerät über eine Batterie betrieben?",
            context=(
                f"{hostile_ldo} hat {hostile_iq:.0f} mA Ruhestrom — bei Batteriebetrieb "
                f"empfiehlt sich AP2112K (55 µA). Bei USB/Netzteil ist {hostile_ldo} OK."
            ),
            options=[
                "Ja, Batterie/Akku (Laufzeit wichtig)",
                "Nein, USB oder Netzteil",
                "Beides (Batterie + USB-Laden)",
            ],
        )

    def _check_sensor_cost(
        self, selection: Any, reqs: Any
    ) -> ClarificationQuestion | None:
        """Ask if a cheaper sensor alternative is acceptable."""
        for sensor in getattr(selection, "sensors", []):
            if sensor is None:
                continue
            mpn = getattr(sensor, "mpn", "")
            if mpn not in _SENSOR_ALTERNATIVES:
                continue

            current_cost = getattr(sensor, "unit_cost_usd", 0.0) or 0.0
            alt_mpn, alt_cost, alt_note = _SENSOR_ALTERNATIVES[mpn]

            if current_cost <= 0:
                continue
            savings_pct = (current_cost - alt_cost) / current_cost
            if savings_pct < 0.20:
                continue  # Less than 20% cheaper → not worth asking

            return ClarificationQuestion(
                field="sensor_cost",
                question=f"Soll {mpn} (${current_cost:.2f}) durch {alt_mpn} (${alt_cost:.2f}) ersetzt werden?",
                context=f"${current_cost - alt_cost:.2f} günstiger (-{savings_pct:.0%}). Unterschied: {alt_note}",
                options=[
                    f"Nein, {mpn} beibehalten (höhere Genauigkeit)",
                    f"Ja, {alt_mpn} verwenden (kostenoptimiert)",
                ],
            )

        return None

    def _check_voltage_mismatch(
        self, selection: Any, reqs: Any
    ) -> ClarificationQuestion | None:
        """26.5 — Proactively warn about 5V components with 3.3V MCU.

        B4 will auto-insert a level-shifter, but direction (uni/bidirectional)
        and pull-up configuration are not trivially determined.  Asking the
        user upfront lets them confirm or override the auto-selection.
        """
        mcu = getattr(selection, "mcu", None)
        if mcu is None:
            return None

        # Check if MCU is a known 3.3V family
        mcu_mpn_upper = getattr(mcu, "mpn", "").upper()
        is_3v3_mcu = any(fam in mcu_mpn_upper for fam in _LOW_VOLTAGE_MCU_FAMILIES)
        if not is_3v3_mcu:
            return None

        # Look for known 5V-only sensors in the selection
        mismatched: list[str] = []
        for sensor in getattr(selection, "sensors", []):
            if sensor is None:
                continue
            mpn = getattr(sensor, "mpn", "")
            mpn_upper = mpn.upper()

            # Check against known 5V components list
            for known_mpn, vdd_min in _FIVE_VOLT_COMPONENTS.items():
                if known_mpn.upper() in mpn_upper and vdd_min > 3.6:
                    mismatched.append(mpn)
                    break

            # Also check electrical_ratings if available
            if not mismatched or mpn not in mismatched:
                ratings = getattr(sensor, "electrical_ratings", {}) or {}
                vdd_min_rated = ratings.get("vdd_min", 0)
                if isinstance(vdd_min_rated, (int, float)) and vdd_min_rated > 3.6:
                    mismatched.append(mpn)

        if not mismatched:
            return None

        components_str = ", ".join(mismatched[:3])
        return ClarificationQuestion(
            field="level_shifter_direction",
            question=(
                f"Spannungsmismatch erkannt: {components_str} (5V) + {mcu.mpn} (3.3V). "
                f"B4 fügt automatisch Level-Shifter ein. Welche Richtung?"
            ),
            context=(
                "Bidirektional (TXB0104/BSS138+Pullup) für I2C/Bidirektionale Signale. "
                "Unidirektional (74LVC) für reine Output-Signale. "
                "Falsche Wahl kann zu Lock-Up oder Kommunikationsfehlern führen."
            ),
            options=[
                "Bidirektional (I2C, SPI MISO/MOSI — sicherer Default)",
                "Unidirektional Output (MCU→Sensor, z.B. UART TX, PWM)",
                "Unidirektional Input (Sensor→MCU, z.B. UART RX)",
                "Automatisch entscheiden lassen (B4 wählt je Interface)",
            ],
        )

    # ------------------------------------------------------------------
    # Internal: answer application
    # ------------------------------------------------------------------

    def _apply_answers(
        self,
        selection: Any,
        reqs: Any,
        questions: list[ClarificationQuestion],
        answers: list[str],
    ) -> Any:
        """Apply user answers to the ComponentSelection.

        Modifies selection.assumptions to record decisions.
        For sensor swaps, replaces the sensor in-place if the user agreed.
        """
        for q, answer in zip(questions, answers):
            if not answer.strip():
                continue

            if q.field == "rf_band":
                _record_assumption(selection, f"RF-Band: {answer}")

            elif q.field == "power_source":
                _record_assumption(selection, f"Stromversorgung: {answer}")
                # Suggest LDO swap via assumption (DesignImprover will fix later)
                if "batterie" in answer.lower() or "akku" in answer.lower():
                    _record_assumption(
                        selection,
                        "Battery-Betrieb bestätigt — AMS1117 → AP2112K empfohlen (DesignImprover)",
                    )

            elif q.field == "sensor_cost":
                if answer and (answer.startswith("Ja") or "ja" in answer.lower()):
                    _swap_sensor(selection, reqs, answer)

            elif q.field == "level_shifter_direction":
                # 26.5 — Record level-shifter direction choice for B4
                _record_assumption(selection, f"Level-Shifter-Richtung (Nutzer): {answer}")
                if "bidirektional" in answer.lower() or "i2c" in answer.lower():
                    _record_assumption(selection, "Level-Shifter: bidirektional — TXB0104 oder BSS138+Pullup")
                elif "output" in answer.lower() and "unidirektional" in answer.lower():
                    _record_assumption(selection, "Level-Shifter: unidirektional Output — 74LVC1T45 oder ähnlich")
                elif "input" in answer.lower() and "unidirektional" in answer.lower():
                    _record_assumption(selection, "Level-Shifter: unidirektional Input — Spannungsteiler oder 74LVC1T45")
                else:
                    _record_assumption(selection, "Level-Shifter: automatisch (B4 wählt je Interface)")

        return selection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record_assumption(selection: Any, assumption: str) -> None:
    assumptions = getattr(selection, "assumptions", None)
    if isinstance(assumptions, list):
        assumptions.append(assumption)


def _swap_sensor(selection: Any, reqs: Any, answer: str) -> None:
    """Attempt to swap a sensor for its cheaper alternative."""
    for i, sensor in enumerate(getattr(selection, "sensors", [])):
        if sensor is None:
            continue
        mpn = getattr(sensor, "mpn", "")
        if mpn in _SENSOR_ALTERNATIVES:
            _, alt_cost, _ = _SENSOR_ALTERNATIVES[mpn]
            # Simple swap: update cost + MPN on the same object
            # (full re-select would require KnowledgeAgent — keep it lightweight)
            try:
                alt_mpn = _SENSOR_ALTERNATIVES[mpn][0]
                sensor.mpn = alt_mpn
                sensor.unit_cost_usd = alt_cost
                _record_assumption(
                    selection,
                    f"Bauteil-Tausch durch Nutzer bestätigt: {mpn} → {alt_mpn}",
                )
                log.info("ComponentChallengeAgent: swapped %s → %s", mpn, alt_mpn)
            except AttributeError:
                pass  # Frozen dataclass or unexpected type — skip silently


def _parse_json_response(content: str) -> dict:
    """Extract JSON from LLM response, stripping markdown code fences."""
    text = content.strip()
    # Strip ```json ... ``` fences
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return {"questions": [], "clear_enough": True, "confidence": 0.9}
