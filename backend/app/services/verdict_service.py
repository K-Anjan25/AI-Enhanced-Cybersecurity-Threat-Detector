"""Analyst verdicts: written once, superseded in order, never edited (T-309).

FR-16 lets an analyst mark an alert ``true_positive``, ``false_positive`` or
``benign``. The acceptance criterion is that verdicts are immutable once written
and that a second verdict **supersedes** the first with the history retained.

Three decisions make that mean something rather than being a comment.

**A verdict is an appended record, not a field someone can overwrite.** The
current verdict on the alert row is a denormalised pointer for the list view;
the truth is the ordered records, and :class:`VerdictLedger` exposes no update
or delete at all. A test asserts that absence the same way R-31's test asserts
it for the audit log, because "we would not do that" is not an invariant.

**A repeat is not a supersession.** Recording the same verdict for the same
alert by the same analyst returns the existing record with ``unchanged`` instead
of appending a duplicate. Without that rule a client retry after a timeout, or a
double-click, would pad the history with rows that look like reconsideration.
A *different* verdict -- or the same verdict from a different analyst, which is
agreement worth recording -- appends and supersedes.

**The alert is identified by ``(id, created_at)``, not by id alone.** Per D-030
the partitioned ``alerts`` table cannot enforce a globally unique ``id``, so a
verdict addressed by id alone would be a verdict on whichever partition the
database happened to search. ``created_at`` is the partition key, and R-34
requires it on every read or write against that table, so it is required here
too rather than defaulted.

**What is not here, and why not.** The persistence adapter. :class:`VerdictLedger`
is a protocol and the in-memory implementation is what runs in this environment;
a deployment needs a new append-only table -- the schema has ``alerts.verdict``,
which holds only the current decision, so the history the criterion requires has
nowhere to live yet -- created by a migration (R-32), plus the bounded ``UPDATE``
of the alert row that :func:`alert_verdict_update` describes. Neither is written
here because there is no PostgreSQL in this environment to verify a migration
against, the same gap T-301 and T-308 recorded rather than papered over. Three
things the adapter must get right, named so the gap is not rediscovered as a bug:
the actor is the token's opaque ``sub`` while ``alerts.verdict_by`` is a numeric
``users.id``, so the mapping has to come from the users table rather than an
``int()`` cast that fails at runtime; the record id is derived read-then-write, so
concurrent appends must be serialised by the store (a sequence or a unique index
on the alert and a per-alert ordinal); and an append must not be a ``UPSERT``,
which would make the second verdict overwrite the first.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from app.db.models import Verdict
from app.schemas.verdict import MAX_NOTE_LENGTH

__all__ = [
    "AlertVerdictUpdate",
    "InMemoryVerdictLedger",
    "UnknownVerdict",
    "VerdictAction",
    "VerdictLedger",
    "VerdictOutcome",
    "VerdictRecord",
    "alert_verdict_update",
    "record_verdict",
]


class UnknownVerdict(ValueError):
    """The requested verdict is not one of FR-16's three values."""


