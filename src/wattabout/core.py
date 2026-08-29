from __future__ import annotations

import inspect
import math
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from numbers import Real
from typing import Any, Literal, Protocol

from pint import DimensionalityError, Quantity, Unit

from .context import Context, ElectricitySupply, get_context
from .formatting import format_quantity
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
    is_rate: bool = False

    def __getitem__(self, metric: str) -> Quantity:
        try:
            return self.values[metric]
        except KeyError as error:
            raise MissingMetricError(f"Impact has no {metric!r} metric") from error

    def over(self, duration: Quantity) -> Impact:
        if not self.is_rate:
            raise WattAboutError("Only impact rates can be integrated over a duration")
        duration.to("second")
        if duration.magnitude <= 0:
            raise WattAboutError("duration must be greater than zero")
        return replace(
            self,
            values={metric: value * duration for metric, value in self.values.items()},
            assumptions=(*self.assumptions, f"Integrated over: {duration:~}"),
            is_rate=False,
        )

    def per(self, denominator: Quantity) -> Impact:
        if denominator.magnitude <= 0:
            raise WattAboutError("impact intensity denominator must be greater than zero")
        return replace(
            self,
            values={metric: value / denominator for metric, value in self.values.items()},
            assumptions=(*self.assumptions, f"Normalized by: {denominator:~}"),
        )

    def scaled(self, factor: float) -> Impact:
        return replace(
            self,
            values={metric: value * factor for metric, value in self.values.items()},
            assumptions=(*self.assumptions, f"Occurrence factor: {factor:g}"),
        )


PrepareActivity = Callable[[Any, Mapping[str, Any]], tuple[Quantity, Quantity, Mapping[str, Any]]]
ImpactModel = Callable[[Quantity, Mapping[str, Any], Context], Impact]
InverseModel = Callable[[Quantity, str, Unit, Mapping[str, Any], Context], Quantity]
ElectricitySupplyModel = Callable[[Mapping[str, Any], Context], ElectricitySupply]


@dataclass(frozen=True, slots=True)
class ParameterSchema:
    kind: Literal["quantity", "asset", "choice", "boolean", "number", "string", "mapping"]
    default_unit: Unit | None = None
    accepted_units: tuple[Unit, ...] = ()
    choices: tuple[Any, ...] = ()
    asset_category: str | None = None
    nullable: bool = False


