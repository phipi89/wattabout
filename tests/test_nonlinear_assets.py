import pytest

import wattabout as wa


def test_oven_includes_fixed_preheating_energy() -> None:
    twenty_minutes = wa.household.oven(20 * wa.minute, temperature=200 * wa.degC)
    forty_minutes = wa.household.oven(40 * wa.minute, temperature=200 * wa.degC)

    comparison = twenty_minutes / forty_minutes

    assert comparison.ratio == pytest.approx((0.5 + 0.8 / 3) / (0.5 + 1.6 / 3))
    assert comparison.ratio > 0.5


def test_oven_temperature_is_required() -> None:
    with pytest.raises(wa.MissingParameterError, match="temperature"):
        wa.household.oven(20 * wa.minute)


def test_unknown_parameters_are_rejected() -> None:
    with pytest.raises(wa.WattAboutError, match="Unknown parameter"):
        wa.household.oven(20 * wa.minute, temperature=200 * wa.degC, turbo=True)


def test_configured_oven_solves_equivalent_duration() -> None:
    target = wa.household.oven.configure(temperature=200 * wa.degC)

    comparison = wa.energy.electricity(1 * wa.kWh) / target

    assert comparison.amount is not None
    assert comparison.amount.to("minute").magnitude == pytest.approx(37.5)
    assert str(comparison) == "37.5 min"


def test_cold_oven_has_minimum_session_impact() -> None:
    target = wa.household.oven.configure(temperature=200 * wa.degC)

    with pytest.raises(wa.NoEquivalentAmountError, match="minimum cold-start"):
        wa.energy.electricity(0.1 * wa.kWh) / target


def test_concrete_oven_ratio_survives_equivalence_gap() -> None:
    comparison = wa.energy.electricity(0.1 * wa.kWh) / wa.household.oven(
        20 * wa.minute, temperature=200 * wa.degC
    )

    assert comparison.ratio == pytest.approx(0.1 / (0.5 + 0.8 / 3))
    assert comparison.amount is None


def test_preheated_oven_is_linear_in_cooking_duration() -> None:
    target = wa.household.oven.configure(temperature=200 * wa.degC, include_preheating=False)

    comparison = wa.energy.electricity(0.4 * wa.kWh) / target

    assert comparison.amount is not None
    assert comparison.amount.to("minute").magnitude == pytest.approx(30)


def test_refrigerator_uses_average_load() -> None:
    context = wa.Context(grid_intensity=0.1 * wa.kg_co2e / wa.kWh)
    impact = wa.household.refrigerator(24 * wa.hour).impact(context)["climate"]

    assert impact.to("g_co2e").magnitude == pytest.approx(72)


def test_dishwasher_uses_energy_per_complete_cycle() -> None:
    context = wa.Context(grid_intensity=0.1 * wa.kg_co2e / wa.kWh)
    impact = wa.household.dishwasher(2).impact(context)["climate"]

    assert impact.to("g_co2e").magnitude == pytest.approx(160)


def test_preheated_oven_rate_excludes_startup_energy() -> None:
    context = wa.Context(grid_intensity=0.1 * wa.kg_co2e / wa.kWh)
    oven_rate = wa.household.oven.rate(temperature=200 * wa.degC)

    impact = oven_rate.impact(context)["climate"]
    two_hour_total = oven_rate.over(2 * wa.hour).impact(context)["climate"]

    assert impact.to("g_co2e / hour").magnitude == pytest.approx(80)
    assert two_hour_total.to("g_co2e").magnitude == pytest.approx(160)
    assert "operating rate" in str(oven_rate)


def test_configured_oven_exposes_rate() -> None:
    configured = wa.household.oven.configure(temperature=220 * wa.degC)

    assert configured.rate().impact().is_rate


def test_building_rate_compares_to_oven_rate_dimensionlessly() -> None:
    house = wa.buildings.house_1990s(120 * wa.m2)
    oven = wa.household.oven.rate(temperature=220 * wa.degC)

    comparison = house / oven

    assert isinstance(comparison.ratio, float)
    assert str(comparison).endswith("×")


def test_rate_duration_keyword_matches_explicit_integration() -> None:
    configured_oven = wa.household.oven.configure(temperature=200 * wa.degC)
    oven_shorthand = configured_oven.rate(duration=2 * wa.hour)
    oven_explicit = configured_oven.rate().over(2 * wa.hour)
    refrigerator_shorthand = wa.household.refrigerator.rate(duration=24 * wa.hour)
    refrigerator_direct = wa.household.refrigerator(24 * wa.hour)
    light_shorthand = wa.household.led_light.rate(duration=5 * wa.hour, power="10 W")
    light_direct = wa.household.led_light(5 * wa.hour, power="10 W")

    assert oven_shorthand.impact()["climate"] == oven_explicit.impact()["climate"]
    assert refrigerator_shorthand.impact()["climate"] == refrigerator_direct.impact()["climate"]
    assert light_shorthand.impact()["climate"] == light_direct.impact()["climate"]
