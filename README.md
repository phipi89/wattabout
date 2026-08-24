# WattAbout

> Put things on the same scale.

WattAbout is a Python library that helps me build an intuition for the climate impact of very different things. It simplifies comparison between food, transportation, trees, … via their co2 equivalent emissions.

```python
from wattabout import *

# building this was about half a cervelat
ai.frontier_llm(3e6 * token, cache_read_ratio=0.95) / food.cervelat(100 * gram)
# 0.531×


# lets do a trip
lunch = food.meal_omnivore()               # 2 kg_CO2e
travel = transport.petrol_car(35 * km)     # 5.99 kg_CO2e
conclusion = household.shower(10 * minute) # 267 g_CO2e
(lunch + travel + conclusion) / lifestyle.swiss_resident(1 * day)
# 0.226×


# how many trees to compensate my trip to New York over 10 years?
intercontinental_flight = transport.flight(8_000 * km) # 2.58 t_CO2e
(2 * intercontinental_flight) / nature.tree_growth(10 * year)
# -197×


# how much better became heating and insulation technology?
buildings.house_1960s() / buildings.minergie
# 70.7×
```


getting started:

```python
# most models are linear
buildings.house_2000s(150 * m2)
# 2.52×10³ kg_CO2e / year

# but some are not
transport.flight(1000 * km) / (2 * transport.flight(500 * km))
# 0.794×

# explore with
list_categories()
list_assets()
transport.flight?
```

This is not a tool for a proper lifecycle study. The built-in numbers are ai-generated prototype estimates. The longer explanation, model assumptions, and API reference live in [the design notes](docs/design.md).
