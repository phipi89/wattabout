import pytest

import wattabout as wa


def test_frontier_llm_uses_token_energy_pue_and_data_center_grid() -> None:
    context = wa.Context(data_center_grid_intensity=0.4 * wa.kg_co2e / wa.kWh)

    impact = wa.ai.frontier_llm(1 * wa.million_token).impact(context)["climate"]

    assert impact.to("kg_co2e").magnitude == pytest.approx(1.5 * 1.2 * 0.4)


def test_efficient_profile_uses_lower_prototype_intensity() -> None:
    tokens = 1 * wa.million_token

    comparison = wa.ai.frontier_llm(tokens) / wa.ai.efficient_llm(tokens)

    assert comparison.ratio == pytest.approx(6)


def test_cloud_grid_can_be_overridden_per_activity() -> None:
    impact = wa.ai.frontier_llm(
        1 * wa.million_token,
        grid_intensity=0.1 * wa.kg_co2e / wa.kWh,
        pue=1,
    ).impact()["climate"]

    assert impact.to("kg_co2e").magnitude == pytest.approx(0.15)


def test_local_llm_uses_device_power_throughput_and_local_grid() -> None:
    context = wa.Context(grid_intensity=0.1 * wa.kg_co2e / wa.kWh)
    impact = wa.ai.local_llm(
        1 * wa.million_token,
        device_power=wa.Q_("180 W"),
        throughput=wa.Q_("50 token / second"),
    ).impact(context)["climate"]

    expected_kwh = 0.18 * (1_000_000 / 50 / 3600)
    assert impact.to("kg_co2e").magnitude == pytest.approx(expected_kwh * 0.1)


def test_llm_profiles_are_explicitly_inference_only() -> None:
    explanation = wa.ai.frontier_llm(10_000 * wa.token).equivalent_to(wa.ai.local_llm).explain()

    assert "Excludes model training" in explanation
    assert "not measurements of a named model" in explanation


def test_llm_assets_are_discoverable() -> None:
    assert wa.ai.list_assets() == ("efficient_llm", "frontier_llm", "local_llm")
    assert "not a DeepSeek" in wa.ai.frontier_llm.describe()


def test_cache_reads_reduce_hosted_inference_energy() -> None:
    tokens = 1 * wa.million_token
    uncached = wa.ai.frontier_llm(tokens)
    cached = wa.ai.frontier_llm(tokens, cache_read_ratio=0.95)

    comparison = uncached / cached

    assert comparison.ratio == pytest.approx(1 / 0.145)
    assert (cached.impact()["climate"] / uncached.impact()["climate"]).magnitude == pytest.approx(
        0.145
    )


def test_cache_energy_factor_is_configurable() -> None:
    impact = wa.ai.efficient_llm(
        1 * wa.million_token,
        cache_read_ratio=0.8,
        cache_read_energy_factor=0.25,
    ).impact()["climate"]
    uncached = wa.ai.efficient_llm(1 * wa.million_token).impact()["climate"]

    assert (impact / uncached).magnitude == pytest.approx(0.4)


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        ("cache_read_ratio", -0.1),
        ("cache_read_ratio", 1.1),
        ("cache_read_energy_factor", -0.1),
        ("cache_read_energy_factor", 1.1),
    ],
)
def test_invalid_cache_parameters_are_rejected(parameter: str, value: float) -> None:
    with pytest.raises(wa.WattAboutError, match="between zero and one"):
        wa.ai.frontier_llm(1_000, **{parameter: value}).impact()


def test_cache_assumptions_are_explained() -> None:
    explanation = (
        wa.ai.frontier_llm(
            1 * wa.million_token,
            cache_read_ratio=0.95,
        )
        .equivalent_to(wa.ai.efficient_llm)
        .explain()
    )

    assert "Cache-read ratio: 95%" in explanation
    assert "Cached-token energy factor: 10%" in explanation
    assert "Effective uncached-equivalent tokens: 145000" in explanation


def test_local_llm_rejects_cloud_cache_parameters() -> None:
    with pytest.raises(wa.WattAboutError, match="Unknown parameter"):
        wa.ai.local_llm(1_000, cache_read_ratio=0.95)
