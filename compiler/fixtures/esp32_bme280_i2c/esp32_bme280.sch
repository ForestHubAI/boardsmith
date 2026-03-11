<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE eagle SYSTEM "eagle.dtd">
<eagle version="9.6.2">
<drawing>
<settings>
<setting alwaysvectorfont="no"/>
</settings>
<grid distance="0.1" unitdist="inch"/>
<layers>
<layer number="1" name="Top" color="4" fill="1" visible="yes" active="yes"/>
<layer number="91" name="Nets" color="2" fill="1" visible="yes" active="yes"/>
<layer number="94" name="Symbols" color="4" fill="1" visible="yes" active="yes"/>
</layers>
<schematic>
<libraries>
<library name="esp32">
<packages>
<package name="ESP32-WROOM-32">
</package>
</packages>
<symbols>
<symbol name="ESP32">
<pin name="GPIO21/SDA" x="-20" y="10" length="middle" direction="io"/>
<pin name="GPIO22/SCL" x="-20" y="8" length="middle" direction="io"/>
<pin name="GPIO4/INT" x="-20" y="6" length="middle" direction="in"/>
<pin name="3V3" x="-20" y="4" length="middle" direction="pwr"/>
<pin name="GND" x="-20" y="2" length="middle" direction="pwr"/>
<pin name="EN" x="-20" y="0" length="middle" direction="in"/>
<pin name="GPIO0" x="20" y="10" length="middle" direction="io"/>
<pin name="GPIO2" x="20" y="8" length="middle" direction="io"/>
<pin name="TX" x="20" y="6" length="middle" direction="out"/>
<pin name="RX" x="20" y="4" length="middle" direction="in"/>
</symbol>
</symbols>
<devicesets>
<deviceset name="ESP32-WROOM-32" prefix="U">
<gates>
<gate name="G$1" symbol="ESP32" x="0" y="0"/>
</gates>
<devices>
<device name="" package="ESP32-WROOM-32">
<connects>
<connect gate="G$1" pin="GPIO21/SDA" pad="33"/>
<connect gate="G$1" pin="GPIO22/SCL" pad="36"/>
<connect gate="G$1" pin="GPIO4/INT" pad="26"/>
<connect gate="G$1" pin="3V3" pad="2"/>
<connect gate="G$1" pin="GND" pad="1"/>
<connect gate="G$1" pin="EN" pad="3"/>
<connect gate="G$1" pin="GPIO0" pad="25"/>
<connect gate="G$1" pin="GPIO2" pad="24"/>
<connect gate="G$1" pin="TX" pad="35"/>
<connect gate="G$1" pin="RX" pad="34"/>
</connects>
</device>
</devices>
</deviceset>
</devicesets>
</library>
<library name="sensors">
<packages>
<package name="BME280-LGA8">
</package>
</packages>
<symbols>
<symbol name="BME280">
<pin name="SDA" x="-15" y="5" length="middle" direction="io"/>
<pin name="SCL" x="-15" y="3" length="middle" direction="in"/>
<pin name="VDD" x="-15" y="1" length="middle" direction="pwr"/>
<pin name="GND" x="-15" y="-1" length="middle" direction="pwr"/>
<pin name="CSB" x="15" y="5" length="middle" direction="in"/>
<pin name="SDO" x="15" y="3" length="middle" direction="out"/>
</symbol>
</symbols>
<devicesets>
<deviceset name="BME280" prefix="U">
<gates>
<gate name="G$1" symbol="BME280" x="0" y="0"/>
</gates>
<devices>
<device name="" package="BME280-LGA8">
<connects>
<connect gate="G$1" pin="SDA" pad="1"/>
<connect gate="G$1" pin="SCL" pad="2"/>
<connect gate="G$1" pin="VDD" pad="5"/>
<connect gate="G$1" pin="GND" pad="4"/>
<connect gate="G$1" pin="CSB" pad="6"/>
<connect gate="G$1" pin="SDO" pad="3"/>
</connects>
</device>
</devices>
</deviceset>
</devicesets>
</library>
<library name="passive">
<packages>
<package name="R0402">
</package>
<package name="C0402">
</package>
</packages>
<symbols>
<symbol name="R">
<pin name="1" x="-5" y="0" length="short" direction="pas"/>
<pin name="2" x="5" y="0" length="short" direction="pas"/>
</symbol>
<symbol name="C">
<pin name="1" x="-5" y="0" length="short" direction="pas"/>
<pin name="2" x="5" y="0" length="short" direction="pas"/>
</symbol>
</symbols>
<devicesets>
<deviceset name="R" prefix="R">
<gates>
<gate name="G$1" symbol="R" x="0" y="0"/>
</gates>
<devices>
<device name="0402" package="R0402">
<connects>
<connect gate="G$1" pin="1" pad="1"/>
<connect gate="G$1" pin="2" pad="2"/>
</connects>
</device>
</devices>
</deviceset>
<deviceset name="C" prefix="C">
<gates>
<gate name="G$1" symbol="C" x="0" y="0"/>
</gates>
<devices>
<device name="0402" package="C0402">
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
<part name="R1" library="passive" deviceset="R" device="0402" value="4.7k"/>
<part name="R2" library="passive" deviceset="R" device="0402" value="4.7k"/>
<part name="C1" library="passive" deviceset="C" device="0402" value="100nF"/>
</parts>
<sheets>
<sheet>
<instances>
<instance part="U1" gate="G$1" x="50" y="50"/>
<instance part="U2" gate="G$1" x="120" y="50"/>
<instance part="R1" gate="G$1" x="85" y="65"/>
<instance part="R2" gate="G$1" x="85" y="55"/>
<instance part="C1" gate="G$1" x="130" y="35"/>
</instances>
<nets>
<net name="SDA" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="GPIO21/SDA"/>
<pinref part="U2" gate="G$1" pin="SDA"/>
<pinref part="R1" gate="G$1" pin="1"/>
<wire x1="30" y1="60" x2="105" y2="55" width="0.1524" layer="91"/>
</segment>
</net>
<net name="SCL" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="GPIO22/SCL"/>
<pinref part="U2" gate="G$1" pin="SCL"/>
<pinref part="R2" gate="G$1" pin="1"/>
<wire x1="30" y1="58" x2="105" y2="53" width="0.1524" layer="91"/>
</segment>
</net>
<net name="3V3" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="3V3"/>
<pinref part="U2" gate="G$1" pin="VDD"/>
<pinref part="R1" gate="G$1" pin="2"/>
<pinref part="R2" gate="G$1" pin="2"/>
<pinref part="C1" gate="G$1" pin="1"/>
<pinref part="U2" gate="G$1" pin="CSB"/>
</segment>
</net>
<net name="GND" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="GND"/>
<pinref part="U2" gate="G$1" pin="GND"/>
<pinref part="C1" gate="G$1" pin="2"/>
<pinref part="U2" gate="G$1" pin="SDO"/>
</segment>
</net>
</nets>
</sheet>
</sheets>
</schematic>
</drawing>
</eagle>