@dataclass(frozen=True, slots=True)
class Parameter:
    name: str
    description: str
    default: Any = None
    required: bool = False
    schema: ParameterSchema | None = None


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
        raw_ratio = target_impact / unit_impact
        try:
            ratio = raw_ratio.to(ureg.dimensionless).magnitude
        except DimensionalityError:
            if raw_ratio.check("[time]") and asset.is_rate:
                # A total compared against an annual rate asset asks how much
                # of the asset operated for its implicit one-year basis.
                years = raw_ratio.to("year").magnitude
                return years * unit
            # A rate compared against a scalable one-off asset yields
            # equivalents per year, e.g. phone_device / year.
            return raw_ratio * unit
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
    accepted_input_units: tuple[Unit, ...] = ()
    amount_name: str = "amount"
    description: str = ""
    parameters: tuple[Parameter, ...] = ()
    examples: tuple[str, ...] = ()
    is_rate: bool = False
    rate_model: ImpactModel | None = None
    rate_activity_name: str | None = None
    integration_parameter: str | None = None
    default_amount: Quantity | None = None
    electricity_supply_model: ElectricitySupplyModel | None = None

    def __post_init__(self) -> None:
        if not self.accepted_input_units:
            object.__setattr__(self, "accepted_input_units", (self.default_input_unit,))
        dimensions = [unit.dimensionality for unit in self.accepted_input_units]
        if self.default_input_unit.dimensionality not in dimensions:
            raise WattAboutError(
                f"Asset {self.id} accepted input units must include its default dimension"
            )
        if len(dimensions) != len(set(dimensions)):
            raise WattAboutError(f"Asset {self.id} has duplicate accepted input dimensions")
        if not self.amount_name.isidentifier():
            raise WattAboutError(f"Invalid amount parameter name {self.amount_name!r}")
        parameter_names = [parameter.name for parameter in self.parameters]
        if len(parameter_names) != len(set(parameter_names)):
            raise WattAboutError(f"Asset {self.id} has duplicate parameter metadata")
        if self.amount_name in parameter_names:
            raise WattAboutError(
                f"Asset {self.id} uses {self.amount_name!r} for both amount and a parameter"
            )
        if self.integration_parameter is not None:
            if not self.is_rate:
                raise WattAboutError(
                    f"Asset {self.id} has an integration parameter but is not a rate asset"
                )
            if self.integration_parameter not in parameter_names:
                raise WattAboutError(
                    f"Asset {self.id} integration parameter is missing from its metadata"
                )

    def __call__(self, amount: Any = None, **parameters: Any) -> Activity:
        self._validate_parameters(parameters, require_all=True)
        amount_was_omitted = amount is None
        if amount is None:
            amount = (
                self.default_amount
                if self.default_amount is not None
                else 1 * self.default_input_unit
            )
        elif not isinstance(amount, Quantity):
            amount = amount * self.default_input_unit
        reference_amount, display_amount, normalized = self.prepare(amount, parameters)
        activity = Activity(
            self,
            reference_amount,
            display_amount,
            normalized,
            impact_is_rate=self.is_rate,
            amount_was_omitted=amount_was_omitted,
        )
        if self.integration_parameter is not None:
            duration = parameters.get(self.integration_parameter)
            if duration is not None:
                return activity.over(duration)
        return activity

    def configure(self, **parameters: Any) -> ConfiguredAsset:
        self._validate_parameters(parameters, require_all=True)
        return ConfiguredAsset(self, dict(parameters))

    def electricity_supply(
        self, context: Context | None = None, **parameters: Any
    ) -> ElectricitySupply:
        if self.electricity_supply_model is None:
            raise WattAboutError(f"Asset {self.id} cannot supply electricity")
        self._validate_parameters(parameters, require_all=True)
        return self.electricity_supply_model(parameters, context or get_context())

    def rate(self, *, duration: Quantity | None = None, **parameters: Any) -> Activity:
        if self.rate_model is None:
            raise WattAboutError(f"Asset {self.id} does not provide an operating rate")
        self._validate_parameters(parameters, require_all=True)
        activity = Activity(
            self,
            1 * self.default_input_unit,
            1 * self.default_input_unit,
            dict(parameters),
            impact_model_override=self.rate_model,
            impact_is_rate=True,
        )
        return activity.over(duration) if duration is not None else activity

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
        if self.default_amount is not None:
            lines.extend(["", f"Default amount: {format_quantity(self.default_amount, '')}"])
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

    def rate(self, *, duration: Quantity | None = None) -> Activity:
        return self.asset.rate(duration=duration, **self.parameters)

    def electricity_supply(self, context: Context | None = None) -> ElectricitySupply:
        return self.asset.electricity_supply(context, **self.parameters)

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


def _activities_of(item: Activity | CombinedActivities) -> tuple[Activity, ...]:
    if isinstance(item, CombinedActivities):
        return item.activities
    if isinstance(item, Activity):
        return (item,)
    raise TypeError(f"Cannot combine {type(item).__name__} into activities")


