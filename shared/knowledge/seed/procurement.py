# SPDX-License-Identifier: AGPL-3.0-or-later
"""DB-6: Procurement seed data — LCSC part numbers, prices, and substitute mappings.

Data sourced from LCSC.com (2026-03). Prices at qty=10 in USD.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Supplier parts — LCSC listings for top-50 MPNs
# ---------------------------------------------------------------------------

SUPPLIER_PARTS: list[dict] = [
    # MCU modules
    {"mpn": "ESP32-WROOM-32",   "supplier": "LCSC", "sku": "C82899",  "unit_price_usd": 2.15,  "moq": 1,  "stock_qty": 50000, "url": "https://www.lcsc.com/product-detail/C82899.html",  "last_seen": "2026-03-01"},
    {"mpn": "ESP32-S3-WROOM-1", "supplier": "LCSC", "sku": "C2913202","unit_price_usd": 2.80,  "moq": 1,  "stock_qty": 30000, "url": "https://www.lcsc.com/product-detail/C2913202.html","last_seen": "2026-03-01"},
    # Sensors
    {"mpn": "BME280",           "supplier": "LCSC", "sku": "C17024",  "unit_price_usd": 2.90,  "moq": 1,  "stock_qty": 20000, "url": "https://www.lcsc.com/product-detail/C17024.html",  "last_seen": "2026-03-01"},
    {"mpn": "BME680",           "supplier": "LCSC", "sku": "C114664", "unit_price_usd": 4.60,  "moq": 1,  "stock_qty": 8000,  "url": "https://www.lcsc.com/product-detail/C114664.html", "last_seen": "2026-03-01"},
    {"mpn": "MPU-6050",         "supplier": "LCSC", "sku": "C24112",  "unit_price_usd": 0.75,  "moq": 1,  "stock_qty": 80000, "url": "https://www.lcsc.com/product-detail/C24112.html",  "last_seen": "2026-03-01"},
    {"mpn": "ICM-42688-P",      "supplier": "LCSC", "sku": "C2016204","unit_price_usd": 2.10,  "moq": 1,  "stock_qty": 15000, "url": "https://www.lcsc.com/product-detail/C2016204.html","last_seen": "2026-03-01"},
    {"mpn": "SCD41",            "supplier": "LCSC", "sku": "C3029458","unit_price_usd": 42.00, "moq": 1,  "stock_qty": 2000,  "url": "https://www.lcsc.com/product-detail/C3029458.html","last_seen": "2026-03-01"},
    {"mpn": "VL53L0X",          "supplier": "LCSC", "sku": "C91194",  "unit_price_usd": 2.20,  "moq": 1,  "stock_qty": 12000, "url": "https://www.lcsc.com/product-detail/C91194.html",  "last_seen": "2026-03-01"},
    {"mpn": "INA219",           "supplier": "LCSC", "sku": "C18974",  "unit_price_usd": 0.95,  "moq": 1,  "stock_qty": 35000, "url": "https://www.lcsc.com/product-detail/C18974.html",  "last_seen": "2026-03-01"},
    {"mpn": "INA226",           "supplier": "LCSC", "sku": "C138656", "unit_price_usd": 1.20,  "moq": 1,  "stock_qty": 18000, "url": "https://www.lcsc.com/product-detail/C138656.html", "last_seen": "2026-03-01"},
    {"mpn": "BH1750",           "supplier": "LCSC", "sku": "C78960",  "unit_price_usd": 0.55,  "moq": 1,  "stock_qty": 25000, "url": "https://www.lcsc.com/product-detail/C78960.html",  "last_seen": "2026-03-01"},
    {"mpn": "ADS1115",          "supplier": "LCSC", "sku": "C37593",  "unit_price_usd": 1.85,  "moq": 1,  "stock_qty": 20000, "url": "https://www.lcsc.com/product-detail/C37593.html",  "last_seen": "2026-03-01"},
    # Display
    {"mpn": "SSD1306",          "supplier": "LCSC", "sku": "C96457",  "unit_price_usd": 1.20,  "moq": 1,  "stock_qty": 40000, "url": "https://www.lcsc.com/product-detail/C96457.html",  "last_seen": "2026-03-01"},
    # RF / LoRa
    {"mpn": "SX1276",           "supplier": "LCSC", "sku": "C97648",  "unit_price_usd": 4.80,  "moq": 1,  "stock_qty": 6000,  "url": "https://www.lcsc.com/product-detail/C97648.html",  "last_seen": "2026-03-01"},
    # Memory
    {"mpn": "W25Q128JV",        "supplier": "LCSC", "sku": "C97521",  "unit_price_usd": 0.90,  "moq": 1,  "stock_qty": 60000, "url": "https://www.lcsc.com/product-detail/C97521.html",  "last_seen": "2026-03-01"},
    # LDOs
    {"mpn": "AMS1117-3.3",      "supplier": "LCSC", "sku": "C6186",   "unit_price_usd": 0.08,  "moq": 1,  "stock_qty": 500000,"url": "https://www.lcsc.com/product-detail/C6186.html",   "last_seen": "2026-03-01"},
    {"mpn": "AP2112K-3.3TRG1",  "supplier": "LCSC", "sku": "C51118",  "unit_price_usd": 0.18,  "moq": 1,  "stock_qty": 200000,"url": "https://www.lcsc.com/product-detail/C51118.html",  "last_seen": "2026-03-01"},
    {"mpn": "LM3671MFX-3.3",    "supplier": "LCSC", "sku": "C2767",   "unit_price_usd": 0.90,  "moq": 1,  "stock_qty": 20000, "url": "https://www.lcsc.com/product-detail/C2767.html",   "last_seen": "2026-03-01"},
    {"mpn": "TPS562201DDCR",    "supplier": "LCSC", "sku": "C163847", "unit_price_usd": 0.65,  "moq": 1,  "stock_qty": 30000, "url": "https://www.lcsc.com/product-detail/C163847.html", "last_seen": "2026-03-01"},
    {"mpn": "MP1584EN",         "supplier": "LCSC", "sku": "C21325",  "unit_price_usd": 0.45,  "moq": 1,  "stock_qty": 50000, "url": "https://www.lcsc.com/product-detail/C21325.html",  "last_seen": "2026-03-01"},
    # Battery management
    {"mpn": "MCP73831T-2ACI/OT","supplier": "LCSC", "sku": "C424093", "unit_price_usd": 0.55,  "moq": 1,  "stock_qty": 25000, "url": "https://www.lcsc.com/product-detail/C424093.html", "last_seen": "2026-03-01"},
    {"mpn": "TP4056",           "supplier": "LCSC", "sku": "C16581",  "unit_price_usd": 0.12,  "moq": 1,  "stock_qty": 200000,"url": "https://www.lcsc.com/product-detail/C16581.html",  "last_seen": "2026-03-01"},
    # Comms
    {"mpn": "SN65HVD230",       "supplier": "LCSC", "sku": "C136759", "unit_price_usd": 0.95,  "moq": 1,  "stock_qty": 15000, "url": "https://www.lcsc.com/product-detail/C136759.html", "last_seen": "2026-03-01"},
    {"mpn": "MAX485ECSA+",      "supplier": "LCSC", "sku": "C144435", "unit_price_usd": 0.75,  "moq": 1,  "stock_qty": 20000, "url": "https://www.lcsc.com/product-detail/C144435.html", "last_seen": "2026-03-01"},
    {"mpn": "TJA1051T/3",       "supplier": "LCSC", "sku": "C7452",   "unit_price_usd": 0.85,  "moq": 1,  "stock_qty": 25000, "url": "https://www.lcsc.com/product-detail/C7452.html",   "last_seen": "2026-03-01"},
    {"mpn": "CP2102N",          "supplier": "LCSC", "sku": "C6568",   "unit_price_usd": 1.40,  "moq": 1,  "stock_qty": 30000, "url": "https://www.lcsc.com/product-detail/C6568.html",   "last_seen": "2026-03-01"},
    {"mpn": "CH340C",           "supplier": "LCSC", "sku": "C84681",  "unit_price_usd": 0.20,  "moq": 1,  "stock_qty": 100000,"url": "https://www.lcsc.com/product-detail/C84681.html",  "last_seen": "2026-03-01"},
    {"mpn": "LAN8720A",         "supplier": "LCSC", "sku": "C507432", "unit_price_usd": 1.80,  "moq": 1,  "stock_qty": 8000,  "url": "https://www.lcsc.com/product-detail/C507432.html", "last_seen": "2026-03-01"},
    # Protection
    {"mpn": "USBLC6-2SC6",      "supplier": "LCSC", "sku": "C7519",   "unit_price_usd": 0.18,  "moq": 1,  "stock_qty": 150000,"url": "https://www.lcsc.com/product-detail/C7519.html",   "last_seen": "2026-03-01"},
    {"mpn": "PRTR5V0U2X",       "supplier": "LCSC", "sku": "C12333",  "unit_price_usd": 0.20,  "moq": 1,  "stock_qty": 80000, "url": "https://www.lcsc.com/product-detail/C12333.html",  "last_seen": "2026-03-01"},
    # Actuators / drivers
    {"mpn": "TB6612FNG",        "supplier": "LCSC", "sku": "C123986", "unit_price_usd": 0.98,  "moq": 1,  "stock_qty": 20000, "url": "https://www.lcsc.com/product-detail/C123986.html", "last_seen": "2026-03-01"},
    {"mpn": "ULN2003A",         "supplier": "LCSC", "sku": "C5723",   "unit_price_usd": 0.12,  "moq": 1,  "stock_qty": 200000,"url": "https://www.lcsc.com/product-detail/C5723.html",   "last_seen": "2026-03-01"},
    {"mpn": "IRLML6244TRPBF",   "supplier": "LCSC", "sku": "C20917",  "unit_price_usd": 0.15,  "moq": 1,  "stock_qty": 80000, "url": "https://www.lcsc.com/product-detail/C20917.html",  "last_seen": "2026-03-01"},
    # Analog
    {"mpn": "LM358",            "supplier": "LCSC", "sku": "C7950",   "unit_price_usd": 0.10,  "moq": 1,  "stock_qty": 300000,"url": "https://www.lcsc.com/product-detail/C7950.html",   "last_seen": "2026-03-01"},
    {"mpn": "LM393",            "supplier": "LCSC", "sku": "C7949",   "unit_price_usd": 0.09,  "moq": 1,  "stock_qty": 250000,"url": "https://www.lcsc.com/product-detail/C7949.html",   "last_seen": "2026-03-01"},
    {"mpn": "ADuM1201ARZ",      "supplier": "LCSC", "sku": "C9234",   "unit_price_usd": 2.40,  "moq": 1,  "stock_qty": 5000,  "url": "https://www.lcsc.com/product-detail/C9234.html",   "last_seen": "2026-03-01"},
    # Passives — standard values
    {"mpn": "GRM155R71C104KA88D","supplier": "LCSC", "sku": "C14663", "unit_price_usd": 0.004, "moq": 100,"stock_qty": 1000000,"url": "https://www.lcsc.com/product-detail/C14663.html", "last_seen": "2026-03-01"},
    {"mpn": "RC0402FR-074K7L",  "supplier": "LCSC", "sku": "C25896",  "unit_price_usd": 0.003, "moq": 100,"stock_qty": 2000000,"url": "https://www.lcsc.com/product-detail/C25896.html",  "last_seen": "2026-03-01"},
    # Crystal
    {"mpn": "X322516MLB4SI",    "supplier": "LCSC", "sku": "C13738",  "unit_price_usd": 0.25,  "moq": 1,  "stock_qty": 50000, "url": "https://www.lcsc.com/product-detail/C13738.html",  "last_seen": "2026-03-01"},
]

# ---------------------------------------------------------------------------
# Substitute relationships (pin-compatible or functional equivalents)
# ---------------------------------------------------------------------------

SUBSTITUTES: list[dict] = [
    # BME280 → BMP280 (no humidity, pin-compat footprint)
    {"primary_mpn": "BME280",    "substitute_mpn": "BMP280",     "reason": "functional-equiv", "confidence": 0.85, "verified": True,  "notes": "Same footprint LGA-8; BMP280 has no humidity sensor"},
    # BME280 → BME680 (adds VOC gas sensing, pin-compat)
    {"primary_mpn": "BME280",    "substitute_mpn": "BME680",     "reason": "functional-equiv", "confidence": 0.90, "verified": True,  "notes": "BME680 superset: adds VOC, same I2C protocol"},
    # MPU-6050 → ICM-42688-P (newer, better, SPI only at high speed)
    {"primary_mpn": "MPU-6050",  "substitute_mpn": "ICM-42688-P","reason": "functional-equiv", "confidence": 0.80, "verified": True,  "notes": "ICM-42688-P has lower noise floor and better FIFO; different register map"},
    # MPU-6050 → MPU-6500 (pin-compatible)
    {"primary_mpn": "MPU-6050",  "substitute_mpn": "MPU-6500",   "reason": "pin-compatible",  "confidence": 0.95, "verified": True,  "notes": "Drop-in I2C/SPI replacement with improved gyro"},
    # AMS1117-3.3 → AP2112K-3.3TRG1 (lower IQ, better dropout)
    {"primary_mpn": "AMS1117-3.3","substitute_mpn":"AP2112K-3.3TRG1","reason":"functional-equiv","confidence":0.85,"verified":True,  "notes": "SOT-25 vs SOT-223; AP2112K has 50µA IQ vs 5mA"},
    # LDO alternatives
    {"primary_mpn": "AMS1117-3.3","substitute_mpn":"MCP1703A3302E/DB","reason":"functional-equiv","confidence":0.75,"verified":False,"notes":"250mA max vs 1A; better for low-power designs"},
    # TP4056 → MCP73831 (more control, similar function)
    {"primary_mpn": "TP4056",    "substitute_mpn":"MCP73831T-2ACI/OT","reason":"functional-equiv","confidence":0.80,"verified":True,  "notes": "Both 1A Li-Ion chargers; MCP73831 has prog current pin"},
    # TJA1051 → SN65HVD230 (3.3V CAN, same contract)
    {"primary_mpn": "TJA1051T/3","substitute_mpn": "SN65HVD230", "reason": "functional-equiv", "confidence": 0.80, "verified": False, "notes": "Both 3.3V CAN transceivers; different slope control pins"},
    # MAX485 → SP3485 (pin-compatible RS485)
    {"primary_mpn": "MAX485ECSA+","substitute_mpn":"SP3485EN-L/TR","reason":"pin-compatible",  "confidence": 0.95, "verified": True,  "notes": "Drop-in replacement; SP3485 has lower supply current"},
    # SSD1306 I2C/SPI — same chip different package
    {"primary_mpn": "SSD1306",   "substitute_mpn": "SH1106",     "reason": "functional-equiv", "confidence": 0.75, "verified": False, "notes": "SH1106 has 132×64 controller vs 128×64; needs offset"},
    # W25Q128 → W25Q64 (half size, pin-compatible)
    {"primary_mpn": "W25Q128JV", "substitute_mpn": "W25Q64JVSSIQ","reason":"pin-compatible",  "confidence": 0.90, "verified": True,  "notes": "8MB vs 16MB; identical SPI protocol and pin-out"},
    # SX1276 → RFM95W module (uses SX1276 internally)
    {"primary_mpn": "SX1276",    "substitute_mpn": "RFM95W",     "reason": "functional-equiv", "confidence": 0.85, "verified": True,  "notes": "RFM95W is a module with SX1276 + crystal + matching"},
    # CH340 variants
    {"primary_mpn": "CH340C",    "substitute_mpn": "CH340G",     "reason": "pin-compatible",  "confidence": 0.95, "verified": True,  "notes": "CH340G needs external crystal; CH340C has internal"},
    {"primary_mpn": "CH340C",    "substitute_mpn": "CP2102N",    "reason": "functional-equiv", "confidence": 0.80, "verified": True,  "notes": "CP2102N has better driver support and baud accuracy"},
    # USBLC6 → PRTR5V0U2X (same function, different footprint)
    {"primary_mpn": "USBLC6-2SC6","substitute_mpn":"PRTR5V0U2X","reason": "functional-equiv", "confidence": 0.80, "verified": False, "notes": "PRTR5V0U2X is SOT-363; USBLC6 is SOT-23-6; both USB ESD"},
]
