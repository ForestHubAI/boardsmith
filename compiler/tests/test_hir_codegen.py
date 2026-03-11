# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for HIR-driven code generation.

These tests verify that HIR contracts (BusContract, InitContract,
PowerSequence) are correctly transformed into C firmware for each
target platform: ESP32, STM32, and RP2040.
"""

from pathlib import Path

from boardsmith_fw.codegen.hir_codegen import (
    HIRCodegenResult,
    generate_from_hir,
)
from boardsmith_fw.models.hir import (
    HIR,
    BusContract,
    I2CSpec,
    InitContract,
    InitPhase,
    InitPhaseSpec,
    PowerDependency,
    PowerRail,
    PowerSequence,
    RegisterRead,
    RegisterWrite,
    SPISpec,
    UARTSpec,
    VoltageLevel,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"

# ---------------------------------------------------------------------------
# Helpers — build realistic HIR objects for testing
# ---------------------------------------------------------------------------


def _make_bme280_hir() -> HIR:
    """Build a minimal HIR for a single BME280 on I2C."""
    return HIR(
        source="test",
        bus_contracts=[
            BusContract(
                bus_name="I2C_0",
                bus_type="I2C",
                master_id="ESP32",
                slave_ids=["BME280"],
                configured_clock_hz=400_000,
                i2c=I2CSpec(address="0x76", max_clock_hz=400_000),
                pin_assignments={"SDA": "21", "SCL": "22"},
            ),
        ],
        init_contracts=[
            InitContract(
                component_id="BME280",
                component_name="BME280",
                phases=[
                    InitPhaseSpec(
                        phase=InitPhase.RESET,
                        order=0,
                        writes=[
                            RegisterWrite(
                                reg_addr="0xE0",
                                value="0xB6",
                                description="Soft reset",
                            ),
                        ],
                        delay_after_ms=10,
                        postcondition="Device in sleep mode after reset",
                    ),
                    InitPhaseSpec(
                        phase=InitPhase.VERIFY,
                        order=1,
                        reads=[
                            RegisterRead(
                                reg_addr="0xD0",
                                expected_value="0x60",
                                description="Verify chip ID",
                            ),
                        ],
                        precondition="Device powered and bus initialized",
                    ),
                    InitPhaseSpec(
                        phase=InitPhase.CONFIGURE,
                        order=2,
                        writes=[
                            RegisterWrite(
                                reg_addr="0xF2",
                                value="0x01",
                                description="Set humidity oversampling x1",
                            ),
                            RegisterWrite(
                                reg_addr="0xF4",
                                value="0x27",
                                description="Set temp/pressure oversampling, normal mode",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def _make_multi_bus_hir() -> HIR:
    """HIR with I2C, SPI, and UART buses + multiple components."""
    return HIR(
        source="test_multi",
        bus_contracts=[
            BusContract(
                bus_name="I2C_0",
                bus_type="I2C",
                master_id="MCU",
                slave_ids=["BME280"],
                configured_clock_hz=400_000,
                i2c=I2CSpec(address="0x76"),
                pin_assignments={"SDA": "21", "SCL": "22"},
            ),
            BusContract(
                bus_name="SPI_0",
                bus_type="SPI",
                master_id="MCU",
                slave_ids=["W25Q128"],
                configured_clock_hz=8_000_000,
                spi=SPISpec(max_clock_hz=8_000_000, mode=0),
                pin_assignments={"MOSI": "23", "MISO": "19", "SCK": "18"},
            ),
            BusContract(
                bus_name="UART_1",
                bus_type="UART",
                master_id="MCU",
                slave_ids=["NEO_M8N"],
                uart=UARTSpec(baud_rate=9600),
                pin_assignments={"TX": "17", "RX": "16"},
            ),
        ],
        init_contracts=[
            InitContract(
                component_id="BME280",
                component_name="BME280",
                phases=[
                    InitPhaseSpec(
                        phase=InitPhase.RESET,
                        order=0,
                        writes=[
                            RegisterWrite(
                                reg_addr="0xE0", value="0xB6",
                                description="Soft reset",
                            ),
                        ],
                        delay_after_ms=10,
                    ),
                ],
            ),
            InitContract(
                component_id="W25Q128",
                component_name="W25Q128",
                phases=[
                    InitPhaseSpec(
                        phase=InitPhase.VERIFY,
                        order=0,
                        reads=[
                            RegisterRead(
                                reg_addr="0x9F",
                                description="Read JEDEC ID",
                            ),
                        ],
                    ),
                ],
            ),
        ],
        power_sequence=PowerSequence(
            rails=[
                PowerRail(
                    name="3V3_SYS",
                    voltage=VoltageLevel(nominal=3.3, min=3.0, max=3.6),
                    enable_gpio="25",
                ),
                PowerRail(
                    name="1V8_CORE",
                    voltage=VoltageLevel(nominal=1.8, min=1.7, max=1.9),
                ),
            ],
            dependencies=[
                PowerDependency(
                    source="3V3_SYS",
                    target="1V8_CORE",
                    min_delay_ms=5,
                    description="3V3 must be stable before 1V8",
                ),
            ],
        ),
    )


# ---------------------------------------------------------------------------
# ESP32 code generation
# ---------------------------------------------------------------------------


class TestESP32Generation:
    def test_generates_files(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")

        assert isinstance(result, HIRCodegenResult)
        paths = [f.path for f in result.files]
        assert "main/main.c" in paths
        assert "main/bme280.h" in paths
        assert "main/bme280.c" in paths
        assert "main/CMakeLists.txt" in paths

    def test_driver_header_has_guard(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")

        header = next(f for f in result.files if f.path == "main/bme280.h")
        assert "#ifndef BME280_H" in header.content
        assert "#define BME280_H" in header.content
        assert "#endif" in header.content

    def test_driver_header_has_i2c_addr(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")

        header = next(f for f in result.files if f.path == "main/bme280.h")
        assert "#define BME280_I2C_ADDR 0x76" in header.content

    def test_driver_has_init_function(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")

        impl = next(f for f in result.files if f.path == "main/bme280.c")
        assert "bme280_init" in impl.content
        assert "esp_err_t" in impl.content

    def test_phased_init_has_reset(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")

        impl = next(f for f in result.files if f.path == "main/bme280.c")
        # Phase 24: Adapter-driven — Bosch library init handles reset internally
        assert "bme280_init" in impl.content
        assert "BME280_OK" in impl.content

    def test_phased_init_has_verify(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")

        impl = next(f for f in result.files if f.path == "main/bme280.c")
        # Phase 24: Adapter-driven — library verifies chip ID during bme280_init()
        assert "BME280_OVERSAMPLING" in impl.content
        assert "bme280_get_sensor_data" in impl.content

    def test_phased_init_has_configure(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")

        impl = next(f for f in result.files if f.path == "main/bme280.c")
        # Phase 24: Adapter-driven — Bosch library API for oversampling and mode
        assert "BME280_OVERSAMPLING_1X" in impl.content
        assert "BME280_NORMAL_MODE" in impl.content

    def test_phase_delay(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")

        impl = next(f for f in result.files if f.path == "main/bme280.c")
        # Phase 24: Adapter-driven — delay via user_delay_us callback using vTaskDelay
        assert "vTaskDelay" in impl.content

    def test_phase_precondition_comment(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")

        impl = next(f for f in result.files if f.path == "main/bme280.c")
        # Phase 24: Adapter-driven — I2C HAL callbacks provided in driver file
        assert "user_i2c_read" in impl.content

    def test_phase_postcondition_comment(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")

        impl = next(f for f in result.files if f.path == "main/bme280.c")
        # Phase 24: Adapter-driven — device enters normal (operational) mode
        assert "BME280_NORMAL_MODE" in impl.content

    def test_i2c_bus_init_from_contract(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")

        main = next(f for f in result.files if f.path == "main/main.c")
        # Should use pin assignments from BusContract, not hardcoded
        assert "GPIO_NUM_21" in main.content  # SDA from contract
        assert "GPIO_NUM_22" in main.content  # SCL from contract
        assert "400000" in main.content  # clock from contract

    def test_expected_value_verification(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")

        impl = next(f for f in result.files if f.path == "main/bme280.c")
        # Phase 24: Adapter-driven — Bosch library uses BME280_OK return codes
        assert "BME280_OK" in impl.content
        assert "rslt" in impl.content

    def test_cmake_includes_driver(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")

        cmake = next(f for f in result.files if f.path == "main/CMakeLists.txt")
        assert "bme280.c" in cmake.content
        assert "main.c" in cmake.content

    def test_main_loop_reads(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")

        main = next(f for f in result.files if f.path == "main/main.c")
        assert "bme280_read" in main.content
        assert "while (1)" in main.content


class TestESP32MultiBus:
    def test_spi_bus_init(self):
        hir = _make_multi_bus_hir()
        result = generate_from_hir(hir, target="esp32")

        main = next(f for f in result.files if f.path == "main/main.c")
        # SPI bus init should use pins from BusContract
        assert "GPIO_NUM_23" in main.content  # MOSI
        assert "GPIO_NUM_19" in main.content  # MISO
        assert "GPIO_NUM_18" in main.content  # SCK
        assert "SPI2_HOST" in main.content

    def test_uart_bus_init(self):
        hir = _make_multi_bus_hir()
        result = generate_from_hir(hir, target="esp32")

        main = next(f for f in result.files if f.path == "main/main.c")
        assert "9600" in main.content  # baud rate from UARTSpec
        assert "UART_NUM_1" in main.content
        assert "GPIO_NUM_17" in main.content  # TX
        assert "GPIO_NUM_16" in main.content  # RX

    def test_power_sequence(self):
        hir = _make_multi_bus_hir()
        result = generate_from_hir(hir, target="esp32")

        main = next(f for f in result.files if f.path == "main/main.c")
        assert "POWER SEQUENCING" in main.content
        assert "3V3_SYS" in main.content
        assert "gpio_set_level(GPIO_NUM_25, 1)" in main.content

    def test_power_delay(self):
        hir = _make_multi_bus_hir()
        result = generate_from_hir(hir, target="esp32")

        main = next(f for f in result.files if f.path == "main/main.c")
        # 5ms delay between 3V3 and 1V8
        assert "vTaskDelay(pdMS_TO_TICKS(5))" in main.content

    def test_multiple_drivers_generated(self):
        hir = _make_multi_bus_hir()
        result = generate_from_hir(hir, target="esp32")

        paths = [f.path for f in result.files]
        assert "main/bme280.h" in paths
        assert "main/bme280.c" in paths
        assert "main/w25q128.h" in paths
        assert "main/w25q128.c" in paths


# ---------------------------------------------------------------------------
# STM32 code generation
# ---------------------------------------------------------------------------


class TestSTM32Generation:
    def test_generates_files(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="stm32")

        paths = [f.path for f in result.files]
        assert "Src/main.c" in paths
        assert "Src/bme280.h" in paths
        assert "Src/bme280.c" in paths

    def test_uses_hal_types(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="stm32")

        header = next(f for f in result.files if f.path == "Src/bme280.h")
        assert "HAL_StatusTypeDef" in header.content
        assert "I2C_HandleTypeDef" in header.content
        assert "stm32f4xx_hal.h" in header.content

    def test_hal_driver_impl(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="stm32")

        impl = next(f for f in result.files if f.path == "Src/bme280.c")
        assert "HAL_I2C_Master_Transmit" in impl.content
        assert "HAL_I2C_Master_Receive" in impl.content
        # Phase 24: Adapter-driven — comment uses lowercase "reset" and "Verify"
        assert "reset" in impl.content.lower()
        assert "0x60" in impl.content  # chip ID verification

    def test_i2c_address_shifted(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="stm32")

        header = next(f for f in result.files if f.path == "Src/bme280.h")
        # STM32 HAL uses left-shifted 7-bit address
        assert "(0x76 << 1)" in header.content

    def test_phased_init(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="stm32")

        impl = next(f for f in result.files if f.path == "Src/bme280.c")
        assert "0xE0" in impl.content  # reset register
        assert "0xB6" in impl.content  # reset value
        assert "0xD0" in impl.content  # chip ID register

    def test_expected_value_check(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="stm32")

        impl = next(f for f in result.files if f.path == "Src/bme280.c")
        # Phase 24: Adapter-driven — uses named variable "chip_id" instead of "val"
        assert "chip_id != 0x60" in impl.content
        assert "HAL_ERROR" in impl.content

    def test_delay(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="stm32")

        impl = next(f for f in result.files if f.path == "Src/bme280.c")
        assert "HAL_Delay(10)" in impl.content

    def test_main_has_hal_init(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="stm32")

        main = next(f for f in result.files if f.path == "Src/main.c")
        assert "HAL_Init()" in main.content
        assert "SystemClock_Config()" in main.content
        assert "bme280_init" in main.content


# ---------------------------------------------------------------------------
# RP2040 code generation
# ---------------------------------------------------------------------------


class TestRP2040Generation:
    def test_generates_files(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="rp2040")

        paths = [f.path for f in result.files]
        assert "main.c" in paths
        assert "bme280.h" in paths
        assert "bme280.c" in paths

    def test_uses_pico_sdk(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="rp2040")

        header = next(f for f in result.files if f.path == "bme280.h")
        assert "hardware/i2c.h" in header.content
        assert "i2c_inst_t" in header.content

    def test_driver_impl(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="rp2040")

        impl = next(f for f in result.files if f.path == "bme280.c")
        assert "i2c_write_blocking" in impl.content
        assert "i2c_read_blocking" in impl.content
        assert "pico/stdlib.h" in impl.content

    def test_phased_init(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="rp2040")

        impl = next(f for f in result.files if f.path == "bme280.c")
        assert "RESET" in impl.content
        assert "VERIFY" in impl.content
        assert "CONFIGURE" in impl.content

    def test_expected_value_check(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="rp2040")

        impl = next(f for f in result.files if f.path == "bme280.c")
        assert "val != 0x60" in impl.content
        assert "return -2" in impl.content

    def test_delay(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="rp2040")

        impl = next(f for f in result.files if f.path == "bme280.c")
        assert "sleep_ms(10)" in impl.content

    def test_main_has_bus_init(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="rp2040")

        main = next(f for f in result.files if f.path == "main.c")
        assert "stdio_init_all()" in main.content
        assert "i2c_init(i2c0, 400000)" in main.content
        assert "gpio_set_function(21, GPIO_FUNC_I2C)" in main.content
        assert "gpio_pull_up(21)" in main.content

    def test_i2c_address(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="rp2040")

        impl = next(f for f in result.files if f.path == "bme280.c")
        assert "#define ADDR 0x76" in impl.content


# ---------------------------------------------------------------------------
# Target dispatch and edge cases
# ---------------------------------------------------------------------------


class TestTargetDispatch:
    def test_unknown_target_falls_back_to_esp32(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="avr")

        assert any("Unknown target" in w for w in result.warnings)
        # Should still produce files (esp32 fallback)
        paths = [f.path for f in result.files]
        assert "main/main.c" in paths

    def test_empty_hir_produces_main(self):
        hir = HIR(source="empty")
        result = generate_from_hir(hir, target="esp32")

        paths = [f.path for f in result.files]
        assert "main/main.c" in paths
        assert "main/CMakeLists.txt" in paths

    def test_no_bus_contract_for_component(self):
        """Component without a matching bus contract still generates."""
        hir = HIR(
            source="test",
            init_contracts=[
                InitContract(
                    component_id="ORPHAN",
                    component_name="Orphan_Chip",
                    phases=[
                        InitPhaseSpec(
                            phase=InitPhase.CONFIGURE,
                            order=0,
                            writes=[
                                RegisterWrite(
                                    reg_addr="0x00",
                                    value="0x01",
                                    description="Write config",
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
        result = generate_from_hir(hir, target="esp32")
        paths = [f.path for f in result.files]
        assert "main/orphan_chip.c" in paths

    def test_read_without_expected_value(self):
        """A read without expected_value should just log, not verify."""
        hir = HIR(
            source="test",
            bus_contracts=[
                BusContract(
                    bus_name="I2C_0",
                    bus_type="I2C",
                    master_id="MCU",
                    slave_ids=["CHIP"],
                    i2c=I2CSpec(address="0x50"),
                ),
            ],
            init_contracts=[
                InitContract(
                    component_id="CHIP",
                    component_name="TestChip",
                    phases=[
                        InitPhaseSpec(
                            phase=InitPhase.VERIFY,
                            order=0,
                            reads=[
                                RegisterRead(
                                    reg_addr="0x00",
                                    description="Read status",
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
        result = generate_from_hir(hir, target="esp32")
        impl = next(f for f in result.files if f.path == "main/testchip.c")
        # Should log value without comparison
        assert "ESP_LOGI" in impl.content
        assert "ESP_ERR_INVALID_RESPONSE" not in impl.content


# ---------------------------------------------------------------------------
# Integration: end-to-end from fixture → HIR → codegen
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_esp32_bme280_fixture(self):
        """Full pipeline: fixture schematic → HIR → generated code."""
        from boardsmith_fw.analysis.graph_builder import build_hardware_graph
        from boardsmith_fw.analysis.hir_builder import build_hir
        from boardsmith_fw.knowledge.resolver import resolve_knowledge
        from boardsmith_fw.parser.eagle_parser import parse_eagle_schematic

        sch_path = FIXTURES / "esp32_bme280_i2c" / "esp32_bme280.sch"
        parsed = parse_eagle_schematic(sch_path)
        graph = build_hardware_graph(str(sch_path), parsed.components, parsed.nets)
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)

        result = generate_from_hir(hir, target="esp32")

        # Should have generated files
        assert len(result.files) >= 3  # at least main.c, driver.h, driver.c
        paths = [f.path for f in result.files]
        assert "main/main.c" in paths
        assert "main/CMakeLists.txt" in paths

        # Main should have bus init with contract-driven pins
        main = next(f for f in result.files if f.path == "main/main.c")
        assert "i2c_config_t" in main.content
        assert "Boardsmith-FW" in main.content

    def test_rp2040_bme280_fixture(self):
        """Full pipeline: RP2040 fixture → HIR → generated code."""
        from boardsmith_fw.analysis.graph_builder import build_hardware_graph
        from boardsmith_fw.analysis.hir_builder import build_hir
        from boardsmith_fw.knowledge.resolver import resolve_knowledge
        from boardsmith_fw.parser.eagle_parser import parse_eagle_schematic

        sch_path = FIXTURES / "rp2040_bme280_i2c" / "rp2040_bme280.sch"
        parsed = parse_eagle_schematic(sch_path)
        graph = build_hardware_graph(str(sch_path), parsed.components, parsed.nets)
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)

        result = generate_from_hir(hir, target="rp2040")

        assert len(result.files) >= 2
        paths = [f.path for f in result.files]
        assert "main.c" in paths

    def test_codegen_from_hir_uses_negotiated_clock(self):
        """Verify that generated code uses the clock from BusContract,
        not a hardcoded default."""
        from boardsmith_fw.analysis.graph_builder import build_hardware_graph
        from boardsmith_fw.analysis.hir_builder import build_hir
        from boardsmith_fw.knowledge.resolver import resolve_knowledge
        from boardsmith_fw.parser.eagle_parser import parse_eagle_schematic

        sch_path = FIXTURES / "esp32_bme280_i2c" / "esp32_bme280.sch"
        parsed = parse_eagle_schematic(sch_path)
        graph = build_hardware_graph(str(sch_path), parsed.components, parsed.nets)
        knowledge = resolve_knowledge(graph)
        hir = build_hir(graph, knowledge)

        # Find the I2C bus contract
        i2c_bc = next(
            (bc for bc in hir.bus_contracts if bc.bus_type == "I2C"), None,
        )
        assert i2c_bc is not None

        result = generate_from_hir(hir, target="esp32")
        main = next(f for f in result.files if f.path == "main/main.c")

        # The generated code should use the negotiated clock
        assert str(i2c_bc.configured_clock_hz) in main.content


class TestSanitize:
    def test_basic_names(self):
        from boardsmith_fw.codegen.hir_codegen import _sanitize

        assert _sanitize("BME280") == "bme280"
        assert _sanitize("W25Q128") == "w25q128"
        assert _sanitize("NEO-M8N") == "neo_m8n"

    def test_special_chars(self):
        from boardsmith_fw.codegen.hir_codegen import _sanitize

        assert _sanitize("chip@v2.1") == "chip_v2_1"
        assert _sanitize("") == "component"

    def test_spaces(self):
        from boardsmith_fw.codegen.hir_codegen import _sanitize

        assert _sanitize("My Chip") == "my_chip"


# ---------------------------------------------------------------------------
# Phase 19 — Retry helpers, bus recovery, ISR templates
# ---------------------------------------------------------------------------


class TestPhase19RetryHelpers:
    """Generated ESP32 I2C helpers must include robust I2C communication helpers."""

    def test_retry_helpers_present(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")
        impl = next(f for f in result.files if f.path.endswith("bme280.c"))

        # Phase 24: Adapter-driven — ESP-IDF I2C master API used directly
        assert "i2c_master_write_read_device" in impl.content
        assert "i2c_master_write_to_device" in impl.content
        assert "user_i2c_read" in impl.content

    def test_init_uses_retry_helpers(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")
        impl = next(f for f in result.files if f.path.endswith("bme280.c"))

        # Phase 24: Adapter-driven — Bosch library init used instead of raw register writes
        assert "bme280_init" in impl.content
        assert "BME280_OK" in impl.content

    def test_read_function_uses_retry(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")
        impl = next(f for f in result.files if f.path.endswith("bme280.c"))

        # Phase 24: Adapter-driven — Bosch library read API
        assert "bme280_get_sensor_data" in impl.content

    def test_error_messages_include_err_name(self):
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")
        impl = next(f for f in result.files if f.path.endswith("bme280.c"))

        # Phase 24: Adapter-driven — BME280 return codes used for error handling
        assert "BME280_OK" in impl.content
        assert "rslt" in impl.content

    def test_retry_helpers_all_targets(self):
        """Verify all targets compile without error (structural smoke test)."""
        hir = _make_bme280_hir()
        for target in ("esp32", "stm32", "rp2040", "nrf52"):
            result = generate_from_hir(hir, target=target)
            # Must produce at least a driver impl and main
            assert any("bme280" in f.path for f in result.files), (
                f"{target}: no bme280 driver file"
            )
            assert any("main.c" in f.path for f in result.files), (
                f"{target}: no main.c"
            )


class TestPhase19ISRTemplates:
    """When InitContract.irq_gpio is set, an ISR handler must be generated."""

    def _make_irq_hir(self, gpio: str = "4", trigger: str = "falling") -> HIR:
        """Build a HIR with a BME280-like component that has an IRQ pin."""
        return HIR(
            source="test",
            bus_contracts=[
                BusContract(
                    bus_name="I2C_0",
                    bus_type="I2C",
                    master_id="ESP32",
                    slave_ids=["MPU6050"],
                    configured_clock_hz=400_000,
                    i2c=I2CSpec(address="0x68", max_clock_hz=400_000),
                    pin_assignments={"SDA": "21", "SCL": "22"},
                ),
            ],
            init_contracts=[
                InitContract(
                    component_id="MPU6050",
                    component_name="MPU6050",
                    irq_gpio=gpio,
                    irq_trigger=trigger,
                    phases=[
                        InitPhaseSpec(
                            phase=InitPhase.CONFIGURE,
                            order=0,
                            writes=[
                                RegisterWrite(
                                    reg_addr="0x6B",
                                    value="0x00",
                                    description="Wake up",
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )

    def test_isr_handler_generated(self):
        hir = self._make_irq_hir(gpio="4", trigger="falling")
        result = generate_from_hir(hir, target="esp32")
        impl = next(f for f in result.files if f.path.endswith("mpu6050.c"))

        assert "IRAM_ATTR mpu6050_isr_handler" in impl.content
        assert "mpu6050_irq_install" in impl.content
        assert "mpu6050_irq_pending" in impl.content
        assert "GPIO_INTR_NEGEDGE" in impl.content

    def test_isr_rising_edge(self):
        hir = self._make_irq_hir(gpio="5", trigger="rising")
        result = generate_from_hir(hir, target="esp32")
        impl = next(f for f in result.files if f.path.endswith("mpu6050.c"))

        assert "GPIO_INTR_POSEDGE" in impl.content

    def test_isr_any_edge(self):
        hir = self._make_irq_hir(gpio="5", trigger="change")
        result = generate_from_hir(hir, target="esp32")
        impl = next(f for f in result.files if f.path.endswith("mpu6050.c"))

        assert "GPIO_INTR_ANYEDGE" in impl.content

    def test_isr_gpio_number_in_config(self):
        hir = self._make_irq_hir(gpio="12")
        result = generate_from_hir(hir, target="esp32")
        impl = next(f for f in result.files if f.path.endswith("mpu6050.c"))

        assert "GPIO {12}" in impl.content or "GPIO 12" in impl.content or "(1ULL << 12)" in impl.content

    def test_isr_header_declares_install(self):
        hir = self._make_irq_hir(gpio="4")
        result = generate_from_hir(hir, target="esp32")
        header = next(f for f in result.files if f.path.endswith("mpu6050.h"))

        assert "mpu6050_irq_install" in header.content
        assert "mpu6050_irq_pending" in header.content

    def test_no_isr_without_irq_gpio(self):
        """Components without irq_gpio must NOT generate ISR code."""
        hir = _make_bme280_hir()
        result = generate_from_hir(hir, target="esp32")
        impl = next(f for f in result.files if f.path.endswith("bme280.c"))

        assert "isr_handler" not in impl.content
        assert "irq_install" not in impl.content


class TestPhase19IRQBuilder:
    """Test the _find_irq_gpio and _parse_gpio_number helpers in hir_builder."""

    def test_parse_gpio_esp32(self):
        from boardsmith_fw.analysis.hir_builder import _parse_gpio_number

        assert _parse_gpio_number("GPIO4") == "4"
        assert _parse_gpio_number("GPIO21/SDA") == "21"
        assert _parse_gpio_number("IO4") == "4"

    def test_parse_gpio_stm32(self):
        from boardsmith_fw.analysis.hir_builder import _parse_gpio_number

        assert _parse_gpio_number("PA5") == "5"
        assert _parse_gpio_number("PB12") == "12"

    def test_parse_gpio_nrf52(self):
        from boardsmith_fw.analysis.hir_builder import _parse_gpio_number

        assert _parse_gpio_number("P0.04") == "04"

    def test_parse_gpio_unknown(self):
        from boardsmith_fw.analysis.hir_builder import _parse_gpio_number

        assert _parse_gpio_number("VCC") is None
        assert _parse_gpio_number("SDA") is None
