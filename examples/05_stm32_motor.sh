#!/usr/bin/env bash
# Example 5: STM32F4 brushless motor controller with L298N H-bridge
# No API key needed — runs in deterministic mode

boardsmith build \
  --prompt "STM32F4 brushless motor controller with L298N dual H-bridge, PWM speed control, encoder feedback, 12V power input with 3.3V LDO" \
  --target stm32f4 \
  --no-llm \
  --no-pcb \
  --seed 42 \
  --clarification none \
  --out ./output/05_stm32_motor

echo ""
echo "Output: ./output/05_stm32_motor/"
echo "Open schematic.kicad_sch in KiCad to view the design."
