from .assets import registry
from .context import Context, context, get_context
from .core import (
    Activity,
    AnalyticEquivalence,
    Asset,
    Comparison,
    ConfiguredAsset,
    Impact,
    LinearEquivalence,
    MissingMetricError,
    MissingParameterError,
    NoEquivalentAmountError,
    Parameter,
    Source,
    WattAboutError,
)
from .units import (
    MJ,
    Q_,
    cm,
    coffee_cup,
    degC,
    dishwasher_cycle,
    g_co2e,
    gram,
    hour,
    kg,
    kg_co2e,
    km,
    kWh,
    kWh_th,
    laptop_device,
    liter,
    m,
    m2,
    minute,
    mm,
    phone_charge,
    phone_device,
    ureg,
    year,
)

building = registry.namespace("building")
buildings = building
electronics = registry.namespace("electronics")
energy = registry.namespace("energy")
food = registry.namespace("food")
heating = registry.namespace("heating")
household = registry.namespace("household")
transport = registry.namespace("transport")


def categories() -> tuple[str, ...]:
    return registry.categories()


__all__ = [
    "MJ",
    "Q_",
    "Activity",
    "AnalyticEquivalence",
    "Asset",
    "Comparison",
    "ConfiguredAsset",
    "Context",
    "Impact",
    "LinearEquivalence",
    "MissingMetricError",
    "MissingParameterError",
    "NoEquivalentAmountError",
    "Parameter",
    "Source",
    "WattAboutError",
    "building",
    "buildings",
    "categories",
    "cm",
    "coffee_cup",
    "context",
    "degC",
    "dishwasher_cycle",
    "electronics",
    "energy",
    "food",
    "g_co2e",
    "get_context",
    "gram",
    "heating",
    "hour",
    "household",
    "kWh",
    "kWh_th",
    "kg",
    "kg_co2e",
    "km",
    "laptop_device",
    "liter",
    "m",
    "m2",
    "minute",
    "mm",
    "phone_charge",
    "phone_device",
    "registry",
    "transport",
    "ureg",
    "year",
]
