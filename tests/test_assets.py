import pytest
from pint import DimensionalityError

import wattabout as wa


def test_train_impact_scales_with_distance() -> None:
    impact = wa.transport.train(100 * wa.km).impact()["climate"]

    assert impact.to("kg_co2e").magnitude == pytest.approx(0.71)


def test_car_occupancy_allocates_vehicle_impact() -> None:
    one_person = wa.transport.petrol_car(10 * wa.km).impact()["climate"]
    two_people = wa.transport.petrol_car(10 * wa.km, occupancy=2).impact()["climate"]

    assert two_people == one_person / 2


def test_cervelat_length_is_derived_from_geometry() -> None:
    one_mm = wa.food.cervelat(1 * wa.mm)

    assert one_mm.reference_amount.to("gram").magnitude == pytest.approx(0.9532, rel=0.001)
    assert one_mm.impact()["climate"].to("g_co2e").magnitude == pytest.approx(5.623, rel=0.001)


def test_cervelat_accepts_mass() -> None:
    impact = wa.food.cervelat(100 * wa.gram).impact()["climate"]

    assert impact.to("kg_co2e").magnitude == pytest.approx(0.59)


def test_invalid_asset_dimension_is_rejected() -> None:
    with pytest.raises(DimensionalityError):
        wa.transport.train(1 * wa.liter)


def test_invalid_occupancy_is_rejected() -> None:
    with pytest.raises(wa.WattAboutError, match="occupancy"):
        wa.transport.petrol_car(1 * wa.km, occupancy=0).impact()


def test_registry_contains_public_assets() -> None:
    assert len(wa.registry) == 51
    assert wa.registry.get("food.cervelat") is wa.food.cervelat


def test_activity_has_compact_representation() -> None:
    activity = wa.transport.train(10 * wa.km)

    assert str(activity) == "10 km of Swiss passenger train ride"
    assert repr(activity) == "71 g_CO2e"


def test_rate_activity_repr_shows_climate_impact_rate() -> None:
    activity = wa.buildings.minergie(120 * wa.m2)

    assert repr(activity) == "102 kg_CO2e / year"


def test_activity_repr_uses_active_context() -> None:
    activity = wa.energy.electricity(1 * wa.kWh)

    with wa.context(grid_intensity=0.1 * wa.kg_co2e / wa.kWh):
        assert repr(activity) == "100 g_CO2e"
