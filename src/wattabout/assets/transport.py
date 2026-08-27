from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pint import DimensionalityError, Quantity

from ..context import Context
from ..core import (
    AnalyticEquivalence,
    Asset,
    Impact,
    LinearEquivalence,
    NoEquivalentAmountError,
    Parameter,
    Source,
    WattAboutError,
)
from ..units import Q_, ureg
from .common import TRANSPORT_SOURCE, linear_factor_model, quantity_prepare

AVIATION_SOURCE = Source(
    name="Aviation prototype factors",
    citation=(
        "Illustrative per-passenger flight factors with piecewise distance dependence; "
        "replace with fleet-specific data before scientific use"
    ),
)
CYCLING_SOURCE = Source(
    name="Cycling lifecycle prototype factors",
    citation=(
        "Illustrative bicycle manufacture and maintenance allocated over lifetime distance; "
        "rider food and infrastructure are excluded"
    ),
)

CABIN_MULTIPLIERS = {"economy": 1.0, "premium": 1.6, "business": 2.9}
FLIGHT_FIXED = Q_(70, "kg_co2e")
FLIGHT_SHORT_RATE = Q_(0.20, "kg_co2e / km")
FLIGHT_LONG_RATE = Q_(0.11, "kg_co2e / km")
FLIGHT_BREAKPOINT = 3800.0


def _flight_energy(
    distance_km: float,
    fixed: Quantity,
    short: Quantity,
    long: Quantity,
    breakpoint: float,
) -> Quantity:
    if distance_km <= breakpoint:
        return (fixed + short * Q_(distance_km, "km")).to("kg_co2e")
    base = (fixed + short * Q_(breakpoint, "km")).to("kg_co2e")
    return (base + long * Q_(distance_km - breakpoint, "km")).to("kg_co2e")


def _flight_impact(
    distance: Quantity,
    parameters: Mapping[str, Any],
    context: Context,
    *,
    aircraft_level: bool,
) -> Impact:
    km = distance.to("km").magnitude
    if km < 0:
        raise WattAboutError("flight distance must be nonnegative")
    if aircraft_level:
        passengers = float(parameters.get("passengers", 4))
        if passengers <= 0:
            raise WattAboutError("passengers must be greater than zero")
        fixed = Q_(parameters.get("aircraft_fixed", "400 kg_co2e")).to("kg_co2e")
        short = Q_(parameters.get("aircraft_short_rate", "1.6 kg_co2e / km")).to("kg_co2e / km")
        long = Q_(parameters.get("aircraft_long_rate", "1.0 kg_co2e / km")).to("kg_co2e / km")
        breakpoint = float(parameters.get("breakpoint", FLIGHT_BREAKPOINT))
        cabin = 1.0
    else:
        passengers = 1.0
        cabin_name = parameters.get("cabin_class", "economy")
        if cabin_name not in CABIN_MULTIPLIERS:
            choices = ", ".join(sorted(CABIN_MULTIPLIERS))
            raise WattAboutError(f"Unknown cabin_class {cabin_name!r}; choose from: {choices}")
        cabin = CABIN_MULTIPLIERS[cabin_name]
        fixed = Q_(parameters.get("fixed", FLIGHT_FIXED)).to("kg_co2e")
        short = Q_(parameters.get("short_rate", FLIGHT_SHORT_RATE)).to("kg_co2e / km")
        long = Q_(parameters.get("long_rate", FLIGHT_LONG_RATE)).to("kg_co2e / km")
        breakpoint = float(parameters.get("breakpoint", FLIGHT_BREAKPOINT))

    non_co2 = float(parameters.get("non_co2_multiplier", 2.0))
    if non_co2 < 1:
        raise WattAboutError("non_co2_multiplier must be at least one")

    total = _flight_energy(km, fixed, short, long, breakpoint)
    if aircraft_level:
        climate = (total / passengers * cabin * non_co2).to("kg_co2e")
    else:
        climate = (total * cabin * non_co2).to("kg_co2e")

    assumptions = [
        f"Distance: {km:g} km",
        f"Fixed takeoff and landing share: {fixed:~}",
        f"Short-haul rate up to {breakpoint:g} km: {short:~}",
        f"Long-haul rate beyond {breakpoint:g} km: {long:~}",
    ]
    if cabin != 1.0:
        assumptions.append(f"Cabin-class multiplier: {cabin:g}")
    assumptions.append(f"Non-CO₂ effects multiplier (contrails, NOₓ): {non_co2:g}")
    if aircraft_level:
        assumptions.append(f"Aircraft impact split across {passengers:g} passengers")
    return Impact(
        values={"climate": climate},
        source=AVIATION_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="operational_flight",
        dataset=context.dataset,
        assumptions=tuple(assumptions),
    )


