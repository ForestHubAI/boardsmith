# SPDX-License-Identifier: AGPL-3.0-or-later
"""Communication modules — GNSS, LoRa, 2.4GHz, Ethernet, CAN."""

from __future__ import annotations

from boardsmith_fw.models.component_knowledge import (
    ComponentKnowledge,
    InitStep,
    InterfaceType,
    RegisterField,
    RegisterInfo,
    TimingConstraint,
)


def _neo_m8n() -> ComponentKnowledge:
    """u-blox NEO-M8N — GNSS receiver module (UART/I2C/SPI)."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="NEO-M8N",
        manufacturer="u-blox",
        mpn="NEO-M8N",
        description="u-blox M8 concurrent GNSS module (GPS, GLONASS, BeiDou, Galileo)",
        category="gnss_receiver",
        interface=InterfaceType.UART,
        registers=[],  # UBX protocol, not register-based
        init_sequence=[
            InitStep(order=1, reg_addr="", value="", description="Wait for module startup", delay_ms=1000),
            InitStep(
                order=2, reg_addr="", value="UBX-CFG-PRT",
                description="Configure UART port: 9600 baud, UBX+NMEA protocol",
            ),
            InitStep(
                order=3, reg_addr="", value="UBX-CFG-MSG",
                description="Enable GGA, RMC, GSV messages at 1Hz",
            ),
            InitStep(
                order=4, reg_addr="", value="UBX-CFG-RATE",
                description="Set measurement rate to 1000ms (1Hz)",
            ),
        ],
        timing_constraints=[
            TimingConstraint(parameter="Cold start TTFF", typical="26", unit="s"),
            TimingConstraint(parameter="Hot start TTFF", typical="1", unit="s"),
            TimingConstraint(parameter="Navigation update rate", max="10", unit="Hz"),
            TimingConstraint(parameter="UART baud rate (default)", typical="9600", unit="baud"),
        ],
        notes=[
            "Default UART baud rate: 9600, can be changed via UBX-CFG-PRT",
            "NMEA 0183 output by default (GGA, GLL, GSA, GSV, RMC, VTG)",
            "UBX binary protocol for configuration and high-precision output",
            "Backup battery on V_BCKP pin enables hot start",
        ],
    )


def _sx1276() -> ComponentKnowledge:
    """Semtech SX1276 — Long-range LoRa transceiver (SPI)."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="SX1276",
        manufacturer="Semtech",
        mpn="SX1276",
        description="137-1020MHz long range LoRa/FSK transceiver",
        category="rf_transceiver",
        interface=InterfaceType.SPI,
        spi_mode=0,
        registers=[
            RegisterInfo(address="0x01", name="RegOpMode", description="Operating mode and modulation",
                         fields=[
                             RegisterField(name="LongRangeMode", bits="7", description="0=FSK/OOK, 1=LoRa"),
                             RegisterField(name="Mode", bits="2:0", description="0=sleep 1=stby 2=FSTX 3=TX 5=RX"),
                         ]),
            RegisterInfo(address="0x06", name="RegFrfMsb", description="Carrier frequency MSB"),
            RegisterInfo(address="0x07", name="RegFrfMid", description="Carrier frequency MID"),
            RegisterInfo(address="0x08", name="RegFrfLsb", description="Carrier frequency LSB"),
            RegisterInfo(address="0x09", name="RegPaConfig", description="PA output power config"),
            RegisterInfo(address="0x0D", name="RegFifoAddrPtr", description="FIFO SPI pointer"),
            RegisterInfo(address="0x0E", name="RegFifoTxBaseAddr", description="TX FIFO base address"),
            RegisterInfo(address="0x0F", name="RegFifoRxBaseAddr", description="RX FIFO base address"),
            RegisterInfo(address="0x12", name="RegIrqFlags", description="IRQ flags (write 0xFF to clear)"),
            RegisterInfo(address="0x13", name="RegRxNbBytes", description="Number of received bytes"),
            RegisterInfo(address="0x1D", name="RegModemConfig1", description="BW, coding rate, header mode"),
            RegisterInfo(address="0x1E", name="RegModemConfig2", description="SF, CRC, RX timeout MSB",
                         fields=[
                             RegisterField(name="SpreadingFactor", bits="7:4", description="SF7-SF12"),
                         ]),
            RegisterInfo(address="0x26", name="RegModemConfig3", description="Low data rate optimize, AGC auto"),
            RegisterInfo(address="0x00", name="RegFifo", description="FIFO read/write access"),
            RegisterInfo(address="0x42", name="RegVersion", description="Silicon revision, returns 0x12"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x01", value="0x80", description="Sleep mode, LoRa mode"),
            InitStep(order=2, reg_addr="0x06", value="0x6C", description="Set frequency 434MHz MSB"),
            InitStep(order=3, reg_addr="0x07", value="0x80", description="Set frequency 434MHz MID"),
            InitStep(order=4, reg_addr="0x08", value="0x00", description="Set frequency 434MHz LSB"),
            InitStep(order=5, reg_addr="0x09", value="0x8F", description="PA config: PA_BOOST, +17dBm"),
            InitStep(order=6, reg_addr="0x1D", value="0x72", description="BW 125kHz, CR 4/5, explicit header"),
            InitStep(order=7, reg_addr="0x1E", value="0x74", description="SF7, CRC on"),
            InitStep(order=8, reg_addr="0x26", value="0x04", description="AGC auto on"),
            InitStep(order=9, reg_addr="0x0E", value="0x00", description="TX base address 0"),
            InitStep(order=10, reg_addr="0x0F", value="0x00", description="RX base address 0"),
            InitStep(order=11, reg_addr="0x01", value="0x81", description="Standby mode"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="SPI clock frequency", max="10000000", unit="Hz"),
            TimingConstraint(parameter="TX power-up time", max="1.5", unit="ms"),
            TimingConstraint(parameter="Supply current (TX +17dBm)", typical="120", unit="mA"),
            TimingConstraint(parameter="Supply current (RX)", typical="10.3", unit="mA"),
        ],
        notes=[
            "Frequency: Frf = RegFrf * 32MHz / 2^19",
            "FIFO: 256 bytes shared between TX and RX",
            "DIO0 pin: TX Done (TX mode) or RX Done (RX mode) interrupt",
            "RFM95W/RFM96W modules use SX1276 internally",
        ],
    )


