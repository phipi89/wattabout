import pytest

import wattabout as wa


def test_categories_and_assets_are_discoverable() -> None:
    assert wa.categories() == (
        "building",
        "electronics",
        "energy",
        "food",
        "heating",
        "household",
        "transport",
    )
    assert wa.transport.assets() == ("bus", "ev", "petrol_car", "train")
    assert "ev" in dir(wa.transport)
    assert tuple(wa.transport) == tuple(wa.registry.assets("transport"))


def test_unknown_category_asset_uses_normal_attribute_error() -> None:
    with pytest.raises(AttributeError, match="no asset"):
        _ = wa.transport.teleporter


def test_asset_description_exposes_parameters_and_examples() -> None:
    description = wa.transport.ev.describe()

    assert "Electric car travel" in description
    assert "occupancy" in description
    assert "18 kWh / (100 km)" in description
    assert "wa.transport.ev" in description


def test_impact_records_selected_dataset() -> None:
    context = wa.Context(dataset="custom-dataset")

    assert wa.food.tofu(100 * wa.gram).impact(context).dataset == "custom-dataset"


def test_ev_operational_impact_uses_grid_context() -> None:
    low_grid = wa.Context(grid_intensity=0.02 * wa.kg_co2e / wa.kWh)
    high_grid = wa.Context(grid_intensity=0.4 * wa.kg_co2e / wa.kWh)
    activity = wa.transport.ev(100 * wa.km, include_vehicle=False)

    low = activity.impact(low_grid)["climate"]
    high = activity.impact(high_grid)["climate"]

    assert high / low == pytest.approx(20)


def test_ev_occupancy_allocates_impact() -> None:
    one_person = wa.transport.ev(100 * wa.km).impact()["climate"]
    two_people = wa.transport.ev(100 * wa.km, occupancy=2).impact()["climate"]

    assert two_people == one_person / 2


def test_electricity_and_phone_charge_use_same_grid_context() -> None:
    context = wa.Context(grid_intensity=0.1 * wa.kg_co2e / wa.kWh)
    charge = wa.electronics.phone_charge(
        1, battery_capacity=wa.Q_("20 Wh"), charging_efficiency=1
    ).impact(context)["climate"]
    electricity = wa.energy.electricity(wa.Q_("20 Wh")).impact(context)["climate"]

    assert charge == electricity


def test_embodied_electronics_assets_are_comparable() -> None:
    comparison = wa.electronics.laptop(1) / wa.electronics.phone(1)

    assert comparison.ratio == pytest.approx(250 / 70)
    assert str(comparison) == "3.57×"


def test_led_light_accepts_duration_and_power() -> None:
    context = wa.Context(grid_intensity=0.1 * wa.kg_co2e / wa.kWh)
    impact = wa.household.led_light(10 * wa.hour, power="10 W").impact(context)["climate"]

    assert impact.to("g_co2e").magnitude == pytest.approx(10)
