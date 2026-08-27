from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pint import Quantity

from ..context import Context, ElectricitySupply
from ..core import Asset, Impact, LinearEquivalence, Parameter, Source, WattAboutError
from ..units import Q_, ureg
from .common import ENERGY_SOURCE, PHYSICAL_MODEL_SOURCE, linear_factor_model, quantity_prepare

SOLAR_SOURCE = Source(
    name="Rooftop photovoltaic lifecycle scenario",
    citation=(
        "Prototype 40 g CO2e/kWh lifecycle intensity informed by IEA PVPS lifecycle "
        "assessments; actual results depend on module, location, yield, and lifetime"
    ),
    url="https://iea-pvps.org/key-topics/environmental-life-cycle-assessment-of-electricity-from-pv-systems/",
)
FUEL_SOURCE = Source(
    name="Liquid fuel lifecycle factors",
    citation=(
        "Prototype tailpipe and upstream factors informed by UK government greenhouse-gas "
        "conversion factors for company reporting"
    ),
    url="https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting",
)
PELLET_SOURCE = Source(
    name="Wood pellet combustion scenario",
    citation=(
        "Prototype pellet factors with 4.8 kWh/kg lower heating value from UK Forest "
        "Research; gross biogenic stack CO2 is counted by default and no regrowth credit is applied"
    ),
    url="https://www.forestresearch.gov.uk/tools-and-resources/fthr/biomass-energy-resources/reference-biomass/facts-figures/typical-calorific-values-of-fuels/",
)


