# SPDX-License-Identifier: AGPL-3.0-or-later
"""Multi-Board Topology models.

Describes a system of multiple boards (nodes) connected via
communication links, with typed message schemas flowing between them.

    topology.yaml → TopologyRoot → codegen for each node
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MessageField(BaseModel):
    """A single field in a message definition."""

    name: str
    type: str = "float"  # float, int32, uint8, bool, char[N]


class MessageDef(BaseModel):
    """A message that flows between nodes."""

    name: str
    fields: list[MessageField] = Field(default_factory=list)


class CommLink(BaseModel):
    """A communication link between two nodes."""

    source: str  # node id
    target: str  # node id
    protocol: str  # "uart", "spi", "i2c", "esp_now", "ble", "mqtt"
    baud_rate: int = 115200
    topic: str = ""  # for MQTT
    config: dict[str, str] = Field(default_factory=dict)
    messages: list[str] = Field(default_factory=list)  # message names


class BoardNode(BaseModel):
    """A single board/MCU in the topology."""

    id: str
    name: str = ""
    mcu: str = ""  # e.g., "ESP32-WROOM-32", "ESP32-C3", "STM32F4"
    family: str = "esp32"  # esp32, stm32, rp2040
    role: str = "sensor"  # gateway, sensor, actuator


class TopologyRoot(BaseModel):
    """Root model for a multi-board topology definition."""

    boardsmith_fw_topology: str = "1.0"
    system_name: str = ""
    nodes: list[BoardNode] = Field(default_factory=list)
    messages: list[MessageDef] = Field(default_factory=list)
    links: list[CommLink] = Field(default_factory=list)

    def get_node(self, node_id: str) -> BoardNode | None:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def get_links_for_node(self, node_id: str) -> list[CommLink]:
        return [lk for lk in self.links if lk.source == node_id or lk.target == node_id]

    def get_message(self, name: str) -> MessageDef | None:
        for m in self.messages:
            if m.name == name:
                return m
        return None

    def get_outgoing_links(self, node_id: str) -> list[CommLink]:
        return [lk for lk in self.links if lk.source == node_id]

    def get_incoming_links(self, node_id: str) -> list[CommLink]:
        return [lk for lk in self.links if lk.target == node_id]
