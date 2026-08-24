import pytest

import wattabout as wa


def test_flight_has_fixed_takeoff_component() -> None:
    short = wa.transport.flight(100 * wa.km).impact()["climate"]
    long = wa.transport.flight(200 * wa.km).impact()["climate"]

    # Affine model: doubling distance adds less than the total impact
    assert (long - short) < short
    assert short.to("kg_co2e").magnitude == pytest.approx((70 + 20) * 2)


def test_flight_per_km_intensity_decreases_with_distance() -> None:
    continental = wa.transport.flight(800 * wa.km).impact()["climate"]
    intercontinental = wa.transport.flight(6000 * wa.km).impact()["climate"]

    per_km_cont = (continental / 800).magnitude
    per_km_long = (intercontinental / 6000).magnitude

    assert per_km_cont > per_km_long


def test_flight_cabin_class_multiplies_impact() -> None:
    economy = wa.transport.flight(6000 * wa.km).impact()["climate"]
    business = wa.transport.flight(6000 * wa.km, cabin_class="business").impact()["climate"]

    assert (business / economy).magnitude == pytest.approx(2.9)


def test_flight_non_co2_multiplier_is_configurable() -> None:
    with_co2_only = wa.transport.flight(6000 * wa.km, non_co2_multiplier=1).impact()["climate"]
    with_effects = wa.transport.flight(6000 * wa.km).impact()["climate"]

    assert (with_effects / with_co2_only).magnitude == pytest.approx(2)
    assert with_co2_only.to("kg_co2e").magnitude == pytest.approx(70 + 0.20 * 3800 + 0.11 * 2200)


def test_invalid_flight_parameters_are_rejected() -> None:
    with pytest.raises(wa.WattAboutError, match="cabin_class"):
        wa.transport.flight(500 * wa.km, cabin_class="standing").impact()
    with pytest.raises(wa.WattAboutError, match="non_co2_multiplier"):
        wa.transport.flight(500 * wa.km, non_co2_multiplier=0.5).impact()


def test_private_jet_divides_across_passengers() -> None:
    four = wa.transport.flight_private(500 * wa.km).impact()["climate"]
    eight = wa.transport.flight_private(500 * wa.km, passengers=8).impact()["climate"]

    assert (four / eight).magnitude == pytest.approx(2)


def test_flight_inversion_solves_distance_below_breakpoint() -> None:
    target = wa.transport.flight.configure()
    comparison = wa.electronics.laptop(2) / target

    assert comparison.amount is not None
    # Effective per-passenger defaults: fixed 400/4*2 = 200 kg, rate 1.6/4*2 = 0.8 kg/km
    expected_km = (500 - 200) / 0.8
    assert comparison.amount.to("km").magnitude == pytest.approx(expected_km)
    assert str(comparison).endswith("km")


def test_flight_inversion_crosses_breakpoint_for_large_sources() -> None:
    source = wa.buildings.house_1960s(120 * wa.m2).over(1 * wa.year)
    target = wa.transport.flight.configure()

    comparison = source / target

    assert comparison.amount is not None
    assert comparison.amount.to("km").magnitude > 3800


def test_flight_below_takeoff_minimum_raises() -> None:
    target = wa.transport.flight.configure()

    with pytest.raises(wa.NoEquivalentAmountError, match="takeoff-and-landing"):
        wa.transport.train(100 * wa.km) / target


def test_tree_growth_is_quadratic_then_linear() -> None:
    thirty = wa.nature.tree_growth(30 * wa.year).impact()["climate"]
    sixty = wa.nature.tree_growth(60 * wa.year).impact()["climate"]

    assert thirty.to("kg_co2e").magnitude == pytest.approx(-236.25)
    assert sixty.to("kg_co2e").magnitude == pytest.approx(-840.0)
    # Quadratic while young: average annual absorption rises with age
    assert abs(thirty) / 30 > abs(wa.nature.tree_growth(15 * wa.year).impact()["climate"]) / 15


def test_negative_ratios_flow_through_comparisons() -> None:
    tree = wa.nature.tree_growth(30 * wa.year)

    concrete = tree / wa.electronics.phone()
    assert isinstance(concrete.ratio, float)
    assert concrete.ratio == pytest.approx(-236.25 / 70)
    assert str(concrete).startswith("-")


def test_phone_maps_to_tree_absorption_years() -> None:
    comparison = wa.electronics.phone() / wa.nature.tree_growth

    assert comparison.amount is not None
    years = comparison.amount.to("year").magnitude
    assert years == pytest.approx(16.3, rel=0.01)
    assert "year" in str(comparison)


def test_meal_assets_are_separate_and_linear() -> None:
    omnivore = wa.food.meal_omnivore(1).impact()["climate"]
    vegetarian = wa.food.meal_vegetarian(1).impact()["climate"]
    vegan = wa.food.meal_vegan(2).impact()["climate"]

    assert omnivore.to("kg_co2e").magnitude == pytest.approx(2.0)
    assert vegetarian.to("kg_co2e").magnitude == pytest.approx(1.2)
    assert vegan.to("kg_co2e").magnitude == pytest.approx(1.4)
    assert str(wa.food.meal_omnivore(1) / wa.food.meal_vegan).endswith("meal")


def test_laptop_use_uses_macbook_like_default_power() -> None:
    context = wa.Context(grid_intensity=0.1 * wa.kg_co2e / wa.kWh)

    impact = wa.electronics.laptop_use(8 * wa.hour).impact(context)["climate"]

    assert impact.to("g_co2e").magnitude == pytest.approx(8)
    assert "M-series MacBook" in wa.electronics.laptop_use.describe()


def test_laptop_use_rate_supports_duration_integration() -> None:
    context = wa.Context(grid_intensity=0.1 * wa.kg_co2e / wa.kWh)

    rate = wa.electronics.laptop_use.rate(power="10 W")
    shorthand = wa.electronics.laptop_use.rate(duration=8 * wa.hour, power="10 W")
    direct = wa.electronics.laptop_use(8 * wa.hour, power="10 W")

    assert rate.impact(context)["climate"].to("g_co2e / hour").magnitude == pytest.approx(1)
    assert shorthand.impact(context)["climate"] == direct.impact(context)["climate"]


def test_mixed_waste_scales_with_mass() -> None:
    impact = wa.waste.mixed(20 * wa.kg).impact()["climate"]

    assert impact.to("kg_co2e").magnitude == pytest.approx(11.6)
    assert str(wa.transport.train(30 * wa.km) / wa.waste.mixed).endswith("kg")


def test_parcel_from_china_defaults_to_air() -> None:
    air = wa.shipping.parcel_from_china(1).impact()["climate"]
    rail = wa.shipping.parcel_from_china(1, mode="rail").impact()["climate"]
    sea = wa.shipping.parcel_from_china(3, mode="sea", mass="2 kg").impact()["climate"]

    assert air.to("kg_co2e").magnitude == pytest.approx(0.25 + 4.0)
    assert rail.to("kg_co2e").magnitude == pytest.approx(0.25 + 0.12)
    assert sea.to("kg_co2e").magnitude == pytest.approx(3 * (0.25 + 2 * 0.08))


def test_parcel_rejects_unknown_mode() -> None:
    with pytest.raises(wa.WattAboutError, match="transport mode"):
        wa.shipping.parcel_from_china(1, mode="drone").impact()


def test_new_categories_are_discoverable() -> None:
    assert wa.nature.list_assets() == ("tree_growth",)
    assert wa.shipping.list_assets() == ("parcel_from_china",)
    assert wa.waste.list_assets() == ("mixed",)
