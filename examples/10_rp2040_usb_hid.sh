#!/usr/bin/env bash
# Example 10: RP2040 USB HID keyboard and gamepad
# No API key needed — runs in deterministic mode

boardsmith build \
  --prompt "RP2040 USB HID keyboard and gamepad with 16 mechanical key switches, 2-axis analog joystick, 6 action buttons, RGB LED per key via SPI shift register, USB-C connector" \
  --target rp2040 \
  --no-llm \
  --no-pcb \
  --seed 42 \
  --clarification none \
  --out ./output/10_rp2040_usb_hid

echo ""
echo "Output: ./output/10_rp2040_usb_hid/"
echo "Open schematic.kicad_sch in KiCad to view the design."
