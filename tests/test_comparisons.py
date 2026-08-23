import pytest

import wattabout as wa


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


def test_asset_target_cannot_be_converted_to_float() -> None:
    comparison = wa.food.cervelat(2.5 * wa.mm) / wa.transport.train

    with pytest.raises(TypeError, match="concrete activities"):
        float(comparison)


def test_unknown_metric_has_clear_error() -> None:
    with pytest.raises(wa.MissingMetricError, match="water"):
        wa.transport.train(1 * wa.km).equivalent_to(wa.food.cervelat, metric="water")
