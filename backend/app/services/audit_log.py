"""The audit trail: what happened, who did it, and nowhere to edit it (T-312).

FR-42 records every mutating action -- actor, action, target, timestamp, source
IP -- in an append-only log, and R-31 makes editing that history a defect rather
than a mistake. Five decisions here, because each is a place an audit log
usually fails.

**The trail records changes, not requests.** A refused request changed nothing:
there is no new state for anyone to be held to account for, and writing a row per
attempt would let any client fill the trail with rows of its choosing -- which is
how a log becomes unreadable exactly when someone needs to read it. So a route
appends *after* its work succeeded, a route that answers 4xx appends nothing, a
verdict that is re-sent unchanged appends nothing (no decision changed), and an
ingest batch that accepted zero records appends nothing (nothing entered the
system; the request log already holds that it was made). What is recorded is the
count of what got in -- including the rejected count of a partly-bad batch, which
is the only trace the trail keeps of the records it refused.

**Coverage is a table, and a test walks the live application.**
:data:`AUDITED_ROUTES` maps ``(method, path)`` to the action it records, and a
test enumerates every mutating route on the built app and fails if one of them is
neither in the table nor in the explicitly-exempt map (which is empty). "Every
mutating route is audited" is then a property of the application rather than a
list someone maintains by hand -- the same mechanism ROUTE_MATRIX uses for RBAC.

**The detail is thin on purpose.** Counts, currencies and identifiers: how many
records a batch carried, which verdict superseded which. Never a record's
content, never an analyst's note, never a webhook URL (which may carry a token)
and never a signing secret (R-54, R-58). An audit row that quotes the thing it
audits is a second copy of the sensitive data with weaker access control.

**A stored record cannot be edited in memory either.** :class:`AuditRecord` is
frozen and its ``detail`` is wrapped in a read-only view at construction, so
``record.detail["action"] = "..."`` raises instead of quietly rewriting the
history the trail handed out. R-31 is about the *idea* of an edit path, not about
the database having the last word on it.

**The source IP is the immediate peer.** ``request.client.host``, never
``X-Forwarded-For``: a request header is attacker-controlled, and an audit log
that records whatever a client claims about itself is worse than one that omits
the field. Behind a proxy the peer *is* the proxy, so a deployment must have
uvicorn's ``--proxy-headers`` enabled with ``--forwarded-allow-ips`` naming the
proxy for this to be the real origin -- named here because it is configuration,
not code, and a silent wrong answer is the failure mode.

**What is not here.** The SQL adapter. :class:`AuditTrail` is a protocol and the
in-memory implementation is what runs in this environment; a deployment needs a
persistent one, and :func:`audit_insert` and :func:`audit_select` are the two
statements it runs, written as functions so they can be compiled and asserted
without a database. There is deliberately no update or delete statement for
``audit_log`` anywhere in this module, which is the strongest form the R-31
assertion can take without a server to enforce it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

from sqlalchemy import Insert, Select, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import AuditLog

__all__ = [
    "AUDITED_ROUTES",
    "AUDIT_EXEMPT_ROUTES",
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "MUTATING_METHODS",
    "AuditAction",
    "AuditEntry",
    "AuditRecord",
    "AuditTrail",
    "InMemoryAuditTrail",
    "audit_insert",
    "audit_select",
    "record_action",
]

#: HTTP methods that change state. GET and HEAD are excluded by name rather than
#: by "everything else", so a new read method cannot be swept into the check.
MUTATING_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


class AuditAction(StrEnum):
    """The actions the trail records, one per mutating route.

    Values are dotted ``noun.verb`` strings rather than enum member names: they
    are persisted, filtered on and rendered in the admin screen, so they are part
    of the wire contract and a rename would be a data migration.
    """

    ingest_flows = "ingest.flows"
    ingest_logs = "ingest.logs"
    alert_verdict = "alert.verdict"
    webhook_create = "webhook.create"
    webhook_delete = "webhook.delete"
    key_create = "key.create"
    key_revoke = "key.revoke"
    retention_apply = "retention.apply"
    privacy_erasure = "privacy.erasure"
    model_promote = "model.promote"
    model_rollback = "model.rollback"
    threshold_recalibrate = "threshold.recalibrate"
    threshold_set = "threshold.set"
    user_role = "user.role"
    #: The one *read* in this table: an export is data leaving the system, which is
    #: the question the trail answers (T-408, D-065).
    hunt_export = "hunt.export"


#: Route to action: the coverage contract (FR-42). A mutating route missing from
#: this table fails the suite, so a new endpoint cannot ship unlogged.
AUDITED_ROUTES: Mapping[tuple[str, str], AuditAction] = MappingProxyType(
    {
        ("POST", "/api/v1/ingest/flows"): AuditAction.ingest_flows,
        ("POST", "/api/v1/ingest/logs"): AuditAction.ingest_logs,
        ("POST", "/api/v1/alerts/{alert_id}/verdict"): AuditAction.alert_verdict,
        ("POST", "/api/v1/webhooks"): AuditAction.webhook_create,
        ("DELETE", "/api/v1/webhooks/{webhook_id}"): AuditAction.webhook_delete,
        ("POST", "/api/v1/keys"): AuditAction.key_create,
        ("DELETE", "/api/v1/keys/{key_id}"): AuditAction.key_revoke,
        ("POST", "/api/v1/retention/run"): AuditAction.retention_apply,
        ("POST", "/api/v1/privacy/erasure"): AuditAction.privacy_erasure,
        ("POST", "/api/v1/models/{model_id}/promote"): AuditAction.model_promote,
        ("POST", "/api/v1/models/{kind}/rollback"): AuditAction.model_rollback,
        ("POST", "/api/v1/thresholds/recalibrate"): AuditAction.threshold_recalibrate,
        ("PUT", "/api/v1/thresholds/{family}/{band}"): AuditAction.threshold_set,
        ("POST", "/api/v1/users/{user_id}/role"): AuditAction.user_role,
        # The export (T-408). A POST because it writes a trail row -- see the
        # module docstring of ``app.api.v1.endpoints.hunt``.
        ("POST", "/api/v1/hunt/export"): AuditAction.hunt_export,
    }
)

#: Mutating routes that deliberately record nothing, with the reason. Empty, and
#: it should stay that way: an entry here is a decision that an action is not
#: worth attributing, which is the thing FR-42 exists to prevent.
AUDIT_EXEMPT_ROUTES: Mapping[tuple[str, str], str] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """One action, as an endpoint reports it.

    Attributes:
        action: what was done, from :class:`AuditAction`.
        actor: the authenticated principal, as the access token names it. The
            numeric ``users.id`` the table column wants is the adapter's mapping
            (the same seam D-038 names for verdicts), because the token subject
            is opaque.
        target_type: the kind of thing acted on -- ``alert``, ``webhook``.
        target_id: its identifier, as a string so one column holds every kind.
        detail: thin, non-sensitive context. Read-only once constructed.
        ip: the peer address the request came from, or ``None`` when the
            transport has no peer (an ASGI test client, for instance).
        at: when it happened, timezone-aware.
    """

    action: AuditAction
    actor: str
    target_type: str
    target_id: str
    at: datetime
    detail: Mapping[str, object] = field(default_factory=dict)
    ip: str | None = None

    def __post_init__(self) -> None:
        """Refuse a record that cannot be attributed, addressed or trusted."""
        if not self.actor.strip():
            raise ValueError(
                "an audit record must name its actor; an unattributed action cannot "
                "answer 'who did this', which is the only question the trail exists for"
            )
        if not self.target_type.strip() or not self.target_id.strip():
            raise ValueError("an audit record must name its target")
        if self.at.tzinfo is None or self.at.utcoffset() is None:
            raise ValueError(
                "at must be timezone-aware; a naive timestamp is written as the "
                "session's zone, so two rows an hour apart can sort as though they "
                "were simultaneous"
            )
        # Frozen stops field assignment, not mutation of what a field points at:
        # without this, a caller holding the detail dict could rewrite history
        # after the trail had accepted it.
        object.__setattr__(self, "detail", MappingProxyType(dict(self.detail)))


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """A stored record and the position the trail gave it.

    Attributes:
        sequence: 1-based, assigned by the trail, never reused. The store owns
            it because only the store can guarantee monotonicity; deriving it
            from the record's content would collide on a legitimate repeat (D-036
            is the opposite case: a verdict is identified by its data because a
            repeated verdict *is* the same fact, while two identical ingest
            batches are two events).
        record: the fact.
    """

    sequence: int
    record: AuditRecord

    def __post_init__(self) -> None:
        """Refuse a stored row without a position."""
        if self.sequence < 1:
            raise ValueError(f"sequence must be a positive position, got {self.sequence}")


class AuditTrail(Protocol):
    """Append-only storage for audit records.

    There is deliberately no ``update`` or ``delete``, and no ``purge`` or
    ``truncate``. The in-memory implementation is tested for the absence of those
    names, the way R-31 is asserted for the ORM model, because an implementation
    that satisfied this protocol by being mutable would defeat the criterion
    while passing the type checker.
    """

    def append(self, record: AuditRecord) -> AuditEntry:
        """Store a record and return it with its position."""
        ...

    def entries(
        self,
        *,
        start: datetime,
        end: datetime,
        action: AuditAction | None = None,
        actor: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        before: int | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> tuple[AuditEntry, ...]:
        """Read records in a time range, newest first.

        ``start`` and ``end`` are required. The audit table is not partitioned --
        it must keep every row retention does not explicitly drop -- but it grows
        forever, and a read with a generous default range is the unbounded scan
        R-34's principle forbids, just written differently.
        """
        ...


class InMemoryAuditTrail:
    """An :class:`AuditTrail` in a list, for tests and single-process runs.

    Not durable, and therefore not the trail a deployment runs: a restart would
    erase the history. The persistent trail is the ``audit_log`` table and it is
    not written here because there is no PostgreSQL in this environment to verify
    a migration or a query against -- recorded, not hidden.
    """

    __slots__ = ("_entries", "_next_sequence")

    def __init__(self) -> None:
        """Start empty."""
        self._entries: list[AuditEntry] = []
        self._next_sequence = 1

    def append(self, record: AuditRecord) -> AuditEntry:
        """Store a record and return it with its position."""
        entry = AuditEntry(sequence=self._next_sequence, record=record)
        self._entries.append(entry)
        self._next_sequence += 1
        return entry

    def entries(
        self,
        *,
        start: datetime,
        end: datetime,
        action: AuditAction | None = None,
        actor: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        before: int | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> tuple[AuditEntry, ...]:
        """Read records in ``[start, end)``, newest first, at most ``limit``.

        ``before`` is an exclusive sequence cursor: the next page asks for
        ``before=<last sequence of this page>``. Offset paging would drift here
        because the trail only ever grows, and a page that repeats or skips a row
        is a page an auditor cannot cite.
        """
        if end <= start:
            raise ValueError(
                f"the range is empty or inverted: start {start.isoformat()} must "
                f"precede end {end.isoformat()}"
            )
        if limit < 1:
            raise ValueError(f"limit must be at least 1, got {limit}")
        selected = [
            entry
            for entry in self._entries
            if start <= entry.record.at < end
            and (action is None or entry.record.action == action)
            and (actor is None or entry.record.actor == actor)
            and (target_type is None or entry.record.target_type == target_type)
            and (target_id is None or entry.record.target_id == target_id)
            and (before is None or entry.sequence < before)
        ]
        selected.reverse()
        return tuple(selected[:limit])

    def __len__(self) -> int:
        """How many records are stored."""
        return len(self._entries)


def record_action(
    trail: AuditTrail,
    *,
    action: AuditAction,
    actor: str,
    target_type: str,
    target_id: str,
    at: datetime,
    detail: Mapping[str, object] | None = None,
    ip: str | None = None,
) -> AuditEntry:
    """Build a record for one action and append it.

    The single call an endpoint makes after its work succeeded, so the five call
    sites cannot each invent their own field set or their own idea of what
    belongs in ``detail``.

    Raises:
        ValueError: if the record cannot be attributed, addressed or trusted.
    """
    return trail.append(
        AuditRecord(
            action=action,
            actor=actor,
            target_type=target_type,
            target_id=target_id,
            at=at,
            detail=detail if detail is not None else {},
            ip=ip,
        )
    )


def audit_insert(record: AuditRecord, *, actor_id: int) -> Insert:
    """The INSERT the persistent trail runs for one record.

    Args:
        record: the action.
        actor_id: the numeric ``users.id`` behind the token subject. The mapping
            from the opaque subject to the row is the adapter's, exactly as it is
            for ``alerts.verdict_by`` (D-038), and it is a parameter here because
            this function cannot look it up.

    Returns:
        An ``INSERT`` against ``audit_log``. Nothing else in this module writes
        it, and no statement anywhere updates or deletes from it (R-31).
    """
    return pg_insert(AuditLog).values(
        actor_id=actor_id,
        action=record.action.value,
        target_type=record.target_type,
        target_id=record.target_id,
        detail=dict(record.detail),
        ip=record.ip,
        at=record.at,
    )


def audit_select(
    *,
    start: datetime,
    end: datetime,
    actor_id: int | None = None,
    action: AuditAction | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    before: int | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Select[AuditLog]:
    """The SELECT the persistent trail runs for a page.

    Newest first, bounded to ``[start, end)`` and to ``limit`` rows, with an
    exclusive ``before`` id cursor. Every filter is optional except the time
    range, which is not: the table keeps history forever, and this is the
    statement that would read all of it.
    """
    if end <= start:
        raise ValueError("the range is empty or inverted")
    statement = select(AuditLog).where(AuditLog.at >= start, AuditLog.at < end)
    if actor_id is not None:
        statement = statement.where(AuditLog.actor_id == actor_id)
    if action is not None:
        statement = statement.where(AuditLog.action == action.value)
    if target_type is not None:
        statement = statement.where(AuditLog.target_type == target_type)
    if target_id is not None:
        statement = statement.where(AuditLog.target_id == target_id)
    if before is not None:
        statement = statement.where(AuditLog.id < before)
    return statement.order_by(AuditLog.at.desc(), AuditLog.id.desc()).limit(limit)
