from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from pint import DimensionalityError, Quantity

from ..context import Context
from ..core import Impact, Source, WattAboutError
from ..units import Q_

TRANSPORT_SOURCE = Source(
    name="Swiss transport prototype factors",
    citation="Representative Swiss transport estimates informed by Mobitool; replace before scientific use",
    url="https://www.mobitool.ch/",
)
FOOD_SOURCE = Source(
    name="Food LCA prototype factors",
    citation="Representative food lifecycle estimates; replace before scientific use",
)
ELECTRONICS_SOURCE = Source(
    name="Electronics prototype factors",
    citation="Representative electronics lifecycle estimates; replace before scientific use",
)
ENERGY_SOURCE = Source(
    name="Energy prototype factors",
    citation="Representative direct energy emission factors; replace before scientific use",
)
PHYSICAL_MODEL_SOURCE = Source(
    name="Physical energy model",
    citation="Calculated from physical inputs and the configured grid intensity",
)


def quantity_prepare(unit: str):
    def prepare(
        amount: Any, parameters: Mapping[str, Any]
    ) -> tuple[Quantity, Quantity, Mapping[str, Any]]:
        quantity = Q_(amount).to(unit)
        return quantity, quantity, dict(parameters)

    return prepare


def cervelat_prepare(
    amount: Any, parameters: Mapping[str, Any]
) -> tuple[Quantity, Quantity, Mapping[str, Any]]:
    quantity = Q_(amount)
    normalized = dict(parameters)
    diameter = Q_(normalized.pop("diameter", "34 mm")).to("m")
    density = Q_(normalized.pop("density", "1050 kg / m^3")).to("kg / m^3")
    try:
        mass = quantity.to("kg")
    except DimensionalityError:
        length = quantity.to("m")
        volume = math.pi * (diameter / 2) ** 2 * length
        mass = (volume * density).to("kg")
    normalized.update({"diameter": diameter, "density": density})
    return mass, quantity, normalized


def linear_factor_model(
    *,
    factor: Quantity,
    source: Source,
    boundary: str,
    reference_unit: str,
    assumptions: tuple[str, ...] = (),
    allocate_by_occupancy: bool = False,
):
    def calculate(amount: Quantity, parameters: Mapping[str, Any], context: Context) -> Impact:
        occupancy = float(parameters.get("occupancy", 1.0))
        if occupancy <= 0:
            raise WattAboutError("occupancy must be greater than zero")
        divisor = occupancy if allocate_by_occupancy else 1.0
        value = (amount.to(reference_unit) * factor / divisor).to("kg_co2e")
        dynamic_assumptions = assumptions
        if allocate_by_occupancy:
            dynamic_assumptions += (f"Occupancy: {occupancy:g} people",)
        return Impact(
            values={"climate": value},
            source=source,
            geography=context.region,
            reference_year=context.year,
            boundary=boundary,
            dataset=context.dataset,
            assumptions=dynamic_assumptions,
        )

    return calculate
