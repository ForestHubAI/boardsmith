<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE eagle SYSTEM "eagle.dtd">
<eagle version="9.6.2">
<drawing>
<settings><setting alwaysvectorfont="no"/></settings>
<grid distance="0.1" unitdist="inch"/>
<layers>
<layer number="1" name="Top" color="4" fill="1" visible="yes" active="yes"/>
<layer number="91" name="Nets" color="2" fill="1" visible="yes" active="yes"/>
</layers>
<schematic>
<libraries>
<library name="esp32">
<packages><package name="ESP32-WROOM-32"/></packages>
<symbols>
<symbol name="ESP32">
<pin name="GPIO21/SDA" x="-20" y="14" length="middle" direction="io"/>
<pin name="GPIO22/SCL" x="-20" y="12" length="middle" direction="io"/>
<pin name="GPIO23/MOSI" x="-20" y="10" length="middle" direction="out"/>
<pin name="GPIO19/MISO" x="-20" y="8" length="middle" direction="in"/>
<pin name="GPIO18/SCK" x="-20" y="6" length="middle" direction="out"/>
<pin name="GPIO5/CS" x="-20" y="4" length="middle" direction="out"/>
<pin name="GPIO17/TX" x="20" y="14" length="middle" direction="out"/>
<pin name="GPIO16/RX" x="20" y="12" length="middle" direction="in"/>
<pin name="GPIO4/INT" x="20" y="10" length="middle" direction="in"/>
<pin name="GPIO34/ADC" x="20" y="8" length="middle" direction="in"/>
<pin name="3V3" x="20" y="4" length="middle" direction="pwr"/>
<pin name="GND" x="20" y="2" length="middle" direction="pwr"/>
</symbol>
</symbols>
<devicesets>
<deviceset name="ESP32-WROOM-32" prefix="U">
<gates><gate name="G$1" symbol="ESP32" x="0" y="0"/></gates>
<devices>
<device name="" package="ESP32-WROOM-32">
<connects>
<connect gate="G$1" pin="GPIO21/SDA" pad="33"/>
<connect gate="G$1" pin="GPIO22/SCL" pad="36"/>
<connect gate="G$1" pin="GPIO23/MOSI" pad="37"/>
<connect gate="G$1" pin="GPIO19/MISO" pad="31"/>
<connect gate="G$1" pin="GPIO18/SCK" pad="30"/>
<connect gate="G$1" pin="GPIO5/CS" pad="29"/>
<connect gate="G$1" pin="GPIO17/TX" pad="28"/>
<connect gate="G$1" pin="GPIO16/RX" pad="27"/>
<connect gate="G$1" pin="GPIO4/INT" pad="26"/>
<connect gate="G$1" pin="GPIO34/ADC" pad="6"/>
<connect gate="G$1" pin="3V3" pad="2"/>
<connect gate="G$1" pin="GND" pad="1"/>
</connects>
</device>
</devices>
</deviceset>
</devicesets>
</library>
<library name="sensors">
<packages><package name="BME280-LGA8"/></packages>
<symbols>
<symbol name="BME280">
<pin name="SDA" x="-10" y="3" length="middle" direction="io"/>
<pin name="SCL" x="-10" y="1" length="middle" direction="in"/>
<pin name="VDD" x="-10" y="-1" length="middle" direction="pwr"/>
<pin name="GND" x="-10" y="-3" length="middle" direction="pwr"/>
</symbol>
</symbols>
<devicesets>
<deviceset name="BME280" prefix="U">
<gates><gate name="G$1" symbol="BME280" x="0" y="0"/></gates>
<devices>
<device name="" package="BME280-LGA8">
<connects>
<connect gate="G$1" pin="SDA" pad="1"/>
<connect gate="G$1" pin="SCL" pad="2"/>
<connect gate="G$1" pin="VDD" pad="5"/>
<connect gate="G$1" pin="GND" pad="4"/>
</connects>
</device>
</devices>
</deviceset>
</devicesets>
</library>
<library name="flash">
<packages><package name="SOIC8"/></packages>
<symbols>
<symbol name="W25Q">
<pin name="MOSI" x="-10" y="3" length="middle" direction="in"/>
<pin name="MISO" x="-10" y="1" length="middle" direction="out"/>
<pin name="SCK" x="-10" y="-1" length="middle" direction="in"/>
<pin name="CS" x="-10" y="-3" length="middle" direction="in"/>
<pin name="VCC" x="10" y="3" length="middle" direction="pwr"/>
<pin name="GND" x="10" y="-3" length="middle" direction="pwr"/>
</symbol>
</symbols>
<devicesets>
<deviceset name="W25Q128" prefix="U">
<gates><gate name="G$1" symbol="W25Q" x="0" y="0"/></gates>
<devices>
<device name="" package="SOIC8">
<connects>
<connect gate="G$1" pin="MOSI" pad="5"/>
<connect gate="G$1" pin="MISO" pad="2"/>
<connect gate="G$1" pin="SCK" pad="6"/>
<connect gate="G$1" pin="CS" pad="1"/>
<connect gate="G$1" pin="VCC" pad="8"/>
<connect gate="G$1" pin="GND" pad="4"/>
</connects>
</device>
</devices>
</deviceset>
</devicesets>
</library>
<library name="gps">
<packages><package name="LCC18"/></packages>
<symbols>
<symbol name="NEOM8N">
<pin name="TX" x="-10" y="3" length="middle" direction="out"/>
<pin name="RX" x="-10" y="1" length="middle" direction="in"/>
<pin name="VCC" x="10" y="3" length="middle" direction="pwr"/>
<pin name="GND" x="10" y="-3" length="middle" direction="pwr"/>
</symbol>
</symbols>
<devicesets>
<deviceset name="NEO-M8N" prefix="U">
<gates><gate name="G$1" symbol="NEOM8N" x="0" y="0"/></gates>
<devices>
<device name="" package="LCC18">
<connects>
<connect gate="G$1" pin="TX" pad="17"/>
<connect gate="G$1" pin="RX" pad="18"/>
<connect gate="G$1" pin="VCC" pad="12"/>
<connect gate="G$1" pin="GND" pad="10"/>
</connects>
</device>
</devices>
</deviceset>
</devicesets>
</library>
<library name="passive">
<packages><package name="R0402"/></packages>
<symbols>
<symbol name="R">
<pin name="1" x="-5" y="0" length="short" direction="pas"/>
<pin name="2" x="5" y="0" length="short" direction="pas"/>
</symbol>
</symbols>
<devicesets>
<deviceset name="R" prefix="R">
<gates><gate name="G$1" symbol="R" x="0" y="0"/></gates>
<devices>
<device name="0402" package="R0402">
<connects>
<connect gate="G$1" pin="1" pad="1"/>
<connect gate="G$1" pin="2" pad="2"/>
</connects>
</device>
</devices>
</deviceset>
</devicesets>
</library>
</libraries>
<parts>
<part name="U1" library="esp32" deviceset="ESP32-WROOM-32" device="">
<attribute name="MANUFACTURER" value="Espressif"/>
<attribute name="MPN" value="ESP32-WROOM-32"/>
</part>
<part name="U2" library="sensors" deviceset="BME280" device="">
<attribute name="MANUFACTURER" value="Bosch"/>
<attribute name="MPN" value="BME280"/>
</part>
<part name="U3" library="flash" deviceset="W25Q128" device="">
<attribute name="MANUFACTURER" value="Winbond"/>
<attribute name="MPN" value="W25Q128JVSIQ"/>
</part>
<part name="U4" library="gps" deviceset="NEO-M8N" device="">
<attribute name="MANUFACTURER" value="u-blox"/>
<attribute name="MPN" value="NEO-M8N"/>
</part>
<part name="R1" library="passive" deviceset="R" device="0402" value="4.7k"/>
<part name="R2" library="passive" deviceset="R" device="0402" value="4.7k"/>
</parts>
<sheets>
<sheet>
<instances>
<instance part="U1" gate="G$1" x="50" y="50"/>
<instance part="U2" gate="G$1" x="120" y="70"/>
<instance part="U3" gate="G$1" x="120" y="40"/>
<instance part="U4" gate="G$1" x="120" y="10"/>
<instance part="R1" gate="G$1" x="85" y="75"/>
<instance part="R2" gate="G$1" x="85" y="65"/>
</instances>
<nets>
<net name="SDA" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="GPIO21/SDA"/>
<pinref part="U2" gate="G$1" pin="SDA"/>
<pinref part="R1" gate="G$1" pin="1"/>
</segment>
</net>
<net name="SCL" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="GPIO22/SCL"/>
<pinref part="U2" gate="G$1" pin="SCL"/>
<pinref part="R2" gate="G$1" pin="1"/>
</segment>
</net>
<net name="MOSI" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="GPIO23/MOSI"/>
<pinref part="U3" gate="G$1" pin="MOSI"/>
</segment>
</net>
<net name="MISO" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="GPIO19/MISO"/>
<pinref part="U3" gate="G$1" pin="MISO"/>
</segment>
</net>
<net name="SCK" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="GPIO18/SCK"/>
<pinref part="U3" gate="G$1" pin="SCK"/>
</segment>
</net>
<net name="CS" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="GPIO5/CS"/>
<pinref part="U3" gate="G$1" pin="CS"/>
</segment>
</net>
<net name="TX" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="GPIO17/TX"/>
<pinref part="U4" gate="G$1" pin="RX"/>
</segment>
</net>
<net name="RX" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="GPIO16/RX"/>
<pinref part="U4" gate="G$1" pin="TX"/>
</segment>
</net>
<net name="3V3" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="3V3"/>
<pinref part="U2" gate="G$1" pin="VDD"/>
<pinref part="U3" gate="G$1" pin="VCC"/>
<pinref part="U4" gate="G$1" pin="VCC"/>
<pinref part="R1" gate="G$1" pin="2"/>
<pinref part="R2" gate="G$1" pin="2"/>
</segment>
</net>
<net name="GND" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="GND"/>
<pinref part="U2" gate="G$1" pin="GND"/>
<pinref part="U3" gate="G$1" pin="GND"/>
<pinref part="U4" gate="G$1" pin="GND"/>
</segment>
</net>
</nets>
</sheet>
</sheets>
</schematic>
</drawing>
</eagle>
