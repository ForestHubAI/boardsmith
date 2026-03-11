# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for P0 Industry Phase — Industrial Patterns, Component Classes,
EDA Quality Gates, Connectors, Interface Protection.

Covers:
  P0.1 — IndustrialPatternLibrary (10 patterns)
  P0.2 — New component classes (8 MPNs)
  P0.3 — EdaBinding + SubstituteInfo schema
  P0.4 — New connector templates (5 MPNs)
  P0.5 — Interface protection patterns (6 bus types)
"""
from __future__ import annotations

import pytest


# ===================================================================
# P0.1 — Industrial Pattern Library
# ===================================================================


class TestIndustrialPatternSchema:
    """Test the IndustrialPattern data model."""

    def test_import(self):
        from shared.knowledge.industrial_patterns import (
            IndustrialPattern, IndustrialPatternLibrary,
            PatternComponent, PatternNet, PlacementHint, PatternTestCase,
            ParamSpec,
        )
        assert IndustrialPattern is not None
        assert IndustrialPatternLibrary is not None

    def test_pattern_dataclass_fields(self):
        from shared.knowledge.industrial_patterns import IndustrialPattern
        p = IndustrialPattern(
            id="test_v1",
            version="1.0.0",
            name="Test Pattern",
            description="A test pattern",
            category="power_input",
            keywords=["test"],
        )
        assert p.id == "test_v1"
        assert p.version == "1.0.0"
        assert p.quality_state == "validated"
        assert p.components == []
        assert p.nets == []


class TestIndustrialPatternLibrary:
    """Test the pattern library with all 10 built-in patterns."""

    @pytest.fixture
    def lib(self):
        from shared.knowledge.industrial_patterns import IndustrialPatternLibrary
        return IndustrialPatternLibrary()

    def test_all_patterns_count(self, lib):
        assert len(lib.all_patterns()) == 10

    def test_all_pattern_ids(self, lib):
        expected_ids = [
            "24v_input_protection_v1",
            "usb_device_mcu_v1",
            "rs485_node_v1",
            "can_node_v1",
            "liion_charging_powerpath_v1",
            "adc_input_protection_v1",
            "ethernet_rmii_phy_v1",
            "lora_rf_frontend_v1",
            "i2c_bus_protected_v1",
            "spi_bus_standard_v1",
        ]
        assert sorted(lib.pattern_ids()) == sorted(expected_ids)

    def test_get_by_id(self, lib):
        p = lib.get("24v_input_protection_v1")
        assert p is not None
        assert p.name == "24V Industrial Input Protection"
        assert p.category == "power_input"

    def test_get_nonexistent(self, lib):
        assert lib.get("nonexistent_v1") is None

    def test_find_by_category(self, lib):
        power = lib.find_by_category("power_input")
        assert len(power) == 1
        assert power[0].id == "24v_input_protection_v1"

        bus = lib.find_by_category("bus_protection")
        assert len(bus) >= 5  # USB, RS485, CAN, Ethernet, LoRa, I2C, SPI

    def test_find_by_keyword(self, lib):
        results = lib.find_by_keyword("rs485 modbus")
        assert len(results) >= 1
        assert results[0].id == "rs485_node_v1"

    def test_find_by_keyword_german(self, lib):
        results = lib.find_by_keyword("batterie laden lipo")
        assert len(results) >= 1
        assert results[0].id == "liion_charging_powerpath_v1"

    def test_find_by_quality(self, lib):
        validated = lib.find_by_quality("validated")
        assert len(validated) == 10  # all are "validated"

        verified = lib.find_by_quality("verified")
        assert len(verified) == 0  # none are "verified" yet

    @pytest.mark.parametrize("pattern_id", [
        "24v_input_protection_v1",
        "usb_device_mcu_v1",
        "rs485_node_v1",
        "can_node_v1",
        "liion_charging_powerpath_v1",
        "adc_input_protection_v1",
        "ethernet_rmii_phy_v1",
        "lora_rf_frontend_v1",
        "i2c_bus_protected_v1",
        "spi_bus_standard_v1",
    ])
    def test_pattern_completeness(self, lib, pattern_id):
        """Every pattern must have components, nets, and notes."""
        p = lib.get(pattern_id)
        assert p is not None, f"Pattern {pattern_id} not found"
        assert len(p.components) >= 1, f"{pattern_id}: no components"
        assert len(p.nets) >= 1, f"{pattern_id}: no nets"
        assert len(p.keywords) >= 3, f"{pattern_id}: too few keywords"
        assert len(p.notes) >= 1, f"{pattern_id}: no notes"
        assert p.version == "1.0.0"

    def test_24v_protection_chain_components(self, lib):
        p = lib.get("24v_input_protection_v1")
        roles = {c.role for c in p.components}
        assert "fuse" in roles
        assert "tvs" in roles
        assert "rev_pol_mosfet" in roles
        assert "buck" in roles

    def test_usb_device_components(self, lib):
        p = lib.get("usb_device_mcu_v1")
        roles = {c.role for c in p.components}
        assert "connector" in roles
        assert "esd" in roles
        assert "dp_series_r" in roles
        assert "dm_series_r" in roles
        assert "ldo" in roles

    def test_can_node_has_cmc(self, lib):
        p = lib.get("can_node_v1")
        roles = {c.role for c in p.components}
        assert "cmc" in roles
        assert "esd" in roles
        assert "transceiver" in roles

    def test_battery_pattern_has_protection(self, lib):
        p = lib.get("liion_charging_powerpath_v1")
        roles = {c.role for c in p.components}
        assert "protection_ic" in roles
        assert "protection_mosfets" in roles
        assert "charger" in roles


# ===================================================================
# P0.2 — New Component Classes
# ===================================================================


class TestNewComponentClasses:
    """Verify the 8 new industrial component classes are in the DB."""

    @pytest.fixture(scope="class")
    def db(self):
        import sys
        sys.path.insert(0, "shared")
        from knowledge import db
        db.rebuild()
        return db

    def test_db_count_increased(self, db):
        n = db.count()
        assert n >= 153  # 145 original + 8 new

    @pytest.mark.parametrize("mpn,sub_type", [
        ("TPS22918DBVR", "load_switch"),
        ("LM74610DGKR", "ideal_diode"),
        ("BQ24075RGTR", "power_path"),
        ("DW01A-G", "battery_protection"),
        ("FS8205A", "battery_protection"),
        ("INA128UA", "inamp"),
        ("MCP2562FD-E/SN", "can-fd"),
        ("ISO1042BQDWRQ1", "isolated-can"),
    ])
    def test_new_component_exists(self, db, mpn, sub_type):
        entry = db.find_by_mpn(mpn)
        assert entry is not None, f"MPN {mpn} not found in DB"
        assert entry["sub_type"] == sub_type

    def test_load_switch_capabilities(self, db):
        entry = db.find_by_mpn("TPS22918DBVR")
        caps = entry.get("capabilities", {})
        assert caps.get("topology") == "load_switch"
        assert caps.get("enable_pin") is True

    def test_battery_protection_pair(self, db):
        dw01 = db.find_by_mpn("DW01A-G")
        fs82 = db.find_by_mpn("FS8205A")
        assert dw01["capabilities"].get("recommended_mosfet") == "FS8205A"
        assert fs82["capabilities"].get("paired_with") == "DW01A-G"

    def test_power_path_has_usb_limit(self, db):
        entry = db.find_by_mpn("BQ24075RGTR")
        caps = entry.get("capabilities", {})
        assert caps.get("power_path_management") is True
        assert caps.get("usb_current_limit") is True

    def test_can_fd_transceiver(self, db):
        entry = db.find_by_mpn("MCP2562FD-E/SN")
        caps = entry.get("capabilities", {})
        assert caps.get("protocol") == "can_fd"
        assert caps.get("data_rate_bps") == 8_000_000


# ===================================================================
# P0.3 — EDA Binding Quality Gates
# ===================================================================


class TestEdaBindingSchema:
    """Test the EdaBinding and SubstituteInfo TypedDicts."""

    def test_eda_binding_import(self):
        from shared.knowledge.schema import EdaBinding
        binding: EdaBinding = {
            "symbol_lib": "boardsmith_symbols",
            "footprint_lib": "kicad_default",
            "pinmap_verified": True,
            "footprint_variants": ["QFN-28", "TQFP-32"],
            "pinmap_hash": "sha256:abc123",
            "quality_state": "verified",
            "last_verified": "2026-03-01",
        }
        assert binding["quality_state"] == "verified"
        assert len(binding["footprint_variants"]) == 2

    def test_substitute_info_import(self):
        from shared.knowledge.schema import SubstituteInfo
        sub: SubstituteInfo = {
            "approved_substitutes": ["MCP1700-3302E"],
            "class_substitutes": ["any_3.3v_ldo_800ma"],
            "drop_in_constraint": "drop-in",
            "supply_risk_score": 1,
            "lifecycle_status": "active",
            "second_sources": ["Microchip", "ON Semi"],
        }
        assert sub["supply_risk_score"] == 1
        assert sub["drop_in_constraint"] == "drop-in"

    def test_component_entry_accepts_eda_binding(self):
        from shared.knowledge.schema import ComponentEntry
        entry: ComponentEntry = {
            "mpn": "TEST-MPN",
            "eda_binding": {
                "quality_state": "validated",
                "pinmap_verified": False,
            },
        }
        assert entry["eda_binding"]["quality_state"] == "validated"

    def test_component_entry_accepts_substitute_info(self):
        from shared.knowledge.schema import ComponentEntry
        entry: ComponentEntry = {
            "mpn": "TEST-MPN",
            "substitute_info": {
                "lifecycle_status": "active",
                "supply_risk_score": 2,
            },
        }
        assert entry["substitute_info"]["lifecycle_status"] == "active"


# ===================================================================
# P0.4 — New Connector Templates
# ===================================================================


class TestNewConnectors:
    """Verify the 5 new connector templates are in the DB."""

    @pytest.fixture(scope="class")
    def db(self):
        import sys
        sys.path.insert(0, "shared")
        from knowledge import db
        db.rebuild()
        return db

    @pytest.mark.parametrize("mpn,sub_type", [
        ("B2B-PH-K-S", "jst-ph"),
        ("B4B-XH-A", "jst-xh"),
        ("CONN-SCREW-3PIN-508", "screw-terminal"),
        ("CONN-M12-4PIN", "m12"),
        ("HR911105A", "rj45"),
    ])
    def test_connector_exists(self, db, mpn, sub_type):
        entry = db.find_by_mpn(mpn)
        assert entry is not None, f"Connector {mpn} not found"
        assert entry["category"] == "connector"
        assert entry["sub_type"] == sub_type

    def test_jst_ph_battery(self, db):
        entry = db.find_by_mpn("B2B-PH-K-S")
        caps = entry.get("capabilities", {})
        assert caps.get("pitch_mm") == 2.0
        assert caps.get("application") == "battery"

    def test_rj45_magnetics(self, db):
        entry = db.find_by_mpn("HR911105A")
        caps = entry.get("capabilities", {})
        assert caps.get("integrated_magnetics") is True
        assert caps.get("speed_mbps") == 100

    def test_m12_industrial(self, db):
        entry = db.find_by_mpn("CONN-M12-4PIN")
        caps = entry.get("capabilities", {})
        assert caps.get("ip_rating") == "IP67"
        assert "industrial" in entry.get("tags", [])


# ===================================================================
# P0.5 — Interface Protection Patterns
# ===================================================================


class TestInterfaceProtection:
    """Test per-interface protection patterns."""

    def test_import(self):
        from shared.knowledge.interface_protection import (
            InterfaceProtection, ProtectionComponent,
            INTERFACE_PROTECTION, get_protection, get_all_protections,
            get_mandatory_components, check_protection_completeness,
        )
        assert len(INTERFACE_PROTECTION) == 6

    def test_all_bus_types_defined(self):
        from shared.knowledge.interface_protection import INTERFACE_PROTECTION
        expected = {"USB", "RS485", "CAN", "Ethernet", "I2C_ext", "SPI_ext"}
        assert set(INTERFACE_PROTECTION.keys()) == expected

    @pytest.mark.parametrize("bus_type", [
        "USB", "RS485", "CAN", "Ethernet", "I2C_ext", "SPI_ext",
    ])
    def test_protection_has_components(self, bus_type):
        from shared.knowledge.interface_protection import get_protection
        prot = get_protection(bus_type)
        assert prot is not None
        assert len(prot.mandatory_components) >= 1
        assert len(prot.placement_rules) >= 1

    def test_usb_protection_components(self):
        from shared.knowledge.interface_protection import get_protection
        prot = get_protection("USB")
        roles = {c.role for c in prot.mandatory_components}
        assert "esd_data" in roles
        assert "vbus_ferrite" in roles

    def test_usb_esd_mpn(self):
        from shared.knowledge.interface_protection import get_protection
        prot = get_protection("USB")
        esd = [c for c in prot.mandatory_components if c.role == "esd_data"][0]
        assert "USBLC6-2SC6" in esd.recommended_mpns

    def test_can_protection_has_cmc(self):
        from shared.knowledge.interface_protection import get_protection
        prot = get_protection("CAN")
        roles = {c.role for c in prot.mandatory_components}
        assert "cmc" in roles
        assert "esd_can" in roles

    def test_rs485_bias_resistors(self):
        from shared.knowledge.interface_protection import get_protection
        prot = get_protection("RS485")
        roles = {c.role for c in prot.mandatory_components}
        assert "bias_pullup" in roles
        assert "bias_pulldown" in roles

    def test_get_mandatory_only(self):
        from shared.knowledge.interface_protection import get_mandatory_components
        mandatory = get_mandatory_components("RS485")
        # termination is optional, so should not be in mandatory list
        roles = {c.role for c in mandatory}
        assert "termination" not in roles
        assert "tvs_ab" in roles

    def test_check_completeness_all_placed(self):
        from shared.knowledge.interface_protection import check_protection_completeness
        placed = {"esd_data", "vbus_ferrite", "vbus_cap"}
        missing = check_protection_completeness("USB", placed)
        assert len(missing) == 0

    def test_check_completeness_missing(self):
        from shared.knowledge.interface_protection import check_protection_completeness
        placed = {"vbus_ferrite"}  # missing esd_data and vbus_cap
        missing = check_protection_completeness("USB", placed)
        assert len(missing) == 2
        assert any("esd_data" in m for m in missing)

    def test_nonexistent_bus_type(self):
        from shared.knowledge.interface_protection import get_protection
        assert get_protection("HDMI") is None

    def test_get_all_protections(self):
        from shared.knowledge.interface_protection import get_all_protections
        all_prots = get_all_protections()
        assert len(all_prots) == 6
