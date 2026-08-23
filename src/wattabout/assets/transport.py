from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pint import Quantity

from ..context import Context
from ..core import Asset, Impact, LinearEquivalence, Parameter, WattAboutError
from ..units import Q_, ureg
from .common import TRANSPORT_SOURCE, linear_factor_model, quantity_prepare


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
            f"Grid intensity: {context.grid_intensity:~}",
            f"Occupancy: {occupancy:g} people",
            f"Vehicle lifecycle included: {bool(parameters.get('include_vehicle', True))}",
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

ASSETS = (train, petrol_car, ev, bus)
