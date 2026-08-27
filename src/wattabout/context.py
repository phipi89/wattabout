from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace

from pint import Quantity

from .units import Q_


@dataclass(frozen=True, slots=True)
class ElectricitySupply:
    name: str
    intensity: Quantity
    assumptions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Context:
    region: str = "CH"
    year: int = 2025
    dataset: str = "wattabout-prototype-ch-2025.1"
    default_metric: str = "climate"
    grid_intensity: Quantity = field(default_factory=lambda: Q_(0.085, "kg_co2e / kWh"))
    data_center_grid_intensity: Quantity = field(default_factory=lambda: Q_(0.4, "kg_co2e / kWh"))
    heating_oil_intensity: Quantity = field(default_factory=lambda: Q_(0.267, "kg_co2e / kWh"))
    natural_gas_intensity: Quantity = field(default_factory=lambda: Q_(0.202, "kg_co2e / kWh"))
    kettle_efficiency: float = 0.85
    water_inlet_temperature: Quantity = field(default_factory=lambda: Q_(15, "degC"))
    water_services_intensity: Quantity = field(
        default_factory=lambda: Q_(0.0005, "kg_co2e / liter")
    )
    electricity_source_name: str = "regional grid"
    electricity_source_assumptions: tuple[str, ...] = ()

    def with_overrides(self, **changes: object) -> Context:
        return replace(self, **changes)

    @property
    def electricity_assumptions(self) -> tuple[str, ...]:
        return (
            f"Electricity source: {self.electricity_source_name}",
            f"Electricity intensity: {self.grid_intensity:~}",
            *self.electricity_source_assumptions,
        )


_active_context: ContextVar[Context | None] = ContextVar("wattabout_context", default=None)
_default_context = Context()


def get_context() -> Context:
    return _active_context.get() or _default_context


@contextmanager
def context(
    base: Context | object | None = None,
    *,
    electricity: object | None = None,
    **overrides: object,
) -> Iterator[Context]:
    source = electricity
    if base is not None and not isinstance(base, Context):
        if source is not None:
            raise ValueError("Electricity source was supplied both positionally and by keyword")
        source = base
        base = None
    if source is not None and "grid_intensity" in overrides:
        raise ValueError("Cannot supply both an electricity source and grid_intensity")
    if source is None and "grid_intensity" in overrides:
        overrides.setdefault("electricity_source_name", "custom grid intensity")
        overrides.setdefault("electricity_source_assumptions", ())

    selected = base or get_context()
    selected = selected.with_overrides(**overrides)
    if source is not None:
        supply_method = getattr(source, "electricity_supply", None)
        if supply_method is None:
            raise TypeError(f"{type(source).__name__} is not an electricity source")
        supply = supply_method(selected)
        if not isinstance(supply, ElectricitySupply):
            raise TypeError("electricity_supply() must return ElectricitySupply")
        intensity = supply.intensity.to("kg_co2e / kWh")
        if intensity.magnitude < 0:
            raise ValueError("Electricity intensity must be nonnegative")
        selected = selected.with_overrides(
            grid_intensity=intensity,
            electricity_source_name=supply.name,
            electricity_source_assumptions=supply.assumptions,
        )
    token = _active_context.set(selected)
    try:
        yield selected
    finally:
        _active_context.reset(token)
