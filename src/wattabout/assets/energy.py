from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pint import Quantity

from ..context import Context
from ..core import Asset, Impact, LinearEquivalence
from ..units import Q_, ureg
from .common import ENERGY_SOURCE, PHYSICAL_MODEL_SOURCE, linear_factor_model, quantity_prepare


def _electricity_impact(
    amount: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    climate = (amount.to("kWh") * context.grid_intensity).to("kg_co2e")
    return Impact(
        values={"climate": climate},
        source=PHYSICAL_MODEL_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="operational",
        dataset=context.dataset,
        assumptions=(f"Grid intensity: {context.grid_intensity:~}",),
    )


electricity = Asset(
    id="energy.electricity",
    name="grid electricity",
    default_input_unit=ureg.kWh,
    default_comparison_unit=ureg.kWh,
    prepare=quantity_prepare("kWh"),
    impact_model=_electricity_impact,
    equivalence=LinearEquivalence(),
    amount_name="energy",
    description="Electricity using the active context's grid carbon intensity.",
    examples=("wa.energy.electricity(5 * wa.kWh)",),
)

natural_gas = Asset(
    id="energy.natural_gas",
    name="natural gas energy",
    default_input_unit=ureg.kWh,
    default_comparison_unit=ureg.kWh,
    prepare=quantity_prepare("kWh"),
    impact_model=linear_factor_model(
        factor=Q_(0.202, "kg_co2e / kWh"),
        source=ENERGY_SOURCE,
        boundary="operational",
        reference_unit="kWh",
        assumptions=("Direct combustion estimate",),
    ),
    equivalence=LinearEquivalence(),
    amount_name="energy",
    description="Useful energy from direct natural-gas combustion.",
    examples=("wa.energy.natural_gas(10 * wa.kWh)",),
)

ASSETS = (electricity, natural_gas)
