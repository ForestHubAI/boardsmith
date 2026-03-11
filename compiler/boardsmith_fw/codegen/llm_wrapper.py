# SPDX-License-Identifier: AGPL-3.0-or-later
"""Code generator: LLM-enhanced or template-based firmware generation.

The LLM receives structured JSON (HardwareGraph + ComponentKnowledge)
and generates C/C++ firmware code grounded in that data.
Falls back to templates if no API key is set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from boardsmith_fw.models.component_knowledge import ComponentKnowledge
from boardsmith_fw.models.hardware_graph import HardwareGraph


@dataclass
class GeneratedFile:
    path: str
    content: str


@dataclass
class GenerationResult:
    files: list[GeneratedFile] = field(default_factory=list)
    explanation: str = ""


@dataclass
class GenerationRequest:
    graph: HardwareGraph
    knowledge: list[ComponentKnowledge]
    description: str
    lang: str  # "c" or "cpp"
    target: str = "auto"  # "esp32", "stm32", or "auto" (detect from graph)
    model: str = "gpt-4o"
    rtos: bool = False  # Use FreeRTOS task-per-bus architecture
    rtos_stack_size: int = 4096


def _resolve_target(req: GenerationRequest) -> str:
    """Resolve 'auto' target based on MCU detected in graph."""
    if req.target != "auto":
        return req.target
    if req.graph.mcu:
        from boardsmith_fw.models.hardware_graph import MCUFamily

        if req.graph.mcu.family == MCUFamily.ESP32_C3:
            return "esp32c3"
        if req.graph.mcu.family == MCUFamily.STM32:
            return "stm32"
        if req.graph.mcu.family == MCUFamily.RP2040:
            return "rp2040"
        if req.graph.mcu.family == MCUFamily.NRF52:
            return "nrf52"
    return "esp32"


async def generate_firmware(request: GenerationRequest) -> GenerationResult:
    """Generate firmware — LLM if available, else templates."""
    try:
        from llm.gateway import get_default_gateway
        from llm.types import Message, TaskType

        gateway = get_default_gateway()
        if not gateway.is_llm_available():
            return _generate_from_templates(request)

        system = _build_system_prompt(request)
        user = _build_user_prompt(request)

        response = await gateway.complete(
            task=TaskType.CODE_GEN,
            messages=[Message(role="user", content=user)],
            system=system,
            temperature=0.2,
            max_tokens=8000,
            model_override=request.model if request.model != "gpt-4o" else None,
        )

        if response.skipped or not response.content:
            return _generate_from_templates(request)

        return _parse_llm_response(response.content)
    except Exception:
        return _generate_from_templates(request)


# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

def _build_system_prompt(req: GenerationRequest) -> str:
    lang_label = "C++" if req.lang == "cpp" else "C"
    target = _resolve_target(req)

    if target == "stm32":
        return (
            f"You are an expert embedded systems firmware engineer specializing in STM32.\n"
            f"Generate clean, compilable {lang_label} code for STM32 HAL projects.\n\n"
            "Rules:\n"
            "- Generate ONLY code files. No explanations outside code blocks.\n"
            "- All code must be compilable with arm-none-eabi-gcc and STM32 HAL.\n"
            "- Use the hardware graph and component knowledge to configure pins/buses.\n"
            "- Include proper init sequences from datasheets.\n"
            "- Use STM32 HAL APIs (HAL_StatusTypeDef, HAL_I2C_Mem_Read, etc.).\n"
            "- Use HAL_Delay for timing, printf via SWO/UART for logging.\n"
            '- For each file write "=== FILE: <path> ===" followed by the content.\n'
            '- End with "=== EXPLANATION ===" and a brief explanation.'
        )

    if target == "rp2040":
        return (
            f"You are an expert embedded systems firmware engineer specializing in RP2040.\n"
            f"Generate clean, compilable {lang_label} code for Raspberry Pi Pico SDK projects.\n\n"
            "Rules:\n"
            "- Generate ONLY code files. No explanations outside code blocks.\n"
            "- All code must be compilable with the Pico SDK and arm-none-eabi-gcc.\n"
            "- Use the hardware graph and component knowledge to configure pins/buses.\n"
            "- Include proper init sequences from datasheets.\n"
            "- Use Pico SDK APIs (i2c_write_blocking, spi_write_read_blocking, etc.).\n"
            "- Use sleep_ms for timing, printf via USB/UART for logging.\n"
            '- For each file write "=== FILE: <path> ===" followed by the content.\n'
            '- End with "=== EXPLANATION ===" and a brief explanation.'
        )

    return (
        f"You are an expert embedded systems firmware engineer specializing in ESP32.\n"
        f"Generate clean, compilable {lang_label} code for ESP32 bare-metal/ESP-IDF projects.\n\n"
        "Rules:\n"
        "- Generate ONLY code files. No explanations outside code blocks.\n"
        "- All code must be compilable with the ESP-IDF toolchain.\n"
        "- Use the hardware graph and component knowledge to configure pins/buses.\n"
        "- Include proper init sequences from datasheets.\n"
        "- Use ESP-IDF APIs (esp_err_t, i2c_cmd_handle_t, etc.).\n"
        '- For each file write "=== FILE: <path> ===" followed by the content.\n'
        '- End with "=== EXPLANATION ===" and a brief explanation.'
    )


def _build_user_prompt(req: GenerationRequest) -> str:
    target = _resolve_target(req)
    fallback_mcu = "STM32 (assumed)" if target == "stm32" else "ESP32 (assumed)"
    mcu = f"MCU: {req.graph.mcu.type} ({req.graph.mcu.component_id})" if req.graph.mcu else f"MCU: {fallback_mcu}"

    bus_lines = "\n".join(
        f"{b.type.value} bus \"{b.name}\": nets=[{','.join(b.nets)}] "
        f"master={b.master_component_id or '?'} slaves=[{','.join(b.slave_component_ids)}]"
        for b in req.graph.buses
    ) or "None detected"

    comp_lines = "\n".join(
        f"Component {k.component_id} ({k.mpn}): interface={k.interface.value}"
        + (f" i2c_addr={k.i2c_address}" if k.i2c_address else "")
        + (f" registers={len(k.registers)}" if k.registers else "")
        for k in req.knowledge
    ) or "None with knowledge"

    power = ", ".join(f"{p.name}: {p.voltage}" for p in req.graph.power_domains) or "Default"
    irq = ", ".join(
        f"{i.net}: {i.source_component_id} -> {i.target_component_id}"
        for i in req.graph.irq_lines
    ) or "None"

    ext = "cpp" if req.lang == "cpp" else "c"
    target_label = "STM32 HAL" if target == "stm32" else "ESP32"
    return (
        f"Generate a {target_label} firmware project:\n\n"
        f"FUNCTION: {req.description}\nLANGUAGE: {ext}\n\n"
        f"HARDWARE:\n{mcu}\n\nBUSES:\n{bus_lines}\n\n"
        f"COMPONENTS:\n{comp_lines}\n\n"
        f"POWER DOMAINS:\n{power}\n\nIRQ LINES:\n{irq}\n\n"
        f"Generate: Src/main.{ext}, CMakeLists.txt, Inc/ headers, driver files."
    )


def _parse_llm_response(content: str) -> GenerationResult:
    files: list[GeneratedFile] = []
    explanation = ""

    sections = re.split(r"===\s*FILE:\s*", content, flags=re.IGNORECASE)
    for sec in sections[1:]:
        nl = sec.find("\n")
        fpath = sec[:nl].strip().rstrip("= ").strip()
        body = sec[nl + 1:]

        for marker in ("=== EXPLANATION", "=== FILE:"):
            idx = body.find(marker)
            if idx >= 0:
                body = body[:idx]

        body = re.sub(r"^```\w*\n?", "", body, flags=re.MULTILINE)
        body = re.sub(r"```\s*$", "", body, flags=re.MULTILINE)
        body = body.strip()

        if fpath and body:
            files.append(GeneratedFile(path=fpath, content=body))

    m = re.search(r"===\s*EXPLANATION\s*===\s*\n([\s\S]*)", content, re.IGNORECASE)
    if m:
        explanation = m.group(1).strip()

    return GenerationResult(files=files, explanation=explanation)


# ---------------------------------------------------------------------------
# Template fallback
# ---------------------------------------------------------------------------

def _sanitize(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)[:32]


def _get_pin(bus, signal: str, fallback: str) -> str:
    """Get GPIO from bus.pin_mapping for a signal, or return fallback."""
    for pm in bus.pin_mapping:
        if pm.signal == signal and pm.gpio:
            return pm.gpio
    return fallback


def _generate_from_templates(req: GenerationRequest) -> GenerationResult:
    target = _resolve_target(req)
    if target == "stm32":
        return _generate_stm32_templates(req)
    if target == "rp2040":
        return _generate_rp2040_templates(req)
    return _generate_esp32_templates(req)


# ---------------------------------------------------------------------------
# ESP32 templates
# ---------------------------------------------------------------------------

def _generate_esp32_templates(req: GenerationRequest) -> GenerationResult:
    ext = "cpp" if req.lang == "cpp" else "c"
    files: list[GeneratedFile] = []

    files.append(GeneratedFile(
        path="CMakeLists.txt",
        content=(
            "cmake_minimum_required(VERSION 3.16)\n\n"
            "include($ENV{IDF_PATH}/tools/cmake/project.cmake)\n"
            "project(eagle_firmware)\n"
        ),
    ))

    src_files = [f"main.{ext}"]
    driver_headers: list[str] = []

    for bus in req.graph.buses:
        for slave_id in bus.slave_component_ids:
            comp = next((c for c in req.graph.components if c.id == slave_id), None)
            if not comp:
                continue
            knowledge = next((k for k in req.knowledge if k.component_id == slave_id), None)
            driver_name = f"driver_{_sanitize(comp.value or comp.name)}"
            header = f"{driver_name}.h"
            impl = f"{driver_name}.{ext}"

            files.append(GeneratedFile(
                path=f"main/{header}",
                content=_gen_esp32_driver_header(comp, knowledge, bus.type.value),
            ))
            files.append(GeneratedFile(
                path=f"main/{impl}",
                content=_gen_esp32_driver_impl(comp, knowledge, bus.type.value),
            ))
            src_files.append(impl)
            driver_headers.append(header)

    srcs = " ".join(f'"{f}"' for f in src_files)
    files.append(GeneratedFile(
        path="main/CMakeLists.txt",
        content=f'idf_component_register(\n    SRCS {srcs}\n    INCLUDE_DIRS "."\n)\n',
    ))

    if req.rtos:
        from boardsmith_fw.codegen.rtos_generator import generate_rtos_main_esp32

        rtos_main = generate_rtos_main_esp32(
            graph=req.graph,
            knowledge=req.knowledge,
            description=req.description,
            lang=req.lang,
            driver_headers=driver_headers,
            stack_size=req.rtos_stack_size,
        )
        files.append(rtos_main)
    else:
        files.append(GeneratedFile(
            path=f"main/main.{ext}",
            content=_gen_esp32_main(req, driver_headers),
        ))

    return GenerationResult(
        files=files,
        explanation="Generated ESP32/ESP-IDF project (template-based). "
        "Set OPENAI_API_KEY for LLM-enhanced generation.",
    )


# ---------------------------------------------------------------------------
# STM32 templates
# ---------------------------------------------------------------------------

def _generate_stm32_templates(req: GenerationRequest) -> GenerationResult:
    ext = "cpp" if req.lang == "cpp" else "c"
    files: list[GeneratedFile] = []

    mcu_type = req.graph.mcu.type if req.graph.mcu else "STM32F4"

    # Top-level CMakeLists.txt
    files.append(GeneratedFile(
        path="CMakeLists.txt",
        content=_gen_stm32_cmake(mcu_type, ext),
    ))

    driver_headers: list[str] = []

    for bus in req.graph.buses:
        for slave_id in bus.slave_component_ids:
            comp = next((c for c in req.graph.components if c.id == slave_id), None)
            if not comp:
                continue
            knowledge = next((k for k in req.knowledge if k.component_id == slave_id), None)
            driver_name = f"driver_{_sanitize(comp.value or comp.name)}"
            header = f"{driver_name}.h"
            impl = f"{driver_name}.{ext}"

            files.append(GeneratedFile(
                path=f"Inc/{header}",
                content=_gen_stm32_driver_header(comp, knowledge, bus.type.value),
            ))
            files.append(GeneratedFile(
                path=f"Src/{impl}",
                content=_gen_stm32_driver_impl(comp, knowledge, bus.type.value),
            ))
            driver_headers.append(header)

    files.append(GeneratedFile(
        path=f"Src/main.{ext}",
        content=_gen_stm32_main(req, driver_headers),
    ))

    return GenerationResult(
        files=files,
        explanation=f"Generated STM32 HAL project for {mcu_type} (template-based). "
        "Set OPENAI_API_KEY for LLM-enhanced generation.",
    )


def _gen_esp32_main(req: GenerationRequest, driver_headers: list[str]) -> str:
    includes = "\n".join(f'#include "{h}"' for h in driver_headers)
    extern_c = 'extern "C" ' if req.lang == "cpp" else ""

    init_lines: list[str] = []
    loop_lines: list[str] = []

    for bus in req.graph.buses:
        if bus.type.value == "I2C":
            sda = _get_pin(bus, "SDA", "21")
            scl = _get_pin(bus, "SCL", "22")
            init_lines += [
                "    // Initialize I2C bus",
                "    i2c_config_t i2c_conf = {",
                "        .mode = I2C_MODE_MASTER,",
                f"        .sda_io_num = GPIO_NUM_{sda},",
                f"        .scl_io_num = GPIO_NUM_{scl},",
                "        .sda_pullup_en = GPIO_PULLUP_ENABLE,",
                "        .scl_pullup_en = GPIO_PULLUP_ENABLE,",
                "        .master.clk_speed = 100000,",
                "    };",
                "    i2c_param_config(I2C_NUM_0, &i2c_conf);",
                "    i2c_driver_install(I2C_NUM_0, I2C_MODE_MASTER, 0, 0, 0);",
                "",
            ]
        elif bus.type.value == "SPI":
            mosi = _get_pin(bus, "MOSI", "23")
            miso = _get_pin(bus, "MISO", "19")
            sck = _get_pin(bus, "SCK", "18")
            init_lines += [
                "    // Initialize SPI bus",
                "    spi_bus_config_t spi_conf = {",
                f"        .mosi_io_num = GPIO_NUM_{mosi},",
                f"        .miso_io_num = GPIO_NUM_{miso},",
                f"        .sclk_io_num = GPIO_NUM_{sck},",
                "        .quadwp_io_num = -1,",
                "        .quadhd_io_num = -1,",
                "    };",
                "    spi_bus_initialize(SPI2_HOST, &spi_conf, SPI_DMA_CH_AUTO);",
                "",
            ]
        elif bus.type.value == "UART":
            tx = _get_pin(bus, "TX", "17")
            rx = _get_pin(bus, "RX", "16")
            init_lines += [
                "    // Initialize UART",
                "    uart_config_t uart_conf = {",
                "        .baud_rate = 9600,",
                "        .data_bits = UART_DATA_8_BITS,",
                "        .parity = UART_PARITY_DISABLE,",
                "        .stop_bits = UART_STOP_BITS_1,",
                "        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,",
                "    };",
                "    uart_param_config(UART_NUM_1, &uart_conf);",
                f"    uart_set_pin(UART_NUM_1, GPIO_NUM_{tx}, GPIO_NUM_{rx}, -1, -1);",
                "    uart_driver_install(UART_NUM_1, 1024, 0, 0, NULL, 0);",
                "",
            ]
        elif bus.type.value == "ADC":
            adc_pin = _get_pin(bus, "ADC", "34")
            init_lines += [
                "    // Initialize ADC",
                "    adc1_config_width(ADC_WIDTH_BIT_12);",
                f"    adc1_config_channel_atten(ADC1_CHANNEL_{adc_pin}, ADC_ATTEN_DB_11);",
                "",
            ]
        elif bus.type.value == "PWM":
            pwm_pin = _get_pin(bus, "PWM", "25")
            init_lines += [
                "    // Initialize LEDC PWM",
                "    ledc_timer_config_t ledc_timer = {",
                "        .speed_mode = LEDC_LOW_SPEED_MODE,",
                "        .duty_resolution = LEDC_TIMER_13_BIT,",
                "        .timer_num = LEDC_TIMER_0,",
                "        .freq_hz = 5000,",
                "        .clk_cfg = LEDC_AUTO_CLK,",
                "    };",
                "    ledc_timer_config(&ledc_timer);",
                "    ledc_channel_config_t ledc_ch = {",
                f"        .gpio_num = GPIO_NUM_{pwm_pin},",
                "        .speed_mode = LEDC_LOW_SPEED_MODE,",
                "        .channel = LEDC_CHANNEL_0,",
                "        .timer_sel = LEDC_TIMER_0,",
                "        .duty = 0,",
                "        .hpoint = 0,",
                "    };",
                "    ledc_channel_config(&ledc_ch);",
                "",
            ]

        for slave_id in bus.slave_component_ids:
            comp = next((c for c in req.graph.components if c.id == slave_id), None)
            if not comp:
                continue
            fn = _sanitize(comp.value or comp.name).lower()
            init_lines.append(f"    {fn}_init();")
            loop_lines.append(f"        {fn}_read();")

    return (
        f"/**\n"
        f" * Eagle->ESP32 Generated Firmware\n"
        f" * Function: {req.description}\n"
        f" * Generated by boardsmith-fw CLI\n"
        f" */\n\n"
        f"#include <stdio.h>\n"
        f'#include "freertos/FreeRTOS.h"\n'
        f'#include "freertos/task.h"\n'
        f'#include "driver/i2c.h"\n'
        f'#include "driver/spi_master.h"\n'
        f'#include "driver/uart.h"\n'
        f'#include "driver/gpio.h"\n'
        f'#include "driver/adc.h"\n'
        f'#include "driver/ledc.h"\n'
        f'#include "esp_log.h"\n'
        f"{includes}\n\n"
        f'static const char *TAG = "main";\n\n'
        f"{extern_c}void app_main(void)\n"
        f"{{\n"
        f'    ESP_LOGI(TAG, "Eagle->ESP32 Firmware Starting...");\n'
        f'    ESP_LOGI(TAG, "Function: {req.description}");\n\n'
        f"{chr(10).join(init_lines)}\n\n"
        f'    ESP_LOGI(TAG, "Initialization complete. Entering main loop.");\n\n'
        f"    while (1) {{\n"
        f"{chr(10).join(loop_lines)}\n"
        f"        vTaskDelay(pdMS_TO_TICKS(1000));\n"
        f"    }}\n"
        f"}}\n"
    )


def _gen_esp32_driver_header(comp, knowledge, bus_type: str) -> str:
    fn = _sanitize(comp.value or comp.name).lower()
    guard = fn.upper() + "_H"
    addr = (knowledge.i2c_address if knowledge else None) or "0x00"
    return (
        f"#ifndef {guard}\n#define {guard}\n\n"
        f'#include "esp_err.h"\n\n'
        f"#define {fn.upper()}_I2C_ADDR {addr}\n\n"
        f"esp_err_t {fn}_init(void);\n"
        f"esp_err_t {fn}_read(void);\n\n"
        f"#endif /* {guard} */\n"
    )


def _gen_esp32_driver_impl(comp, knowledge, bus_type: str) -> str:
    fn = _sanitize(comp.value or comp.name).lower()
    addr = (knowledge.i2c_address if knowledge else None) or "0x00"
    name = comp.value or comp.name

    reg_writes = ""
    if knowledge and knowledge.init_sequence:
        for step in knowledge.init_sequence:
            if step.reg_addr and step.value:
                reg_writes += f"    // {step.description}\n"
                reg_writes += f"    ret = write_register({step.reg_addr}, {step.value});\n"
                reg_writes += "    if (ret != ESP_OK) return ret;\n"
                if step.delay_ms:
                    reg_writes += f"    vTaskDelay(pdMS_TO_TICKS({step.delay_ms}));\n"

    init_body = reg_writes if reg_writes else (
        f"    /* No init sequence available for {name} — verify datasheet and add register writes */\n"
        "    ret = ESP_OK;"
    )

    if bus_type == "I2C":
        return (
            f'#include "{fn}.h"\n'
            f'#include "driver/i2c.h"\n'
            f'#include "esp_log.h"\n'
            f'#include "freertos/FreeRTOS.h"\n'
            f'#include "freertos/task.h"\n\n'
            f'static const char *TAG = "{fn}";\n'
            f"#define I2C_PORT I2C_NUM_0\n"
            f"#define I2C_TIMEOUT_MS 1000\n\n"
            f"static esp_err_t write_register(uint8_t reg, uint8_t value)\n{{\n"
            f"    i2c_cmd_handle_t cmd = i2c_cmd_link_create();\n"
            f"    i2c_master_start(cmd);\n"
            f"    i2c_master_write_byte(cmd, ({fn.upper()}_I2C_ADDR << 1) | I2C_MASTER_WRITE, true);\n"
            f"    i2c_master_write_byte(cmd, reg, true);\n"
            f"    i2c_master_write_byte(cmd, value, true);\n"
            f"    i2c_master_stop(cmd);\n"
            f"    esp_err_t ret = i2c_master_cmd_begin(I2C_PORT, cmd, pdMS_TO_TICKS(I2C_TIMEOUT_MS));\n"
            f"    i2c_cmd_link_delete(cmd);\n"
            f"    return ret;\n}}\n\n"
            f"static esp_err_t read_registers(uint8_t reg, uint8_t *data, size_t len)\n{{\n"
            f"    i2c_cmd_handle_t cmd = i2c_cmd_link_create();\n"
            f"    i2c_master_start(cmd);\n"
            f"    i2c_master_write_byte(cmd, ({fn.upper()}_I2C_ADDR << 1) | I2C_MASTER_WRITE, true);\n"
            f"    i2c_master_write_byte(cmd, reg, true);\n"
            f"    i2c_master_start(cmd);\n"
            f"    i2c_master_write_byte(cmd, ({fn.upper()}_I2C_ADDR << 1) | I2C_MASTER_READ, true);\n"
            f"    i2c_master_read(cmd, data, len, I2C_MASTER_LAST_NACK);\n"
            f"    i2c_master_stop(cmd);\n"
            f"    esp_err_t ret = i2c_master_cmd_begin(I2C_PORT, cmd, pdMS_TO_TICKS(I2C_TIMEOUT_MS));\n"
            f"    i2c_cmd_link_delete(cmd);\n"
            f"    return ret;\n}}\n\n"
            f"esp_err_t {fn}_init(void)\n{{\n"
            f'    ESP_LOGI(TAG, "Initializing {name} at I2C addr {addr}");\n'
            f"    esp_err_t ret;\n\n"
            f"{init_body}\n\n"
            f'    ESP_LOGI(TAG, "Init %s", ret == ESP_OK ? "OK" : "FAILED");\n'
            f"    return ret;\n}}\n\n"
            f"esp_err_t {fn}_read(void)\n{{\n"
            f"    uint8_t data[8];\n"
            f"    esp_err_t ret = read_registers(0x00, data, sizeof(data));\n"
            f"    if (ret == ESP_OK) {{\n"
            f'        ESP_LOGI(TAG, "Read: 0x%02x 0x%02x 0x%02x", data[0], data[1], data[2]);\n'
            f"    }}\n"
            f"    return ret;\n}}\n"
        )

    if bus_type == "SPI":
        return (
            f'#include "{fn}.h"\n'
            f'#include "driver/spi_master.h"\n'
            f'#include "driver/gpio.h"\n'
            f'#include "esp_log.h"\n\n'
            f'static const char *TAG = "{fn}";\n'
            f"static spi_device_handle_t spi_handle;\n\n"
            f"esp_err_t {fn}_init(void)\n{{\n"
            f'    ESP_LOGI(TAG, "Initializing {name} (SPI)");\n'
            f"    spi_device_interface_config_t dev_cfg = {{\n"
            f"        .clock_speed_hz = 1000000,\n"
            f"        .mode = 0,\n"
            f"        .spics_io_num = GPIO_NUM_5,\n"
            f"        .queue_size = 1,\n"
            f"    }};\n"
            f"    esp_err_t ret = spi_bus_add_device(SPI2_HOST, &dev_cfg, &spi_handle);\n"
            f'    ESP_LOGI(TAG, "Init %s", ret == ESP_OK ? "OK" : "FAILED");\n'
            f"    return ret;\n}}\n\n"
            f"esp_err_t {fn}_read(void)\n{{\n"
            f"    uint8_t tx[2] = {{0x00, 0x00}};\n"
            f"    uint8_t rx[2] = {{0}};\n"
            f"    spi_transaction_t t = {{ .length = 16, .tx_buffer = tx, .rx_buffer = rx }};\n"
            f"    esp_err_t ret = spi_device_transmit(spi_handle, &t);\n"
            f"    if (ret == ESP_OK) {{\n"
            f'        ESP_LOGI(TAG, "Read: 0x%02x 0x%02x", rx[0], rx[1]);\n'
            f"    }}\n"
            f"    return ret;\n}}\n"
        )

    # UART
    return (
        f'#include "{fn}.h"\n'
        f'#include "driver/uart.h"\n'
        f'#include "esp_log.h"\n\n'
        f'static const char *TAG = "{fn}";\n'
        f"#define UART_PORT UART_NUM_1\n\n"
        f"esp_err_t {fn}_init(void)\n{{\n"
        f'    ESP_LOGI(TAG, "Initializing {name} (UART)");\n'
        f"    return ESP_OK;\n}}\n\n"
        f"esp_err_t {fn}_read(void)\n{{\n"
        f"    uint8_t buf[128];\n"
        f"    int len = uart_read_bytes(UART_PORT, buf, sizeof(buf), pdMS_TO_TICKS(100));\n"
        f"    if (len > 0) {{\n"
        f'        ESP_LOGI(TAG, "Received %d bytes", len);\n'
        f"    }}\n"
        f"    return ESP_OK;\n}}\n"
    )


# ---------------------------------------------------------------------------
# STM32 HAL template helpers
# ---------------------------------------------------------------------------

def _gen_stm32_cmake(mcu_type: str, ext: str) -> str:
    return (
        "cmake_minimum_required(VERSION 3.16)\n"
        "project(eagle_firmware C ASM)\n\n"
        "set(CMAKE_C_STANDARD 11)\n"
        "set(CMAKE_SYSTEM_NAME Generic)\n"
        "set(CMAKE_SYSTEM_PROCESSOR arm)\n"
        "set(CMAKE_C_COMPILER arm-none-eabi-gcc)\n"
        "set(CMAKE_ASM_COMPILER arm-none-eabi-gcc)\n\n"
        f"# Target MCU: {mcu_type}\n"
        "# Adjust linker script and startup file for your specific chip\n\n"
        "add_executable(${PROJECT_NAME}\n"
        f"    Src/main.{ext}\n"
        ")\n\n"
        "target_include_directories(${PROJECT_NAME} PRIVATE Inc)\n"
    )


def _gen_stm32_main(req: GenerationRequest, driver_headers: list[str]) -> str:
    includes = "\n".join(f'#include "{h}"' for h in driver_headers)

    mcu_type = req.graph.mcu.type if req.graph.mcu else "STM32F4"

    init_lines: list[str] = []
    loop_lines: list[str] = []

    for bus in req.graph.buses:
        if bus.type.value == "I2C":
            init_lines += [
                "    /* Initialize I2C1 */",
                "    hi2c1.Instance = I2C1;",
                "    hi2c1.Init.ClockSpeed = 100000;",
                "    hi2c1.Init.DutyCycle = I2C_DUTYCYCLE_2;",
                "    hi2c1.Init.OwnAddress1 = 0;",
                "    hi2c1.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;",
                "    hi2c1.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;",
                "    hi2c1.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;",
                "    hi2c1.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;",
                "    HAL_I2C_Init(&hi2c1);",
                "",
            ]
        elif bus.type.value == "SPI":
            init_lines += [
                "    /* Initialize SPI1 */",
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
                "",
            ]
        elif bus.type.value == "UART":
            init_lines += [
                "    /* Initialize USART2 */",
                "    huart2.Instance = USART2;",
                "    huart2.Init.BaudRate = 115200;",
                "    huart2.Init.WordLength = UART_WORDLENGTH_8B;",
                "    huart2.Init.StopBits = UART_STOPBITS_1;",
                "    huart2.Init.Parity = UART_PARITY_NONE;",
                "    huart2.Init.Mode = UART_MODE_TX_RX;",
                "    huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;",
                "    HAL_UART_Init(&huart2);",
                "",
            ]
        elif bus.type.value == "ADC":
            init_lines += [
                "    /* Initialize ADC1 */",
                "    hadc1.Instance = ADC1;",
                "    hadc1.Init.Resolution = ADC_RESOLUTION_12B;",
                "    hadc1.Init.ScanConvMode = DISABLE;",
                "    hadc1.Init.ContinuousConvMode = DISABLE;",
                "    hadc1.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_NONE;",
                "    hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;",
                "    hadc1.Init.NbrOfConversion = 1;",
                "    HAL_ADC_Init(&hadc1);",
                "",
            ]
        elif bus.type.value == "PWM":
            init_lines += [
                "    /* Initialize TIM1 PWM */",
                "    htim1.Instance = TIM1;",
                "    htim1.Init.Prescaler = 84 - 1;",
                "    htim1.Init.CounterMode = TIM_COUNTERMODE_UP;",
                "    htim1.Init.Period = 1000 - 1;",
                "    htim1.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;",
                "    HAL_TIM_PWM_Init(&htim1);",
                "    HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_1);",
                "",
            ]

        for slave_id in bus.slave_component_ids:
            comp = next((c for c in req.graph.components if c.id == slave_id), None)
            if not comp:
                continue
            fn = _sanitize(comp.value or comp.name).lower()
            init_lines.append(f"    {fn}_init();")
            loop_lines.append(f"        {fn}_read();")

    # Determine which HAL handles to declare
    has_i2c = any(b.type.value == "I2C" for b in req.graph.buses)
    has_spi = any(b.type.value == "SPI" for b in req.graph.buses)
    has_uart = any(b.type.value == "UART" for b in req.graph.buses)
    has_adc = any(b.type.value == "ADC" for b in req.graph.buses)
    has_pwm = any(b.type.value == "PWM" for b in req.graph.buses)

    handle_decls = ""
    if has_i2c:
        handle_decls += "I2C_HandleTypeDef hi2c1;\n"
    if has_spi:
        handle_decls += "SPI_HandleTypeDef hspi1;\n"
    if has_uart:
        handle_decls += "UART_HandleTypeDef huart2;\n"
    if has_adc:
        handle_decls += "ADC_HandleTypeDef hadc1;\n"
    if has_pwm:
        handle_decls += "TIM_HandleTypeDef htim1;\n"

    return (
        f"/**\n"
        f" * Eagle->STM32 Generated Firmware\n"
        f" * MCU: {mcu_type}\n"
        f" * Function: {req.description}\n"
        f" * Generated by boardsmith-fw CLI\n"
        f" */\n\n"
        f"#include <stdio.h>\n"
        f"#include <stdint.h>\n"
        f'#include "stm32f4xx_hal.h"\n'
        f"{includes}\n\n"
        f"{handle_decls}\n"
        f"void SystemClock_Config(void);\n"
        f"static void MX_GPIO_Init(void);\n\n"
        f"int main(void)\n"
        f"{{\n"
        f"    HAL_Init();\n"
        f"    SystemClock_Config();\n"
        f"    MX_GPIO_Init();\n\n"
        f"{chr(10).join(init_lines)}\n\n"
        f"    while (1) {{\n"
        f"{chr(10).join(loop_lines)}\n"
        f"        HAL_Delay(1000);\n"
        f"    }}\n"
        f"}}\n\n"
        f"void SystemClock_Config(void)\n"
        f"{{\n"
        f"    /* Clock configuration for {mcu_type} — generated scaffold */\n"
        f"    RCC_OscInitTypeDef RCC_OscInitStruct = {{0}};\n"
        f"    RCC_ClkInitTypeDef RCC_ClkInitStruct = {{0}};\n\n"
        f"    /* Enable HSI oscillator */\n"
        f"    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;\n"
        f"    RCC_OscInitStruct.HSIState = RCC_HSI_ON;\n"
        f"    RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;\n"
        f"    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;\n"
        f"    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;\n"
        f"    RCC_OscInitStruct.PLL.PLLM = 8;\n"
        f"    RCC_OscInitStruct.PLL.PLLN = 168;\n"
        f"    RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;\n"
        f"    RCC_OscInitStruct.PLL.PLLQ = 4;\n"
        f"    HAL_RCC_OscConfig(&RCC_OscInitStruct);\n\n"
        f"    /* Configure AHB/APB clocks */\n"
        f"    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK\n"
        f"                                | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;\n"
        f"    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;\n"
        f"    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;\n"
        f"    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV4;\n"
        f"    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV2;\n"
        f"    HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_5);\n"
        f"}}\n\n"
        f"static void MX_GPIO_Init(void)\n"
        f"{{\n"
        f"    __HAL_RCC_GPIOA_CLK_ENABLE();\n"
        f"    __HAL_RCC_GPIOB_CLK_ENABLE();\n"
        f"    __HAL_RCC_GPIOC_CLK_ENABLE();\n"
        f"}}\n"
    )


def _gen_stm32_driver_header(comp, knowledge, bus_type: str) -> str:
    fn = _sanitize(comp.value or comp.name).lower()
    guard = fn.upper() + "_H"
    addr = (knowledge.i2c_address if knowledge else None) or "0x00"

    extra = ""
    if bus_type == "I2C":
        extra = (
            f"#define {fn.upper()}_I2C_ADDR ({addr} << 1)\n\n"
            f"extern I2C_HandleTypeDef hi2c1;\n\n"
        )
    elif bus_type == "SPI":
        extra = "extern SPI_HandleTypeDef hspi1;\n\n"
    elif bus_type == "UART":
        extra = "extern UART_HandleTypeDef huart2;\n\n"

    return (
        f"#ifndef {guard}\n#define {guard}\n\n"
        f'#include "stm32f4xx_hal.h"\n\n'
        f"{extra}"
        f"HAL_StatusTypeDef {fn}_init(void);\n"
        f"HAL_StatusTypeDef {fn}_read(void);\n\n"
        f"#endif /* {guard} */\n"
    )


def _gen_stm32_driver_impl(comp, knowledge, bus_type: str) -> str:
    fn = _sanitize(comp.value or comp.name).lower()
    addr = (knowledge.i2c_address if knowledge else None) or "0x00"
    name = comp.value or comp.name

    reg_writes = ""
    if knowledge and knowledge.init_sequence:
        for step in knowledge.init_sequence:
            if step.reg_addr and step.value:
                reg_writes += f"    /* {step.description} */\n"
                reg_writes += f"    reg = {step.reg_addr}; val = {step.value};\n"
                reg_writes += f"    ret = HAL_I2C_Mem_Write(&hi2c1, {fn.upper()}_I2C_ADDR, reg, 1, &val, 1, 100);\n"
                reg_writes += "    if (ret != HAL_OK) return ret;\n"
                if step.delay_ms:
                    reg_writes += f"    HAL_Delay({step.delay_ms});\n"

    if bus_type == "I2C":
        fallback = (
            f"    /* No init sequence available for {name} — verify datasheet and add register writes */\n"
            "    ret = HAL_OK;"
        )
        init_body = reg_writes if reg_writes else fallback
        return (
            f'#include "{fn}.h"\n'
            f"#include <stdio.h>\n\n"
            f"HAL_StatusTypeDef {fn}_init(void)\n{{\n"
            f"    HAL_StatusTypeDef ret;\n"
            f"    uint8_t reg, val;\n\n"
            f'    /* Initializing {name} at I2C addr {addr} */\n'
            f"{init_body}\n\n"
            f"    return ret;\n}}\n\n"
            f"HAL_StatusTypeDef {fn}_read(void)\n{{\n"
            f"    uint8_t data[8];\n"
            f"    HAL_StatusTypeDef ret = HAL_I2C_Mem_Read(\n"
            f"        &hi2c1, {fn.upper()}_I2C_ADDR, 0x00, 1, data, sizeof(data), 100\n"
            f"    );\n"
            f"    return ret;\n}}\n"
        )

    if bus_type == "SPI":
        return (
            f'#include "{fn}.h"\n'
            f"#include <stdio.h>\n\n"
            f"HAL_StatusTypeDef {fn}_init(void)\n{{\n"
            f'    /* Initializing {name} (SPI) */\n'
            f"    return HAL_OK;\n}}\n\n"
            f"HAL_StatusTypeDef {fn}_read(void)\n{{\n"
            f"    uint8_t tx[2] = {{0x00, 0x00}};\n"
            f"    uint8_t rx[2] = {{0}};\n"
            f"    HAL_StatusTypeDef ret = HAL_SPI_TransmitReceive(&hspi1, tx, rx, 2, 100);\n"
            f"    return ret;\n}}\n"
        )

    # UART
    return (
        f'#include "{fn}.h"\n'
        f"#include <stdio.h>\n\n"
        f"HAL_StatusTypeDef {fn}_init(void)\n{{\n"
        f'    /* Initializing {name} (UART) */\n'
        f"    return HAL_OK;\n}}\n\n"
        f"HAL_StatusTypeDef {fn}_read(void)\n{{\n"
        f"    uint8_t buf[128];\n"
        f"    HAL_StatusTypeDef ret = HAL_UART_Receive(&huart2, buf, sizeof(buf), 100);\n"
        f"    return ret;\n}}\n"
    )


# ---------------------------------------------------------------------------
# RP2040 / Pico SDK templates
# ---------------------------------------------------------------------------

def _generate_rp2040_templates(req: GenerationRequest) -> GenerationResult:
    ext = "cpp" if req.lang == "cpp" else "c"
    files: list[GeneratedFile] = []

    project_name = "eagle_firmware"
    src_files = [f"main.{ext}"]
    driver_headers: list[str] = []

    for bus in req.graph.buses:
        for slave_id in bus.slave_component_ids:
            comp = next(
                (c for c in req.graph.components if c.id == slave_id), None
            )
            if not comp:
                continue
            knowledge = next(
                (k for k in req.knowledge if k.component_id == slave_id), None
            )
            driver_name = f"driver_{_sanitize(comp.value or comp.name)}"
            header = f"{driver_name}.h"
            impl = f"{driver_name}.{ext}"

            files.append(GeneratedFile(
                path=f"src/{header}",
                content=_gen_rp2040_driver_header(comp, knowledge, bus.type.value),
            ))
            files.append(GeneratedFile(
                path=f"src/{impl}",
                content=_gen_rp2040_driver_impl(comp, knowledge, bus.type.value),
            ))
            src_files.append(impl)
            driver_headers.append(header)

    files.append(GeneratedFile(
        path="CMakeLists.txt",
        content=_gen_rp2040_cmake(project_name, ext, src_files),
    ))

    files.append(GeneratedFile(
        path=f"src/main.{ext}",
        content=_gen_rp2040_main(req, driver_headers),
    ))

    return GenerationResult(
        files=files,
        explanation="Generated RP2040/Pico SDK project (template-based). "
        "Set OPENAI_API_KEY for LLM-enhanced generation.",
    )


def _gen_rp2040_cmake(project_name: str, ext: str, src_files: list[str]) -> str:
    srcs = "\n    ".join(f"src/{f}" for f in src_files)
    return (
        "cmake_minimum_required(VERSION 3.13)\n\n"
        "include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)\n\n"
        f"project({project_name} C CXX ASM)\n"
        "set(CMAKE_C_STANDARD 11)\n"
        "set(CMAKE_CXX_STANDARD 17)\n\n"
        "pico_sdk_init()\n\n"
        f"add_executable(${{PROJECT_NAME}}\n"
        f"    {srcs}\n"
        ")\n\n"
        "target_include_directories(${PROJECT_NAME} PRIVATE src)\n\n"
        "target_link_libraries(${PROJECT_NAME}\n"
        "    pico_stdlib\n"
        "    hardware_i2c\n"
        "    hardware_spi\n"
        "    hardware_uart\n"
        "    hardware_gpio\n"
        "    hardware_adc\n"
        "    hardware_pwm\n"
        ")\n\n"
        "pico_add_extra_outputs(${PROJECT_NAME})\n"
        "pico_enable_stdio_usb(${PROJECT_NAME} 1)\n"
        "pico_enable_stdio_uart(${PROJECT_NAME} 0)\n"
    )


def _gen_rp2040_main(req: GenerationRequest, driver_headers: list[str]) -> str:
    includes = "\n".join(f'#include "{h}"' for h in driver_headers)

    init_lines: list[str] = []
    loop_lines: list[str] = []

    for bus in req.graph.buses:
        if bus.type.value == "I2C":
            sda = _get_pin(bus, "SDA", "4")
            scl = _get_pin(bus, "SCL", "5")
            init_lines += [
                "    // Initialize I2C0",
                "    i2c_init(i2c0, 100 * 1000);",
                f"    gpio_set_function({sda}, GPIO_FUNC_I2C);",
                f"    gpio_set_function({scl}, GPIO_FUNC_I2C);",
                f"    gpio_pull_up({sda});",
                f"    gpio_pull_up({scl});",
                "",
            ]
        elif bus.type.value == "SPI":
            mosi = _get_pin(bus, "MOSI", "19")
            miso = _get_pin(bus, "MISO", "16")
            sck = _get_pin(bus, "SCK", "18")
            init_lines += [
                "    // Initialize SPI0",
                "    spi_init(spi0, 1000 * 1000);",
                f"    gpio_set_function({miso}, GPIO_FUNC_SPI);",
                f"    gpio_set_function({sck}, GPIO_FUNC_SPI);",
                f"    gpio_set_function({mosi}, GPIO_FUNC_SPI);",
                "",
            ]
        elif bus.type.value == "UART":
            tx = _get_pin(bus, "TX", "0")
            rx = _get_pin(bus, "RX", "1")
            init_lines += [
                "    // Initialize UART0",
                "    uart_init(uart0, 9600);",
                f"    gpio_set_function({tx}, GPIO_FUNC_UART);",
                f"    gpio_set_function({rx}, GPIO_FUNC_UART);",
                "",
            ]
        elif bus.type.value == "ADC":
            adc_pin = _get_pin(bus, "ADC", "26")
            init_lines += [
                "    // Initialize ADC",
                "    adc_init();",
                f"    adc_gpio_init({adc_pin});",
                f"    adc_select_input({adc_pin} - 26);",
                "",
            ]
        elif bus.type.value == "PWM":
            pwm_pin = _get_pin(bus, "PWM", "25")
            init_lines += [
                "    // Initialize PWM",
                f"    gpio_set_function({pwm_pin}, GPIO_FUNC_PWM);",
                f"    uint slice = pwm_gpio_to_slice_num({pwm_pin});",
                "    pwm_set_wrap(slice, 65535);",
                "    pwm_set_enabled(slice, true);",
                "",
            ]

        for slave_id in bus.slave_component_ids:
            comp = next(
                (c for c in req.graph.components if c.id == slave_id), None
            )
            if not comp:
                continue
            fn = _sanitize(comp.value or comp.name).lower()
            init_lines.append(f"    {fn}_init();")
            loop_lines.append(f"        {fn}_read();")

    return (
        f"/**\n"
        f" * Eagle->RP2040 Generated Firmware\n"
        f" * Function: {req.description}\n"
        f" * Generated by boardsmith-fw CLI\n"
        f" */\n\n"
        f"#include <stdio.h>\n"
        f'#include "pico/stdlib.h"\n'
        f'#include "hardware/i2c.h"\n'
        f'#include "hardware/spi.h"\n'
        f'#include "hardware/uart.h"\n'
        f'#include "hardware/gpio.h"\n'
        f'#include "hardware/adc.h"\n'
        f'#include "hardware/pwm.h"\n'
        f"{includes}\n\n"
        f"int main(void)\n"
        f"{{\n"
        f"    stdio_init_all();\n"
        f'    printf(\"Eagle->RP2040 Firmware Starting...\\n\");\n\n'
        f"{chr(10).join(init_lines)}\n\n"
        f'    printf(\"Initialization complete.\\n\");\n\n'
        f"    while (1) {{\n"
        f"{chr(10).join(loop_lines)}\n"
        f"        sleep_ms(1000);\n"
        f"    }}\n\n"
        f"    return 0;\n"
        f"}}\n"
    )


def _gen_rp2040_driver_header(comp, knowledge, bus_type: str) -> str:
    fn = _sanitize(comp.value or comp.name).lower()
    guard = fn.upper() + "_H"
    addr = (knowledge.i2c_address if knowledge else None) or "0x00"

    extra = ""
    if bus_type == "I2C":
        extra = f"#define {fn.upper()}_I2C_ADDR {addr}\n\n"

    return (
        f"#ifndef {guard}\n#define {guard}\n\n"
        f'#include "pico/stdlib.h"\n\n'
        f"{extra}"
        f"int {fn}_init(void);\n"
        f"int {fn}_read(void);\n\n"
        f"#endif /* {guard} */\n"
    )


def _gen_rp2040_driver_impl(comp, knowledge, bus_type: str) -> str:
    fn = _sanitize(comp.value or comp.name).lower()
    addr = (knowledge.i2c_address if knowledge else None) or "0x00"
    name = comp.value or comp.name

    reg_writes = ""
    if knowledge and knowledge.init_sequence:
        for step in knowledge.init_sequence:
            if step.reg_addr and step.value:
                reg_writes += f"    /* {step.description} */\n"
                reg_writes += (
                    f"    buf[0] = {step.reg_addr}; buf[1] = {step.value};\n"
                )
                reg_writes += (
                    f"    ret = i2c_write_blocking("
                    f"i2c0, {fn.upper()}_I2C_ADDR, buf, 2, false);\n"
                )
                reg_writes += "    if (ret < 0) return ret;\n"
                if step.delay_ms:
                    reg_writes += f"    sleep_ms({step.delay_ms});\n"

    if bus_type == "I2C":
        fallback = (
            f"    /* No init sequence available for {name} — verify datasheet and add register writes */\n"
            "    ret = 0;"
        )
        init_body = reg_writes if reg_writes else fallback
        return (
            f'#include "{fn}.h"\n'
            f'#include "hardware/i2c.h"\n'
            f"#include <stdio.h>\n\n"
            f"int {fn}_init(void)\n{{\n"
            f"    int ret;\n"
            f"    uint8_t buf[2];\n\n"
            f'    printf("Initializing {name} at I2C addr {addr}\\n");\n\n'
            f"{init_body}\n\n"
            f'    printf("Init %s\\n", ret >= 0 ? "OK" : "FAILED");\n'
            f"    return ret >= 0 ? 0 : ret;\n}}\n\n"
            f"int {fn}_read(void)\n{{\n"
            f"    uint8_t reg = 0x00;\n"
            f"    uint8_t data[8];\n"
            f"    int ret = i2c_write_blocking("
            f"i2c0, {fn.upper()}_I2C_ADDR, &reg, 1, true);\n"
            f"    if (ret < 0) return ret;\n"
            f"    ret = i2c_read_blocking("
            f"i2c0, {fn.upper()}_I2C_ADDR, data, sizeof(data), false);\n"
            f"    if (ret >= 0) {{\n"
            f'        printf("{name}: 0x%02x 0x%02x 0x%02x\\n",'
            f" data[0], data[1], data[2]);\n"
            f"    }}\n"
            f"    return ret >= 0 ? 0 : ret;\n}}\n"
        )

    if bus_type == "SPI":
        return (
            f'#include "{fn}.h"\n'
            f'#include "hardware/spi.h"\n'
            f'#include "hardware/gpio.h"\n'
            f"#include <stdio.h>\n\n"
            f"#define CS_PIN 17\n\n"
            f"int {fn}_init(void)\n{{\n"
            f'    printf("Initializing {name} (SPI)\\n");\n'
            f"    gpio_init(CS_PIN);\n"
            f"    gpio_set_dir(CS_PIN, GPIO_OUT);\n"
            f"    gpio_put(CS_PIN, 1);\n"
            f"    return 0;\n}}\n\n"
            f"int {fn}_read(void)\n{{\n"
            f"    uint8_t tx[2] = {{0x00, 0x00}};\n"
            f"    uint8_t rx[2] = {{0}};\n"
            f"    gpio_put(CS_PIN, 0);\n"
            f"    spi_write_read_blocking(spi0, tx, rx, 2);\n"
            f"    gpio_put(CS_PIN, 1);\n"
            f'    printf("{name}: 0x%02x 0x%02x\\n", rx[0], rx[1]);\n'
            f"    return 0;\n}}\n"
        )

    # UART
    return (
        f'#include "{fn}.h"\n'
        f'#include "hardware/uart.h"\n'
        f"#include <stdio.h>\n\n"
        f"int {fn}_init(void)\n{{\n"
        f'    printf("Initializing {name} (UART)\\n");\n'
        f"    return 0;\n}}\n\n"
        f"int {fn}_read(void)\n{{\n"
        f"    uint8_t buf[128];\n"
        f"    int len = 0;\n"
        f"    while (uart_is_readable(uart0) && len < (int)sizeof(buf)) {{\n"
        f"        buf[len++] = uart_getc(uart0);\n"
        f"    }}\n"
        f"    if (len > 0) {{\n"
        f'        printf("Received %d bytes\\n", len);\n'
        f"    }}\n"
        f"    return 0;\n}}\n"
    )