@dataclass(frozen=True, slots=True)
class VerdictRecord:
    """One analyst decision, as written.

    Frozen, and the ledger stores the instance it was given. Nothing in this
    module can produce a modified copy: a correction is a *new* record that
    points back at this one.

    Attributes:
        id: positional within the alert's history -- ``<alert>-v<n>``, derived
            from the history itself rather than from a process counter (D-036).
        alert_id: the alert's ``id`` column.
        alert_created_at: the alert's partition key. Required to address the
            alert at all (D-030); a verdict cannot say which partition it means
            without it.
        verdict: the decision.
        actor: the authenticated principal, as the access token names it.
        at: when the decision was recorded, timezone-aware.
        note: optional free text, stripped and length-checked.
        supersedes: the id of the record this one replaces, ``None`` for the first.
    """

    id: str
    alert_id: int
    alert_created_at: datetime
    verdict: Verdict
    actor: str
    at: datetime
    note: str | None
    supersedes: str | None

    def __post_init__(self) -> None:
        """Refuse a record that cannot be attributed or ordered."""
        if not self.id.strip():
            raise ValueError("a verdict record needs an id")
        if self.alert_id < 1:
            raise ValueError(f"alert_id must be a positive row id, got {self.alert_id}")
        for name, value in (("at", self.at), ("alert_created_at", self.alert_created_at)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware, got a naive timestamp")
        if not self.actor.strip():
            raise ValueError(
                "a verdict must name the analyst who set it; an unattributed verdict "
                "cannot answer 'who decided this', which is the point of keeping it"
            )
        if self.note is not None and len(self.note) > MAX_NOTE_LENGTH:
            raise ValueError(f"note is {len(self.note)} characters, over the {MAX_NOTE_LENGTH}")


class VerdictLedger(Protocol):
    """Append-only storage for verdict records.

    There is deliberately no ``update`` or ``delete``. Implementing this
    protocol with a mutable store would satisfy the type checker and defeat the
    acceptance criterion, so the in-memory implementation is tested for the
    absence of those methods and the live one must be append-only by the same
    argument as ``audit_log`` (R-31).
    """

    def current(self, alert_id: int, alert_created_at: datetime) -> VerdictRecord | None:
        """The latest verdict for one alert, or ``None`` if none was set."""
        ...

    def history(self, alert_id: int, alert_created_at: datetime) -> Sequence[VerdictRecord]:
        """Every verdict for one alert, oldest first."""
        ...

    def append(self, record: VerdictRecord) -> None:
        """Add a record. Appending is the only write this store performs."""
        ...


class InMemoryVerdictLedger:
    """A :class:`VerdictLedger` in a dictionary, for tests and single-process runs.

    Not durable, and therefore not the ledger a deployment runs: a restart would
    erase the history the criterion requires retaining. The persistent ledger is
    a table, and it is not written here because there is no PostgreSQL in this
    environment to verify one against -- recorded, not hidden.
    """

    __slots__ = ("_by_alert",)

    def __init__(self) -> None:
        """Start empty."""
        self._by_alert: dict[tuple[int, datetime], list[VerdictRecord]] = {}

    def current(self, alert_id: int, alert_created_at: datetime) -> VerdictRecord | None:
        """The latest verdict for one alert, or ``None``."""
        records = self._by_alert.get((alert_id, alert_created_at))
        return records[-1] if records else None

    def history(self, alert_id: int, alert_created_at: datetime) -> tuple[VerdictRecord, ...]:
        """Every verdict for one alert, oldest first."""
        return tuple(self._by_alert.get((alert_id, alert_created_at), ()))

    def append(self, record: VerdictRecord) -> None:
        """Add a record to its alert's history."""
        self._by_alert.setdefault((record.alert_id, record.alert_created_at), []).append(record)

    def __len__(self) -> int:
        """How many verdict records are stored."""
        return sum(len(records) for records in self._by_alert.values())


class VerdictAction(StrEnum):
    """What recording a verdict did."""

    recorded = "recorded"
    unchanged = "unchanged"


@dataclass(frozen=True, slots=True)
class VerdictOutcome:
    """The result of recording one verdict.

    Attributes:
        action: ``recorded`` when a new record was appended, ``unchanged`` when
            the same analyst re-sent the verdict that is already current.
        record: the current record afterwards.
        superseded: the record this one replaced, or ``None``.
    """

    action: VerdictAction
    record: VerdictRecord
    superseded: VerdictRecord | None


@dataclass(frozen=True, slots=True)
class AlertVerdictUpdate:
    """The bounded alert-row write a verdict implies.

    Attributes:
        alert_id: the row to update.
        created_at: the partition key, part of the predicate because R-34
            forbids a partitioned write with no time bound.
        verdict: the value for the ``verdict`` column.
        verdict_at: the value for the ``verdict_at`` column.
        actor: the token subject. The adapter resolves this to the numeric
            ``verdict_by`` foreign key; this module does not guess.
    """

    alert_id: int
    created_at: datetime
    verdict: str
    verdict_at: datetime
    actor: str


def _as_verdict(value: str | Verdict) -> Verdict:
    """Coerce a wire string to the domain enum, naming the allowed values.

    Raises:
        UnknownVerdict: if the value is not one of FR-16's three. Refused rather
            than defaulted: a typo that silently became ``benign`` would be a
            wrong label on a real alert.
    """
    if isinstance(value, Verdict):
        return value
    try:
        return Verdict(value)
    except ValueError as exc:
        allowed = ", ".join(sorted(member.value for member in Verdict))
        msg = f"verdict {value!r} is not one of: {allowed}"
        raise UnknownVerdict(msg) from exc


def _clean_note(note: str | None) -> str | None:
    """Strip a note and turn an empty one into ``None``.

    An empty string and an absent note mean the same thing, and storing both
    would produce two histories that read differently for no reason.
    """
    if note is None:
        return None
    cleaned = note.strip()
    return cleaned or None


def record_verdict(
    ledger: VerdictLedger,
    *,
    alert_id: int,
    alert_created_at: datetime,
    verdict: str | Verdict,
    actor: str,
    at: datetime,
    note: str | None = None,
) -> VerdictOutcome:
    """Record an analyst's verdict on one alert.

    Args:
        ledger: the append-only store.
        alert_id: the alert's ``id`` column.
        alert_created_at: the alert's partition key, which addresses the alert
            unambiguously (D-030, R-34).
        verdict: one of ``true_positive``, ``false_positive``, ``benign``.
        actor: the authenticated principal's subject.
        at: when the decision was recorded, timezone-aware.
        note: optional free text.

    Returns:
        The outcome: ``recorded`` with the new record, or ``unchanged`` with the
        record already current when the same analyst repeats their own verdict.

    Raises:
        UnknownVerdict: if the verdict is not one of FR-16's three values.
        ValueError: if a timestamp is naive, the actor is empty or the note is
            over :data:`app.schemas.verdict.MAX_NOTE_LENGTH` -- raised by
            :class:`VerdictRecord`,
            which is where those invariants live.
    """
    resolved = _as_verdict(verdict)
    cleaned = _clean_note(note)
    current = ledger.current(alert_id, alert_created_at)
    if current is not None and current.verdict is resolved and current.actor == actor:
        return VerdictOutcome(action=VerdictAction.unchanged, record=current, superseded=None)

    record = VerdictRecord(
        id=f"{alert_id}-v{len(ledger.history(alert_id, alert_created_at)) + 1}",
        alert_id=alert_id,
        alert_created_at=alert_created_at,
        verdict=resolved,
        actor=actor,
        at=at,
        note=cleaned,
        supersedes=current.id if current is not None else None,
    )
    ledger.append(record)
    return VerdictOutcome(action=VerdictAction.recorded, record=record, superseded=current)


def alert_verdict_update(outcome: VerdictOutcome) -> AlertVerdictUpdate | None:
    """The alert-row write a verdict implies, or ``None`` when nothing changed.

    Returning ``None`` for ``unchanged`` is deliberate: a repeat verdict is not a
    write, and issuing one would move ``verdict_at`` forward and make a
    re-submission look like a fresh decision.
    """
    if outcome.action is VerdictAction.unchanged:
        return None
    record = outcome.record
    return AlertVerdictUpdate(
        alert_id=record.alert_id,
        created_at=record.alert_created_at,
        verdict=record.verdict.value,
        verdict_at=record.at,
        actor=record.actor,
    )
