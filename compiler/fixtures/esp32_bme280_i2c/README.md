# Fixture: ESP32 + BME280 I2C Sensor

Minimal Eagle schematic for testing the boardsmith-fw CLI pipeline.

## Circuit Description

- **U1**: ESP32-WROOM-32 (MCU)
- **U2**: BME280 (temperature/humidity/pressure sensor, I2C)
- **R1, R2**: 4.7kΩ pull-up resistors on SDA/SCL
- **C1**: 100nF decoupling capacitor on BME280 VDD

## Connections

| Net  | U1 Pin         | U2 Pin | Notes                |
|------|---------------|--------|----------------------|
| SDA  | GPIO21/SDA    | SDA    | I2C data, 4.7k pull-up |
| SCL  | GPIO22/SCL    | SCL    | I2C clock, 4.7k pull-up |
| 3V3  | 3V3           | VDD, CSB | Power + I2C mode select |
| GND  | GND           | GND, SDO | Ground + I2C addr low bit |

BME280 I2C address: 0x76 (SDO=GND) or 0x77 (SDO=VDD).
This fixture ties SDO to GND → address 0x76.

## Usage

```bash
boardsmith-fw import fixtures/esp32_bme280_i2c/esp32_bme280.sch
boardsmith-fw analyze
boardsmith-fw research
boardsmith-fw generate --description "Read temperature, humidity, and pressure from BME280 every second" --lang c
boardsmith-fw build
```
