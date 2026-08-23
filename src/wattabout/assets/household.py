from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pint import Quantity

from ..context import Context
from ..core import (
    AnalyticEquivalence,
    Asset,
    Impact,
    LinearEquivalence,
    NoEquivalentAmountError,
    Parameter,
    WattAboutError,
)
from ..units import Q_, ureg
from .common import PHYSICAL_MODEL_SOURCE, quantity_prepare


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
    required_electricity = (target_impact / context.grid_intensity).to("kWh")
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

ASSETS = (boil_water, led_light, oven, refrigerator, dishwasher)
