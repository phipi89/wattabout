import pytest

import wattabout as wa


def test_adding_activities_sums_climate_impacts() -> None:
    combo = wa.food.cervelat(10 * wa.cm) + wa.household.boil_water(1 * wa.liter)

    expected = (
        wa.food.cervelat(10 * wa.cm).impact()["climate"]
        + wa.household.boil_water(1 * wa.liter).impact()["climate"]
    )

    assert combo.impact()["climate"] == expected


def test_chained_addition_flattens_children() -> None:
    combo = (
        wa.food.cervelat(10 * wa.cm)
        + wa.household.boil_water(1 * wa.liter)
        + wa.electronics.phone()
    )

    assert len(combo.activities) == 3
    assert str(combo).count(" + ") == 2
    assert "smartphone production" in str(combo)


def test_subtraction_adds_a_negative_occurrence() -> None:
    coffee = wa.food.coffee()
    phone = wa.electronics.phone()

    difference = phone - coffee

    assert len(difference.activities) == 2
    assert difference.activities[1].occurrence_factor == -1
    assert difference.emission == phone.emission - coffee.emission
    assert str(difference) == f"{phone.summary_label} - {coffee.summary_label}"


def test_subtracting_combinations_flattens_and_formats_signed_factors() -> None:
    phone = wa.electronics.phone()
    coffee = wa.food.coffee()
    train = wa.transport.train(10 * wa.km)

    difference = phone - (2 * coffee + train)

    assert len(difference.activities) == 3
    assert difference.emission == phone.emission - 2 * coffee.emission - train.emission
    assert str(difference) == (
        f"{phone.summary_label} - 2 × {coffee.summary_label} - {train.summary_label}"
    )


def test_builtin_sum_works_via_radd() -> None:
    activities = [wa.food.coffee(), wa.food.coffee(), wa.electronics.phone()]

    combo = sum(activities)

    assert isinstance(combo, wa.CombinedActivities)
    assert len(combo.activities) == 3


def test_combined_activity_supports_comparisons() -> None:
    combo = wa.food.cervelat(10 * wa.cm) + wa.household.boil_water(1 * wa.liter)

    bare = combo / wa.transport.train
    concrete = combo / wa.transport.train(30 * wa.km)

    assert bare.amount is not None
    assert bare.amount.to("km").magnitude == pytest.approx(80.6, rel=0.01)
    assert isinstance(concrete.ratio, float)


def test_combined_impact_composes_sources() -> None:
    combo = wa.food.cervelat(10 * wa.cm) + wa.transport.train(100 * wa.km)
    citations = list(combo.impact().source.citations())

    assert len(citations) >= 3
    assert any("food lifecycle" in citation for citation in citations)
    assert any("transport" in citation for citation in citations)


def test_rate_and_total_cannot_be_added() -> None:
    with pytest.raises(wa.WattAboutError, match="rate and non-rate"):
        wa.buildings.minergie(100 * wa.m2) + wa.transport.train(10 * wa.km)


def test_rate_and_total_cannot_be_subtracted() -> None:
    with pytest.raises(wa.WattAboutError, match="rate and non-rate"):
        wa.buildings.minergie(100 * wa.m2) - wa.transport.train(10 * wa.km)


def test_rates_can_be_added_and_remain_a_rate() -> None:
    combo = wa.buildings.minergie(100 * wa.m2) + wa.buildings.house_1960s(100 * wa.m2)

    impact = combo.impact()["climate"]

    assert impact.check("kg_co2e / year")
    assert impact.to("kg_co2e / year").magnitude == pytest.approx(
        100 * 35 / 3.5 * 0.085 + 100 * 180 / 0.8 * 0.267
    )


def test_combined_repr_shows_summed_impact() -> None:
    combo = wa.food.coffee() + wa.food.coffee()

    assert repr(combo) == "360 g_CO2e"


def test_building_default_floor_area_is_swiss_average() -> None:
    activity = wa.buildings.minergie()

    assert activity.display_amount.to("m^2").magnitude == 120
    assert activity.impact()["climate"].to("kg_co2e / year").magnitude == pytest.approx(102)
    assert "Default amount" in wa.buildings.house_1960s.describe()


def test_default_amount_keeps_scalable_target_semantics() -> None:
    comparison = wa.electronics.phone() / wa.buildings.minergie()

    assert comparison.amount is not None
    assert comparison.amount.check("[length] ** 2")
    # 70 kg phone = one year of heating how many m² of MINERGIE-like building?
    assert comparison.amount.to("m^2").magnitude == pytest.approx(70 / (35 / 3.5 * 0.085))
    assert str(comparison).endswith("m²")
