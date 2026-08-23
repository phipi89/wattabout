import pytest

import wattabout as wa


def test_boiling_uses_grid_intensity() -> None:
    low_carbon = wa.Context(grid_intensity=0.02 * wa.kg_co2e / wa.kWh)
    high_carbon = wa.Context(grid_intensity=0.4 * wa.kg_co2e / wa.kWh)
    activity = wa.household.boil_water(1 * wa.liter)

    low = activity.impact(low_carbon)["climate"]
    high = activity.impact(high_carbon)["climate"]

    assert high / low == pytest.approx(20)


def test_boiling_physics_is_in_expected_range() -> None:
    impact = wa.household.boil_water(1 * wa.liter).impact()["climate"]

    assert impact.to("g_co2e").magnitude == pytest.approx(9.88, rel=0.01)


def test_context_override_is_temporary() -> None:
    original = wa.get_context()

    with wa.context(region="DE", grid_intensity=0.4 * wa.kg_co2e / wa.kWh):
        assert wa.get_context().region == "DE"
        assert wa.get_context().grid_intensity.to("kg_co2e/kWh").magnitude == 0.4

    assert wa.get_context() is original


def test_invalid_efficiency_is_rejected() -> None:
    with pytest.raises(wa.WattAboutError, match="efficiency"):
        wa.household.boil_water(1 * wa.liter, efficiency=1.2).impact()


def test_temperature_parameters_affect_result() -> None:
    cool = wa.household.boil_water(1 * wa.liter, start_temperature=20 * wa.degC).impact()["climate"]
    cold = wa.household.boil_water(1 * wa.liter, start_temperature=5 * wa.degC).impact()["climate"]

    assert cold > cool
