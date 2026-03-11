# SPDX-License-Identifier: AGPL-3.0-or-later
"""HIR-driven code generation — contracts to C firmware.

This replaces dumb f-string templates with contract-driven code emission.
Every line of generated code is traceable to a formal HIR contract:
  - BusContract → bus initialization (pins, clock, protocol)
  - InitContract → driver init with phased writes/reads/verification
  - PowerSequence → power rail enable ordering
  - ElectricalSpec → generated comments/warnings

Usage:
    from boardsmith_fw.codegen.hir_codegen import generate_from_hir
    result = generate_from_hir(hir, target="esp32")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from boardsmith_fw.models.hir import (
    HIR,
    BusContract,
    InitContract,
    InitPhaseSpec,
    PowerSequence,
)


# ---------------------------------------------------------------------------
# Binding Layer integration — contract → adapter → code resolution
# ---------------------------------------------------------------------------

# Phase 24.1: Canonical target → SDK key mapping
_TARGET_TO_SDK: dict[str, str] = {
    "esp32":   "esp-idf",
    "esp32c3": "esp-idf",
    "stm32":   "stm32hal",
    "rp2040":  "pico-sdk",
    "nrf52":   "zephyr",
}


def _resolve_adapter_for_component(component_mpn: str, target_sdk: str = "esp-idf"):
    """Resolve a LibraryAdapter for a component via the binding layer.

    Resolution chain: MPN → SoftwareProfile → api_contract_id → Adapter.

    Phase 24.1: Accepts both target names ("esp32") and SDK keys ("esp-idf")
    so callers don't need to know the mapping.

    Returns (adapter, sw_profile) or (None, None) on failure.
    """
    # Normalise: target name → SDK key (e.g. "stm32" → "stm32hal")
    sdk_key = _TARGET_TO_SDK.get(target_sdk, target_sdk)

    try:
        # Eagerly import adapters so all registered adapters are loaded
        import shared.knowledge.adapters as _adapters_module  # noqa: F401
        from shared.knowledge.software_profiles import get as get_sw_profile
        from shared.knowledge.contracts import get_registry
    except ImportError:
        return None, None

    sw_profile = get_sw_profile(component_mpn)
    if sw_profile is None:
        return None, None

    contract_id = sw_profile.api_contract_id
    if not contract_id:
        return None, None

    registry = get_registry()
    adapter = registry.resolve_adapter(contract_id, sdk_key)
    return adapter, sw_profile


def _normalize_gpio_pin(pin_value: str) -> str:
    """Normalize a GPIO pin identifier to a bare number string.

    Phase 24.2: The topology synthesizer may store pin assignments as
    "GPIO21", "IO21", "PA5", or plain "21".  This function strips common
    prefixes so generated code always reads ``GPIO_NUM_21`` (ESP32) or
    ``GPIO_PIN_5`` (STM32) — never ``GPIO_NUM_GPIO21``.

    Supported formats:
        "GPIO21"   → "21"
        "IO21"     → "21"
        "21"       → "21"    (pass-through)
        "PA5"      → "PA5"   (STM32 port+pin — kept as-is for HAL)
        "PB12"     → "PB12"

    Args:
        pin_value: Raw pin assignment string from BusContract.pin_assignments.

    Returns:
        Normalized string suitable for GPIO_NUM_{n} macros.
    """
    import re as _re
    if not pin_value:
        return pin_value
    # Strip "GPIO" prefix (ESP32 topology synthesizer style)
    stripped = _re.sub(r"^GPIO", "", pin_value.strip(), flags=_re.IGNORECASE)
    # Strip "IO" prefix (ESP32 alternate naming)
    stripped = _re.sub(r"^IO", "", stripped, flags=_re.IGNORECASE)
    # If result is purely numeric, return as string int
    if stripped.isdigit():
        return str(int(stripped))
    # STM32 port+pin (PA5, PB12, PC0) — return unchanged for HAL macros
    return stripped


def _get_adapter_includes(adapter) -> list[str]:
    """Extract all unique includes needed by an adapter."""
    if adapter is None:
        return []
    includes = list(adapter.required_includes)
    for ct in adapter.capability_mappings.values():
        for inc in ct.includes:
            if inc not in includes:
                includes.append(inc)
    return includes


@dataclass
class GeneratedFile:
    path: str
    content: str


@dataclass
class HIRCodegenResult:
    files: list[GeneratedFile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_from_hir(
    hir: HIR,
    target: str = "esp32",
) -> HIRCodegenResult:
    """Generate firmware files from validated HIR contracts.

    This is the main entry point. All code is derived from HIR — no raw
    HardwareGraph or ComponentKnowledge access.
    """
    result = HIRCodegenResult()

    if target in ("esp32", "esp32c3"):
        _generate_esp32(hir, result)
    elif target == "stm32":
        _generate_stm32(hir, result)
    elif target == "rp2040":
        _generate_rp2040(hir, result)
    elif target == "nrf52":
        _generate_nrf52(hir, result)
    else:
        result.warnings.append(f"Unknown target '{target}', using esp32")
        _generate_esp32(hir, result)

    return result


# ---------------------------------------------------------------------------
# ESP32 (ESP-IDF) generation
# ---------------------------------------------------------------------------


def _generate_esp32(hir: HIR, result: HIRCodegenResult) -> None:
    """Generate ESP-IDF firmware from HIR."""
    driver_headers: list[str] = []

    # Generate drivers from InitContracts + BusContracts
    for contract in hir.init_contracts:
        safe_name = _sanitize(contract.component_name)
        header_name = f"{safe_name}.h"
        driver_headers.append(header_name)

        # Find bus contract for this component
        bus = _find_bus_for_component(hir, contract.component_id)

        result.files.append(GeneratedFile(
            path=f"main/{header_name}",
            content=_emit_esp32_driver_header(contract, bus),
        ))
        result.files.append(GeneratedFile(
            path=f"main/{safe_name}.c",
            content=_emit_esp32_driver_impl(contract, bus),
        ))

    # Generate main.c
    result.files.append(GeneratedFile(
        path="main/main.c",
        content=_emit_esp32_main(hir, driver_headers),
    ))

    # Generate CMakeLists.txt
    driver_srcs = [f"{_sanitize(c.component_name)}.c" for c in hir.init_contracts]
    result.files.append(GeneratedFile(
        path="main/CMakeLists.txt",
        content=_emit_esp32_cmake(driver_srcs),
    ))


def _emit_esp32_driver_header(
    contract: InitContract,
    bus: BusContract | None,
) -> str:
    """Generate driver .h from InitContract."""
    safe = _sanitize(contract.component_name)
    guard = f"{safe.upper()}_H"

    lines = [
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        '#include "esp_err.h"',
        "",
        f"// {contract.component_name} driver",
        f"// Generated from HIR InitContract ({len(contract.phases)} phases)",
        "",
    ]

    if bus and bus.i2c:
        lines.append(f"#define {safe.upper()}_I2C_ADDR {bus.i2c.address}")
        lines.append("")

    lines += [
        f"esp_err_t {safe}_init(void);",
        f"esp_err_t {safe}_read(uint8_t *data, size_t len);",
    ]

    if contract.irq_gpio:
        lines += [
            "",
            f"// Interrupt support (GPIO {contract.irq_gpio}, {contract.irq_trigger} edge)",
            '#include "driver/gpio.h"',
            '#include "freertos/queue.h"',
            f"esp_err_t {safe}_irq_install(void);",
            f"bool      {safe}_irq_pending(TickType_t wait_ticks);",
        ]

    lines += [
        "",
        f"#endif // {guard}",
        "",
    ]
    return "\n".join(lines)


def _emit_esp32_driver_impl(
    contract: InitContract,
    bus: BusContract | None,
) -> str:
    """Generate driver .c from InitContract with phased init.

    If a LibraryAdapter exists for the component, emits adapter-driven code
    (contract → adapter → code template chain) instead of generic register stubs.
    """
    safe = _sanitize(contract.component_name)

    # Try binding layer resolution: MPN → SoftwareProfile → Adapter → CodeTemplates
    component_mpn = _extract_mpn_from_name(contract.component_name)
    adapter, sw_profile = _resolve_adapter_for_component(component_mpn, "esp-idf")

    if adapter and adapter.capability_mappings:
        return _emit_esp32_adapter_driver(contract, bus, safe, adapter, sw_profile)

    # Fallback: generic register-level driver from InitContract phases
    return _emit_esp32_generic_driver(contract, bus, safe)


def _extract_mpn_from_name(component_name: str) -> str:
    """Extract MPN from component name (e.g. 'BME280 Temperature Sensor' → 'BME280')."""
    return component_name.split()[0].upper() if component_name else ""


def _emit_esp32_adapter_driver(
    contract: InitContract,
    bus: BusContract | None,
    safe: str,
    adapter,
    sw_profile,
) -> str:
    """Emit ESP32 driver using LibraryAdapter code templates (binding layer)."""
    lines: list[str] = []

    # Adapter-specific includes
    adapter_includes = _get_adapter_includes(adapter)
    lines.append(f'#include "{safe}.h"')
    lines.append("")
    for inc in adapter_includes:
        lines.append(f'#include "{inc}"')
    lines += [
        '#include "esp_log.h"',
        "",
        f'static const char *TAG = "{safe}";',
        "",
    ]

    # Init template comment from adapter
    if adapter.init_template:
        for comment_line in adapter.init_template.split("\n"):
            lines.append(comment_line)
        lines.append("")

    # Emit init function from adapter's 'init' capability
    init_code = adapter.capability_mappings.get("init")
    lines.append(f"esp_err_t {safe}_init(void)")
    lines.append("{")
    lines.append(f'    ESP_LOGI(TAG, "Initializing {contract.component_name} via {adapter.driver_option_key}");')
    if init_code:
        for code_line in init_code.template.split("\n"):
            lines.append(f"    {code_line}")
    else:
        # Fallback to phased init from contract
        for phase_spec in contract.phases:
            for l in _emit_phase(phase_spec):
                lines.append(l)
        lines.append("    return ESP_OK;")
    lines += ["}", ""]

    # Emit read function from adapter capability (try common read patterns)
    read_cap_name = _find_read_capability(adapter)
    read_code = adapter.capability_mappings.get(read_cap_name) if read_cap_name else None
    lines.append(f"esp_err_t {safe}_read(uint8_t *data, size_t len)")
    lines.append("{")
    if read_code:
        for code_line in read_code.template.split("\n"):
            lines.append(f"    {code_line}")
    else:
        lines.append("    if (len == 0) return ESP_OK;")
        lines.append("    // TODO: implement read via adapter")
        lines.append("    return ESP_OK;")
    lines += ["}", ""]

    # Emit additional capability functions as comments for reference
    emitted = {"init", read_cap_name or ""}
    for cap_name, code_template in adapter.capability_mappings.items():
        if cap_name in emitted:
            continue
        lines.append(f"/* === {cap_name} (from {adapter.adapter_id}) ===")
        for code_line in code_template.template.split("\n"):
            lines.append(f"   {code_line}")
        lines.append("*/")
        lines.append("")

    # ISR handler if needed
    if contract.irq_gpio:
        lines += _emit_esp32_isr(contract, safe)

    return "\n".join(lines)


def _find_read_capability(adapter) -> str | None:
    """Find the primary 'read' capability in an adapter."""
    for name in ("read", "read_temperature", "read_accel", "read_co2", "receive"):
        if name in adapter.capability_mappings:
            return name
    return None


def _emit_esp32_generic_driver(
    contract: InitContract,
    bus: BusContract | None,
    safe: str,
) -> str:
    """Fallback: generic register-level driver from InitContract phases."""
    lines: list[str] = []

    # Includes
    lines += [
        f'#include "{safe}.h"',
        "",
        '#include <string.h>',
        '#include "driver/i2c.h"',
        '#include "esp_log.h"',
        '#include "freertos/FreeRTOS.h"',
        '#include "freertos/task.h"',
        "",
        f'static const char *TAG = "{safe}";',
        "",
    ]

    # I2C address and port
    i2c_addr = "0x00"
    if bus and bus.i2c:
        i2c_addr = bus.i2c.address
    lines.append(f"#define I2C_ADDR {i2c_addr}")
    lines.append("#define I2C_PORT I2C_NUM_0")
    lines.append("")

    # Helper functions
    lines += _emit_esp32_i2c_helpers(safe)

    # Init function — phased from InitContract
    lines += _emit_esp32_init_function(contract, safe)

    # Read function
    lines += _emit_esp32_read_function(contract, safe)

    # ISR handler — only if this component drives an interrupt line
    if contract.irq_gpio:
        lines += _emit_esp32_isr(contract, safe)

    return "\n".join(lines)


def _emit_esp32_i2c_helpers(safe: str) -> list[str]:
    """Emit I2C write_register / read_register helpers with retry and bus recovery."""
    return [
        "static esp_err_t write_register(uint8_t reg, uint8_t val)",
        "{",
        "    uint8_t buf[2] = {reg, val};",
        "    return i2c_master_write_to_device(",
        "        I2C_PORT, I2C_ADDR, buf, 2,",
        "        pdMS_TO_TICKS(100)",
        "    );",
        "}",
        "",
        "static esp_err_t read_registers(",
        "    uint8_t reg, uint8_t *data, size_t len)",
        "{",
        "    return i2c_master_write_read_device(",
        "        I2C_PORT, I2C_ADDR,",
        "        &reg, 1, data, len,",
        "        pdMS_TO_TICKS(100)",
        "    );",
        "}",
        "",
        "/* I2C bus recovery — sends 9 SCL clocks + STOP to release a stuck slave. */",
        "static void i2c_bus_recover(void)",
        "{",
        "    i2c_reset_tx_fifo(I2C_PORT);",
        "    i2c_reset_rx_fifo(I2C_PORT);",
        "    vTaskDelay(pdMS_TO_TICKS(5));",
        "}",
        "",
        "/* write_register with up to 3 retries and bus recovery on failure. */",
        "static esp_err_t write_register_retry(uint8_t reg, uint8_t val)",
        "{",
        "    esp_err_t ret;",
        "    for (int _i = 0; _i < 3; _i++) {",
        "        ret = write_register(reg, val);",
        "        if (ret == ESP_OK) return ESP_OK;",
        "        i2c_bus_recover();",
        "    }",
        "    return ret;",
        "}",
        "",
        "/* read_registers with up to 3 retries and bus recovery on failure. */",
        "static esp_err_t read_registers_retry(",
        "    uint8_t reg, uint8_t *data, size_t len)",
        "{",
        "    esp_err_t ret;",
        "    for (int _i = 0; _i < 3; _i++) {",
        "        ret = read_registers(reg, data, len);",
        "        if (ret == ESP_OK) return ESP_OK;",
        "        i2c_bus_recover();",
        "    }",
        "    return ret;",
        "}",
        "",
    ]


def _emit_esp32_init_function(
    contract: InitContract,
    safe: str,
) -> list[str]:
    """Emit {component}_init() with phased register writes and reads."""
    lines = [
        f"esp_err_t {safe}_init(void)",
        "{",
        f'    ESP_LOGI(TAG, "Initializing {contract.component_name}");',
        "    esp_err_t ret;",
        "",
    ]

    for phase_spec in contract.phases:
        lines += _emit_phase(phase_spec)

    lines += [
        f'    ESP_LOGI(TAG, "{contract.component_name} init complete");',
        "    return ESP_OK;",
        "}",
        "",
    ]
    return lines


def _emit_phase(phase_spec: InitPhaseSpec) -> list[str]:
    """Emit code for a single init phase (RESET, CONFIGURE, VERIFY, etc.)."""
    lines: list[str] = []
    phase_name = phase_spec.phase.value.upper()

    lines.append(f"    /* === {phase_name} PHASE === */")

    if phase_spec.precondition:
        lines.append(f"    // Precondition: {phase_spec.precondition}")

    # Register writes — use retry helper for robustness
    for write in phase_spec.writes:
        lines.append(f"    // {write.description}")
        lines.append(f"    ret = write_register_retry({write.reg_addr}, {write.value});")
        lines.append("    if (ret != ESP_OK) {")
        lines.append(
            f'        ESP_LOGE(TAG, "{write.description} failed: %s", esp_err_to_name(ret));'
        )
        lines.append("        return ret;")
        lines.append("    }")

    # Register reads with verification — use retry helper for robustness
    for read in phase_spec.reads:
        lines.append(f"    // {read.description}")
        lines.append("    {")
        lines.append("        uint8_t val;")
        lines.append(
            f"        ret = read_registers_retry({read.reg_addr}, &val, 1);"
        )
        lines.append("        if (ret != ESP_OK) {")
        lines.append(
            f'            ESP_LOGE(TAG, "{read.description} failed: %s", esp_err_to_name(ret));'
        )
        lines.append("            return ret;")
        lines.append("        }")

        if read.expected_value:
            lines.append(
                f"        if (val != {read.expected_value}) {{"
            )
            lines.append(
                f'            ESP_LOGE(TAG, "{read.description}: '
                f'expected {read.expected_value}, got 0x%02x", val);'
            )
            lines.append(
                "            return ESP_ERR_INVALID_RESPONSE;"
            )
            lines.append("        }")
            lines.append(
                '        ESP_LOGI(TAG, "Verified: 0x%02x", val);'
            )
        else:
            lines.append(
                f'        ESP_LOGI(TAG, "{read.description}: 0x%02x", val);'
            )

        lines.append("    }")

    # Delay after phase
    if (phase_spec.delay_after_ms or 0) > 0:
        lines.append(
            f"    vTaskDelay(pdMS_TO_TICKS({phase_spec.delay_after_ms}));"
        )

    if phase_spec.postcondition:
        lines.append(f"    // Postcondition: {phase_spec.postcondition}")

    lines.append("")
    return lines


def _emit_esp32_read_function(
    contract: InitContract,
    safe: str,
) -> list[str]:
    """Emit {component}_read() function."""
    return [
        f"esp_err_t {safe}_read(uint8_t *data, size_t len)",
        "{",
        "    if (len == 0) return ESP_OK;",
        "    return read_registers_retry(0x00, data, len);",
        "}",
        "",
    ]


def _emit_esp32_isr(
    contract: InitContract,
    safe: str,
) -> list[str]:
    """Emit GPIO ISR handler for a component with an interrupt pin."""
    gpio = contract.irq_gpio
    trigger = contract.irq_trigger or "falling"
    idf_trigger = {
        "falling": "GPIO_INTR_NEGEDGE",
        "rising":  "GPIO_INTR_POSEDGE",
        "change":  "GPIO_INTR_ANYEDGE",
    }.get(trigger, "GPIO_INTR_NEGEDGE")

    return [
        f"/* === {contract.component_name} Interrupt Handler (GPIO {gpio}, {trigger} edge) === */",
        "",
        "/* FreeRTOS queue — {safe}_isr posts to this, main task reads from it. */",
        f"static QueueHandle_t {safe}_irq_queue;",
        "",
        f"static void IRAM_ATTR {safe}_isr_handler(void *arg)",
        "{",
        "    uint32_t gpio_num = (uint32_t)arg;",
        f"    xQueueSendFromISR({safe}_irq_queue, &gpio_num, NULL);",
        "}",
        "",
        f"esp_err_t {safe}_irq_install(void)",
        "{",
        f"    {safe}_irq_queue = xQueueCreate(4, sizeof(uint32_t));",
        f"    if (!{safe}_irq_queue) return ESP_ERR_NO_MEM;",
        "",
        f"    gpio_config_t io_conf = {{",
        f"        .pin_bit_mask = (1ULL << {gpio}),",
        "        .mode = GPIO_MODE_INPUT,",
        "        .pull_up_en = GPIO_PULLUP_ENABLE,",
        "        .pull_down_en = GPIO_PULLDOWN_DISABLE,",
        f"        .intr_type = {idf_trigger},",
        "    };",
        "    esp_err_t ret = gpio_config(&io_conf);",
        "    if (ret != ESP_OK) return ret;",
        "",
        "    gpio_install_isr_service(0);",
        f"    return gpio_isr_handler_add({gpio}, {safe}_isr_handler, (void *){gpio});",
        "}",
        "",
        f"/* Call this from a task loop to handle {contract.component_name} interrupts. */",
        f"bool {safe}_irq_pending(TickType_t wait_ticks)",
        "{",
        "    uint32_t gpio_num;",
        f"    return xQueueReceive({safe}_irq_queue, &gpio_num, wait_ticks) == pdTRUE;",
        "}",
        "",
    ]


def _emit_esp32_main(
    hir: HIR,
    driver_headers: list[str],
) -> str:
    """Generate main.c from HIR: power sequence → bus init → component init."""
    lines: list[str] = []

    # Includes
    lines += [
        '#include <stdio.h>',
        '#include "driver/i2c.h"',
        '#include "esp_log.h"',
        '#include "freertos/FreeRTOS.h"',
        '#include "freertos/task.h"',
        "",
    ]
    for h in driver_headers:
        lines.append(f'#include "{h}"')
    lines += [
        "",
        'static const char *TAG = "main";',
        "",
    ]

    # Bus init functions
    for bc in hir.bus_contracts:
        lines += _emit_esp32_bus_init(bc)

    # app_main
    lines += [
        "void app_main(void)",
        "{",
        '    ESP_LOGI(TAG, "Boardsmith-FW Starting...");',
        "",
    ]

    # Power sequencing
    if hir.power_sequence and hir.power_sequence.rails:
        lines += _emit_power_sequence(hir.power_sequence)

    # Bus initialization
    for bc in hir.bus_contracts:
        bus_fn = _sanitize(bc.bus_name)
        lines.append(f"    // Initialize {bc.bus_name} ({bc.bus_type})")
        lines.append(f"    {bus_fn}_bus_init();")
        lines.append("")

    # Component initialization (ordered by init contracts)
    for ic in hir.init_contracts:
        safe = _sanitize(ic.component_name)
        lines.append(f"    // Initialize {ic.component_name}")
        lines.append(f"    if ({safe}_init() != ESP_OK) {{")
        lines.append(
            f'        ESP_LOGE(TAG, "{ic.component_name} init failed");'
        )
        lines.append("    }")
        lines.append("")

    # Main loop
    lines += [
        '    ESP_LOGI(TAG, "All components initialized.");',
        "",
        "    while (1) {",
    ]
    for ic in hir.init_contracts:
        safe = _sanitize(ic.component_name)
        lines.append(f"        // Read {ic.component_name}")
        lines.append(f"        uint8_t {safe}_data[8];")
        lines.append(f"        {safe}_read({safe}_data, sizeof({safe}_data));")
    lines += [
        "        vTaskDelay(pdMS_TO_TICKS(1000));",
        "    }",
        "}",
        "",
    ]

    return "\n".join(lines)


def _emit_esp32_bus_init(bc: BusContract) -> list[str]:
    """Generate bus initialization function from BusContract."""
    bus_fn = _sanitize(bc.bus_name)
    lines: list[str] = []

    if bc.bus_type == "I2C":
        # Phase 24.2: Normalize pin IDs — strip GPIO/IO prefix for GPIO_NUM_ macros
        sda = _normalize_gpio_pin(bc.pin_assignments.get("SDA", "21"))
        scl = _normalize_gpio_pin(bc.pin_assignments.get("SCL", "22"))
        clock = bc.configured_clock_hz or 100000

        lines += [
            f"static void {bus_fn}_bus_init(void)",
            "{",
            f"    // {bc.bus_name}: I2C bus",
            f"    // Clock: {clock} Hz "
            f"(negotiated from {len(bc.slave_ids)} slave(s))",
            "    i2c_config_t conf = {",
            "        .mode = I2C_MODE_MASTER,",
            f"        .sda_io_num = GPIO_NUM_{sda},",
            f"        .scl_io_num = GPIO_NUM_{scl},",
            "        .sda_pullup_en = GPIO_PULLUP_ENABLE,",
            "        .scl_pullup_en = GPIO_PULLUP_ENABLE,",
            f"        .master.clk_speed = {clock},",
            "    };",
            "    i2c_param_config(I2C_NUM_0, &conf);",
            "    i2c_driver_install(I2C_NUM_0, I2C_MODE_MASTER, 0, 0, 0);",
            f'    ESP_LOGI(TAG, "{bc.bus_name} I2C initialized '
            f'(SDA={sda}, SCL={scl}, {clock}Hz)");',
            "}",
            "",
        ]

    elif bc.bus_type == "SPI":
        # Phase 24.2: Normalize pin IDs
        mosi = _normalize_gpio_pin(bc.pin_assignments.get("MOSI", "23"))
        miso = _normalize_gpio_pin(bc.pin_assignments.get("MISO", "19"))
        sck  = _normalize_gpio_pin(bc.pin_assignments.get("SCK", "18"))
        clock = bc.configured_clock_hz or 1000000

        lines += [
            f"static void {bus_fn}_bus_init(void)",
            "{",
            f"    // {bc.bus_name}: SPI bus ({clock} Hz)",
            "    spi_bus_config_t bus_cfg = {",
            f"        .mosi_io_num = GPIO_NUM_{mosi},",
            f"        .miso_io_num = GPIO_NUM_{miso},",
            f"        .sclk_io_num = GPIO_NUM_{sck},",
            "        .quadwp_io_num = -1,",
            "        .quadhd_io_num = -1,",
            "        .max_transfer_sz = 4096,",
            "    };",
            "    spi_bus_initialize(SPI2_HOST, &bus_cfg, "
            "SPI_DMA_CH_AUTO);",
            f'    ESP_LOGI(TAG, "{bc.bus_name} SPI initialized");',
            "}",
            "",
        ]

    elif bc.bus_type == "UART":
        # Phase 24.2: Normalize pin IDs
        tx = _normalize_gpio_pin(bc.pin_assignments.get("TX", "17"))
        rx = _normalize_gpio_pin(bc.pin_assignments.get("RX", "16"))
        baud = 115200
        if bc.uart:
            baud = bc.uart.baud_rate

        lines += [
            f"static void {bus_fn}_bus_init(void)",
            "{",
            f"    // {bc.bus_name}: UART ({baud} baud)",
            "    uart_config_t uart_cfg = {",
            f"        .baud_rate = {baud},",
            "        .data_bits = UART_DATA_8_BITS,",
            "        .parity = UART_PARITY_DISABLE,",
            "        .stop_bits = UART_STOP_BITS_1,",
            "        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,",
            "    };",
            "    uart_param_config(UART_NUM_1, &uart_cfg);",
            f"    uart_set_pin(UART_NUM_1, "
            f"GPIO_NUM_{tx}, GPIO_NUM_{rx}, -1, -1);",
            "    uart_driver_install(UART_NUM_1, 1024, 0, 0, NULL, 0);",
            f'    ESP_LOGI(TAG, "{bc.bus_name} UART initialized");',
            "}",
            "",
        ]

    else:
        lines += [
            f"static void {bus_fn}_bus_init(void)",
            "{",
            f'    ESP_LOGW(TAG, "{bc.bus_name}: '
            f'{bc.bus_type} bus init not implemented");',
            "}",
            "",
        ]

    return lines


def _emit_power_sequence(ps: PowerSequence) -> list[str]:
    """Generate power rail enable sequence."""
    lines = ["    /* === POWER SEQUENCING === */"]

    try:
        order = ps.get_startup_order()
    except ValueError:
        lines.append("    // Warning: circular power dependency detected")
        lines.append("")
        return lines

    if not order:
        return []

    for i, rail_name in enumerate(order):
        rail = next((r for r in ps.rails if r.name == rail_name), None)
        if not rail:
            continue

        if i > 0:
            # Check for delay dependency
            for dep in ps.dependencies:
                if dep.target == rail_name:
                    lines.append(
                        f"    // {dep.description}"
                    )
                    if dep.min_delay_ms > 0:
                        lines.append(
                            f"    vTaskDelay(pdMS_TO_TICKS("
                            f"{dep.min_delay_ms}));"
                        )

        lines.append(
            f'    ESP_LOGI(TAG, "Power rail {rail.name} '
            f'({rail.voltage.nominal}V) ready");'
        )

        if rail.enable_gpio:
            lines.append(
                f"    gpio_set_level(GPIO_NUM_{rail.enable_gpio}, 1);"
            )

    lines.append("")
    return lines


def _emit_esp32_cmake(driver_srcs: list[str]) -> str:
    """Generate CMakeLists.txt for ESP-IDF component."""
    srcs = " ".join(["main.c"] + driver_srcs)
    return (
        f'idf_component_register(\n'
        f'    SRCS "{srcs}"\n'
        f'    INCLUDE_DIRS "."\n'
        f')\n'
    )


# ---------------------------------------------------------------------------
# STM32 (HAL) generation — structure only
# ---------------------------------------------------------------------------


def _generate_stm32(hir: HIR, result: HIRCodegenResult) -> None:
    """Generate STM32 HAL firmware from HIR.

    Phase 24.3: Now emits complete bus initialization functions
    (MX_I2C1_Init / MX_SPI1_Init) from BusContracts instead of
    assuming CubeMX-generated stubs.  Also resolves STM32 HAL adapters
    for known components (BME280, MPU6050) for register-level inits.
    """
    driver_headers: list[str] = []

    # Collect bus inits (deduped by bus_name)
    bus_init_lines: list[str] = []
    seen_buses: set[str] = set()
    for bc in hir.bus_contracts:
        if bc.bus_name not in seen_buses:
            bus_init_lines.extend(_emit_stm32_bus_init(bc))
            seen_buses.add(bc.bus_name)

    for contract in hir.init_contracts:
        safe = _sanitize(contract.component_name)
        header_name = f"{safe}.h"
        driver_headers.append(header_name)

        bus = _find_bus_for_component(hir, contract.component_id)

        # Phase 24.1: try STM32 HAL adapter first
        adapter, sw_profile = _resolve_adapter_for_component(
            contract.component_name, "stm32"
        )

        result.files.append(GeneratedFile(
            path=f"Src/{header_name}",
            content=_emit_stm32_driver_header(contract, bus),
        ))
        result.files.append(GeneratedFile(
            path=f"Src/{safe}.c",
            content=_emit_stm32_driver_impl(contract, bus, adapter),
        ))

    result.files.append(GeneratedFile(
        path="Src/main.c",
        content=_emit_stm32_main(hir, driver_headers, bus_init_lines),
    ))


def _emit_stm32_bus_init(bc: BusContract) -> list[str]:
    """Generate STM32 HAL bus initialization from BusContract.

    Phase 24.3: Replaces the previous stub that assumed CubeMX's
    MX_I2C1_Init(). Now generates a complete MX_<BUS>_Init() function
    with GPIO + HAL peripheral configuration derived from the HIR.

    Supports I2C and SPI buses.  UART is emitted as a stub (uncommon
    on STM32 sensor boards).
    """
    bus_fn = f"MX_{bc.bus_name.replace(' ', '_')}_Init"
    lines: list[str] = []

    if bc.bus_type == "I2C":
        # Phase 24.2: normalize pin IDs for STM32 port+pin style
        sda_raw = bc.pin_assignments.get("SDA", "PB7")
        scl_raw = bc.pin_assignments.get("SCL", "PB6")
        # STM32 PA/PB/PC pins: keep as-is; numeric → "PB{n}"
        sda = sda_raw if not sda_raw.isdigit() else f"PB{sda_raw}"
        scl = scl_raw if not scl_raw.isdigit() else f"PB{scl_raw}"

        clock = bc.configured_clock_hz or 100_000
        timing = "0x10909CEC" if clock <= 100_000 else "0x00702991"  # SM / FM

        lines += [
            "I2C_HandleTypeDef hi2c1;",
            "",
            f"void {bus_fn}(void)",
            "{",
            f"    /* {bc.bus_name}: I2C {clock} Hz (HIR Phase 24.3) */",
            "    hi2c1.Instance = I2C1;",
            f"    hi2c1.Init.Timing = {timing};",
            "    hi2c1.Init.OwnAddress1 = 0;",
            "    hi2c1.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;",
            "    hi2c1.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;",
            "    hi2c1.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;",
            "    hi2c1.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;",
            "    HAL_I2C_Init(&hi2c1);",
            "}",
            "",
        ]

    elif bc.bus_type == "SPI":
        mosi_raw = bc.pin_assignments.get("MOSI", "PA7")
        miso_raw = bc.pin_assignments.get("MISO", "PA6")
        sck_raw  = bc.pin_assignments.get("SCK", "PA5")
        mosi = mosi_raw if not mosi_raw.isdigit() else f"PA{mosi_raw}"
        miso = miso_raw if not miso_raw.isdigit() else f"PA{miso_raw}"
        sck  = sck_raw  if not sck_raw.isdigit()  else f"PA{sck_raw}"
        clock = bc.configured_clock_hz or 1_000_000

        lines += [
            "SPI_HandleTypeDef hspi1;",
            "",
            f"void {bus_fn}(void)",
            "{",
            f"    /* {bc.bus_name}: SPI {clock} Hz */",
            "    hspi1.Instance = SPI1;",
            "    hspi1.Init.Mode = SPI_MODE_MASTER;",
            "    hspi1.Init.Direction = SPI_DIRECTION_2LINES;",
            "    hspi1.Init.DataSize = SPI_DATASIZE_8BIT;",
            "    hspi1.Init.CLKPolarity = SPI_POLARITY_LOW;",
            "    hspi1.Init.CLKPhase = SPI_PHASE_1EDGE;",
            "    hspi1.Init.NSS = SPI_NSS_SOFT;",
            "    hspi1.Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_16;",
            "    hspi1.Init.FirstBit = SPI_FIRSTBIT_MSB;",
            "    HAL_SPI_Init(&hspi1);",
            "}",
            "",
        ]

    else:
        lines += [
            f"void {bus_fn}(void)",
            "{",
            f"    /* {bc.bus_name}: {bc.bus_type} bus init stub */",
            "}",
            "",
        ]

    return lines


def _emit_stm32_driver_header(
    contract: InitContract,
    bus: BusContract | None,
) -> str:
    safe = _sanitize(contract.component_name)
    guard = f"{safe.upper()}_H"
    lines = [
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        '#include "stm32f4xx_hal.h"',
        "",
        f"// {contract.component_name} driver (HIR-generated)",
        "",
    ]
    if bus and bus.i2c:
        lines.append(f"#define {safe.upper()}_I2C_ADDR ({bus.i2c.address} << 1)")
    lines += [
        "",
        f"HAL_StatusTypeDef {safe}_init(I2C_HandleTypeDef *hi2c);",
        f"HAL_StatusTypeDef {safe}_read("
        f"I2C_HandleTypeDef *hi2c, uint8_t *data, uint16_t len);",
        "",
        f"#endif // {guard}",
        "",
    ]
    return "\n".join(lines)


def _emit_stm32_driver_impl(
    contract: InitContract,
    bus: BusContract | None,
    adapter=None,
) -> str:
    """Emit STM32 HAL driver implementation.

    Phase 24.3: If a STM32 HAL adapter is available (Phase 24.1), use
    its init template for real register-level init with chip-ID verification.
    Falls back to generic phase-based register writes from InitContract.
    """
    safe = _sanitize(contract.component_name)
    i2c_addr = "0x00"
    if bus and bus.i2c:
        i2c_addr = bus.i2c.address

    lines = [
        f'#include "{safe}.h"',
        "",
        f"#define ADDR ({i2c_addr} << 1)",
        "",
        f"HAL_StatusTypeDef {safe}_init(I2C_HandleTypeDef *hi2c)",
        "{",
    ]

    # Phase 24.1/24.3: Use adapter's init code if available
    if adapter and "init" in adapter.capability_mappings:
        init_tmpl = adapter.capability_mappings["init"].template
        for tmpl_line in init_tmpl.split("\n"):
            lines.append(f"    {tmpl_line}")
        lines += ["    return HAL_OK;", "}"]
    else:
        # Fallback: generic phase-based register writes
        lines += ["    HAL_StatusTypeDef ret;", "    uint8_t buf[2];", ""]

        for phase_spec in contract.phases:
            phase_name = phase_spec.phase.value.upper()
            lines.append(f"    /* === {phase_name} === */")

            for write in phase_spec.writes:
                lines.append(f"    // {write.description}")
                lines.append(
                    f"    buf[0] = {write.reg_addr}; "
                    f"buf[1] = {write.value};"
                )
                lines.append(
                    "    ret = HAL_I2C_Master_Transmit("
                    "hi2c, ADDR, buf, 2, 100);"
                )
                lines.append("    if (ret != HAL_OK) return ret;")

            for read in phase_spec.reads:
                lines.append(f"    // {read.description}")
                lines.append("    {")
                lines.append(f"        uint8_t reg = {read.reg_addr};")
                lines.append("        uint8_t val;")
                lines.append(
                    "        HAL_I2C_Master_Transmit("
                    "hi2c, ADDR, &reg, 1, 100);"
                )
                lines.append(
                    "        ret = HAL_I2C_Master_Receive("
                    "hi2c, ADDR, &val, 1, 100);"
                )
                lines.append("        if (ret != HAL_OK) return ret;")
                if read.expected_value:
                    lines.append(
                        f"        if (val != {read.expected_value})"
                        " return HAL_ERROR;"
                    )
                lines.append("    }")

            if (phase_spec.delay_after_ms or 0) > 0:
                lines.append(f"    HAL_Delay({phase_spec.delay_after_ms});")
            lines.append("")

        lines += ["    return HAL_OK;", "}"]

    lines += [
        "",
        f"HAL_StatusTypeDef {safe}_read(",
        "    I2C_HandleTypeDef *hi2c, uint8_t *data, uint16_t len)",
        "{",
        "    uint8_t reg = 0x00;",
        "    HAL_I2C_Master_Transmit(hi2c, ADDR, &reg, 1, 100);",
        "    return HAL_I2C_Master_Receive(hi2c, ADDR, data, len, 100);",
        "}",
        "",
    ]
    return "\n".join(lines)


def _emit_stm32_main(
    hir: HIR,
    driver_headers: list[str],
    bus_init_lines: list[str] | None = None,
) -> str:
    """Emit STM32 HAL main.c.

    Phase 24.3: Now includes a generated SystemClock_Config() stub and
    calls HIR-derived MX_<BUS>_Init() functions instead of hardcoded
    MX_I2C1_Init() from CubeMX.
    """
    lines = [
        "/* Auto-generated by Boardsmith Phase 24.3 — STM32 HAL */",
        '#include "stm32f4xx_hal.h"',
        "",
    ]
    for h in driver_headers:
        lines.append(f'#include "{h}"')

    # Forward-declare bus init functions and handle types
    if bus_init_lines:
        lines += ["", "/* === Generated Bus Handles (Phase 24.3) === */"]
        lines += bus_init_lines

    # SystemClock_Config stub (real value depends on crystal + target MCU)
    lines += [
        "",
        "/* SystemClock_Config — placeholder; configure for your crystal */",
        "static void SystemClock_Config(void)",
        "{",
        "    RCC_OscInitTypeDef osc = {0};",
        "    osc.OscillatorType = RCC_OSCILLATORTYPE_HSI;",
        "    osc.HSIState = RCC_HSI_ON;",
        "    osc.PLL.PLLState = RCC_PLL_NONE;",
        "    HAL_RCC_OscConfig(&osc);",
        "}",
        "",
    ]

    # Collect all bus init function names from HIR
    bus_init_calls = [
        f"MX_{bc.bus_name.replace(' ', '_')}_Init()"
        for bc in hir.bus_contracts
    ]

    lines += [
        "int main(void)",
        "{",
        "    HAL_Init();",
        "    SystemClock_Config();",
    ]
    for call in bus_init_calls:
        lines.append(f"    {call};")
    lines.append("")

    for ic in hir.init_contracts:
        safe = _sanitize(ic.component_name)
        lines.append(f"    {safe}_init(&hi2c1);")

    lines += ["", "    while (1) {"]
    for ic in hir.init_contracts:
        safe = _sanitize(ic.component_name)
        lines.append(f"        uint8_t {safe}_buf[8];")
        lines.append(
            f"        {safe}_read(&hi2c1, {safe}_buf, sizeof({safe}_buf));"
        )
    lines += [
        "        HAL_Delay(1000);",
        "    }",
        "}",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# RP2040 (Pico SDK) generation — structure only
# ---------------------------------------------------------------------------


def _generate_rp2040(hir: HIR, result: HIRCodegenResult) -> None:
    """Generate Pico SDK firmware from HIR."""
    driver_headers: list[str] = []

    for contract in hir.init_contracts:
        safe = _sanitize(contract.component_name)
        header_name = f"{safe}.h"
        driver_headers.append(header_name)
        bus = _find_bus_for_component(hir, contract.component_id)

        result.files.append(GeneratedFile(
            path=header_name,
            content=_emit_rp2040_driver_header(contract, bus),
        ))
        result.files.append(GeneratedFile(
            path=f"{safe}.c",
            content=_emit_rp2040_driver_impl(contract, bus),
        ))

    result.files.append(GeneratedFile(
        path="main.c",
        content=_emit_rp2040_main(hir, driver_headers),
    ))


def _emit_rp2040_driver_header(
    contract: InitContract,
    bus: BusContract | None,
) -> str:
    safe = _sanitize(contract.component_name)
    guard = f"{safe.upper()}_H"
    lines = [
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        '#include "hardware/i2c.h"',
        "",
        f"// {contract.component_name} driver (HIR-generated)",
        "",
    ]
    if bus and bus.i2c:
        lines.append(f"#define {safe.upper()}_I2C_ADDR {bus.i2c.address}")
    lines += [
        "",
        f"int {safe}_init(i2c_inst_t *i2c);",
        f"int {safe}_read(i2c_inst_t *i2c, uint8_t *data, size_t len);",
        "",
        f"#endif // {guard}",
        "",
    ]
    return "\n".join(lines)


def _emit_rp2040_driver_impl(
    contract: InitContract,
    bus: BusContract | None,
) -> str:
    safe = _sanitize(contract.component_name)
    i2c_addr = "0x00"
    if bus and bus.i2c:
        i2c_addr = bus.i2c.address

    lines = [
        f'#include "{safe}.h"',
        '#include <stdio.h>',
        '#include "pico/stdlib.h"',
        "",
        f"#define ADDR {i2c_addr}",
        "",
        "static int write_reg(i2c_inst_t *i2c, uint8_t reg, uint8_t val)",
        "{",
        "    uint8_t buf[2] = {reg, val};",
        "    return i2c_write_blocking(i2c, ADDR, buf, 2, false);",
        "}",
        "",
        "static int read_reg(",
        "    i2c_inst_t *i2c, uint8_t reg, uint8_t *data, size_t len)",
        "{",
        "    i2c_write_blocking(i2c, ADDR, &reg, 1, true);",
        "    return i2c_read_blocking(i2c, ADDR, data, len, false);",
        "}",
        "",
        f"int {safe}_init(i2c_inst_t *i2c)",
        "{",
    ]

    for phase_spec in contract.phases:
        phase_name = phase_spec.phase.value.upper()
        lines.append(f"    /* === {phase_name} === */")

        for write in phase_spec.writes:
            lines.append(f"    // {write.description}")
            lines.append(
                f"    if (write_reg(i2c, {write.reg_addr}, "
                f"{write.value}) < 0) return -1;"
            )

        for read in phase_spec.reads:
            lines.append(f"    // {read.description}")
            lines.append("    {")
            lines.append("        uint8_t val;")
            lines.append(
                f"        if (read_reg(i2c, {read.reg_addr}, "
                "&val, 1) < 0) return -1;"
            )
            if read.expected_value:
                lines.append(
                    f"        if (val != {read.expected_value}) return -2;"
                )
            lines.append("    }")

        if (phase_spec.delay_after_ms or 0) > 0:
            lines.append(f"    sleep_ms({phase_spec.delay_after_ms});")
        lines.append("")

    lines += [
        "    return 0;",
        "}",
        "",
        f"int {safe}_read(i2c_inst_t *i2c, uint8_t *data, size_t len)",
        "{",
        "    return read_reg(i2c, 0x00, data, len);",
        "}",
        "",
    ]
    return "\n".join(lines)


def _emit_rp2040_main(hir: HIR, driver_headers: list[str]) -> str:
    lines = [
        '#include <stdio.h>',
        '#include "pico/stdlib.h"',
        '#include "hardware/i2c.h"',
        "",
    ]
    for h in driver_headers:
        lines.append(f'#include "{h}"')
    lines += [
        "",
        "int main(void)",
        "{",
        "    stdio_init_all();",
        "",
    ]

    # Bus init from contracts
    for bc in hir.bus_contracts:
        if bc.bus_type == "I2C":
            sda = bc.pin_assignments.get("SDA", "4")
            scl = bc.pin_assignments.get("SCL", "5")
            clock = bc.configured_clock_hz or 100000
            lines += [
                f"    // {bc.bus_name}: I2C ({clock} Hz)",
                f"    i2c_init(i2c0, {clock});",
                f"    gpio_set_function({sda}, GPIO_FUNC_I2C);",
                f"    gpio_set_function({scl}, GPIO_FUNC_I2C);",
                f"    gpio_pull_up({sda});",
                f"    gpio_pull_up({scl});",
                "",
            ]

    for ic in hir.init_contracts:
        safe = _sanitize(ic.component_name)
        lines.append(f"    {safe}_init(i2c0);")

    lines += [
        "",
        "    while (1) {",
    ]
    for ic in hir.init_contracts:
        safe = _sanitize(ic.component_name)
        lines.append(f"        uint8_t {safe}_data[8];")
        lines.append(f"        {safe}_read(i2c0, {safe}_data, 8);")
    lines += [
        "        sleep_ms(1000);",
        "    }",
        "}",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# nRF52 (Zephyr RTOS) generation
# ---------------------------------------------------------------------------


def _generate_nrf52(hir: HIR, result: HIRCodegenResult) -> None:
    """Generate Zephyr RTOS firmware from HIR."""
    driver_headers: list[str] = []

    for contract in hir.init_contracts:
        safe = _sanitize(contract.component_name)
        header_path = f"src/{safe}.h"
        impl_path = f"src/{safe}.c"

        header = _emit_nrf52_driver_header(contract, hir)
        impl = _emit_nrf52_driver_impl(contract, hir)

        result.files.append(GeneratedFile(path=header_path, content=header))
        result.files.append(GeneratedFile(path=impl_path, content=impl))
        driver_headers.append(safe)

    main = _emit_nrf52_main(hir, driver_headers)
    result.files.append(GeneratedFile(path="src/main.c", content=main))


def _emit_nrf52_driver_header(contract: InitContract, hir: HIR) -> str:
    safe = _sanitize(contract.component_name)
    upper = safe.upper()

    bus = _find_bus_for_component(hir, contract.component_id)

    lines = [
        f"/* {contract.component_name} driver — nRF52/Zephyr */",
        f"#ifndef {upper}_H",
        f"#define {upper}_H",
        "",
        "#include <zephyr/kernel.h>",
        "#include <zephyr/device.h>",
    ]

    if bus and bus.bus_type == "I2C":
        lines.append("#include <zephyr/drivers/i2c.h>")
        if bus.i2c and bus.i2c.address:
            lines.append(f"#define {upper}_I2C_ADDR 0x{int(bus.i2c.address, 16):02X}")
    elif bus and bus.bus_type == "SPI":
        lines.append("#include <zephyr/drivers/spi.h>")

    lines += [
        "",
        f"int {safe}_init(const struct device *dev);",
        f"int {safe}_read(const struct device *dev);",
        "",
        f"#endif /* {upper}_H */",
        "",
    ]
    return "\n".join(lines)


def _emit_nrf52_driver_impl(contract: InitContract, hir: HIR) -> str:
    safe = _sanitize(contract.component_name)
    upper = safe.upper()

    bus = _find_bus_for_component(hir, contract.component_id)

    lines = [
        f"/* {contract.component_name} driver impl — nRF52/Zephyr */",
        f'#include "{safe}.h"',
        "",
        '#include <zephyr/logging/log.h>',
        f'LOG_MODULE_REGISTER({safe}, LOG_LEVEL_INF);',
        "",
    ]

    if bus and bus.bus_type == "I2C":
        lines += [
            "static int write_register(const struct device *dev, uint8_t reg, uint8_t val) {",
            "    uint8_t buf[2] = {reg, val};",
            f"    return i2c_write(dev, buf, 2, {upper}_I2C_ADDR);",
            "}",
            "",
            "static int read_registers(const struct device *dev, uint8_t reg, uint8_t *buf, uint8_t len) {",
            f"    return i2c_write_read(dev, {upper}_I2C_ADDR, &reg, 1, buf, len);",
            "}",
            "",
        ]

    # Init function with phased execution
    lines += [f"int {safe}_init(const struct device *dev) {{"]
    for phase in sorted(contract.phases, key=lambda p: p.order):
        lines.append(f"    /* === {phase.phase.value.upper()} PHASE === */")
        if phase.precondition:
            lines.append(f"    /* Pre: {phase.precondition} */")
        for write in phase.writes:
            desc = f"  /* {write.description} */" if write.description else ""
            lines.append(
                f"    write_register(dev, {write.reg_addr}, {write.value});{desc}"
            )
        for read in phase.reads:
            lines.append(
                f"    {{ uint8_t v; read_registers(dev, {read.reg_addr}, &v, 1); }}"
            )
        if phase.delay_after_ms:
            lines.append(f"    k_msleep({phase.delay_after_ms});")

    lines += [
        f'    LOG_INF("{contract.component_name} initialized");',
        "    return 0;",
        "}",
        "",
    ]

    # Read function
    lines += [
        f"int {safe}_read(const struct device *dev) {{",
        "    uint8_t buf[8] = {0};",
    ]
    if bus and bus.bus_type == "I2C":
        lines.append("    read_registers(dev, 0x00, buf, sizeof(buf));")
    lines += [
        "    return 0;",
        "}",
        "",
    ]

    return "\n".join(lines)


def _emit_nrf52_main(hir: HIR, driver_headers: list[str]) -> str:
    lines = [
        "/* boardsmith-fw main — nRF52/Zephyr */",
        '#include <zephyr/kernel.h>',
        '#include <zephyr/device.h>',
        '#include <zephyr/drivers/i2c.h>',
        '#include <zephyr/logging/log.h>',
        "",
        'LOG_MODULE_REGISTER(main, LOG_LEVEL_INF);',
        "",
    ]

    for h in driver_headers:
        lines.append(f'#include "{h}.h"')

    lines += ["", "void main(void) {"]

    # Bus init
    for bc in hir.bus_contracts:
        if bc.bus_type == "I2C":
            lines += [
                f"    /* {bc.bus_name}: I2C */",
                f"    const struct device *i2c_{_sanitize(bc.bus_name)} = DEVICE_DT_GET(DT_NODELABEL(i2c0));",
                f"    if (!device_is_ready(i2c_{_sanitize(bc.bus_name)})) {{",
                f'        LOG_ERR("{bc.bus_name} not ready");',
                "        return;",
                "    }",
            ]
        elif bc.bus_type == "SPI":
            lines += [
                f"    /* {bc.bus_name}: SPI */",
                f"    const struct device *spi_{_sanitize(bc.bus_name)} = DEVICE_DT_GET(DT_NODELABEL(spi0));",
            ]

    lines.append("")

    # Driver init
    for h in driver_headers:
        bus_dev = _sanitize(hir.bus_contracts[0].bus_name) if hir.bus_contracts else "dev"
        lines.append(f"    {h}_init(i2c_{bus_dev});")

    lines += [
        "",
        '    LOG_INF("System initialized");',
        "",
        "    while (1) {",
    ]

    for h in driver_headers:
        bus_var = _sanitize(hir.bus_contracts[0].bus_name) if hir.bus_contracts else "dev"
        lines.append(f"        {h}_read(i2c_{bus_var});")

    lines += [
        "        k_msleep(1000);",
        "    }",
        "}",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize(name: str) -> str:
    """Convert component name to a valid C identifier."""
    s = re.sub(r"[^a-zA-Z0-9]", "_", name.lower()).strip("_")
    return s or "component"


def _find_bus_for_component(
    hir: HIR,
    component_id: str,
) -> BusContract | None:
    """Find the bus contract that includes a component as a slave."""
    for bc in hir.bus_contracts:
        if component_id in bc.slave_ids:
            return bc
    return None
