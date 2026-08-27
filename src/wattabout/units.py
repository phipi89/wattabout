from __future__ import annotations

from pint import UnitRegistry

ureg = UnitRegistry(autoconvert_offset_to_baseunit=True)
ureg.define("kg_co2e = [climate_impact] = kg_CO2e")
ureg.define("g_co2e = 0.001 kg_co2e = g_CO2e")
ureg.define("tonne_co2e = 1000 kg_co2e = t_CO2e")
ureg.define("coffee_cup = [coffee_serving]")
ureg.define("phone_device = [phone_count]")
ureg.define("laptop_device = [laptop_count]")
ureg.define("phone_charge = [phone_charge_count]")
ureg.define("dishwasher_cycle = [dishwasher_cycle_count]")
ureg.define("kWh_th = [useful_heat]")
ureg.define("MWh_th = 1000 kWh_th")
ureg.define("token = [llm_token]")
ureg.define("million_token = 1000000 token")
ureg.define("meal = [meal_count]")
ureg.define("parcel = [parcel_count]")
ureg.define("laundry_cycle = [laundry_cycle_count]")
ureg.define("dryer_cycle = [dryer_cycle_count]")
ureg.define("CHF = [currency]")
ureg.define("eruption_event = [eruption_count]")

Q_ = ureg.Quantity

kg_co2e = ureg.kg_co2e
g_co2e = ureg.g_co2e
tonne_co2e = ureg.tonne_co2e
CHF = ureg.CHF
km = ureg.kilometer
m = ureg.meter
m2 = ureg.meter**2
hectare = ureg.hectare
ha = ureg.hectare
km2 = ureg.kilometer**2
cm = ureg.centimeter
mm = ureg.millimeter
kg = ureg.kilogram
gram = ureg.gram
mg = ureg.milligram
tonne = ureg.tonne
liter = ureg.liter
ml = ureg.milliliter
W = ureg.watt
kW = ureg.kilowatt
Wh = ureg.watt_hour
kWh = ureg.kilowatt_hour
MWh = ureg.megawatt_hour
MJ = ureg.megajoule
degC = ureg.degC
hour = ureg.hour
minute = ureg.minute
second = ureg.second
millisecond = ureg.millisecond
microsecond = ureg.microsecond
nanosecond = ureg.nanosecond
day = ureg.day
week = ureg.week
year = ureg.year
coffee_cup = ureg.coffee_cup
phone_device = ureg.phone_device
laptop_device = ureg.laptop_device
phone_charge = ureg.phone_charge
dishwasher_cycle = ureg.dishwasher_cycle
kWh_th = ureg.kWh_th
MWh_th = ureg.MWh_th
token = ureg.token
million_token = ureg.million_token
meal = ureg.meal
parcel = ureg.parcel
laundry_cycle = ureg.laundry_cycle
dryer_cycle = ureg.dryer_cycle
eruption_event = ureg.eruption_event
