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
            f"Grid intensity: {context.grid_intensity:~}",
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

ASSETS = (phone, laptop, phone_charge)
