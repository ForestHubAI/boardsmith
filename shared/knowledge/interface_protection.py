# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-Interface Protection Patterns — mandatory ESD/EMC protection per bus type.

Each external interface (USB, RS485, CAN, Ethernet, I2C-external) gets a
mandatory protection pattern specifying which components must be placed
and where.

The synthesizer uses these patterns to automatically insert protection
when an interface is routed to an external connector.

Usage::

    from knowledge.interface_protection import INTERFACE_PROTECTION, get_protection

    prot = get_protection("USB")
    # -> InterfaceProtection(bus_type="USB", ...)
    for comp in prot.mandatory_components:
        print(comp.role, comp.recommended_mpns)
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProtectionComponent:
    """A protection component required for an interface."""
    role: str                        # "esd", "tvs", "ferrite", "cmc", "termination"
    description: str
    recommended_mpns: list[str] = field(default_factory=list)
    value: str = ""                  # for passives: "120Ω", "100nF"
    placement: str = ""              # "within 3mm of connector"
    mandatory: bool = True


@dataclass
class InterfaceProtection:
    """Complete protection specification for one interface type."""
    bus_type: str                    # "USB" | "RS485" | "CAN" | "Ethernet" | "I2C_ext" | "SPI_ext"
    description: str
    mandatory_components: list[ProtectionComponent] = field(default_factory=list)
    placement_rules: list[str] = field(default_factory=list)
    return_path_rules: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-Interface Protection Definitions
# ---------------------------------------------------------------------------