@dataclass(frozen=True, slots=True)
class Comparable:
    """Shared comparison and addition behavior for impact-bearing objects."""

    def impact(self, context: Context | None = None) -> Impact:
        raise NotImplementedError

    @property
    def summary_label(self) -> str:
        raise NotImplementedError

    def _rate_flags(self) -> set[bool]:
        return {activity.impact_is_rate for activity in _activities_of(self)}

    @property
    def emission(self) -> Quantity:
        """Climate impact in the active context."""
        return self.impact()["climate"]

    @property
    def energy(self) -> Quantity:
        """Electricity with the same climate impact on the active context's grid."""
        return (self.emission / get_context().grid_intensity).to_reduced_units()

    def __add__(self, other: object) -> CombinedActivities:
        if isinstance(other, (Activity, CombinedActivities)):
            return CombinedActivities.create((*_activities_of(self), *_activities_of(other)))
        return NotImplemented

    def __radd__(self, other: object) -> Activity | CombinedActivities:
        if other == 0:
            return self  # type: ignore[return-value]
        return NotImplemented

    def __sub__(self, other: object) -> CombinedActivities:
        if isinstance(other, (Activity, CombinedActivities)):
            return self + (-1 * other)
        return NotImplemented

    def __mul__(self, factor: object) -> Activity | CombinedActivities:
        if isinstance(factor, bool) or not isinstance(factor, Real):
            return NotImplemented
        numeric_factor = float(factor)
        if not math.isfinite(numeric_factor):
            raise WattAboutError("activity multiplier must be a finite number")
        if numeric_factor == 0:
            numeric_factor = 0.0
        scaled = tuple(
            replace(
                activity,
                occurrence_factor=activity.occurrence_factor * numeric_factor,
                amount_was_omitted=False,
            )
            for activity in _activities_of(self)
        )
        return scaled[0] if len(scaled) == 1 else CombinedActivities.create(scaled)

    def __rmul__(self, factor: object) -> Activity | CombinedActivities:
        return self * factor

    def equivalent_to(
        self,
        target: Asset | ConfiguredAsset | Activity | CombinedActivities,
        *,
        metric: str | None = None,
        unit: str | Unit | None = None,
        context: Context | None = None,
        **target_parameters: Any,
    ) -> Comparison:
        selected_context = context or get_context()
        selected_metric = metric or selected_context.default_metric
        target_is_bundle = isinstance(target, CombinedActivities)
        target_is_concrete = target_is_bundle or (
            isinstance(target, Activity) and not target.amount_was_omitted
        )
        if target_is_bundle:
            if unit is not None:
                raise WattAboutError("unit cannot be supplied with a combined target")
            if target_parameters:
                raise WattAboutError("Target parameters cannot be supplied with a combined target")
            target_asset = None
            target_reference = target
            target_unit = None
            fixed_parameters = {}
        elif target_is_concrete:
            if target_parameters:
                raise WattAboutError(
                    "Target parameters cannot be supplied with an existing target activity"
                )
            target_asset = target.asset
            target_reference = target
            target_unit = ureg.Unit(unit) if unit is not None else target.display_amount.units
            fixed_parameters = target.parameters
        elif isinstance(target, Activity):
            if target_parameters:
                raise WattAboutError(
                    "Target parameters cannot be supplied with an existing target activity"
                )
            target_asset = target.asset
            target_unit = (
                ureg.Unit(unit) if unit is not None else target_asset.default_comparison_unit
            )
            fixed_parameters = target.parameters
            target_reference = None
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
        if target_is_bundle:
            target_reference_impact = target_reference.impact(selected_context)
            target_reference_value = target_reference_impact[selected_metric]
            if target_reference_value.magnitude == 0:
                raise WattAboutError("Cannot compare against zero impact for combined activities")
            raw_ratio = source_value / target_reference_value
            try:
                ratio = float(raw_ratio.to(ureg.dimensionless).magnitude)
            except DimensionalityError:
                ratio = raw_ratio
            amount = None
        elif target_is_concrete:
            target_reference_impact = target_reference.impact(selected_context)
            target_reference_value = target_reference_impact[selected_metric]
            if target_reference_value.magnitude == 0:
                raise WattAboutError(f"Cannot compare against zero impact for {target_asset.name}")
            raw_ratio = source_value / target_reference_value
            try:
                ratio = float(raw_ratio.to(ureg.dimensionless).magnitude)
            except DimensionalityError:
                ratio = raw_ratio
            if isinstance(ratio, float):
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
                if source_impact.is_rate and not target_reference_impact.is_rate:
                    amount = raw_ratio * target.display_amount
                elif not source_impact.is_rate and target_reference_impact.is_rate:
                    amount = raw_ratio
                else:
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
            uses_archetype_defaults = (
                isinstance(self, Activity)
                and self.amount_was_omitted
                and amount.dimensionality == self.display_amount.dimensionality
            )
            if uses_archetype_defaults:
                target_reference = (
                    target if isinstance(target, Activity) else target_asset(**fixed_parameters)
                )
            else:
                target_reference = target_asset(1 * target_unit, **fixed_parameters)
            target_reference_impact = target_reference.impact(selected_context)
            raw_ratio = source_value / target_reference_impact[selected_metric]
            try:
                ratio = float(raw_ratio.to(ureg.dimensionless).magnitude)
            except DimensionalityError:
                ratio = raw_ratio

        warnings: list[str] = []
        if source_impact.method != target_reference_impact.method:
            warnings.append("The activities use different impact assessment methods.")
        if source_impact.boundary != target_reference_impact.boundary:
            warnings.append(
                f"Lifecycle boundaries differ: {source_impact.boundary} versus "
                f"{target_reference_impact.boundary}."
            )
        prefers_ratio = (
            isinstance(self, Activity)
            and self.amount_was_omitted
            and not target_is_concrete
            and amount is not None
            and amount.dimensionality == self.display_amount.dimensionality
        )
        return Comparison(
            source=self,
            target=target if target_is_bundle else target_asset,
            target_reference=target_reference,
            target_is_concrete=target_is_concrete,
            metric=selected_metric,
            amount=amount,
            ratio=ratio,
            prefers_ratio=prefers_ratio,
            source_impact=source_impact,
            target_reference_impact=target_reference_impact,
            warnings=tuple(warnings),
        )

    def __truediv__(self, target: object) -> Activity | CombinedActivities | Comparison:
        if not isinstance(target, bool) and isinstance(target, Real):
            divisor = float(target)
            if not math.isfinite(divisor) or divisor == 0:
                raise WattAboutError("activity divisor must be a finite non-zero number")
            return self * (1 / divisor)
        if not isinstance(target, (Asset, ConfiguredAsset, Activity, CombinedActivities)):
            return NotImplemented
        return self.equivalent_to(target)


