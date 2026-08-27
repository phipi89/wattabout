import pytest

import wattabout as wa


def test_direct_air_capture_scales_chf_by_price_and_delivery() -> None:
    removal = wa.nature.direct_air_capture(100 * wa.CHF)

    assert removal.emission.to("kg_co2e").magnitude == pytest.approx(-80)
    assert "contracted removal" in removal.impact().assumptions[2]


def test_direct_air_capture_can_represent_delivered_certificates() -> None:
    delivered = wa.nature.direct_air_capture(100 * wa.CHF, delivery_fraction=1)

    assert delivered.emission.to("kg_co2e").magnitude == pytest.approx(-100)


def test_emission_maps_to_positive_dac_spending() -> None:
    comparison = wa.electronics.phone() / wa.nature.direct_air_capture

    assert comparison.amount is not None
    assert comparison.amount.to("CHF").magnitude == pytest.approx(87.5)
    assert comparison.ratio == pytest.approx(-87.5 / 1)


def test_dac_concrete_ratio_remains_negative() -> None:
    comparison = wa.electronics.phone() / wa.nature.direct_air_capture(100 * wa.CHF)

    assert comparison.ratio == pytest.approx(-70 / 80)
    assert comparison.percentage == pytest.approx(-87.5)


@pytest.mark.parametrize("delivery_fraction", [-0.1, 1.1])
def test_dac_rejects_invalid_delivery_fraction(delivery_fraction: float) -> None:
    with pytest.raises(wa.WattAboutError, match="delivery_fraction"):
        wa.nature.direct_air_capture(100 * wa.CHF, delivery_fraction=delivery_fraction).impact()


def test_forest_fire_accepts_square_meters_and_scales_by_burned_area() -> None:
    fire = wa.nature.forest_fire(5_000 * wa.m2)

    assert fire.emission.to("tonne_co2e").magnitude == pytest.approx(37.5)
    assert fire.display_amount.to("hectare").magnitude == pytest.approx(0.5)


def test_forest_fire_factor_is_configurable() -> None:
    fire = wa.nature.forest_fire(2 * wa.hectare, emissions_per_area="20 tonne_co2e / hectare")

    assert fire.emission.to("tonne_co2e").magnitude == pytest.approx(40)


@pytest.mark.parametrize(
    ("profile", "megatonnes"),
    [
        ("mount_st_helens_1980", 10),
        ("pinatubo_1991", 50),
        ("etna_2004_2005", 3.8),
        ("small", 0.1),
    ],
)
def test_volcanic_profiles_use_explicit_co2_totals(profile: str, megatonnes: float) -> None:
    eruption = wa.nature.volcanic_eruption(1, profile=profile)

    assert eruption.emission.to("tonne_co2e").magnitude == pytest.approx(megatonnes * 1_000_000)


def test_volcanic_custom_event_and_unknown_profile() -> None:
    custom = wa.nature.volcanic_eruption(2, co2_per_event="250000 tonne_co2e")
    assert custom.emission.to("tonne_co2e").magnitude == pytest.approx(500_000)

    with pytest.raises(wa.WattAboutError, match="Unknown volcanic profile"):
        wa.nature.volcanic_eruption(1, profile="mystery").impact()


def test_rooftop_solar_has_positive_lifecycle_impact() -> None:
    solar = wa.energy.rooftop_solar(5_000 * wa.kWh)

    assert solar.emission.to("kg_co2e").magnitude == pytest.approx(200)


def test_rooftop_solar_can_power_an_oven_context() -> None:
    oven = wa.household.oven(30 * wa.minute, temperature=200 * wa.degC)

    with wa.context(wa.energy.rooftop_solar):
        solar_impact = oven.emission
    with wa.context(grid_intensity=0.085 * wa.kg_co2e / wa.kWh):
        grid_impact = oven.emission

    assert solar_impact / grid_impact == pytest.approx(0.04 / 0.085)


def test_explicit_electricity_context_matches_positional_form() -> None:
    light = wa.household.led_light(10 * wa.hour, power="10 W")

    with wa.context(wa.energy.rooftop_solar):
        positional = light.emission
    with wa.context(electricity=wa.energy.rooftop_solar):
        explicit = light.emission

    assert positional == explicit


