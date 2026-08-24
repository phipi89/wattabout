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
    modern = wa.buildings.minergie(150 * wa.m2)
    old = wa.buildings.house_1960s(150 * wa.m2)

    modern_climate = modern.impact()["climate"].to("kg_co2e / year").magnitude
    old_climate = old.impact()["climate"].to("kg_co2e / year").magnitude

    assert modern_climate == pytest.approx(127.5)
    assert old_climate == pytest.approx(9011.25)
    assert (modern / old).ratio == pytest.approx(modern_climate / old_climate)


def test_building_rate_scales_with_area_and_integrates_explicitly() -> None:
    building = wa.buildings.minergie(100 * wa.m2)
    annual_rate = building.impact()["climate"]
    larger_rate = wa.buildings.minergie(200 * wa.m2).impact()["climate"]
    two_year_total = building.over(2 * wa.year).impact()["climate"]

    assert larger_rate == annual_rate * 2
    assert two_year_total.to("kg_co2e").magnitude == pytest.approx(
        annual_rate.to("kg_co2e / year").magnitude * 2
    )


def test_building_duration_keyword_is_integration_shorthand() -> None:
    shorthand = wa.buildings.minergie(120 * wa.m2, duration=1 * wa.year)
    explicit = wa.buildings.minergie(120 * wa.m2).over(1 * wa.year)

    assert shorthand.impact()["climate"] == explicit.impact()["climate"]
    assert not shorthand.impact().is_rate
    assert "over 1 year" in str(shorthand)


def test_total_compared_to_concrete_building_rate_returns_duration() -> None:
    inference = wa.ai.frontier_llm(1 * wa.million_token)
    building_rate = wa.buildings.minergie(120 * wa.m2)

    comparison = inference / building_rate

    assert comparison.amount is not None
    assert comparison.amount.to("day").magnitude == pytest.approx(0.72 / 102 * 365.25)
    assert str(comparison) == "2.58 d"


def test_building_impact_intensity_retains_area_and_time_units() -> None:
    building = wa.buildings.house_1990s(120 * wa.m2)

    intensity = building.impact_intensity()["climate"]

    assert intensity.to("kg_co2e / m^2 / year").magnitude == pytest.approx(110 / 0.9 * 0.202)


def test_building_accepts_configured_heating_system() -> None:
    heating = wa.heating.heat_pump.configure(scop=5)
    impact = wa.buildings.minergie(100 * wa.m2, heating=heating).impact()["climate"]

    expected = 100 * 35 / 5 * 0.085
    assert impact.to("kg_co2e / year").magnitude == pytest.approx(expected)


def test_custom_building_requires_demand_and_heating() -> None:
    with pytest.raises(wa.MissingParameterError, match="heating, specific_heat_demand"):
        wa.buildings.custom(100 * wa.m2)


def test_building_explanation_includes_composed_sources() -> None:
    comparison = wa.buildings.minergie(100 * wa.m2) / wa.buildings.house_1960s(100 * wa.m2)
    explanation = comparison.explain()

    assert "MINERGIE standard overview" in explanation
    assert "heat-pump performance" in explanation
    assert "1960s Swiss house" in explanation
    assert "boiler performance" in explanation
    assert not comparison.warnings


def test_building_bare_target_returns_equivalent_floor_area() -> None:
    source = wa.buildings.minergie(100 * wa.m2)

    comparison = source / wa.buildings.house_1960s

    assert comparison.amount is not None
    assert comparison.amount.to("m^2").magnitude == pytest.approx(100 * 127.5 / 9011.25)


def test_decade_profiles_have_decreasing_heat_demand() -> None:
    heating = wa.heating.heat_pump.configure(scop=1)
    profiles = (
        wa.buildings.house_1980s,
        wa.buildings.house_1990s,
        wa.buildings.house_2000s,
    )

    impacts = [profile(100 * wa.m2, heating=heating).impact()["climate"] for profile in profiles]

    assert impacts[0] > impacts[1] > impacts[2]
    assert impacts[0] / impacts[1] == pytest.approx(150 / 110)
    assert impacts[1] / impacts[2] == pytest.approx(110 / 75)


def test_decade_profile_defaults_are_documented_and_names_are_consistent() -> None:
    assert "150 kWh_th/m²/year" in wa.buildings.house_1980s.describe()
    assert "110 kWh_th/m²/year" in wa.buildings.house_1990s.describe()
    assert "75 kWh_th/m²/year" in wa.buildings.house_2000s.describe()
    assert not hasattr(wa, "building")
    assert "house_1990" not in wa.buildings.list_assets()


def test_building_to_one_off_asset_retains_annual_unit() -> None:
    house = wa.buildings.house_1990s(120 * wa.m2)

    bare_comparison = house / wa.electronics.phone
    concrete_comparison = house / wa.electronics.phone()

    for comparison in (bare_comparison, concrete_comparison):
        assert comparison.amount is not None
        assert comparison.amount.to("phone_device / year").magnitude == pytest.approx(
            120 * 110 / 0.9 * 0.202 / 70
        )
        assert "/ year" in str(comparison)