@dataclass(frozen=True, slots=True)
class Activity(Comparable):
    """One concrete activity with an environmental impact."""

    asset: Asset
    reference_amount: Quantity
    display_amount: Quantity
    parameters: Mapping[str, Any] = field(default_factory=dict)
    impact_model_override: ImpactModel | None = None
    impact_is_rate: bool = False
    integration_duration: Quantity | None = None
    amount_was_omitted: bool = False
    occurrence_factor: float = 1.0

    def impact(self, context: Context | None = None) -> Impact:
        model = self.impact_model_override or self.asset.impact_model
        impact = model(
            self.reference_amount,
            self.parameters,
            context or get_context(),
        )
        if impact.is_rate != self.impact_is_rate and self.integration_duration is None:
            raise WattAboutError(f"Asset {self.asset.id} returned an unexpected impact basis")
        if self.integration_duration is not None:
            impact = impact.over(self.integration_duration)
        if self.occurrence_factor != 1:
            impact = impact.scaled(self.occurrence_factor)
        return impact

    def over(self, duration: Quantity) -> Activity:
        if not self.impact_is_rate:
            raise WattAboutError("Only rate activities can be integrated over a duration")
        duration.to("second")
        if duration.magnitude <= 0:
            raise WattAboutError("duration must be greater than zero")
        return replace(
            self,
            impact_is_rate=False,
            integration_duration=duration,
        )

    def impact_intensity(
        self, context: Context | None = None, *, per: Quantity | None = None
    ) -> Impact:
        impact = self.impact(context)
        if not impact.is_rate:
            raise WattAboutError("Impact intensity requires a rate activity")
        return impact.per(self.display_amount if per is None else per)

    @property
    def summary_label(self) -> str:
        result = f"{format_quantity(self.display_amount, '')} of {self.asset.name}"
        if self.impact_is_rate:
            if self.impact_model_override is not None:
                result = f"operating rate of {self.asset.name}"
            else:
                result = f"operating rate for {result}"
        elif self.integration_duration is not None:
            if self.impact_model_override is not None:
                result = (
                    f"{format_quantity(self.integration_duration, '')} of "
                    f"{self.asset.rate_activity_name or self.asset.name}"
                )
            else:
                result = f"{result} over {format_quantity(self.integration_duration, '')}"
        if self.occurrence_factor != 1:
            return f"{self.occurrence_factor:g} × {result}"
        return result

    def __str__(self) -> str:
        return self.summary_label

    def __repr__(self) -> str:
        return format_quantity(self.impact()["climate"])


