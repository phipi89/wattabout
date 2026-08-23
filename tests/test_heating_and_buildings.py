import pytest
from pint import DimensionalityError

import wattabout as wa


def test_heat_pump_converts_useful_heat_using_scop() -> None:
    context = wa.Context(grid_intensity=0.1 * wa.kg_co2e / wa.kWh)
    impact = wa.heating.heat_pump(10_000 * wa.kWh_th, scop=4).impact(context)["climate"]

    assert impact.to("kg_co2e").magnitude == pytest.approx(250)


def test_oil_boiler_uses_efficiency_and_context_intensity() -> None:
    context = wa.Context(heating_oil_intensity=0.25 * wa.kg_co2e / wa.kWh)
    impact = wa.heating.oil_boiler(10_000 * wa.kWh_th, efficiency=0.8).impact(context)["climate"]

    assert impact.to("kg_co2e").magnitude == pytest.approx(3125)


def test_heating_requires_useful_heat_units() -> None:
    with pytest.raises(DimensionalityError):
        wa.heating.heat_pump(100 * wa.kWh)


def test_building_profiles_compose_demand_and_heating() -> None:
    modern = wa.building.minergie(150 * wa.m2)
    old = wa.building.house_1960s(150 * wa.m2)

    modern_climate = modern.impact()["climate"].to("kg_co2e").magnitude
    old_climate = old.impact()["climate"].to("kg_co2e").magnitude

    assert modern_climate == pytest.approx(127.5)
    assert old_climate == pytest.approx(9011.25)
    assert (modern / old).ratio == pytest.approx(modern_climate / old_climate)


def test_building_impact_scales_with_area_and_duration() -> None:
    one_year = wa.building.minergie(100 * wa.m2).impact()["climate"]
    two_years = wa.building.minergie(200 * wa.m2, duration=2 * wa.year).impact()["climate"]

    assert two_years == one_year * 4


def test_building_accepts_configured_heating_system() -> None:
    heating = wa.heating.heat_pump.configure(scop=5)
    impact = wa.building.minergie(100 * wa.m2, heating=heating).impact()["climate"]

    expected = 100 * 35 / 5 * 0.085
    assert impact.to("kg_co2e").magnitude == pytest.approx(expected)


def test_custom_building_requires_demand_and_heating() -> None:
    with pytest.raises(wa.MissingParameterError, match="heating, specific_heat_demand"):
        wa.building.custom(100 * wa.m2)


def test_building_explanation_includes_composed_sources() -> None:
    comparison = wa.building.minergie(100 * wa.m2) / wa.building.house_1960s(100 * wa.m2)
    explanation = comparison.explain()

    assert "MINERGIE standard overview" in explanation
    assert "heat-pump performance" in explanation
    assert "1960s Swiss house" in explanation
    assert "boiler performance" in explanation
    assert not comparison.warnings


def test_building_bare_target_returns_equivalent_floor_area() -> None:
    source = wa.building.minergie(100 * wa.m2)

    comparison = source / wa.building.house_1960s

    assert comparison.amount is not None
    assert comparison.amount.to("m^2").magnitude == pytest.approx(100 * 127.5 / 9011.25)


def test_decade_profiles_have_decreasing_heat_demand() -> None:
    heating = wa.heating.heat_pump.configure(scop=1)
    profiles = (
        wa.buildings.house_1980,
        wa.buildings.house_1990,
        wa.buildings.house_2000,
    )

    impacts = [profile(100 * wa.m2, heating=heating).impact()["climate"] for profile in profiles]

    assert impacts[0] > impacts[1] > impacts[2]
    assert impacts[0] / impacts[1] == pytest.approx(150 / 110)
    assert impacts[1] / impacts[2] == pytest.approx(110 / 75)


def test_decade_profile_defaults_are_documented() -> None:
    assert "150 kWh_th/m²/year" in wa.building.house_1980.describe()
    assert "110 kWh_th/m²/year" in wa.building.house_1990.describe()
    assert "75 kWh_th/m²/year" in wa.building.house_2000.describe()
    assert wa.buildings is wa.building
