#!/usr/bin/env bash
# Example 2: RP2040 CO2 monitor with OLED display
# No API key needed — runs in deterministic mode

boardsmith build \
  --prompt "RP2040 CO2 monitor with SCD41 sensor and SSD1306 OLED display, USB powered" \
  --target rp2040 \
  --no-llm \
  --no-pcb \
  --seed 42 \
  --clarification none \
  --out ./output/02_co2_monitor

echo ""
echo "Output: ./output/02_co2_monitor/"
echo "Open schematic.kicad_sch in KiCad to view the design."
