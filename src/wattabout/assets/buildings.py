from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pint import Quantity

from ..context import Context
from ..core import (
    Asset,
    ConfiguredAsset,
    Impact,
    LinearEquivalence,
    Parameter,
    Source,
    WattAboutError,
)
from ..units import Q_, ureg
from .common import quantity_prepare
from .heating import gas_boiler, heat_pump, oil_boiler

MINERGIE_SOURCE = Source(
    name="MINERGIE operational scenario",
    citation=(
        "Illustrative 35 kWh_th/m²/year scenario informed by the MINERGIE standard overview; "
        "not a certification calculation"
    ),
    url="https://www.minergie.ch/de/standards/neubau/minergie/",
)
HOUSE_1960S_SOURCE = Source(
    name="1960s building archetype",
    citation=(
        "Illustrative unrenovated 1960s Swiss house demand of 180 kWh_th/m²/year; "
        "replace before scientific use"
    ),
)
CUSTOM_BUILDING_SOURCE = Source(
    name="User-configured building",
    citation="User-configured specific useful space-heating demand",
)
DEFAULT_FLOOR_AREA_SOURCE = Source(
    name="Swiss average floor area",
    citation=(
        "Prototype default heated floor area of 120 m², informed by the Swiss Federal "
        "Statistical Office building and dwelling statistics (average dwelling: 102 m² "
        "living space in 2024); replace before scientific use"
    ),
    url="https://www.bfs.admin.ch/bfs/de/home/statistiken/bau-wohnungswesen.html",
)
DEFAULT_FLOOR_AREA = Q_(120, "m^2")


def _building_model(
    *,
    default_demand: str | None,
    default_heating: Asset | None,
    profile_source: Source,
):
    def calculate(area: Quantity, parameters: Mapping[str, Any], context: Context) -> Impact:
        floor_area = area.to("m^2")
        if floor_area.magnitude <= 0:
            raise WattAboutError("building floor area must be greater than zero")
        demand_value = parameters.get("specific_heat_demand", default_demand)
        if demand_value is None:
            raise WattAboutError("specific_heat_demand is required")
        demand = Q_(demand_value).to("kWh_th / m^2 / year")
        if demand.magnitude < 0:
            raise WattAboutError("specific_heat_demand must be nonnegative")
        useful_heat_rate = (floor_area * demand).to("kWh_th / year")
        annual_useful_heat = (useful_heat_rate * Q_(1, "year")).to("kWh_th")

        heating = parameters.get("heating", default_heating)
        if not isinstance(heating, (Asset, ConfiguredAsset)):
            raise WattAboutError("heating must be a heating Asset or ConfiguredAsset")
        heating_asset = heating.asset if isinstance(heating, ConfiguredAsset) else heating
        if heating_asset.category != "heating":
            raise WattAboutError("heating must come from the heating category")
        heating_parameters = parameters.get("heating_parameters", {})
        if not isinstance(heating_parameters, Mapping):
            raise WattAboutError("heating_parameters must be a mapping")
        if isinstance(heating, ConfiguredAsset):
            if heating_parameters:
                raise WattAboutError(
                    "heating_parameters cannot be used with a configured heating asset"
                )
            heating_activity = heating(annual_useful_heat)
        else:
            heating_activity = heating(annual_useful_heat, **heating_parameters)
        heating_impact = heating_activity.impact(context)
        source = Source(
            name=f"{profile_source.name} with {heating_asset.name}",
            citation=profile_source.citation,
            url=profile_source.url,
            components=(heating_impact.source,),
        )
        return Impact(
            values={
                metric: value / Q_(1, "year") for metric, value in heating_impact.values.items()
            },
            source=source,
            geography=context.region,
            reference_year=context.year,
            boundary="operational_space_heating",
            dataset=context.dataset,
            assumptions=(
                f"Heated floor area: {floor_area:~}",
                f"Specific useful heat demand: {demand:~}",
                "Annual operating rate",
                "Space heating only; excludes hot water, cooling, appliances, and embodied impacts",
                *heating_impact.assumptions,
            ),
            is_rate=True,
        )

    return calculate


def _building_parameters(
    *, required_demand: bool = False, required_heating: bool = False
) -> tuple[Parameter, ...]:
    return (
        Parameter("duration", "optional duration used to integrate the annual rate", None),
        Parameter(
            "specific_heat_demand",
            "annual useful space-heat demand per floor area",
            None if required_demand else "profile default",
            required=required_demand,
        ),
        Parameter(
            "heating",
            "heating Asset or ConfiguredAsset",
            None if required_heating else "profile default",
            required=required_heating,
        ),
        Parameter("heating_parameters", "parameters passed to the heating asset", "{}"),
    )


