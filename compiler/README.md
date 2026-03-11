# boardsmith-fw — Hardware-Aware Firmware Compiler

CLI tool that compiles **Eagle/KiCad schematics** into validated, compilable **ESP32/STM32/RP2040** firmware projects.

Not a code generator — a **semantic hardware compiler** that understands bus protocols, register contracts, timing constraints, and power sequencing.

## What It Does

```
Schematic (.sch/.kicad_sch)
    -> Parser (Eagle XML / KiCad S-expr)
    -> HardwareGraph (topology: components, buses, power domains)
    -> HIR (semantics: bus contracts, init sequences, constraints)
    -> Constraint Solver (voltage levels, clock negotiation, pin conflicts)
    -> Code Generation (contract-driven C drivers + LLM-assisted glue)
    -> Compilable firmware project
```

**The idea:** Design your schematic, run `boardsmith-fw generate`, get a compilable firmware project. No datasheet reading, no register mapping, no boilerplate.

## Supported Inputs

| Format | Parser | Status |
|--------|--------|--------|
| Eagle `.sch` (XML) | lxml | Full support (Eagle 6+/7+/9+) |
| KiCad `.kicad_sch` (S-expr) | Built-in | Full support (KiCad 6+/7+/8+) |
| Netlist `.net`/`.txt` | Built-in | Basic support |

## Supported Targets

| MCU | Framework | Code Style |
|-----|-----------|------------|
| **ESP32** | ESP-IDF | `i2c_master_write_to_device`, FreeRTOS tasks |
| **STM32** | STM32 HAL | `HAL_I2C_Master_Transmit`, `HAL_Init` |
| **RP2040** | Pico SDK | `i2c_write_blocking`, `gpio_set_function` |

Auto-detection: the parser identifies the MCU from the schematic and selects the right target.

## Key Features

- **HIR (Hardware Intermediate Representation)** — formal contracts between schematic topology and generated code
- **Constraint Solver** — validates voltage levels, clock feasibility, I2C pullups, pin conflicts before generating code
- **50+ Component Knowledge DB** — real register addresses, init sequences, and timing data for sensors, displays, comms modules, memory, motor drivers, RTCs, and more
- **Contract-Driven Code Generation** — every generated line traces to a BusContract, InitContract, or PowerSequence (not hardcoded templates)
- **LLM Datasheet Extraction** — feed a PDF, get structured ComponentKnowledge (registers, init, timing)
- **FreeRTOS** — optional task-per-bus architecture (`--rtos`)
- **PlatformIO** — generate `platformio.ini` (`--platformio`)
- **CI/CD** — generate GitHub Actions workflow (`--ci`)
- **Incremental Regeneration** — fingerprint-based change detection, only regenerate what changed

## Installation

```bash
pip install -e ".[dev]"
```

This installs the `boardsmith-fw` CLI command.

## Quick Start

```bash
# 1. Import a schematic
boardsmith-fw import fixtures/esp32_bme280_i2c/esp32_bme280.sch --out output

# 2. Analyze hardware (generates hardware_graph.json + analysis.md)
boardsmith-fw analyze --out output

# 3. Generate firmware
cd output
boardsmith-fw generate --description "Read BME280 sensor data every second" --lang c

# 4. Build (requires ESP-IDF / STM32 toolchain / Pico SDK)
boardsmith-fw build --project generated_firmware
```

## Commands

| Command | Description |
|---------|-------------|
| `boardsmith-fw import <path>` | Parse schematic/netlist into internal model |
| `boardsmith-fw analyze` | Build hardware graph + analysis report |
| `boardsmith-fw research` | Search datasheets, extract component knowledge |
| `boardsmith-fw generate` | Generate firmware from graph + knowledge + HIR |
| `boardsmith-fw build` | Compile with target toolchain |
| `boardsmith-fw flash` | Flash firmware to MCU |
| `boardsmith-fw monitor` | Serial monitor (miniterm) |
| `boardsmith-fw verify` | Compile-check via Docker or local toolchain |
| `boardsmith-fw extract <pdf>` | Extract component knowledge from datasheet PDF |
| `boardsmith-fw knowledge [mpn]` | Browse the built-in component knowledge DB |
| `boardsmith-fw init` | Generate default `.boardsmith-fw.yaml` config |

### Generation Options

