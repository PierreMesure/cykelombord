"""Strict parsing for the human-authored bicycle-carriage ruleset."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class RulesError(RuntimeError):
    """Raised when a ruleset is missing, malformed, or internally inconsistent."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Match(_StrictModel):
    modes: list[Literal["rail", "bus", "ferry"]]
    agencies: list[str] = Field(default_factory=list)
    agency_aliases: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    corridors: list[str] = Field(default_factory=list)
    vehicle_types: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def needs_a_selector(self) -> Match:
        if not (
            self.agencies
            or self.agency_aliases
            or self.services
            or self.corridors
            or self.vehicle_types
        ):
            raise ValueError(
                "match needs at least one agency, alias, service, corridor, or vehicle type"
            )
        return self


class Fare(_StrictModel):
    kind: Literal["free", "fixed_sek", "included_with_ticket", "unknown"]
    amount_sek: int | None = Field(default=None, ge=0)
    note: str | None = None

    @model_validator(mode="after")
    def fixed_fares_need_an_amount(self) -> Fare:
        if self.kind == "fixed_sek" and self.amount_sek is None:
            raise ValueError("fixed_sek fare needs amount_sek")
        if self.kind != "fixed_sek" and self.amount_sek is not None:
            raise ValueError("only fixed_sek fares may have amount_sek")
        return self


class Capacity(_StrictModel):
    kind: Literal["exact", "range", "at_least", "variable", "unspecified"]
    min: int | None = Field(default=None, ge=0)
    max: int | None = Field(default=None, ge=0)
    per: Literal["train", "trainset", "vehicle", "unknown"] = "unknown"
    note: str | None = None

    @model_validator(mode="after")
    def capacity_numbers_match_kind(self) -> Capacity:
        if self.kind == "exact" and (self.min is None or self.min != self.max):
            raise ValueError("exact capacity needs identical min and max")
        if self.kind == "range" and (self.min is None or self.max is None or self.min > self.max):
            raise ValueError("range capacity needs min <= max")
        if self.kind == "at_least" and (self.min is None or self.max is not None):
            raise ValueError("at_least capacity needs min and no max")
        has_numbers = self.min is not None or self.max is not None
        if self.kind in {"variable", "unspecified"} and has_numbers:
            raise ValueError("variable and unspecified capacity cannot have min or max")
        return self


class Condition(_StrictModel):
    kind: Literal[
        "bike_type",
        "capacity_discretion",
        "event_dates",
        "route_exclusion",
        "season",
        "secure_bike",
        "time_window",
    ]
    description: str


class Evidence(_StrictModel):
    page: int = Field(ge=1)
    locator: str


class BicyclePolicy(_StrictModel):
    permission: Literal["allowed", "not_allowed", "packed_only", "conditional", "unknown"]
    bike_booking: Literal["required", "not_required", "first_come", "unknown"] = "unknown"
    ticket_purchase: Literal["advance_only", "onboard_allowed", "unknown"] = "unknown"
    fare: Fare
    capacity: Capacity
    conditions: list[Condition] = Field(default_factory=list)


class Rule(_StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    priority: int = Field(ge=0, le=1000)
    match: Match
    bicycle: BicyclePolicy
    evidence: list[Evidence] = Field(min_length=1)


class Advisory(_StrictModel):
    """Source-backed information for the frontend that does not affect GTFS pruning."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    match: Match
    kind: Literal["capacity", "event", "operational"]
    severity: Literal["info", "warning"] = "info"
    message: str
    recurrence: Literal["weekend_before_midsummer"] | None = None
    evidence: list[Evidence] = Field(min_length=1)


class SourceDocument(_StrictModel):
    name: str
    edition: str
    url: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Ruleset(_StrictModel):
    schema_version: Literal[1]
    source: SourceDocument
    rules: list[Rule] = Field(min_length=1)
    advisories: list[Advisory] = Field(default_factory=list)

    @model_validator(mode="after")
    def rule_ids_are_unique(self) -> Ruleset:
        ids = [rule.id for rule in self.rules] + [advisory.id for advisory in self.advisories]
        if len(ids) != len(set(ids)):
            raise ValueError("rule and advisory ids must be unique")
        return self


def load_ruleset(path: Path) -> Ruleset:
    """Load and strictly validate a YAML ruleset."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise RulesError(f"Could not read {path}: {error}") from error
    except yaml.YAMLError as error:
        raise RulesError(f"Could not parse YAML in {path}: {error}") from error
    if not isinstance(raw, dict):
        raise RulesError(f"Ruleset {path} must contain a YAML mapping.")
    try:
        return Ruleset.model_validate(cast(dict[str, Any], raw))
    except ValidationError as error:
        raise RulesError(str(error)) from error