_PROTECTIONS: list[InterfaceProtection] = [

    # --- USB 2.0 ---
    InterfaceProtection(
        bus_type="USB",
        description="USB 2.0 D+/D-/VBUS protection for external connectors",
        mandatory_components=[
            ProtectionComponent(
                role="esd_data",
                description="ESD protection on D+/D- lines, low capacitance (<2pF)",
                recommended_mpns=["USBLC6-2SC6"],
                placement="within 3mm of USB connector, before series resistors",
            ),
            ProtectionComponent(
                role="vbus_ferrite",
                description="Ferrite bead on VBUS line for EMI filtering",
                recommended_mpns=["BLM18BD102SN1D"],
                value="1kΩ@100MHz",
                placement="between connector VBUS and downstream circuitry",
            ),
            ProtectionComponent(
                role="vbus_cap",
                description="Bulk capacitor on VBUS after ferrite",
                value="10µF",
                placement="within 3mm of LDO/regulator input",
            ),
        ],
        placement_rules=[
            "ESD IC closest to connector, before any other component on D+/D-",
            "D+/D- traces: 90Ω differential impedance, length-matched ±2mm",
            "Series resistors (27Ω) between ESD IC and MCU pins",
        ],
        return_path_rules=[
            "Solid GND plane under D+/D- differential pair",
            "GND via near ESD IC for low-impedance return path",
        ],
        notes=[
            "USBLC6-2SC6: <1pF capacitance per line, IEC 61000-4-2 Level 4",
            "Ferrite bead prevents conducted EMI on VBUS from reaching sensitive circuits",
        ],
    ),

    # --- RS-485 ---
    InterfaceProtection(
        bus_type="RS485",
        description="RS-485 A/B line protection for external screw terminals",
        mandatory_components=[
            ProtectionComponent(
                role="tvs_ab",
                description="TVS diode on A and B lines, bidirectional",
                recommended_mpns=["PESD3V3S2UT"],
                placement="within 3mm of screw terminal connector",
            ),
            ProtectionComponent(
                role="termination",
                description="120Ω termination resistor across A/B (bus endpoints only)",
                value="120Ω",
                mandatory=False,
            ),
            ProtectionComponent(
                role="bias_pullup",
                description="Bias resistor pulling A high for defined idle state",
                value="560Ω",
                placement="between VCC and A line",
            ),
            ProtectionComponent(
                role="bias_pulldown",
                description="Bias resistor pulling B low for defined idle state",
                value="560Ω",
                placement="between B line and GND",
            ),
        ],
        placement_rules=[
            "TVS closest to connector, before transceiver A/B pins",
            "Transceiver decoupling (100nF) within 3mm of VCC pin",
        ],
        return_path_rules=[
            "GND connection between RS485 GND and system GND",
            "Cable shield connected to GND through 100nF capacitor (not direct)",
        ],
        notes=[
            "TVS clamping voltage must be below transceiver absolute max on A/B",
            "Bias resistors ensure defined idle state when no driver active",
            "120Ω termination only at BOTH ends of the bus",
        ],
    ),

    # --- CAN / CAN-FD ---
    InterfaceProtection(
        bus_type="CAN",
        description="CAN bus CANH/CANL protection with EMC filtering",
        mandatory_components=[
            ProtectionComponent(
                role="esd_can",
                description="Bidirectional TVS on CANH/CANL lines",
                recommended_mpns=["PESD5V0S2BT"],
                placement="within 3mm of CAN connector",
            ),
            ProtectionComponent(
                role="cmc",
                description="Common-mode choke between transceiver and connector",
                recommended_mpns=["DLW21HN900SQ2L"],
                value="90Ω@100MHz",
                placement="between transceiver CANH/CANL and connector",
            ),
            ProtectionComponent(
                role="termination",
                description="120Ω termination across CANH/CANL (bus endpoints only)",
                value="120Ω",
                mandatory=False,
            ),
        ],
        placement_rules=[
            "Signal path: Transceiver → CMC → TVS → Connector",
            "Transceiver decoupling (100nF) within 3mm of VCC pin",
            "TVS ground return via short to GND plane",
        ],
        return_path_rules=[
            "Solid GND plane under CAN transceiver and connector area",
            "GND stitching vias around CAN connector",
        ],
        notes=[
            "Common-mode choke significantly improves EMC performance",
            "Split termination (2×60Ω + 4.7nF center to GND) optional for better EMC",
            "CAN-FD: ensure CMC bandwidth sufficient for data phase bit rate",
        ],
    ),

    # --- Ethernet 10/100 ---
    InterfaceProtection(
        bus_type="Ethernet",
        description="Ethernet TX/RX protection with magnetics",
        mandatory_components=[
            ProtectionComponent(
                role="magnetics",
                description="1:1 transformer magnetics (often in RJ45 jack)",
                recommended_mpns=["HR911105A"],
                placement="between PHY and RJ45 connector",
            ),
            ProtectionComponent(
                role="esd_eth",
                description="ESD protection on line side of magnetics",
                recommended_mpns=["PESD3V3S2UT"],
                placement="between magnetics and RJ45 connector",
                mandatory=False,
            ),
        ],
        placement_rules=[
            "PHY to RJ45 traces: short, matched length TX+/TX- and RX+/RX-",
            "100Ω differential impedance for TX and RX pairs",
            "PHY decoupling: 100nF on AVDD, 100nF on DVDD, 10µF bulk",
        ],
        return_path_rules=[
            "Solid GND plane under PHY and Ethernet traces",
            "Isolation gap between digital GND and chassis GND if needed",
        ],
        notes=[
            "RJ45 with integrated magnetics (HR911105A) simplifies layout",
            "MDIO bus needs 1.5kΩ pull-up to DVDD",
            "PHY strapping pins set address and mode — check at power-up",
        ],
    ),

    # --- I2C External (Cable) ---
    InterfaceProtection(
        bus_type="I2C_ext",
        description="I2C protection for external cable connections",
        mandatory_components=[
            ProtectionComponent(
                role="esd_i2c",
                description="ESD protection on SDA and SCL, low capacitance",
                recommended_mpns=["PESD3V3S2UT"],
                placement="at connector, before pull-ups",
            ),
            ProtectionComponent(
                role="series_r_sda",
                description="Series resistor on SDA for cable noise filtering",
                value="33Ω",
                placement="between MCU SDA and connector",
            ),
            ProtectionComponent(
                role="series_r_scl",
                description="Series resistor on SCL for cable noise filtering",
                value="33Ω",
                placement="between MCU SCL and connector",
            ),
        ],
        placement_rules=[
            "ESD TVS at connector end, series R between MCU and connector",
            "Pull-ups on MCU side of series resistors",
        ],
        return_path_rules=[
            "GND wire in cable alongside SDA/SCL",
        ],
        notes=[
            "For cable > 1m, consider I2C bus buffer/extender (P82B715)",
            "Total bus capacitance with cable: < 400pF (standard mode)",
            "ESD TVS capacitance adds to bus capacitance — choose < 10pF",
        ],
    ),

    # --- SPI External ---
    InterfaceProtection(
        bus_type="SPI_ext",
        description="SPI protection for external connections",
        mandatory_components=[
            ProtectionComponent(
                role="esd_spi",
                description="ESD protection on MOSI/MISO/SCK/CS lines",
                recommended_mpns=["PESD3V3S2UT"],
                placement="at connector, before any series R",
            ),
            ProtectionComponent(
                role="sck_series_r",
                description="Series resistor on SCK to reduce EMI and ringing",
                value="33Ω",
                placement="close to MCU SCK pin",
            ),
        ],
        placement_rules=[
            "ESD at connector end",
            "CS pull-ups (10kΩ) to keep slaves deselected during boot",
        ],
        return_path_rules=[
            "GND wire in cable",
            "Keep SPI cable < 30cm for reliable operation",
        ],
        notes=[
            "SPI is not designed for long cables — keep connections short",
            "For longer distances, consider RS-485 or CAN instead",
        ],
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Lookup dict
INTERFACE_PROTECTION: dict[str, InterfaceProtection] = {p.bus_type: p for p in _PROTECTIONS}


def get_protection(bus_type: str) -> InterfaceProtection | None:
    """Get the protection specification for a bus type.

    Accepts: "USB", "RS485", "CAN", "Ethernet", "I2C_ext", "SPI_ext"
    Returns None if no protection defined for this bus type.
    """
    return INTERFACE_PROTECTION.get(bus_type)


def get_all_protections() -> list[InterfaceProtection]:
    """Return all defined interface protection patterns."""
    return list(_PROTECTIONS)


def get_mandatory_components(bus_type: str) -> list[ProtectionComponent]:
    """Get only mandatory protection components for a bus type."""
    prot = get_protection(bus_type)
    if prot is None:
        return []
    return [c for c in prot.mandatory_components if c.mandatory]


def check_protection_completeness(bus_type: str, placed_roles: set[str]) -> list[str]:
    """Check if all mandatory protection components are placed.

    Returns list of missing role descriptions.
    """
    prot = get_protection(bus_type)
    if prot is None:
        return []
    missing = []
    for comp in prot.mandatory_components:
        if comp.mandatory and comp.role not in placed_roles:
            missing.append(f"{bus_type}: missing {comp.role} — {comp.description}")
    return missing
