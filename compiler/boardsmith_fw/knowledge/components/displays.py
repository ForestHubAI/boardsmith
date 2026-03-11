# SPDX-License-Identifier: AGPL-3.0-or-later
"""Display components — OLED, TFT LCD, LED drivers."""

from __future__ import annotations

from boardsmith_fw.models.component_knowledge import (
    ComponentKnowledge,
    InitStep,
    InterfaceType,
    RegisterInfo,
    TimingConstraint,
)


def _ssd1306() -> ComponentKnowledge:
    """Solomon Systech SSD1306 — 128x64 OLED display controller."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="SSD1306",
        manufacturer="Solomon Systech",
        mpn="SSD1306",
        description="128x64 dot matrix OLED/PLED segment/common driver",
        category="display",
        interface=InterfaceType.I2C,
        i2c_address="0x3C",
        spi_mode=0,
        registers=[
            RegisterInfo(address="0xAE", name="DISPLAY_OFF", description="Display OFF"),
            RegisterInfo(address="0xAF", name="DISPLAY_ON", description="Display ON"),
            RegisterInfo(address="0xD5", name="SET_CLOCK_DIV", description="Set display clock divide ratio"),
            RegisterInfo(address="0xA8", name="SET_MULTIPLEX", description="Set multiplex ratio (rows - 1)"),
            RegisterInfo(address="0xD3", name="SET_DISPLAY_OFFSET", description="Set display offset"),
            RegisterInfo(address="0x40", name="SET_START_LINE", description="Set display start line (0x40-0x7F)"),
            RegisterInfo(address="0x8D", name="CHARGE_PUMP", description="Charge pump setting (0x14=enable)"),
            RegisterInfo(address="0x20", name="SET_MEMORY_MODE", description="Addr mode (0=horiz, 1=vert, 2=page)"),
            RegisterInfo(address="0xA1", name="SEG_REMAP", description="Segment re-map (0xA0=normal, 0xA1=remapped)"),
            RegisterInfo(address="0xC8", name="COM_SCAN_DEC", description="COM scan dir (0xC0=normal, 0xC8=remapped)"),
            RegisterInfo(address="0xDA", name="SET_COM_PINS", description="COM pins hardware config"),
            RegisterInfo(address="0x81", name="SET_CONTRAST", description="Set contrast (0x00-0xFF)"),
            RegisterInfo(address="0xD9", name="SET_PRECHARGE", description="Set pre-charge period"),
            RegisterInfo(address="0xDB", name="SET_VCOMH_DESELECT", description="Set VCOMH deselect level"),
            RegisterInfo(address="0xA4", name="DISPLAY_ALL_ON_RESUME", description="Output follows RAM content"),
            RegisterInfo(address="0xA6", name="NORMAL_DISPLAY", description="Normal display (not inverted)"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0xAE", value="", description="Display OFF"),
            InitStep(order=2, reg_addr="0xD5", value="0x80", description="Clock divide 1, osc freq default"),
            InitStep(order=3, reg_addr="0xA8", value="0x3F", description="Multiplex ratio 64"),
            InitStep(order=4, reg_addr="0xD3", value="0x00", description="Display offset 0"),
            InitStep(order=5, reg_addr="0x40", value="", description="Start line 0"),
            InitStep(order=6, reg_addr="0x8D", value="0x14", description="Enable charge pump"),
            InitStep(order=7, reg_addr="0x20", value="0x00", description="Horizontal addressing mode"),
            InitStep(order=8, reg_addr="0xA1", value="", description="Segment remap 127 to SEG0"),
            InitStep(order=9, reg_addr="0xC8", value="", description="COM scan direction remapped"),
            InitStep(order=10, reg_addr="0xDA", value="0x12", description="COM pins: alternative, no remap"),
            InitStep(order=11, reg_addr="0x81", value="0xCF", description="Contrast 207"),
            InitStep(order=12, reg_addr="0xD9", value="0xF1", description="Pre-charge period: phase1=1, phase2=15"),
            InitStep(order=13, reg_addr="0xDB", value="0x40", description="VCOMH deselect 0.77*VCC"),
            InitStep(order=14, reg_addr="0xA4", value="", description="Display follows RAM"),
            InitStep(order=15, reg_addr="0xA6", value="", description="Normal display mode"),
            InitStep(order=16, reg_addr="0xAF", value="", description="Display ON"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="SPI clock frequency", max="10000000", unit="Hz"),
            TimingConstraint(parameter="Power-on time", max="100", unit="ms"),
            TimingConstraint(parameter="Supply current (50% pixels)", typical="10", unit="mA"),
        ],
        notes=[
            "I2C address 0x3C (SA0=low) or 0x3D (SA0=high)",
            "I2C data: control byte (0x00=command, 0x40=data) followed by payload",
            "Framebuffer: 128*64/8 = 1024 bytes, arranged in 8 pages of 128 columns",
            "Also supports 3/4-wire SPI with D/C# pin",
        ],
    )


def _sh1106() -> ComponentKnowledge:
    """Sino Wealth SH1106 — 132x64 OLED display controller."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="SH1106",
        manufacturer="Sino Wealth",
        mpn="SH1106",
        description="132x64 OLED/PLED segment/common driver (SSD1306-like)",
        category="display",
        interface=InterfaceType.I2C,
        i2c_address="0x3C",
        spi_mode=0,
        registers=[
            RegisterInfo(address="0xAE", name="DISPLAY_OFF", description="Display OFF"),
            RegisterInfo(address="0xAF", name="DISPLAY_ON", description="Display ON"),
            RegisterInfo(address="0xD5", name="SET_CLOCK_DIV", description="Set display clock"),
            RegisterInfo(address="0xA8", name="SET_MULTIPLEX", description="Set multiplex ratio"),
            RegisterInfo(address="0xD3", name="SET_DISPLAY_OFFSET", description="Set display offset"),
            RegisterInfo(address="0x8D", name="CHARGE_PUMP", description="Charge pump setting"),
            RegisterInfo(address="0xB0", name="SET_PAGE_ADDR", description="Set page address (0xB0-0xB7)"),
            RegisterInfo(address="0x10", name="SET_HIGH_COLUMN", description="Set higher column address"),
            RegisterInfo(address="0x02", name="SET_LOW_COLUMN", description="Set lower column address (offset 2)"),
            RegisterInfo(address="0x81", name="SET_CONTRAST", description="Set contrast"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0xAE", value="", description="Display OFF"),
            InitStep(order=2, reg_addr="0xD5", value="0x80", description="Clock divide default"),
            InitStep(order=3, reg_addr="0xA8", value="0x3F", description="Multiplex ratio 64"),
            InitStep(order=4, reg_addr="0xD3", value="0x00", description="Display offset 0"),
            InitStep(order=5, reg_addr="0x40", value="", description="Start line 0"),
            InitStep(order=6, reg_addr="0x8D", value="0x14", description="Enable charge pump"),
            InitStep(order=7, reg_addr="0xA1", value="", description="Segment remap"),
            InitStep(order=8, reg_addr="0xC8", value="", description="COM scan direction remapped"),
            InitStep(order=9, reg_addr="0xDA", value="0x12", description="COM pins config"),
            InitStep(order=10, reg_addr="0x81", value="0x80", description="Contrast 128"),
            InitStep(order=11, reg_addr="0xA6", value="", description="Normal display"),
            InitStep(order=12, reg_addr="0xAF", value="", description="Display ON"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="SPI clock frequency", max="4000000", unit="Hz"),
            TimingConstraint(parameter="Supply current (50% pixels)", typical="8", unit="mA"),
        ],
        notes=[
            "I2C address 0x3C or 0x3D",
            "132 columns vs SSD1306's 128 — column offset 2 needed for centering",
            "Page addressing mode only (no horizontal/vertical addressing mode)",
            "Write each page (0xB0-0xB7) separately with column address set",
        ],
    )


