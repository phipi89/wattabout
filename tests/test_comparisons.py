import pytest

import wattabout as wa
from wattabout.units import ureg


def test_compact_train_to_cervelat_comparison() -> None:
    comparison = wa.transport.train(1 * wa.km) / wa.food.cervelat

    assert comparison.metric == "climate"
    assert comparison.amount.to("mm").magnitude == pytest.approx(1.263, rel=0.01)
    assert str(comparison) == "1.26 mm"
    assert repr(comparison) == "1.26 mm"
    assert comparison.warnings


def test_explicit_target_unit() -> None:
    comparison = wa.transport.train(10 * wa.km).equivalent_to(wa.food.cervelat, unit="gram")

    assert comparison.amount.to("gram").magnitude == pytest.approx(12.0339)


def test_comparison_explanation_contains_provenance_and_assumptions() -> None:
    explanation = wa.transport.train(1 * wa.km).equivalent_to(wa.food.cervelat).explain()

    assert "Source impact:" in explanation
    assert "Mobitool" in explanation
    assert "Assumptions:" in explanation
    assert "Warnings:" in explanation


def test_activity_target_reports_amount_and_reference_ratio() -> None:
    comparison = wa.food.cervelat(wa.Q_("10 cm")) / wa.transport.train(wa.Q_("10 km"))

    assert comparison.amount.to("km").magnitude == pytest.approx(79.2, rel=0.01)
    assert comparison.ratio == pytest.approx(7.92, rel=0.01)
    assert str(comparison) == "7.92×"
    assert repr(comparison) == "7.92×"
    assert float(comparison) == pytest.approx(7.92, rel=0.01)


def test_activity_target_preserves_parameters() -> None:
    comparison = wa.transport.train(10 * wa.km) / wa.transport.petrol_car(1 * wa.km, occupancy=2)

    assert comparison.amount.to("km").magnitude == pytest.approx(0.830, rel=0.01)
    assert comparison.ratio == pytest.approx(0.830, rel=0.01)


def test_target_parameters_cannot_be_repeated_for_activity() -> None:
    target = wa.transport.petrol_car(1 * wa.km, occupancy=2)

    with pytest.raises(wa.WattAboutError, match="Target parameters"):
        wa.transport.train(1 * wa.km).equivalent_to(target, occupancy=3)


def test_asset_target_ratio_is_convertible_to_float() -> None:
    comparison = wa.food.cervelat(2.5 * wa.mm) / wa.transport.train

    assert isinstance(comparison.ratio, float)
    assert float(comparison) == comparison.ratio


def test_dimensional_ratio_cannot_be_converted_to_float() -> None:
    comparison = wa.electronics.phone() / wa.household.refrigerator.rate()

    with pytest.raises(TypeError, match="dimensionless"):
        float(comparison)


def test_unknown_metric_has_clear_error() -> None:
    with pytest.raises(wa.MissingMetricError, match="water"):
        wa.transport.train(1 * wa.km).equivalent_to(wa.food.cervelat, metric="water")


def test_omitted_target_amount_behaves_like_bare_asset() -> None:
    source = wa.electronics.phone()

    bare = source / wa.household.boil_water
    omitted = source / wa.household.boil_water()

    assert bare.amount is not None
    assert omitted.amount is not None
    assert omitted.amount.to("liter") == bare.amount.to("liter")
    assert str(omitted) == "7.08×10³ L"


def test_explicit_target_amount_remains_concrete_ratio() -> None:
    comparison = wa.electronics.phone() / wa.household.boil_water(1 * wa.liter)

    assert isinstance(comparison.ratio, float)
    assert str(comparison) == "7.08e+03×"


def test_omitted_parameterized_target_is_scalable() -> None:
    comparison = wa.electronics.phone() / wa.household.oven(temperature=200 * wa.degC)

    assert comparison.amount is not None
    assert comparison.amount.to("minute").magnitude == pytest.approx(61_727, rel=0.01)
    assert str(comparison).endswith("min")


def test_omitted_and_bare_targets_match_across_default_catalog() -> None:
    source = wa.electronics.phone()
    default_assets = [
        asset
        for asset in wa.registry
        if not any(parameter.required for parameter in asset.parameters)
    ]

    for asset in default_assets:
        try:
            bare = source / asset
            omitted = source / asset()
        except wa.NoEquivalentAmountError:
            continue
        assert bare.amount is not None, asset.id
        assert omitted.amount is not None, asset.id
        assert omitted.amount.to(bare.amount.units).magnitude == pytest.approx(
            bare.amount.magnitude
        ), asset.id


def test_rate_targets_are_always_concrete() -> None:
    rate = wa.household.refrigerator.rate()

    comparison = wa.electronics.phone() / rate

    assert not isinstance(comparison.ratio, float)
    assert comparison.amount is not None
    assert comparison.amount.check("[time]")


def test_ratio_and_amount_invariant_holds_across_catalog() -> None:
    source = wa.electronics.phone()
    for asset in wa.registry:
        if asset.id == "nature.tree_growth":
            continue  # matches by absorption magnitude, so signs differ by design
        if any(parameter.required for parameter in asset.parameters):
            targets: tuple[object, ...] = ()
        else:
            targets = (asset, asset())
        for target in targets:
            try:
                comparison = source.equivalent_to(target)
            except wa.NoEquivalentAmountError:
                continue
            expected = comparison.amount / comparison.target_reference.display_amount
            if isinstance(comparison.ratio, float):
                assert comparison.ratio == pytest.approx(
                    expected.to(ureg.dimensionless).magnitude
                ), asset.id
            else:
                # Dimensional ratios keep their raw units (e.g. year); the
                # invariant is then numeric equality with the cancelled form.
                assert comparison.ratio.magnitude == pytest.approx(expected.magnitude), asset.id


def test_archetype_vs_archetype_prefers_ratio_for_matching_dimensions() -> None:
    comparison = wa.transport.ev() / wa.transport.petrol_car

    assert str(comparison) == "0.47×"
    ev_per_km = 0.18 * 0.085 + 0.065
    assert comparison.ratio == pytest.approx(ev_per_km / 0.171, rel=0.001)
    assert float(comparison) == comparison.ratio


def test_explicit_source_keeps_equivalent_amount_for_like_dimensions() -> None:
    comparison = wa.transport.train(30 * wa.km) / wa.transport.petrol_car

    assert comparison.amount is not None
    assert comparison.amount.check("[length]")
    assert "km" in str(comparison)
    assert "×" not in str(comparison)


def test_building_default_comparison_shows_ratio() -> None:
    old = wa.buildings.house_1960s()
    modern = wa.buildings.house_2000s()
    minergie = wa.buildings.minergie()

    omitted = old / modern
    bare = old / wa.buildings.house_2000s

    expected = (old.emission / modern.emission).to(ureg.dimensionless).magnitude
    assert omitted.ratio == pytest.approx(expected)
    assert omitted.ratio == pytest.approx(3.5688, rel=0.001)
    assert bare.ratio == omitted.ratio
    assert omitted.target_reference.display_amount == 120 * wa.m2
    assert str(omitted) == "3.57×"
    assert (old / minergie).ratio == pytest.approx(70.676, rel=0.001)
    assert isinstance(omitted.ratio, float)