def _nrf24l01() -> ComponentKnowledge:
    """Nordic Semiconductor nRF24L01+ — 2.4GHz RF transceiver (SPI)."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="NRF24L01",
        manufacturer="Nordic Semiconductor",
        mpn="nRF24L01+",
        description="2.4GHz ISM band transceiver with Enhanced ShockBurst",
        category="rf_transceiver",
        interface=InterfaceType.SPI,
        spi_mode=0,
        registers=[
            RegisterInfo(address="0x00", name="CONFIG", description="Configuration register",
                         fields=[
                             RegisterField(name="MASK_RX_DR", bits="6", description="Mask RX_DR interrupt"),
                             RegisterField(name="MASK_TX_DS", bits="5", description="Mask TX_DS interrupt"),
                             RegisterField(name="EN_CRC", bits="3", description="Enable CRC"),
                             RegisterField(name="CRCO", bits="2", description="CRC encoding scheme (0=1byte, 1=2byte)"),
                             RegisterField(name="PWR_UP", bits="1", description="Power up"),
                             RegisterField(name="PRIM_RX", bits="0", description="RX/TX control (1=PRX, 0=PTX)"),
                         ]),
            RegisterInfo(address="0x01", name="EN_AA", description="Enable auto-acknowledgement"),
            RegisterInfo(address="0x02", name="EN_RXADDR", description="Enable RX addresses"),
            RegisterInfo(address="0x03", name="SETUP_AW", description="Address width (3-5 bytes)"),
            RegisterInfo(address="0x04", name="SETUP_RETR", description="Auto-retransmit delay and count"),
            RegisterInfo(address="0x05", name="RF_CH", description="RF channel (0-125)"),
            RegisterInfo(address="0x06", name="RF_SETUP", description="RF setup: data rate, TX power",
                         fields=[
                             RegisterField(name="RF_DR_HIGH", bits="3", description="Data rate high bit"),
                             RegisterField(name="RF_PWR", bits="2:1", description="TX power (0=-18dBm, 3=0dBm)"),
                         ]),
            RegisterInfo(address="0x07", name="STATUS", description="Status register (IRQ flags, TX/RX FIFO)"),
            RegisterInfo(address="0x0A", name="RX_ADDR_P0", description="Receive address pipe 0 (5 bytes)"),
            RegisterInfo(address="0x10", name="TX_ADDR", description="Transmit address (5 bytes)"),
            RegisterInfo(address="0x11", name="RX_PW_P0", description="RX payload width pipe 0 (1-32)"),
            RegisterInfo(address="0x17", name="FIFO_STATUS", description="FIFO status (TX/RX full/empty)"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x00", value="0x0E", description="Power up, CRC 2-byte, PTX"),
            InitStep(order=2, reg_addr="", value="", description="Wait for power-up", delay_ms=2),
            InitStep(order=3, reg_addr="0x05", value="0x4C", description="RF channel 76 (2476MHz)"),
            InitStep(order=4, reg_addr="0x06", value="0x06", description="1Mbps, 0dBm TX power"),
            InitStep(order=5, reg_addr="0x03", value="0x03", description="5-byte address width"),
            InitStep(order=6, reg_addr="0x04", value="0x3F", description="1000us retry delay, 15 retries"),
            InitStep(order=7, reg_addr="0x01", value="0x3F", description="Enable auto-ack all pipes"),
            InitStep(order=8, reg_addr="0x02", value="0x03", description="Enable RX pipe 0 and 1"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="SPI clock frequency", max="10000000", unit="Hz"),
            TimingConstraint(parameter="Power-on-reset time", max="100", unit="ms"),
            TimingConstraint(parameter="Standby to TX/RX", max="130", unit="us"),
            TimingConstraint(parameter="Supply current (TX 0dBm)", typical="11.3", unit="mA"),
            TimingConstraint(parameter="Supply current (RX)", typical="13.5", unit="mA"),
        ],
        notes=[
            "SPI with additional CE (Chip Enable) and IRQ pins",
            "Payload: 1-32 bytes per packet",
            "Enhanced ShockBurst: auto-ack and auto-retransmit",
            "250kbps, 1Mbps, or 2Mbps data rates",
            "126 channels (2400-2525 MHz)",
        ],
    )


def _enc28j60() -> ComponentKnowledge:
    """Microchip ENC28J60 — Ethernet controller (SPI)."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="ENC28J60",
        manufacturer="Microchip",
        mpn="ENC28J60",
        description="10Base-T Ethernet controller with SPI interface",
        category="ethernet",
        interface=InterfaceType.SPI,
        spi_mode=0,
        registers=[
            RegisterInfo(address="0x00", name="ERDPTL", description="Read pointer low byte"),
            RegisterInfo(address="0x01", name="ERDPTH", description="Read pointer high byte"),
            RegisterInfo(address="0x02", name="EWRPTL", description="Write pointer low byte"),
            RegisterInfo(address="0x04", name="ETXSTL", description="TX start low byte"),
            RegisterInfo(address="0x06", name="ETXNDL", description="TX end low byte"),
            RegisterInfo(address="0x08", name="ERXSTL", description="RX start low byte"),
            RegisterInfo(address="0x0A", name="ERXNDL", description="RX end low byte"),
            RegisterInfo(address="0x19", name="ECON1", description="Ethernet control 1 (bank select, TX/RX enable)"),
            RegisterInfo(address="0x1E", name="ECON2", description="Ethernet control 2"),
            RegisterInfo(address="0x1B", name="EREVID", description="Ethernet revision ID"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x1F", value="0x80", description="System reset via SPI command"),
            InitStep(order=2, reg_addr="", value="", description="Wait for oscillator", delay_ms=1),
            InitStep(order=3, reg_addr="0x08", value="0x00", description="RX buffer start 0x0000"),
            InitStep(order=4, reg_addr="0x0A", value="0xFF,0x1F", description="RX buffer end 0x1FFF"),
            InitStep(order=5, reg_addr="0x04", value="0x00,0x20", description="TX buffer start 0x2000"),
            InitStep(order=6, reg_addr="0x19", value="0x04", description="Enable RX"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="SPI clock frequency", max="20000000", unit="Hz"),
            TimingConstraint(parameter="Oscillator startup", max="300", unit="us"),
            TimingConstraint(parameter="Supply current", typical="170", unit="mA"),
        ],
        notes=[
            "8KB on-chip buffer split between TX and RX",
            "SPI commands: read (0x00), write (0x40), bit set (0x80), bit clear (0xA0), reset (0xFF)",
            "Bank switching via ECON1 bits 1:0 (4 register banks)",
            "Hardware MAC and 10Base-T PHY, no TCP/IP stack built-in",
        ],
    )


