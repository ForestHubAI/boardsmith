#!/usr/bin/env bash
# Example 3: ESP32 LoRa sensor node (battery powered)
# No API key needed — runs in deterministic mode

boardsmith build \
  --prompt "ESP32 LoRa sensor node with SX1276 on SPI, BME280 over I2C, 3.7V LiPo battery" \
  --target esp32 \
  --no-llm \
  --no-pcb \
  --seed 42 \
  --clarification none \
  --out ./output/03_lora_node

echo ""
echo "Output: ./output/03_lora_node/"
echo "Open schematic.kicad_sch in KiCad to view the design."
