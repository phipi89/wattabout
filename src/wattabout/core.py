from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from pint import Quantity, Unit

from .context import Context, get_context
from .units import ureg


class WattAboutError(Exception):
    """Base exception for wattabout errors."""


class MissingMetricError(WattAboutError):
    """Raised when an activity has no value for a requested metric."""


class MissingParameterError(WattAboutError):
    """Raised when an asset is missing a required parameter."""


class NoEquivalentAmountError(WattAboutError):
    """Raised when no target amount can match a source impact."""


@dataclass(frozen=True, slots=True)
class Source:
    name: str
    citation: str
    url: str | None = None
    components: tuple[Source, ...] = ()

    def citations(self) -> Iterator[str]:
        yield self.citation
        for component in self.components:
            yield from component.citations()


@dataclass(frozen=True, slots=True)
class Impact:
    values: Mapping[str, Quantity]
    source: Source
    geography: str
    reference_year: int
    boundary: str
    dataset: str
    method: str = "IPCC 2021 GWP100"
    assumptions: tuple[str, ...] = ()

    def __getitem__(self, metric: str) -> Quantity:
        try:
            return self.values[metric]
        except KeyError as error:
            raise MissingMetricError(f"Impact has no {metric!r} metric") from error


PrepareActivity = Callable[[Any, Mapping[str, Any]], tuple[Quantity, Quantity, Mapping[str, Any]]]
ImpactModel = Callable[[Quantity, Mapping[str, Any], Context], Impact]
InverseModel = Callable[[Quantity, str, Unit, Mapping[str, Any], Context], Quantity]


@dataclass(frozen=True, slots=True)
class Parameter:
    name: str
    description: str
    default: Any = None
    required: bool = False


class Equivalence(Protocol):
    name: str

    def solve(
        self,
        asset: Asset,
        target_impact: Quantity,
        metric: str,
        unit: Unit,
        parameters: Mapping[str, Any],
        context: Context,
    ) -> Quantity: ...


@dataclass(frozen=True, slots=True)
class LinearEquivalence:
    name: str = "linear"

    def solve(
        self,
        asset: Asset,
        target_impact: Quantity,
        metric: str,
        unit: Unit,
        parameters: Mapping[str, Any],
        context: Context,
    ) -> Quantity:
        unit_impact = asset(1 * unit, **parameters).impact(context)[metric]
        if unit_impact.magnitude == 0:
            raise NoEquivalentAmountError(
                f"Cannot solve an equivalent amount for zero-impact asset {asset.name}"
            )
        ratio = (target_impact / unit_impact).to_base_units().magnitude
        return ratio * unit


@dataclass(frozen=True, slots=True)
class AnalyticEquivalence:
    inverse: InverseModel
    name: str = "analytic"

    def solve(
        self,
        asset: Asset,
        target_impact: Quantity,
        metric: str,
        unit: Unit,
        parameters: Mapping[str, Any],
        context: Context,
    ) -> Quantity:
        amount = self.inverse(target_impact, metric, unit, parameters, context).to(unit)
        if amount.magnitude < 0:
            raise NoEquivalentAmountError(f"Equivalent amount for {asset.name} would be negative")
        return amount


