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
