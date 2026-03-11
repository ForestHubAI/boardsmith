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
<library name="stm32">
<packages>
<package name="LQFP64">
</package>
</packages>
<symbols>
<symbol name="STM32F411">
<pin name="PB6/SCL" x="-20" y="10" length="middle" direction="io"/>
<pin name="PB7/SDA" x="-20" y="8" length="middle" direction="io"/>
<pin name="PA0/INT" x="-20" y="6" length="middle" direction="in"/>
<pin name="VDD" x="-20" y="4" length="middle" direction="pwr"/>
<pin name="VSS" x="-20" y="2" length="middle" direction="pwr"/>
<pin name="NRST" x="-20" y="0" length="middle" direction="in"/>
<pin name="PA2/TX" x="20" y="10" length="middle" direction="out"/>
<pin name="PA3/RX" x="20" y="8" length="middle" direction="in"/>
<pin name="PA5/SCK" x="20" y="6" length="middle" direction="io"/>
<pin name="PA6/MISO" x="20" y="4" length="middle" direction="in"/>
<pin name="PA7/MOSI" x="20" y="2" length="middle" direction="out"/>
<pin name="PA4/NSS" x="20" y="0" length="middle" direction="io"/>
</symbol>
</symbols>
<devicesets>
<deviceset name="STM32F411CEU6" prefix="U">
<gates>
<gate name="G$1" symbol="STM32F411" x="0" y="0"/>
</gates>
<devices>
<device name="" package="LQFP64">
<connects>
<connect gate="G$1" pin="PB6/SCL" pad="58"/>
<connect gate="G$1" pin="PB7/SDA" pad="59"/>
<connect gate="G$1" pin="PA0/INT" pad="14"/>
<connect gate="G$1" pin="VDD" pad="1"/>
<connect gate="G$1" pin="VSS" pad="63"/>
<connect gate="G$1" pin="NRST" pad="7"/>
<connect gate="G$1" pin="PA2/TX" pad="16"/>
<connect gate="G$1" pin="PA3/RX" pad="17"/>
<connect gate="G$1" pin="PA5/SCK" pad="21"/>
<connect gate="G$1" pin="PA6/MISO" pad="22"/>
<connect gate="G$1" pin="PA7/MOSI" pad="23"/>
<connect gate="G$1" pin="PA4/NSS" pad="20"/>
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
<part name="U1" library="stm32" deviceset="STM32F411CEU6" device="">
<attribute name="MANUFACTURER" value="STMicroelectronics"/>
<attribute name="MPN" value="STM32F411CEU6"/>
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
<pinref part="U1" gate="G$1" pin="PB7/SDA"/>
<pinref part="U2" gate="G$1" pin="SDA"/>
<pinref part="R1" gate="G$1" pin="1"/>
</segment>
</net>
<net name="SCL" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="PB6/SCL"/>
<pinref part="U2" gate="G$1" pin="SCL"/>
<pinref part="R2" gate="G$1" pin="1"/>
</segment>
</net>
<net name="3V3" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="VDD"/>
<pinref part="U2" gate="G$1" pin="VDD"/>
<pinref part="R1" gate="G$1" pin="2"/>
<pinref part="R2" gate="G$1" pin="2"/>
<pinref part="C1" gate="G$1" pin="1"/>
<pinref part="U2" gate="G$1" pin="CSB"/>
</segment>
</net>
<net name="GND" class="0">
<segment>
<pinref part="U1" gate="G$1" pin="VSS"/>
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