def _solve_flight_distance(
    target_impact: Quantity,
    metric: str,
    unit: Any,
    parameters: Mapping[str, Any],
    context: Context,
) -> Quantity:
    if metric != "climate":
        raise NoEquivalentAmountError(f"Flight has no invertible {metric!r} metric")
    if parameters.get("cabin_class") is not None or "fixed" in parameters:
        fixed = Q_(parameters.get("fixed", FLIGHT_FIXED)).to("kg_co2e")
        short = Q_(parameters.get("short_rate", FLIGHT_SHORT_RATE)).to("kg_co2e / km")
        long = Q_(parameters.get("long_rate", FLIGHT_LONG_RATE)).to("kg_co2e / km")
        breakpoint = float(parameters.get("breakpoint", FLIGHT_BREAKPOINT))
        cabin_name = parameters.get("cabin_class", "economy")
        cabin = CABIN_MULTIPLIERS.get(cabin_name)
        if cabin is None:
            raise NoEquivalentAmountError(f"Unknown cabin_class {cabin_name!r}")
        passengers = 1.0
    else:
        passengers = float(parameters.get("passengers", 4))
        fixed = Q_(parameters.get("aircraft_fixed", "400 kg_co2e")).to("kg_co2e")
        short = Q_(parameters.get("aircraft_short_rate", "1.6 kg_co2e / km")).to("kg_co2e / km")
        long = Q_(parameters.get("aircraft_long_rate", "1.0 kg_co2e / km")).to("kg_co2e / km")
        breakpoint = float(parameters.get("breakpoint", FLIGHT_BREAKPOINT))
        cabin = 1.0
    non_co2 = float(parameters.get("non_co2_multiplier", 2.0))
    effective_fixed = (fixed / passengers * cabin * non_co2).to("kg_co2e")
    effective_short = (short / passengers * cabin * non_co2).to("kg_co2e / km")
    effective_long = (long / passengers * cabin * non_co2).to("kg_co2e / km")

    try:
        required = target_impact.to("kg_co2e").magnitude
    except DimensionalityError as error:
        raise NoEquivalentAmountError(
            "A flight distance can only be inferred from an integrated impact"
        ) from error
    fixed_value = effective_fixed.magnitude
    first_segment_value = fixed_value + effective_short.to("kg_co2e / km").magnitude * breakpoint
    if required < fixed_value:
        raise NoEquivalentAmountError(
            "Source impact is below the flight's minimum takeoff-and-landing impact"
        )
    if required <= first_segment_value:
        km = (required - fixed_value) / effective_short.to("kg_co2e / km").magnitude
    else:
        km = (
            breakpoint
            + (required - first_segment_value) / effective_long.to("kg_co2e / km").magnitude
        )
    return Q_(km, "km").to(unit)


