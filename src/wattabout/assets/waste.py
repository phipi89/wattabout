from ..core import Asset, LinearEquivalence
from ..units import Q_, ureg
from .common import Source, linear_factor_model, quantity_prepare

WASTE_SOURCE = Source(
    name="Residual waste prototype factor",
    citation=(
        "Illustrative mixed residual municipal waste factor reflecting Swiss "
        "incineration with energy recovery; replace before scientific use"
    ),
)


mixed = Asset(
    id="waste.mixed",
    name="mixed residual waste",
    default_input_unit=ureg.kg,
    default_comparison_unit=ureg.kg,
    prepare=quantity_prepare("kg"),
    impact_model=linear_factor_model(
        factor=Q_(0.58, "kg_co2e / kg"),
        source=WASTE_SOURCE,
        boundary="cradle_to_disposal",
        reference_unit="kg",
        assumptions=("Incineration with energy recovery; recyclables already separated",),
    ),
    equivalence=LinearEquivalence(),
    amount_name="mass",
    description="Mixed residual municipal waste sent to incineration.",
    examples=("wa.waste.mixed(20 * wa.kg)",),
)

ASSETS = (mixed,)
