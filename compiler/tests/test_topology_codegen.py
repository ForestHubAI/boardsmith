# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for Phase 6.3 — Multi-Board Topology."""

from pathlib import Path

from boardsmith_fw.codegen.topology_codegen import (
    TopologyCodegenResult,
    generate_topology,
    parse_topology,
    parse_topology_file,
)
from boardsmith_fw.models.topology import (
    BoardNode,
    CommLink,
    MessageDef,
    MessageField,
    TopologyRoot,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "topology_gateway_sensor"

SIMPLE_TOPOLOGY = """\
boardsmith_fw_topology: "1.0"
system_name: "Test Network"
nodes:
  - id: gw
    name: Gateway
    family: esp32
    role: gateway
  - id: s1
    name: Sensor
    family: esp32
    role: sensor
messages:
  - name: temp_reading
    fields:
      - { name: temperature, type: float }
      - { name: humidity, type: float }
links:
  - source: s1
    target: gw
    protocol: uart
    baud_rate: 9600
    messages: [temp_reading]
"""


# -----------------------------------------------------------------------
# Model tests
# -----------------------------------------------------------------------


class TestTopologyModel:
    def test_parse_simple(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        assert topo.system_name == "Test Network"
        assert len(topo.nodes) == 2
        assert len(topo.messages) == 1
        assert len(topo.links) == 1

    def test_get_node(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        gw = topo.get_node("gw")
        assert gw is not None
        assert gw.role == "gateway"
        assert topo.get_node("nonexistent") is None

    def test_get_links_for_node(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        gw_links = topo.get_links_for_node("gw")
        assert len(gw_links) == 1
        s1_links = topo.get_links_for_node("s1")
        assert len(s1_links) == 1

    def test_get_outgoing_incoming(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        # s1 sends temp_reading to gw
        assert len(topo.get_outgoing_links("s1")) == 1
        assert len(topo.get_incoming_links("s1")) == 0
        assert len(topo.get_outgoing_links("gw")) == 0
        assert len(topo.get_incoming_links("gw")) == 1

    def test_get_message(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        msg = topo.get_message("temp_reading")
        assert msg is not None
        assert len(msg.fields) == 2
        assert topo.get_message("unknown") is None

    def test_message_field_types(self):
        msg = MessageDef(
            name="test",
            fields=[
                MessageField(name="a", type="float"),
                MessageField(name="b", type="uint8"),
            ],
        )
        assert msg.fields[0].type == "float"
        assert msg.fields[1].type == "uint8"

    def test_board_node_defaults(self):
        node = BoardNode(id="n1")
        assert node.family == "esp32"
        assert node.role == "sensor"

    def test_comm_link_defaults(self):
        link = CommLink(source="a", target="b", protocol="uart")
        assert link.baud_rate == 115200
        assert link.messages == []


# -----------------------------------------------------------------------
# Messages header
# -----------------------------------------------------------------------


class TestMessagesHeader:
    def test_generates_messages_header(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        r = generate_topology(topo)
        names = [f[0] for f in r.files]
        assert "shared/messages.h" in names

    def test_packed_struct(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        r = generate_topology(topo)
        header = dict(r.files)["shared/messages.h"]
        assert "typedef struct" in header
        assert "__attribute__((packed))" in header
        assert "temp_reading_t" in header

    def test_field_types_in_struct(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        r = generate_topology(topo)
        header = dict(r.files)["shared/messages.h"]
        assert "float temperature;" in header
        assert "float humidity;" in header

    def test_include_guard(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        r = generate_topology(topo)
        header = dict(r.files)["shared/messages.h"]
        assert "#ifndef TOPOLOGY_MESSAGES_H" in header
        assert "#endif" in header


# -----------------------------------------------------------------------
# Per-node code (ESP32 UART)
# -----------------------------------------------------------------------


class TestEsp32UartNode:
    def test_generates_node_files(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        r = generate_topology(topo)
        names = [f[0] for f in r.files]
        assert "gw/comm.h" in names
        assert "gw/comm.c" in names
        assert "s1/comm.h" in names
        assert "s1/comm.c" in names

    def test_sender_has_send_function(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        r = generate_topology(topo)
        s1_h = dict(r.files)["s1/comm.h"]
        assert "comm_send_temp_reading" in s1_h
        # sender should NOT have recv callback
        assert "comm_on_temp_reading" not in s1_h

    def test_receiver_has_callback(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        r = generate_topology(topo)
        gw_h = dict(r.files)["gw/comm.h"]
        assert "comm_on_temp_reading" in gw_h
        # receiver should NOT have send function for this message
        assert "comm_send_temp_reading" not in gw_h

    def test_sender_impl_uart_write(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        r = generate_topology(topo)
        s1_c = dict(r.files)["s1/comm.c"]
        assert "uart_write_bytes" in s1_c
        assert "temp_reading_t" in s1_c

    def test_receiver_impl_weak_callback(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        r = generate_topology(topo)
        gw_c = dict(r.files)["gw/comm.c"]
        assert "__attribute__((weak))" in gw_c
        assert "comm_on_temp_reading" in gw_c

    def test_comm_init_uart_setup(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        r = generate_topology(topo)
        s1_c = dict(r.files)["s1/comm.c"]
        assert "uart_param_config" in s1_c
        assert "uart_driver_install" in s1_c
        assert "9600" in s1_c

    def test_comm_init_in_header(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        r = generate_topology(topo)
        s1_h = dict(r.files)["s1/comm.h"]
        assert "void comm_init(void)" in s1_h

    def test_include_guard_per_node(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        r = generate_topology(topo)
        gw_h = dict(r.files)["gw/comm.h"]
        assert "#ifndef COMM_GW_H" in gw_h
        s1_h = dict(r.files)["s1/comm.h"]
        assert "#ifndef COMM_S1_H" in s1_h


# -----------------------------------------------------------------------
# ESP-NOW protocol
# -----------------------------------------------------------------------


ESP_NOW_TOPOLOGY = """\
boardsmith_fw_topology: "1.0"
system_name: "ESP-NOW Test"
nodes:
  - { id: sender, family: esp32, role: sensor }
  - { id: receiver, family: esp32, role: gateway }
messages:
  - name: measurement
    fields: [{ name: value, type: float }]
links:
  - source: sender
    target: receiver
    protocol: esp_now
    messages: [measurement]
"""


class TestEspNow:
    def test_esp_now_send(self):
        topo = parse_topology(ESP_NOW_TOPOLOGY)
        r = generate_topology(topo)
        impl = dict(r.files)["sender/comm.c"]
        assert "esp_now_send" in impl
        assert "broadcast" in impl

    def test_esp_now_include(self):
        topo = parse_topology(ESP_NOW_TOPOLOGY)
        r = generate_topology(topo)
        impl = dict(r.files)["sender/comm.c"]
        assert "esp_now.h" in impl

    def test_esp_now_init(self):
        topo = parse_topology(ESP_NOW_TOPOLOGY)
        r = generate_topology(topo)
        impl = dict(r.files)["sender/comm.c"]
        assert "esp_now_init" in impl


# -----------------------------------------------------------------------
# MQTT protocol
# -----------------------------------------------------------------------


MQTT_TOPOLOGY = """\
boardsmith_fw_topology: "1.0"
system_name: "MQTT Test"
nodes:
  - { id: pub, family: esp32, role: gateway }
  - { id: sub, family: esp32, role: sensor }
messages:
  - name: status
    fields: [{ name: code, type: uint8 }]
links:
  - source: pub
    target: sub
    protocol: mqtt
    topic: "devices/status"
    messages: [status]
"""


class TestMqtt:
    def test_mqtt_publish(self):
        topo = parse_topology(MQTT_TOPOLOGY)
        r = generate_topology(topo)
        impl = dict(r.files)["pub/comm.c"]
        assert "mqtt_publish" in impl
        assert "devices/status" in impl

    def test_mqtt_init_comment(self):
        topo = parse_topology(MQTT_TOPOLOGY)
        r = generate_topology(topo)
        impl = dict(r.files)["pub/comm.c"]
        assert "MQTT" in impl


# -----------------------------------------------------------------------
# STM32 node
# -----------------------------------------------------------------------


STM32_TOPOLOGY = """\
boardsmith_fw_topology: "1.0"
system_name: "STM32 Node"
nodes:
  - { id: gw, family: esp32, role: gateway }
  - { id: ctrl, family: stm32, role: actuator }
messages:
  - name: command
    fields: [{ name: action, type: uint8 }]
links:
  - source: gw
    target: ctrl
    protocol: uart
    baud_rate: 115200
    messages: [command]
"""


class TestStm32Node:
    def test_stm32_recv_impl(self):
        topo = parse_topology(STM32_TOPOLOGY)
        r = generate_topology(topo)
        ctrl_c = dict(r.files)["ctrl/comm.c"]
        assert "stm32f4xx_hal.h" in ctrl_c

    def test_stm32_comm_init(self):
        topo = parse_topology(STM32_TOPOLOGY)
        r = generate_topology(topo)
        ctrl_c = dict(r.files)["ctrl/comm.c"]
        assert "comm_init" in ctrl_c
        assert "CubeMX" in ctrl_c  # UART configured by CubeMX


# -----------------------------------------------------------------------
# RP2040 node
# -----------------------------------------------------------------------


RP2040_TOPOLOGY = """\
boardsmith_fw_topology: "1.0"
system_name: "RP2040 Node"
nodes:
  - { id: pico, family: rp2040, role: sensor }
  - { id: hub, family: esp32, role: gateway }
messages:
  - name: data_pkt
    fields: [{ name: val, type: float }]
links:
  - source: pico
    target: hub
    protocol: uart
    baud_rate: 57600
    messages: [data_pkt]
"""


class TestRp2040Node:
    def test_rp2040_uart_write(self):
        topo = parse_topology(RP2040_TOPOLOGY)
        r = generate_topology(topo)
        impl = dict(r.files)["pico/comm.c"]
        assert "uart_write_blocking" in impl

    def test_rp2040_uart_init(self):
        topo = parse_topology(RP2040_TOPOLOGY)
        r = generate_topology(topo)
        impl = dict(r.files)["pico/comm.c"]
        assert "uart_init" in impl
        assert "57600" in impl

    def test_rp2040_includes(self):
        topo = parse_topology(RP2040_TOPOLOGY)
        r = generate_topology(topo)
        impl = dict(r.files)["pico/comm.c"]
        assert "pico/stdlib.h" in impl
        assert "hardware/uart.h" in impl


# -----------------------------------------------------------------------
# Fixture file integration
# -----------------------------------------------------------------------


class TestFixtureIntegration:
    def test_parse_fixture(self):
        topo = parse_topology_file(FIXTURES / "topology.yaml")
        assert topo.system_name == "Sensor Gateway Network"
        assert len(topo.nodes) == 3
        assert len(topo.messages) == 2
        assert len(topo.links) == 2

    def test_fixture_gateway_has_esp_now_recv(self):
        topo = parse_topology_file(FIXTURES / "topology.yaml")
        r = generate_topology(topo)
        gw_h = dict(r.files)["gateway/comm.h"]
        assert "comm_on_sensor_data" in gw_h

    def test_fixture_gateway_has_uart_send(self):
        topo = parse_topology_file(FIXTURES / "topology.yaml")
        r = generate_topology(topo)
        gw_h = dict(r.files)["gateway/comm.h"]
        assert "comm_send_actuator_cmd" in gw_h

    def test_fixture_sensor_has_esp_now_send(self):
        topo = parse_topology_file(FIXTURES / "topology.yaml")
        r = generate_topology(topo)
        s1_c = dict(r.files)["sensor_1/comm.c"]
        assert "esp_now_send" in s1_c

    def test_fixture_actuator_is_stm32(self):
        topo = parse_topology_file(FIXTURES / "topology.yaml")
        r = generate_topology(topo)
        act_c = dict(r.files)["actuator_1/comm.c"]
        assert "stm32f4xx_hal.h" in act_c

    def test_fixture_messages_header(self):
        topo = parse_topology_file(FIXTURES / "topology.yaml")
        r = generate_topology(topo)
        header = dict(r.files)["shared/messages.h"]
        assert "sensor_data_t" in header
        assert "actuator_cmd_t" in header
        assert "float temperature;" in header
        assert "uint8_t relay_id;" in header
        assert "bool state;" in header

    def test_fixture_file_count(self):
        topo = parse_topology_file(FIXTURES / "topology.yaml")
        r = generate_topology(topo)
        # 1 messages header + 3 nodes * 2 (h+c) + 1 summary = 8
        assert len(r.files) == 8


# -----------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------


class TestTopologySummary:
    def test_summary_contains_nodes(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        r = generate_topology(topo)
        md = dict(r.files)["topology_summary.md"]
        assert "gw" in md
        assert "s1" in md
        assert "gateway" in md
        assert "sensor" in md

    def test_summary_contains_messages(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        r = generate_topology(topo)
        md = dict(r.files)["topology_summary.md"]
        assert "temp_reading" in md
        assert "temperature" in md

    def test_summary_contains_links(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        r = generate_topology(topo)
        md = dict(r.files)["topology_summary.md"]
        assert "uart" in md


# -----------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_topology(self):
        topo = TopologyRoot()
        r = generate_topology(topo)
        assert len(r.warnings) > 0
        assert "No nodes" in r.warnings[0]

    def test_no_messages(self):
        topo = TopologyRoot(
            nodes=[BoardNode(id="n1")],
            messages=[],
            links=[],
        )
        r = generate_topology(topo)
        names = [f[0] for f in r.files]
        # No messages header generated
        assert "shared/messages.h" not in names

    def test_result_type(self):
        topo = parse_topology(SIMPLE_TOPOLOGY)
        r = generate_topology(topo)
        assert isinstance(r, TopologyCodegenResult)
