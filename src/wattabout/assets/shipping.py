from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pint import Quantity

from ..context import Context
from ..core import Asset, Impact, LinearEquivalence, Parameter, Source, WattAboutError
from ..units import Q_, ureg
from .common import quantity_prepare

SHIPPING_SOURCE = Source(
    name="E-commerce parcel prototype factors",
    citation=(
        "Illustrative parcel shipping factors for China-Europe routes; replace with "
        "carrier-specific data before scientific use"
    ),
)

LINE_HAUL_FACTORS = {
    "air": Q_(4.0, "kg_co2e / kg"),
    "rail": Q_(0.12, "kg_co2e / kg"),
    "sea": Q_(0.08, "kg_co2e / kg"),
}
PARCEL_HANDLING = Q_(0.25, "kg_co2e")


def _parcel_impact(parcels: Quantity, parameters: Mapping[str, Any], context: Context) -> Impact:
    count = parcels.to("parcel").magnitude
    if count < 0:
        raise WattAboutError("parcel count must be nonnegative")
    mass = Q_(parameters.get("mass", "1 kg")).to("kg")
    if mass.magnitude < 0:
        raise WattAboutError("mass must be nonnegative")
    mode = parameters.get("mode", "air")
    if mode not in LINE_HAUL_FACTORS:
        choices = ", ".join(sorted(LINE_HAUL_FACTORS))
        raise WattAboutError(f"Unknown transport mode {mode!r}; choose from: {choices}")
    line_haul = LINE_HAUL_FACTORS[mode]
    per_parcel = PARCEL_HANDLING + mass * line_haul
    climate = (count * per_parcel).to("kg_co2e")
    return Impact(
        values={"climate": climate},
        source=SHIPPING_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="cradle_to_door",
        dataset=context.dataset,
        assumptions=(
            f"Line-haul mode: {mode} ({line_haul:~} of cargo mass)",
            f"Parcel contents mass: {mass:~}",
            f"Sorting and last-mile handling: {PARCEL_HANDLING:~} per parcel",
            "China to Switzerland route; excludes manufacturing of the goods",
        ),
    )


parcel_from_china = Asset(
    id="shipping.parcel_from_china",
    name="e-commerce parcel shipped from China",
    default_input_unit=ureg.parcel,
    default_comparison_unit=ureg.parcel,
    prepare=quantity_prepare("parcel"),
    impact_model=_parcel_impact,
    equivalence=LinearEquivalence(),
    amount_name="parcels",
    description="Transport of one e-commerce parcel from China to Switzerland.",
    parameters=(
        Parameter("mass", "contents plus packaging mass", "1 kg"),
        Parameter("mode", "line-haul transport mode", "air"),
    ),
    examples=(
        "wa.shipping.parcel_from_china(1)",
        "wa.shipping.parcel_from_china(2, mode='rail')",
    ),
)

ASSETS = (parcel_from_china,)