def _st7735() -> ComponentKnowledge:
    """Sitronix ST7735 — 128x160 TFT LCD controller (SPI)."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="ST7735",
        manufacturer="Sitronix",
        mpn="ST7735S",
        description="262K color 128x160 TFT LCD driver with SPI interface",
        category="display",
        interface=InterfaceType.SPI,
        spi_mode=0,
        registers=[
            RegisterInfo(address="0x01", name="SWRESET", description="Software reset"),
            RegisterInfo(address="0x11", name="SLPOUT", description="Sleep out"),
            RegisterInfo(address="0x3A", name="COLMOD", description="Interface pixel format (0x05=16bit, 0x06=18bit)"),
            RegisterInfo(address="0x36", name="MADCTL", description="Memory data access control (rotation, mirror)"),
            RegisterInfo(address="0x2A", name="CASET", description="Column address set (4 bytes)"),
            RegisterInfo(address="0x2B", name="RASET", description="Row address set (4 bytes)"),
            RegisterInfo(address="0x2C", name="RAMWR", description="Memory write (pixel data follows)"),
            RegisterInfo(address="0x29", name="DISPON", description="Display ON"),
            RegisterInfo(address="0x28", name="DISPOFF", description="Display OFF"),
            RegisterInfo(address="0xB1", name="FRMCTR1", description="Frame rate control (normal mode)"),
            RegisterInfo(address="0xC0", name="PWCTR1", description="Power control 1"),
            RegisterInfo(address="0xC5", name="VMCTR1", description="VCOM control"),
            RegisterInfo(address="0xE0", name="GMCTRP1", description="Gamma (+) correction"),
            RegisterInfo(address="0xE1", name="GMCTRN1", description="Gamma (-) correction"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x01", value="", description="Software reset"),
            InitStep(order=2, reg_addr="", value="", description="Wait for reset", delay_ms=150),
            InitStep(order=3, reg_addr="0x11", value="", description="Sleep out"),
            InitStep(order=4, reg_addr="", value="", description="Wait for sleep out", delay_ms=150),
            InitStep(order=5, reg_addr="0xB1", value="0x01,0x2C,0x2D", description="Frame rate: normal mode"),
            InitStep(order=6, reg_addr="0xC0", value="0xA2,0x02,0x84", description="Power control 1"),
            InitStep(order=7, reg_addr="0xC5", value="0x0E", description="VCOM control"),
            InitStep(order=8, reg_addr="0x3A", value="0x05", description="16-bit color (RGB565)"),
            InitStep(order=9, reg_addr="0x36", value="0x08", description="Memory access: BGR order"),
            InitStep(order=10, reg_addr="0x29", value="", description="Display ON"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="SPI clock frequency", max="15000000", unit="Hz"),
            TimingConstraint(parameter="Reset pulse width", min="10", unit="us"),
            TimingConstraint(parameter="Supply current (display on)", typical="4", unit="mA"),
        ],
        notes=[
            "SPI mode 0 with D/C (Data/Command) pin",
            "CS active low, D/C=0 for commands, D/C=1 for data",
            "RGB565 format: 2 bytes per pixel, 128*160*2 = 40960 bytes full frame",
            "Tab offset varies by display variant (green/red/black tab)",
        ],
    )


def _st7789() -> ComponentKnowledge:
    """Sitronix ST7789 — 240x320 TFT LCD controller (SPI)."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="ST7789",
        manufacturer="Sitronix",
        mpn="ST7789V",
        description="262K color 240x320 TFT LCD driver with SPI interface",
        category="display",
        interface=InterfaceType.SPI,
        spi_mode=0,
        registers=[
            RegisterInfo(address="0x01", name="SWRESET", description="Software reset"),
            RegisterInfo(address="0x11", name="SLPOUT", description="Sleep out"),
            RegisterInfo(address="0x3A", name="COLMOD", description="Interface pixel format"),
            RegisterInfo(address="0x36", name="MADCTL", description="Memory data access control"),
            RegisterInfo(address="0x2A", name="CASET", description="Column address set"),
            RegisterInfo(address="0x2B", name="RASET", description="Row address set"),
            RegisterInfo(address="0x2C", name="RAMWR", description="Memory write"),
            RegisterInfo(address="0x21", name="INVON", description="Display inversion ON"),
            RegisterInfo(address="0x13", name="NORON", description="Normal display mode ON"),
            RegisterInfo(address="0x29", name="DISPON", description="Display ON"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x01", value="", description="Software reset"),
            InitStep(order=2, reg_addr="", value="", description="Wait for reset", delay_ms=150),
            InitStep(order=3, reg_addr="0x11", value="", description="Sleep out"),
            InitStep(order=4, reg_addr="", value="", description="Wait for sleep out", delay_ms=50),
            InitStep(order=5, reg_addr="0x3A", value="0x55", description="16-bit color (RGB565)"),
            InitStep(order=6, reg_addr="0x36", value="0x00", description="Memory access control: normal"),
            InitStep(order=7, reg_addr="0x21", value="", description="Display inversion ON (required for IPS panels)"),
            InitStep(order=8, reg_addr="0x13", value="", description="Normal display mode"),
            InitStep(order=9, reg_addr="0x29", value="", description="Display ON"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="SPI clock frequency", max="62500000", unit="Hz"),
            TimingConstraint(parameter="Reset time", min="10", unit="us"),
            TimingConstraint(parameter="Supply current (display on)", typical="5", unit="mA"),
        ],
        notes=[
            "SPI mode 0, with D/C pin",
            "Most 240x240 round/square displays use ST7789 with offset",
            "Display inversion ON is typically needed for IPS panel variants",
            "Full frame RGB565: 240*320*2 = 153600 bytes",
        ],
    )


