#!/usr/bin/env bash
# Example 1: ESP32 Temperature + Humidity sensor
# No API key needed — runs in deterministic mode

boardsmith build \
  --prompt "ESP32 with BME280 temperature and humidity sensor over I2C, 3.3V power from USB" \
  --target esp32 \
  --no-llm \
  --no-pcb \
  --seed 42 \
  --clarification none \
  --out ./output/01_temp_sensor

echo ""
echo "Output: ./output/01_temp_sensor/"
echo "Open schematic.kicad_sch in KiCad to view the design."
