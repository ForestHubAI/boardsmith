# SPDX-License-Identifier: AGPL-3.0-or-later
"""B1. Intent Parser — converts natural language prompt to RequirementsSpec.

Supports two modes:
  - LLM mode: uses LLMGateway (Anthropic Haiku by default) for accurate intent extraction
  - Rule-based mode: simple keyword matching (for testing / --no-llm use)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RequirementsSpec:
    """Structured requirements extracted from a design prompt."""
    raw_prompt: str = ""

    # Functional
    functional_goals: list[str] = field(default_factory=list)

    # Sensing/actuation modalities
    sensing_modalities: list[str] = field(default_factory=list)   # "temperature", "humidity", ...
    actuation_modalities: list[str] = field(default_factory=list)

    # Explicit component MPNs mentioned in the prompt
    sensor_mpns: list[str] = field(default_factory=list)          # e.g. ["BME280", "MPU-6050"]

    # Buses/protocols required
    required_interfaces: list[str] = field(default_factory=list)  # "I2C", "SPI", "UART"

    # Power
    supply_voltage: float | None = None                            # V
    power_budget_ma: float | None = None

    # MCU preferences
    mcu_family: str | None = None                                  # "esp32", "stm32", ...
    mcu_mpn: str | None = None

    # Environmental
    temp_min_c: float | None = None
    temp_max_c: float | None = None

    # Cost/availability
    max_unit_cost_usd: float | None = None
    prefer_availability: bool = False

    # Ambiguities
    unresolved: list[str] = field(default_factory=list)

    # Confidence per sub-requirement
    confidence_per_field: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# LLM-based parser
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a hardware requirements analyst. Given a user's design prompt,
extract structured hardware requirements as a JSON object with these fields:

{
  "functional_goals": ["<list of high-level goals>"],
  "sensing_modalities": ["temperature", "humidity", "pressure", "motion", "distance", "adc", "current", "voltage", "gps", ...],
  "actuation_modalities": ["motor", "led", "relay", ...],
  "sensor_mpns": ["<ALL explicit component MPNs mentioned in the prompt — include sensors AND peripherals/modules, e.g. BME280, MPU-6050, VL53L0X, LAN8720A, W25Q128, SIM7600G-H, MAX98357A, TB6612FNG>"],
  "required_interfaces": ["I2C", "SPI", "UART", "GPIO", ...],
  "supply_voltage": <null or number in V, e.g. 3.3>,
  "power_budget_ma": <null or number>,
  "mcu_family": <null or "esp32", "esp32c3", "stm32", "stm32f4", "stm32h7", "arduino", "rp2040", "nrf52", ...>,
  "mcu_mpn": <null or exact MPN if specified>,
  "temp_min_c": <null or number>,
  "temp_max_c": <null or number>,
  "max_unit_cost_usd": <null or number>,
  "prefer_availability": <bool>,
  "unresolved": ["<BLOCKING ambiguities only — contradictory or fundamentally unclear requirements. Do NOT list optional design choices — those have safe defaults. Examples of things to NEVER list as unresolved: MCU variant, power budget, sampling rate, ADC MPN, number of ADC channels, analog reference voltage, PCB layer count, SPI clock speed specifics.>"],
  "confidence_per_field": {
    "<only fields explicitly mentioned or strongly implied in the prompt>": 0.9
  }
}

Rules:
- sensor_mpns: include ALL component MPNs explicitly named in the prompt (sensors AND peripherals):
  * "LAN8720" or "LAN8720A" mentioned → sensor_mpns must include "LAN8720A"
  * "W25Q128" or "SPI Flash" or "externem SPI Flash" mentioned → sensor_mpns must include "W25Q128"
  * "SIM7600" or "SIM7600G-H" mentioned → sensor_mpns must include "SIM7600G-H"
  * "MAX98357A" mentioned → sensor_mpns must include "MAX98357A"
  * "TB6612FNG" mentioned → sensor_mpns must include "TB6612FNG"
  * "NEO-M8N" mentioned → sensor_mpns must include "NEO-M8N"
  * Any explicit chip/module MPN → add to sensor_mpns
- sensing_modalities mapping: use EXACTLY these canonical modality strings:
  * temperature/thermal sensors → "temperature"
  * humidity sensors → "humidity"
  * pressure/barometric sensors → "pressure"
  * motion/IMU/accelerometer/gyroscope → "motion"
  * external ADC chip / SPI ADC / I2C ADC / data acquisition / "16-bit ADC" / analog measurement → "adc"
  * current sensing / power monitoring / INA226 → "current"
  * voltage measurement → "voltage"
  * GPS/GNSS / NEO-M8N → "gps"
  * distance/range/ultrasonic → "distance"
  * audio / audio codec / I2S / microphone / speaker / Class-D → "audio"
  * Ethernet PHY / LAN8720 / networking → "ethernet"
  * LTE / 4G / cellular / GSM / SIM7600 → "lte"
  * Li-Ion battery charger / LiPo charger / Ladefunktion / TP4056 / BQ25895 → "battery_charger"
  * Li-Ion fuel gauge / battery SOC monitor / state of charge / MAX17043 / LC709203F → "fuel_gauge"
  * H-Bridge / motor driver / DC motor / PWM motor → "motor" (use actuation_modalities, not sensing_modalities!)
  * IMU / accelerometer / gyroscope / ICM-42688 / MPU-6050 → "motion"
  DO NOT use "analog", "analog voltage", "data acquisition", or other free-form strings for sensing_modalities.
- actuation_modalities mapping: use EXACTLY these canonical modality strings:
  * LCD / OLED / display / screen / Anzeige / Bildschirm / SSD1306 / ST7789 / 16x2 LCD / I2C display → "display"
  * motor / H-bridge / Gleichstrommotor / DC motor / TB6612 / DRV8833 → "motor"
  * LED / Licht / LED-Streifen / Beleuchtung → "led"
  * relay / Relais / Schaltrelais → "relay"
  * buzzer / Signalton / Pieper → "buzzer"
- confidence_per_field: only include fields that appear in the prompt. Do NOT include fields that were not mentioned (omit them entirely — absence is fine, not low confidence). Values: 0.5 (vague mention) to 1.0 (explicit).
- unresolved: leave empty [] for most prompts. Only add items that are genuinely contradictory or ambiguous in a way that prevents synthesis.

Only output valid JSON. Do not add explanations outside the JSON object.
"""


