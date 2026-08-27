from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pint import Quantity

from ..context import Context
from ..core import Asset, Impact, LinearEquivalence, Parameter, WattAboutError
from ..units import Q_, ureg
from .common import ELECTRONICS_SOURCE, PHYSICAL_MODEL_SOURCE, linear_factor_model, quantity_prepare


def _phone_charge_impact(
    charges: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    capacity = Q_(parameters.get("battery_capacity", "15 Wh")).to("kWh")
    efficiency = float(parameters.get("charging_efficiency", 0.85))
    if not 0 < efficiency <= 1:
        raise WattAboutError("charging_efficiency must be greater than zero and at most one")
    electricity = charges.to("phone_charge").magnitude * capacity / efficiency
    climate = (electricity * context.grid_intensity).to("kg_co2e")
    return Impact(
        values={"climate": climate},
        source=PHYSICAL_MODEL_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="operational",
        dataset=context.dataset,
        assumptions=(
            f"Battery capacity: {capacity:~}",
            f"Charging efficiency: {efficiency:.0%}",
            *context.electricity_assumptions,
        ),
    )


phone = Asset(
    id="electronics.phone",
    name="smartphone production",
    default_input_unit=ureg.phone_device,
    default_comparison_unit=ureg.phone_device,
    prepare=quantity_prepare("phone_device"),
    impact_model=linear_factor_model(
        factor=Q_(70, "kg_co2e / phone_device"),
        source=ELECTRONICS_SOURCE,
        boundary="cradle_to_gate",
        reference_unit="phone_device",
        assumptions=("Representative smartphone production",),
    ),
    equivalence=LinearEquivalence(),
    amount_name="devices",
    description="Embodied production impact of a representative smartphone.",
    examples=("wa.electronics.phone(1)",),
)

laptop = Asset(
    id="electronics.laptop",
    name="laptop production",
    default_input_unit=ureg.laptop_device,
    default_comparison_unit=ureg.laptop_device,
    prepare=quantity_prepare("laptop_device"),
    impact_model=linear_factor_model(
        factor=Q_(250, "kg_co2e / laptop_device"),
        source=ELECTRONICS_SOURCE,
        boundary="cradle_to_gate",
        reference_unit="laptop_device",
        assumptions=("Representative laptop production",),
    ),
    equivalence=LinearEquivalence(),
    amount_name="devices",
    description="Embodied production impact of a representative laptop computer.",
    examples=("wa.electronics.laptop(1)",),
)

phone_charge = Asset(
    id="electronics.phone_charge",
    name="smartphone charge",
    default_input_unit=ureg.phone_charge,
    default_comparison_unit=ureg.phone_charge,
    prepare=quantity_prepare("phone_charge"),
    impact_model=_phone_charge_impact,
    equivalence=LinearEquivalence(),
    amount_name="charges",
    description="Electricity required for a full smartphone battery charge.",
    parameters=(
        Parameter("battery_capacity", "usable battery energy", "15 Wh"),
        Parameter("charging_efficiency", "wall-to-battery efficiency", "0.85"),
    ),
    examples=("wa.electronics.phone_charge(1)",),
)


def _laptop_use_impact(
    duration: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    power = Q_(parameters.get("power", "10 W")).to("kW")
    if power.magnitude < 0:
        raise WattAboutError("power must be nonnegative")
    electricity = (power * duration.to("hour")).to("kWh")
    climate = (electricity * context.grid_intensity).to("kg_co2e")
    return Impact(
        values={"climate": climate},
        source=PHYSICAL_MODEL_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="operational",
        dataset=context.dataset,
        assumptions=(
            f"Average active-use power: {power:~}",
            *context.electricity_assumptions,
        ),
    )


def _laptop_use_rate_impact(_: Quantity, parameters: Mapping[str, Any], context: Context) -> Impact:
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
        assumptions=(
            f"Average active-use power: {power:~}",
            *context.electricity_assumptions,
        ),
        is_rate=True,
    )


laptop_use = Asset(
    id="electronics.laptop_use",
    name="laptop active use",
    default_input_unit=ureg.hour,
    default_comparison_unit=ureg.hour,
    prepare=quantity_prepare("hour"),
    impact_model=_laptop_use_impact,
    equivalence=LinearEquivalence(),
    amount_name="duration",
    description=(
        "Operational electricity for active laptop use; default reflects an "
        "M-series MacBook (Apple reports ~3 W idle display-on and 14-22 W under load)."
    ),
    parameters=(Parameter("power", "average active-use electrical power", "10 W"),),
    examples=(
        "wa.electronics.laptop_use(8 * wa.hour)",
        "wa.electronics.laptop_use.rate(power='10 W')",
    ),
    rate_model=_laptop_use_rate_impact,
)

ASSETS = (phone, laptop, phone_charge, laptop_use)
