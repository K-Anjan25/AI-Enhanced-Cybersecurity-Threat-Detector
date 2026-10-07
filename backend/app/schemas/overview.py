"""Wire contracts for the overview aggregation (T-416, FR-50).

One request, three panels: the KPI tiles, the severity series and the entity list
are one window's aggregate, so they cannot disagree with each other the way three
independent reads can. The pipeline strip stays where it was -- ``/metrics`` is the
scrape, and a scrape is not a window (D-060).

Two fields exist to keep the response honest rather than merely complete:

* ``unrecognised_severity`` -- a band the enum does not define is counted here,
  so ``sum(by_severity) + unrecognised_severity == alerts`` always holds and a tile
  can never quietly drop a row it did not understand.
* ``entities_capped``, ``families_capped`` and ``verdicts_measured`` -- "ten
  entities" is not "ten of 4,000", and a mean of one verdict is not a trend; both
  counts travel with the figure they qualify.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "OverviewBucket",
    "OverviewFamily",
    "OverviewEntity",
    "OverviewOut",
    "OverviewTotals",
    "OverviewWindow",
]


class OverviewWindow(BaseModel):
    """The window the figures describe, echoed so a client can label them."""

    model_config = ConfigDict(frozen=True)

    start: datetime
    end: datetime
    #: Whole hours between the bounds, for the label the screen prints.
    hours: float = Field(ge=0)


class OverviewTotals(BaseModel):
    """The KPI tiles: the window's counts, complete rather than capped."""

    model_config = ConfigDict(frozen=True)

    alerts: int = Field(ge=0)
    open: int = Field(ge=0)
    by_severity: dict[str, int]
    unrecognised_severity: int = Field(ge=0)
    verdicts: dict[str, int]
    unrecorded: int = Field(ge=0)
    verdicts_measured: int = Field(ge=0)
    mean_time_to_verdict_seconds: float | None


class OverviewBucket(BaseModel):
    """One point of the severity series.

    ``score`` is the mean composite score of the bucket's alerts, or ``null`` when the
    bucket held none (T-418). It exists because the traffic explorer draws the alert
    overlay along the same buckets as its own volume series, and one window's alert
    numbers should come from one place: the aggregate that already counted them.
    """

    model_config = ConfigDict(frozen=True)

    start: datetime
    total: int = Field(ge=0)
    by_severity: dict[str, int]
    score: float | None = Field(
        default=None,
        description="Mean score of the bucket's alerts; null for a bucket that held none.",
    )


class OverviewEntity(BaseModel):
    """One entity in the window, named.

    ``kind`` and ``value`` are the host, address, user or service the ``entities``
    table holds for this id. They are ``None`` when the registry cannot name the
    id, and ``named`` says which case this is rather than leaving a client to infer
    it from a null -- a screen that renders "Entity 42" must know it is showing an
    id *because the name is unknown*, not because the API forgot a field.
    """

    model_config = ConfigDict(frozen=True)

    entity_id: int
    kind: str | None
    value: str | None
    named: bool
    alerts: int = Field(ge=0)
    occurrences: int = Field(ge=0)
    open: int = Field(ge=0)
    worst_severity: str
    max_score: float
    last_seen: datetime


class OverviewFamily(BaseModel):
    """One threat family's share of the window.

    ``(unnamed)`` is the label for a blank attribution rather than a dropped row:
    the bars have to add up to the window, and "the model attributed no family" is
    a fact about the window, not a missing value.
    """

    model_config = ConfigDict(frozen=True)

    family: str
    alerts: int = Field(ge=0)
    worst_severity: str


class OverviewOut(BaseModel):
    """The overview's three panels, from one read of one window."""

    model_config = ConfigDict(frozen=True)

    window: OverviewWindow
    bucket_minutes: int
    totals: OverviewTotals
    series: list[OverviewBucket]
    entities: list[OverviewEntity]
    entities_capped: bool
    families: list[OverviewFamily]
    families_capped: bool