def _call_llm(prompt: str) -> dict[str, Any]:
    """Call LLMGateway to extract requirements (sync wrapper)."""
    from llm.gateway import get_default_gateway
    from llm.types import Message, TaskType

    gateway = get_default_gateway()
    response = gateway.complete_sync(
        task=TaskType.INTENT_PARSE,
        messages=[Message(role="user", content=prompt)],
        system=_SYSTEM_PROMPT,
        max_tokens=1024,
    )

    if response.skipped or not response.content:
        raise RuntimeError("LLM skipped or returned empty response")

    text = response.content.strip()
    # Extract JSON if wrapped in markdown code block
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


# ---------------------------------------------------------------------------
# Rule-based fallback parser
# ---------------------------------------------------------------------------

_SENSING_KEYWORDS: dict[str, list[str]] = {
    "temperature": ["temperature", "temp", "thermal", "thermometer", "temperatur"],
    "humidity": ["humidity", "humid", "moisture", "rh", "feuchtigkeit"],
    "pressure": ["pressure", "barometric", "baro", "altitude", "druck"],
    "motion": ["motion", "imu", "accelerometer", "gyroscope", "gyro", "inertial",
               "beschleunigung", "lagesensor", "icm-42688", "icm42688", "mpu-6050", "mpu6050"],
    "distance": ["distance", "range", "tof", "proximity", "ultrasonic", "abstand",
                 "entfernung", "ultraschall", "ultraschallsensor", "hc-sr04", "hcsr04"],
    "light": ["light", "lux", "ambient light", "ldr", "photo", "licht"],
    "gas": ["gas", "co2", "voc", "air quality", "luftqualität"],
    "current": ["current sensor", "current measurement", "ampere", "strommessung",
                "stromstärke", "shunt resistor", "ina219", "ina226", "power monitor",
                "strommessmodul", "leistungsmessung"],
    "voltage": ["spannungsmessung", "voltage measurement",
                "spannungsteiler", "voltage divider"],
    "gps": ["gps", "gnss", "position", "location", "standort", "neo-m8n", "neo m8n"],
    # Audio — codec, amplifier, microphone interface
    "audio": ["audio codec", "i2s codec", "audio amplifier", "klasse-d", "class-d",
              "lautsprecher", "speaker amplifier", "i2s audio", "mikrofon",
              "microphone", "vorverstärker", "preamplifier", "max98357", "wm8731", "pcm5102"],
    # Ethernet PHY
    "ethernet": ["ethernet phy", "lan8720", "rmii", "ethernet transceiver", "phy transceiver"],
    # LTE/Cellular modules
    "lte": ["lte modul", "lte module", "sim7600", "sim800", "4g modul", "cellular",
            "lte cat", "gsm modul", "gsm module", "mobilfunk"],
    # CAN transceiver (non-isolated) — multi-word phrases only, no bare "can"
    # to avoid false positives with words like "scanner", "cancel", "can bus" interface
    "can": [
        "can-fd", "canfd", "can transceiver", "can-transceiver",
        "can-bus transceiver", "canbus transceiver",
        "tcan1042", "sn65hvd230",
    ],
    # Isolated CAN transceiver — galvanic isolation for CAN bus
    "isolated_can": [
        "galvanischer isolation", "galvanic isolation", "galvanische trennung",
        "isolated can", "isolierter can", "can isolation", "can isolierung",
        "iso1042", "iso1050", "tja1050",
    ],
    # Battery charger ICs (TP4056, BQ25895, etc.)
    "battery_charger": [
        "ladefunktion", "li-ion lad", "lipo lad", "batterie lad",
        "battery charg", "charge controller",
        "bq25895", "tp4056",
    ],
    # Battery fuel gauge / SOC monitor ICs (MAX17043, LC709203F, etc.)
    "fuel_gauge": [
        "fuel gauge", "fuel-gauge", "kraftstoffanzeige", "akku monitor",
        "battery monitor", "soc monitor", "state of charge",
        "max17043", "lc709203f", "lc709203", "bq27441",
    ],
    # Solar power management — MPPT converter and solar battery charger
    "solar": [
        "solar", "solar-eingang", "solar eingang", "solareingang", "solarpanel",
        "solar panel", "mppt", "photovoltaik", "pv-eingang", "pv eingang",
        "laderegler", "solar charger", "solar charge", "spv1040", "bq24650",
    ],
    # External ADC — high-resolution or SPI ADC modules
    # NOTE: "analog" is intentionally NOT a sensing modality here.
    # Analog components (op-amps, comparators) are selected via Priority 5
    # (_MODALITY_ANALOG keyword scan) in component_selector.py, not via sensing_modalities.
    "adc": ["external adc", "spi adc", "i2c adc", "16-bit adc", "24-bit adc",
            "data acquisition", "datenerfassung", "adc-modul",
            "ads8681", "ads1115", "ads1675", "ads7028", "mcp3204"],
}

