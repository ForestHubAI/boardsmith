# SPDX-License-Identifier: AGPL-3.0-or-later
"""Intent Schema — declarative firmware intent language.

Describes WHAT the firmware should do, not HOW.
The intent compiler translates this into a C application loop.

Example YAML:

    boardsmith_fw_intent: "1.0"
    firmware:
      name: weather_station
      tasks:
        - name: read_env
          every: 5s
          read:
            - component: BME280
              values: [temperature, pressure, humidity]
              store_as: env
        - name: log_to_serial
          trigger: read_env
          actions:
            - serial.print: "T={env.temperature:.1f}C P={env.pressure:.1f}hPa"
        - name: save_to_flash
          trigger: read_env
          every: 60s
          actions:
            - flash.append:
                device: W25Q128JV
                data: env
                format: binary
"""

from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Read actions
# ---------------------------------------------------------------------------

class IntentRead(BaseModel):
    """Read sensor values and store under a name."""
    component: str                          # MPN or component id, e.g. "BME280"
    values: list[str] = Field(default_factory=list)  # ["temperature", "pressure"]
    store_as: str = ""                      # variable name in generated code


# ---------------------------------------------------------------------------
# Generic actions (serial print, flash write, display, etc.)
# ---------------------------------------------------------------------------

class IntentAction(BaseModel):
    """A single firmware action (serial print, flash write, display update)."""
    action: str                             # e.g. "serial.print", "flash.append"
    args: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

class IntentTask(BaseModel):
    """A firmware task — periodic or event-triggered."""
    name: str
    every: Optional[str] = None            # e.g. "5s", "100ms", "1min"
    trigger: Optional[str] = None          # another task name that triggers this
    read: list[IntentRead] = Field(default_factory=list)
    actions: list[Union[str, dict]] = Field(default_factory=list)

    def every_ms(self) -> int:
        """Convert 'every' string to milliseconds."""
        if not self.every:
            return 0
        s = self.every.strip().lower()
        if s.endswith("min"):
            return int(float(s[:-3]) * 60_000)
        if s.endswith("ms"):
            return int(float(s[:-2]))
        if s.endswith("s"):
            return int(float(s[:-1]) * 1_000)
        return int(s)  # bare number treated as ms

    def parsed_actions(self) -> list[IntentAction]:
        """Normalise the heterogeneous action list into IntentAction objects."""
        result = []
        for item in self.actions:
            if isinstance(item, str):
                # "serial.print: msg" or just "serial.print"
                if ":" in item:
                    action, arg = item.split(":", 1)
                    result.append(IntentAction(action=action.strip(), args={"text": arg.strip()}))
                else:
                    result.append(IntentAction(action=item.strip()))
            elif isinstance(item, dict):
                for action, args in item.items():
                    if isinstance(args, dict):
                        result.append(IntentAction(action=action, args=args))
                    else:
                        result.append(IntentAction(action=action, args={"text": str(args)}))
        return result


# ---------------------------------------------------------------------------
# Top-level intent document
# ---------------------------------------------------------------------------

class IntentFirmware(BaseModel):
    """The firmware intent specification."""
    name: str = "firmware"
    tasks: list[IntentTask] = Field(default_factory=list)


class IntentRoot(BaseModel):
    """Root of the intent YAML document."""
    boardsmith_fw_intent: str = "1.0"
    firmware: IntentFirmware
