import inspect
from dataclasses import FrozenInstanceError

import pytest

import wattabout as wa


def test_asset_signature_exposes_required_and_optional_parameters() -> None:
    signature = inspect.signature(wa.household.oven)

    assert tuple(signature.parameters) == (
        "cooking_time",
        "temperature",
        "ambient_temperature",
        "include_preheating",
        "preheat_energy_at_200c",
        "holding_power_at_200c",
    )
    assert signature.parameters["cooking_time"].default is None
    assert signature.parameters["temperature"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["temperature"].default is inspect.Parameter.empty
    assert signature.parameters["include_preheating"].default is True


def test_asset_documentation_is_available_to_inspection_tools() -> None:
    documentation = inspect.getdoc(wa.household.oven)

    assert documentation is not None
    assert "temperature: oven target temperature (required)" in documentation
    assert "Equivalence: analytic" in documentation
    assert "wa.household.oven(20 * wa.minute" in documentation


def test_configured_asset_signature_only_requires_amount() -> None:
    configured = wa.household.oven.configure(temperature=200 * wa.degC)

    assert tuple(inspect.signature(configured).parameters) == ("cooking_time",)
    assert "Configured parameters:" in inspect.getdoc(configured)


def test_catalog_uses_meaningful_primary_argument_names() -> None:
    assert tuple(inspect.signature(wa.transport.train).parameters) == ("distance",)
    assert next(iter(inspect.signature(wa.buildings.minergie).parameters)) == "floor_area"
    assert next(iter(inspect.signature(wa.heating.heat_pump).parameters)) == "useful_heat"
    assert "duration" in inspect.signature(wa.buildings.minergie).parameters


def test_assets_expose_accepted_input_dimensions() -> None:
    assert wa.transport.train.accepted_input_units == (wa.km,)
    assert wa.food.cervelat.accepted_input_units == (wa.gram, wa.m)
    assert {unit.dimensionality for unit in wa.food.cervelat.accepted_input_units} == {
        wa.gram.dimensionality,
        wa.m.dimensionality,
    }


def test_parameter_positional_declarations_remain_compatible() -> None:
    parameter = wa.Parameter("name", "description", "default", True)

    assert parameter.default == "default"
    assert parameter.required is True
    assert parameter.schema is None


def test_oven_temperature_exposes_quantity_schema() -> None:
    parameter = next(item for item in wa.household.oven.parameters if item.name == "temperature")

    assert isinstance(parameter.schema, wa.ParameterSchema)
    assert parameter.schema.kind == "quantity"
    assert parameter.schema.default_unit == wa.degC
    assert parameter.schema.accepted_units == (wa.ureg.degC, wa.ureg.degF, wa.ureg.kelvin)
    assert parameter.schema.choices == ()
    assert parameter.schema.asset_category is None
    assert parameter.schema.nullable is False


def test_custom_building_required_parameters_expose_typed_schemas() -> None:
    parameters = {parameter.name: parameter for parameter in wa.buildings.custom.parameters}
    demand = parameters["specific_heat_demand"].schema
    heating = parameters["heating"].schema

    assert demand is not None
    assert demand.kind == "quantity"
    assert demand.default_unit == wa.ureg.kWh_th / wa.m2 / wa.year
    assert demand.accepted_units == (
        wa.ureg.kWh_th / wa.m2 / wa.year,
        wa.ureg.MWh_th / wa.m2 / wa.year,
        wa.ureg.kWh_th / wa.ureg.foot**2 / wa.year,
    )
    assert demand.nullable is False
    assert heating == wa.ParameterSchema(kind="asset", asset_category="heating")


def test_parameter_schema_is_immutable() -> None:
    schema = wa.ParameterSchema(kind="quantity", default_unit=wa.degC)

    with pytest.raises(FrozenInstanceError):
        schema.nullable = True  # type: ignore[misc]