def _ili9341() -> ComponentKnowledge:
    """Ilitek ILI9341 — 240x320 TFT LCD controller (SPI/parallel)."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="ILI9341",
        manufacturer="Ilitek",
        mpn="ILI9341",
        description="262K color 240x320 TFT LCD single-chip driver",
        category="display",
        interface=InterfaceType.SPI,
        spi_mode=0,
        registers=[
            RegisterInfo(address="0x01", name="SWRESET", description="Software reset"),
            RegisterInfo(address="0x11", name="SLPOUT", description="Sleep out"),
            RegisterInfo(address="0x3A", name="PIXFMT", description="Pixel format (0x55=16-bit)"),
            RegisterInfo(address="0x36", name="MADCTL", description="Memory access control"),
            RegisterInfo(address="0x2A", name="CASET", description="Column address set"),
            RegisterInfo(address="0x2B", name="PASET", description="Page address set"),
            RegisterInfo(address="0x2C", name="RAMWR", description="Memory write"),
            RegisterInfo(address="0x29", name="DISPON", description="Display ON"),
            RegisterInfo(address="0xCB", name="PWCTR_A", description="Power control A"),
            RegisterInfo(address="0xCF", name="PWCTR_B", description="Power control B"),
            RegisterInfo(address="0xC0", name="PWCTR1", description="Power control 1"),
            RegisterInfo(address="0xC1", name="PWCTR2", description="Power control 2"),
            RegisterInfo(address="0xB6", name="DFUNCTR", description="Display function control"),
            RegisterInfo(address="0x04", name="RDDID", description="Read display ID (returns manuf, driver, version)"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x01", value="", description="Software reset"),
            InitStep(order=2, reg_addr="", value="", description="Wait for reset", delay_ms=150),
            InitStep(order=3, reg_addr="0x11", value="", description="Sleep out"),
            InitStep(order=4, reg_addr="", value="", description="Wait for sleep out", delay_ms=150),
            InitStep(order=5, reg_addr="0xCF", value="0x00,0xC1,0x30", description="Power control B"),
            InitStep(order=6, reg_addr="0xC0", value="0x23", description="Power control 1: VRH=4.60V"),
            InitStep(order=7, reg_addr="0xC1", value="0x10", description="Power control 2"),
            InitStep(order=8, reg_addr="0x3A", value="0x55", description="16-bit color (RGB565)"),
            InitStep(order=9, reg_addr="0x36", value="0x48", description="Memory access: row/col exchange, BGR"),
            InitStep(order=10, reg_addr="0x29", value="", description="Display ON"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="SPI clock frequency", max="10000000", unit="Hz"),
            TimingConstraint(parameter="Reset pulse width", min="10", unit="us"),
            TimingConstraint(parameter="Supply current (display on)", typical="7", unit="mA"),
        ],
        notes=[
            "SPI mode 0, with D/C and CS pins",
            "Also supports 8/16-bit parallel interface",
            "Touch controller (XPT2046) often paired, separate SPI CS",
            "Full frame RGB565: 240*320*2 = 153600 bytes",
        ],
    )


def _max7219() -> ComponentKnowledge:
    """Maxim MAX7219 — 8-digit LED display driver (SPI)."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="MAX7219",
        manufacturer="Maxim Integrated",
        mpn="MAX7219",
        description="8-digit LED display driver, SPI interface, cascade-able",
        category="display",
        interface=InterfaceType.SPI,
        spi_mode=0,
        registers=[
            RegisterInfo(address="0x00", name="NOOP", description="No operation"),
            RegisterInfo(address="0x01", name="DIGIT_0", description="Digit 0 data"),
            RegisterInfo(address="0x02", name="DIGIT_1", description="Digit 1 data"),
            RegisterInfo(address="0x03", name="DIGIT_2", description="Digit 2 data"),
            RegisterInfo(address="0x04", name="DIGIT_3", description="Digit 3 data"),
            RegisterInfo(address="0x05", name="DIGIT_4", description="Digit 4 data"),
            RegisterInfo(address="0x06", name="DIGIT_5", description="Digit 5 data"),
            RegisterInfo(address="0x07", name="DIGIT_6", description="Digit 6 data"),
            RegisterInfo(address="0x08", name="DIGIT_7", description="Digit 7 data"),
            RegisterInfo(address="0x09", name="DECODE_MODE", description="BCD decode mode (0xFF=all digits)"),
            RegisterInfo(address="0x0A", name="INTENSITY", description="Display intensity (0x00-0x0F)"),
            RegisterInfo(address="0x0B", name="SCAN_LIMIT", description="Scan limit (0-7 digits)"),
            RegisterInfo(address="0x0C", name="SHUTDOWN", description="Shutdown mode (0=shutdown, 1=normal)"),
            RegisterInfo(address="0x0F", name="DISPLAY_TEST", description="Display test (0=normal, 1=all on)"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x0C", value="0x00", description="Shutdown mode"),
            InitStep(order=2, reg_addr="0x0F", value="0x00", description="Display test off"),
            InitStep(order=3, reg_addr="0x09", value="0x00", description="No BCD decode (raw segments)"),
            InitStep(order=4, reg_addr="0x0B", value="0x07", description="Scan all 8 digits"),
            InitStep(order=5, reg_addr="0x0A", value="0x07", description="Medium intensity"),
            InitStep(order=6, reg_addr="0x0C", value="0x01", description="Normal operation"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="SPI clock frequency", max="10000000", unit="Hz"),
            TimingConstraint(parameter="Supply current (all on, max intensity)", max="330", unit="mA"),
        ],
        notes=[
            "16-bit SPI frames: [address(8)][data(8)], active-low CS",
            "For 8x8 LED matrix: each digit register controls one row (8 LEDs)",
            "Cascade: chain DOUT to DIN of next module, wider CS pulse",
            "RSET resistor sets segment current: I_SEG = 100 * V / R_SET",
        ],
    )


