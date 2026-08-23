# WattAbout

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

A bare asset on the right produces an equivalent amount. A concrete activity
on the right produces a dimensionless impact ratio:

```python
equivalent = wa.food.cervelat(10 * wa.cm) / wa.transport.train
print(equivalent)  # 79.2 km
print(equivalent.amount)  # 79.2 kilometer

ratio = wa.food.cervelat(10 * wa.cm) / wa.transport.train(10 * wa.km)
print(ratio)  # 7.92×
print(ratio.ratio)  # 7.92
float(ratio)  # 7.92
```

Detailed provenance and assumptions remain available:

```python
print(equivalent.explain())
```

## Categories

```python
wa.categories()
# ('building', 'electronics', 'energy', 'food', 'heating', 'household', 'transport')

wa.transport.assets()
# ('bus', 'ev', 'petrol_car', 'train')

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
| `transport` | `bus`, `ev`, `petrol_car`, `train` |
| `electronics` | `laptop`, `phone`, `phone_charge` |
| `food` | `cervelat`, `cheese`, `coffee`, `tofu` |
| `household` | `boil_water`, `dishwasher`, `led_light`, `oven`, `refrigerator` |
| `energy` | `electricity`, `natural_gas` |
| `heating` | `electric_resistance`, `gas_boiler`, `heat_pump`, `oil_boiler` |
| `building` | `custom`, `house_1960s`, `house_1980`, `house_1990`, `house_2000`, `minergie` |

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

Refrigerators intentionally use average load, and dishwashers use energy per
complete cycle rather than simulating internal phases.

## Heating And Buildings

Heating assets accept delivered useful heat in `kWh_th`:

```python
wa.heating.heat_pump(10_000 * wa.kWh_th, scop=3.5)
wa.heating.oil_boiler(10_000 * wa.kWh_th, efficiency=0.8)
```

Building profiles combine floor area, duration, specific useful heat demand,
and a heating system:

```python
modern = wa.building.minergie(
    150 * wa.m2,
    heating=wa.heating.heat_pump,
    heating_parameters={"scop": 3.5},
)

old = wa.building.house_1960s(
    150 * wa.m2,
    heating=wa.heating.oil_boiler,
    heating_parameters={"efficiency": 0.8},
)

modern / old
# 0.0141× under the prototype defaults
```

Additional decade archetypes are available through either `building` or its
`buildings` convenience alias:

```python
wa.buildings.house_1980(150 * wa.m2)  # 150 kWh_th / m² / year, oil boiler
wa.buildings.house_1990(150 * wa.m2)  # 110 kWh_th / m² / year, gas boiler
wa.buildings.house_2000(150 * wa.m2)  # 75 kWh_th / m² / year, gas boiler
```

The decade values and default heating systems are illustrative archetypes. Both
can be overridden with `specific_heat_demand`, `heating`, and
`heating_parameters`.

The `minergie` profile is an illustrative operational space-heating scenario,
not a MINERGIE certification calculation. Building profiles exclude domestic
hot water, cooling, appliances, and embodied impacts.

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