_ACTUATION_KEYWORDS: dict[str, list[str]] = {
    # "led" uses word-boundary matching (see _rule_based_parse) to avoid matching "oled"
    "led": [r"\bled\b", "status-led", "status led", "indicator", "blink", "dimm",
            "leuchtdiode", "light emitting", "vorwiderstand"],
    "motor": ["h-bridge", "h-brücke", "motor-treiber", "motortreiber", "dc motor",
              "stepper", "schrittmotor", "tb6612", "drv8833", "l298"],
    "mosfet-motor": ["mosfet motor", "pwm fan", "gebläse", "lüfter", "fan control"],
    "relay": ["relay", "relais"],
    "buzzer": ["buzzer", "beeper", "piezo"],
    "display": ["display", "oled", "lcd", "screen", "tft", "anzeige"],
    "transistor": ["transistor", "npn", "pnp", "gate treiber"],
    "mosfet": ["mosfet", "n-kanal", "p-kanal", "n-channel", "p-channel", "nmos", "pmos",
               "irlz44n", "irfz44n", "2n7000"],
    "spi-flash": ["spi flash", "spi-flash", "flash chip", "nor flash", "w25q",
                  "externem spi flash", "external flash", "external spi"],
    "microsd": ["sd-karte", "microsd", "sd card", "micro-sd", "speicherkarte"],
    "communication": ["can bus", "canbus", "rs485", "rs232", "lora", "lorawan",
                      "gsm", "lte", "bluetooth", "ble", "wifi", "ethernet",
                      "uart header", "rs-485", "can-bus", "funk"],
    "power": ["ldo", "step-down", "buck", "boost", "lipo", "akku", "battery",
              "charger", "lade", "tp4056", "power management", "stromversorgung"],
    "button": ["taster", "button", "pushbutton", "digitalem eingang", "taste"],
    "levelshifter": ["level-shifter", "level shifter", "levelshifter", "pegelwandler",
                     "pegel-wandler", "logic level", "spannungspegel", "level converter",
                     "pegel konverter", "bidirectional level"],
}

