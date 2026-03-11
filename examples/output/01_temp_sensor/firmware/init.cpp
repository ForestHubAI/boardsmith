// Auto-generated peripheral initialization
#include "hardware.h"
#include <Arduino.h>


// --- ESP32 Wi-Fi+BT Module initialization ---
static void init_ESP32_WROOM_32() {
    // Phase: reset
    delay(100);
    // Phase: configure
}

// --- BME280 Pressure/Humidity/Temperature Sensor initialization ---
static void init_BME280() {
    // Phase: reset
    delay(2);
    // Write 0xE0 = 0xB6 — Soft reset
    _i2c_write(I2C_ADDR_BME280, 0xE0, 0xB6);
    // Phase: verify
    // Read 0xD0, expect 0x60 — chip_id expect 0x60
    _i2c_verify(I2C_ADDR_BME280, 0xD0, 0x60);
    // Phase: configure
    // Write 0xF2 = 0x01 — ctrl_hum: oversampling x1
    _i2c_write(I2C_ADDR_BME280, 0xF2, 0x01);
    // Write 0xF4 = 0x27 — ctrl_meas: temp x1, press x1, normal
    _i2c_write(I2C_ADDR_BME280, 0xF4, 0x27);
    // Write 0xF5 = 0xA0 — config: standby 1000ms, filter off
    _i2c_write(I2C_ADDR_BME280, 0xF5, 0xA0);
}

// I2C helpers
static void _i2c_write(uint8_t addr, uint8_t reg, uint8_t val) {
    Wire.beginTransmission(addr);
    Wire.write(reg);
    Wire.write(val);
    Wire.endTransmission();
}

static uint8_t _i2c_read(uint8_t addr, uint8_t reg) {
    Wire.beginTransmission(addr);
    Wire.write(reg);
    Wire.endTransmission(false);
    Wire.requestFrom(addr, (uint8_t)1);
    return Wire.read();
}

static bool _i2c_verify(uint8_t addr, uint8_t reg, uint8_t expected) {
    uint8_t val = _i2c_read(addr, reg);
    if (val != expected) {
        Serial.printf("Verify failed: addr=0x%02X reg=0x%02X got=0x%02X expected=0x%02X\n",
                      addr, reg, val, expected);
        return false;
    }
    return true;
}

void init_all_peripherals() {
    init_ESP32_WROOM_32();
    init_BME280();
}
