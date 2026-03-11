#!/usr/bin/env bash
# Example 4: RP2040 with SSD1306 OLED display over I2C
# No API key needed — runs in deterministic mode

boardsmith build \
  --prompt "RP2040 with SSD1306 128x64 OLED display over I2C, USB powered, status LED, boot and user buttons" \
  --target rp2040 \
  --no-llm \
  --no-pcb \
  --seed 42 \
  --clarification none \
  --out ./output/04_rp2040_display

echo ""
echo "Output: ./output/04_rp2040_display/"
echo "Open schematic.kicad_sch in KiCad to view the design."
