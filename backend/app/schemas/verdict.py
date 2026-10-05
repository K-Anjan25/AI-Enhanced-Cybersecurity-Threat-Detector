"""Wire contracts for analyst verdicts (FR-16, T-309).

The verdict field is a plain ``str`` here rather than an enum, for the same
reason :class:`~app.schemas.query.AlertQuery` takes severity as a string: the
import-boundary contract forbids ``app.schemas`` from reaching into the database
module where the domain enum lives, because that module imports SQLAlchemy and
schemas are meant to stay declarative. The service validates the value and
refuses an unknown one, which is where a wire string becomes a domain value.

`created_at` is required on both requests and is the alert's partition key, not
a convenience: per D-030 an alert's ``id`` is not unique across the partitioned
``alerts`` table, so ``id`` alone does not identify a row, and R-34 forbids
touching that table without a time bound.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

#: FR-16 has no note field; this is the free text an analyst may attach. Long
#: enough for a sentence or two, short enough that a history cannot be used as a
#: file store. Defined here because the schema enforces it on the way in and the
#: service enforces it in the record -- one number, two places that must agree.
MAX_NOTE_LENGTH = 500

__all__ = [
    "MAX_NOTE_LENGTH",
    "VerdictHistoryOut",
    "VerdictOutcomeOut",
    "VerdictRecordOut",
    "VerdictRequest",
]


class VerdictRequest(BaseModel):
    """A verdict to record on one alert."""

    model_config = ConfigDict(frozen=True)

    verdict: str = Field(description="true_positive, false_positive or benign.")
    created_at: datetime = Field(
        description="The alert's created_at, which addresses its partition (D-030)."
    )
    note: str | None = Field(default=None, max_length=MAX_NOTE_LENGTH)


class VerdictRecordOut(BaseModel):
    """One verdict record as returned by the API."""

    model_config = ConfigDict(frozen=True)

    id: str
    alert_id: int
    verdict: str
    actor: str
    at: datetime
    note: str | None
    supersedes: str | None


class VerdictOutcomeOut(BaseModel):
    """The result of recording a verdict.

    ``action`` is ``recorded`` or ``unchanged``. The second is not an error: the
    same analyst re-sending the verdict already current means the client may
    safely retry, and nothing in the history moved.
    """

    model_config = ConfigDict(frozen=True)

    action: str
    record: VerdictRecordOut
    superseded: VerdictRecordOut | None


class VerdictHistoryOut(BaseModel):
    """Every verdict recorded on one alert, oldest first."""

    model_config = ConfigDict(frozen=True)

    alert_id: int
    created_at: datetime
    current: VerdictRecordOut | None
    items: list[VerdictRecordOut]