def _w5500() -> ComponentKnowledge:
    """WIZnet W5500 — Hardwired TCP/IP Ethernet controller (SPI)."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="W5500",
        manufacturer="WIZnet",
        mpn="W5500",
        description="Hardwired TCP/IP embedded Ethernet controller, 8 sockets",
        category="ethernet",
        interface=InterfaceType.SPI,
        spi_mode=0,
        registers=[
            RegisterInfo(address="0x0000", name="MR", description="Mode register"),
            RegisterInfo(address="0x0001", name="GAR", description="Gateway address (4 bytes)"),
            RegisterInfo(address="0x0005", name="SUBR", description="Subnet mask (4 bytes)"),
            RegisterInfo(address="0x0009", name="SHAR", description="Source MAC address (6 bytes)"),
            RegisterInfo(address="0x000F", name="SIPR", description="Source IP address (4 bytes)"),
            RegisterInfo(address="0x0039", name="VERSIONR", description="Chip version, returns 0x04"),
            RegisterInfo(address="0x0017", name="PHYCFGR", description="PHY configuration register"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x0000", value="0x80", description="Software reset"),
            InitStep(order=2, reg_addr="", value="", description="Wait for reset", delay_ms=2),
            InitStep(order=3, reg_addr="0x0039", value="", description="Read version to verify (expect 0x04)"),
            InitStep(order=4, reg_addr="0x0009", value="", description="Configure MAC address (6 bytes)"),
            InitStep(order=5, reg_addr="0x000F", value="", description="Configure source IP (4 bytes)"),
            InitStep(order=6, reg_addr="0x0001", value="", description="Configure gateway (4 bytes)"),
            InitStep(order=7, reg_addr="0x0005", value="", description="Configure subnet mask (4 bytes)"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="SPI clock frequency", max="80000000", unit="Hz"),
            TimingConstraint(parameter="Reset time", max="1", unit="ms"),
            TimingConstraint(parameter="Supply current", typical="132", unit="mA"),
        ],
        notes=[
            "Hardwired TCP/IP: TCP, UDP, IPv4, ARP, IGMP, PPPoE built-in",
            "8 independent sockets, 32KB TX + 32KB RX buffer",
            "SPI frame: address(16) + control(8) + data, variable length",
            "Block select byte selects common regs, socket regs, or TX/RX buffers",
        ],
    )


def _mcp2515() -> ComponentKnowledge:
    """Microchip MCP2515 — CAN bus controller (SPI)."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="MCP2515",
        manufacturer="Microchip",
        mpn="MCP2515",
        description="Stand-alone CAN controller with SPI interface",
        category="can_controller",
        interface=InterfaceType.SPI,
        spi_mode=0,
        registers=[
            RegisterInfo(address="0x0F", name="CANCTRL", description="CAN control register",
                         fields=[
                             RegisterField(name="REQOP", bits="7:5", description="Request operation mode"),
                             RegisterField(name="CLKEN", bits="2", description="CLKOUT pin enable"),
                         ]),
            RegisterInfo(address="0x0E", name="CANSTAT", description="CAN status (OPMOD, interrupt code)"),
            RegisterInfo(address="0x28", name="CNF3", description="Bit timing config 3"),
            RegisterInfo(address="0x29", name="CNF2", description="Bit timing config 2"),
            RegisterInfo(address="0x2A", name="CNF1", description="Bit timing config 1 (BRP, SJW)"),
            RegisterInfo(address="0x2B", name="CANINTE", description="Interrupt enable"),
            RegisterInfo(address="0x2C", name="CANINTF", description="Interrupt flag"),
            RegisterInfo(address="0x30", name="TXB0CTRL", description="TX buffer 0 control"),
            RegisterInfo(address="0x60", name="RXB0CTRL", description="RX buffer 0 control"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="", value="0xC0", description="SPI reset instruction"),
            InitStep(order=2, reg_addr="", value="", description="Wait for reset", delay_ms=10),
            InitStep(order=3, reg_addr="0x0F", value="0x80", description="Request Configuration mode"),
            InitStep(order=4, reg_addr="0x2A", value="0x00", description="CNF1: BRP=0, SJW=1 TQ (500kbps @ 8MHz)"),
            InitStep(order=5, reg_addr="0x29", value="0x90", description="CNF2: BTLMODE=1, PHSEG1=2"),
            InitStep(order=6, reg_addr="0x28", value="0x02", description="CNF3: PHSEG2=2"),
            InitStep(order=7, reg_addr="0x2B", value="0x03", description="Enable RX0 and RX1 interrupts"),
            InitStep(order=8, reg_addr="0x0F", value="0x00", description="Normal operation mode"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="SPI clock frequency", max="10000000", unit="Hz"),
            TimingConstraint(parameter="Oscillator startup", max="128", unit="cycles"),
            TimingConstraint(parameter="Supply current", typical="5", unit="mA"),
        ],
        notes=[
            "Requires external CAN transceiver (MCP2551 or TJA1050)",
            "3 TX buffers, 2 RX buffers with programmable filters/masks",
            "SPI instructions: RESET(0xC0), READ(0x03), WRITE(0x02), BIT_MODIFY(0x05)",
            "Crystal oscillator typically 8MHz or 16MHz",
        ],
    )


