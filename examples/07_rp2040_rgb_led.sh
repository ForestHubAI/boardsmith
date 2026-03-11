#!/usr/bin/env bash
# Example 7: RP2040 with WS2812B addressable RGB LEDs
# No API key needed — runs in deterministic mode

boardsmith build \
  --prompt "RP2040 controlling 60 WS2812B addressable RGB LEDs on a single data line with level shifter, USB powered, 5V 3A power supply, decoupling capacitors per LED strip section" \
  --target rp2040 \
  --no-llm \
  --no-pcb \
  --seed 42 \
  --clarification none \
  --out ./output/07_rp2040_rgb_led

echo ""
echo "Output: ./output/07_rp2040_rgb_led/"
echo "Open schematic.kicad_sch in KiCad to view the design."