def test_configured_diesel_generator_sets_effective_intensity_and_provenance() -> None:
    source = wa.energy.diesel.configure(generator_efficiency=0.5)

    with wa.context(source) as selected:
        impact = wa.household.led_light(1 * wa.hour, power="1 kW").impact()

    expected = (2.68 + 0.62) / (9.8 * 0.5)
    assert selected.grid_intensity.to("kg_co2e / kWh").magnitude == pytest.approx(expected)
    assert impact["climate"].to("kg_co2e").magnitude == pytest.approx(expected)
    assert "Electricity source: diesel generator" in impact.assumptions
    assert any("50%" in assumption for assumption in impact.assumptions)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (wa.energy.petrol, (2.31 + 0.54) / (8.9 * 0.3)),
        (wa.energy.natural_gas, 0.202 / 0.5),
    ],
)
def test_combustion_assets_can_supply_generator_electricity(source, expected: float) -> None:
    with wa.context(source) as selected:
        assert selected.grid_intensity.to("kg_co2e / kWh").magnitude == pytest.approx(expected)


def test_electricity_context_restores_and_rejects_conflicts() -> None:
    original = wa.get_context()

    with wa.context(wa.energy.rooftop_solar):
        assert wa.get_context().electricity_source_name == "rooftop solar"
    assert wa.get_context() is original

    with (
        pytest.raises(ValueError, match="both an electricity source and grid_intensity"),
        wa.context(
            wa.energy.rooftop_solar,
            grid_intensity=0.1 * wa.kg_co2e / wa.kWh,
        ),
    ):
        pass


def test_wood_pellets_are_not_an_electricity_source() -> None:
    with (
        pytest.raises(wa.WattAboutError, match="cannot supply electricity"),
        wa.context(wa.energy.wood_pellets),
    ):
        pass


def test_petrol_and_diesel_separate_tailpipe_and_upstream_factors() -> None:
    petrol = wa.energy.petrol(10 * wa.liter).emission
    diesel = wa.energy.diesel(10 * wa.liter).emission

    assert petrol.to("kg_co2e").magnitude == pytest.approx(10 * (2.31 + 0.54))
    assert diesel.to("kg_co2e").magnitude == pytest.approx(10 * (2.68 + 0.62))


def test_air_conditioning_uses_load_cop_duty_cycle_and_grid() -> None:
    context = wa.Context(grid_intensity=0.2 * wa.kg_co2e / wa.kWh)
    cooling = wa.household.air_conditioning(
        8 * wa.hour, cooling_load="2.5 kW", cop=2.5, duty_cycle=0.5
    )

    assert cooling.impact(context)["climate"].to("kg_co2e").magnitude == pytest.approx(
        8 * 2.5 / 2.5 * 0.5 * 0.2
    )


def test_air_conditioning_rate_integrates_to_direct_activity() -> None:
    rate = wa.household.air_conditioning.rate(cooling_load="2.5 kW", cop=3.5, duty_cycle=0.5)
    integrated = rate.over(8 * wa.hour)
    direct = wa.household.air_conditioning(8 * wa.hour)

    assert integrated.emission == direct.emission


def test_wood_pellets_count_gross_biogenic_co2_by_default() -> None:
    pellets = wa.energy.wood_pellets(1 * wa.kg)

    expected = 1.8 + 4.8 * (0.025 + 0.005)
    assert pellets.emission.to("kg_co2e").magnitude == pytest.approx(expected)
    assert any("No future forest regrowth" in item for item in pellets.impact().assumptions)


def test_wood_pellets_can_use_reporting_style_biogenic_accounting() -> None:
    pellets = wa.energy.wood_pellets(1 * wa.kg, include_biogenic_co2=False)

    assert pellets.emission.to("kg_co2e").magnitude == pytest.approx(4.8 * (0.025 + 0.005))
    assert any("Gross biogenic stack CO2: 1.8" in item for item in pellets.impact().assumptions)
