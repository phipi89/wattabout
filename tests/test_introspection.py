import inspect

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
    assert next(iter(inspect.signature(wa.building.minergie).parameters)) == "floor_area"
    assert next(iter(inspect.signature(wa.heating.heat_pump).parameters)) == "useful_heat"