```bash
boardsmith-fw generate \
  --description "Read temperature and humidity" \
  --lang c \
  --target auto \
  --rtos \
  --platformio \
  --ci \
  --out firmware
```

## Architecture

```
boardsmith_fw/
├── parser/
│   ├── eagle_parser.py          # Eagle .sch XML parser
│   └── kicad_parser.py          # KiCad .kicad_sch S-expression parser
├── models/
│   ├── hardware_graph.py        # HardwareGraph (components, buses, power domains)
│   ├── component_knowledge.py   # ComponentKnowledge (registers, init, timing)
│   └── hir.py                   # HIR (BusContract, InitContract, PowerSequence, Constraints)
├── analysis/
│   ├── graph_builder.py         # Schematic -> HardwareGraph (bus/power detection)
│   ├── hir_builder.py           # HardwareGraph + Knowledge -> HIR
│   ├── constraint_solver.py     # Formal constraint validation
│   ├── timing_engine.py         # Bus timing validation
│   ├── conflict_detector.py     # Pin/address conflict detection
│   └── analysis_report.py       # Markdown report generator
├── knowledge/
│   ├── builtin_db.py            # 50+ components, 110+ MPN entries
│   ├── components/              # Modular knowledge: sensors, displays, comms, ...
│   ├── resolver.py              # Knowledge resolution chain (builtin -> cache -> LLM)
│   ├── extractor.py             # LLM-based datasheet extraction pipeline
│   └── prompts.py               # Structured extraction prompts
├── codegen/
│   ├── hir_codegen.py           # HIR -> C firmware (ESP32/STM32/RP2040)
│   ├── llm_wrapper.py           # LLM-assisted code generation + template fallback
│   ├── rtos_generator.py        # FreeRTOS task-per-bus architecture
│   ├── platformio.py            # PlatformIO project generation
│   ├── ci_templates.py          # GitHub Actions workflows
│   └── fingerprint.py           # Incremental regeneration
├── commands/                    # CLI command implementations
└── cli.py                       # Typer CLI entry point
```

## How the HIR Works

The **Hardware Intermediate Representation** sits between the schematic and code generation:

1. **BusContract** — protocol requirements: which pins, what clock speed (negotiated from the slowest slave), I2C addresses, SPI modes
2. **InitContract** — phased initialization: RESET -> VERIFY (chip ID) -> CONFIGURE -> CALIBRATE -> ENABLE, with register writes/reads and delays
3. **PowerSequence** — topological startup order: 3V3 before 1V8, with inter-rail delays
4. **Constraints** — formal checks: voltage level compatibility, clock feasibility, pullup resistance, pin conflicts

The constraint solver validates all of this **before** generating a single line of code.

## Component Knowledge DB

50+ components with real datasheet data:

| Category | Count | Examples |
|----------|-------|----------|
| Sensors | 21 | BME280, MPU6050, VL53L0X, INA219, ADS1115 |
| Displays | 7 | SSD1306, ST7789, ILI9341, MAX7219 |
| Communication | 7 | SX1276 (LoRa), NRF24L01, MCP2515 (CAN), W5500 |
| Memory | 4 | W25Q128 (SPI Flash), AT24C256 (EEPROM) |
| Motor/Power | 4 | DRV8825, PCA9685, TB6612FNG |
| Misc (RTC, I/O) | 7 | DS3231, MCP23017, TCA9548A |

Each entry includes register addresses, init sequences, timing constraints, and field-level bit definitions from actual datasheets.

## Configuration

| Environment Variable | Description |
|---------------------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for LLM-enhanced code generation and datasheet extraction |
| `IDF_PATH` | Path to ESP-IDF installation (for `build` command with ESP32 target) |

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Test (289 tests)
pytest

# Lint
ruff check boardsmith_fw/ tests/

# Type check
mypy boardsmith_fw/
```

## Test Fixtures

| Fixture | Description |
|---------|-------------|
| `esp32_bme280_i2c` | ESP32 + BME280 I2C sensor |
| `stm32f4_bme280_i2c` | STM32F4 + BME280 I2C sensor |
| `rp2040_bme280_i2c` | RP2040 + BME280 I2C sensor |
| `esp32_multi_bus` | ESP32 + I2C + SPI + UART (3 buses) |
| `kicad_bme280_i2c` | KiCad format BME280 schematic |

## License

MIT