def _commercial_flight_impact(
    distance: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    return _flight_impact(distance, parameters, context, aircraft_level=False)


def _private_flight_impact(
    distance: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    return _flight_impact(distance, parameters, context, aircraft_level=True)


flight = Asset(
    id="transport.flight",
    name="commercial passenger flight",
    default_input_unit=ureg.km,
    default_comparison_unit=ureg.km,
    prepare=quantity_prepare("km"),
    impact_model=_commercial_flight_impact,
    equivalence=AnalyticEquivalence(_solve_flight_distance),
    amount_name="distance",
    description=(
        "Per-passenger flight impact with a fixed takeoff-and-landing component "
        "and distance-dependent cruise rates."
    ),
    parameters=(
        Parameter("cabin_class", "cabin class", "economy"),
        Parameter("non_co2_multiplier", "multiplier for contrails and NOₓ effects", 2.0),
        Parameter("fixed", "per-passenger takeoff and landing impact", "70 kg_co2e"),
        Parameter(
            "short_rate", "per-passenger cruise rate up to the breakpoint", "0.20 kg_co2e / km"
        ),
        Parameter(
            "long_rate", "per-passenger cruise rate beyond the breakpoint", "0.11 kg_co2e / km"
        ),
        Parameter("breakpoint", "distance separating short- and long-haul rates", 3800.0),
    ),
    examples=(
        "wa.transport.flight(800 * wa.km)",
        "wa.transport.flight(6000 * wa.km, cabin_class='business')",
        "wa.transport.flight(6000 * wa.km, non_co2_multiplier=1)",
    ),
)

flight_private = Asset(
    id="transport.flight_private",
    name="private jet flight",
    default_input_unit=ureg.km,
    default_comparison_unit=ureg.km,
    prepare=quantity_prepare("km"),
    impact_model=_private_flight_impact,
    equivalence=AnalyticEquivalence(_solve_flight_distance),
    amount_name="distance",
    description="Aircraft-level private-jet impact divided across the passengers on board.",
    parameters=(
        Parameter("passengers", "passengers sharing the aircraft impact", 4.0),
        Parameter("non_co2_multiplier", "multiplier for contrails and NOₓ effects", 2.0),
        Parameter("aircraft_fixed", "aircraft takeoff and landing impact", "400 kg_co2e"),
        Parameter(
            "aircraft_short_rate", "aircraft cruise rate up to the breakpoint", "1.6 kg_co2e / km"
        ),
        Parameter(
            "aircraft_long_rate", "aircraft cruise rate beyond the breakpoint", "1.0 kg_co2e / km"
        ),
        Parameter("breakpoint", "distance separating short- and long-haul rates", 3800.0),
    ),
    examples=(
        "wa.transport.flight_private(500 * wa.km)",
        "wa.transport.flight_private(500 * wa.km, passengers=8)",
    ),
)


def _ev_impact(distance: Quantity, parameters: Mapping[str, Any], context: Context) -> Impact:
    occupancy = float(parameters.get("occupancy", 1.0))
    if occupancy <= 0:
        raise WattAboutError("occupancy must be greater than zero")
    consumption = Q_(parameters.get("consumption", "18 kWh / (100 km)")).to("kWh / km")
    vehicle_factor = Q_(parameters.get("vehicle_factor", "0.065 kg_co2e / km")).to("kg_co2e / km")
    electricity = (distance.to("km") * consumption).to("kWh")
    operational = (electricity * context.grid_intensity).to("kg_co2e")
    vehicle = distance.to("km") * vehicle_factor if parameters.get("include_vehicle", True) else 0
    climate = ((operational + vehicle) / occupancy).to("kg_co2e")
    return Impact(
        values={"climate": climate},
        source=TRANSPORT_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="cradle_to_grave",
        dataset=context.dataset,
        assumptions=(
            f"Electricity consumption: {consumption:~}",
            *context.electricity_assumptions,
            f"Occupancy: {occupancy:g} people",
            f"Vehicle lifecycle included: {bool(parameters.get('include_vehicle', True))}",
        ),
    )


def _bicycle_impact(distance: Quantity, parameters: Mapping[str, Any], context: Context) -> Impact:
    trip = distance.to("km")
    if trip.magnitude < 0:
        raise WattAboutError("bicycle distance must be nonnegative")
    lifecycle_rate = Q_(parameters.get("lifecycle_rate", "0.005 kg_co2e / km")).to("kg_co2e / km")
    if lifecycle_rate.magnitude < 0:
        raise WattAboutError("lifecycle_rate must be nonnegative")
    climate = (trip * lifecycle_rate).to("kg_co2e")
    return Impact(
        values={"climate": climate},
        source=CYCLING_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="vehicle_lifecycle",
        dataset=context.dataset,
        assumptions=(
            f"Bicycle lifecycle allocation: {lifecycle_rate:~}",
            "Rider food energy and transport infrastructure excluded",
        ),
    )


def _ebike_impact(distance: Quantity, parameters: Mapping[str, Any], context: Context) -> Impact:
    trip = distance.to("km")
    if trip.magnitude < 0:
        raise WattAboutError("e-bike distance must be nonnegative")
    lifecycle_rate = Q_(parameters.get("lifecycle_rate", "0.012 kg_co2e / km")).to("kg_co2e / km")
    consumption = Q_(parameters.get("consumption", "0.01 kWh / km")).to("kWh / km")
    charging_efficiency = float(parameters.get("charging_efficiency", 0.9))
    if lifecycle_rate.magnitude < 0 or consumption.magnitude < 0:
        raise WattAboutError("e-bike lifecycle_rate and consumption must be nonnegative")
    if not 0 < charging_efficiency <= 1:
        raise WattAboutError("charging_efficiency must be greater than zero and at most one")
    electricity = (trip * consumption / charging_efficiency).to("kWh")
    operational = (electricity * context.grid_intensity).to("kg_co2e")
    lifecycle = (trip * lifecycle_rate).to("kg_co2e")
    return Impact(
        values={"climate": operational + lifecycle},
        source=CYCLING_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="cradle_to_grave",
        dataset=context.dataset,
        assumptions=(
            f"E-bike lifecycle allocation including battery: {lifecycle_rate:~}",
            f"Battery electricity consumption: {consumption:~}",
            f"Charging efficiency: {charging_efficiency:.0%}",
            *context.electricity_assumptions,
            "Rider food energy and transport infrastructure excluded",
        ),
    )


train = Asset(
    id="transport.train",
    name="Swiss passenger train ride",
    default_input_unit=ureg.km,
    default_comparison_unit=ureg.km,
    prepare=quantity_prepare("km"),
    impact_model=linear_factor_model(
        factor=Q_(0.0071, "kg_co2e / km"),
        source=TRANSPORT_SOURCE,
        boundary="cradle_to_grave",
        reference_unit="km",
        assumptions=("One passenger using average Swiss rail service",),
    ),
    equivalence=LinearEquivalence(),
    amount_name="distance",
    description="Passenger distance on an average Swiss rail service.",
    examples=("wa.transport.train(30 * wa.km)",),
)

petrol_car = Asset(
    id="transport.petrol_car",
    name="petrol passenger car ride",
    default_input_unit=ureg.km,
    default_comparison_unit=ureg.km,
    prepare=quantity_prepare("km"),
    impact_model=linear_factor_model(
        factor=Q_(0.171, "kg_co2e / km"),
        source=TRANSPORT_SOURCE,
        boundary="cradle_to_grave",
        reference_unit="km",
        assumptions=("Representative combustion passenger car",),
        allocate_by_occupancy=True,
    ),
    equivalence=LinearEquivalence(),
    amount_name="distance",
    description="Passenger travel in a representative petrol car.",
    parameters=(Parameter("occupancy", "people sharing the vehicle impact", "1"),),
    examples=("wa.transport.petrol_car(20 * wa.km, occupancy=2)",),
)

ev = Asset(
    id="transport.ev",
    name="electric passenger car ride",
    default_input_unit=ureg.km,
    default_comparison_unit=ureg.km,
    prepare=quantity_prepare("km"),
    impact_model=_ev_impact,
    equivalence=LinearEquivalence(),
    amount_name="distance",
    description="Electric car travel using the context's electricity grid intensity.",
    parameters=(
        Parameter("occupancy", "people sharing the vehicle impact", "1"),
        Parameter("consumption", "vehicle electricity consumption", "18 kWh / (100 km)"),
        Parameter("vehicle_factor", "allocated vehicle lifecycle impact", "65 g CO2e / km"),
        Parameter("include_vehicle", "include allocated vehicle lifecycle impact", True),
    ),
    examples=("wa.transport.ev(50 * wa.km, occupancy=2)",),
)

bus = Asset(
    id="transport.bus",
    name="average passenger bus ride",
    default_input_unit=ureg.km,
    default_comparison_unit=ureg.km,
    prepare=quantity_prepare("km"),
    impact_model=linear_factor_model(
        factor=Q_(0.089, "kg_co2e / km"),
        source=TRANSPORT_SOURCE,
        boundary="cradle_to_grave",
        reference_unit="km",
        assumptions=("Average occupancy is included in the passenger-kilometer factor",),
    ),
    equivalence=LinearEquivalence(),
    amount_name="distance",
    description="One passenger traveling by an average scheduled bus.",
    examples=("wa.transport.bus(10 * wa.km)",),
)

bicycle = Asset(
    id="transport.bicycle",
    name="bicycle ride",
    default_input_unit=ureg.km,
    default_comparison_unit=ureg.km,
    prepare=quantity_prepare("km"),
    impact_model=_bicycle_impact,
    equivalence=LinearEquivalence(),
    amount_name="distance",
    description="Bicycle travel with manufacture and maintenance allocated per kilometre.",
    parameters=(
        Parameter(
            "lifecycle_rate", "bicycle manufacture and maintenance per distance", "5 g CO2e / km"
        ),
    ),
    examples=("wa.transport.bicycle(10 * wa.km)",),
)

ebike = Asset(
    id="transport.ebike",
    name="electric bicycle ride",
    default_input_unit=ureg.km,
    default_comparison_unit=ureg.km,
    prepare=quantity_prepare("km"),
    impact_model=_ebike_impact,
    equivalence=LinearEquivalence(),
    amount_name="distance",
    description="E-bike travel including lifecycle allocation and grid-sensitive charging.",
    parameters=(
        Parameter(
            "lifecycle_rate",
            "e-bike and battery manufacture and maintenance per distance",
            "12 g CO2e / km",
        ),
        Parameter("consumption", "battery electricity delivered per distance", "1 kWh / 100 km"),
        Parameter("charging_efficiency", "battery charging efficiency", 0.9),
    ),
    examples=("wa.transport.ebike(10 * wa.km)",),
)

ASSETS = (train, petrol_car, ev, bus, bicycle, ebike, flight, flight_private)
