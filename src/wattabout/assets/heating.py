from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pint import Quantity

from ..context import Context
from ..core import Asset, Impact, LinearEquivalence, Parameter, Source, WattAboutError
from ..units import Q_, ureg
from .common import ENERGY_SOURCE, PHYSICAL_MODEL_SOURCE, quantity_prepare
from .energy import wood_pellets

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
PELLET_BOILER_SOURCE = Source(
    name="Wood pellet boiler model",
    citation="Prototype seasonal pellet-boiler conversion using the wood pellet fuel model",
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
            *context.electricity_assumptions,
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
            *context.electricity_assumptions,
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


def _pellet_boiler_impact(
    useful_heat: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    heat = _physical_energy(useful_heat)
    efficiency = float(parameters.get("efficiency", 0.85))
    if not 0 < efficiency <= 1:
        raise WattAboutError("efficiency must be greater than zero and at most one")
    lower_heating_value = Q_(parameters.get("lower_heating_value", "4.8 kWh / kg")).to("kWh / kg")
    if lower_heating_value.magnitude <= 0:
        raise WattAboutError("lower_heating_value must be positive")
    fuel_energy = (heat / efficiency).to("kWh")
    pellet_mass = (fuel_energy / lower_heating_value).to("kg")
    pellet_activity = wood_pellets(
        pellet_mass,
        lower_heating_value=lower_heating_value,
        supply_chain_intensity=parameters.get("supply_chain_intensity", "0.025 kg_co2e / kWh"),
        non_co2_combustion_intensity=parameters.get(
            "non_co2_combustion_intensity", "0.005 kg_co2e / kWh"
        ),
        biogenic_stack_co2_factor=parameters.get("biogenic_stack_co2_factor", "1.8 kg_co2e / kg"),
        include_biogenic_co2=parameters.get("include_biogenic_co2", True),
    )
    pellet_impact = pellet_activity.impact(context)
    return Impact(
        values={"climate": pellet_impact["climate"]},
        source=Source(
            name="Pellet boiler with wood pellet supply",
            citation=PELLET_BOILER_SOURCE.citation,
            components=(pellet_impact.source,),
        ),
        geography=context.region,
        reference_year=context.year,
        boundary="cradle_to_boiler_gate_and_combustion",
        dataset=context.dataset,
        assumptions=(
            f"Seasonal boiler efficiency: {efficiency:.0%}",
            f"Useful heat delivered: {useful_heat.to('kWh_th'):~}",
            f"Pellet fuel energy: {fuel_energy:~}",
            f"Pellet mass: {pellet_mass:~}",
            *pellet_impact.assumptions,
        ),
    )


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

pellet_boiler = Asset(
    id="heating.pellet_boiler",
    name="wood pellet boiler heating",
    default_input_unit=ureg.kWh_th,
    default_comparison_unit=ureg.kWh_th,
    prepare=quantity_prepare("kWh_th"),
    impact_model=_pellet_boiler_impact,
    equivalence=LinearEquivalence(),
    amount_name="useful_heat",
    description="Useful heat from a pellet boiler using the wood pellet fuel model.",
    parameters=(
        Parameter("efficiency", "seasonal useful-heat efficiency", 0.85),
        Parameter("lower_heating_value", "pellet net calorific value", "4.8 kWh / kg"),
        Parameter(
            "supply_chain_intensity",
            "forestry, processing, and transport impact per fuel energy",
            "0.025 kg_co2e / kWh",
        ),
        Parameter(
            "non_co2_combustion_intensity",
            "methane and nitrous oxide impact per fuel energy",
            "0.005 kg_co2e / kWh",
        ),
        Parameter(
            "biogenic_stack_co2_factor",
            "gross biogenic stack CO2 per pellet mass",
            "1.8 kg_co2e / kg",
        ),
        Parameter(
            "include_biogenic_co2",
            "include gross biogenic stack CO2 in the climate metric",
            True,
        ),
    ),
    examples=("wa.heating.pellet_boiler(10000 * wa.kWh_th)",),
)

ASSETS = (heat_pump, oil_boiler, gas_boiler, electric_resistance, pellet_boiler)