def _period_house(
    *,
    year: int,
    demand: int,
    default_heating: Asset,
) -> Asset:
    source = Source(
        name=f"{year}s building archetype",
        citation=(
            f"Illustrative Swiss {year}s house demand of {demand} kWh_th/m²/year; "
            "replace before scientific use"
        ),
    )
    return Asset(
        id=f"buildings.house_{year}s",
        name=f"typical {year}s house space heating",
        default_input_unit=ureg.meter**2,
        default_comparison_unit=ureg.meter**2,
        prepare=quantity_prepare("m^2"),
        impact_model=_building_model(
            default_demand=f"{demand} kWh_th / m^2 / year",
            default_heating=default_heating,
            profile_source=source,
        ),
        equivalence=LinearEquivalence(),
        amount_name="floor_area",
        default_amount=DEFAULT_FLOOR_AREA,
        description=(
            f"Illustrative annual space-heating scenario for a typical {year}s house "
            f"using {demand} kWh_th/m²/year."
        ),
        parameters=_building_parameters(),
        examples=(
            f"wa.buildings.house_{year}s(150 * wa.m2)",
            "wa.buildings.minergie()  # Swiss-average prototype floor area",
        ),
        is_rate=True,
        integration_parameter="duration",
    )


minergie = Asset(
    id="buildings.minergie",
    name="MINERGIE-like new-building space heating",
    default_input_unit=ureg.meter**2,
    default_comparison_unit=ureg.meter**2,
    prepare=quantity_prepare("m^2"),
    impact_model=_building_model(
        default_demand="35 kWh_th / m^2 / year",
        default_heating=heat_pump,
        profile_source=MINERGIE_SOURCE,
    ),
    equivalence=LinearEquivalence(),
    amount_name="floor_area",
    default_amount=DEFAULT_FLOOR_AREA,
    description=(
        "Illustrative MINERGIE-like operational space-heating scenario, not a certification model."
    ),
    parameters=_building_parameters(),
    examples=(
        "wa.buildings.minergie(150 * wa.m2)",
        "wa.buildings.minergie(150 * wa.m2, heating=wa.heating.heat_pump)",
    ),
    is_rate=True,
    integration_parameter="duration",
)

house_1960s = Asset(
    id="buildings.house_1960s",
    name="unrenovated 1960s house space heating",
    default_input_unit=ureg.meter**2,
    default_comparison_unit=ureg.meter**2,
    prepare=quantity_prepare("m^2"),
    impact_model=_building_model(
        default_demand="180 kWh_th / m^2 / year",
        default_heating=oil_boiler,
        profile_source=HOUSE_1960S_SOURCE,
    ),
    equivalence=LinearEquivalence(),
    amount_name="floor_area",
    default_amount=DEFAULT_FLOOR_AREA,
    description="Illustrative annual space-heating scenario for an unrenovated 1960s house.",
    parameters=_building_parameters(),
    examples=(
        "wa.buildings.house_1960s(150 * wa.m2)",
        "wa.buildings.house_1960s(150 * wa.m2, heating=wa.heating.oil_boiler)",
    ),
    is_rate=True,
    integration_parameter="duration",
)

house_1980s = _period_house(
    year=1980,
    demand=150,
    default_heating=oil_boiler,
)

house_1990s = _period_house(
    year=1990,
    demand=110,
    default_heating=gas_boiler,
)

house_2000s = _period_house(
    year=2000,
    demand=75,
    default_heating=gas_boiler,
)

custom = Asset(
    id="buildings.custom",
    name="custom building space heating",
    default_input_unit=ureg.meter**2,
    default_comparison_unit=ureg.meter**2,
    prepare=quantity_prepare("m^2"),
    impact_model=_building_model(
        default_demand=None,
        default_heating=None,
        profile_source=CUSTOM_BUILDING_SOURCE,
    ),
    equivalence=LinearEquivalence(),
    amount_name="floor_area",
    default_amount=DEFAULT_FLOOR_AREA,
    description="User-configured annual operational space-heating scenario.",
    parameters=_building_parameters(required_demand=True, required_heating=True),
    examples=(
        "wa.buildings.custom(150 * wa.m2, specific_heat_demand=wa.Q_('90 kWh_th / m^2 / year'), heating=wa.heating.gas_boiler)",
    ),
    is_rate=True,
    integration_parameter="duration",
)

ASSETS = (minergie, house_1960s, house_1980s, house_1990s, house_2000s, custom)
