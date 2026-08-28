from ..core import Asset, LinearEquivalence, Parameter
from ..units import Q_, ureg
from .common import FOOD_SOURCE, cervelat_prepare, linear_factor_model, quantity_prepare


def _food_asset(asset_id: str, name: str, factor: float, description: str) -> Asset:
    return Asset(
        id=f"food.{asset_id}",
        name=name,
        default_input_unit=ureg.gram,
        default_comparison_unit=ureg.gram,
        prepare=quantity_prepare("kg"),
        impact_model=linear_factor_model(
            factor=Q_(factor, "kg_co2e / kg"),
            source=FOOD_SOURCE,
            boundary="cradle_to_consumer",
            reference_unit="kg",
        ),
        equivalence=LinearEquivalence(),
        amount_name="mass",
        description=description,
        examples=(f"wa.food.{asset_id}(100 * wa.gram)",),
    )


def _meal_asset(diet: str, factor: float) -> Asset:
    return Asset(
        id=f"food.meal_{diet}",
        name=f"{diet} meal",
        default_input_unit=ureg.meal,
        default_comparison_unit=ureg.meal,
        prepare=quantity_prepare("meal"),
        impact_model=linear_factor_model(
            factor=Q_(factor, "kg_co2e / meal"),
            source=FOOD_SOURCE,
            boundary="cradle_to_consumer",
            reference_unit="meal",
            assumptions=("Representative mixed ingredients for one prepared meal",),
        ),
        equivalence=LinearEquivalence(),
        amount_name="meals",
        description=f"Representative {diet} meal including supply-chain impacts.",
        examples=(f"wa.food.meal_{diet}(1)",),
    )


cervelat = Asset(
    id="food.cervelat",
    name="cervelat",
    default_input_unit=ureg.gram,
    default_comparison_unit=ureg.mm,
    prepare=cervelat_prepare,
    impact_model=linear_factor_model(
        factor=Q_(5.9, "kg_co2e / kg"),
        source=FOOD_SOURCE,
        boundary="cradle_to_consumer",
        reference_unit="kg",
        assumptions=("Standard cylindrical cervelat geometry",),
    ),
    equivalence=LinearEquivalence(),
    accepted_input_units=(ureg.gram, ureg.meter),
    amount_name="amount",
    description="Cervelat by mass or by length using an assumed cylindrical geometry.",
    parameters=(
        Parameter("diameter", "sausage diameter used for length conversion", "34 mm"),
        Parameter("density", "sausage density used for length conversion", "1050 kg / m³"),
    ),
    examples=("wa.food.cervelat(10 * wa.cm)", "wa.food.cervelat(100 * wa.gram)"),
)

coffee = Asset(
    id="food.coffee",
    name="cup of coffee",
    default_input_unit=ureg.coffee_cup,
    default_comparison_unit=ureg.coffee_cup,
    prepare=quantity_prepare("coffee_cup"),
    impact_model=linear_factor_model(
        factor=Q_(0.18, "kg_co2e / coffee_cup"),
        source=FOOD_SOURCE,
        boundary="cradle_to_consumer",
        reference_unit="coffee_cup",
        assumptions=("One prepared cup of coffee",),
    ),
    equivalence=LinearEquivalence(),
    amount_name="cups",
    description="A prepared cup of coffee including representative supply-chain impacts.",
    examples=("wa.food.coffee(2)",),
)

cheese = _food_asset("cheese", "cheese", 13.5, "Representative hard cheese by mass.")
tofu = _food_asset("tofu", "tofu", 3.0, "Representative tofu by mass.")

meal_omnivore = _meal_asset("omnivore", 2.0)
meal_vegetarian = _meal_asset("vegetarian", 1.2)
meal_vegan = _meal_asset("vegan", 0.7)

ASSETS = (cervelat, coffee, cheese, tofu, meal_omnivore, meal_vegetarian, meal_vegan)
