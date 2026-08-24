from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pint import DimensionalityError, Quantity

from ..context import Context
from ..core import (
    AnalyticEquivalence,
    Asset,
    Impact,
    NoEquivalentAmountError,
    Parameter,
    Source,
    WattAboutError,
)
from ..units import Q_, ureg
from .common import quantity_prepare

NATURE_SOURCE = Source(
    name="Tree growth sequestration model",
    citation=(
        "Prototype quadratic sequestration curve for a temperate tree; replace with "
        "species- and site-specific data before scientific use"
    ),
)

PEAK_ANNUAL_ABSORPTION = Q_(21, "kg_co2e / year")
MATURITY_AGE = 40.0


def _tree_parameters(parameters: Mapping[str, Any]) -> tuple[float, float]:
    peak = Q_(parameters.get("peak_annual_absorption", PEAK_ANNUAL_ABSORPTION)).to("kg_co2e / year")
    maturity = float(parameters.get("maturity_age", MATURITY_AGE))
    if peak.magnitude <= 0 or maturity <= 0:
        raise WattAboutError("peak_annual_absorption and maturity_age must be positive")
    return peak.to("kg_co2e / year").magnitude, maturity


def _tree_growth_impact(
    duration: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    age = duration.to("year").magnitude
    if age < 0:
        raise WattAboutError("tree growth period must be nonnegative")
    peak_value, maturity = _tree_parameters(parameters)
    absorbed = _cumulative_absorption(age, peak_value, maturity)
    return Impact(
        values={"climate": Q_(-absorbed, "kg_co2e")},
        source=NATURE_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="sequestration",
        dataset=context.dataset,
        assumptions=(
            f"Quadratic growth to maturity at {maturity:g} years",
            f"Peak annual absorption at maturity: {peak_value:g} kg_co2e/year",
            "Absorption continues linearly after maturity; end of life excluded",
        ),
    )


def _cumulative_absorption(age_years: float, peak_value: float, maturity: float) -> float:
    """Cumulative absorption in kg_co2e for a quadratic-then-linear growth curve."""
    k = peak_value / (2 * maturity)  # kg/year²
    if age_years <= maturity:
        return k * age_years**2
    return k * maturity**2 + peak_value * (age_years - maturity)


def _solve_tree_growth_period(
    target_impact: Quantity,
    metric: str,
    unit: Any,
    parameters: Mapping[str, Any],
    context: Context,
) -> Quantity:
    if metric != "climate":
        raise NoEquivalentAmountError(f"Tree has no invertible {metric!r} metric")
    try:
        magnitude = target_impact.to("kg_co2e").magnitude
    except DimensionalityError as error:
        raise NoEquivalentAmountError(
            "A tree growth period can only be inferred from an integrated impact"
        ) from error
    # Tree impacts are negative; equivalents are matched by absorption
    # magnitude so that e.g. a phone maps to the years needed to absorb it.
    absorbed = abs(magnitude)
    peak_value, maturity = _tree_parameters(parameters)
    young_capacity = _cumulative_absorption(maturity, peak_value, maturity)
    if absorbed <= young_capacity:
        k = peak_value / (2 * maturity)
        age = (absorbed / k) ** 0.5
    else:
        age = maturity + (absorbed - young_capacity) / peak_value
    return Q_(age, "year").to(unit)


tree_growth = Asset(
    id="nature.tree_growth",
    name="growing tree carbon uptake",
    default_input_unit=ureg.year,
    default_comparison_unit=ureg.year,
    prepare=quantity_prepare("year"),
    impact_model=_tree_growth_impact,
    equivalence=AnalyticEquivalence(_solve_tree_growth_period),
    amount_name="growth_period",
    description=(
        "Cumulative carbon absorption while a tree grows from seed; impacts are negative."
    ),
    parameters=(
        Parameter("peak_annual_absorption", "annual absorption at maturity", "21 kg_co2e / year"),
        Parameter("maturity_age", "age at which peak absorption is reached", 40.0),
    ),
    examples=(
        "wa.nature.tree_growth(30 * wa.year)",
        "wa.electronics.phone() / wa.nature.tree_growth",
    ),
)

ASSETS = (tree_growth,)
