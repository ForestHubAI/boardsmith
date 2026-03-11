# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the three-layer knowledge DB schemas (DBroadmap Phase A).

Layer 1 — Hardware Knowledge: MCU Device Profile + Reference Design Template
Layer 2 — Software Knowledge: Device Software Profile
Layer 3 — Binding Layer: Logical Driver Contract + Library Adapter + Binding Record
"""
from __future__ import annotations

import pytest

from shared.knowledge.mcu_profile_schema import (
    AltFunction,
    AttributeProvenance,
    BootConfig,
    BootModePin,
    BusConfig,
    CapSpec,
    ClockConfig,
    ClockSource,
    ClockSourceType,
    ConnectorSpec,
    DatasheetRef,
    DebugInterface,
    DecouplingRule,
    FirmwareBinding,
    IOElectricalRules,
    KeepoutZone,
    LayoutConstraints,
    MCUDeviceProfile,
    MCUIdentity,
    MCUPinout,
    MCUPowerTree,
    MandatoryComponent,
    NetTemplate,
    PeripheralPatterns,
    I2CPattern,
    PinDefinition,
    PinElectrical,
    PinType,
    PlacementRule,
    PowerDomain,
    PowerInputPattern,
    ProtectionSpec,
    RegulatorOption,
    ReservedPin,
    ResetCircuit,
    RoutingRule,
    TemperatureGrade,
)
from shared.knowledge.refdesign_template_schema import (
    PowerTopology,
    ReferenceDesignTemplate,
    TemplateIdentity,
)
from shared.knowledge.software_profile_schema import (
    DeviceSoftwareProfile,
    DriverFootprint,
    DriverOption,
    DriverQualityScore,
    IntegrationType,
    LicenseCompatibility,
    MaintenanceStatus,
    SourceType,
)
from shared.knowledge.binding_schema import (
    BindingRecord,
    Capability,
    CodeTemplate,
    ContractRegistry,
    FunctionSignature,
    LibraryAdapter,
    LogicalDriverContract,
    Parameter,
)


# ===================================================================
# Layer 1 — Hardware Knowledge Layer
# ===================================================================


class TestMCUIdentity:
    def test_minimal(self):
        ident = MCUIdentity(
            vendor="Espressif",
            family="ESP32-S3",
            series="ESP32-S3-WROOM-1",
            mpn="ESP32-S3-WROOM-1-N16R8",
            package="SMD module",
            pin_count=44,
        )
        assert ident.vendor == "Espressif"
        assert ident.temperature_grade == TemperatureGrade.industrial

    def test_with_datasheet_refs(self):
        ident = MCUIdentity(
            vendor="ST",
            family="STM32G4",
            series="STM32G431",
            mpn="STM32G431CBU6",
            package="UFQFPN48",
            pin_count=48,
            datasheet_refs=[
                DatasheetRef(url="https://example.com/ds.pdf", version="v1.3"),
            ],
        )
        assert len(ident.datasheet_refs) == 1


class TestPinout:
    def test_pin_definition(self):
        pin = PinDefinition(
            pin_name="GPIO21",
            pin_number="33",
            pin_type=PinType.gpio,
            alt_functions=[
                AltFunction(function="I2C0_SDA", available_modes=["standard", "fast"]),
            ],
        )
        assert pin.pin_name == "GPIO21"
        assert len(pin.alt_functions) == 1
        assert pin.boot_strap is False

    def test_reserved_pin(self):
        rp = ReservedPin(pin_name="GPIO6", reason="flash", can_use_as_gpio=False)
        assert rp.reason == "flash"

    def test_pinout_composite(self):
        pinout = MCUPinout(
            pins=[
                PinDefinition(pin_name="VDD", pin_number="1", pin_type=PinType.power),
                PinDefinition(pin_name="GND", pin_number="2", pin_type=PinType.ground),
                PinDefinition(pin_name="GPIO0", pin_number="3", pin_type=PinType.gpio, boot_strap=True),
            ],
            reserved_pins=[
                ReservedPin(pin_name="GPIO6", reason="flash"),
            ],
        )
        assert len(pinout.pins) == 3
        assert pinout.pins[2].boot_strap is True


class TestPowerTree:
    def test_power_domain(self):
        domain = PowerDomain(
            name="VDD",
            nominal_voltage=3.3,
            allowed_range=(3.0, 3.6),
            max_current_draw_ma=500.0,
            decoupling=[
                DecouplingRule(
                    domain="VDD",
                    capacitors=[CapSpec(value="100nF", type="X7R", package="0402")],
                    placement_rule="within 3mm of pin group",
                    pin_group=["VDD1", "VDD2", "VDD3"],
                ),
            ],
        )
        assert domain.nominal_voltage == 3.3
        assert len(domain.decoupling) == 1

    def test_power_input_pattern(self):
        pattern = PowerInputPattern(
            name="usb_5v",
            input_voltage_range=(4.5, 5.5),
            recommended_regulators=[
                RegulatorOption(
                    topology="ldo",
                    recommended_mpns=["AP2112K-3.3"],
                    output_voltage=3.3,
                    max_current_ma=600,
                    dropout_voltage=0.25,
                ),
            ],
        )
        assert pattern.name == "usb_5v"


class TestClocking:
    def test_clock_config(self):
        cfg = ClockConfig(
            main_clock=ClockSource(
                type=ClockSourceType.external_xtal,
                frequency_hz=40_000_000,
                accuracy_ppm=10,
                load_capacitance_pf=10.0,
                osc_pins=["XTAL_P", "XTAL_N"],
                required_caps=[CapSpec(value="10pF", type="C0G", package="0402", quantity=2)],
            ),
            rtc_clock=ClockSource(
                type=ClockSourceType.external_xtal,
                frequency_hz=32_768,
                accuracy_ppm=20,
                osc_pins=["XTAL32K_P", "XTAL32K_N"],
            ),
            safe_default_mhz=40,
        )
        assert cfg.main_clock.frequency_hz == 40_000_000
        assert cfg.safe_default_mhz == 40


class TestBootConfig:
    def test_boot_config(self):
        boot = BootConfig(
            reset_circuit=ResetCircuit(
                nrst_pin="EN",
                recommended_pullup_ohm=10000,
                cap_to_gnd_nf=100,
            ),
            boot_mode_pins=[
                BootModePin(
                    pin="GPIO0",
                    normal_boot_state="high",
                    pull_resistor="pull_up_10k",
                    notes="Hold LOW during reset for UART bootloader",
                ),
            ],
            programming_mode_entry=[
                "Hold GPIO0 LOW",
                "Assert EN LOW for 100ms",
                "Release EN",
                "Release GPIO0 after 50ms",
            ],
        )
        assert boot.reset_circuit.nrst_pin == "EN"
        assert len(boot.boot_mode_pins) == 1


class TestDebugInterface:
    def test_swd(self):
        dbg = DebugInterface(
            protocol="SWD",
            pins={"SWDIO": "PA13", "SWCLK": "PA14", "NRST": "NRST"},
            recommended_connector=ConnectorSpec(
                name="ARM SWD 2x5 1.27mm",
                footprint="PinHeader_2x05_P1.27mm_Vertical",
                pinout={"SWDIO": 2, "SWCLK": 4, "GND": 3, "VTref": 1},
            ),
        )
        assert dbg.protocol == "SWD"
        assert dbg.recommended_connector is not None


class TestMandatoryComponents:
    def test_decoupling_cap(self):
        mc = MandatoryComponent(
            component_type="cap",
            value="100nF",
            spec="X7R 0402 ±10%",
            quantity_rule="per_vdd_pin",
            connectivity=NetTemplate(net_name="VDD", connected_pins=["VDD1", "GND"]),
            placement="within 3mm of VDD pin",
            rationale="Datasheet Section 4.2: 100nF ceramic per VDD",
        )
        assert mc.quantity_rule == "per_vdd_pin"


class TestPeripheralPatterns:
    def test_i2c_pattern(self):
        pp = PeripheralPatterns(
            i2c=I2CPattern(
                pullup_value_rule="4.7kΩ for ≤100kHz, 2.2kΩ for 400kHz, 1kΩ for 1MHz",
                max_bus_capacitance_pf=400,
                max_devices_per_bus=8,
            ),
        )
        assert pp.i2c is not None
        assert pp.i2c.max_bus_capacitance_pf == 400


class TestMCUDeviceProfile:
    """Test the complete composite model."""

    def test_minimal_profile(self):
        """A profile with only required fields."""
        profile = MCUDeviceProfile(
            identity=MCUIdentity(
                vendor="Espressif",
                family="ESP32-S3",
                series="ESP32-S3-WROOM-1",
                mpn="ESP32-S3-WROOM-1-N16R8",
                package="SMD module",
                pin_count=44,
            ),
        )
        assert profile.identity.mpn == "ESP32-S3-WROOM-1-N16R8"
        assert profile.pinout.pins == []
        assert profile.power.power_domains == []

    def test_json_roundtrip(self):
        profile = MCUDeviceProfile(
            identity=MCUIdentity(
                vendor="RP",
                family="RP2040",
                series="RP2040",
                mpn="RP2040",
                package="QFN-56",
                pin_count=56,
            ),
            clock=ClockConfig(
                main_clock=ClockSource(
                    type=ClockSourceType.external_xtal,
                    frequency_hz=12_000_000,
                ),
                safe_default_mhz=12,
            ),
        )
        json_str = profile.model_dump_json()
        restored = MCUDeviceProfile.model_validate_json(json_str)
        assert restored.identity.mpn == "RP2040"
        assert restored.clock is not None
        assert restored.clock.main_clock.frequency_hz == 12_000_000

    def test_provenance(self):
        prov = AttributeProvenance(
            source_ref="ESP32-S3 Datasheet v1.3, Section 4.2.1",
            source_type="datasheet",
            verification_status="reviewed",
            confidence_score=0.95,
            last_validated_date="2026-01-15",
            validated_against="ESP-IDF v5.2",
        )
        assert prov.confidence_score == 0.95


# ===================================================================
# Layer 1 — Reference Design Template
# ===================================================================


class TestReferenceDesignTemplate:
    def test_minimal(self):
        tmpl = ReferenceDesignTemplate(
            identity=TemplateIdentity(
                name="USB Dev Board",
                applicable_families=["ESP32-S3", "RP2040"],
                application_context="prototyping",
            ),
        )
        assert tmpl.identity.name == "USB Dev Board"

    def test_with_power_topology(self):
        tmpl = ReferenceDesignTemplate(
            identity=TemplateIdentity(
                name="Battery Sensor Node",
                applicable_families=["ESP32-S3"],
                board_size_mm=(30, 25),
            ),
            power=PowerTopology(
                input_pattern=PowerInputPattern(
                    name="lipo_3v7",
                    input_voltage_range=(3.0, 4.2),
                    recommended_regulators=[
                        RegulatorOption(
                            topology="ldo",
                            output_voltage=3.3,
                            max_current_ma=300,
                        ),
                    ],
                ),
            ),
        )
        assert tmpl.power is not None


# ===================================================================
# Layer 2 — Software Knowledge
# ===================================================================


class TestDriverQualityScore:
    def test_composite_calculation(self):
        score = DriverQualityScore(
            test_pass_rate=0.95,
            maintenance_factor=0.90,
            ecosystem_support=0.80,
            community_adoption=0.70,
            license_score=1.0,
        )
        expected = 0.95 * 0.30 + 0.90 * 0.25 + 0.80 * 0.20 + 0.70 * 0.10 + 1.0 * 0.15
        assert abs(score.composite - expected) < 1e-9

    def test_default_composite(self):
        score = DriverQualityScore()
        assert 0.0 <= score.composite <= 1.0


class TestDriverOption:
    def test_basic_driver(self):
        driver = DriverOption(
            name="Bosch Official C Driver",
            key="bosch_official",
            source_type=SourceType.git,
            source_url="https://github.com/BoschSensortec/BME280_driver",
            license="BSD-3-Clause",
            maturity="high",
            ecosystem=["baremetal", "Zephyr", "ESP-IDF"],
            supported_targets=["esp32", "stm32", "rp2040", "nrf52"],
            footprint=DriverFootprint(flash_bytes=8200, ram_bytes=512),
            quality_score=DriverQualityScore(
                test_pass_rate=0.95,
                maintenance_factor=0.90,
                ecosystem_support=0.80,
                community_adoption=0.70,
                license_score=1.0,
            ),
        )
        assert driver.computed_quality > 0.8
        assert driver.license_compatibility == LicenseCompatibility.compatible


class TestDeviceSoftwareProfile:
    @pytest.fixture
    def bme280_profile(self):
        return DeviceSoftwareProfile(
            component_mpn="BME280",
            protocol="I2C",
            driver_options=[
                DriverOption(
                    name="Bosch Official",
                    key="bosch_official",
                    source_type=SourceType.git,
                    source_url="https://github.com/BoschSensortec/BME280_driver",
                    license="BSD-3-Clause",
                    supported_targets=["esp32", "stm32", "rp2040"],
                ),
                DriverOption(
                    name="Adafruit BME280",
                    key="adafruit",
                    source_type=SourceType.git,
                    source_url="https://github.com/adafruit/Adafruit_BME280_Library",
                    license="MIT",
                    supported_targets=["esp32", "rp2040"],
                    integration_type=IntegrationType.package_manager,
                ),
            ],
            default_driver_key="bosch_official",
            api_contract_id="temperature_sensor_v1",
        )

    def test_get_default_driver(self, bme280_profile):
        default = bme280_profile.get_default_driver()
        assert default is not None
        assert default.key == "bosch_official"

    def test_get_drivers_for_target(self, bme280_profile):
        esp32_drivers = bme280_profile.get_drivers_for_target("esp32")
        assert len(esp32_drivers) == 2
        stm32_drivers = bme280_profile.get_drivers_for_target("stm32")
        assert len(stm32_drivers) == 1

    def test_compatible_drivers(self, bme280_profile):
        compatible = bme280_profile.get_compatible_drivers()
        assert len(compatible) == 2

    def test_json_roundtrip(self, bme280_profile):
        json_str = bme280_profile.model_dump_json()
        restored = DeviceSoftwareProfile.model_validate_json(json_str)
        assert restored.component_mpn == "BME280"
        assert len(restored.driver_options) == 2


# ===================================================================
# Layer 3 — Binding Layer
# ===================================================================


class TestLogicalDriverContract:
    def test_temperature_sensor_contract(self):
        contract = LogicalDriverContract(
            contract_id="temperature_sensor_v1",
            contract_version="1.0.0",
            category="sensor",
            description="Temperature/humidity/pressure sensor contract",
            capabilities=[
                Capability(name="init", return_type="int", required=True),
                Capability(name="read_temperature", return_type="float", required=True),
                Capability(name="read_humidity", return_type="float", required=False),
                Capability(name="read_pressure", return_type="float", required=False),
            ],
            init_signature=FunctionSignature(
                name="sensor_init",
                parameters=[
                    Parameter(name="bus_handle", type="void*"),
                    Parameter(name="address", type="uint8_t", default="0x76"),
                ],
                return_type="int",
            ),
        )
        assert len(contract.capabilities) == 4
        required = [c for c in contract.capabilities if c.required]
        assert len(required) == 2


class TestLibraryAdapter:
    def test_bme280_bosch_adapter(self):
        adapter = LibraryAdapter(
            adapter_id="bme280_bosch_espidf_v1",
            contract_id="temperature_sensor_v1",
            driver_option_key="bosch_official",
            target_sdk="esp-idf",
            capability_mappings={
                "read_temperature": CodeTemplate(
                    template="bme280_get_sensor_data(BME280_ALL, &data, &dev); return data.temperature;",
                    includes=["bme280.h"],
                ),
                "read_humidity": CodeTemplate(
                    template="bme280_get_sensor_data(BME280_ALL, &data, &dev); return data.humidity;",
                    includes=["bme280.h"],
                ),
                "read_pressure": CodeTemplate(
                    template="bme280_get_sensor_data(BME280_ALL, &data, &dev); return data.pressure;",
                    includes=["bme280.h"],
                ),
            },
            required_includes=["bme280.h", "bme280_defs.h"],
            required_defines=["BME280_FLOAT_ENABLE"],
            init_template=(
                "struct bme280_dev dev;\n"
                "dev.intf = BME280_I2C_INTF;\n"
                "dev.read = user_i2c_read;\n"
                "dev.write = user_i2c_write;\n"
                "dev.delay_us = user_delay_us;\n"
                "bme280_init(&dev);"
            ),
        )
        assert "read_temperature" in adapter.capability_mappings
        assert len(adapter.required_includes) == 2


class TestBindingRecord:
    def test_concrete_binding(self):
        record = BindingRecord(
            component_mpn="BME280",
            hardware_contract="i2c_sensor_v1",
            software_contract="temperature_sensor_v1",
            selected_driver="bosch_bme280_c_v3.5.1",
            selected_adapter="bme280_bosch_espidf_v1",
            target="esp32",
            sdk="esp-idf",
            pinned_version="v3.5.1",
            integration_method=IntegrationType.source_embed,
        )
        assert record.target == "esp32"
        assert record.pinned_version == "v3.5.1"


class TestContractRegistry:
    @pytest.fixture
    def registry(self):
        reg = ContractRegistry()
        reg.register_contract(
            LogicalDriverContract(
                contract_id="temperature_sensor_v1",
                category="sensor",
                capabilities=[
                    Capability(name="read_temperature", return_type="float"),
                ],
            )
        )
        reg.register_adapter(
            LibraryAdapter(
                adapter_id="bme280_bosch_espidf_v1",
                contract_id="temperature_sensor_v1",
                driver_option_key="bosch_official",
                target_sdk="esp-idf",
                capability_mappings={
                    "read_temperature": CodeTemplate(
                        template="bme280_get_sensor_data(BME280_ALL, &data, &dev); return data.temperature;",
                    ),
                },
            )
        )
        return reg

    def test_resolve_adapter(self, registry):
        adapter = registry.resolve_adapter("temperature_sensor_v1", "esp-idf")
        assert adapter is not None
        assert adapter.adapter_id == "bme280_bosch_espidf_v1"

    def test_resolve_adapter_not_found(self, registry):
        adapter = registry.resolve_adapter("temperature_sensor_v1", "zephyr")
        assert adapter is None

    def test_resolve_code(self, registry):
        code = registry.resolve_code("temperature_sensor_v1", "read_temperature", "esp-idf")
        assert code is not None
        assert "bme280_get_sensor_data" in code.template

    def test_resolve_code_not_found(self, registry):
        code = registry.resolve_code("temperature_sensor_v1", "read_humidity", "esp-idf")
        assert code is None
