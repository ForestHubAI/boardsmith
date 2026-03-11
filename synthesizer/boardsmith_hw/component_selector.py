# SPDX-License-Identifier: AGPL-3.0-or-later
"""B3. Component Selector — selects best-fit components from the knowledge catalog.

Resolution strategy (agent-first):
  1. Builtin DB match (exact MPN or modality mapping) — instant
  2. Knowledge Agent (download + extract) — for unknown MPNs/modalities
  3. Fallback: best-scored component from catalog
"""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any

from synth_core.api.compiler import list_components
from boardsmith_hw.requirements_normalizer import NormalizedRequirements

log = logging.getLogger(__name__)


@dataclass
class SelectedComponent:
    mpn: str
    manufacturer: str
    name: str
    category: str
    interface_types: list[str]
    role: str                   # "mcu" or sensing modality label
    known_i2c_addresses: list[str]
    init_contract_coverage: bool
    unit_cost_usd: float
    score: float
    raw: dict[str, Any]
    instance_idx: int = 0       # 0 = first instance; ≥1 = duplicate (same MPN, different comp_id)


@dataclass
class ComponentSelection:
    mcu: SelectedComponent | None
    sensors: list[SelectedComponent] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    confidence: float = 0.8
    label: str = "preferred"   # "preferred" | "alternative" | "cost-optimized"


# Mapping from sensing modality → preferred component categories / keywords
_MODALITY_SENSORS: dict[str, list[str]] = {
    "temperature": ["BME280", "AHT20"],
    "humidity": ["BME280", "AHT20"],
    "pressure": ["BME280"],
    "motion": ["ICM-42688-P", "MPU-6050"],
    "imu": ["ICM-42688-P", "MPU-6050"],
    "distance": ["HC-SR04", "VL53L0X"],
    "light": [],
    "gas": [],
    "adc": ["ADS8681", "ADS1115"],   # 16-bit SPI ADC preferred; I2C fallback
    "current": ["INA226", "ACS712ELCTR-20A-T"],
    "voltage": ["INA226"],
    "gps": ["NEO-M8N", "NEO-6M"],
    "co2": ["SCD41"],
    "thermocouple": ["MAX6675ISA+"],
    "rtd": ["MAX31865ATP+"],
    "hall": ["TLE4913"],
    "encoder": ["AS5600-ASOM"],
    "audio": ["MAX98357A", "WM8731"],   # Class-D amp or full codec
    "ethernet": ["LAN8720A"],          # Ethernet PHY
    "lte": ["SIM7600G-H"],             # LTE/cellular module
    "cellular": ["SIM7600G-H"],
    "can": ["TCAN1042VDRQ1"],            # Non-isolated CAN transceiver
    "isolated_can": ["ISO1042BQDWRQ1"],  # Isolated CAN transceiver for galvanic isolation
    "battery_charger": ["TP4056"],       # Li-Ion/LiPo battery charger IC
    "fuel_gauge": ["MAX17043"],          # Li-Ion/LiPo battery fuel gauge / SOC monitor
    "solar": ["SPV1040", "BQ24650"],     # MPPT boost converter + solar battery charger
}

# Mapping from actuation modality → preferred MPNs
_MODALITY_ACTUATORS: dict[str, list[str]] = {
    "led": ["LTST-C150GKT"],
    "button": ["SKRPACE010"],
    "transistor": ["2N2222A"],
    "mosfet": ["IRLZ44N", "AO3400A"],
    "motor": ["TB6612FNG", "DRV8833"],
    "h-bridge": ["TB6612FNG", "DRV8833"],
    "relay": ["ULN2003A"],
    "optocoupler": ["TLP281-4"],
    "buzzer": [],
    "display": ["SSD1306"],            # already handled as sensing
    "spi-flash": ["W25Q128"],          # SPI NOR Flash chip (W25Q128JV)
    "microsd": ["MICROSD-SLOT-SPI"],   # MicroSD card slot
    "flash": ["MICROSD-SLOT-SPI"],     # Generic fallback for "flash" / "storage"
    "communication": [],               # transceivers handled via sensor_mpns
    "power": [],                       # handled by topology voltage regulator synthesis
    "levelshifter": ["TXB0104"],       # level shifter for mixed-voltage GPIO
    # Battery management (LLM may put these in actuation_modalities)
    "battery_charger": ["TP4056"],     # Li-Ion/LiPo USB charger IC
    "charger": ["TP4056"],             # alias for battery_charger
    "charging": ["TP4056"],            # German: Ladefunktion
    "fuel_gauge": ["MAX17043"],        # Li-Ion/LiPo fuel gauge (State of Charge)
    "ladesteuerung": ["TP4056"],       # German: charger control
    "power_path": ["TP4056"],          # power path management (TP4056 has built-in)
}

# Mapping from analog circuit keyword → preferred component MPN
# Used for no-LLM path; the LLM path can override via sensor_mpns.
# Keys are lower-case substrings that trigger analog component selection.
_MODALITY_ANALOG: dict[str, str] = {
    # Op-amps (MCP6002 preferred for 3.3V rail-to-rail systems)
    "amplifier":          "MCP6002",
    "verstärker":         "MCP6002",
    "op-amp":             "MCP6002",
    "opamp":              "MCP6002",
    "op amp":             "MCP6002",
    "signal conditioning":"MCP6002",
    "signalaufbereitung": "MCP6002",
    "voltage follower":   "MCP6002",
    "spannungsfolger":    "MCP6002",
    "follower":           "MCP6002",
    "buffer amplifier":   "MCP6002",
    "puffer":             "MCP6002",
    "unity gain":         "MCP6002",
    # Comparators
    "comparator":         "LM393",
    "komparator":         "LM393",
    "zero-crossing":      "LM393",
    "nulldurchgang":      "LM393",
    "schmitt":            "LM393",
    "hysteresis":         "LM393",
    "hysterese":          "LM393",
    "threshold detector": "LM393",
    "schwellwertschalter":"LM393",
    "level detector":     "LM393",
    # Voltage references
    "voltage reference":  "LM4040",
    "spannungsreferenz":  "LM4040",
    "vref":               "LM4040",
    "adc reference":      "LM4040",
    "referenz":           "LM4040",
}

