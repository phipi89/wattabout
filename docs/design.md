# WattAbout Design And Reference

`wattabout` compares everyday activities through shared environmental impact
indicators. Its initial catalog provides climate-impact estimates with Swiss
defaults while retaining the assumptions and sources behind each result.

> [!WARNING]
> The bundled factors are illustrative prototype values. They are suitable for
> developing and demonstrating the API, not for scientific or commercial claims.

## Usage

```python
import wattabout as wa

wa.transport.train(30 * wa.km) / wa.food.cervelat
# 37.9 mm

wa.food.cervelat(2.5 * wa.mm) / wa.transport.train(30 * wa.km)
# 0.066×
```

An omitted right-hand amount is a scalable per-unit reference, whether written
as a bare asset or with empty parentheses. An explicit amount creates a
concrete comparison target:

```python
equivalent = wa.food.cervelat(10 * wa.cm) / wa.transport.train
print(equivalent)  # 79.2 km
print(equivalent.amount)  # 79.2 kilometer

ratio = wa.food.cervelat(10 * wa.cm) / wa.transport.train(10 * wa.km)
print(ratio)  # 7.92×
print(ratio.ratio)  # 7.92
float(ratio)  # 7.92

wa.electronics.phone() / wa.household.boil_water
# 7.08×10³ L

wa.electronics.phone() / wa.household.boil_water()
# 7.08×10³ L

wa.electronics.phone() / wa.household.boil_water(1 * wa.liter)
# 7.08e+03×
```

The rule applies throughout the catalog:

| Right operand | Meaning | Result |
|---|---|---|
| `asset` | Scalable reference | Equivalent amount |
| `asset()` | Scalable reference with defaults | Equivalent amount |
| `asset(explicit_amount)` | Concrete activity | Impact ratio |
| `asset.rate(...)` | Concrete operating rate | Ratio or duration |

One refinement applies when the left amount is also omitted and both sides
share the same dimensionality: archetype-versus-archetype comparisons display
as a ratio, because per-unit intensities are what is being compared:

```python
wa.transport.ev() / wa.transport.petrol_car
# 0.47×

wa.buildings.minergie() / wa.buildings.house_1960s
# 1.7×
```

Every comparison stores both views regardless of display. For linear,
same-sign comparisons, `ratio == amount / target_reference.display_amount`:

```python
comparison = wa.transport.ev() / wa.transport.petrol_car

comparison.amount  # 0.47 km — equivalent petrol-car distance
comparison.ratio  # 0.47     — dimensionless intensity ratio
float(comparison)  # 0.47     (any dimensionless ratio)
```

An empty call still represents one default unit when used as the source. Only
its interpretation as the right-hand comparison target is scalable.

Detailed provenance and assumptions remain available:

```python
print(equivalent.explain())
```

Activities can be added to combine their impacts, regardless of their amount
units. Multiplication repeats an occurrence without changing the activity's
input, which matters for nonlinear models:

```python
combo = wa.food.cervelat(10 * wa.cm) + wa.household.boil_water(1 * wa.liter)

repr(combo)  # 572 g_CO2e
print(combo)  # 10 cm of cervelat + 1 L of water boiled in an electric kettle

combo / wa.transport.train
# 80.6 km

sum([wa.food.coffee(), wa.food.coffee(), wa.electronics.phone()])
# 70.4 kg_CO2e

trip = 2 * wa.transport.flight(8_000 * wa.km)
# two 8,000 km flights, not one 16,000 km flight

wa.nature.tree_growth(5 * wa.year) + trip
```

Rate and non-rate activities cannot be mixed in one sum; rate sums remain
rates.

Activity representations show their climate impact in the active context:

```python
wa.electronics.phone()
# 70 kg_CO2e

wa.buildings.minergie(120 * wa.m2)
# 102 kg_CO2e / year

print(wa.electronics.phone())
# 1 phone_device of smartphone production

wa.electronics.phone().emission
# 70 kg_CO2e

wa.electronics.phone().energy
# electricity with the same climate impact at the context's grid intensity
```

`energy` is a grid-equivalent comparison, not the physical energy consumed by
the activity. Both properties use the active context.

## Categories

```python
wa.list_categories()
# ('ai', 'buildings', ..., 'lifestyle', ..., 'waste')

wa.list_assets("transport")
# ('transport.bus', 'transport.ev', ..., 'transport.train')

wa.transport.list_assets()
# ('bus', 'ev', ..., 'train')

print(wa.transport.ev.describe())
```

In IPython, `?` displays each asset's generated signature and documentation:

```python
wa.household.oven?
# Signature: oven(
#     cooking_time=None,
#     *,
#     temperature,
#     ambient_temperature='20 degC',
#     include_preheating=True,
#     ...,
# )
```

The same information is available through standard Python introspection:

```python
import inspect

inspect.signature(wa.household.oven)
help(wa.household.oven)
wa.household.oven.describe()
wa.household.oven.parameters
```

Included prototype assets:

| Category | Assets |
|---|---|
| `transport` | `bicycle`, `bus`, `ebike`, `ev`, `flight`, `flight_private`, `petrol_car`, `train` |
| `electronics` | `laptop`, `laptop_use`, `phone`, `phone_charge` |
| `food` | `cervelat`, `cheese`, `coffee`, `meal_omnivore`, `meal_vegetarian`, `meal_vegan`, `tofu` |
| `household` | `boil_water`, `dishwasher`, `hot_water`, `led_light`, `oven`, `refrigerator`, `shower`, `tumble_dryer`, `washing_machine` |
| `energy` | `electricity`, `natural_gas` |
| `heating` | `electric_resistance`, `gas_boiler`, `heat_pump`, `oil_boiler` |
| `buildings` | `custom`, `house_1960s`, `house_1980s`, `house_1990s`, `house_2000s`, `minergie` |
| `ai` | `efficient_llm`, `frontier_llm`, `local_llm` |
| `lifestyle` | `china_resident`, `european_resident`, `india_resident`, `swiss_resident`, `us_resident` |
| `nature` | `tree_growth` |
| `shipping` | `parcel_from_china` |
| `waste` | `mixed` |

Examples with configurable models:

```python
wa.transport.ev(
    50 * wa.km,
    occupancy=2,
    consumption=wa.Q_("16 kWh / (100 km)"),
)

wa.food.cervelat(
    10 * wa.cm,
    diameter=36 * wa.mm,
)

wa.electronics.phone_charge(
    1,
    battery_capacity=wa.Q_("18 Wh"),
)
```

## Nonlinear Sessions

Assets explicitly declare how equivalent amounts are calculated. Most are
linear, but startup-heavy sessions can provide an analytic inverse. Oven
cooking time excludes preheating and requires a target temperature:

```python
short = wa.household.oven(20 * wa.minute, temperature=200 * wa.degC)
long = wa.household.oven(40 * wa.minute, temperature=200 * wa.degC)

short / long
# 0.742×, not 0.5×, because both sessions include preheating
```

Configure required target parameters before asking for an equivalent amount:

```python
oven_200 = wa.household.oven.configure(temperature=200 * wa.degC)
wa.energy.electricity(1 * wa.kWh) / oven_200
# 37.5 min
```

If the source impact is below the minimum cold-start impact, WattAbout raises
`NoEquivalentAmountError` rather than returning a negative duration.

A duration-free oven rate represents preheated steady operation and excludes
the one-time startup energy:

```python
oven_rate = wa.household.oven.rate(temperature=220 * wa.degC)
oven_rate.impact()["climate"]  # kg CO2e / hour
oven_rate.over(2 * wa.hour)  # integrated two-hour activity

# Equivalent shorthand for linear rate integration
wa.household.oven.rate(
    temperature=220 * wa.degC,
    duration=2 * wa.hour,
)
```

Refrigerators intentionally use average load, and dishwashers use energy per
complete cycle rather than simulating internal phases.

Domestic hot water and showers use water-heating physics plus drinking-water
supply and wastewater treatment. The default shower lasts eight minutes at
9 L/min and uses electric resistance heating, but each assumption is
configurable:

```python
wa.household.hot_water(50 * wa.liter)
wa.household.shower(8 * wa.minute)
wa.household.shower(
    5 * wa.minute,
    flow_rate=6 * wa.liter / wa.minute,
    heating=wa.heating.heat_pump.configure(scop=3),
)
```

Laundry cycles include electricity, water services, and a prototype detergent
factor. Tumble drying is represented by electricity per complete cycle:

```python
wa.household.washing_machine(1)
wa.household.tumble_dryer(1)
```

Bicycle factors allocate manufacture and maintenance over distance. E-bikes
also include battery manufacture and grid-sensitive charging. Rider food and
transport infrastructure are excluded from both models:

```python
wa.transport.bicycle(10 * wa.km)
wa.transport.ebike(10 * wa.km)
```

## Heating And Buildings

Heating assets accept delivered useful heat in `kWh_th`:

```python
wa.heating.heat_pump(10_000 * wa.kWh_th, scop=3.5)
wa.heating.oil_boiler(10_000 * wa.kWh_th, efficiency=0.8)
```

Building profiles combine floor area, specific useful heat demand, and a
heating system. Their impacts are annual rates. Omitting the floor area uses a
prototype Swiss-average heated floor area of 120 m², informed by the Federal
Statistical Office building and dwelling statistics:

```python
modern = wa.buildings.minergie(
    150 * wa.m2,
    heating=wa.heating.heat_pump,
    heating_parameters={"scop": 3.5},
)

old = wa.buildings.house_1960s(
    150 * wa.m2,
    heating=wa.heating.oil_boiler,
    heating_parameters={"efficiency": 0.8},
)

modern / old
# 0.0141× under the prototype defaults

wa.buildings.minergie()
# annual rate for the 120 m² default floor area
```

Decade archetypes use consistent plural decade names:

```python
wa.buildings.house_1980s(150 * wa.m2)  # 150 kWh_th / m² / year, oil boiler
wa.buildings.house_1990s(150 * wa.m2)  # 110 kWh_th / m² / year, gas boiler
wa.buildings.house_2000s(150 * wa.m2)  # 75 kWh_th / m² / year, gas boiler
```

The decade values and default heating systems are illustrative archetypes. Both
can be overridden with `specific_heat_demand`, `heating`, and
`heating_parameters`.

The `minergie` profile is an illustrative operational space-heating scenario,
not a MINERGIE certification calculation. Building profiles exclude domestic
hot water, cooling, appliances, and embodied impacts.

Annual rates preserve their dimensions in cross-category comparisons:

```python
house = wa.buildings.house_1990s(120 * wa.m2)

house.impact()["climate"]
# 2.96e3 kg_CO2e / year

house.impact_intensity()["climate"]
# 24.7 kg_CO2e / m² / year

house / wa.electronics.phone()
# 42.3 phone_device / year

house.over(10 * wa.year) / wa.electronics.phone()
# 423×
```

Rate-producing assets consistently accept an optional `duration` as shorthand
for `.over(duration)`. Omitting it keeps the rate:

```python
annual = wa.buildings.minergie(120 * wa.m2)
# kg CO2e / year

one_year = wa.buildings.minergie(
    120 * wa.m2,
    duration=1 * wa.year,
)
# kg CO2e

assert one_year.impact()["climate"] == annual.over(1 * wa.year).impact()["climate"]

wa.household.refrigerator.rate(duration=24 * wa.hour)
wa.household.led_light.rate(duration=5 * wa.hour, power="10 W")
```

Comparing a total to a concrete rate returns the equivalent operating duration:

```python
wa.ai.frontier_llm(1e6) / wa.buildings.minergie(120 * wa.m2)
# 2.58 d

wa.ai.frontier_llm(1e6) / wa.buildings.minergie(
    120 * wa.m2,
    duration=1 * wa.year,
)
# 0.00706×
```

## LLM Inference

Token-based profiles cover three broad inference classes:

```python
wa.ai.frontier_llm(10_000 * wa.token)
wa.ai.efficient_llm(10_000 * wa.token)
wa.ai.local_llm(10_000 * wa.token)
```

`frontier_llm` is a state-of-the-art capability-class scenario, while
`efficient_llm` represents a smaller high-throughput hosted model. They are not
measurements of DeepSeek or another named provider. Their prototype energy per
million tokens, data-center PUE, and grid intensity are visible and overrideable:

```python
wa.ai.frontier_llm(
    1 * wa.million_token,
    energy_per_million_tokens=wa.Q_("1.2 kWh / million_token"),
    pue=1.15,
    grid_intensity=wa.Q_("300 g_co2e / kWh"),
)
```

Local inference is calculated from device power and measured throughput:

```python
wa.ai.local_llm(
    10_000 * wa.token,
    device_power=wa.Q_("180 W"),
    throughput=wa.Q_("45 token / second"),
)
```

All LLM profiles currently cover operational inference only. They exclude
training, hardware manufacture, networking, and the end-user device unless
explicitly stated otherwise.

Hosted profiles can account for prefix-cache reads:

```python
uncached = wa.ai.frontier_llm(1 * wa.million_token)
cached = wa.ai.frontier_llm(
    1 * wa.million_token,
    cache_read_ratio=0.95,
)

uncached / cached
# 6.9×
```

Cached tokens are not assumed to be free. The prototype default charges them
at 10% of uncached-token energy:

```text
energy multiplier = 0.05 + 0.95 × 0.10 = 0.145
```

