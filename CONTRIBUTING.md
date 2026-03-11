# Contributing to Boardsmith

The fastest way to make Boardsmith better: **add a component**. It takes ~20 minutes, you don't need to understand the architecture, and every new part immediately works in the pipeline for everyone.

Three ways to contribute, ordered by effort:

1. **[Add a component](#adding-components)** — 20 minutes, no architecture knowledge needed
2. **[Fix a bug or improve a stage](#development-workflow)** — standard open-source flow
3. **[Add an agent or pipeline stage](#adding-agents)** — deeper, read the architecture first

---

## Adding Components

This is the highest-value contribution. The knowledge base drives everything -- component selection, topology synthesis, BOM generation, and firmware init sequences. Every verified component makes Boardsmith more useful for everyone.

### How the knowledge base works

Components live in category files under `shared/knowledge/seed/`:

```
shared/knowledge/seed/
├── sensor.py       <- BME280, MPU6050, SCD41, ...
├── display.py      <- SSD1306, ST7789, ...
├── mcu.py          <- ESP32, RP2040, STM32F4, ...
├── comms.py        <- SX1276 LoRa, nRF24L01, ...
├── power.py        <- LDOs, DC-DC converters
├── memory.py       <- Flash, EEPROM, FRAM
├── actuator.py     <- Motors, servos, relays
└── other.py        <- Everything else
```

Each entry is a Python `TypedDict`. When you run `pytest`, the DB is rebuilt from these files automatically.

### Minimal component entry

The minimum viable entry for a sensor:

```python
# shared/knowledge/seed/sensor.py

ComponentEntry(
    mpn="SHT31-DIS",
    manufacturer="Sensirion",
    name="SHT31 Temperature and Humidity Sensor",
    category="sensor",
    sub_type="temp_humidity",
    description="High-accuracy I2C temperature and humidity sensor",
    interface_types=["I2C"],
    package="DFN-8",
    mounting="smd",
    electrical_ratings=ElectricalRatings(
        vdd_min=2.4,
        vdd_max=5.5,
        current_draw_typical_ma=0.3,
    ),
    timing_caps=TimingCaps(
        i2c_max_clock_hz=1_000_000,
        i2c_modes=["standard", "fast", "fast-plus"],
    ),
    known_i2c_addresses=["0x44", "0x45"],
    i2c_address_selectable=True,
    unit_cost_usd=2.50,
    tags=["temperature", "humidity", "i2c", "sensirion"],
    datasheet_url="https://sensirion.com/media/documents/213E6A3B/63A5A569/Datasheet_SHT3x_DIS.pdf",
    status="active",
    capabilities={
        "measures": ["temperature", "humidity"],
        "temp_range_c": [-40, 125],
        "temp_accuracy_c": 0.3,
        "humidity_range_pct": [0, 100],
        "humidity_accuracy_pct": 2.0,
    },
    library_support=["arduino", "micropython", "esp-idf", "zephyr"],
),
```

### Full component schema

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `mpn` | `str` | yes | Manufacturer part number, e.g. `"BME280"` |
| `manufacturer` | `str` | yes | e.g. `"Bosch Sensortec"` |
| `name` | `str` | yes | Human-readable name |
| `category` | `str` | yes | `sensor`, `mcu`, `display`, `comms`, `memory`, `power`, `actuator`, `other` |
| `sub_type` | `str` | yes | e.g. `"imu"`, `"oled"`, `"lora"`, `"ldo"` |
| `description` | `str` | yes | One sentence |
| `interface_types` | `list[str]` | yes | `["I2C"]`, `["SPI"]`, `["I2C", "SPI"]` |
| `package` | `str` | -- | `"QFN-24"`, `"DFN-8"`, `"Module"` |
| `mounting` | `str` | -- | `"smd"`, `"tht"`, `"module"` |
| `electrical_ratings` | `ElectricalRatings` | yes | At minimum: `vdd_min`, `vdd_max` |
| `timing_caps` | `TimingCaps` | yes | Max clock frequency for the interface |
| `known_i2c_addresses` | `list[str]` | if I2C | Hex strings: `["0x76", "0x77"]` |
| `i2c_address_selectable` | `bool` | if I2C | Can address be changed with ADDR pin? |
| `unit_cost_usd` | `float` | yes | Rough single-unit price |
| `tags` | `list[str]` | yes | Lowercase keywords for search |
| `datasheet_url` | `str` | yes | Direct PDF link preferred |
| `status` | `str` | yes | `"active"`, `"nrnd"`, `"obsolete"` |
| `capabilities` | `dict` | yes | Category-specific specs (see below) |
| `library_support` | `list[str]` | -- | `["arduino", "esp-idf", "micropython"]` |
| `init_contract_template` | `InitContractTemplate` | -- | Register init sequence (advanced) |

### Capabilities by category

```python
# sensor
capabilities={
    "measures": ["temperature", "pressure", "humidity"],
    "temp_range_c": [-40, 85],
    "resolution_bits": 16,
}

# display
capabilities={
    "resolution": [128, 64],
    "color": False,
    "protocol": "I2C",
    "driver_ic": "SSD1306",
}

# comms
capabilities={
    "frequency_band_mhz": 868,
    "protocol": "LoRa",
    "max_output_dbm": 20,
    "spreading_factors": [7, 8, 9, 10, 11, 12],
}

# mcu
capabilities={
    "cores": 2,
    "max_freq_mhz": 240,
    "flash_kb": 0,
    "ram_kb": 520,
    "gpio_count": 34,
    "wifi": True,
    "bluetooth": True,
}
```

### Step by step

```bash
# 1. Fork and clone
git clone https://github.com/ForestHubAI/boardsmith
cd VibeHard
pip install -e ".[dev]"

# 2. Add your component to the right seed file
# shared/knowledge/seed/sensor.py  (or display.py, comms.py, etc.)

# 3. Verify it loads
boardsmith list-components | grep SHT31

# 4. Quick smoke test
boardsmith build -p "ESP32 with SHT31 humidity sensor" --no-llm --no-pcb

# 5. Run the test suite
pytest

# 6. Open a PR
```

The test suite rebuilds the DB from seed files on every run -- no extra steps needed.

---

## Requesting a Component

Not adding it yourself? Open a **Component Request** issue with the template. Include:
- MPN and manufacturer
- What you want to build with it
- Datasheet link

Good component requests get picked up fast -- this is the most useful issue type.

---

## Development Workflow

```bash
git clone https://github.com/ForestHubAI/boardsmith
cd VibeHard
pip install -e ".[dev]"

# Run all tests (~10 seconds, no API key needed)
pytest

# Run a single module
pytest tests/synthesizer/ -v

# Try a build (no API key)
boardsmith build -p "ESP32 with MPU6050 IMU" --no-llm --no-pcb --seed 42
```

### Project structure

```
synthesizer/          Track B: Prompt -> Schematic + BOM
  synth_core/         9-stage pipeline (B1-B9)
  boardsmith_hw/      KiCad export, PCB pipeline, design improver

compiler/             Track A: Schematic -> Firmware
  boardsmith_fw/           Parser, constraint solver, codegen per target

shared/               Common base -- import from here, not from the above
  agents/             22 agents (IterativeOrchestrator, DesignReviewAgent, ...)
  knowledge/          SQLite FTS5 DB, seed files, schema
  llm/                Provider-agnostic LLM gateway
  models/hir.py       HIR v1.1.0 -- the single source of truth
  plugins/            Plugin system (entry_points-based)
  licensing/          License tier & feature gates
  tools/              Tool registry for agent ReAct loops

boardsmith_enterprise/  Enterprise add-ons (proprietary, separate license)
boardsmith_cli/         CLI entry point (main.py)
tests/                222 tests
```

### The HIR contract

All data flows through `shared/models/hir.py`. If you add a field to a pipeline stage, add it to the HIR first. Never pass raw dicts between modules -- use `HardwareIR` or its sub-models.

```python
from shared.models.hir import HardwareIR, ComponentInstance, BusSpec
```

### Adding a pipeline stage fix

Each stage in `synthesizer/synth_core/` follows the same pattern:

```python
class B3ComponentSelector:
    def run(self, spec: RequirementsSpec, use_llm: bool = True) -> ComponentSelection:
        ...
```

- Always implement a deterministic fallback (used when `use_llm=False`)
- Return a Pydantic model, not a dict
- Add tests in `synthesizer/tests/test_b3_*.py`

---

## Adding Agents

Agents live in `shared/agents/`. They use a ReAct loop from `shared/agents/react_loop.py`.

The minimal agent:

```python
from shared.agents.react_loop import run_react_loop, ReActResult
from shared.llm.gateway import LLMGateway

class MyAgent:
    def __init__(self, gateway: LLMGateway | None = None) -> None:
        self._gateway = gateway

    async def run(self, context: dict) -> MyResult:
        if self._gateway is None:
            return self._deterministic_fallback(context)
        result = await run_react_loop(
            gateway=self._gateway,
            system_prompt=SYSTEM_PROMPT,
            tools=MY_TOOLS,
            initial_message=...,
        )
        return self._parse(result)

    def _deterministic_fallback(self, context: dict) -> MyResult:
        # Must always work without LLM
        ...
```

**Rule:** every agent must work without an LLM. The `--no-llm` mode is not optional.

---

## Code style

```bash
ruff check .        # linting
ruff format .       # formatting (line-length 120)
mypy shared/        # type checking
```

The CI runs all three. PRs that break `ruff` or fail tests won't be merged.

---

## What we don't want

- New dependencies without discussion (keep the install lean)
- Agents that only work with an LLM (must have deterministic fallback)
- Components without a datasheet link
- Breaking changes to HIR v1.1.0 without a migration path

---

## Contributor License Agreement (CLA)

Boardsmith uses a **dual-license model** (AGPL-3.0 + Commercial). To maintain the ability to offer commercial licenses, all contributors must agree to the [CLA](legal/CLA.md) before their first contribution is merged.

**What the CLA does:**
- Assigns copyright of your contributions to the project maintainers
- Grants you a perpetual, irrevocable license back to use your own contributions
- Enables the project to offer commercial licenses alongside AGPL-3.0

**How to sign:** By opening a pull request, you acknowledge that you have read and agree to the [CLA](legal/CLA.md). First-time contributors will be asked to confirm via a comment.

## License

By contributing, you agree that your contributions will be licensed under the [AGPL-3.0 License](LICENSE) and that the [CLA](legal/CLA.md) applies.
