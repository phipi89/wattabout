from __future__ import annotations

from collections.abc import Sequence

from pint import DimensionalityError, Quantity, Unit

from .units import ureg

_PREFERRED_UNITS: tuple[tuple[Unit, ...], ...] = (
    (
        ureg.nanosecond,
        ureg.microsecond,
        ureg.millisecond,
        ureg.second,
        ureg.minute,
        ureg.hour,
        ureg.day,
        ureg.week,
        ureg.year,
    ),
    (ureg.millimeter, ureg.centimeter, ureg.meter, ureg.kilometer),
    (ureg.meter**2, ureg.hectare, ureg.kilometer**2),
    (ureg.milligram, ureg.gram, ureg.kilogram, ureg.tonne),
    (ureg.milliliter, ureg.liter, ureg.meter**3),
    (ureg.watt_hour, ureg.kilowatt_hour, ureg.megawatt_hour),
    (ureg.kWh_th, ureg.MWh_th),
    (ureg.g_co2e, ureg.kg_co2e, ureg.tonne_co2e),
    (ureg.token, ureg.million_token),
)


def _converted_candidates(quantity: Quantity, units: Sequence[Unit]) -> list[Quantity] | None:
    try:
        return [quantity.to(unit) for unit in units]
    except DimensionalityError:
        return None


def to_preferred_unit(quantity: Quantity) -> Quantity:
    """Return a human-scale unit for supported scalar quantity dimensions."""
    if quantity.magnitude == 0:
        return quantity
    for units in _PREFERRED_UNITS:
        candidates = _converted_candidates(quantity, units)
        if candidates is None:
            continue
        suitable = [candidate for candidate in candidates if abs(candidate.magnitude) >= 1]
        return suitable[-1] if suitable else candidates[0]
    return quantity


def format_quantity(quantity: Quantity, precision: str = ".3g", *, auto_scale: bool = True) -> str:
    """Format a quantity with preferred units while preserving compound bases."""
    if auto_scale:
        quantity = to_preferred_unit(quantity)
    formatted = f"{quantity:{precision}~P}"
    return (
        formatted.replace(" / a", " / year")
        .replace("/a", " / year")
        .replace(" a", " year")
        .replace(" week", " wk")
        .replace("/week", "/wk")
        .replace(" l", " L")
    )