# UART connector MPN — added to BOM when UART is in required_interfaces
_UART_CONNECTOR_MPN = "CONN-UART-4PIN"
# CAN/RS485 connector MPNs — added when CAN/RS485 is in required_interfaces
_CAN_CONNECTOR_MPN = "CONN-CAN-2PIN"
_RS485_CONNECTOR_MPN = "CONN-RS485-2PIN"


def _mpn_matches(catalog_mpn: str, requested_mpn: str) -> bool:
    """Check if a catalog MPN matches a requested MPN.

    Handles exact matches and common variant suffixes (e.g. W25Q128 → W25Q128JV).
    Also normalises known dash/space variations.
    """
    def _norm(s: str) -> str:
        return s.upper().replace("-", "").replace(" ", "").replace("_", "")

    cat = _norm(catalog_mpn)
    req = _norm(requested_mpn)
    # Apply known normalizations (legacy compat)
    req = req.replace("MPU6050", "MPU6050").replace("ICM42688P", "ICM42688P")
    # Exact match
    if cat == req:
        return True
    # Prefix match: catalog variant (e.g. W25Q128JV) starts with requested base (e.g. W25Q128)
    # Allow suffix of ≤6 chars to cover package/variant codes (e.g. TCAN1042VDRQ1, ADS1115IDGSR)
    if cat.startswith(req) and len(cat) - len(req) <= 6:
        return True
    # Reverse prefix: requested is more specific than catalog (e.g. requested W25Q128JVSIQ)
    if req.startswith(cat) and len(req) - len(cat) <= 6:
        return True
    return False


def _get_modality_sensors(modality: str) -> list[str]:
    """Get preferred MPNs for a modality — static mapping + dynamic DB lookup.

    Falls back to scanning Builtin-DB tags if the static mapping is empty
    or has no entry for the modality (e.g. 'co2', 'uv', 'color').
    """
    static = _MODALITY_SENSORS.get(modality, [])
    if static:
        return static

    # Dynamic: search Builtin DB for components tagged with this modality
    try:
        from knowledge.components import COMPONENTS
        matches: list[str] = []
        q = modality.lower()
        for entry in COMPONENTS:
            tags = [t.lower() for t in entry.get("tags", [])]
            desc = entry.get("description", "").lower()
            if q in tags or q in desc:
                mpn = entry.get("mpn", "")
                if mpn and mpn not in matches:
                    matches.append(mpn)
        if matches:
            return matches
    except ImportError:
        pass

    return []

_MCU_FAMILY_MPNS: dict[str, list[str]] = {
    "esp32":   ["ESP32-WROOM-32"],
    "esp32c3": ["ESP32-C3-WROOM-02"],
    "esp32s3": ["ESP32-S3-WROOM-1"],
    "stm32":   ["STM32F103C8T6"],
    "stm32f4": ["STM32F405RGT6"],
    "stm32h7": ["STM32H743VIT6"],
    "stm32g4": ["STM32G431CBU6"],
    "stm32l4": ["STM32L476RGT6"],
    "stm32f7": ["STM32F746ZGT6"],
    "imxrt":   ["MIMXRT1062DVJ6A"],
    "lpc55":   ["LPC55S69JBD100"],
    "renesas": ["R7FA4M2AD3CFP"],
    "same51":  ["ATSAME51J20A-AU"],
    "xmc":     ["XMC4700F144K2048"],
    "arduino": ["ATmega328P-AU", "ATmega328P"],
    "mega":    ["ATmega2560-16AU", "ATmega2560"],
    "atmega":  ["ATmega328P-AU", "ATmega328P"],
    "rp2040":  ["RP2040"],
    "nrf52":   ["nRF52840"],
}


def _score_component(entry: dict, reqs: NormalizedRequirements) -> float:
    """Heuristic score (0-1) for a candidate component given requirements."""
    score = 0.5
    ratings = entry.get("electrical_ratings", {})

    # Voltage compatibility
    v_min, v_max = reqs.supply_voltage_range
    comp_vdd_min = ratings.get("vdd_min", 0)
    comp_vdd_max = ratings.get("vdd_max", 99)
    if comp_vdd_min <= v_max and comp_vdd_max >= v_min:
        score += 0.2

    # Temperature compatibility
    t_min, t_max = reqs.temperature_range
    comp_t_min = ratings.get("temp_min_c", -999)
    comp_t_max = ratings.get("temp_max_c", 999)
    if comp_t_min <= t_min and comp_t_max >= t_max:
        score += 0.1

    # Cost
    if reqs.max_cost_usd:
        cost = entry.get("unit_cost_usd", 0)
        if cost <= reqs.max_cost_usd:
            score += 0.1
    else:
        score += 0.05

    # Init contract
    if entry.get("init_contract_coverage"):
        score += 0.1

    return min(1.0, score)


def _agent_find_sync(query: str) -> dict | None:
    """Synchronous wrapper to call Knowledge Agent from sync context."""
    try:
        from agents.knowledge_agent import KnowledgeAgent

        async def _run():
            agent = KnowledgeAgent()
            result = await agent.find(query)
            return result

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_run())
        finally:
            loop.close()

        if result is None:
            return None
        return {
            "mpn": result.mpn,
            "manufacturer": result.manufacturer,
            "name": result.name,
            "category": result.category,
            "interface_types": result.interface_types,
            "electrical_ratings": result.electrical_ratings,
            "known_i2c_addresses": result.known_i2c_addresses,
            "unit_cost_usd": result.unit_cost_usd,
            "tags": result.tags,
            "init_contract_coverage": False,
            "_agent_confidence": result.confidence,
            "_agent_source": result.source,
        }
    except Exception as e:
        log.debug("Knowledge Agent unavailable: %s", e)
        return None


