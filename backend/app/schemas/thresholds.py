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
    "ThresholdListOut",
    "ThresholdOut",
    "ThresholdOutcomeOut",
]


class ThresholdOut(BaseModel):
    """One ``thresholds`` row, as the API returns it."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    family: str
    band: str
    value: float
    source: str
    updated_at: datetime


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
