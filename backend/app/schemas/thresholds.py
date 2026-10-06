"""Wire contracts for the threshold endpoints (FR-18, R-69, T-322).

Two things the shape of these models is saying:

**A threshold is read with what is in force, not with what was requested.** The
listing carries the value for each ``(family, band)`` the deployment has moved
away from FR-13's defaults, *and* those defaults themselves, because an operator
asking "what will fire an alert" needs both halves: the rows, and the documented
values that govern every family with no row. Returning only the rows would make an
empty list look like "no thresholds", which is the opposite of the truth.

**A refusal is reported, never inferred from a number.** :class:`ThresholdOutcomeOut`
carries ``reason``, so a family the job declined to fit is distinguishable from a
fit that happened to ask for the value already in force. ``requested`` is ``None``
in the first case and a number in the second, and a client that wanted to tell them
apart could not do it from ``previous``/``applied`` alone.

The band is a plain ``str`` rather than an enum here, for the reason
``app/schemas/query.py`` gives: the domain enum lives in the database module, which
imports SQLAlchemy, and schemas stay declarative. The service refuses an unknown
band, which is where a wire string becomes a domain value -- including ``info``,
which has no lower bound to move.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "RecalibrationOut",
    "RecalibrationRequest",
    "ThresholdImpactOut",
    "ThresholdListOut",
    "ThresholdOut",
    "ThresholdOutcomeOut",
    "ThresholdSetOut",
    "ThresholdSetRequest",
]


class ThresholdOut(BaseModel):
    """One ``thresholds`` row, as the API returns it."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    family: str
    band: str
    value: float
    source: str = Field(
        description=(
            "Stored provenance, as written: `recalculation` for a fitted value, "
            "`manual` for one a person set."
        )
    )
    source_label: str = Field(
        default="",
        description=(
            "design.md §4.8's vocabulary: `calibrated` or `manual`. A family with no "
            "row at all is `default`, which the listing reports as a documented value "
            "rather than as a row."
        ),
    )
    updated_at: datetime
    changed_by: str | None = Field(
        default=None,
        description=(
            "Who last moved this value, read from the audit trail. Null when the "
            "trail holds no record at the row's write instant, which is a fact "
            "rather than a reason to guess."
        ),
    )


class ThresholdSetRequest(BaseModel):
    """A hand-set threshold (design.md §4.8's manual edit).

    ``value`` is a proportion, so it is bounded here as well as in the service: a
    request carrying 70 for 0.70 is refused at the edge with a schema error rather
    than reaching a service that would refuse it as out of range.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: float = Field(gt=0.0, lt=1.0, description="The new lower bound, strictly inside (0, 1).")


class ThresholdSetOut(BaseModel):
    """What a hand-set threshold did, including when it changed nothing."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    family: str
    band: str
    previous: float
    previous_label: str
    applied: float
    source: str
    changed: bool = Field(
        description="False when the same hand had already set this value: nothing was written."
    )
    at: datetime


class ThresholdImpactOut(BaseModel):
    """What a proposed threshold would have produced over the preview window.

    ``would_fire`` counts recorded alerts whose score is at or above the proposed
    bound -- the cases the correlator already stored, whatever severity they were
    banded at (T-308 bands after the case exists). The unit is *alerts*, not raw
    events: a row stands for a case, and its ``occurrence_count`` says how many
    occurrences went into it.
    """

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    family: str
    band: str
    proposed: float
    current: float
    current_source: str
    window_start: datetime
    window_end: datetime
    alerts_read: int
    would_fire: int
    would_stop_firing: int
    would_start_firing: int
    complete: bool = Field(
        description="False when the page cap stopped the walk: the counts are a floor, not a total."
    )


class ThresholdListOut(BaseModel):
    """The values in force for this deployment, and the defaults behind them."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    defaults: dict[str, float] = Field(
        description="FR-13's documented initial band edges, in force wherever no row exists."
    )
    items: list[ThresholdOut]


class RecalibrationRequest(BaseModel):
    """Which band to recalibrate. Everything else is policy, not a per-run knob."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    band: str = Field(
        default="high",
        description=(
            "FR-13 band whose lower bound to move. `high` is the default because the "
            "PRD measures precision and recall at the deployed `high` threshold, so "
            "that is the bar a false-positive budget applies to."
        ),
    )


class ThresholdOutcomeOut(BaseModel):
    """What the run decided about one threshold."""

    model_config = ConfigDict(frozen=True)

    family: str
    band: str
    previous: float
    previous_was_default: bool
    requested: float | None
    applied: float
    changed: bool
    clamped: bool
    sample_size: int
    reason: str = Field(description="`fitted` or `insufficient_feedback`.")


class RecalibrationOut(BaseModel):
    """A run's report: the window it read, and every threshold it considered."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    band: str
    at: datetime
    since: datetime
    until: datetime
    quantile: float
    minimum_sample: int
    considered: int
    changed: int
    outcomes: list[ThresholdOutcomeOut]
