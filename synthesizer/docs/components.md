# Bauteil-Bibliothek — Vollständige Übersicht

> **212 Bauteile** · Stand 2026-03-07 · Letzter vollständiger Audit: 2026-03-07
>
> **Quellen:**
> - `shared/knowledge/boardsmith.db` — 202 Einträge (vollständige Metadaten, Beschaffung, Ratings)
> - `synthesizer/synth_core/knowledge/symbol_map.py` — 90 Einträge mit KiCad-Symbol + verifizierten Pin-Nummern
> - **212 eindeutige Bauteile total** (80 in beiden Quellen, 122 nur DB, 10 nur KiCad)
>
> **Letzter Audit:** 6 kritische Pin-Fehler behoben (SN65HVD230, ADUM1201ARZ, TXS0102, FT232RL, INA219), 10 neue DB-Einträge, Pakete korrigiert (INA219/INA226/MCP9808/SSD1306)
>
> **Legende:** ✅ = KiCad-Symbol vorhanden (schaltplanfähig) · 📋 = nur Datenbank (kein Symbol)

---

## Inhaltsverzeichnis

1. [MCUs](#1-mcus) — 21
2. [Sensoren](#2-sensoren) — 40
3. [Kommunikation](#3-kommunikation) — 32
4. [Stromversorgung](#4-stromversorgung) — 31
5. [Aktoren & Treiber](#5-aktoren--treiber) — 16
6. [Display & Audio](#6-display--audio) — 10
7. [Speicher](#7-speicher) — 8
8. [Steckverbinder](#8-steckverbinder) — 11
9. [Analog & Logik](#9-analog--logik) — 8
10. [Passive Bauteile](#10-passive-bauteile) — 12
11. [Sonstige](#11-sonstige) — 16

---

## 1. MCUs

| MPN | Hersteller | Beschreibung | Package | Vdd | ✅ |
|-----|-----------|-------------|---------|-----|---|
| `ATmega328P` | Microchip | 8-bit AVR 20MHz, 32KB flash, 2KB SRAM — Arduino Uno | DIP-28 | 1.8–5.5V | 📋 |
| `ATmega328P-AU` | Microchip | 8-bit AVR 20MHz, 32KB flash, 2KB SRAM, Arduino Uno/Nano core | TQFP-32 | 1.8–5.5V | ✅ |
| `ATmega2560-16AU` | Microchip | 8-bit AVR 16MHz, 256KB flash, 8KB SRAM, 86 I/O, Arduino Mega | TQFP-100 | 4.5–5.5V | ✅ |
| `ATSAME51J20A-AU` | Microchip | ARM Cortex-M4F 120MHz, 1MB flash, 256KB SRAM, CAN-FD, dual DAC | TQFP-64 | 1.71–3.63V | 📋 |
| `ESP32-C3-MINI-1` | Espressif | RISC-V 160MHz, Wi-Fi+BLE5, 4MB flash, ultra-low cost | SMD 13×16.6mm | 3.0–3.6V | 📋 |
| `ESP32-C3-WROOM-02` | Espressif | RISC-V 160MHz, Wi-Fi+BLE5, 4MB flash | SMD module | 3.0–3.6V | ✅ |
| `ESP32-S3-WROOM-1` | Espressif | Dual-core LX7 240MHz, Wi-Fi+BLE5, 8MB flash, USB OTG, AI | SMD module | 3.0–3.6V | ✅ |
| `ESP32-WROOM-32` | Espressif | Dual-core LX6 240MHz, Wi-Fi+BT, 4MB flash | SMD module | 3.0–3.6V | ✅ |
| `LPC55S69JBD100` | NXP | Dual ARM Cortex-M33 150MHz, TrustZone, PUF, CASPER crypto | LQFP-100 | 1.71–3.6V | ✅ |
| `MIMXRT1062DVJ6A` | NXP | ARM Cortex-M7 600MHz, 1MB SRAM, kein internes Flash | BGA-196 | 2.97–3.63V | ✅ |
| `R7FA4M2AD3CFP` | Renesas | ARM Cortex-M33 100MHz, 512KB flash, TrustZone, kapazitives Touch | LQFP-100 | 1.6–5.5V | 📋 |
| `RP2040` | Raspberry Pi | Dual-core Cortex-M0+ 133MHz, 264KB SRAM, PIO | QFN-56 | 1.8–3.6V | ✅ |
| `STM32F103C8T6` | ST | ARM Cortex-M3 72MHz, 64KB flash, 20KB SRAM | LQFP-48 | 2.0–3.6V | ✅ |
| `STM32F405RGT6` | ST | ARM Cortex-M4 168MHz, 1MB flash, 192KB SRAM, FPU, USB OTG, I2S | LQFP-64 | 1.8–3.6V | ✅ |
| `STM32F411CEU6` | ST | ARM Cortex-M4F 100MHz, 512KB flash, 128KB SRAM, USB FS | UFQFPN-48 | 1.7–3.6V | 📋 |
| `STM32F746ZGT6` | ST | ARM Cortex-M7 216MHz, 1MB flash, 340KB SRAM, Ethernet MAC | LQFP-144 | 1.7–3.6V | ✅ |
| `STM32G431CBU6` | ST | ARM Cortex-M4F 170MHz, 128KB flash, CORDIC, Motor-Control-Timer | QFN-32 | 1.71–3.6V | ✅ |
| `STM32H743VIT6` | ST | ARM Cortex-M7 480MHz, 2MB flash, 1MB SRAM, Ethernet, USB HS | LQFP-100 | 1.62–3.6V | ✅ |
| `STM32L476RGT6` | ST | ARM Cortex-M4F 80MHz, 1MB flash, Ultra-Low-Power 28µA/MHz | LQFP-64 | 1.71–3.6V | ✅ |
| `XMC4700F144K2048` | Infineon | ARM Cortex-M4F 144MHz, 2MB flash, EtherCAT, Delta-Sigma | LQFP-144 | 3.13–3.63V | 📋 |
| `nRF52840` | Nordic | ARM Cortex-M4F 64MHz, BLE 5.3, 802.15.4, USB, 1MB flash | AQFN-94 | 1.7–3.6V | ✅ |

---

## 2. Sensoren

### 2.1 Temperatur & Feuchtigkeit

| MPN | Hersteller | Beschreibung | Package | Interface | ✅ |
|-----|-----------|-------------|---------|-----------|---|
| `AHT20` | ASAIR | Kalibrierter Feuchte+Temp-Sensor | LCC-6 | I2C | ✅ |
| `AM2302` | Aosong | Digitaler Temp+Feuchte-Sensor, Single-Wire | 4-pin | 1-Wire | 📋 |
| `BME280` | Bosch | Feuchte + Temp + Luftdruck | LGA-8 | I2C/SPI | ✅ |
| `BME680` | Bosch | Temp + Druck + Feuchte + VOC Gas | LGA-8 | I2C/SPI | 📋 |
| `BMP280` | Bosch | Luftdruck + Temp (ohne Feuchte) | LGA-8 | I2C/SPI | ✅ |
| `DS18B20` | Maxim | 1-Wire Digitalthermometer, -55 bis +125°C | TO-92 | 1-Wire | ✅ |
| `MAX31855KASA+` | Maxim | K-Typ Thermoelement-Verstärker, -200 bis +1350°C, 0.25°C | SOIC-8 | SPI | 📋 |
| `MAX31865ATP+` | Analog Devices | PT100/PT1000 RTD Interface, 15-Bit, 0.03125°C | TQFN-20 | SPI | ✅ |
| `MAX6675ISA+` | Analog Devices | K-Typ Thermoelement-zu-Digital, 12-Bit, 0–1024°C | SOIC-8 | SPI | ✅ |
| `MCP9808` | Microchip | Hochgenau ±0.25°C I2C Temperatursensor | SOT-23-5 | I2C | ✅ |
| `MLX90614ESF` | Melexis | Kontaktloser IR-Thermometer, -70 bis +380°C, ±0.5°C | TO-39 | I2C | 📋 |
| `SHT31-DIS` | Sensirion | Digitalfühler Feuchte ±2%RH + Temp ±0.3°C | DFN-8 | I2C | 📋 |
| `SHTC3` | Sensirion | Ultra-Low-Power Feuchte ±2%RH + Temp ±0.2°C | DFN-4 | I2C | ✅ |

### 2.2 Bewegung & IMU

| MPN | Hersteller | Beschreibung | Package | Interface | ✅ |
|-----|-----------|-------------|---------|-----------|---|
| `ADXL345` | Analog Devices | 3-Achsen Beschleunigung, 13-Bit, ±16g | LGA-14 | I2C/SPI | 📋 |
| `BNO055` | Bosch | 9-Achsen Absolut-Orientierung mit integrierter Sensorfusion | LGA-28 | I2C | 📋 |
| `ICM-42688-P` | TDK InvenSense | 6-Achsen IMU ±16g / ±2000dps, 20-Bit FIFO | LGA-14 | I2C/SPI | ✅ |
| `LIS3DH` | ST | Ultra-Low-Power 3-Achsen MEMS Beschleunigung, ±2/4/8/16g | LGA-16 | I2C/SPI | 📋 |
| `LSM6DSO` | ST | 6-Achsen IMU mit Machine-Learning-Core | LGA-14 | I2C/SPI | 📋 |
| `MPU-6050` | InvenSense | 6-Achsen IMU (Gyro + Accel) mit DMP | QFN-24 | I2C | ✅ |

### 2.3 Strom & Spannung

| MPN | Hersteller | Beschreibung | Package | Interface | ✅ |
|-----|-----------|-------------|---------|-----------|---|
| `ACS712ELCTR-05B-T` | Allegro | ±5A Hall-Effekt Stromsensor, 185mV/A, analog | SOIC-8 | Analog | 📋 |
| `ACS712ELCTR-20A-T` | Allegro | Hall-Effekt Stromsensor ±20A, 100mV/A | SOIC-8 | Analog | 📋 |
| `ADS1115` | TI | 16-Bit 4-Kanal Delta-Sigma ADC mit PGA | MSOP-10 | I2C | 📋 |
| `ADS8681` | TI | 16-Bit 1MSPS SAR ADC, ±10V/±5V, SPI | TSSOP-16 | SPI | ✅ |
| `INA219` | TI | High-Side Strom/Leistungsmonitor, 26V max | SOT-23-8 | I2C | ✅ |
| `INA226` | TI | 36V 16-Bit Strom/Spannung/Leistung, ±0.1% | SOT-23-10 | I2C | ✅ |
| `INA128UA` | TI | Präzisions-Instrumentenverstärker, 120dB CMRR, für Brückensensoren | SOIC-8 | Analog | 📋 |

### 2.4 Distanz & Licht

| MPN | Hersteller | Beschreibung | Package | Interface | ✅ |
|-----|-----------|-------------|---------|-----------|---|
| `APDS-9960` | Broadcom | Annäherung + Umgebungslicht + RGB + Geste | LCC-6 | I2C | 📋 |
| `BH1750` | ROHM | 16-Bit Umgebungslichtsensor, 1–65535 lux | WSOF-6I | I2C | 📋 |
| `BH1750FVI` | ROHM | Digitaler Lichtsensor, 1–65535 lux | WSOF-6I | I2C | 📋 |
| `HC-SR04` | Generic | Ultraschall-Distanzsensor, 2–400cm, TRIG/ECHO | Modul | GPIO | ✅ |
| `TSL2561` | AMS | Licht-zu-Digital, 0.1–40000 lux | CHIPLT-6 | I2C | 📋 |
| `VL53L0X` | ST | 940nm Laser ToF Distanzsensor, bis 2m | LCC-12 | I2C | ✅ |

### 2.5 Sonstige Sensoren

| MPN | Hersteller | Beschreibung | Package | Interface | ✅ |
|-----|-----------|-------------|---------|-----------|---|
| `AS5600-ASOM` | ams-OSRAM | 12-Bit Magnetischer Drehgeber, kontaktlos | SOIC-8 | I2C/PWM | ✅ |
| `HX711` | Avia Semiconductor | 24-Bit ADC für Wägezellen und Kraftsensoren | SOP-16 | SPI-like | 📋 |
| `MAX30102` | Maxim | Pulsoxymetrie + Herzfrequenz-Biosensor | OLGA-14 | I2C | 📋 |
| `MPR121QR2` | NXP | 12-Elektroden kapazitives Touch mit Proximity | QFN-20 | I2C | 📋 |
| `NEO-6M` | u-blox | GPS-Empfänger-Modul, 50-Kanal, 1Hz, NMEA | SMD Modul | UART | 📋 |
| `SCD41` | Sensirion | Photoakustischer CO2-Sensor 400–5000ppm ±40ppm | SMD Modul | I2C | 📋 |
| `TLE4913` | Infineon | Unipolarer Hall-Effekt-Latch, 3–24V, für RPM | SOT-23 | Digital | 📋 |
| `WM8731` | Wolfson | Stereo Audio Codec mit Kopfhörertreiber, ADC+DAC | QFN-28 | I2S/I2C | ✅ |
| `MAX98357A` | Maxim | 3.2W Class-D I2S Mono-Verstärker, kein MCLK | TDFN-16 | I2S | ✅ |

---

## 3. Kommunikation

### 3.1 RS-485 / RS-422

| MPN | Hersteller | Beschreibung | Package | Vdd | ✅ |
|-----|-----------|-------------|---------|-----|---|
| `MAX485` | Maxim | Half-Duplex RS-485/RS-422, 2.5Mbps, 5V | SOIC-8 | 4.75–5.25V | ✅ |
| `MAX485ESA+` | Maxim | Half-Duplex RS-485/RS-422, 2.5Mbps, Low-Power | SOIC-8 | 4.75–5.25V | 📋 |
| `SP3485EN` | MaxLinear | 3.3V RS-485, 10Mbps, 500µA, ESD ±15kV | SOIC-8 | 3.0–3.6V | ✅ |
| `SP3485EN-L/TR` | Sipex/MaxLinear | 3.3V RS-485, 10Mbps, pin-kompatibel MAX485 | SOIC-8 | 3.0–3.6V | 📋 |

### 3.2 CAN-Bus

| MPN | Hersteller | Beschreibung | Package | Vdd | ✅ |
|-----|-----------|-------------|---------|-----|---|
| `ISO1042BQDWRQ1` | TI | Isolierter CAN-FD Transceiver, 5kVrms, 5Mbps, AEC-Q100 | SOIC-16W | 4.5–5.5V | 📋 |
| `MCP2515` | Microchip | Stand-alone CAN Controller mit SPI, bis 1Mbps | DIP-18 | 2.7–5.5V | 📋 |
| `MCP2562FD-E/SN` | Microchip | CAN-FD Transceiver, 8Mbps, 3.3V I/O, AEC-Q100 | SOIC-8 | 4.5–5.5V | 📋 |
| `SN65HVD230` | TI | 3.3V CAN-Bus Transceiver, bis 1Mbps | SOIC-8 | 3.0–3.6V | ✅ |
| `TCAN1042VDRQ1` | TI | CAN-FD Transceiver 5Mbps, 3.3V, AEC-Q100, ±58V Fehlertoleranz | SOIC-8 | 4.5–5.5V | ✅ |
| `TJA1051T/3` | NXP | 3.3V CAN Transceiver, ISO 11898-2, 5Mbps | SOIC-8 | 4.5–5.5V | 📋 |

### 3.3 USB-UART-Brücken

| MPN | Hersteller | Beschreibung | Package | Vdd | ✅ |
|-----|-----------|-------------|---------|-----|---|
| `CH340G` | WCH | USB 2.0 FS zu UART, 2Mbaud, günstigste Option | SOP-16 | 3.3–5.0V | ✅ |
| `CP2102N` | Silicon Labs | USB 2.0 FS zu UART, 3Mbaud, kein externes Quarz | QFN-28 | 3.0–3.6V | 📋 |
| `CP2102N-A02-GQFN28R` | Silicon Labs | USB zu UART, bis 3Mbps, integrierter 5V-Regler | QFN-28 | 3.0–5.0V | 📋 |
| `FT232RL` | FTDI | USB 2.0 FS zu UART, 3Mbaud, EEPROM für VID/PID | SSOP-28 | 3.3–5.25V | ✅ |

### 3.4 Ethernet & WLAN

| MPN | Hersteller | Beschreibung | Package | Vdd | ✅ |
|-----|-----------|-------------|---------|-----|---|
| `ENC28J60` | Microchip | 10Base-T Ethernet-Controller, SPI, 8KB Puffer | SSOP-28 | 3.1–3.5V | 📋 |
| `KSZ8081RNAIA` | Microchip | 10/100 Ethernet PHY, RMII, 3.3V, Industrietemp | QFN-32 | 3.0–3.6V | 📋 |
| `LAN8720A` | Microchip | 10/100 Ethernet PHY mit RMII, Auto MDI/MDI-X | QFN-24 | 3.0–3.6V | ✅ |
| `W5500` | WIZnet | Hardwired TCP/IP, 8 Sockets, 80MHz SPI | LQFP-48 | 3.0–3.6V | ✅ |

### 3.5 Funk / Drahtlos

| MPN | Hersteller | Beschreibung | Package | Vdd | ✅ |
|-----|-----------|-------------|---------|-----|---|
| `CC1101` | TI | Sub-1GHz RF Transceiver, 315/433/868/915MHz | QLP-20 | 1.8–3.6V | 📋 |
| `HC-05` | Generic | Bluetooth 2.0+EDR Serial-Modul, SPP, AT-Commands | SMD Modul | 3.1–4.2V | 📋 |
| `NEO-M8N` | u-blox | M8 GNSS Modul (GPS+GLONASS+BeiDou+Galileo) | SMD Modul | 1.71–1.89V | ✅ |
| `RFM95W` | HopeRF | LoRa Modul 868/915MHz, +20dBm, -148dBm | SMD Modul | 1.8–3.7V | ✅ |
| `SIM800L` | SIMCom | GSM/GPRS Modul, UART AT-Commands | Modul | 3.4–4.4V | ✅ |
| `SIM7600G-H` | SIMCom | LTE Cat-4/3G/2G Multi-Band mit GNSS, UART | SMD Modul | 3.4–4.2V | ✅ |
| `SX1276` | Semtech | 137–1020MHz LoRa/FSK Transceiver | QFN-28 | 1.8–3.7V | ✅ |
| `nRF24L01+` | Nordic | 2.4GHz ISM Transceiver mit Enhanced ShockBurst | QFN-20 | 1.9–3.6V | 📋 |

### 3.6 Isolation & Pegelwandlung

| MPN | Hersteller | Beschreibung | Package | Vdd | ✅ |
|-----|-----------|-------------|---------|-----|---|
| `ADUM1201ARZ` | Analog Devices | Dual Digital-Isolator, 25Mbps, 2.5kVrms | SOIC-8 | 2.7–5.5V | ✅ |
| `ADuM1201ARZ` | Analog Devices | Dual iCoupler, 2.5kVrms, 100Mbps, bidirektional | SOIC-8 | 2.7–5.5V | 📋 |
| `ADUM3160BRWZ` | Analog Devices | USB 2.0 Full-Speed Isolator, 5kV | SOIC-16W | 4.5–5.5V | 📋 |
| `BSS138` | ON Semi | N-Kanal MOSFET Pegelwandler, SOT-23 | SOT-23 | bis 20V | ✅ |
| `PRTR5V0U2X` | Nexperia | ESD/TVS für USB D+/D-, 0.35pF | SOT-363 | bis 5.5V | 📋 |
| `TCA9548A` | TI | 8-Kanal I2C-Multiplexer mit aktivem Reset | TSSOP-24 | 1.65–5.5V | ✅ |
| `TXB0104` | TI | 4-Bit bidirektionaler Pegelwandler, TSSOP-14 | TSSOP-14 | 1.2–5.5V | ✅ |
| `TXS0102` | TI | 2-Bit bidirektionaler Pegelwandler, VSSOP-8 | VSSOP-8 | 1.65–5.5V | ✅ |
| `TXS0108EPWR` | TI | 8-Bit auto-dir. Pegelwandler, 100Mbps | TSSOP-20 | 1.2–5.5V | 📋 |

---

## 4. Stromversorgung

### 4.1 LDO-Regler

| MPN | Hersteller | Beschreibung | Package | Vin max | Vout | Imax | ✅ |
|-----|-----------|-------------|---------|---------|------|------|----|
| `AMS1117-3.3` | AMS | 3.3V LDO, 1.1V Dropout, sehr verbreitet | SOT-223 | 15V | 3.3V | 800mA | ✅ |
| `AMS1117-5.0` | AMS | 5.0V LDO, 12V→5V Zwischenrail | SOT-223 | 15V | 5.0V | 800mA | ✅ |
| `AP2112K-3.3` | Diodes Inc | 3.3V LDO, 300mV Dropout, 55µA Quiescent | SOT-25 | 6V | 3.3V | 600mA | ✅ |
| `AP2112K-3.3TRG1` | Diodes Inc | 3.3V LDO Tape-&-Reel Variante | SOT-25 | 6V | 3.3V | 600mA | ✅ |
| `LM2940CT-3.3` | TI | 3.3V LDO, 26V max Input, 24V Industrieanwendungen | TO-220-3 | 26V | 3.3V | 1A | ✅ |
| `MCP1700-3302E` | Microchip | 3.3V Ultra-Low-Power LDO, 1.6µA Quiescent | SOT-23 | 6V | 3.3V | 250mA | ✅ |
| `TPS7A2033DBVR` | TI | Ultra-Low-Noise 4.4µVrms 200mA LDO, für ADC/RF | SOT-23-5 | 5.5V | 3.3V | 200mA | 📋 |

### 4.2 Buck-Konverter

| MPN | Hersteller | Beschreibung | Package | Vin | Imax | ✅ |
|-----|-----------|-------------|---------|-----|------|----|
| `LM2596S-3.3` | TI | 3A Stepdown, 3.3V fest, 4.5–40V | TO-263-5 | 40V | 3A | 📋 |
| `LM2596S-5.0` | TI | 3A Stepdown, 5V fest, 4.5–40V | TO-263-5 | 40V | 3A | 📋 |
| `LM5164DDAR` | TI | 42V 1A Sync-Buck, integrierte FETs, 93% | SOIC-8 | 42V | 1A | 📋 |
| `MP1584EN` | MPS | 3A Sync-Buck, 4.5–28V, einstellbar | SOIC-8 | 28V | 3A | ✅ |
| `MP2307DN` | MPS | 3A Sync-Buck, 4.75–23V, 340kHz | SOIC-8 | 23V | 3A | ✅ |
| `TPS563200` | TI | 3A Sync-Buck, 4.3–17V, SOT-23-6 | SOT-23-6 | 17V | 3A | ✅ |
| `XL4016E1` | XLSEMI | 8A Stepdown, 8–40V, für High-Current Lasten | TO-220-5 | 40V | 8A | 📋 |

### 4.3 Boost-Konverter

| MPN | Hersteller | Beschreibung | Package | Vout max | Imax | ✅ |
|-----|-----------|-------------|---------|----------|------|----|
| `MT3608` | Aerosemi | 2A Stepup, 2–24V In, bis 28V Out, für LiPo→5V | SOT-23-6 | 28V | 2A | 📋 |

### 4.4 Akkumanagement

| MPN | Hersteller | Beschreibung | Package | Chemie | ✅ |
|-----|-----------|-------------|---------|--------|---|
| `BQ24075RGTR` | TI | 1.5A Li-Ion Lader mit Power-Path, USB-Strombegrenzung | QFN-16 | Li-Ion | 📋 |
| `DW01A-G` | Fortune | 1S Li-Ion Schutz: Überladung/Tiefentladung/Überstrom | SOT-23-6 | Li-Ion | 📋 |
| `FS8205A` | Fortune | Dual N-FET für Li-Ion Schutz, Rds(on) 24mΩ | TSSOP-8 | — | 📋 |
| `IP5306` | INJOINIC | Power-Bank IC: 5V/2.4A Boost + LiPo Lader + Fuel Gauge + LEDs | SOP-8 | Li-Ion | 📋 |
| `MAX17048G+T` | Maxim | 1-Zell LiPo Fuel Gauge, ModelGauge, 3µA Quiescent | DFN-8 | Li-Ion | ✅ |
| `MCP73831T-2ATI` | Microchip | 500mA Li-Ion/LiPo Laderegler, programmierbar | SOT-23-5 | Li-Ion | ✅ |
| `TP4056` | NanjingTopPower | 1A Standalone Li-Ion Lader | SOP-8 | Li-Ion | ✅ |

### 4.5 Schutz & Sonstiges

| MPN | Hersteller | Beschreibung | Package | ✅ |
|-----|-----------|-------------|---------|---|
| `DLW21HN900SQ2L` | Murata | Common Mode Choke 90Ω@100MHz, 300mA, EMC | 0805 | 📋 |
| `LM74610DGKR` | TI | Ideal-Dioden-Controller, 0 Quiescent, für Verpolungsschutz | VSSOP-8 | 📋 |
| `LTC4359ITS8-TRMPBF` | Analog Devices | Ideal-Dioden-Controller, 3.5–36V, ersetzt Schottky-Diode | TSOT-23-8 | 📋 |
| `MF-MSMF050-2` | Bourns | PTC Sicherung 500mA/1A, 15V, rückstellbar | 1812 | 📋 |
| `PESD3V3S2UT` | Nexperia | Dual-ESD Schutz 3.3V I/O, 1.5pF | SOT-23 | 📋 |
| `PESD5V0S2BT` | Nexperia | Dual-ESD Schutz USB, 5V, <0.5pF, IEC 61000-4-2 | SOT-23 | 📋 |
| `SMAJ24CA` | Littelfuse | 24V bidirektionale TVS, 400W, für 24V Industriebus | DO-214AC | 📋 |
| `SMBJ24CA` | Littelfuse | 24V bidirektionale TVS, 600W | SMB | 📋 |
| `TPS22918DBVR` | TI | 5.5V/2A Load Switch, 52mΩ Rds, für Power-Gating | SOT-23-6 | 📋 |
| `TPS3840DL33DBVR` | TI | Nano-Power Spannungsüberwacher 3.3V, Reset-Generator | SOT-23-5 | 📋 |
| `USBLC6-2SC6` | ST | USB ESD-Schutz, 6V VBUS, 1.5pF, IEC 61000-4-2 | SOT-23-6 | 📋 |

---

## 5. Aktoren & Treiber

| MPN | Hersteller | Beschreibung | Package | Imax | ✅ |
|-----|-----------|-------------|---------|------|----|
| `2N2222A` | ON Semi | NPN BJT 600mA 40V, GPIO-Schalter/PWM | TO-92 | 600mA | 📋 |
| `A4988` | Allegro | DMOS Microstepping Bipolarer Schrittmotor-Treiber, 2A, 35V | QFN-28 | 2A | 📋 |
| `AO3400A` | Alpha & Omega | N-Kanal MOSFET 30V/5.7A, Logic-Level 2.5V, Low-Side | SOT-23 | 5.7A | 📋 |
| `DRV8825` | TI | Bipolarer Schrittmotor-Treiber, 2.5A, 45V, bis 1/32 Microstepping | HTSSOP-28 | 2.5A | 📋 |
| `DRV8833` | TI | Dual H-Brücke, 2.7–10.8V, 1.5A/Brücke | HTSSOP-16 | 1.5A | ✅ |
| `IRF540N` | Infineon | N-Kanal MOSFET 100V/33A, für Hochstrom/Motoren/Heizung | TO-220 | 33A | 📋 |
| `IRLML6244TRPBF` | Infineon | Logic-Level N-FET 20V/6.3A, Vgs_th=0.9V | SOT-23 | 6.3A | 📋 |
| `IRLZ44N` | Vishay | N-Kanal Logic-Level MOSFET 55V/47A | TO-220 | 47A | ✅ |
| `LTST-C150GKT` | Lite-On | Standard grüne LED 20mA, Vf≈2.1V, 0603 | 0603 | 20mA | 📋 |
| `MAX98357AETE+T` | Maxim | 3.2W Class-D Mono Verstärker mit I2S, kein MCLK | TQFN-16 | — | 📋 |
| `PCA9685` | NXP | 16-Kanal 12-Bit PWM I2C LED/Servo-Controller | TSSOP-28 | — | 📋 |
| `PCM5102APWR` | TI | Stereo Audio DAC, I2S, 32-Bit/384kHz, -100dB THD+N | TSSOP-20 | — | 📋 |
| `SKRPACE010` | Alps | 6mm Taktschalter, 50mA, SMD, 260gf | SMD-4PIN | 50mA | 📋 |
| `TB6612FNG` | Toshiba | Dual H-Brücke DC-Motor, 1.2A/3.2A Peak | SSOP-24 | 1.2A | ✅ |
| `TLP281-4` | Toshiba | Quad Phototransistor-Optokoppler, 3750Vrms | SOP-16 | — | 📋 |
| `ULN2003A` | TI | 7-Kanal Darlington-Array, 500mA/Kanal | SOIC-16 | 500mA | ✅ |

---

## 6. Display & Audio

| MPN | Hersteller | Beschreibung | Package | Interface | ✅ |
|-----|-----------|-------------|---------|-----------|---|
| `HT16K33` | Holtek | 16×8 LED Controller mit I2C und Keyscan | SOP-28 | I2C | 📋 |
| `ILI9341` | Ilitek | 262K Farb-TFT 240×320 LCD-Treiber | COG Modul | SPI | 📋 |
| `MAX7219` | Maxim | 8-Digit LED-Treiber, SPI, kaskadierbar | DIP-24 | SPI | ✅ |
| `PCM5102APWR` | TI | Stereo Audio DAC I2S, 32-Bit/384kHz | TSSOP-20 | I2S | 📋 |
| `SH1106` | Sino Wealth | 132×64 OLED/PLED Segment-Treiber (SSD1306-ähnlich) | COG Modul | I2C/SPI | 📋 |
| `SSD1306` | Solomon Systech | 128×64 Monochrom OLED-Treiber | COG Modul | I2C/SPI | ✅ |
| `ST7735S` | Sitronix | 262K Farb-TFT 128×160 LCD-Treiber, SPI | COG Modul | SPI | ✅ |
| `ST7789V` | Sitronix | 262K Farb-TFT 240×320 LCD-Treiber, SPI | COG Modul | SPI | 📋 |
| `TM1637` | Titan Micro | 4-Digit 7-Segment LED-Treiber, 2-Wire (CLK+DIO) | SOP-20 | 2-Wire | 📋 |
| `UC8151C` | Ultrachip | 2.13" E-Ink 250×122 Display-Treiber, SPI | COG Modul | SPI | 📋 |

---

## 7. Speicher

| MPN | Hersteller | Beschreibung | Package | Kapazität | Interface | ✅ |
|-----|-----------|-------------|---------|----------|-----------|---|
| `23LC1024` | Microchip | 1Mbit (128KB) SPI SRAM, flüchtig, sofortiges Schreiben | SOIC-8 | 128KB | SPI | 📋 |
| `AT24C256` | Microchip | 256Kbit (32KB) I2C EEPROM | SOIC-8 | 32KB | I2C | 📋 |
| `AT24C32` | Microchip | 32Kbit (4KB) I2C EEPROM | SOIC-8 | 4KB | I2C | 📋 |
| `CY15B104Q` | Infineon | 4Mbit SPI FRAM, 10^14 Zyklen, für Datenlogging | SOIC-8 | 512KB | SPI | 📋 |
| `FM25V10-G` | Infineon | 1Mbit SPI FRAM, 40MHz, kein Verschleiß | SOIC-8 | 128KB | SPI | 📋 |
| `IS25LP128F` | ISSI | 128Mbit SPI NOR Flash, Quad-SPI, 133MHz, Industrietemperatur | SOIC-8 | 16MB | QSPI | 📋 |
| `MICROSD-SLOT-SPI` | Generic | Push-Push MicroSD Karten-Slot, SPI | SMD-8 | variabel | SPI | ✅ |
| `W25Q128JV` | Winbond | 128Mbit (16MB) SPI NOR Flash | SOIC-8 | 16MB | SPI | ✅ |

---

## 8. Steckverbinder

| MPN | Hersteller | Beschreibung | Package | ✅ |
|-----|-----------|-------------|---------|---|
| `B2B-PH-K-S` | JST | JST-PH 2-Pin, 2mm, Standard LiPo Akkustecker | THT-2PIN | 📋 |
| `B4B-XH-A` | JST | JST-XH 4-Pin, 2.5mm, Board-to-Board | THT-4PIN | 📋 |
| `CONN-ANT-UFL` | Generic | U.FL/IPEX HF-Antennenstecker 50Ω, koaxial | SMD | ✅ |
| `CONN-CAN-2PIN` | Generic | 2-Pin 5.08mm Schraubklemme für CAN-Bus (CANH/CANL) | THT | ✅ |
| `CONN-JTAG-2x10` | Generic | JTAG 2×10 2.54mm Debug-Header | THT | ✅ |
| `CONN-M12-4PIN` | Generic | M12 4-Pin A-codiert, IP67, Industriesensor-Standard | Panel-mount | 📋 |
| `CONN-RS485-2PIN` | Generic | 2-Pin 5.08mm Schraubklemme für RS-485 (A/B) | THT | ✅ |
| `CONN-SCREW-3PIN-508` | Generic | 3-Pin 5.08mm Schraubklemme, 24V Industrieeingang | THT-3PIN | 📋 |
| `CONN-SWD-2x5` | Generic | ARM SWD 2×5 1.27mm Debug-Header | THT | ✅ |
| `CONN-UART-4PIN` | Generic | 4-Pin 2.54mm UART-Header (VCC/GND/TX/RX) | THT | ✅ |
| `HR911105A` | Hanrun | RJ45 mit integrierten Magneten + LEDs (Link/Activity) | THT-RJ45 | 📋 |
| `USB-C-CONN` | Generic | USB-C Buchse (GCT USB4085), SMD | SMD | ✅ |

---

## 9. Analog & Logik

| MPN | Hersteller | Beschreibung | Package | Vdd | ✅ |
|-----|-----------|-------------|---------|-----|---|
| `CD74HC4051E` | TI | 8-Kanal Analog-Mux/Demux, 3 Selektionsleitungen | DIP-16 | 2.0–6.0V | 📋 |
| `LM358` | TI | Dual Op-Amp, 3–32V Single-Supply | SOIC-8 | 3.0–32V | 📋 |
| `LM393` | TI | Dual Spannungskomparator, Open-Collector | SOIC-8 | 2.0–36V | 📋 |
| `LM4040` | TI | Präzisions 2.5V Shunt-Spannungsreferenz, ±0.1% | SOT-23-3 | 2.5–36V | 📋 |
| `MCP4725` | Microchip | 12-Bit Single-Channel DAC mit I2C und EEPROM | SOT-23-6 | 2.7–5.5V | 📋 |
| `MCP4725A0T-E/OT` | Microchip | 12-Bit DAC mit I2C und NV-EEPROM | SOT-23-6 | 2.7–5.5V | 📋 |
| `MCP6002` | Microchip | Dual Rail-to-Rail Op-Amp, 1.8–6V, 1MHz GBW | SOT-23-8 | 1.8–6V | 📋 |
| `SN74HC595N` | TI | 8-Bit Seriell-zu-Parallel Schieberegister, Daisychain | DIP-16 | 2.0–6.0V | 📋 |

---

## 10. Passive Bauteile

### Widerstände

| MPN | Beschreibung | Package | Wert | ✅ |
|-----|-------------|---------|------|---|
| `RC0402FR-07100RL` | Gate/Serien-Widerstand | 0402 | 100Ω 1% | ✅ |
| `RC0402FR-07470RL` | UART Serienschutz | 0402 | 470Ω 1% | ✅ |
| `RC0402FR-074K7L` | I2C Pull-up | 0402 | 4.7kΩ 1% | ✅ |

### Kondensatoren

| MPN | Beschreibung | Package | Wert | ✅ |
|-----|-------------|---------|------|---|
| `GRM155R71C104KA88D` | Entkopplungs-Kondensator | 0402 | 100nF 16V X7R | ✅ |
| `GRM188R61A106KE69D` | Bulk-Kondensator | 0603 | 10µF 10V X5R | ✅ |

### Ferrite & EMC

| MPN | Hersteller | Beschreibung | Package | ✅ |
|-----|-----------|-------------|---------|---|
| `BLM18BD102SN1D` | Murata | 1kΩ@100MHz Ferritperle, 500mA, Netzteilfilter | 0603 | 📋 |
| `BLM18PG121SN1D` | Murata | 120Ω@100MHz Ferritperle, EMI-Unterdrückung | 0603 | ✅ |

### Quarze

| MPN | Beschreibung | Package | Frequenz | ✅ |
|-----|-------------|---------|---------|---|
| `HC49-8MHZ` / `HC49-8MHz` | HC-49S Quarz für STM32, 20pF | HC-49S | 8MHz | ✅/📋 |
| `HC49-12MHZ` / `HC49-12MHz` | HC-49S Quarz für RP2040, 15pF | HC-49S | 12MHz | ✅/📋 |
| `HC49-16MHZ` / `HC49-16MHz` | HC-49S Quarz für STM32 | HC-49S | 16MHz | ✅/📋 |
| `HC49-32MHZ` | HC-49S Quarz für ESP32/High-Speed | HC-49S | 32MHz | ✅ |

### Dioden

| MPN | Hersteller | Beschreibung | Package | ✅ |
|-----|-----------|-------------|---------|---|
| `1N4007` | Generic | Gleichrichterdiode / Freilaufdiode, 1A 1000V | DO-41 | ✅ |

---

## 11. Sonstige (RTC, GPIO-Expander, etc.)

| MPN | Hersteller | Beschreibung | Package | Interface | ✅ |
|-----|-----------|-------------|---------|-----------|---|
| `DS3231` | Maxim | Hochgenaue I2C-RTC/TCXO, ±2ppm | SOIC-16 | I2C | 📋 |
| `DS3231SN` | Maxim | Hochgenaue I2C-RTC mit TCXO und Quarz, ±2ppm | SOIC-16 | I2C | 📋 |
| `MCP23017` | Microchip | 16-Bit I/O-Expander, I2C, 2×8 Bit | SOIC-28 | I2C | 📋 |
| `MCP4725` | Microchip | 12-Bit DAC mit I2C | SOT-23-6 | I2C | 📋 |
| `PCF8563` | NXP | RTC/Kalender, Ultra-Low-Power 250nA | SOIC-8 | I2C | 📋 |
| `PCF8563T` | NXP | Low-Power RTC, Alarm, Timer, programmierbarer Taktausgang | SO-8 | I2C | 📋 |
| `PCF8574` | NXP | Remote 8-Bit I/O-Expander, I2C | DIP-16 | I2C | 📋 |
| `PCF8574T` | NXP | 8-Bit I/O-Expander, I2C, für HD44780 LCD-Adapter | SO-16 | I2C | 📋 |
| `CD74HC4051E` | TI | 8-Kanal Analog-Mux, 3 Selektionsleitungen | DIP-16 | GPIO | 📋 |
| `MCP4725A0T-E/OT` | Microchip | 12-Bit DAC mit I2C + NV-EEPROM | SOT-23-6 | I2C | 📋 |
| `SN74HC595N` | TI | 8-Bit Serial-In/Parallel-Out Schieberegister | DIP-16 | SPI | 📋 |
| `TXS0108EPWR` | TI | 8-Bit auto-dir. Pegelwandler, 1.2V–5.5V, 100Mbps | TSSOP-20 | — | 📋 |

---

## Statistik

| Kategorie | Gesamt | davon mit KiCad ✅ | nur DB 📋 |
|-----------|-------:|------------------:|----------:|
| MCUs | 21 | 17 | 4 |
| Sensoren | 40 | 18 | 22 |
| Kommunikation | 32 | 14 | 18 |
| Stromversorgung | 31 | 9 | 22 |
| Aktoren & Treiber | 16 | 5 | 11 |
| Display & Audio | 10 | 4 | 6 |
| Speicher | 8 | 2 | 6 |
| Steckverbinder | 12 | 8 | 4 |
| Analog & Logik | 8 | 0 | 8 |
| Passive Bauteile | 12 | 9 | 3 |
| Sonstige | 12 | 0 | 12 |
| **Gesamt** | **202** | **86** | **116** |

> ℹ️ Einige MPNs erscheinen in mehreren Kategorien (z.B. `MAX98357A` unter Sensoren und Aktoren) oder haben leicht abweichende MPN-Schreibweisen zwischen den Quellen (`HC49-8MHZ` vs `HC49-8MHz`). Die **echte Gesamtzahl eindeutiger Bauteile** beträgt **~205**.