_INTERFACE_KEYWORDS: dict[str, list[str]] = {
    "I2C": ["i2c", "i²c", "twi"],
    "SPI": ["spi"],
    "UART": ["uart", "serial", "rs232"],
    "GPIO": ["gpio", "digital pin", "digitalem eingang", "interrupt"],
    "CAN": ["can bus", "canbus", "can-bus"],
    "PWM": ["pwm", "servo"],
    "RS485": ["rs485", "rs-485", "max485", "differential bus"],
    "Ethernet": ["ethernet", "lan8720", "rj45"],
    "I2S": ["i2s", "audio codec"],
}

_MCU_KEYWORDS: dict[str, str] = {
    # More specific entries first — first match wins (dict is ordered in Python 3.7+)
    "esp32-c3": "esp32c3",
    "esp32-s3": "esp32s3",   # S3 → own family (distinct module)
    "esp32c3": "esp32c3",
    "esp32s3": "esp32s3",
    "esp32": "esp32",
    "esp8266": "esp8266",
    "stm32h7": "stm32h7",   # H7 family → STM32H743VIT6
    "stm32f7": "stm32f7",   # F7 family → STM32F746ZGT6
    "stm32f746": "stm32f7",
    "stm32g4": "stm32g4",   # G4 family → STM32G431CBU6
    "stm32g431": "stm32g4",
    "stm32l4": "stm32l4",   # L4 family → STM32L476RGT6
    "stm32l476": "stm32l4",
    "stm32f4": "stm32f4",   # F4 family → STM32F405RGT6
    "stm32f405": "stm32f4",
    "stm32f411": "stm32f4",
    "stm32f1": "stm32",
    "stm32f103": "stm32",
    "stm32": "stm32",
    "lpc55s": "lpc55",       # NXP LPC55Sxx variants → LPC55S69JBD100
    "lpc55": "lpc55",        # NXP LPC55 → LPC55S69JBD100
    "lpc": "lpc55",          # NXP LPC family (generic) → lpc55
    "i.mx": "imxrt",         # NXP i.MX RT → MIMXRT1062DVJ6A
    "imxrt": "imxrt",
    "rp2040": "rp2040",
    "pico": "rp2040",
    "nrf52840": "nrf52",
    "nrf52": "nrf52",
    "atmega2560": "mega",    # Arduino Mega — must precede "atmega" to avoid partial match
    "atmega328p": "atmega",
    "atmega328":  "atmega",
    "mega":       "mega",
    "atmega":     "atmega",
    "arduino": "arduino",
    "raspberry": "rp2040",   # "Raspberry Pi Pico" → rp2040
    "teensy": "teensy",
}

# Known peripheral/sensor MPNs that can be directly named in prompts.
# These are matched case-insensitively against the prompt text.
_KNOWN_PERIPHERAL_MPNS: list[str] = [
    # Sensors — temperature / environmental
    "BME280", "AHT20", "BMP388", "BMP280", "SHT31", "SHT31-DIS", "HDC1080",
    "DS18B20",                         # 1-Wire temperature sensor
    "MCP9808",                         # I2C precision temperature sensor
    "MAX31865",                        # RTD-to-Digital converter (PT100)
    "MAX6675",                         # K-type thermocouple converter
    "SCD41",                           # CO2 + Temp/Humidity sensor
    # Sensors — motion / position
    "MPU-6050", "MPU6050", "ICM-42688", "ICM42688", "ICM-42688-P",
    "AS5600",                          # Magnetic rotary encoder (I2C)
    # Sensors — current / voltage / ADC
    "INA226", "INA219",
    "ADS1115",                         # 16-bit 4-channel I2C ADC
    "ADS8681",                         # 16-bit 1MSPS SPI ADC
    # Sensors — distance / proximity
    "VL53L0X", "HC-SR04", "HC-SR04P",
    # Sensors — other
    "SHTC3",
    # Display
    "SSD1306", "ST7735", "ST7789", "ILI9341",
    "MAX7219",                         # LED matrix driver (SPI)
    # Memory / Storage
    "W25Q128", "W25Q64", "W25Q32",
    "MICROSD-SLOT-SPI",
    # Communication
    "SX1276", "SX1278", "RFM95W",     # LoRa
    "SN65HVD230", "ISO3082",           # CAN / isolated RS485
    "MAX485", "MAX3485", "MAX481", "SP3485",  # RS485
    "TCAN1042",                        # CAN transceiver
    "LAN8720", "LAN8720A",             # Ethernet PHY
    "W5500",                           # Ethernet controller (SPI)
    "SIM800L", "SIM7600", "SIM7600G", "SIM7600G-H", "SIM7000",   # GSM / LTE
    "NEO-M8N", "NEO-M8", "NEO-6M",    # GPS
    "ADUM1201",                        # Digital isolator
    # Power
    "TP4056",                          # LiPo charger
    "ISO1042BQDWRQ1", "ISO1042",       # Isolated CAN transceiver
    "BQ24650",                         # Solar battery charger
    "SPV1040",                         # MPPT boost converter
    # Audio
    "CS4344", "MAX98357", "MAX98357A", "WM8731", "PCM5102", "TAS5756",
    # Motor drivers
    "TB6612FNG", "TB6612", "DRV8833", "L298N", "L293D",
    # ADC — high-resolution external ADCs
    "ADS8681", "ADS1115", "ADS1675", "ADS7028", "MCP3204",
    # Analog — op-amps, comparators, voltage references
    "MCP6002", "LM358", "LM393", "LM4040",
    # Level shifters
    "TXB0104",
]


