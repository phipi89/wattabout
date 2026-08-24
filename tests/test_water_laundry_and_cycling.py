import pytest

import wattabout as wa


def test_hot_water_uses_physical_heat_and_water_services() -> None:
    context = wa.Context(
        grid_intensity=0.085 * wa.kg_co2e / wa.kWh,
        water_services_intensity=0.0005 * wa.kg_co2e / wa.liter,
    )

    impact = wa.household.hot_water(1 * wa.liter).impact(context)["climate"]

    useful_kwh = 4.186 * 25 / 3600
    assert impact.to("kg_co2e").magnitude == pytest.approx(useful_kwh * 0.085 + 0.0005)


def test_default_shower_is_eight_minutes_at_nine_liters_per_minute() -> None:
    shower = wa.household.shower()
    impact = shower.impact()

    assert shower.display_amount == 8 * wa.minute
    assert any("Water volume: 72.0 l" in assumption for assumption in impact.assumptions)
    assert impact["climate"].to("kg_co2e").magnitude == pytest.approx(0.2139, rel=0.01)


def test_shower_accepts_configured_heat_pump() -> None:
    resistance = wa.household.shower(8 * wa.minute).emission
    heat_pump = wa.household.shower(
        8 * wa.minute,
        heating=wa.heating.heat_pump.configure(scop=3),
    ).emission

    assert heat_pump < resistance


def test_shower_flow_and_context_water_factor_are_configurable() -> None:
    context = wa.Context(
        grid_intensity=0 * wa.kg_co2e / wa.kWh,
        water_services_intensity=0.001 * wa.kg_co2e / wa.liter,
    )
    shower = wa.household.shower(5 * wa.minute, flow_rate="6 liter / minute")

    assert shower.impact(context)["climate"].to("kg_co2e").magnitude == pytest.approx(0.03)


def test_shower_rejects_invalid_temperature_and_flow() -> None:
    with pytest.raises(wa.WattAboutError, match="temperature"):
        wa.household.shower(5 * wa.minute, temperature="10 degC").impact()
    with pytest.raises(wa.WattAboutError, match="flow_rate"):
        wa.household.shower(5 * wa.minute, flow_rate="-1 liter / minute").impact()


def test_washing_machine_includes_electricity_water_and_detergent() -> None:
    context = wa.Context(
        grid_intensity=0.1 * wa.kg_co2e / wa.kWh,
        water_services_intensity=0.001 * wa.kg_co2e / wa.liter,
    )

    impact = wa.household.washing_machine(1).impact(context)["climate"]

    assert impact.to("kg_co2e").magnitude == pytest.approx(0.6 * 0.1 + 50 * 0.001 + 0.1)


def test_tumble_dryer_uses_grid_context() -> None:
    context = wa.Context(grid_intensity=0.2 * wa.kg_co2e / wa.kWh)

    impact = wa.household.tumble_dryer(2).impact(context)["climate"]

    assert impact.to("kg_co2e").magnitude == pytest.approx(2 * 1.5 * 0.2)


def test_bicycle_excludes_rider_food_and_uses_lifecycle_rate() -> None:
    impact = wa.transport.bicycle(10 * wa.km).impact()

    assert impact["climate"].to("kg_co2e").magnitude == pytest.approx(0.05)
    assert any("Rider food" in assumption for assumption in impact.assumptions)


def test_ebike_combines_lifecycle_and_grid_sensitive_charging() -> None:
    low_grid = wa.Context(grid_intensity=0 * wa.kg_co2e / wa.kWh)
    high_grid = wa.Context(grid_intensity=0.2 * wa.kg_co2e / wa.kWh)
    ride = wa.transport.ebike(10 * wa.km)

    low = ride.impact(low_grid)["climate"].to("kg_co2e").magnitude
    high = ride.impact(high_grid)["climate"].to("kg_co2e").magnitude

    assert low == pytest.approx(0.12)
    assert high == pytest.approx(0.12 + 10 * 0.01 / 0.9 * 0.2)


def test_new_cycle_units_are_public() -> None:
    assert wa.household.washing_machine(2 * wa.laundry_cycle).display_amount.magnitude == 2
    assert wa.household.tumble_dryer(2 * wa.dryer_cycle).display_amount.magnitude == 2
