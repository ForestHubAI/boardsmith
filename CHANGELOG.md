# Changelog

All notable changes to Boardsmith will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] — 2026-03-10

### Added

- **ERCAgent** (`synthesizer/boardsmith_hw/agent/erc_agent.py`) — LLM-guided ERC repair loop.
  Bounded to 5 iterations with stall detection (sorted-violation-hash). Integrated into
  `boardsmith build` and `boardsmith build-project` via `--max-erc-iterations`.
- **`boardsmith modify`** — Brownfield schematic patching. LLM generates ADD/MODIFY patch,
  user confirms (or `--yes` for non-interactive), ERCAgent validates post-patch.
  Backs up schematic as `.bak` before every write.
- **`boardsmith verify`** — Semantic verification of design intent against HIR. Runs
  SemanticVerificationAgent: connectivity, bootability, power, components, BOM, PCB basic.
- **WriteSchematicPatchTool** — ADD/MODIFY only (no DELETE without `--allow-delete`).
  UUID generation, `.bak` backup before every write.
- **SemanticVerificationAgent** (`boardsmith_hw/agent/semantic_agent.py`) — 6 verification
  tools wired into B8.3/B8.4 stages: connectivity, bootability, power, components, BOM, PCB.
- **6 semantic verification tools**: VerifyConnectivityTool, VerifyBootabilityTool,
  VerifyPowerTool, VerifyComponentsTool, VerifyBomTool, VerifyPcbBasicTool.
- **EDA Tool Layer** (Phase 6): RunERCTool, ReadSchematicTool, SearchComponentTool — all
  import-clean with `BOARDSMITH_NO_LLM=1`.
- **`complete_with_tools()`** in `AnthropicProvider` — Anthropic tool-use alongside existing
  `complete()`. ToolDispatcher for agent ReAct loops.
- **`--max-erc-iterations`** flag on `boardsmith build` and `boardsmith build-project`.

### Changed

- ERCAgent loop integrated into `boardsmith build` and `boardsmith build-project` pipelines
  (B8.2 stage). ERC repair runs automatically after schematic generation when LLM is
  available.
- SemanticVerificationAgent integrated into pipeline at B8.3 (tools) and B8.4 (agent loop).
- `boardsmith_hw/agent/` module is isolated — fully import-clean with `BOARDSMITH_NO_LLM=1`.

### Notes

- OpenAI tool-use support deferred to v0.3. Only Anthropic provider supports tool-use in v0.2.
- HIR-out-of-sync after `boardsmith modify` is a documented v0.3 gap; user warning displayed.
- `boardsmith verify` requires LLM (`pip install boardsmith[llm]`); no `--no-llm` fallback.

## [0.1.0] — 2026-03-08

### Added

- **9-stage synthesis pipeline** — Prompt → Intent → Components → Topology → Electrical → Schematic → PCB → Firmware → Confidence. Each stage is independently testable and pluggable.
- **212 verified components** — sensors (BME280, SCD41, MPU-6050), displays (SSD1306, ST7789), communications (SX1276 LoRa, W5500 Ethernet, MCP2515 CAN-FD), MCUs, power ICs, and industrial-grade parts. Each with datasheet-sourced electrical specs, timing constraints, I2C addresses, and LCSC part numbers.
- **191 LCSC part mappings** with 100% coverage for JLCPCB SMT assembly.
- **Multi-target MCU support** — ESP32 (ESP-IDF + Arduino), RP2040 (Pico SDK), STM32 (HAL, F4/F7/G4/H7/L4), nRF52840, LPC55, i.MX RT. 21 firmware adapters across 4 SDKs including Zephyr.
- **KiCad schematic export** — wired schematics with computed pull-up resistors, decoupling caps, crystal load caps, level shifters, boot/reset circuits, and debug headers. Not templates — all values are calculated from datasheet specs.
- **PCB layout pipeline** — FreeRouting integration, GND plane + stitching vias, decoupling cap placement (1.5mm from VDD pin), net classes (Signal/Power/HighCurrent), silkscreen, and post-routing DRC.
- **Gerber export** — JLCPCB-compatible manufacturing package (copper, drill, outline, assembly files).
- **JLCPCB BOM export** — grouped by MPN + footprint, upload-ready for SMT assembly.
- **19 CLI commands** — build, compile, research, list-components, drc, bom, firmware, and more.
- **Offline mode** (`--no-llm`) — full deterministic pipeline using the built-in knowledge base. No API key, no network.
- **LLM mode** (`pip install boardsmith[llm]`) — iterative refinement via Anthropic Claude or OpenAI GPT. The LLM handles intent; the pipeline enforces physics.
- **10 industrial design patterns** — 24V input protection, USB device, RS-485 node, CAN-FD, isolated CAN, I2C external, SPI external, Ethernet, battery management, and motor driver.
- **EDA quality layer** — 57 component profiles with Pydantic-typed footprint/symbol/3D metadata; EdaBinding TypedDict for component-to-KiCad mapping.
- **Manufacturing-ready validation** — 11 constraint checks (voltage compatibility, I2C address conflicts, pin assignment, power budget, timing, decoupling, pull-up values, bus width, clock domains, current limits, ERC) + kicad-cli DRC with 3 waived synthetic-footprint rules.
- **Orchestrator with 9 quality gates** — erc_clean, drc_clean, boot_pins_valid, clock_valid, power_valid, bom_complete, firmware_valid, gerber_valid, release_ready. Selective re-entry on failure.
- **SQLite component database** — normalized schema, FTS5 full-text search, range query API, draft-state agent auto-promote (confidence ≥ 0.75).
- **Knowledge Agent** — web search, Octopart integration, auto-insert for verified components.
- **LLM Gateway** — Anthropic, OpenAI, Ollama with cost tracking and retry.
- **Dual-license structure** — AGPL-3.0 for open source, commercial license for closed-source integration.
- **SPDX license headers** on all source files.
- **Plugin system** (`shared/plugins/`) with entry_points-based discovery for community extensions.
- **1,838 passing tests** across 69 test files. 60/60 ERC-clean validated designs.

### Changed

- LLM SDKs (`anthropic`, `openai`) moved to optional `[llm]` extra — `pip install boardsmith` installs without API dependencies.
- Version string now reads from `importlib.metadata` — bumping `pyproject.toml` is the single source of truth.
- All CLI output is English.

---

[Unreleased]: https://github.com/marcusrub/VibeHard/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/marcusrub/VibeHard/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/marcusrub/VibeHard/releases/tag/v0.1.0
