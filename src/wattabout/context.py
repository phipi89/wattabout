from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace

from pint import Quantity

from .units import Q_


@dataclass(frozen=True, slots=True)
class Context:
    region: str = "CH"
    year: int = 2025
    dataset: str = "wattabout-prototype-ch-2025.1"
    default_metric: str = "climate"
    grid_intensity: Quantity = field(default_factory=lambda: Q_(0.085, "kg_co2e / kWh"))
    heating_oil_intensity: Quantity = field(default_factory=lambda: Q_(0.267, "kg_co2e / kWh"))
    natural_gas_intensity: Quantity = field(default_factory=lambda: Q_(0.202, "kg_co2e / kWh"))
    kettle_efficiency: float = 0.85
    water_inlet_temperature: Quantity = field(default_factory=lambda: Q_(15, "degC"))

    def with_overrides(self, **changes: object) -> Context:
        return replace(self, **changes)


_active_context: ContextVar[Context | None] = ContextVar("wattabout_context", default=None)
_default_context = Context()


def get_context() -> Context:
    return _active_context.get() or _default_context


@contextmanager
def context(base: Context | None = None, **overrides: object) -> Iterator[Context]:
    selected = base or get_context()
    selected = selected.with_overrides(**overrides)
    token = _active_context.set(selected)
    try:
        yield selected
    finally:
        _active_context.reset(token)