def _cc1101() -> ComponentKnowledge:
    """Texas Instruments CC1101 — Sub-1GHz RF transceiver (SPI)."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="CC1101",
        manufacturer="Texas Instruments",
        mpn="CC1101",
        description="Low-power sub-1GHz RF transceiver (315/433/868/915MHz)",
        category="rf_transceiver",
        interface=InterfaceType.SPI,
        spi_mode=0,
        registers=[
            RegisterInfo(address="0x00", name="IOCFG2", description="GDO2 output pin configuration"),
            RegisterInfo(address="0x01", name="IOCFG1", description="GDO1 output pin configuration"),
            RegisterInfo(address="0x02", name="IOCFG0", description="GDO0 output pin configuration"),
            RegisterInfo(address="0x08", name="PKTCTRL0", description="Packet automation control"),
            RegisterInfo(address="0x0B", name="FSCTRL1", description="Frequency synthesizer control"),
            RegisterInfo(address="0x0D", name="FREQ2", description="Frequency control word, high byte"),
            RegisterInfo(address="0x0E", name="FREQ1", description="Frequency control word, mid byte"),
            RegisterInfo(address="0x0F", name="FREQ0", description="Frequency control word, low byte"),
            RegisterInfo(address="0x10", name="MDMCFG4", description="Modem configuration (BW, data rate)"),
            RegisterInfo(address="0x12", name="MDMCFG2", description="Modem config (modulation, sync mode)"),
            RegisterInfo(address="0x35", name="MARCSTATE", description="Main radio state machine state"),
            RegisterInfo(address="0x3F", name="FIFO", description="TX/RX FIFO (64 bytes each)"),
            RegisterInfo(address="0xF0", name="PARTNUM", description="Part number, returns 0x00"),
            RegisterInfo(address="0xF1", name="VERSION", description="Chip version"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="", value="0x30", description="SRES — reset chip strobe"),
            InitStep(order=2, reg_addr="", value="", description="Wait for crystal", delay_ms=1),
            InitStep(order=3, reg_addr="0x02", value="0x06", description="GDO0: sync word detected"),
            InitStep(order=4, reg_addr="0x0D", value="0x10", description="Freq 433.92MHz (FREQ2)"),
            InitStep(order=5, reg_addr="0x0E", value="0xB1", description="Freq 433.92MHz (FREQ1)"),
            InitStep(order=6, reg_addr="0x0F", value="0x3B", description="Freq 433.92MHz (FREQ0)"),
            InitStep(order=7, reg_addr="0x10", value="0xF8", description="200kHz RX BW, data rate MSB"),
            InitStep(order=8, reg_addr="0x12", value="0x32", description="2-FSK, 30/32 sync word detection"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="SPI clock frequency", max="6500000", unit="Hz"),
            TimingConstraint(parameter="Crystal startup", max="150", unit="us"),
            TimingConstraint(parameter="Supply current (TX 10dBm)", typical="30", unit="mA"),
            TimingConstraint(parameter="Supply current (RX)", typical="15.6", unit="mA"),
        ],
        notes=[
            "Frequency: Freq = FREQ[23:0] * F_XOSC / 2^16 (F_XOSC=26MHz)",
            "Strobe commands: 0x30=SRES, 0x34=SRX, 0x35=STX, 0x36=SIDLE",
            "64-byte TX and RX FIFOs",
            "GDO pins for interrupt-driven operation",
        ],
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTRY: dict[str, callable] = {
    # GNSS
    "NEO-M8N": _neo_m8n,
    "NEO-M8": _neo_m8n,
    "NEO-M9N": _neo_m8n,
    "NEO-6M": _neo_m8n,
    # LoRa
    "SX1276": _sx1276,
    "SX1278": _sx1276,  # 433MHz variant, same registers
    "RFM95W": _sx1276,
    "RFM95": _sx1276,
    "RFM96W": _sx1276,
    "SX1262": _sx1276,  # newer, different register set but similar concept
    # 2.4GHz
    "NRF24L01": _nrf24l01,
    "NRF24L01+": _nrf24l01,
    "NRF24L01P": _nrf24l01,
    # Ethernet
    "ENC28J60": _enc28j60,
    "W5500": _w5500,
    "W5100": _w5500,  # similar register concept, smaller buffer
    # CAN
    "MCP2515": _mcp2515,
    "MCP25625": _mcp2515,  # MCP2515 + transceiver
    # Sub-GHz
    "CC1101": _cc1101,
}