@dataclass(frozen=True, slots=True)
class Asset:
    id: str
    name: str
    default_input_unit: Unit
    default_comparison_unit: Unit
    prepare: PrepareActivity
    impact_model: ImpactModel
    equivalence: Equivalence
    amount_name: str = "amount"
    description: str = ""
    parameters: tuple[Parameter, ...] = ()
    examples: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.amount_name.isidentifier():
            raise WattAboutError(f"Invalid amount parameter name {self.amount_name!r}")
        parameter_names = [parameter.name for parameter in self.parameters]
        if len(parameter_names) != len(set(parameter_names)):
            raise WattAboutError(f"Asset {self.id} has duplicate parameter metadata")
        if self.amount_name in parameter_names:
            raise WattAboutError(
                f"Asset {self.id} uses {self.amount_name!r} for both amount and a parameter"
            )

    def __call__(self, amount: Any = None, **parameters: Any) -> Activity:
        self._validate_parameters(parameters, require_all=True)
        if amount is None:
            amount = 1 * self.default_input_unit
        elif not isinstance(amount, Quantity):
            amount = amount * self.default_input_unit
        reference_amount, display_amount, normalized = self.prepare(amount, parameters)
        return Activity(self, reference_amount, display_amount, normalized)

    def configure(self, **parameters: Any) -> ConfiguredAsset:
        self._validate_parameters(parameters, require_all=True)
        return ConfiguredAsset(self, dict(parameters))

    def _validate_parameters(self, parameters: Mapping[str, Any], *, require_all: bool) -> None:
        known = {parameter.name for parameter in self.parameters}
        unknown = set(parameters) - known
        if unknown:
            names = ", ".join(sorted(unknown))
            raise WattAboutError(f"Unknown parameter(s) for {self.id}: {names}")
        if require_all:
            missing = {
                parameter.name
                for parameter in self.parameters
                if parameter.required and parameter.name not in parameters
            }
            if missing:
                names = ", ".join(sorted(missing))
                raise MissingParameterError(f"Asset {self.id} requires parameter(s): {names}")

    def __repr__(self) -> str:
        return f"<Asset {self.id}>"

    @property
    def __signature__(self) -> inspect.Signature:
        parameters = [
            inspect.Parameter(
                self.amount_name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=None,
            )
        ]
        parameters.extend(
            inspect.Parameter(
                parameter.name,
                inspect.Parameter.KEYWORD_ONLY,
                default=(inspect.Parameter.empty if parameter.required else parameter.default),
            )
            for parameter in self.parameters
        )
        return inspect.Signature(parameters, return_annotation=Activity)

    @property
    def __doc__(self) -> str:
        return self.describe()

    @property
    def category(self) -> str:
        return self.id.partition(".")[0]

    def describe(self) -> str:
        lines = [self.name, "", self.description]
        if self.parameters:
            lines.extend(["", "Parameters:"])
            lines.extend(
                (
                    f"  {parameter.name}: {parameter.description} "
                    + ("(required)" if parameter.required else f"(default: {parameter.default})")
                )
                for parameter in self.parameters
            )
        lines.extend(["", f"Equivalence: {self.equivalence.name}"])
        if self.examples:
            lines.extend(["", "Examples:", *(f"  {example}" for example in self.examples)])
        return "\n".join(lines).rstrip()


@dataclass(frozen=True, slots=True)
class ConfiguredAsset:
    asset: Asset
    parameters: Mapping[str, Any]

    def __call__(self, amount: Any = None) -> Activity:
        return self.asset(amount, **self.parameters)

    def describe(self) -> str:
        return self.asset.describe()

    @property
    def __signature__(self) -> inspect.Signature:
        return inspect.Signature(
            [
                inspect.Parameter(
                    self.asset.amount_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=None,
                )
            ],
            return_annotation=Activity,
        )

    @property
    def __doc__(self) -> str:
        configured = ", ".join(f"{name}={value!r}" for name, value in self.parameters.items())
        return f"{self.asset.describe()}\n\nConfigured parameters:\n  {configured}"

    def __repr__(self) -> str:
        parameters = ", ".join(f"{name}={value!r}" for name, value in self.parameters.items())
        return f"<ConfiguredAsset {self.asset.id} {parameters}>"


