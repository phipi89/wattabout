from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pint import Quantity

from ..context import Context
from ..core import Asset, Impact, LinearEquivalence, Parameter, Source, WattAboutError
from ..units import Q_, ureg
from .common import ENERGY_SOURCE, PHYSICAL_MODEL_SOURCE, quantity_prepare

HEAT_PUMP_SOURCE = Source(
    name="Heat pump operational model",
    citation="Prototype seasonal heat-pump performance model; replace before scientific use",
    components=(PHYSICAL_MODEL_SOURCE,),
)
BOILER_SOURCE = Source(
    name="Boiler operational model",
    citation="Prototype seasonal boiler performance model; replace before scientific use",
    components=(ENERGY_SOURCE,),
)


def _physical_energy(useful_heat: Quantity) -> Quantity:
    return useful_heat.to("kWh_th").magnitude * Q_(1, "kWh")


def _heating_impact(
    useful_heat: Quantity,
    parameters: Mapping[str, Any],
    context: Context,
    *,
    system: str,
) -> Impact:
    heat = _physical_energy(useful_heat)
    assumptions: list[str]
    if system == "heat_pump":
        efficiency = float(parameters.get("scop", 3.5))
        if efficiency <= 0:
            raise WattAboutError("scop must be greater than zero")
        energy_input = heat / efficiency
        climate = (energy_input * context.grid_intensity).to("kg_co2e")
        source = HEAT_PUMP_SOURCE
        assumptions = [
            f"Seasonal coefficient of performance: {efficiency:g}",
            f"Grid intensity: {context.grid_intensity:~}",
        ]
    elif system == "electric_resistance":
        efficiency = float(parameters.get("efficiency", 1.0))
        if not 0 < efficiency <= 1:
            raise WattAboutError("efficiency must be greater than zero and at most one")
        energy_input = heat / efficiency
        climate = (energy_input * context.grid_intensity).to("kg_co2e")
        source = PHYSICAL_MODEL_SOURCE
        assumptions = [
            f"Heating efficiency: {efficiency:.0%}",
            f"Grid intensity: {context.grid_intensity:~}",
        ]
    else:
        efficiency = float(parameters.get("efficiency", 0.8 if system == "oil" else 0.9))
        if not 0 < efficiency <= 1:
            raise WattAboutError("efficiency must be greater than zero and at most one")
        energy_input = heat / efficiency
        intensity = (
            context.heating_oil_intensity if system == "oil" else context.natural_gas_intensity
        )
        climate = (energy_input * intensity).to("kg_co2e")
        source = BOILER_SOURCE
        assumptions = [
            f"Seasonal boiler efficiency: {efficiency:.0%}",
            f"Fuel intensity: {intensity:~}",
        ]
    return Impact(
        values={"climate": climate},
        source=source,
        geography=context.region,
        reference_year=context.year,
        boundary="operational_space_heating",
        dataset=context.dataset,
        assumptions=tuple(assumptions),
    )


def _heat_pump_impact(
    useful_heat: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    return _heating_impact(useful_heat, parameters, context, system="heat_pump")


def _oil_boiler_impact(
    useful_heat: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    return _heating_impact(useful_heat, parameters, context, system="oil")


def _gas_boiler_impact(
    useful_heat: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    return _heating_impact(useful_heat, parameters, context, system="gas")


def _resistance_impact(
    useful_heat: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    return _heating_impact(useful_heat, parameters, context, system="electric_resistance")


heat_pump = Asset(
    id="heating.heat_pump",
    name="heat pump space heating",
    default_input_unit=ureg.kWh_th,
    default_comparison_unit=ureg.kWh_th,
    prepare=quantity_prepare("kWh_th"),
    impact_model=_heat_pump_impact,
    equivalence=LinearEquivalence(),
    amount_name="useful_heat",
    description="Useful space heat delivered by an electric heat pump.",
    parameters=(Parameter("scop", "seasonal coefficient of performance", "3.5"),),
    examples=("wa.heating.heat_pump(10_000 * wa.kWh_th, scop=3.5)",),
)

oil_boiler = Asset(
    id="heating.oil_boiler",
    name="oil boiler space heating",
    default_input_unit=ureg.kWh_th,
    default_comparison_unit=ureg.kWh_th,
    prepare=quantity_prepare("kWh_th"),
    impact_model=_oil_boiler_impact,
    equivalence=LinearEquivalence(),
    amount_name="useful_heat",
    description="Useful space heat delivered by a heating-oil boiler.",
    parameters=(Parameter("efficiency", "seasonal boiler efficiency", "0.8"),),
    examples=("wa.heating.oil_boiler(10_000 * wa.kWh_th, efficiency=0.8)",),
)

gas_boiler = Asset(
    id="heating.gas_boiler",
    name="gas boiler space heating",
    default_input_unit=ureg.kWh_th,
    default_comparison_unit=ureg.kWh_th,
    prepare=quantity_prepare("kWh_th"),
    impact_model=_gas_boiler_impact,
    equivalence=LinearEquivalence(),
    amount_name="useful_heat",
    description="Useful space heat delivered by a natural-gas boiler.",
    parameters=(Parameter("efficiency", "seasonal boiler efficiency", "0.9"),),
    examples=("wa.heating.gas_boiler(10_000 * wa.kWh_th)",),
)

electric_resistance = Asset(
    id="heating.electric_resistance",
    name="electric resistance space heating",
    default_input_unit=ureg.kWh_th,
    default_comparison_unit=ureg.kWh_th,
    prepare=quantity_prepare("kWh_th"),
    impact_model=_resistance_impact,
    equivalence=LinearEquivalence(),
    amount_name="useful_heat",
    description="Useful space heat delivered by direct electric resistance heating.",
    parameters=(Parameter("efficiency", "electricity-to-heat efficiency", "1.0"),),
    examples=("wa.heating.electric_resistance(10_000 * wa.kWh_th)",),
)

ASSETS = (heat_pump, oil_boiler, gas_boiler, electric_resistance)
