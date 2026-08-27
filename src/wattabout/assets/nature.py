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
from .common import quantity_prepare

NATURE_SOURCE = Source(
    name="Tree growth sequestration model",
    citation=(
        "Prototype quadratic sequestration curve for a temperate tree; replace with "
        "species- and site-specific data before scientific use"
    ),
)
DAC_SOURCE = Source(
    name="Conservative direct-air-capture purchase scenario",
    citation=(
        "Prototype CHF 1,000/t DAC purchase assumption informed by current durable-removal "
        "market prices; the 80% delivery fraction is a conservative scenario, not an "
        "industry statistic"
    ),
    url="https://www.cdr.fyi/blog/2024-year-in-review",
)
FOREST_FIRE_SOURCE = Source(
    name="Temperate forest fire gross-emissions scenario",
    citation=(
        "Prototype 75 t CO2e/ha gross event factor informed by IPCC biomass-burning methods "
        "and State of Wildfires observations; actual emissions vary strongly by fuel and severity"
    ),
    url="https://essd.copernicus.org/articles/16/3601/2024/",
)
VOLCANO_SOURCE = Source(
    name="Published volcanic CO2 reference events",
    citation=(
        "USGS estimates for Mount St. Helens 1980 and Pinatubo 1991; Etna 2004-2005 "
        "cumulative plume estimate from Burton et al. (2006), doi:10.1029/2006JB004307"
    ),
    url="https://www.usgs.gov/programs/VHP/volcanoes-can-affect-climate",
)

PEAK_ANNUAL_ABSORPTION = Q_(21, "kg_co2e / year")
MATURITY_AGE = 40.0
VOLCANIC_PROFILES = {
    "small": Q_(100_000, "tonne_co2e"),
    "medium": Q_(1_000_000, "tonne_co2e"),
    "large": Q_(10_000_000, "tonne_co2e"),
    "very_large": Q_(50_000_000, "tonne_co2e"),
    "mount_st_helens_1980": Q_(10_000_000, "tonne_co2e"),
    "pinatubo_1991": Q_(50_000_000, "tonne_co2e"),
    "etna_2004_2005": Q_(3_800_000, "tonne_co2e"),
}


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


def _dac_parameters(parameters: Mapping[str, Any]) -> tuple[Quantity, float]:
    price = Q_(parameters.get("price_per_tonne", "1000 CHF / tonne_co2e")).to("CHF / tonne_co2e")
    delivery_fraction = float(parameters.get("delivery_fraction", 0.8))
    if price.magnitude <= 0:
        raise WattAboutError("price_per_tonne must be positive")
    if not 0 <= delivery_fraction <= 1:
        raise WattAboutError("delivery_fraction must be between zero and one")
    return price, delivery_fraction