def _rule_based_parse(prompt: str) -> dict[str, Any]:
    """Simple keyword-based requirement extraction (no LLM).

    Detects both sensing modalities (temperature, humidity, ...) and
    actuation/peripheral goals (LED, motor, display, SPI Flash, ...).
    A prompt is only marked unresolved if it has NO detectable goal at all.
    """
    low = prompt.lower()

    def _kw_in(kws: list[str], text: str) -> bool:
        """Match keywords against text, supporting regex patterns (starting with r'\\b')."""
        for kw in kws:
            if kw.startswith(r"\b") or kw.startswith("(?"):
                if re.search(kw, text):
                    return True
            elif kw in text:
                return True
        return False

    sensing = [mod for mod, kws in _SENSING_KEYWORDS.items() if _kw_in(kws, low)]
    actuation = [mod for mod, kws in _ACTUATION_KEYWORDS.items() if _kw_in(kws, low)]
    interfaces = [iface for iface, kws in _INTERFACE_KEYWORDS.items() if _kw_in(kws, low)]

    # Detect explicit peripheral MPNs (e.g. "BME280", "MPU-6050", "W25Q128")
    # Normalise by stripping dashes/spaces for matching
    sensor_mpns: list[str] = []
    _normalised_seen: set[str] = set()
    low_normalised = low.replace("-", "").replace(" ", "")
    for mpn in _KNOWN_PERIPHERAL_MPNS:
        normalised = mpn.lower().replace("-", "").replace(" ", "")
        if normalised in _normalised_seen:
            continue
        if normalised in low_normalised:
            sensor_mpns.append(mpn)
            _normalised_seen.add(normalised)

    if not interfaces and (sensing or sensor_mpns):
        interfaces = ["I2C"]  # Default to I2C for sensors

    mcu = None
    for kw, family in _MCU_KEYWORDS.items():
        if kw in low:
            mcu = family
            break
    if mcu is None:
        mcu = "esp32"  # Safe default

    # Supply voltage — detect input supply, NOT regulated output.
    # Priority order prevents "3.3V LDO" from overriding "3.7V LiPo" as the supply.
    voltage = None
    if any(kw in low for kw in ["lipo", "li-po", "li-ion", "liion"]):
        # LiPo / Li-Ion battery → 3.7V nominal (charges to 4.2V → always needs LDO for 3.3V logic)
        voltage = 3.7
    elif "akku" in low:
        # German: Akkumulator (rechargeable battery) → 3.7V
        voltage = 3.7
    elif "usb" in low:
        # USB power → 5.0V (USB-C, micro-USB, USB-A all deliver 5V)
        voltage = 5.0
    elif "24v" in low or "24 v" in low:
        voltage = 24.0
    elif "12v" in low or "12 v" in low:
        voltage = 12.0
    elif "5v" in low or "5 v" in low:
        voltage = 5.0
    elif "3.7v" in low or "3.7 v" in low or "3,7v" in low:
        voltage = 3.7
    elif ("3.3v" in low or "3v3" in low or "3.3 v" in low) and not any(
        kw in low for kw in ["ldo", "regler", "step-down", "stepdown", "buck", "boost"]
    ):
        # 3.3V only when there's no voltage regulator context
        # (e.g. "3.3V LDO" means the LDO OUTPUT is 3.3V, not that the supply is 3.3V)
        voltage = 3.3
    elif re.search(r"\b3\s*v\b", low) and not any(
        kw in low for kw in ["ldo", "regler", "step-down", "stepdown", "buck", "boost"]
    ):
        # "3V Versorgung" → 3.0V (close enough to 3.3V, no LDO needed)
        voltage = 3.0

    # Default: if no voltage keyword was found, assume USB 5V as the most common
    # real-world supply. This ensures an LDO is always generated.
    if voltage is None:
        voltage = 5.0

    # Build functional goals from sensing + actuation
    goals: list[str] = []
    goals += [f"Measure {m}" for m in sensing]
    goals += [f"Control {m}" for m in actuation]
    if not goals and sensor_mpns:
        goals = [f"Use {', '.join(sensor_mpns)}"]
    if not goals and interfaces:
        goals = [f"Use {', '.join(interfaces)} interface(s)"]
    if not goals:
        goals = ["GPIO-based embedded design"]

    # Unresolved: ONLY if nothing at all was detected
    has_any_goal = bool(sensing or actuation or sensor_mpns or
                        any(i in interfaces for i in
                            ["I2C", "SPI", "UART", "GPIO", "CAN", "PWM",
                             "RS485", "Ethernet", "I2S"]))
    unresolved = []
    if not has_any_goal:
        unresolved.append(
            "No functional goal detected — please specify sensors, actuators, or peripherals"
        )

    # Confidence — 0.0 means "not applicable" (skipped in average by normalizer)
    sensing_conf = 0.8 if sensing else (0.9 if sensor_mpns else 0.0)
    actuation_conf = 0.8 if actuation else 0.0
    goal_conf = 0.75 if has_any_goal else 0.35

    conf_fields: dict[str, float] = {"mcu_family": 0.7}
    if sensing_conf > 0:
        conf_fields["sensing_modalities"] = sensing_conf
    if actuation_conf > 0:
        conf_fields["actuation_modalities"] = actuation_conf
    conf_fields["functional_goals"] = goal_conf
    if interfaces:
        conf_fields["required_interfaces"] = 0.8

    return {
        "functional_goals": goals,
        "sensing_modalities": sensing,
        "actuation_modalities": actuation,
        "sensor_mpns": sensor_mpns,
        "required_interfaces": interfaces,
        "supply_voltage": voltage,
        "power_budget_ma": None,
        "mcu_family": mcu,
        "mcu_mpn": None,
        "temp_min_c": None,
        "temp_max_c": None,
        "max_unit_cost_usd": None,
        "prefer_availability": False,
        "unresolved": unresolved,
        "confidence_per_field": conf_fields,
    }


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