@dataclass(frozen=True, slots=True)
class CombinedActivities(Comparable):
    """Sum of several activities' environmental impacts."""

    activities: tuple[Activity, ...]

    @classmethod
    def create(cls, items: tuple[Activity, ...]) -> CombinedActivities:
        flags = {activity.impact_is_rate for activity in items}
        if len(flags) > 1:
            raise WattAboutError("Cannot add rate and non-rate activities")
        return cls(items)

    def impact(self, context: Context | None = None) -> Impact:
        selected_context = context or get_context()
        impacts = [activity.impact(selected_context) for activity in self.activities]

        metrics: list[str] = []
        for child_impact in impacts:
            for metric in child_impact.values:
                if metric not in metrics:
                    metrics.append(metric)

        values: dict[str, Quantity] = {}
        for metric in metrics:
            total = impacts[0][metric]
            for child_impact in impacts[1:]:
                total = total + child_impact[metric]
            values[metric] = total

        boundaries = {child_impact.boundary for child_impact in impacts}
        boundary = boundaries.pop() if len(boundaries) == 1 else "mixed"
        assumptions: tuple[str, ...] = ()
        for activity, child_impact in zip(self.activities, impacts):
            assumptions += tuple(
                f"[{activity.summary_label}] {line}" for line in child_impact.assumptions
            )

        return Impact(
            values=values,
            source=Source(
                name="Combined activities",
                citation=("Sum of the combined activities; each component retains its own sources"),
                components=tuple(child_impact.source for child_impact in impacts),
            ),
            geography=selected_context.region,
            reference_year=selected_context.year,
            boundary=boundary,
            dataset=selected_context.dataset,
            assumptions=assumptions,
            is_rate=self.activities[0].impact_is_rate,
        )

    @property
    def summary_label(self) -> str:
        result = self.activities[0].summary_label
        for activity in self.activities[1:]:
            if activity.occurrence_factor < 0:
                unsigned = replace(activity, occurrence_factor=-activity.occurrence_factor)
                result += f" - {unsigned.summary_label}"
            else:
                result += f" + {activity.summary_label}"
        return result

    def __str__(self) -> str:
        return self.summary_label

    def __repr__(self) -> str:
        return format_quantity(self.impact()["climate"])


@dataclass(frozen=True, slots=True)
class Comparison:
    source: Activity | CombinedActivities
    target: Asset | CombinedActivities
    target_reference: Activity | CombinedActivities
    target_is_concrete: bool
    metric: str
    amount: Quantity | None
    ratio: float | Quantity
    source_impact: Impact
    target_reference_impact: Impact
    warnings: tuple[str, ...] = ()
    prefers_ratio: bool = False

    def __str__(self) -> str:
        if isinstance(self.ratio, float) and (self.target_is_concrete or self.prefers_ratio):
            return f"{self.ratio:.3g}×"
        if self.amount is None:
            if isinstance(self.ratio, Quantity):
                return format_quantity(self.ratio)
            raise NoEquivalentAmountError("This comparison has no equivalent target amount")
        if isinstance(self.target, CombinedActivities):
            raise NoEquivalentAmountError("A combined target has no equivalent target amount")
        try:
            target_amount = self.amount.to(self.target.default_comparison_unit)
        except DimensionalityError:
            return format_quantity(self.amount)
        return format_quantity(target_amount, auto_scale=False)

    def __repr__(self) -> str:
        return str(self)

    def __float__(self) -> float:
        if not isinstance(self.ratio, float):
            raise TypeError("Only dimensionless comparisons can be converted to float")
        return self.ratio

    @property
    def percentage(self) -> float:
        if not isinstance(self.ratio, float):
            raise TypeError("Only dimensionless comparisons have a percentage")
        return self.ratio * 100

    def _summary(self) -> str:
        if isinstance(self.target_reference, CombinedActivities):
            target_label = self.target_reference.summary_label
            target_name = target_label
        else:
            target_label = (
                f"{format_quantity(self.target_reference.display_amount, '')} of {self.target.name}"
            )
            target_name = self.target.name
        if self.target_is_concrete:
            return f"{self.source.summary_label} ÷ {target_label} = {self} ({self.metric})"
        return f"{self.source.summary_label} ≈ {self} of {target_name} ({self.metric})"

    def explain(self) -> str:
        source_value = self.source_impact[self.metric].to(
            "g_co2e / year" if self.source_impact.is_rate else "g_co2e"
        )
        target_value = self.target_reference_impact[self.metric].to(
            "g_co2e / year" if self.target_reference_impact.is_rate else "g_co2e"
        )
        target_reference_label = (
            self.target_reference.summary_label
            if isinstance(self.target_reference, CombinedActivities)
            else format_quantity(self.target_reference.display_amount)
        )
        lines = [
            self._summary(),
            "",
            f"Source impact: {source_value:.3g~P}",
            (
                f"Target reference impact ({target_reference_label}): "
                f"{format_quantity(target_value)}"
            ),
            f"Target reference ratio: {format_quantity(self.ratio)}"
            if isinstance(self.ratio, Quantity)
            else f"Target reference ratio: {self.ratio:.3g}",
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