def _electricity_impact(
    amount: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    climate = (amount.to("kWh") * context.grid_intensity).to("kg_co2e")
    return Impact(
        values={"climate": climate},
        source=PHYSICAL_MODEL_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="operational",
        dataset=context.dataset,
        assumptions=context.electricity_assumptions,
    )


def _solar_intensity(parameters: Mapping[str, Any]) -> Quantity:
    intensity = Q_(parameters.get("lifecycle_intensity", "0.04 kg_co2e / kWh")).to("kg_co2e / kWh")
    if intensity.magnitude < 0:
        raise WattAboutError("lifecycle_intensity must be nonnegative")
    return intensity


def _rooftop_solar_impact(
    amount: Quantity, parameters: Mapping[str, Any], context: Context
) -> Impact:
    electricity = amount.to("kWh")
    if electricity.magnitude < 0:
        raise WattAboutError("solar generation must be nonnegative")
    intensity = _solar_intensity(parameters)
    return Impact(
        values={"climate": (electricity * intensity).to("kg_co2e")},
        source=SOLAR_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="cradle_to_grave_generation",
        dataset=context.dataset,
        assumptions=(
            f"Generated electricity: {electricity:~}",
            f"PV lifecycle intensity: {intensity:~}",
            "Avoided grid emissions, storage, curtailment, and temporal matching excluded",
        ),
    )


def _grid_electricity_supply(parameters: Mapping[str, Any], context: Context) -> ElectricitySupply:
    return ElectricitySupply(
        name="regional grid",
        intensity=context.grid_intensity,
        assumptions=(f"Region: {context.region}",),
    )


def _rooftop_solar_supply(parameters: Mapping[str, Any], context: Context) -> ElectricitySupply:
    intensity = _solar_intensity(parameters)
    return ElectricitySupply(
        name="rooftop solar",
        intensity=intensity,
        assumptions=(
            f"PV lifecycle intensity: {intensity:~}",
            "Assumes full supply without timing, storage, curtailment, or grid backup",
        ),
    )


def _liquid_fuel_factors(
    parameters: Mapping[str, Any], *, tailpipe_default: str, upstream_default: str
) -> tuple[Quantity, Quantity]:
    tailpipe = Q_(parameters.get("tailpipe_factor", tailpipe_default)).to("kg_co2e / liter")
    upstream = Q_(parameters.get("upstream_factor", upstream_default)).to("kg_co2e / liter")
    if tailpipe.magnitude < 0 or upstream.magnitude < 0:
        raise WattAboutError("fuel emission factors must be nonnegative")
    return tailpipe, upstream


def _liquid_fuel_model(*, fuel: str, tailpipe_default: str, upstream_default: str):
    def calculate(volume: Quantity, parameters: Mapping[str, Any], context: Context) -> Impact:
        liters = volume.to("liter")
        if liters.magnitude < 0:
            raise WattAboutError(f"{fuel} volume must be nonnegative")
        tailpipe, upstream = _liquid_fuel_factors(
            parameters,
            tailpipe_default=tailpipe_default,
            upstream_default=upstream_default,
        )
        return Impact(
            values={"climate": (liters * (tailpipe + upstream)).to("kg_co2e")},
            source=FUEL_SOURCE,
            geography=context.region,
            reference_year=context.year,
            boundary="well_to_wheel_fuel",
            dataset=context.dataset,
            assumptions=(
                f"Direct combustion factor: {tailpipe:~}",
                f"Upstream fuel factor: {upstream:~}",
                "Vehicle manufacture and distance traveled excluded",
            ),
        )

    return calculate


def _liquid_fuel_supply(
    *,
    fuel: str,
    tailpipe_default: str,
    upstream_default: str,
    energy_density_default: str,
    efficiency_default: float,
):
    def calculate(parameters: Mapping[str, Any], context: Context) -> ElectricitySupply:
        tailpipe, upstream = _liquid_fuel_factors(
            parameters,
            tailpipe_default=tailpipe_default,
            upstream_default=upstream_default,
        )
        energy_density = Q_(parameters.get("energy_density", energy_density_default)).to(
            "kWh / liter"
        )
        efficiency = float(parameters.get("generator_efficiency", efficiency_default))
        if energy_density.magnitude <= 0:
            raise WattAboutError("energy_density must be positive")
        if not 0 < efficiency <= 1:
            raise WattAboutError("generator_efficiency must be greater than zero and at most one")
        intensity = ((tailpipe + upstream) / (energy_density * efficiency)).to("kg_co2e / kWh")
        return ElectricitySupply(
            name=f"{fuel} generator",
            intensity=intensity,
            assumptions=(
                f"Fuel energy density: {energy_density:~}",
                f"Electrical generator efficiency: {efficiency:.0%}",
                f"Fuel lifecycle factor: {(tailpipe + upstream):~}",
            ),
        )

    return calculate


def _natural_gas_supply(parameters: Mapping[str, Any], context: Context) -> ElectricitySupply:
    fuel_intensity = Q_(0.202, "kg_co2e / kWh")
    efficiency = float(parameters.get("generator_efficiency", 0.5))
    if not 0 < efficiency <= 1:
        raise WattAboutError("generator_efficiency must be greater than zero and at most one")
    return ElectricitySupply(
        name="natural gas generator",
        intensity=(fuel_intensity / efficiency).to("kg_co2e / kWh"),
        assumptions=(
            f"Electrical generator efficiency: {efficiency:.0%}",
            f"Natural gas combustion intensity: {fuel_intensity:~}",
        ),
    )


def _wood_pellet_components(
    mass: Quantity, parameters: Mapping[str, Any]
) -> tuple[Quantity, Quantity, Quantity, Quantity, Quantity, bool]:
    pellets = mass.to("kg")
    if pellets.magnitude < 0:
        raise WattAboutError("wood pellet mass must be nonnegative")
    lower_heating_value = Q_(parameters.get("lower_heating_value", "4.8 kWh / kg")).to("kWh / kg")
    supply_chain_intensity = Q_(parameters.get("supply_chain_intensity", "0.025 kg_co2e / kWh")).to(
        "kg_co2e / kWh"
    )
    non_co2_intensity = Q_(
        parameters.get("non_co2_combustion_intensity", "0.005 kg_co2e / kWh")
    ).to("kg_co2e / kWh")
    biogenic_factor = Q_(parameters.get("biogenic_stack_co2_factor", "1.8 kg_co2e / kg")).to(
        "kg_co2e / kg"
    )
    include_biogenic = bool(parameters.get("include_biogenic_co2", True))
    if any(
        value.magnitude < 0
        for value in (
            lower_heating_value,
            supply_chain_intensity,
            non_co2_intensity,
            biogenic_factor,
        )
    ):
        raise WattAboutError("wood pellet factors must be nonnegative")
    if lower_heating_value.magnitude == 0:
        raise WattAboutError("lower_heating_value must be positive")
    fuel_energy = (pellets * lower_heating_value).to("kWh")
    supply_chain = (fuel_energy * supply_chain_intensity).to("kg_co2e")
    non_co2 = (fuel_energy * non_co2_intensity).to("kg_co2e")
    biogenic = (pellets * biogenic_factor).to("kg_co2e")
    return (
        fuel_energy,
        lower_heating_value,
        supply_chain,
        non_co2,
        biogenic,
        include_biogenic,
    )


def _wood_pellet_impact(mass: Quantity, parameters: Mapping[str, Any], context: Context) -> Impact:
    _fuel_energy, lower_heating_value, supply_chain, non_co2, biogenic, include_biogenic = (
        _wood_pellet_components(mass, parameters)
    )
    climate = supply_chain + non_co2 + (biogenic if include_biogenic else 0)
    return Impact(
        values={"climate": climate.to("kg_co2e")},
        source=PELLET_SOURCE,
        geography=context.region,
        reference_year=context.year,
        boundary="cradle_to_boiler_gate_and_combustion",
        dataset=context.dataset,
        assumptions=(
            f"Pellet lower heating value: {lower_heating_value:~}",
            f"Supply-chain impact: {supply_chain:~}",
            f"Non-CO2 combustion impact: {non_co2:~}",
            f"Gross biogenic stack CO2: {biogenic:~}",
            f"Biogenic stack CO2 included in climate metric: {include_biogenic}",
            "No future forest regrowth credit applied",
        ),
    )


electricity = Asset(
    id="energy.electricity",
    name="grid electricity",
    default_input_unit=ureg.kWh,
    default_comparison_unit=ureg.kWh,
    prepare=quantity_prepare("kWh"),
    impact_model=_electricity_impact,
    equivalence=LinearEquivalence(),
    amount_name="energy",
    description="Electricity using the active context's grid carbon intensity.",
    examples=("wa.energy.electricity(5 * wa.kWh)",),
    electricity_supply_model=_grid_electricity_supply,
)

natural_gas = Asset(
    id="energy.natural_gas",
    name="natural gas energy",
    default_input_unit=ureg.kWh,
    default_comparison_unit=ureg.kWh,
    prepare=quantity_prepare("kWh"),
    impact_model=linear_factor_model(
        factor=Q_(0.202, "kg_co2e / kWh"),
        source=ENERGY_SOURCE,
        boundary="operational",
        reference_unit="kWh",
        assumptions=("Direct combustion estimate",),
    ),
    equivalence=LinearEquivalence(),
    amount_name="energy",
    description="Useful energy from direct natural-gas combustion.",
    parameters=(
        Parameter(
            "generator_efficiency",
            "electrical efficiency when used as a context electricity source",
            0.5,
        ),
    ),
    examples=("wa.energy.natural_gas(10 * wa.kWh)",),
    electricity_supply_model=_natural_gas_supply,
)

rooftop_solar = Asset(
    id="energy.rooftop_solar",
    name="rooftop solar electricity generation",
    default_input_unit=ureg.kWh,
    default_comparison_unit=ureg.kWh,
    prepare=quantity_prepare("kWh"),
    impact_model=_rooftop_solar_impact,
    equivalence=LinearEquivalence(),
    amount_name="electricity",
    description="Generated rooftop-PV electricity including an allocated lifecycle footprint.",
    parameters=(
        Parameter(
            "lifecycle_intensity",
            "PV lifecycle impact per generated electricity",
            "40 g CO2e / kWh",
        ),
    ),
    examples=("wa.energy.rooftop_solar(5000 * wa.kWh)",),
    electricity_supply_model=_rooftop_solar_supply,
)

petrol = Asset(
    id="energy.petrol",
    name="petrol fuel",
    default_input_unit=ureg.liter,
    default_comparison_unit=ureg.liter,
    prepare=quantity_prepare("liter"),
    impact_model=_liquid_fuel_model(
        fuel="petrol",
        tailpipe_default="2.31 kg_co2e / liter",
        upstream_default="0.54 kg_co2e / liter",
    ),
    equivalence=LinearEquivalence(),
    amount_name="volume",
    description="Petrol by volume with separate direct-combustion and upstream factors.",
    parameters=(
        Parameter("tailpipe_factor", "direct combustion impact per liter", "2.31 kg_co2e / liter"),
        Parameter("upstream_factor", "fuel supply impact per liter", "0.54 kg_co2e / liter"),
        Parameter(
            "energy_density",
            "fuel lower heating value when used for electricity generation",
            "8.9 kWh / liter",
        ),
        Parameter(
            "generator_efficiency",
            "electrical efficiency when used as a context electricity source",
            0.3,
        ),
    ),
    examples=("wa.energy.petrol(40 * wa.liter)",),
    electricity_supply_model=_liquid_fuel_supply(
        fuel="petrol",
        tailpipe_default="2.31 kg_co2e / liter",
        upstream_default="0.54 kg_co2e / liter",
        energy_density_default="8.9 kWh / liter",
        efficiency_default=0.3,
    ),
)

diesel = Asset(
    id="energy.diesel",
    name="diesel fuel",
    default_input_unit=ureg.liter,
    default_comparison_unit=ureg.liter,
    prepare=quantity_prepare("liter"),
    impact_model=_liquid_fuel_model(
        fuel="diesel",
        tailpipe_default="2.68 kg_co2e / liter",
        upstream_default="0.62 kg_co2e / liter",
    ),
    equivalence=LinearEquivalence(),
    amount_name="volume",
    description="Diesel by volume with separate direct-combustion and upstream factors.",
    parameters=(
        Parameter("tailpipe_factor", "direct combustion impact per liter", "2.68 kg_co2e / liter"),
        Parameter("upstream_factor", "fuel supply impact per liter", "0.62 kg_co2e / liter"),
        Parameter(
            "energy_density",
            "fuel lower heating value when used for electricity generation",
            "9.8 kWh / liter",
        ),
        Parameter(
            "generator_efficiency",
            "electrical efficiency when used as a context electricity source",
            0.4,
        ),
    ),
    examples=("wa.energy.diesel(40 * wa.liter)",),
    electricity_supply_model=_liquid_fuel_supply(
        fuel="diesel",
        tailpipe_default="2.68 kg_co2e / liter",
        upstream_default="0.62 kg_co2e / liter",
        energy_density_default="9.8 kWh / liter",
        efficiency_default=0.4,
    ),
)

wood_pellets = Asset(
    id="energy.wood_pellets",
    name="wood pellet fuel",
    default_input_unit=ureg.kg,
    default_comparison_unit=ureg.kg,
    prepare=quantity_prepare("kg"),
    impact_model=_wood_pellet_impact,
    equivalence=LinearEquivalence(),
    amount_name="mass",
    description="Wood pellets with gross biogenic stack CO2 counted by default.",
    parameters=(
        Parameter("lower_heating_value", "pellet net calorific value", "4.8 kWh / kg"),
        Parameter(
            "supply_chain_intensity",
            "forestry, processing, and transport impact per fuel energy",
            "0.025 kg_co2e / kWh",
        ),
        Parameter(
            "non_co2_combustion_intensity",
            "methane and nitrous oxide impact per fuel energy",
            "0.005 kg_co2e / kWh",
        ),
        Parameter(
            "biogenic_stack_co2_factor",
            "gross biogenic stack CO2 per pellet mass",
            "1.8 kg_co2e / kg",
        ),
        Parameter(
            "include_biogenic_co2",
            "include gross biogenic stack CO2 in the climate metric",
            True,
        ),
    ),
    examples=(
        "wa.energy.wood_pellets(1000 * wa.kg)",
        "wa.energy.wood_pellets(1000 * wa.kg, include_biogenic_co2=False)",
    ),
)

ASSETS = (electricity, natural_gas, rooftop_solar, petrol, diesel, wood_pellets)
