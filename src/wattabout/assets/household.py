from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pint import DimensionalityError, Quantity

from ..context import Context
from ..core import (
    AnalyticEquivalence,
    Asset,
    ConfiguredAsset,
    Impact,
    LinearEquivalence,
    NoEquivalentAmountError,
    Parameter,
    Source,
    WattAboutError,
)
from ..units import Q_, ureg
from .common import PHYSICAL_MODEL_SOURCE, quantity_prepare
from .heating import electric_resistance

WATER_SERVICES_SOURCE = Source(
    name="Water services prototype factor",
    citation=(
        "Illustrative combined drinking-water supply and wastewater treatment factor; "
        "replace with a regional utility factor before scientific use"
    ),
)
LAUNDRY_SOURCE = Source(
    name="Laundry prototype model",
    citation=(
        "Representative modern household appliance, water, and detergent assumptions; "
        "replace with appliance-specific values before scientific use"
    ),
    components=(PHYSICAL_MODEL_SOURCE, WATER_SERVICES_SOURCE),
)


def _boil_water_impact(volume: Quantity, parameters: Mapping[str, Any], context: Context) -> Impact:
    start_temperature = Q_(parameters.get("start_temperature", context.water_inlet_temperature)).to(
        "degC"
    )
    end_temperature = Q_(parameters.get("end_temperature", "100 degC")).to("degC")
    efficiency = float(parameters.get("efficiency", context.kettle_efficiency))
    if not 0 < efficiency <= 1:
        raise WattAboutError("efficiency must be greater than zero and at most one")
    temperature_rise = end_temperature.magnitude - start_temperature.magnitude
    if temperature_rise < 0:
        raise WattAboutError("end_temperature must not be below start_temperature")
    mass = volume.to("liter").magnitude * Q_(1, "kg")
    energy = mass * Q_(4.186, "kJ / kg / kelvin") * temperature_rise * ureg.kelvin
    electricity = (energy / efficiency).to("kWh")
    climate = (electricity * context.grid_intensity).to("kg_co2e")
    return Impact(
        values={"climate": climate},
        source=PHYSICAL_MODEL_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="operational",
        dataset=context.dataset,
        assumptions=(
            f"Water heated from {start_temperature:~} to {end_temperature:~}",
            f"Kettle efficiency: {efficiency:.0%}",
            f"Grid intensity: {context.grid_intensity:~}",
        ),
    )