class ComponentSelector:
    """Selects MCU + peripheral components to fulfill requirements."""

    def __init__(self, seed: int | None = None, use_agent: bool = True) -> None:
        self._rng = random.Random(seed)
        self._use_agent = use_agent

    def select(self, reqs: NormalizedRequirements) -> ComponentSelection:
        assumptions: list[str] = list(reqs.unresolved)
        confidence_factors: list[float] = []

        # --- MCU selection ---
        mcu = self._select_mcu(reqs)
        if mcu is None:
            # fallback
            all_mcus = list_components(category="mcu")
            if all_mcus:
                mcu = self._to_selected(all_mcus[0], "mcu", _score_component(all_mcus[0], reqs))
                assumptions.append(f"No MCU matched family '{reqs.mcu_family}'; defaulted to {mcu.mpn}")
            else:
                assumptions.append("No MCU found in knowledge base — cannot proceed")
                return ComponentSelection(mcu=None, assumptions=assumptions, confidence=0.0)

        confidence_factors.append(mcu.score)

        # --- Peripheral / sensor selection ---
        sensors: list[SelectedComponent] = []
        selected_mpns: set[str] = set()

        # Priority 1: explicit MPNs from prompt (e.g. "BME280", "MPU-6050")
        all_catalog = list_components()
        for mpn in reqs.sensor_mpns:
            match = next(
                (c for c in all_catalog if _mpn_matches(c.get("mpn", ""), mpn)),
                None,
            )
            if match and match.get("mpn") not in selected_mpns:
                sc = self._to_selected(match, match.get("category", "sensor"), _score_component(match, reqs))
                sensors.append(sc)
                selected_mpns.add(match.get("mpn", ""))
                confidence_factors.append(sc.score)
            elif match and match.get("mpn") in selected_mpns:
                # Duplicate MPN requested — note the I2C address conflict if applicable
                dup_mpn = match.get("mpn", mpn)
                i2c_addrs = match.get("known_i2c_addresses", [])
                count = reqs.sensor_mpns.count(mpn)
                if i2c_addrs:
                    addr_str = ", ".join(f"0x{a:02X}" if isinstance(a, int) else str(a) for a in i2c_addrs[:2])
                    assumptions.append(
                        f"Duplicate {dup_mpn} requested ×{count}: I2C address conflict "
                        f"(default {addr_str}). Use ADDR/SDO pin to select alternate address "
                        f"(e.g. ADDR=GND→0x76, ADDR=VCC→0x77)."
                    )
                else:
                    assumptions.append(
                        f"Duplicate {dup_mpn} requested ×{count}: only one instance placed in BOM. "
                        f"Check address/CS pin configuration for multiple devices."
                    )
            elif not match:
                # Agent fallback: try to find the unknown MPN dynamically
                if self._use_agent:
                    log.info("B3: MPN '%s' not in catalog — calling Knowledge Agent", mpn)
                    agent_entry = _agent_find_sync(mpn)
                    if agent_entry and agent_entry.get("mpn") not in selected_mpns:
                        sc = self._to_selected(agent_entry, agent_entry.get("category", "sensor"), _score_component(agent_entry, reqs))
                        sensors.append(sc)
                        selected_mpns.add(agent_entry.get("mpn", mpn))
                        confidence_factors.append(sc.score * agent_entry.get("_agent_confidence", 0.7))
                        assumptions.append(f"MPN '{mpn}' resolved via Knowledge Agent (source: {agent_entry.get('_agent_source', 'agent')})")
                    else:
                        assumptions.append(f"Explicit MPN '{mpn}' not found in catalog or agent; skipping")
                        confidence_factors.append(0.3)
                else:
                    assumptions.append(f"Explicit MPN '{mpn}' not found in catalog; skipping")
                    confidence_factors.append(0.3)

        # --- Duplicate MPN raw-prompt scan ---
        # The LLM often deduplicates sensor_mpns (returns ['BME280'] not ['BME280','BME280']).
        # Detect "MPN + MPN", "2x MPN", "2× MPN", "zwei MPN", "two MPN" patterns in the raw prompt
        # and add an I2C address conflict assumption note if found.
        import re as _re
        _raw_prompt_lower = getattr(getattr(reqs, "raw", None), "raw_prompt", "").lower()
        if _raw_prompt_lower:
            for _sel_mpn in list(selected_mpns):
                _m = _sel_mpn.lower()
                _dup_detected = bool(
                    _re.search(rf"\b{_re.escape(_m)}\s*[+&]\s*{_re.escape(_m)}\b", _raw_prompt_lower)
                    or _re.search(rf"2\s*[x×]\s*{_re.escape(_m)}\b", _raw_prompt_lower)
                    or _re.search(rf"\b(zwei|two|dual)\s+{_re.escape(_m)}\b", _raw_prompt_lower)
                    or _re.search(rf"\b2\s+{_re.escape(_m)}\b", _raw_prompt_lower)
                )
                if _dup_detected and not any(_sel_mpn in a and "address conflict" in a for a in assumptions):
                    _entry = next((c for c in all_catalog if _mpn_matches(c.get("mpn", ""), _sel_mpn)), None)
                    if _entry:
                        _i2c = _entry.get("known_i2c_addresses", [])
                        if _i2c:
                            _addr_str = ", ".join(
                                f"0x{a:02X}" if isinstance(a, int) else str(a) for a in _i2c[:2]
                            )
                            assumptions.append(
                                f"Duplicate {_sel_mpn} requested ×2: I2C address conflict "
                                f"(default {_addr_str}). Use ADDR/SDO pin to select alternate address "
                                f"(e.g. ADDR=GND→0x76, ADDR=VCC→0x77). Only one instance placed in BOM."
                            )
                        else:
                            assumptions.append(
                                f"Duplicate {_sel_mpn} requested ×2: only one instance placed in BOM. "
                                f"Check address/CS pin configuration for multiple devices."
                            )

        # Priority 2: modality-based selection (only for modalities not yet covered)
        # Build a set of words covered by explicit sensor_mpns (Priority 1) — tags + description words
        # This prevents double-adding sensors when the user explicitly named their components.
        # e.g. DS18B20 tags include "temperature" → skip "temperature" modality
        # e.g. AS5600 tags include "rotary","encoder","magnetic" → skip "motion" modality
        _MODALITY_ALIAS: dict[str, list[str]] = {
            "motion":      ["motion", "imu", "accelerometer", "gyroscope", "encoder", "rotary",
                            "magnetic", "angular", "orientation", "position"],
            "temperature": ["temperature", "thermal", "thermometer", "temp"],
            "humidity":    ["humidity", "moisture", "rh"],
            "pressure":    ["pressure", "barometric", "baro"],
            "co2":         ["co2", "co₂", "carbon", "gas", "air_quality"],
            "light":       ["light", "lux", "optical", "photoresistor", "ambient"],
            "distance":    ["distance", "proximity", "ultrasonic", "lidar", "tof", "ranging"],
            "color":       ["color", "colour", "rgb", "spectral"],
            "current":     ["current", "power", "shunt", "ampere", "ina"],
            "display":     ["display", "oled", "lcd", "tft", "screen"],
        }
        _explicit_covered_words: set[str] = set()
        if reqs.sensor_mpns:
            _all_catalog_for_modality = list_components()
            for _explicit_mpn in reqs.sensor_mpns:
                _match = next(
                    (c for c in _all_catalog_for_modality if _mpn_matches(c.get("mpn", ""), _explicit_mpn)),
                    None,
                )
                if _match:
                    for _tag in _match.get("tags", []):
                        _explicit_covered_words.add(_tag.lower())
                    # Also add significant words from the description
                    for _word in _match.get("description", "").lower().split():
                        _clean = _word.strip(".,;:()")
                        if len(_clean) > 3:
                            _explicit_covered_words.add(_clean)

        def _modality_covered_by_explicit(modality: str) -> bool:
            """True if an explicit sensor_mpn already covers this sensing modality."""
            aliases = _MODALITY_ALIAS.get(modality.lower(), [modality.lower()])
            return any(alias in _explicit_covered_words for alias in aliases)

        for modality in reqs.sensing_modalities:
            preferred_mpns = _get_modality_sensors(modality)
            # Skip if a preferred MPN for this modality already selected
            if any(p.upper() in {m.upper() for m in selected_mpns} for p in preferred_mpns):
                continue
            # Skip if an explicit sensor_mpn already covers this modality (by tags or description)
            # e.g. DS18B20 → "temperature", AS5600 → "motion" (rotary encoder)
            if _modality_covered_by_explicit(modality):
                continue
            sensor = self._select_sensor(modality, preferred_mpns, reqs, exclude_mpns=selected_mpns)
            if sensor is None:
                # Agent fallback: search by modality
                if self._use_agent:
                    log.info("B3: No catalog match for modality '%s' — calling Knowledge Agent", modality)
                    agent_entry = _agent_find_sync(f"{modality} sensor")
                    if agent_entry and agent_entry.get("mpn") not in selected_mpns:
                        sc = self._to_selected(agent_entry, modality, _score_component(agent_entry, reqs))
                        sensors.append(sc)
                        selected_mpns.add(agent_entry.get("mpn", modality))
                        confidence_factors.append(sc.score * agent_entry.get("_agent_confidence", 0.7))
                        assumptions.append(f"Modality '{modality}' resolved via Knowledge Agent: {agent_entry.get('mpn', '?')}")
                    else:
                        assumptions.append(f"No component found for modality '{modality}'; skipping")
                        confidence_factors.append(0.3)
                else:
                    assumptions.append(f"No component found for modality '{modality}'; skipping")
                    confidence_factors.append(0.3)
            else:
                if sensor.mpn not in selected_mpns:
                    sensors.append(sensor)
                    selected_mpns.add(sensor.mpn)
                    confidence_factors.append(sensor.score)

        if not sensors and reqs.sensing_modalities:
            assumptions.append("No sensors selected; design may be incomplete")

        # Priority 3: actuation modality-based selection (LEDs, buttons, transistors, …)
        for modality in reqs.actuation_modalities:
            preferred_actuator_mpns = _MODALITY_ACTUATORS.get(modality, [])
            if not preferred_actuator_mpns:
                continue
            # Skip if a preferred actuator MPN for this modality is already selected
            if any(p.upper() in {m.upper() for m in selected_mpns} for p in preferred_actuator_mpns):
                continue
            # Skip if any component of the same category as the preferred actuators is already
            # selected (e.g. ST7735 already satisfies "display" modality — don't also add SSD1306)
            _pref_cats = {
                c.get("category", "")
                for pmpn in preferred_actuator_mpns
                for c in all_catalog
                if _mpn_matches(c.get("mpn", ""), pmpn)
            }
            if _pref_cats and any(s.category in _pref_cats for s in sensors):
                continue
            for pmpn in preferred_actuator_mpns:
                act_match = next(
                    (c for c in all_catalog if _mpn_matches(c.get("mpn", ""), pmpn)),
                    None,
                )
                if act_match and act_match.get("mpn") not in selected_mpns:
                    sc = self._to_selected(act_match, modality, _score_component(act_match, reqs))
                    sensors.append(sc)
                    selected_mpns.add(act_match.get("mpn", ""))
                    confidence_factors.append(sc.score)
                    break
            else:
                assumptions.append(f"Actuation modality '{modality}' has no catalog match; skipping")

        # Priority 4: UART connector — add when UART is in required_interfaces and no external UART
        # peripheral (transceiver, level shifter, or connector) is already in sensors.
        # We intentionally exclude the MCU itself (it has built-in UART) so that e.g. "UART Header"
        # prompts still get a physical connector in the BOM.
        ifaces_upper = [i.upper() for i in reqs.required_interfaces]

        if "UART" in ifaces_upper:
            has_uart_comp = any(
                "UART" in [x.upper() for x in c.interface_types]
                for c in sensors   # only check peripherals, not the MCU
            )
            if not has_uart_comp:
                uart_conn = next(
                    (c for c in all_catalog if _mpn_matches(c.get("mpn", ""), _UART_CONNECTOR_MPN)),
                    None,
                )
                if uart_conn and uart_conn.get("mpn") not in selected_mpns:
                    sc = self._to_selected(uart_conn, "connector", _score_component(uart_conn, reqs))
                    sensors.append(sc)
                    selected_mpns.add(uart_conn.get("mpn", ""))
                    confidence_factors.append(sc.score)

        # Priority 4b-pre0: Ethernet PHY — add LAN8720A when Ethernet is in
        # required_interfaces but no Ethernet PHY is already in sensors.
        # Handles LLM-mode prompts where the intent parser puts "Ethernet" in
        # required_interfaces (not sensing_modalities), bypassing Priority 2.
        _ETH_PHY_MPNS = ["LAN8720A", "DP83848I", "KSZ8081RNB"]
        _ETH_KEYWORDS = ("LAN8720", "DP838", "KSZ80", "RTL820", "IP101", "W5500", "LAN87")
        has_eth_phy = any(
            any(_mpn_matches(c.mpn, t) for t in _ETH_PHY_MPNS)
            or any(k in c.mpn.upper() for k in _ETH_KEYWORDS)
            for c in sensors
        )
        _raw_for_eth = getattr(getattr(reqs, "raw", None), "raw_prompt", "").lower()
        _eth_in_raw = "ethernet" in _raw_for_eth or "eth phy" in _raw_for_eth or "phy" in _raw_for_eth
        _eth_in_ifaces = "ETHERNET" in ifaces_upper or "ETH" in ifaces_upper or _eth_in_raw
        if _eth_in_ifaces and not has_eth_phy:
            for _ep_mpn in _ETH_PHY_MPNS:
                _ep_match = next(
                    (c for c in all_catalog if _mpn_matches(c.get("mpn", ""), _ep_mpn)),
                    None,
                )
                if _ep_match and _ep_match.get("mpn") not in selected_mpns:
                    sc = self._to_selected(_ep_match, "comms", _score_component(_ep_match, reqs))
                    sensors.append(sc)
                    selected_mpns.add(_ep_match.get("mpn", ""))
                    confidence_factors.append(sc.score)
                    assumptions.append(
                        f"Ethernet interface requires external PHY: added {_ep_match.get('mpn')}"
                    )
                    break

        # Priority 4b-pre: CAN transceiver IC — add TCAN1042 when CAN/CAN-FD bus is
        # required but no CAN transceiver IC is already in sensors.
        # Mirrors the RS485 transceiver logic (Priority 4c-pre).
        _CAN_TRANSCEIVER_MPNS = ["TCAN1042VDRQ1", "ISO1042BQDWRQ1"]
        has_can_transceiver = any(
            any(_mpn_matches(c.mpn, t) for t in _CAN_TRANSCEIVER_MPNS)
            for c in sensors
        )
        _raw_for_can = getattr(getattr(reqs, "raw", None), "raw_prompt", "").lower()
        _can_in_raw = (
            "can-fd" in _raw_for_can or "canfd" in _raw_for_can
            or "fdcan" in _raw_for_can
            or " can " in _raw_for_can or "can," in _raw_for_can
            or _raw_for_can.startswith("can ")
        )
        _can_in_ifaces = "CAN" in ifaces_upper or _can_in_raw  # covers CAN-FD, CAN, FDCAN
        if _can_in_ifaces and not has_can_transceiver:
            for _ct_mpn in _CAN_TRANSCEIVER_MPNS:
                _ct_match = next(
                    (c for c in all_catalog if _mpn_matches(c.get("mpn", ""), _ct_mpn)),
                    None,
                )
                if _ct_match and _ct_match.get("mpn") not in selected_mpns:
                    sc = self._to_selected(_ct_match, "transceiver", _score_component(_ct_match, reqs))
                    sensors.append(sc)
                    selected_mpns.add(_ct_match.get("mpn", ""))
                    confidence_factors.append(sc.score)
                    assumptions.append(
                        f"CAN-FD interface requires differential transceiver: added {_ct_match.get('mpn')}"
                    )
                    has_can_transceiver = True
                    break

        # Priority 4b: CAN screw terminal — add when CAN bus is required *or* a CAN
        # transceiver is already in sensors (transceiver detected via explicit MPN or priority 4b-pre).
        has_can_in_sensors = any("CAN" in [x.upper() for x in c.interface_types] for c in sensors) or has_can_transceiver
        if "CAN" in ifaces_upper or has_can_in_sensors:
            can_conn = next(
                (c for c in all_catalog if _mpn_matches(c.get("mpn", ""), _CAN_CONNECTOR_MPN)),
                None,
            )
            if can_conn and can_conn.get("mpn") not in selected_mpns:
                sc = self._to_selected(can_conn, "connector", _score_component(can_conn, reqs))
                sensors.append(sc)
                selected_mpns.add(can_conn.get("mpn", ""))
                confidence_factors.append(sc.score)

        # Priority 4c-pre: RS485 transceiver IC — add MAX485 (or SP3485EN) when RS485
        # is required but no transceiver is already in sensors.
        # Also detects RS485 from the raw prompt directly (fallback for when LLM
        # returns UART instead of RS485 in required_interfaces).
        _RS485_TRANSCEIVER_MPNS = ["MAX485", "SP3485EN"]
        has_rs485_transceiver = any(
            any(_mpn_matches(c.mpn, t) for t in _RS485_TRANSCEIVER_MPNS)
            for c in sensors
        )
        _raw_for_rs485 = getattr(getattr(reqs, "raw", None), "raw_prompt", "").lower()
        _rs485_in_prompt = "rs485" in _raw_for_rs485 or "rs-485" in _raw_for_rs485
        _rs485_required = "RS485" in ifaces_upper or _rs485_in_prompt
        if _rs485_required and not has_rs485_transceiver:
            for _t_mpn in _RS485_TRANSCEIVER_MPNS:
                _t_match = next(
                    (c for c in all_catalog if _mpn_matches(c.get("mpn", ""), _t_mpn)),
                    None,
                )
                if _t_match and _t_match.get("mpn") not in selected_mpns:
                    sc = self._to_selected(_t_match, "transceiver", _score_component(_t_match, reqs))
                    sensors.append(sc)
                    selected_mpns.add(_t_match.get("mpn", ""))
                    confidence_factors.append(sc.score)
                    assumptions.append(f"RS485 interface requires differential transceiver: added {_t_match.get('mpn')}")
                    has_rs485_transceiver = True
                    break

        # Priority 4c: RS485 screw terminal — add when RS485 bus is required *or* RS485
        # transceiver is already in sensors (detected via explicit MPN or raw prompt).
        has_rs485_in_sensors = any("RS485" in [x.upper() for x in c.interface_types] for c in sensors) or has_rs485_transceiver
        if "RS485" in ifaces_upper or _rs485_in_prompt or has_rs485_in_sensors:
            rs_conn = next(
                (c for c in all_catalog if _mpn_matches(c.get("mpn", ""), _RS485_CONNECTOR_MPN)),
                None,
            )
            if rs_conn and rs_conn.get("mpn") not in selected_mpns:
                sc = self._to_selected(rs_conn, "connector", _score_component(rs_conn, reqs))
                sensors.append(sc)
                selected_mpns.add(rs_conn.get("mpn", ""))
                confidence_factors.append(sc.score)

        # Priority 4c-post: Battery charger raw-prompt detection.
        # When the LLM doesn't return battery_charger in actuation_modalities,
        # detect charging keywords directly from the raw prompt.
        _raw_prompt_lower = getattr(getattr(reqs, "raw", None), "raw_prompt", "").lower()
        _charger_keywords = (
            "lade" in _raw_prompt_lower          # German: Ladefunktion, Ladesteuerung, Laden
            or "charger" in _raw_prompt_lower
            or "charging" in _raw_prompt_lower
            or "battery charge" in _raw_prompt_lower
            or "li-ion lade" in _raw_prompt_lower
            or "lipo lade" in _raw_prompt_lower
            or "tp4056" in _raw_prompt_lower
            or "akku" in _raw_prompt_lower and ("lade" in _raw_prompt_lower or "charge" in _raw_prompt_lower)
        )

        # Priority 4c-post (solar branch): When the prompt mentions solar input,
        # add BQ24650 (solar MPPT battery charger) instead of TP4056.
        # TP4056 only accepts USB/5V input and does NOT support MPPT/solar panels.
        _SOLAR_CHARGER_MPNS = ["BQ24650", "SPV1040"]
        _solar_keywords = (
            "solar" in _raw_prompt_lower
            or "photovoltaik" in _raw_prompt_lower   # German: Photovoltaik
            or "pv " in _raw_prompt_lower
            or "mppt" in _raw_prompt_lower
            or "bq24650" in _raw_prompt_lower
            or "spv1040" in _raw_prompt_lower
        )
        _has_solar_charger = any(
            any(_mpn_matches(s.mpn, sc_mpn) for sc_mpn in _SOLAR_CHARGER_MPNS)
            for s in sensors
        )
        if _solar_keywords and _charger_keywords and not _has_solar_charger:
            for _sc_mpn in _SOLAR_CHARGER_MPNS:
                _sc_match = next(
                    (c for c in all_catalog if _mpn_matches(c.get("mpn", ""), _sc_mpn)),
                    None,
                )
                if _sc_match and _sc_match.get("mpn") not in selected_mpns:
                    sc = self._to_selected(_sc_match, "battery_charger", _score_component(_sc_match, reqs))
                    sensors.append(sc)
                    selected_mpns.add(_sc_match.get("mpn", ""))
                    confidence_factors.append(sc.score)
                    assumptions.append(
                        f"Solar charging detected in prompt — added {_sc_match.get('mpn')} "
                        f"solar MPPT battery charger (TP4056 cannot accept solar panel input)"
                    )
                    break

        # Priority 4c-post (USB charger branch): add TP4056 when charger keywords
        # are present but NOT when a solar charger was already added above.
        _has_any_charger = _has_solar_charger or any(
            any(_mpn_matches(s.mpn, sc_mpn) for sc_mpn in _SOLAR_CHARGER_MPNS)
            for s in sensors
        )
        if _charger_keywords and not _has_any_charger and not any(_mpn_matches(s.mpn, "TP4056") for s in sensors):
            _tp_match = next((c for c in all_catalog if _mpn_matches(c.get("mpn", ""), "TP4056")), None)
            if _tp_match and _tp_match.get("mpn") not in selected_mpns:
                sc = self._to_selected(_tp_match, "battery_charger", _score_component(_tp_match, reqs))
                sensors.append(sc)
                selected_mpns.add(_tp_match.get("mpn", ""))
                confidence_factors.append(sc.score)
                assumptions.append("Battery charging detected in prompt — added TP4056 Li-Ion USB charger")

        # Priority 4c-post2: Level shifter raw-prompt detection.
        # When the user asks for voltage domain bridging or level shifting but the LLM
        # doesn't return a level_shifter modality, detect it from the raw prompt and
        # add BSS138 (bidirectional MOSFET level shifter, 1.8V–5V capable).
        _LEVEL_SHIFTER_MPNS = ["BSS138", "TXB0104"]
        _has_level_shifter = any(
            any(_mpn_matches(s.mpn, ls) for ls in _LEVEL_SHIFTER_MPNS)
            for s in sensors
        )
        _level_shift_keywords = (
            "level shift" in _raw_prompt_lower        # "level shifter", "level shifting"
            or "level-shift" in _raw_prompt_lower
            or "pegelwandler" in _raw_prompt_lower    # German: "Pegelwandler"
            or "pegel-wandler" in _raw_prompt_lower
            or "spannungsdomän" in _raw_prompt_lower  # German: "Spannungsdomänen" (voltage domains)
            or "voltage domain" in _raw_prompt_lower
            or "txb0104" in _raw_prompt_lower
            or "bss138" in _raw_prompt_lower
        )
        if _level_shift_keywords and not _has_level_shifter:
            for _ls_mpn in _LEVEL_SHIFTER_MPNS:
                _ls_match = next(
                    (c for c in all_catalog if _mpn_matches(c.get("mpn", ""), _ls_mpn)),
                    None,
                )
                if _ls_match and _ls_match.get("mpn") not in selected_mpns:
                    sc = self._to_selected(_ls_match, "level_shifter", _score_component(_ls_match, reqs))
                    sensors.append(sc)
                    selected_mpns.add(_ls_match.get("mpn", ""))
                    confidence_factors.append(sc.score)
                    assumptions.append(
                        f"Voltage level shifting detected in prompt — added {_ls_match.get('mpn')} bidirectional level shifter"
                    )
                    break

        # Priority 4c-post3: Secondary MCU raw-prompt detection.
        # When a non-target MCU is explicitly named in the prompt (e.g. RP2040 in an ESP32
        # project for a dual-MCU topology), add it to the BOM as a secondary controller.
        _SECONDARY_MCU_MPNS = {
            "rp2040": "RP2040",
            "esp32": "ESP32-WROOM-32",
            "esp32-c3": "ESP32-C3",
            "stm32": "STM32F103C8T6",
            "nrf52": "nRF52840",
        }
        _target_mcu_raw = getattr(reqs, "mcu_family", "") or ""
        _target_mcu_lower = _target_mcu_raw.lower()
        for _kw, _sec_mpn in _SECONDARY_MCU_MPNS.items():
            if _kw in _target_mcu_lower:
                continue  # skip if this IS the target MCU family
            if _kw not in _raw_prompt_lower:
                continue  # keyword not in prompt
            if any(_mpn_matches(s.mpn, _sec_mpn) for s in sensors):
                continue  # already selected
            if _sec_mpn in selected_mpns:
                continue
            _sec_match = next(
                (c for c in all_catalog if _mpn_matches(c.get("mpn", ""), _sec_mpn)),
                None,
            )
            if _sec_match:
                # Use role "coprocessor" so the secondary MCU is treated as a
                # peripheral in schematic wiring (UART cross-connected to primary
                # MCU) rather than as a second master that would create pin_to_pin
                # ERC violations (two Output pins on the same TX/RX net).
                sc = self._to_selected(_sec_match, "coprocessor", _score_component(_sec_match, reqs))
                sensors.append(sc)
                selected_mpns.add(_sec_match.get("mpn", ""))
                confidence_factors.append(sc.score)
                assumptions.append(
                    f"Secondary MCU '{_kw}' detected in prompt — added {_sec_match.get('mpn')} as co-processor"
                )
                break  # only add one secondary MCU

        # Priority 4d: USB-C connector — add when TP4056 LiPo charger is in the BOM.
        # TP4056 requires a USB input for charging; a physical USB-C connector is mandatory.
        _USB_C_CONN_MPN = "USB-C-CONN"
        has_tp4056 = any(_mpn_matches(s.mpn, "TP4056") for s in sensors)
        # _raw_prompt_lower is defined in Priority 4c-post above.
        # Detect any USB power/connector request: explicit "usb-c", "usbc", or
        # generic "usb" combined with power/input context words (German and English).
        _usb_power_context = (
            "über usb" in _raw_prompt_lower      # "powered via USB" in German
            or "via usb" in _raw_prompt_lower
            or "per usb" in _raw_prompt_lower
            or "usb strom" in _raw_prompt_lower  # "USB power supply" DE
            or "usb power" in _raw_prompt_lower
            or "usb eingang" in _raw_prompt_lower
            or "usb versorgung" in _raw_prompt_lower
            or "usb-versorgung" in _raw_prompt_lower
            or "5v usb" in _raw_prompt_lower
            or "usb 5v" in _raw_prompt_lower
            or "usb input" in _raw_prompt_lower
            or "powered.*usb" in _raw_prompt_lower
            or "usb.*power" in _raw_prompt_lower
            or "usb buchse" in _raw_prompt_lower  # "USB socket" DE
            or "usb anschluss" in _raw_prompt_lower  # "USB port" DE
            or "usb port" in _raw_prompt_lower
        )
        has_usb_c_keyword = (
            "usb-c" in _raw_prompt_lower
            or "usb c" in _raw_prompt_lower
            or "usbc" in _raw_prompt_lower
            or _usb_power_context
        )
        if (has_tp4056 or has_usb_c_keyword) and _USB_C_CONN_MPN not in selected_mpns:
            usb_c_conn = next(
                (c for c in all_catalog if _mpn_matches(c.get("mpn", ""), _USB_C_CONN_MPN)),
                None,
            )
            if usb_c_conn:
                sc = self._to_selected(usb_c_conn, "connector", _score_component(usb_c_conn, reqs))
                sensors.append(sc)
                selected_mpns.add(usb_c_conn.get("mpn", ""))
                confidence_factors.append(sc.score)

        # Priority 5: Analog component selection — op-amps, comparators, voltage references.
        # Scan the raw prompt for analog keywords; select at most one analog component per
        # keyword group (first match wins within the group to avoid duplicate op-amps).
        # Skip entirely if an analog component was already added via explicit sensor_mpns
        # (e.g. "LM358" in prompt → already selected above; don't also add MCP6002).
        _explicit_analog_mpns = {
            c.get("mpn", "")
            for c in all_catalog
            if c.get("category") == "analog"
            and c.get("mpn", "") in selected_mpns
        }
        prompt_lower = getattr(reqs.raw, "raw_prompt", "").lower()
        _seen_analog_mpns: set[str] = set()
        for keyword, analog_mpn in _MODALITY_ANALOG.items():
            # Don't add a keyword-based analog component if an explicit analog MPN
            # already covers the same function (op-amp, comparator, reference).
            if _explicit_analog_mpns:
                continue
            if keyword not in prompt_lower:
                continue
            if analog_mpn in selected_mpns or analog_mpn in _seen_analog_mpns:
                continue
            analog_match = next(
                (c for c in all_catalog if _mpn_matches(c.get("mpn", ""), analog_mpn)),
                None,
            )
            if analog_match:
                sc = self._to_selected(analog_match, "analog", _score_component(analog_match, reqs))
                sensors.append(sc)
                selected_mpns.add(analog_match.get("mpn", ""))
                _seen_analog_mpns.add(analog_mpn)
                confidence_factors.append(sc.score)
                assumptions.append(
                    f"Analog component '{analog_mpn}' selected for keyword '{keyword}'"
                )

        overall_conf = sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5

        return ComponentSelection(
            mcu=mcu,
            sensors=sensors,
            assumptions=assumptions,
            confidence=overall_conf,
        )

    def select_n_best(self, reqs: NormalizedRequirements, n: int = 3) -> list[ComponentSelection]:
        """Return up to N ranked design alternatives, varying MCU choice.

        Strategy:
        - Variant 1: Best match for the requested MCU family (same as `select()`)
        - Variant 2: Next-best alternative MCU (different family/performance trade-off)
        - Variant 3: Most cost-efficient MCU that satisfies interface requirements
        """
        all_mcus = list_components(category="mcu")
        scored_mcus = sorted(
            [self._to_selected(c, "mcu", _score_component(c, reqs)) for c in all_mcus],
            key=lambda s: s.score,
            reverse=True,
        )

        # Primary variant: preferred family first
        preferred_mpns = {m.upper() for mpns in _MCU_FAMILY_MPNS.get(reqs.mcu_family.lower() if reqs.mcu_family else "", []) for m in mpns}
        primary = next((s for s in scored_mcus if s.mpn.upper() in preferred_mpns), scored_mcus[0] if scored_mcus else None)
        alternative = next((s for s in scored_mcus if s.mpn != (primary.mpn if primary else "")), None)
        cheapest = min(scored_mcus, key=lambda s: s.unit_cost_usd) if scored_mcus else None

        candidates_by_label = [
            ("preferred", primary),
            ("alternative", alternative),
            ("cost-optimized", cheapest),
        ]

        results: list[ComponentSelection] = []
        seen_mpns: set[str] = set()

        for label, mcu_candidate in candidates_by_label:
            if mcu_candidate is None or mcu_candidate.mpn in seen_mpns:
                continue
            seen_mpns.add(mcu_candidate.mpn)

            # Build sensor selection for this MCU
            sensors, assumptions_var, conf = self._select_sensors_for_mcu(mcu_candidate, reqs, label)
            results.append(ComponentSelection(
                mcu=mcu_candidate,
                sensors=sensors,
                assumptions=assumptions_var,
                confidence=conf,
                label=label,
            ))
            if len(results) >= n:
                break

        # If we have fewer than n, return what we have
        return results or [self.select(reqs)]

    def _select_sensors_for_mcu(
        self,
        mcu: SelectedComponent,
        reqs: NormalizedRequirements,
        label: str,
    ) -> tuple[list[SelectedComponent], list[str], float]:
        """Run sensor selection for a given MCU variant."""
        assumptions = list(reqs.unresolved) + ([] if label == "preferred" else [f"MCU variant: {label} ({mcu.mpn})"])
        confidence_factors = [mcu.score]
        sensors: list[SelectedComponent] = []
        selected_mpns: set[str] = set()

        all_catalog = list_components()
        for mpn in reqs.sensor_mpns:
            match = next(
                (c for c in all_catalog if _mpn_matches(c.get("mpn", ""), mpn)),
                None,
            )
            if match and match.get("mpn") not in selected_mpns:
                sc = self._to_selected(match, match.get("category", "sensor"), _score_component(match, reqs))
                sensors.append(sc)
                selected_mpns.add(match.get("mpn", ""))
                confidence_factors.append(sc.score)

        for modality in reqs.sensing_modalities:
            preferred = _get_modality_sensors(modality)
            if any(p.upper() in {m.upper() for m in selected_mpns} for p in preferred):
                continue
            sensor = self._select_sensor(modality, preferred, reqs, exclude_mpns=selected_mpns)
            if sensor and sensor.mpn not in selected_mpns:
                sensors.append(sensor)
                selected_mpns.add(sensor.mpn)
                confidence_factors.append(sensor.score)

        conf = sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5
        return sensors, assumptions, conf

    def _select_mcu(self, reqs: NormalizedRequirements) -> SelectedComponent | None:
        preferred = _MCU_FAMILY_MPNS.get(reqs.mcu_family.lower(), [])
        candidates = list_components(category="mcu")

        # Try preferred first
        for mpn in preferred:
            for c in candidates:
                if c.get("mpn", "").upper() == mpn.upper():
                    return self._to_selected(c, "mcu", _score_component(c, reqs))

        # Fall back to highest-scored MCU
        scored = sorted(candidates, key=lambda c: _score_component(c, reqs), reverse=True)
        if scored:
            c = scored[0]
            return self._to_selected(c, "mcu", _score_component(c, reqs))
        return None

    def _select_sensor(
        self,
        modality: str,
        preferred_mpns: list[str],
        reqs: NormalizedRequirements,
        exclude_mpns: set[str] | None = None,
    ) -> SelectedComponent | None:
        exclude = {m.upper() for m in (exclude_mpns or set())}
        candidates = [c for c in list_components(category="sensor")
                      if c.get("mpn", "").upper() not in exclude]

        # Try preferred MPN list first in sensor category
        for mpn in preferred_mpns:
            for c in candidates:
                if c.get("mpn", "").upper() == mpn.upper():
                    return self._to_selected(c, modality, _score_component(c, reqs))

        # FIX: Also search all categories for preferred MPNs (covers comms-category ICs
        # like LAN8720A, ISO1042BQDWRQ1 that are in _MODALITY_SENSORS but not category=sensor)
        if preferred_mpns:
            all_catalog = list_components()
            for mpn in preferred_mpns:
                for c in all_catalog:
                    if c.get("mpn", "").upper() == mpn.upper() and c.get("mpn", "").upper() not in exclude:
                        return self._to_selected(c, modality, _score_component(c, reqs))

        # Fall back to best-scored sensor with required interface
        if reqs.required_interfaces:
            for iface in reqs.required_interfaces:
                filtered = [c for c in candidates
                            if iface.upper() in [i.upper() for i in c.get("interface_types", [])]]
                if filtered:
                    best = max(filtered, key=lambda c: _score_component(c, reqs))
                    return self._to_selected(best, modality, _score_component(best, reqs))

        if candidates:
            best = max(candidates, key=lambda c: _score_component(c, reqs))
            return self._to_selected(best, modality, _score_component(best, reqs))

        return None

    @staticmethod
    def _to_selected(entry: dict, role: str, score: float) -> SelectedComponent:
        return SelectedComponent(
            mpn=entry.get("mpn", ""),
            manufacturer=entry.get("manufacturer", ""),
            name=entry.get("name", ""),
            category=entry.get("category", "other"),
            interface_types=entry.get("interface_types", []),
            role=role,
            known_i2c_addresses=entry.get("known_i2c_addresses", []),
            init_contract_coverage=bool(entry.get("init_contract_coverage")),
            unit_cost_usd=entry.get("unit_cost_usd", 0.0),
            score=score,
            raw=entry,
        )
