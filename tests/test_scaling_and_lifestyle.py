import pytest

import wattabout as wa


def test_multiplication_repeats_a_nonlinear_activity() -> None:
    flight = wa.transport.flight(8_000 * wa.km)

    repeated = 2 * flight

    assert repeated.emission == 2 * flight.emission
    assert repeated.emission != wa.transport.flight(16_000 * wa.km).emission
    assert repeated.reference_amount == flight.reference_amount
    assert str(repeated).startswith("2 × ")


def test_multiplication_works_on_both_sides_and_combinations() -> None:
    first = wa.food.coffee() + wa.electronics.phone()

    left = 0.5 * first
    right = first * 0.5

    assert isinstance(left, wa.CombinedActivities)
    assert left.emission == right.emission == first.emission * 0.5


def test_zero_multiplier_has_zero_impact() -> None:
    assert (0 * wa.transport.flight(8_000 * wa.km)).emission.magnitude == 0


@pytest.mark.parametrize("factor", [-1, float("inf"), float("nan")])
def test_invalid_activity_multipliers_are_rejected(factor: float) -> None:
    with pytest.raises(wa.WattAboutError, match="multiplier"):
        factor * wa.food.coffee()


def test_emission_and_grid_energy_equivalent_use_active_context() -> None:
    activity = wa.food.cervelat(100 * wa.gram)

    with wa.context(grid_intensity=0.2 * wa.kg_co2e / wa.kWh):
        assert activity.emission.to("kg_co2e").magnitude == pytest.approx(0.59)
        assert activity.energy.to("kWh").magnitude == pytest.approx(2.95)


def test_rate_energy_equivalent_retains_its_time_basis() -> None:
    with wa.context(grid_intensity=0.1 * wa.kg_co2e / wa.kWh):
        energy = wa.buildings.minergie(120 * wa.m2).energy

    assert energy.check("[energy] / [time]")
    assert energy.to("kWh / year").magnitude == pytest.approx(1_200)


def test_lifestyle_benchmark_accepts_daily_duration() -> None:
    daily = wa.lifestyle.swiss_resident(1 * wa.day)

    assert daily.display_amount == 1 * wa.day
    assert daily.emission.to("kg_co2e").magnitude == pytest.approx(13_339.576 / 365.25)
    assert daily.impact().geography == "CH"
    assert daily.impact().reference_year == 2023


def test_lifestyle_percentage_is_available_on_concrete_comparisons() -> None:
    comparison = wa.food.cervelat(100 * wa.gram) / wa.lifestyle.swiss_resident(1 * wa.day)

    assert comparison.percentage == pytest.approx(float(comparison) * 100)
    assert comparison.percentage == pytest.approx(1.615, rel=0.01)


def test_all_requested_lifestyle_benchmarks_are_discoverable() -> None:
    assert wa.lifestyle.list_assets() == (
        "china_resident",
        "european_resident",
        "india_resident",
        "swiss_resident",
        "us_resident",
    )
