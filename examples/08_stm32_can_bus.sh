#!/usr/bin/env bash
# Example 8: STM32 CAN bus industrial node
# No API key needed — runs in deterministic mode

boardsmith build \
  --prompt "STM32F4 CAN bus industrial node with MCP2551 CAN transceiver, 120-ohm termination resistor, isolated 24V input power with DC-DC converter to 3.3V, status LEDs, RS-485 UART" \
  --target stm32f4 \
  --no-llm \
  --no-pcb \
  --seed 42 \
  --clarification none \
  --out ./output/08_stm32_can_bus

echo ""
echo "Output: ./output/08_stm32_can_bus/"
echo "Open schematic.kicad_sch in KiCad to view the design."
