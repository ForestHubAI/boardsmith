#!/usr/bin/env bash
# Example 6: ESP32 WiFi weather station with BME680
# No API key needed — runs in deterministic mode

boardsmith build \
  --prompt "ESP32 WiFi weather station with BME680 environmental sensor over I2C, measuring temperature, humidity, pressure, and air quality, USB powered with UART debug port" \
  --target esp32 \
  --no-llm \
  --no-pcb \
  --seed 42 \
  --clarification none \
  --out ./output/06_esp32_wifi_sensor

echo ""
echo "Output: ./output/06_esp32_wifi_sensor/"
echo "Open schematic.kicad_sch in KiCad to view the design."
