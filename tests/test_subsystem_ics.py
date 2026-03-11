# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression tests: subsystem ICs in complex nollm synthesis (S03/S06/S10).

Tests verify that complex prompts mentioning Ethernet PHY, isolated CAN, and
solar power management produce BOMs with the expected subsystem ICs.
All tests run under BOARDSMITH_NO_LLM=1 (no API key required).
"""
import pytest
import os

os.environ.setdefault("BOARDSMITH_NO_LLM", "1")

# Force a fresh DB rebuild so new seed entries are visible.
from knowledge import db as _kdb  # noqa: E402
_kdb.rebuild()

from boardsmith_hw.intent_parser import IntentParser  # noqa: E402
from boardsmith_hw.requirements_normalizer import normalize  # noqa: E402
from boardsmith_hw.component_selector import ComponentSelector  # noqa: E402
from synth_core.knowledge.symbol_map import get_symbol_def  # noqa: E402


@pytest.fixture
def parser():
    return IntentParser(use_llm=False)


@pytest.fixture
def selector():
    return ComponentSelector(seed=42, use_agent=False)


def _select(prompt: str, selector: ComponentSelector, parser: IntentParser):
    spec = parser.parse(prompt)
    reqs = normalize(spec)
    return selector.select(reqs)


# ---------------------------------------------------------------------------
# Seed entries
# ---------------------------------------------------------------------------

def test_bq24650_in_seed():
    from knowledge.seed.power import COMPONENTS
    mpns = [c["mpn"] for c in COMPONENTS]
    assert "BQ24650" in mpns, "BQ24650 missing from seed/power.py"


def test_spv1040_in_seed():
    from knowledge.seed.power import COMPONENTS
    mpns = [c["mpn"] for c in COMPONENTS]
    assert "SPV1040" in mpns, "SPV1040 missing from seed/power.py"


# ---------------------------------------------------------------------------
# Symbol map entries
# ---------------------------------------------------------------------------

def test_bq24650_in_symbol_map():
    sym = get_symbol_def("BQ24650", "power", [])
    assert sym is not None
    pin_names = {p.name for p in sym.pins}
    assert "VCC" in pin_names or "VIN" in pin_names
    assert "GND" in pin_names or "GND_EP" in pin_names


def test_spv1040_in_symbol_map():
    sym = get_symbol_def("SPV1040", "power", [])
    assert sym is not None
    pin_names = {p.name for p in sym.pins}
    assert "VIN" in pin_names
    assert "VOUT" in pin_names


# ---------------------------------------------------------------------------
# Intent parsing
# ---------------------------------------------------------------------------

def test_isolated_can_intent(parser):
    """S06: 'galvanischer Isolation' → isolated_can sensing modality."""
    spec = parser.parse(
        "STM32F405 Board mit CAN Bus und galvanischer Isolation, 24V Eingang"
    )
    assert "isolated_can" in spec.sensing_modalities, (
        f"Expected 'isolated_can' in sensing_modalities, got: {spec.sensing_modalities}"
    )


def test_solar_intent(parser):
    """S10: 'Solar-Eingang, Laderegler' → solar sensing modality."""
    spec = parser.parse(
        "ESP32 mit Solar-Eingang, Laderegler und Li-Ion Akku"
    )
    assert "solar" in spec.sensing_modalities, (
        f"Expected 'solar' in sensing_modalities, got: {spec.sensing_modalities}"
    )


# ---------------------------------------------------------------------------
# Component selection — S03/S06/S10 regression
# ---------------------------------------------------------------------------

S03_PROMPT = (
    "Entwerfe ein 4-Layer STM32H743 Board mit Ethernet PHY, USB, CAN-FD, "
    "externem SPI Flash und getrennten Analog- und Digital-GND Domains."
)

S06_PROMPT = (
    "Erstelle ein STM32F405 Board mit PT100 (MAX31865), K-Typ Thermoelement (MAX6675), "
    "24V Eingang, CAN Bus und galvanischer Isolation."
)

S10_PROMPT = (
    "Entwerfe ein robustes Outdoor-Board mit ESP32, GPS (NEO-M8N), LoRa (RFM95W), "
    "Li-Ion Akku, Solar-Eingang, Laderegler und Überspannungsschutz."
)


def test_s03_ethernet_phy_selected(parser, selector):
    """S03: Ethernet PHY prompt → LAN8720A in BOM."""
    sel = _select(S03_PROMPT, selector, parser)
    mpns = [s.mpn.upper() for s in sel.sensors]
    assert "LAN8720A" in mpns, (
        f"LAN8720A missing from S03 selection. Got: {mpns}"
    )


def test_s06_isolated_can_selected(parser, selector):
    """S06: Galvanic isolation prompt → ISO1042BQDWRQ1 in BOM."""
    sel = _select(S06_PROMPT, selector, parser)
    mpns = [s.mpn.upper() for s in sel.sensors]
    # Accept either full MPN or ISO1042 prefix (normalize variant suffixes)
    has_iso1042 = any("ISO1042" in m for m in mpns)
    assert has_iso1042, (
        f"ISO1042 variant missing from S06 selection. Got: {mpns}"
    )


def test_s10_solar_charger_selected(parser, selector):
    """S10: Solar prompt → BQ24650 or SPV1040 in BOM."""
    sel = _select(S10_PROMPT, selector, parser)
    mpns = [s.mpn.upper() for s in sel.sensors]
    has_solar_ic = "BQ24650" in mpns or "SPV1040" in mpns
    assert has_solar_ic, (
        f"Neither BQ24650 nor SPV1040 in S10 selection. Got: {mpns}"
    )
