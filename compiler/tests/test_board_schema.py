# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Phase 6.2: Hardware Schema Language (YAML → HardwareGraph)."""

from pathlib import Path

from boardsmith_fw.models.board_schema import (
    BoardSchemaBoard,
    BoardSchemaBus,
    BoardSchemaDevice,
    BoardSchemaMCU,
    BoardSchemaPower,
    BoardSchemaRoot,
)
from boardsmith_fw.models.hardware_graph import BusType, MCUFamily
from boardsmith_fw.parser.board_schema_parser import (
    _normalize_gpio,
    parse_board_schema,
    parse_board_schema_text,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"
BOARD_YAML = FIXTURES / "board_schema_esp32" / "board.yaml"


# ---------------------------------------------------------------------------
# Pydantic model tests
# ---------------------------------------------------------------------------

class TestBoardSchemaModels:
    def test_mcu_defaults(self):
        mcu = BoardSchemaMCU(mpn="ESP32-WROOM-32")
        assert mcu.id == "U1"
        assert mcu.family == "auto"

    def test_device_optional_address(self):
        d = BoardSchemaDevice(id="U2", mpn="BME280")
        assert d.address is None

    def test_bus_defaults(self):
        b = BoardSchemaBus(name="I2C_0", type="I2C")
        assert b.devices == []
        assert b.pins == {}

    def test_power_components_list(self):
        p = BoardSchemaPower(name="3V3", voltage=3.3, components=["U2", "U3"])
        assert len(p.components) == 2

    def test_root_schema_version(self):
        root = BoardSchemaRoot(
            boardsmith_fw_schema="1.0",
            board=BoardSchemaBoard(
                mcu=BoardSchemaMCU(mpn="ESP32-WROOM-32"),
            ),
        )
        assert root.boardsmith_fw_schema == "1.0"


# ---------------------------------------------------------------------------
# GPIO normalization
# ---------------------------------------------------------------------------

class TestNormalizeGPIO:
    def test_gpio_prefix_stripped(self):
        assert _normalize_gpio("GPIO21") == "21"

    def test_plain_number(self):
        assert _normalize_gpio("21") == "21"

    def test_stm32_port_pin(self):
        assert _normalize_gpio("PB7") == "PB7"

    def test_gpio_uppercase(self):
        assert _normalize_gpio("GPIO0") == "0"


# ---------------------------------------------------------------------------
# Parser — YAML text
# ---------------------------------------------------------------------------

MINIMAL_YAML = """
boardsmith_fw_schema: "1.0"
board:
  name: Minimal Board
  mcu:
    id: U1
    mpn: ESP32-WROOM-32
    family: esp32
  buses:
    - name: I2C_0
      type: I2C
      clock_hz: 400000
      pins:
        SDA: GPIO21
        SCL: GPIO22
      devices:
        - id: U2
          mpn: BME280
          address: "0x76"
  power:
    - name: 3V3
      voltage: 3.3
      components: [U2]
"""


class TestBoardSchemaParser:
    def test_parse_minimal_yaml(self):
        graph = parse_board_schema_text(MINIMAL_YAML)
        assert graph is not None

    def test_mcu_component_created(self):
        graph = parse_board_schema_text(MINIMAL_YAML)
        mcu_comp = next((c for c in graph.components if c.id == "U1"), None)
        assert mcu_comp is not None
        assert mcu_comp.mpn == "ESP32-WROOM-32"

    def test_device_components_created(self):
        graph = parse_board_schema_text(MINIMAL_YAML)
        ids = [c.id for c in graph.components]
        assert "U2" in ids

    def test_bus_created(self):
        graph = parse_board_schema_text(MINIMAL_YAML)
        assert len(graph.buses) == 1
        assert graph.buses[0].name == "I2C_0"
        assert graph.buses[0].type == BusType.I2C

    def test_bus_slaves(self):
        graph = parse_board_schema_text(MINIMAL_YAML)
        bus = graph.buses[0]
        assert "U2" in bus.slave_component_ids

    def test_bus_master_is_mcu(self):
        graph = parse_board_schema_text(MINIMAL_YAML)
        assert graph.buses[0].master_component_id == "U1"

    def test_pin_mappings(self):
        graph = parse_board_schema_text(MINIMAL_YAML)
        bus = graph.buses[0]
        signals = [pm.signal for pm in bus.pin_mapping]
        assert "SDA" in signals
        assert "SCL" in signals

    def test_gpio_extracted(self):
        graph = parse_board_schema_text(MINIMAL_YAML)
        sda = next(pm for pm in graph.buses[0].pin_mapping if pm.signal == "SDA")
        assert sda.gpio == "21"

    def test_nets_created(self):
        graph = parse_board_schema_text(MINIMAL_YAML)
        net_names = [n.name for n in graph.nets]
        assert "I2C_0_SDA" in net_names
        assert "I2C_0_SCL" in net_names

    def test_power_domain_created(self):
        graph = parse_board_schema_text(MINIMAL_YAML)
        assert len(graph.power_domains) == 1
        assert graph.power_domains[0].name == "3V3"
        assert graph.power_domains[0].voltage == "3.3"

    def test_mcu_info_family(self):
        graph = parse_board_schema_text(MINIMAL_YAML)
        assert graph.mcu is not None
        assert graph.mcu.family == MCUFamily.ESP32

    def test_metadata_counts(self):
        graph = parse_board_schema_text(MINIMAL_YAML)
        assert graph.metadata.total_components == 2  # MCU + BME280
        assert graph.metadata.total_nets == 2  # SDA + SCL
        assert "I2C_0" in graph.metadata.detected_buses


# ---------------------------------------------------------------------------
# MCU family auto-detection
# ---------------------------------------------------------------------------

class TestMCUFamilyAutoDetect:
    def _make_graph(self, mpn: str) -> object:
        yaml_text = f"""
boardsmith_fw_schema: "1.0"
board:
  name: Test
  mcu:
    id: U1
    mpn: {mpn}
    family: auto
"""
        return parse_board_schema_text(yaml_text)

    def test_esp32_detected(self):
        g = self._make_graph("ESP32-WROOM-32")
        assert g.mcu.family == MCUFamily.ESP32

    def test_stm32_detected(self):
        g = self._make_graph("STM32F411CEU6")
        assert g.mcu.family == MCUFamily.STM32

    def test_rp2040_detected(self):
        g = self._make_graph("RP2040")
        assert g.mcu.family == MCUFamily.RP2040

    def test_unknown_family(self):
        g = self._make_graph("ATMEGA328P")
        assert g.mcu.family == MCUFamily.UNKNOWN


# ---------------------------------------------------------------------------
# Multi-bus schema
# ---------------------------------------------------------------------------

MULTI_BUS_YAML = """
boardsmith_fw_schema: "1.0"
board:
  name: Multi-Bus Board
  mcu:
    id: U1
    mpn: ESP32-WROOM-32
    family: esp32
  buses:
    - name: I2C_0
      type: I2C
      clock_hz: 400000
      pins:
        SDA: GPIO21
        SCL: GPIO22
      devices:
        - id: U2
          mpn: BME280
          address: "0x76"
        - id: U3
          mpn: SSD1306
          address: "0x3C"
    - name: SPI_FLASH
      type: SPI
      clock_hz: 10000000
      pins:
        MOSI: GPIO23
        MISO: GPIO19
        SCK: GPIO18
        CS: GPIO5
      devices:
        - id: U4
          mpn: W25Q128JV
    - name: UART_GPS
      type: UART
      baud_rate: 9600
      pins:
        TX: GPIO17
        RX: GPIO16
      devices:
        - id: U5
          mpn: NEO-M8N
  power:
    - name: 3V3
      voltage: 3.3
      components: [U2, U3, U4, U5]
"""


class TestMultiBus:
    def test_three_buses_parsed(self):
        graph = parse_board_schema_text(MULTI_BUS_YAML)
        assert len(graph.buses) == 3

    def test_bus_types_correct(self):
        graph = parse_board_schema_text(MULTI_BUS_YAML)
        types = {b.name: b.type for b in graph.buses}
        assert types["I2C_0"] == BusType.I2C
        assert types["SPI_FLASH"] == BusType.SPI
        assert types["UART_GPS"] == BusType.UART

    def test_i2c_two_slaves(self):
        graph = parse_board_schema_text(MULTI_BUS_YAML)
        i2c = next(b for b in graph.buses if b.name == "I2C_0")
        assert len(i2c.slave_component_ids) == 2

    def test_spi_one_slave(self):
        graph = parse_board_schema_text(MULTI_BUS_YAML)
        spi = next(b for b in graph.buses if b.name == "SPI_FLASH")
        assert len(spi.slave_component_ids) == 1

    def test_all_components_present(self):
        graph = parse_board_schema_text(MULTI_BUS_YAML)
        ids = {c.id for c in graph.components}
        assert ids == {"U1", "U2", "U3", "U4", "U5"}


# ---------------------------------------------------------------------------
# Fixture file test
# ---------------------------------------------------------------------------

class TestBoardSchemaFixture:
    def test_fixture_parses(self):
        graph = parse_board_schema(BOARD_YAML)
        assert graph is not None
        assert len(graph.buses) == 3
        assert graph.mcu.family == MCUFamily.ESP32

    def test_fixture_knowledge_resolves(self):
        from boardsmith_fw.knowledge.resolver import resolve_knowledge
        graph = parse_board_schema(BOARD_YAML)
        knowledge = resolve_knowledge(graph)
        # BME280 and W25Q128JV are in builtin DB
        mpns = {k.name for k in knowledge}
        assert "BME280" in mpns or any("BME" in m for m in mpns)

    def test_fixture_hir_builds(self):
        from boardsmith_fw.analysis.hir_builder import build_hir
        from boardsmith_fw.knowledge.resolver import resolve_knowledge
        graph = parse_board_schema(BOARD_YAML)
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)
        assert len(hir.bus_contracts) == 3
        assert any(bc.i2c for bc in hir.bus_contracts)

    def test_fixture_constraints_run(self):
        from boardsmith_fw.analysis.constraint_solver import solve_constraints
        from boardsmith_fw.analysis.hir_builder import build_hir
        from boardsmith_fw.knowledge.resolver import resolve_knowledge
        graph = parse_board_schema(BOARD_YAML)
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)
        hir.constraints = solve_constraints(hir, graph)
        assert len(hir.constraints) >= 1

    def test_fixture_no_errors(self):
        from boardsmith_fw.analysis.constraint_solver import solve_constraints
        from boardsmith_fw.analysis.hir_builder import build_hir
        from boardsmith_fw.knowledge.resolver import resolve_knowledge
        graph = parse_board_schema(BOARD_YAML)
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)
        hir.constraints = solve_constraints(hir, graph)
        errors = hir.get_errors()
        assert len(errors) == 0, f"Errors: {[e.description for e in errors]}"

    def test_fixture_slave_addresses_populated(self):
        from boardsmith_fw.analysis.hir_builder import build_hir
        from boardsmith_fw.knowledge.resolver import resolve_knowledge
        graph = parse_board_schema(BOARD_YAML)
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)
        i2c = next(bc for bc in hir.bus_contracts if bc.i2c)
        # BME280 @ 0x76 and SSD1306 @ 0x3C
        assert "0x76" in i2c.slave_addresses.values()
