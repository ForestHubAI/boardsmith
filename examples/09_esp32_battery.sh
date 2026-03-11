#!/usr/bin/env bash
# Example 9: ESP32 battery-powered IoT node with LiPo charger
# No API key needed — runs in deterministic mode

boardsmith build \
  --prompt "ESP32 battery-powered IoT node with TP4056 LiPo charger, battery voltage monitor via ADC, deep sleep mode, soil moisture sensor over ADC, USB-C charging port" \
  --target esp32 \
  --no-llm \
  --no-pcb \
  --seed 42 \
  --clarification none \
  --out ./output/09_esp32_battery

echo ""
echo "Output: ./output/09_esp32_battery/"
echo "Open schematic.kicad_sch in KiCad to view the design."
