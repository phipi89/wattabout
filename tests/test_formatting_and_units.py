import pytest

import wattabout as wa


@pytest.mark.parametrize(
    ("quantity", "expected"),
    [
        (400 * wa.microsecond, "400 µs"),
        (999 * wa.millisecond, "999 ms"),
        (1_000 * wa.millisecond, "1 s"),
        (52.5 * wa.second, "52.5 s"),
        (3_153 * wa.second, "52.5 min"),
        (7_200 * wa.second, "2 h"),
        (72 * wa.hour, "3 d"),
        (21 * wa.day, "3 wk"),
        (730.5 * wa.day, "2 year"),
    ],
)
def test_time_quantities_use_readable_units(quantity, expected: str) -> None:
    assert wa.format_quantity(quantity) == expected


@pytest.mark.parametrize(
    ("quantity", "expected"),
    [
        (2_500 * wa.m, "2.5 km"),
        (0.25 * wa.m, "25 cm"),
        (0.004 * wa.m, "4 mm"),
        (2_500 * wa.gram, "2.5 kg"),
        (0.2 * wa.gram, "200 mg"),
        (1_500 * wa.Wh, "1.5 kWh"),
        (2_000 * wa.kg_co2e, "2 t_CO2e"),
        (2 * wa.MWh_th, "2 MWh_th"),
        (1 * wa.million_token, "1 million_token"),
        (10_000 * wa.m2, "1 ha"),
        (1_000_000 * wa.m2, "1 km²"),
    ],
)
def test_other_scalar_dimensions_use_readable_units(quantity, expected: str) -> None:
    assert wa.format_quantity(quantity) == expected


def test_zero_and_negative_quantities_are_stable() -> None:
    assert wa.format_quantity(0 * wa.second) == "0 s"
    assert wa.format_quantity(-3_153 * wa.second) == "-52.5 min"


def test_compound_reporting_basis_is_preserved() -> None:
    quantity = 42.3 * wa.phone_device / wa.year

    assert wa.format_quantity(quantity) == "42.3 phone_device / year"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.591123123, "0.591"),
        (59.1123123, "59.1"),
        (12_345_353, "12345353"),
        (12_345_353.72, "12345354"),
        (-12_345_353.72, "-12345354"),
        (0, "0"),
    ],
)
def test_plain_numbers_expand_without_scientific_notation(value: float, expected: str) -> None:
    assert wa.format_number(value, scientific=False) == expected


def test_plain_quantity_keeps_its_current_unit() -> None:
    quantity = 0.591123123 * wa.m

    assert wa.format_quantity(quantity, auto_scale=False, scientific=False) == "0.591 m"
    assert wa.format_quantity(quantity.to(wa.cm), auto_scale=False, scientific=False) == "59.1 cm"
    assert wa.format_quantity(12_345_353 * wa.m, auto_scale=False, scientific=False) == "12345353 m"


def test_llm_to_annual_building_rate_uses_minutes() -> None:
    comparison = wa.ai.frontier_llm(1e6) / wa.buildings.house_1960s(120 * wa.m2)

    assert comparison.amount is not None
    assert comparison.amount.to("minute").magnitude == pytest.approx(52.53, rel=0.001)
    assert str(comparison) == "52.5 min"


def test_common_units_are_exported() -> None:
    assert wa.second == wa.ureg.second
    assert wa.hour == wa.ureg.hour
    assert wa.day == wa.ureg.day
    assert wa.week == wa.ureg.week
    assert wa.W == wa.ureg.watt
    assert wa.kW == wa.ureg.kilowatt
    assert wa.MWh == wa.ureg.megawatt_hour
    assert wa.tonne == wa.ureg.tonne
    assert wa.CHF == wa.ureg.CHF
    assert wa.ha == wa.ureg.hectare
    assert wa.hectare == wa.ureg.hectare
    assert wa.km2 == wa.ureg.kilometer**2
    assert wa.eruption_event == wa.ureg.eruption_event