def _ht16k33() -> ComponentKnowledge:
    """Holtek HT16K33 — LED controller with I2C interface."""
    return ComponentKnowledge(
        version="1.0.0",
        component_id="",
        name="HT16K33",
        manufacturer="Holtek",
        mpn="HT16K33",
        description="RAM mapping 16*8 LED controller with keyscan, I2C interface",
        category="display",
        interface=InterfaceType.I2C,
        i2c_address="0x70",
        registers=[
            RegisterInfo(address="0x00", name="DISPLAY_DATA", description="Display RAM (16 bytes for 16x8 matrix)"),
            RegisterInfo(address="0x20", name="SYSTEM_SETUP", description="System setup (bit 0: oscillator on)"),
            RegisterInfo(address="0x80", name="DISPLAY_SETUP", description="Display on/off + blink rate"),
            RegisterInfo(address="0xE0", name="DIMMING", description="Digital dimming (0x00-0x0F)"),
            RegisterInfo(address="0xA0", name="ROW_INT_SET", description="ROW/INT output pin config"),
        ],
        init_sequence=[
            InitStep(order=1, reg_addr="0x21", value="", description="Turn on system oscillator"),
            InitStep(order=2, reg_addr="0xE0", value="", description="Set dimming to max (0x0F)"),
            InitStep(order=3, reg_addr="0x81", value="", description="Display ON, no blink"),
        ],
        timing_constraints=[
            TimingConstraint(parameter="I2C clock frequency", max="400000", unit="Hz"),
            TimingConstraint(parameter="Supply current (all LEDs)", max="150", unit="mA"),
        ],
        notes=[
            "I2C address 0x70-0x77 (A0-A2 pins)",
            "16 bytes display RAM starting at 0x00",
            "Used in Adafruit LED backpacks (7-segment, 14-segment, 8x8 matrix)",
            "Blink rates: 0=off, 1=2Hz, 2=1Hz, 3=0.5Hz",
        ],
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTRY: dict[str, callable] = {
    "SSD1306": _ssd1306,
    "SH1106": _sh1106,
    "SH1107": _sh1106,  # similar command set
    "ST7735": _st7735,
    "ST7735S": _st7735,
    "ST7789": _st7789,
    "ST7789V": _st7789,
    "ILI9341": _ili9341,
    "ILI9340": _ili9341,  # compatible
    "MAX7219": _max7219,
    "MAX7221": _max7219,  # SPI-compatible variant
    "HT16K33": _ht16k33,
}
