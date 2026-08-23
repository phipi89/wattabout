from __future__ import annotations

from pint import UnitRegistry

ureg = UnitRegistry(autoconvert_offset_to_baseunit=True)
ureg.define("kg_co2e = [climate_impact] = kg_CO2e")
ureg.define("g_co2e = 0.001 kg_co2e = g_CO2e")
ureg.define("coffee_cup = [coffee_serving]")
ureg.define("phone_device = [phone_count]")
ureg.define("laptop_device = [laptop_count]")
ureg.define("phone_charge = [phone_charge_count]")
ureg.define("dishwasher_cycle = [dishwasher_cycle_count]")
ureg.define("kWh_th = [useful_heat]")

Q_ = ureg.Quantity

kg_co2e = ureg.kg_co2e
g_co2e = ureg.g_co2e
km = ureg.kilometer
m = ureg.meter
m2 = ureg.meter**2
cm = ureg.centimeter
mm = ureg.millimeter
kg = ureg.kilogram
gram = ureg.gram
liter = ureg.liter
kWh = ureg.kilowatt_hour
MJ = ureg.megajoule
degC = ureg.degC
hour = ureg.hour
minute = ureg.minute
year = ureg.year
coffee_cup = ureg.coffee_cup
phone_device = ureg.phone_device
laptop_device = ureg.laptop_device
phone_charge = ureg.phone_charge
dishwasher_cycle = ureg.dishwasher_cycle
kWh_th = ureg.kWh_th