def _direct_air_capture_impact(
    spending: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    amount = spending.to("CHF")
    if amount.magnitude < 0:
        raise WattAboutError("direct-air-capture spending must be nonnegative")
    price, delivery_fraction = _dac_parameters(parameters)
    removal = (amount / price * delivery_fraction).to("kg_co2e")
    return Impact(
        values={"climate": -removal},
        source=DAC_SOURCE,
        geography="global",
        reference_year=2026,
        boundary="expected_contracted_durable_removal",
        dataset=context.dataset,
        assumptions=(
            f"Nominal DAC purchase price: {price:~}",
            f"Expected delivery fraction: {delivery_fraction:.0%}",
            "Negative impact represents expected contracted removal, not immediate delivery",
            "Delivered certificates can be represented with delivery_fraction=1",
        ),
    )


def _solve_direct_air_capture_spending(
    target_impact: Quantity,
    metric: str,
    unit: Any,
    parameters: Mapping[str, Any],
    context: Context,
) -> Quantity:
    if metric != "climate":
        raise NoEquivalentAmountError(f"Direct air capture has no invertible {metric!r} metric")
    price, delivery_fraction = _dac_parameters(parameters)
    if delivery_fraction == 0:
        raise NoEquivalentAmountError(
            "Direct-air-capture spending cannot be inferred with zero expected delivery"
        )
    try:
        required = abs(target_impact.to("tonne_co2e"))
    except DimensionalityError as error:
        raise NoEquivalentAmountError(
            "Direct-air-capture spending can only be inferred from an integrated impact"
        ) from error
    return (required * price / delivery_fraction).to(unit)


def _forest_fire_impact(
    burned_area: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    area = burned_area.to("hectare")
    if area.magnitude < 0:
        raise WattAboutError("burned area must be nonnegative")
    factor = Q_(parameters.get("emissions_per_area", "75 tonne_co2e / hectare")).to(
        "tonne_co2e / hectare"
    )
    if factor.magnitude < 0:
        raise WattAboutError("emissions_per_area must be nonnegative")
    return Impact(
        values={"climate": (area * factor).to("kg_co2e")},
        source=FOREST_FIRE_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="gross_fire_event_emissions",
        dataset=context.dataset,
        assumptions=(
            f"Area actually burned: {area:~}",
            f"Gross temperate-forest fire factor: {factor:~}",
            "Future regrowth, soil and peat burning, suppression, and property loss excluded",
        ),
    )


def _volcanic_eruption_impact(
    events: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    count = events.to("eruption_event").magnitude
    if count < 0:
        raise WattAboutError("eruption count must be nonnegative")
    custom = parameters.get("co2_per_event")
    profile = str(parameters.get("profile", "small"))
    if custom is None:
        try:
            per_event = VOLCANIC_PROFILES[profile]
        except KeyError as error:
            choices = ", ".join(sorted(VOLCANIC_PROFILES))
            raise WattAboutError(
                f"Unknown volcanic profile {profile!r}; choose from: {choices}"
            ) from error
    else:
        per_event = Q_(custom).to("tonne_co2e")
    if per_event.magnitude < 0:
        raise WattAboutError("co2_per_event must be nonnegative")
    return Impact(
        values={"climate": (count * per_event).to("kg_co2e")},
        source=VOLCANO_SOURCE,
        geography="global",
        reference_year=context.year,
        boundary="direct_volcanic_co2",
        dataset=context.dataset,
        assumptions=(
            f"Volcanic profile: {profile if custom is None else 'custom'}",
            f"Direct CO2 per event: {per_event:~}",
            "Short-lived sulfate cooling, ash, other gases, and damage are excluded",
            "Generic size profiles are explicit scenarios, not VEI conversions",
        ),
    )


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

direct_air_capture = Asset(
    id="nature.direct_air_capture",
    name="expected contracted direct air capture",
    default_input_unit=ureg.CHF,
    default_comparison_unit=ureg.CHF,
    prepare=quantity_prepare("CHF"),
    impact_model=_direct_air_capture_impact,
    equivalence=AnalyticEquivalence(_solve_direct_air_capture_spending),
    amount_name="spending",
    description="Expected durable atmospheric CO2 removal purchased with Swiss francs.",
    parameters=(
        Parameter("price_per_tonne", "nominal DAC purchase price", "1000 CHF / tonne_co2e"),
        Parameter("delivery_fraction", "expected fraction of contracted removal delivered", 0.8),
    ),
    examples=(
        "wa.nature.direct_air_capture(100 * wa.CHF)",
        "wa.nature.direct_air_capture(100 * wa.CHF, delivery_fraction=1)",
    ),
)

forest_fire = Asset(
    id="nature.forest_fire",
    name="temperate forest fire",
    default_input_unit=ureg.hectare,
    default_comparison_unit=ureg.hectare,
    prepare=quantity_prepare("hectare"),
    impact_model=_forest_fire_impact,
    equivalence=LinearEquivalence(),
    amount_name="burned_area",
    description="Gross climate emissions from the area actually burned in a forest fire.",
    parameters=(
        Parameter(
            "emissions_per_area",
            "gross fire emissions per burned area",
            "75 tonne_co2e / hectare",
        ),
    ),
    examples=(
        "wa.nature.forest_fire(2 * wa.hectare)",
        "wa.nature.forest_fire(5000 * wa.m2)",
    ),
)

volcanic_eruption = Asset(
    id="nature.volcanic_eruption",
    name="volcanic eruption CO2 release",
    default_input_unit=ureg.eruption_event,
    default_comparison_unit=ureg.eruption_event,
    prepare=quantity_prepare("eruption_event"),
    impact_model=_volcanic_eruption_impact,
    equivalence=LinearEquivalence(),
    amount_name="events",
    description="Direct volcanic CO2 using named reference events or explicit size scenarios.",
    parameters=(
        Parameter("profile", "named event or generic size profile", "small"),
        Parameter("co2_per_event", "custom direct CO2 release per event", None),
    ),
    examples=(
        "wa.nature.volcanic_eruption(1, profile='mount_st_helens_1980')",
        "wa.nature.volcanic_eruption(1, profile='etna_2004_2005')",
    ),
)

ASSETS = (tree_growth, direct_air_capture, forest_fire, volcanic_eruption)
