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
        duration = Q_(parameters.get("duration", "1 year")).to("year")
        if duration.magnitude <= 0:
            raise WattAboutError("duration must be greater than zero")
        demand_value = parameters.get("specific_heat_demand", default_demand)
        if demand_value is None:
            raise WattAboutError("specific_heat_demand is required")
        demand = Q_(demand_value).to("kWh_th / m^2 / year")
        if demand.magnitude < 0:
            raise WattAboutError("specific_heat_demand must be nonnegative")
        useful_heat = (floor_area * demand * duration).to("kWh_th")

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
            heating_activity = heating(useful_heat)
        else:
            heating_activity = heating(useful_heat, **heating_parameters)
        heating_impact = heating_activity.impact(context)
        source = Source(
            name=f"{profile_source.name} with {heating_asset.name}",
            citation=profile_source.citation,
            url=profile_source.url,
            components=(heating_impact.source,),
        )
        return Impact(
            values=heating_impact.values,
            source=source,
            geography=context.region,
            reference_year=context.year,
            boundary="operational_space_heating",
            dataset=context.dataset,
            assumptions=(
                f"Heated floor area: {floor_area:~}",
                f"Specific useful heat demand: {demand:~}",
                f"Duration: {duration:~}",
                "Space heating only; excludes hot water, cooling, appliances, and embodied impacts",
                *heating_impact.assumptions,
            ),
        )

    return calculate


def _building_parameters(
    *, required_demand: bool = False, required_heating: bool = False
) -> tuple[Parameter, ...]:
    return (
        Parameter("duration", "operating duration", "1 year"),
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
        id=f"building.house_{year}",
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
        description=(
            f"Illustrative annual space-heating scenario for a typical {year}s house "
            f"using {demand} kWh_th/m²/year."
        ),
        parameters=_building_parameters(),
        examples=(f"wa.building.house_{year}(150 * wa.m2)",),
    )


minergie = Asset(
    id="building.minergie",
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
    description=(
        "Illustrative MINERGIE-like operational space-heating scenario, not a certification model."
    ),
    parameters=_building_parameters(),
    examples=(
        "wa.building.minergie(150 * wa.m2)",
        "wa.building.minergie(150 * wa.m2, heating=wa.heating.heat_pump)",
    ),
)

house_1960s = Asset(
    id="building.house_1960s",
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
    description="Illustrative annual space-heating scenario for an unrenovated 1960s house.",
    parameters=_building_parameters(),
    examples=(
        "wa.building.house_1960s(150 * wa.m2)",
        "wa.building.house_1960s(150 * wa.m2, heating=wa.heating.oil_boiler)",
    ),
)

house_1980 = _period_house(
    year=1980,
    demand=150,
    default_heating=oil_boiler,
)

house_1990 = _period_house(
    year=1990,
    demand=110,
    default_heating=gas_boiler,
)

house_2000 = _period_house(
    year=2000,
    demand=75,
    default_heating=gas_boiler,
)

custom = Asset(
    id="building.custom",
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
    description="User-configured annual operational space-heating scenario.",
    parameters=_building_parameters(required_demand=True, required_heating=True),
    examples=(
        "wa.building.custom(150 * wa.m2, specific_heat_demand=wa.Q_('90 kWh_th / m^2 / year'), heating=wa.heating.gas_boiler)",
    ),
)

ASSETS = (minergie, house_1960s, house_1980, house_1990, house_2000, custom)
