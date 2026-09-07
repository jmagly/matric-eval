"""Explicit, versioned cross-benchmark aggregation declarations."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, pattern=r".*\S.*")]
Finite = Annotated[float, Field(strict=True, allow_inf_nan=False)]
MissingnessPolicy = Literal["require-complete", "exclude-unavailable"]
Direction = Literal["higher", "lower"]


class PolicyRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class MetricTransform(PolicyRecord):
    version: Literal["1"]
    kind: Literal["identity", "affine"]
    source_units: Text
    source_minimum: Finite | None
    source_maximum: Finite | None
    source_direction: Direction
    scale: Finite
    offset: Finite

    @model_validator(mode="after")
    def valid_transform(self) -> Self:
        if self.scale == 0:
            raise ValueError("transform scale must be nonzero")
        if self.source_minimum is not None and self.source_maximum is not None:
            if self.source_minimum > self.source_maximum:
                raise ValueError("transform source minimum exceeds maximum")
        if self.kind == "identity" and (self.scale != 1 or self.offset != 0):
            raise ValueError("identity transform requires scale=1 and offset=0")
        return self


class AggregationTerm(PolicyRecord):
    benchmark_id: Text
    metric_id: Text
    weight: Annotated[float, Field(gt=0, strict=True, allow_inf_nan=False)]
    transform: MetricTransform


class SuiteAggregation(PolicyRecord):
    version: Literal["1"]
    aggregation_id: Text
    target_units: Text
    target_direction: Direction
    missingness_policy: MissingnessPolicy
    terms: list[AggregationTerm]

    @model_validator(mode="after")
    def validate_terms(self) -> Self:
        if not self.terms:
            raise ValueError("aggregation requires at least one term")
        ids = [term.benchmark_id for term in self.terms]
        if len(ids) != len(set(ids)):
            raise ValueError("aggregation benchmark terms must be unique")
        for term in self.terms:
            transform = term.transform
            direction = transform.source_direction
            if transform.scale < 0:
                direction = "lower" if direction == "higher" else "higher"
            if direction != self.target_direction:
                raise ValueError("transform direction does not match target direction")
            if transform.kind == "identity" and transform.source_units != self.target_units:
                raise ValueError("identity transform cannot change units")
        return self