def _led_light_impact(
    duration: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    power = Q_(parameters.get("power", "10 W")).to("kW")
    electricity = (power * duration.to("hour")).to("kWh")
    climate = (electricity * context.grid_intensity).to("kg_co2e")
    return Impact(
        values={"climate": climate},
        source=PHYSICAL_MODEL_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="operational",
        dataset=context.dataset,
        assumptions=(f"Lamp power: {power:~}", f"Grid intensity: {context.grid_intensity:~}"),
    )


def _led_light_rate_impact(_: Quantity, parameters: Mapping[str, Any], context: Context) -> Impact:
    power = Q_(parameters.get("power", "10 W")).to("kW")
    if power.magnitude < 0:
        raise WattAboutError("power must be nonnegative")
    climate = (power * context.grid_intensity).to("kg_co2e / hour")
    return Impact(
        values={"climate": climate},
        source=PHYSICAL_MODEL_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="operational",
        dataset=context.dataset,
        assumptions=(f"Lamp power: {power:~}", f"Grid intensity: {context.grid_intensity:~}"),
        is_rate=True,
    )


def _oven_energy(
    duration: Quantity, parameters: Mapping[str, Any]
) -> tuple[Quantity, Quantity, Quantity, Quantity]:
    temperature = Q_(parameters["temperature"]).to("degC")
    ambient = Q_(parameters.get("ambient_temperature", "20 degC")).to("degC")
    temperature_rise = temperature.magnitude - ambient.magnitude
    if temperature_rise <= 0:
        raise WattAboutError("temperature must be above ambient_temperature")
    scale = temperature_rise / 180
    preheat_at_200c = Q_(parameters.get("preheat_energy_at_200c", "0.5 kWh")).to("kWh")
    holding_at_200c = Q_(parameters.get("holding_power_at_200c", "0.8 kW")).to("kW")
    if preheat_at_200c.magnitude < 0 or holding_at_200c.magnitude <= 0:
        raise WattAboutError("oven preheat energy must be nonnegative and holding power positive")
    preheat = (
        preheat_at_200c * scale if parameters.get("include_preheating", True) else 0 * ureg.kWh
    )
    holding_power = holding_at_200c * scale
    cooking_duration = duration.to("hour")
    if cooking_duration.magnitude < 0:
        raise WattAboutError("oven cooking duration must be nonnegative")
    electricity = (preheat + holding_power * cooking_duration).to("kWh")
    return electricity, preheat, holding_power, temperature


def _oven_impact(duration: Quantity, parameters: Mapping[str, Any], context: Context) -> Impact:
    electricity, preheat, holding_power, temperature = _oven_energy(duration, parameters)
    climate = (electricity * context.grid_intensity).to("kg_co2e")
    return Impact(
        values={"climate": climate},
        source=PHYSICAL_MODEL_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="operational",
        dataset=context.dataset,
        assumptions=(
            f"Target temperature: {temperature:~}",
            f"Preheating energy: {preheat:~}",
            f"Average holding power: {holding_power:~}",
            f"Grid intensity: {context.grid_intensity:~}",
        ),
    )


def _oven_rate_impact(_: Quantity, parameters: Mapping[str, Any], context: Context) -> Impact:
    _, _, holding_power, temperature = _oven_energy(0 * ureg.minute, parameters)
    climate = (holding_power * context.grid_intensity).to("kg_co2e / hour")
    return Impact(
        values={"climate": climate},
        source=PHYSICAL_MODEL_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="operational",
        dataset=context.dataset,
        assumptions=(
            f"Target temperature: {temperature:~}",
            f"Average holding power: {holding_power:~}",
            "Preheated steady operation; excludes preheating",
            f"Grid intensity: {context.grid_intensity:~}",
        ),
        is_rate=True,
    )


def _solve_oven_duration(
    target_impact: Quantity,
    metric: str,
    unit: Any,
    parameters: Mapping[str, Any],
    context: Context,
) -> Quantity:
    if metric != "climate":
        raise NoEquivalentAmountError(f"Oven has no invertible {metric!r} metric")
    if context.grid_intensity.magnitude <= 0:
        raise NoEquivalentAmountError("Oven duration cannot be inferred with zero grid intensity")
    try:
        required_electricity = (target_impact / context.grid_intensity).to("kWh")
    except DimensionalityError as error:
        raise NoEquivalentAmountError(
            "A cold-start oven duration can only be inferred from an integrated impact"
        ) from error
    _, preheat, holding_power, _ = _oven_energy(0 * ureg.minute, parameters)
    remaining = required_electricity - preheat
    if remaining.magnitude < 0:
        raise NoEquivalentAmountError(
            "Source impact is below the oven's minimum cold-start impact; "
            "configure include_preheating=False or compare concrete activities"
        )
    return (remaining / holding_power).to(unit)


def _refrigerator_impact(
    duration: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    average_power = Q_(parameters.get("average_power", "30 W")).to("kW")
    if average_power.magnitude < 0:
        raise WattAboutError("average_power must be nonnegative")
    electricity = (average_power * duration.to("hour")).to("kWh")
    climate = (electricity * context.grid_intensity).to("kg_co2e")
    return Impact(
        values={"climate": climate},
        source=PHYSICAL_MODEL_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="operational",
        dataset=context.dataset,
        assumptions=(
            f"Average refrigerator power: {average_power:~}",
            f"Grid intensity: {context.grid_intensity:~}",
        ),
    )


def _refrigerator_rate_impact(
    _: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    average_power = Q_(parameters.get("average_power", "30 W")).to("kW")
    if average_power.magnitude < 0:
        raise WattAboutError("average_power must be nonnegative")
    climate = (average_power * context.grid_intensity).to("kg_co2e / hour")
    return Impact(
        values={"climate": climate},
        source=PHYSICAL_MODEL_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="operational",
        dataset=context.dataset,
        assumptions=(
            f"Average refrigerator power: {average_power:~}",
            f"Grid intensity: {context.grid_intensity:~}",
        ),
        is_rate=True,
    )


def _dishwasher_impact(cycles: Quantity, parameters: Mapping[str, Any], context: Context) -> Impact:
    cycle_count = cycles.to("dishwasher_cycle").magnitude
    if cycle_count < 0:
        raise WattAboutError("dishwasher cycles must be nonnegative")
    energy_per_cycle = Q_(parameters.get("energy_per_cycle", "0.8 kWh")).to("kWh")
    if energy_per_cycle.magnitude < 0:
        raise WattAboutError("energy_per_cycle must be nonnegative")
    electricity = cycle_count * energy_per_cycle
    climate = (electricity * context.grid_intensity).to("kg_co2e")
    return Impact(
        values={"climate": climate},
        source=PHYSICAL_MODEL_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="operational",
        dataset=context.dataset,
        assumptions=(
            f"Dishwasher energy per complete cycle: {energy_per_cycle:~}",
            f"Grid intensity: {context.grid_intensity:~}",
        ),
    )


def _hot_water_impact(
    volume: Quantity,
    parameters: Mapping[str, Any],
    context: Context,
    *,
    extra_assumptions: tuple[str, ...] = (),
) -> Impact:
    water = volume.to("liter")
    if water.magnitude < 0:
        raise WattAboutError("hot water volume must be nonnegative")
    inlet = Q_(parameters.get("inlet_temperature", context.water_inlet_temperature)).to("degC")
    target = Q_(parameters.get("temperature", "40 degC")).to("degC")
    temperature_rise = target.magnitude - inlet.magnitude
    if temperature_rise < 0:
        raise WattAboutError("temperature must not be below inlet_temperature")

    mass = water.magnitude * Q_(1, "kg")
    physical_heat = (mass * Q_(4.186, "kJ / kg / kelvin") * temperature_rise * ureg.kelvin).to(
        "kWh"
    )
    useful_heat = Q_(physical_heat.magnitude, "kWh_th")

    heating = parameters.get("heating", electric_resistance)
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

    water_intensity = Q_(
        parameters.get("water_services_intensity", context.water_services_intensity)
    ).to("kg_co2e / liter")
    if water_intensity.magnitude < 0:
        raise WattAboutError("water_services_intensity must be nonnegative")
    water_climate = (water * water_intensity).to("kg_co2e")
    climate = (heating_impact["climate"] + water_climate).to("kg_co2e")
    return Impact(
        values={"climate": climate},
        source=Source(
            name=f"Domestic hot water with {heating_asset.name}",
            citation="Physical hot-water model with heating and water-service impacts",
            components=(heating_impact.source, WATER_SERVICES_SOURCE),
        ),
        geography=context.region,
        reference_year=context.year,
        boundary="operational_domestic_hot_water",
        dataset=context.dataset,
        assumptions=(
            *extra_assumptions,
            f"Water volume: {water:~}",
            f"Water heated from {inlet:~} to {target:~}",
            f"Useful heat: {useful_heat:~}",
            f"Water services intensity: {water_intensity:~}",
            *heating_impact.assumptions,
        ),
    )


def _shower_impact(duration: Quantity, parameters: Mapping[str, Any], context: Context) -> Impact:
    time = duration.to("minute")
    if time.magnitude < 0:
        raise WattAboutError("shower duration must be nonnegative")
    flow_rate = Q_(parameters.get("flow_rate", "9 liter / minute")).to("liter / minute")
    if flow_rate.magnitude < 0:
        raise WattAboutError("flow_rate must be nonnegative")
    volume = (time * flow_rate).to("liter")
    return _hot_water_impact(
        volume,
        parameters,
        context,
        extra_assumptions=(f"Shower duration: {time:~}", f"Flow rate: {flow_rate:~}"),
    )


def _washing_machine_impact(
    cycles: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    cycle_count = cycles.to("laundry_cycle").magnitude
    if cycle_count < 0:
        raise WattAboutError("laundry cycles must be nonnegative")
    electricity_per_cycle = Q_(parameters.get("electricity_per_cycle", "0.6 kWh")).to("kWh")
    water_per_cycle = Q_(parameters.get("water_per_cycle", "50 liter")).to("liter")
    detergent_per_cycle = Q_(parameters.get("detergent_impact", "0.1 kg_co2e")).to("kg_co2e")
    water_intensity = Q_(
        parameters.get("water_services_intensity", context.water_services_intensity)
    ).to("kg_co2e / liter")
    if any(
        value.magnitude < 0
        for value in (
            electricity_per_cycle,
            water_per_cycle,
            detergent_per_cycle,
            water_intensity,
        )
    ):
        raise WattAboutError("laundry inputs must be nonnegative")
    electricity = cycle_count * electricity_per_cycle
    water = cycle_count * water_per_cycle
    climate = (
        electricity * context.grid_intensity
        + water * water_intensity
        + cycle_count * detergent_per_cycle
    ).to("kg_co2e")
    return Impact(
        values={"climate": climate},
        source=LAUNDRY_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="operational_laundry",
        dataset=context.dataset,
        assumptions=(
            f"Electricity per cycle: {electricity_per_cycle:~}",
            f"Water per cycle: {water_per_cycle:~}",
            f"Detergent impact per cycle: {detergent_per_cycle:~}",
            f"Water services intensity: {water_intensity:~}",
            f"Grid intensity: {context.grid_intensity:~}",
        ),
    )


def _tumble_dryer_impact(
    cycles: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    cycle_count = cycles.to("dryer_cycle").magnitude
    if cycle_count < 0:
        raise WattAboutError("dryer cycles must be nonnegative")
    electricity_per_cycle = Q_(parameters.get("electricity_per_cycle", "1.5 kWh")).to("kWh")
    if electricity_per_cycle.magnitude < 0:
        raise WattAboutError("electricity_per_cycle must be nonnegative")
    climate = (cycle_count * electricity_per_cycle * context.grid_intensity).to("kg_co2e")
    return Impact(
        values={"climate": climate},
        source=PHYSICAL_MODEL_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="operational_laundry",
        dataset=context.dataset,
        assumptions=(
            f"Electricity per drying cycle: {electricity_per_cycle:~}",
            f"Grid intensity: {context.grid_intensity:~}",
        ),
    )


boil_water = Asset(
    id="household.boil_water",
    name="water boiled in an electric kettle",
    default_input_unit=ureg.liter,
    default_comparison_unit=ureg.liter,
    prepare=quantity_prepare("liter"),
    impact_model=_boil_water_impact,
    equivalence=LinearEquivalence(),
    amount_name="volume",
    description="Water heated to boiling in an electric kettle.",
    parameters=(
        Parameter("start_temperature", "initial water temperature", "context value"),
        Parameter("end_temperature", "target water temperature", "100 degC"),
        Parameter("efficiency", "kettle heating efficiency", "context value"),
    ),
    examples=("wa.household.boil_water(1 * wa.liter)",),
)

led_light = Asset(
    id="household.led_light",
    name="LED light use",
    default_input_unit=ureg.hour,
    default_comparison_unit=ureg.hour,
    prepare=quantity_prepare("hour"),
    impact_model=_led_light_impact,
    equivalence=LinearEquivalence(),
    amount_name="duration",
    description="Operational electricity for an LED lamp over time.",
    parameters=(Parameter("power", "electrical power of the lamp", "10 W"),),
    examples=("wa.household.led_light(5 * wa.hour)",),
    rate_model=_led_light_rate_impact,
)

oven = Asset(
    id="household.oven",
    name="electric oven cooking session",
    default_input_unit=ureg.minute,
    default_comparison_unit=ureg.minute,
    prepare=quantity_prepare("minute"),
    impact_model=_oven_impact,
    equivalence=AnalyticEquivalence(_solve_oven_duration),
    amount_name="cooking_time",
    description="Electric oven cooking time with temperature-dependent preheating and holding energy.",
    parameters=(
        Parameter("temperature", "oven target temperature", required=True),
        Parameter("ambient_temperature", "oven starting temperature", "20 degC"),
        Parameter("include_preheating", "include cold-start preheating", True),
        Parameter("preheat_energy_at_200c", "prototype preheating energy at 200°C", "0.5 kWh"),
        Parameter("holding_power_at_200c", "prototype average holding power at 200°C", "0.8 kW"),
    ),
    examples=(
        "wa.household.oven(20 * wa.minute, temperature=200 * wa.degC)",
        "wa.household.oven.configure(temperature=200 * wa.degC)",
    ),
    rate_model=_oven_rate_impact,
    rate_activity_name="preheated electric oven operation",
)

refrigerator = Asset(
    id="household.refrigerator",
    name="refrigerator operation",
    default_input_unit=ureg.hour,
    default_comparison_unit=ureg.hour,
    prepare=quantity_prepare("hour"),
    impact_model=_refrigerator_impact,
    equivalence=LinearEquivalence(),
    amount_name="duration",
    description="Refrigerator operation represented by average electrical load.",
    parameters=(Parameter("average_power", "representative average electrical load", "30 W"),),
    examples=("wa.household.refrigerator(24 * wa.hour)",),
    rate_model=_refrigerator_rate_impact,
)

dishwasher = Asset(
    id="household.dishwasher",
    name="dishwasher cycle",
    default_input_unit=ureg.dishwasher_cycle,
    default_comparison_unit=ureg.dishwasher_cycle,
    prepare=quantity_prepare("dishwasher_cycle"),
    impact_model=_dishwasher_impact,
    equivalence=LinearEquivalence(),
    amount_name="cycles",
    description="A complete dishwasher program represented by energy per cycle.",
    parameters=(Parameter("energy_per_cycle", "electricity for one complete program", "0.8 kWh"),),
    examples=("wa.household.dishwasher(1)",),
)

hot_water = Asset(
    id="household.hot_water",
    name="domestic hot water",
    default_input_unit=ureg.liter,
    default_comparison_unit=ureg.liter,
    prepare=quantity_prepare("liter"),
    impact_model=_hot_water_impact,
    equivalence=LinearEquivalence(),
    amount_name="volume",
    description="Water heated for domestic use, including supply and wastewater services.",
    parameters=(
        Parameter("temperature", "target water temperature", "40 degC"),
        Parameter("inlet_temperature", "cold-water inlet temperature", "context value"),
        Parameter("heating", "heating Asset or ConfiguredAsset", "electric resistance"),
        Parameter("heating_parameters", "parameters passed to the heating asset", "{}"),
        Parameter(
            "water_services_intensity",
            "combined drinking-water and wastewater impact per volume",
            "context value",
        ),
    ),
    examples=(
        "wa.household.hot_water(50 * wa.liter)",
        "wa.household.hot_water(50 * wa.liter, heating=wa.heating.heat_pump)",
    ),
)

shower = Asset(
    id="household.shower",
    name="shower",
    default_input_unit=ureg.minute,
    default_comparison_unit=ureg.minute,
    default_amount=8 * ureg.minute,
    prepare=quantity_prepare("minute"),
    impact_model=_shower_impact,
    equivalence=LinearEquivalence(),
    amount_name="duration",
    description="A shower modeled from duration, water flow, temperature, and water heating.",
    parameters=(
        Parameter("flow_rate", "average shower water flow", "9 liter / minute"),
        Parameter("temperature", "shower water temperature", "40 degC"),
        Parameter("inlet_temperature", "cold-water inlet temperature", "context value"),
        Parameter("heating", "heating Asset or ConfiguredAsset", "electric resistance"),
        Parameter("heating_parameters", "parameters passed to the heating asset", "{}"),
        Parameter(
            "water_services_intensity",
            "combined drinking-water and wastewater impact per volume",
            "context value",
        ),
    ),
    examples=(
        "wa.household.shower(8 * wa.minute)",
        "wa.household.shower(5 * wa.minute, flow_rate='6 liter / minute')",
    ),
)

washing_machine = Asset(
    id="household.washing_machine",
    name="washing machine cycle",
    default_input_unit=ureg.laundry_cycle,
    default_comparison_unit=ureg.laundry_cycle,
    prepare=quantity_prepare("laundry_cycle"),
    impact_model=_washing_machine_impact,
    equivalence=LinearEquivalence(),
    amount_name="cycles",
    description="A complete laundry cycle including electricity, water services, and detergent.",
    parameters=(
        Parameter("electricity_per_cycle", "electricity for one wash cycle", "0.6 kWh"),
        Parameter("water_per_cycle", "water used for one wash cycle", "50 liter"),
        Parameter("detergent_impact", "detergent lifecycle impact per cycle", "0.1 kg_co2e"),
        Parameter(
            "water_services_intensity",
            "combined drinking-water and wastewater impact per volume",
            "context value",
        ),
    ),
    examples=("wa.household.washing_machine(1)",),
)

tumble_dryer = Asset(
    id="household.tumble_dryer",
    name="tumble dryer cycle",
    default_input_unit=ureg.dryer_cycle,
    default_comparison_unit=ureg.dryer_cycle,
    prepare=quantity_prepare("dryer_cycle"),
    impact_model=_tumble_dryer_impact,
    equivalence=LinearEquivalence(),
    amount_name="cycles",
    description="A complete tumble-dryer cycle represented by electricity use.",
    parameters=(Parameter("electricity_per_cycle", "electricity for one drying cycle", "1.5 kWh"),),
    examples=("wa.household.tumble_dryer(1)",),
)

ASSETS = (
    boil_water,
    led_light,
    oven,
    refrigerator,
    dishwasher,
    hot_water,
    shower,
    washing_machine,
    tumble_dryer,
)