@dataclass(frozen=True, slots=True)
class Activity:
    asset: Asset
    reference_amount: Quantity
    display_amount: Quantity
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def impact(self, context: Context | None = None) -> Impact:
        return self.asset.impact_model(
            self.reference_amount,
            self.parameters,
            context or get_context(),
        )

    def __str__(self) -> str:
        return f"{self.display_amount:~} of {self.asset.name}"

    def __repr__(self) -> str:
        return str(self)

    def equivalent_to(
        self,
        target: Asset | ConfiguredAsset | Activity,
        *,
        metric: str | None = None,
        unit: str | Unit | None = None,
        context: Context | None = None,
        **target_parameters: Any,
    ) -> Comparison:
        selected_context = context or get_context()
        selected_metric = metric or selected_context.default_metric
        if isinstance(target, Activity):
            if target_parameters:
                raise WattAboutError(
                    "Target parameters cannot be supplied with an existing target activity"
                )
            target_asset = target.asset
            target_reference = target
            target_unit = ureg.Unit(unit) if unit is not None else target.display_amount.units
            fixed_parameters = target.parameters
        elif isinstance(target, ConfiguredAsset):
            if target_parameters:
                raise WattAboutError(
                    "Target parameters cannot be supplied with a configured target asset"
                )
            target_asset = target.asset
            target_unit = (
                ureg.Unit(unit) if unit is not None else target_asset.default_comparison_unit
            )
            fixed_parameters = target.parameters
            target_reference = None
        else:
            target_asset = target
            target_unit = ureg.Unit(unit) if unit is not None else target.default_comparison_unit
            fixed_parameters = target_parameters
            target_asset._validate_parameters(fixed_parameters, require_all=True)
            target_reference = None

        source_impact = self.impact(selected_context)
        source_value = source_impact[selected_metric]
        if isinstance(target, Activity):
            target_reference_impact = target_reference.impact(selected_context)
            target_reference_value = target_reference_impact[selected_metric]
            if target_reference_value.magnitude == 0:
                raise WattAboutError(f"Cannot compare against zero impact for {target_asset.name}")
            ratio = (source_value / target_reference_value).to_base_units().magnitude
            try:
                amount = target_asset.equivalence.solve(
                    target_asset,
                    source_value,
                    selected_metric,
                    target_unit,
                    fixed_parameters,
                    selected_context,
                )
            except NoEquivalentAmountError:
                amount = None
        else:
            amount = target_asset.equivalence.solve(
                target_asset,
                source_value,
                selected_metric,
                target_unit,
                fixed_parameters,
                selected_context,
            )
            target_reference = target_asset(amount, **fixed_parameters)
            target_reference_impact = target_reference.impact(selected_context)
            ratio = 1.0

        warnings: list[str] = []
        if source_impact.method != target_reference_impact.method:
            warnings.append("The activities use different impact assessment methods.")
        if source_impact.boundary != target_reference_impact.boundary:
            warnings.append(
                f"Lifecycle boundaries differ: {source_impact.boundary} versus "
                f"{target_reference_impact.boundary}."
            )
        return Comparison(
            source=self,
            target=target_asset,
            target_reference=target_reference,
            target_is_activity=isinstance(target, Activity),
            metric=selected_metric,
            amount=amount,
            ratio=ratio,
            source_impact=source_impact,
            target_reference_impact=target_reference_impact,
            warnings=tuple(warnings),
        )

    def __truediv__(self, target: Asset | ConfiguredAsset | Activity) -> Comparison:
        if not isinstance(target, (Asset, ConfiguredAsset, Activity)):
            return NotImplemented
        return self.equivalent_to(target)


@dataclass(frozen=True, slots=True)
class Comparison:
    source: Activity
    target: Asset
    target_reference: Activity
    target_is_activity: bool
    metric: str
    amount: Quantity | None
    ratio: float
    source_impact: Impact
    target_reference_impact: Impact
    warnings: tuple[str, ...] = ()

    def __str__(self) -> str:
        if self.target_is_activity:
            return f"{self.ratio:.3g}×"
        if self.amount is None:
            raise NoEquivalentAmountError("This comparison has no equivalent target amount")
        return f"{self.amount.magnitude:.3g} {self.amount.units:~}"

    def __repr__(self) -> str:
        return str(self)

    def __float__(self) -> float:
        if not self.target_is_activity:
            raise TypeError(
                "Only comparisons against concrete activities can be converted to float"
            )
        return self.ratio

    def _summary(self) -> str:
        if self.target_is_activity:
            return (
                f"{self.source.display_amount:~} of {self.source.asset.name} ÷ "
                f"{self.target_reference.display_amount:~} of {self.target.name} = "
                f"{self} ({self.metric})"
            )
        return (
            f"{self.source.display_amount:~} of {self.source.asset.name} ≈ "
            f"{self} of {self.target.name} ({self.metric})"
        )

    def explain(self) -> str:
        source_value = self.source_impact[self.metric].to("g_co2e")
        target_value = self.target_reference_impact[self.metric].to("g_co2e")
        lines = [
            self._summary(),
            "",
            f"Source impact: {source_value:.3g~P}",
            (
                f"Target reference impact ({self.target_reference.display_amount:.3g~P}): "
                f"{target_value:.3g~P}"
            ),
            f"Target reference ratio: {self.ratio:.3g}",
        ]
        lines.extend(["", "Sources:"])
        lines.extend(f"- {citation}" for citation in self.source_impact.source.citations())
        lines.extend(
            f"- {citation}" for citation in self.target_reference_impact.source.citations()
        )
        assumptions = self.source_impact.assumptions + self.target_reference_impact.assumptions
        if assumptions:
            lines.extend(["", "Assumptions:", *(f"- {item}" for item in assumptions)])
        if self.warnings:
            lines.extend(["", "Warnings:", *(f"- {item}" for item in self.warnings)])
        return "\n".join(lines)