Override that assumption when better provider-specific data is available:

```python
wa.ai.frontier_llm(
    1 * wa.million_token,
    cache_read_ratio=0.95,
    cache_read_energy_factor=0.05,
)
```

`cache_read_ratio` is cached input tokens divided by all tokens supplied to the
asset. If an API reports the ratio over input tokens only, calculate cached
input tokens divided by input plus output tokens first. Cache parameters are not
available on `local_llm`, whose model is based on output throughput and device
power.

## Flights, Trees, Parcels, And Waste

Flights use one asset with a fixed takeoff-and-landing component and two
distance-dependent cruise rates, so short flights are worse per kilometer:

```python
wa.transport.flight(800 * wa.km)
wa.transport.flight(6000 * wa.km, cabin_class="business")
wa.transport.flight_private(500 * wa.km, passengers=4)
```

The prototype default applies a `non_co2_multiplier=2.0` for contrails and
NOₓ effects (set `1` for CO₂-only). Sources below a flight's minimum
takeoff-and-landing impact raise `NoEquivalentAmountError`.

Trees grow quadratically and return negative impacts:

```python
tree = wa.nature.tree_growth(30 * wa.year)
tree.impact()["climate"]
# -236 kg_co2e

wa.electronics.phone() / wa.nature.tree_growth
# 16.3 year of growth needed to absorb one phone

wa.nature.tree_growth(30 * wa.year) / wa.electronics.phone()
# -3.38×    negative ratios flow through by design
```

Everyday comparisons:

```python
wa.food.meal_vegan(1)  # ≈ 0.7 kg CO2e per meal
wa.electronics.laptop_use(8 * wa.hour)  # M-series MacBook-like 10 W average
wa.waste.mixed(20 * wa.kg)  # residual waste to incineration
wa.shipping.parcel_from_china(1)  # air freight
wa.shipping.parcel_from_china(1, mode="rail")  # overland rail
```

## Lifestyle Benchmarks

Lifestyle assets put an activity next to the average consumption-based CO2
emissions of a resident over a duration:

```python
daily = wa.lifestyle.swiss_resident(1 * wa.day)
comparison = wa.food.cervelat(100 * wa.gram) / daily

comparison.percentage
# 1.6

wa.lifestyle.european_resident(1 * wa.year)
wa.lifestyle.us_resident(1 * wa.day)
wa.lifestyle.china_resident(1 * wa.day)
wa.lifestyle.india_resident(1 * wa.day)
```

These benchmarks use Global Carbon Budget 2025 consumption-based CO2 values
for 2023. They adjust national fossil-and-industry CO2 for trade, but exclude
other greenhouse gases, land-use change, and international aviation and
shipping. They are useful reference points, not complete personal footprints.

## Units And Formatting

Common units are exported directly:

```python
wa.nanosecond
wa.microsecond
wa.millisecond
wa.second
wa.minute
wa.hour
wa.day
wa.week
wa.year

wa.W
wa.kW
wa.Wh
wa.kWh
wa.MWh

wa.mg
wa.gram
wa.kg
wa.tonne

wa.g_co2e
wa.kg_co2e
wa.tonne_co2e
```

Representations automatically select readable units for scalar quantities:

```python
wa.format_quantity(3_153 * wa.second)  # '52.5 min'
wa.format_quantity(2_500 * wa.m)  # '2.5 km'

wa.ai.frontier_llm(1e6) / wa.buildings.house_1960s(120 * wa.m2)
# 52.5 min
```

Equivalent amounts preserve the target asset's semantic unit. Boiled-water
equivalents stay in liters, train equivalents in kilometers, and cervelat
equivalents in millimeters. Automatic scaling applies to residual quantities
such as durations where no target unit is applicable.

Compound reporting bases remain stable rather than being converted to smaller
time units:

```python
wa.buildings.house_1990s(120 * wa.m2) / wa.electronics.phone()
# 42.3 phone_device / year
```

## Configuration

The default context models Switzerland. Contexts are immutable and temporary
overrides do not leak outside their `with` block:

```python
with wa.context(
    region="DE",
    grid_intensity=0.35 * wa.kg_co2e / wa.kWh,
    heating_oil_intensity=0.267 * wa.kg_co2e / wa.kWh,
):
    result = wa.transport.ev(100 * wa.km) / wa.transport.train
```

An explicit context can also be passed directly:

```python
custom = wa.Context(grid_intensity=0.02 * wa.kg_co2e / wa.kWh)
impact = wa.household.boil_water(1 * wa.liter).impact(custom)
```

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
