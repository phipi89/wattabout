from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pint import Quantity

from ..context import Context
from ..core import Asset, Impact, LinearEquivalence, Parameter, Source, WattAboutError
from ..units import Q_, ureg
from .common import quantity_prepare

LLM_SOURCE = Source(
    name="Prototype LLM inference profiles",
    citation=(
        "Illustrative inference-energy profiles by token; not measurements of a named model "
        "or provider"
    ),
)
LOCAL_LLM_SOURCE = Source(
    name="Local LLM inference model",
    citation="Calculated from configured device power, token throughput, and local grid intensity",
)


def _cloud_llm_model(default_energy: str):
    def calculate(tokens: Quantity, parameters: Mapping[str, Any], context: Context) -> Impact:
        token_count = tokens.to("token")
        if token_count.magnitude < 0:
            raise WattAboutError("token count must be nonnegative")
        energy_intensity = Q_(parameters.get("energy_per_million_tokens", default_energy)).to(
            "kWh / million_token"
        )
        pue = float(parameters.get("pue", 1.2))
        if pue < 1:
            raise WattAboutError("pue must be at least one")
        cache_read_ratio = float(parameters.get("cache_read_ratio", 0.0))
        cache_read_energy_factor = float(parameters.get("cache_read_energy_factor", 0.1))
        if not 0 <= cache_read_ratio <= 1:
            raise WattAboutError("cache_read_ratio must be between zero and one")
        if not 0 <= cache_read_energy_factor <= 1:
            raise WattAboutError("cache_read_energy_factor must be between zero and one")
        grid_intensity = Q_(
            parameters.get("grid_intensity", context.data_center_grid_intensity)
        ).to("kg_co2e / kWh")
        energy_multiplier = 1 - cache_read_ratio * (1 - cache_read_energy_factor)
        effective_tokens = token_count * energy_multiplier
        electricity = (effective_tokens * energy_intensity * pue).to("kWh")
        climate = (electricity * grid_intensity).to("kg_co2e")
        return Impact(
            values={"climate": climate},
            source=LLM_SOURCE,
            geography=context.region,
            reference_year=context.year,
            boundary="operational_inference",
            dataset=context.dataset,
            assumptions=(
                "Input and output tokens use one blended prototype intensity",
                f"Cache-read ratio: {cache_read_ratio:.0%}",
                f"Cached-token energy factor: {cache_read_energy_factor:.0%}",
                f"Effective uncached-equivalent tokens: {effective_tokens:~}",
                f"Compute energy intensity: {energy_intensity:~}",
                f"Data-center PUE: {pue:g}",
                f"Data-center grid intensity: {grid_intensity:~}",
                "Excludes model training, hardware manufacture, networking, and end-user device",
            ),
        )

    return calculate


def _local_llm_impact(tokens: Quantity, parameters: Mapping[str, Any], context: Context) -> Impact:
    token_count = tokens.to("token")
    if token_count.magnitude < 0:
        raise WattAboutError("token count must be nonnegative")
    device_power = Q_(parameters.get("device_power", "250 W")).to("kW")
    throughput = Q_(parameters.get("throughput", "30 token / second")).to("token / second")
    if device_power.magnitude < 0 or throughput.magnitude <= 0:
        raise WattAboutError("device_power must be nonnegative and throughput positive")
    runtime = (token_count / throughput).to("hour")
    electricity = (device_power * runtime).to("kWh")
    climate = (electricity * context.grid_intensity).to("kg_co2e")
    return Impact(
        values={"climate": climate},
        source=LOCAL_LLM_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="operational_inference",
        dataset=context.dataset,
        assumptions=(
            f"Average device power: {device_power:~}",
            f"Generation throughput: {throughput:~}",
            f"Runtime: {runtime:~}",
            *context.electricity_assumptions,
            "Excludes model training and hardware manufacture",
        ),
    )


def _cloud_parameters(default_energy: str) -> tuple[Parameter, ...]:
    return (
        Parameter(
            "energy_per_million_tokens",
            "prototype compute energy per million blended tokens",
            default_energy,
        ),
        Parameter("pue", "data-center power usage effectiveness", 1.2),
        Parameter(
            "cache_read_ratio",
            "cached input tokens as a fraction of all supplied tokens",
            0.0,
        ),
        Parameter(
            "cache_read_energy_factor",
            "cached-token energy relative to an uncached token",
            0.1,
        ),
        Parameter(
            "grid_intensity",
            "data-center electricity carbon intensity",
            "context.data_center_grid_intensity",
        ),
    )


frontier_llm = Asset(
    id="ai.frontier_llm",
    name="frontier-scale LLM inference",
    default_input_unit=ureg.token,
    default_comparison_unit=ureg.token,
    prepare=quantity_prepare("token"),
    impact_model=_cloud_llm_model("1.5 kWh / million_token"),
    equivalence=LinearEquivalence(),
    amount_name="tokens",
    description=(
        "Illustrative inference profile for a state-of-the-art frontier capability class; "
        "not a DeepSeek or provider measurement."
    ),
    parameters=_cloud_parameters("1.5 kWh / million_token"),
    examples=("wa.ai.frontier_llm(10_000 * wa.token)",),
)

efficient_llm = Asset(
    id="ai.efficient_llm",
    name="efficient small LLM inference",
    default_input_unit=ureg.token,
    default_comparison_unit=ureg.token,
    prepare=quantity_prepare("token"),
    impact_model=_cloud_llm_model("0.25 kWh / million_token"),
    equivalence=LinearEquivalence(),
    amount_name="tokens",
    description=(
        "Illustrative hosted inference profile for a smaller high-throughput model class."
    ),
    parameters=_cloud_parameters("0.25 kWh / million_token"),
    examples=("wa.ai.efficient_llm(10_000 * wa.token)",),
)

local_llm = Asset(
    id="ai.local_llm",
    name="local LLM inference",
    default_input_unit=ureg.token,
    default_comparison_unit=ureg.token,
    prepare=quantity_prepare("token"),
    impact_model=_local_llm_impact,
    equivalence=LinearEquivalence(),
    amount_name="tokens",
    description="Local inference calculated from device power and measured token throughput.",
    parameters=(
        Parameter("device_power", "average device power during generation", "250 W"),
        Parameter("throughput", "generated token throughput", "30 token / second"),
    ),
    examples=(
        "wa.ai.local_llm(10_000 * wa.token, device_power=wa.Q_('180 W'), throughput=wa.Q_('45 token / second'))",
    ),
)

ASSETS = (frontier_llm, efficient_llm, local_llm)
