from collections.abc import Mapping
from typing import Any

from pint import Quantity

from ..context import Context
from ..core import Asset, Impact, LinearEquivalence, Source
from ..units import Q_, ureg

LIFESTYLE_SOURCE = Source(
    name="Global Carbon Budget consumption-based CO2",
    citation=(
        "Global Carbon Budget (2025), per-capita consumption-based CO2 emissions for 2023; "
        "processed by Our World in Data"
    ),
    url="https://ourworldindata.org/grapher/consumption-co2-per-capita",
)


def _duration_prepare(
    amount: Any, parameters: Mapping[str, Any]
) -> tuple[Quantity, Quantity, Mapping[str, Any]]:
    display = Q_(amount)
    return display.to("year"), display, dict(parameters)


def _resident_asset(asset_id: str, name: str, tonnes_per_year: float, geography: str) -> Asset:
    factor = Q_(tonnes_per_year * 1000, "kg_co2e / year")

    def calculate(amount: Quantity, parameters: Mapping[str, Any], context: Context) -> Impact:
        return Impact(
            values={"climate": (amount.to("year") * factor).to("kg_co2e")},
            source=LIFESTYLE_SOURCE,
            geography=geography,
            reference_year=2023,
            boundary="consumption_based_fossil_and_industry_co2",
            dataset="Global Carbon Budget 2025",
            assumptions=(
                "National production emissions adjusted for carbon embodied in trade",
                (
                    "CO2 from fossil fuels and industry only; other greenhouse gases, land-use "
                    "change, international aviation, and international shipping are excluded"
                ),
            ),
        )

    return Asset(
        id=f"lifestyle.{asset_id}",
        name=name,
        default_input_unit=ureg.day,
        default_comparison_unit=ureg.day,
        prepare=_duration_prepare,
        impact_model=calculate,
        equivalence=LinearEquivalence(),
        amount_name="duration",
        description=f"Average consumption-based carbon emissions of {name.lower()}.",
        examples=(f"wa.lifestyle.{asset_id}(1 * wa.day)",),
    )


swiss_resident = _resident_asset("swiss_resident", "Swiss resident", 13.339576, "CH")
european_resident = _resident_asset("european_resident", "EU-27 resident", 7.3275137, "EU-27")
us_resident = _resident_asset("us_resident", "US resident", 15.813734, "US")
china_resident = _resident_asset("china_resident", "Chinese resident", 7.6319, "CN")
india_resident = _resident_asset("india_resident", "Indian resident", 1.7684926, "IN")

ASSETS = (
    swiss_resident,
    european_resident,
    us_resident,
    china_resident,
    india_resident,
)
