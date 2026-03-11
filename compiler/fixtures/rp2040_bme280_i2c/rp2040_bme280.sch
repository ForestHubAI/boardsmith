<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE eagle SYSTEM "eagle.dtd">
<eagle version="9.6.2">
<drawing>
<settings></settings>
<grid distance="0.1" unitdist="inch" unit="inch"/>
<layers>
<layer number="91" name="Nets" color="2" fill="1" visible="yes" active="yes"/>
<layer number="94" name="Symbols" color="4" fill="1" visible="yes" active="yes"/>
</layers>
<schematic>
<libraries>
<library name="rp2040">
<packages>
<package name="QFN56">
<description>RP2040 QFN-56 Package</description>
</package>
</packages>
<symbols>
<symbol name="RP2040">
<pin name="GPIO0" x="-20.32" y="15.24" length="middle" direction="io"/>
<pin name="GPIO1" x="-20.32" y="12.7" length="middle" direction="io"/>
<pin name="GPIO2" x="-20.32" y="10.16" length="middle" direction="io"/>
<pin name="GPIO3" x="-20.32" y="7.62" length="middle" direction="io"/>
<pin name="GPIO4/SDA" x="-20.32" y="5.08" length="middle" direction="io"/>
<pin name="GPIO5/SCL" x="-20.32" y="2.54" length="middle" direction="io"/>
<pin name="GPIO25" x="20.32" y="15.24" length="middle" direction="io" rot="R180"/>
<pin name="3V3" x="0" y="25.4" length="middle" direction="pwr" rot="R270"/>
<pin name="GND" x="0" y="-25.4" length="middle" direction="pwr" rot="R90"/>
<pin name="VBUS" x="5.08" y="25.4" length="middle" direction="pwr" rot="R270"/>
</symbol>
</symbols>
<devicesets>
<deviceset name="RP2040" prefix="U">
<gates>
<gate name="G$1" symbol="RP2040" x="0" y="0"/>
</gates>
<devices>
<device name="" package="QFN56">
<connects>
<connect gate="G$1" pin="GPIO0" pad="2"/>
<connect gate="G$1" pin="GPIO1" pad="3"/>
<connect gate="G$1" pin="GPIO2" pad="4"/>
<connect gate="G$1" pin="GPIO3" pad="5"/>
<connect gate="G$1" pin="GPIO4/SDA" pad="6"/>
<connect gate="G$1" pin="GPIO5/SCL" pad="7"/>
<connect gate="G$1" pin="GPIO25" pad="29"/>
<connect gate="G$1" pin="3V3" pad="44"/>
<connect gate="G$1" pin="GND" pad="57"/>
<connect gate="G$1" pin="VBUS" pad="40"/>
</connects>
</device>
</devices>
</deviceset>
</devicesets>
</library>
<library name="sensors">
<packages>
<package name="BME280-LGA8">
<description>BME280 LGA-8 2.5x2.5mm</description>
</package>
</packages>
<symbols>
<symbol name="BME280">
<pin name="SDA" x="-15.24" y="2.54" length="middle" direction="io"/>
<pin name="SCL" x="-15.24" y="0" length="middle" direction="in"/>
<pin name="VDD" x="0" y="12.7" length="middle" direction="pwr" rot="R270"/>
<pin name="GND" x="0" y="-12.7" length="middle" direction="pwr" rot="R90"/>
<pin name="CSB" x="15.24" y="2.54" length="middle" direction="in" rot="R180"/>
<pin name="SDO" x="15.24" y="0" length="middle" direction="out" rot="R180"/>
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
<connect gate="G$1" pin="GND" pad="3"/>
<connect gate="G$1" pin="CSB" pad="6"/>
<connect gate="G$1" pin="SDO" pad="4"/>
</connects>
</device>
</devices>
</deviceset>
</devicesets>
</library>
<library name="passive">
<packages>
<package name="R0402"><description>0402 Resistor</description></package>
<package name="C0402"><description>0402 Capacitor</description></package>
</packages>
<symbols>
<symbol name="RESISTOR">
<pin name="1" x="-5.08" y="0" length="middle" direction="pas"/>
<pin name="2" x="5.08" y="0" length="middle" direction="pas" rot="R180"/>
</symbol>
<symbol name="CAPACITOR">
<pin name="1" x="-5.08" y="0" length="middle" direction="pas"/>
<pin name="2" x="5.08" y="0" length="middle" direction="pas" rot="R180"/>
</symbol>
</symbols>
<devicesets>
<deviceset name="R" prefix="R">
<gates><gate name="G$1" symbol="RESISTOR" x="0" y="0"/></gates>
<devices>
<device name="" package="R0402">
<connects>
<connect gate="G$1" pin="1" pad="1"/>
<connect gate="G$1" pin="2" pad="2"/>
</connects>
</device>
</devices>
</deviceset>
<deviceset name="C" prefix="C">
<gates><gate name="G$1" symbol="CAPACITOR" x="0" y="0"/></gates>
<devices>
<device name="" package="C0402">
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
<part name="U1" library="rp2040" deviceset="RP2040" device="">
<attribute name="MANUFACTURER" value="Raspberry Pi"/>
<attribute name="MPN" value="RP2040"/>
</part>
<part name="U2" library="sensors" deviceset="BME280" device="">
<attribute name="MANUFACTURER" value="Bosch"/>
<attribute name="MPN" value="BME280"/>
</part>
<part name="R1" library="passive" deviceset="R" device="" value="4.7k"/>
<part name="R2" library="passive" deviceset="R" device="" value="4.7k"/>
<part name="C1" library="passive" deviceset="C" device="" value="100n"/>
</parts>
<sheets>
<sheet>
<instances>
<instance part="U1" gate="G$1" x="50.8" y="50.8"/>
<instance part="U2" gate="G$1" x="120.65" y="50.8"/>
<instance part="R1" gate="G$1" x="83.82" y="71.12" rot="R90"/>
<instance part="R2" gate="G$1" x="91.44" y="71.12" rot="R90"/>
<instance part="C1" gate="G$1" x="109.22" y="35.56" rot="R90"/>
</instances>
<nets>
<net name="SDA" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="GPIO4/SDA"/>
<wire x1="30.48" y1="55.88" x2="83.82" y2="55.88" width="0.1524" layer="91"/>
<pinref part="R1" gate="G$1" pin="1"/>
<wire x1="83.82" y1="55.88" x2="83.82" y2="66.04" width="0.1524" layer="91"/>
<pinref part="U2" gate="G$1" pin="SDA"/>
<wire x1="83.82" y1="55.88" x2="105.41" y2="53.34" width="0.1524" layer="91"/>
</segment>
</net>
<net name="SCL" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="GPIO5/SCL"/>
<wire x1="30.48" y1="53.34" x2="91.44" y2="53.34" width="0.1524" layer="91"/>
<pinref part="R2" gate="G$1" pin="1"/>
<wire x1="91.44" y1="53.34" x2="91.44" y2="66.04" width="0.1524" layer="91"/>
<pinref part="U2" gate="G$1" pin="SCL"/>
<wire x1="91.44" y1="53.34" x2="105.41" y2="50.8" width="0.1524" layer="91"/>
</segment>
</net>
<net name="3V3" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="3V3"/>
<wire x1="50.8" y1="76.2" x2="50.8" y2="81.28" width="0.1524" layer="91"/>
<pinref part="R1" gate="G$1" pin="2"/>
<wire x1="50.8" y1="81.28" x2="83.82" y2="81.28" width="0.1524" layer="91"/>
<wire x1="83.82" y1="81.28" x2="83.82" y2="76.2" width="0.1524" layer="91"/>
<pinref part="R2" gate="G$1" pin="2"/>
<wire x1="83.82" y1="81.28" x2="91.44" y2="81.28" width="0.1524" layer="91"/>
<wire x1="91.44" y1="81.28" x2="91.44" y2="76.2" width="0.1524" layer="91"/>
<pinref part="U2" gate="G$1" pin="VDD"/>
<wire x1="91.44" y1="81.28" x2="120.65" y2="81.28" width="0.1524" layer="91"/>
<wire x1="120.65" y1="81.28" x2="120.65" y2="63.5" width="0.1524" layer="91"/>
<pinref part="C1" gate="G$1" pin="1"/>
<wire x1="109.22" y1="81.28" x2="109.22" y2="40.64" width="0.1524" layer="91"/>
</segment>
</net>
<net name="GND" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="GND"/>
<wire x1="50.8" y1="25.4" x2="50.8" y2="20.32" width="0.1524" layer="91"/>
<pinref part="U2" gate="G$1" pin="GND"/>
<wire x1="50.8" y1="20.32" x2="120.65" y2="20.32" width="0.1524" layer="91"/>
<wire x1="120.65" y1="20.32" x2="120.65" y2="38.1" width="0.1524" layer="91"/>
<pinref part="C1" gate="G$1" pin="2"/>
<wire x1="109.22" y1="20.32" x2="109.22" y2="30.48" width="0.1524" layer="91"/>
</segment>
</net>
</nets>
</sheet>
</sheets>
</schematic>
</drawing>
</eagle>