class IntentParser:
    """Parses natural-language prompts into RequirementsSpec objects."""

    def __init__(self, use_llm: bool = True) -> None:
        from llm.gateway import get_default_gateway
        self._use_llm = use_llm and get_default_gateway().is_llm_available()

    def parse(self, prompt: str) -> RequirementsSpec:
        """Parse a design prompt and return a RequirementsSpec."""
        if self._use_llm:
            try:
                data = _call_llm(prompt)
            except Exception:
                # Fall back to rule-based on API error
                data = _rule_based_parse(prompt)
        else:
            data = _rule_based_parse(prompt)

        return RequirementsSpec(
            raw_prompt=prompt,
            functional_goals=data.get("functional_goals", []),
            sensing_modalities=data.get("sensing_modalities", []),
            actuation_modalities=data.get("actuation_modalities", []),
            sensor_mpns=data.get("sensor_mpns", []),
            required_interfaces=data.get("required_interfaces", []),
            supply_voltage=data.get("supply_voltage"),
            power_budget_ma=data.get("power_budget_ma"),
            mcu_family=data.get("mcu_family"),
            mcu_mpn=data.get("mcu_mpn"),
            temp_min_c=data.get("temp_min_c"),
            temp_max_c=data.get("temp_max_c"),
            max_unit_cost_usd=data.get("max_unit_cost_usd"),
            prefer_availability=data.get("prefer_availability", False),
            unresolved=data.get("unresolved", []),
            confidence_per_field=data.get("confidence_per_field", {}),
        )
