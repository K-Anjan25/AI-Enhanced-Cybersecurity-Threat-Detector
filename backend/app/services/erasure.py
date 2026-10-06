"""Erasure: a subject's data is removed everywhere it is stored as data (T-314, NFR-05).

R-37 says deletes of user data go through this service -- no ad-hoc ``DELETE``
for a privacy request -- and the service has to answer three questions honestly,
because "we erased them" is a claim a company can be held to.

**Where does it cascade?** A :class:`ErasureTarget` is one store the service
knows how to reach, and the service is constructed with at least one. Each target
reports how many rows it changed, so the report is per-store rather than a single
number: *which* store still holds something is the question an operator asks when
a request is disputed.

**What does it do where a record cannot be rewritten?** Two stores here are
append-only by design: the audit trail (R-31) and the verdict ledger (D-038). The
service does not pretend to rewrite them. It reports them as
:class:`PreservedLedger` entries, naming each one and the reason, so a report can
never be read as "everything is gone". The resolution for those stores is legal
(an immutable security record is the Art. 17(3) exception) or structural (retention
that drops whole periods), and both are named rather than implied.

**Where it can act, it redacts rather than deletes.** An entity row is referenced
by alerts; deleting it would either cascade into alert history or leave dangling
rows. Redacting ``entities.value`` to a deployment-scoped tombstone removes the
identifier and keeps the alerts readable, which is what "erasure" has to mean for
a record whose *purpose* is the alert, not the name.

**The tombstone is a keyed hash, and the limit is named.** ``redactor`` derives it
with HMAC under an HKDF key from ``AEGIS_SECRET_KEY``, so it is stable within a
deployment (a second request for the same subject produces the same tombstone)
and not reversible from the database alone. It is a pseudonym, not an
anonymisation: a deployment that holds its own secret can still test a candidate
identifier against a tombstone, so the protection is against a stolen dump, not
against the operator. That is exactly the property ``architecture.md`` §5 asks for
when it says PII fields are "replaced with salted hashes".

**Idempotence is a ledger, not a guess.** The service keeps an append-only record
of the tombstones it has erased -- not the identifiers, because a ledger of
identifiers would be the very data the request asked to remove. A second request
for the same subject finds the tombstone, touches no target, appends nothing, and
reports ``already_erased``: the request is honoured again, and nothing changes
again. Without the ledger, "idempotent" would mean "the targets happen to be
idempotent", which is a property of other people's stores.

**The report does not repeat the identifier.** It carries the tombstone, the
per-target counts and the reason. Echoing the subject back would put the value in
a response body, a log line and a support ticket -- the three places an erasure
was supposed to remove it from (R-54, R-58).
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

__all__ = [
    "DEFAULT_LEDGER_LIMIT",
    "MAX_LEDGER_LIMIT",
    "EntityRedactionTarget",
    "ErasureKind",
    "ErasureLedger",
    "ErasureReport",
    "ErasureService",
    "ErasureSubject",
    "ErasureTarget",
    "InMemoryErasureLedger",
    "LedgerEntry",
    "PreservedLedger",
    "Redactor",
    "TargetOutcome",
]

#: How many ledger entries a listing returns by default, and the ceiling. The
#: ledger grows with privacy requests, which are rare, but a listing with no
#: bound is the unbounded scan R-34's principle forbids.
DEFAULT_LEDGER_LIMIT = 100
MAX_LEDGER_LIMIT = 1000


class ErasureKind(StrEnum):
    """What kind of thing is being erased.

    The kind is not decoration: a user's data lives in ``users`` (and cascades to
    their API keys), while an entity's lives in ``entities`` (and is referenced by
    alerts). Erasing one must not touch the other's rows, and a request that does
    not say which is refused rather than guessed.
    """

    user = "user"
    entity = "entity"


@dataclass(frozen=True, slots=True)
class ErasureSubject:
    """An identifier to erase.

    Attributes:
        kind: user or entity.
        value: the identifier as it is stored -- an email, a login, a hostname, a
            service name. Held only for the duration of the call: nothing in this
            module stores it.
    """

    kind: ErasureKind
    value: str

    def __post_init__(self) -> None:
        """Refuse an empty identifier.

        A blank subject would match nothing and report a successful erasure of
        nothing, which is the worst possible answer to a privacy request.
        """
        object.__setattr__(self, "kind", _checked_kind(self.kind))
        if not self.value.strip():
            raise ValueError("an erasure subject must name a value; blank erases nothing")
        if len(self.value) > 512:
            raise ValueError(f"subject value is {len(self.value)} characters, over the 512 limit")


def _checked_kind(kind: object) -> ErasureKind:
    """Coerce a kind from untyped input, refusing anything else.

    Typed as ``object`` on purpose: the dataclass annotation says ``ErasureKind``,
    so a check inside the dataclass is unreachable as far as a type checker is
    concerned -- but a request body, a script or a queue message can still pass a
    string, and a wrong kind would silently erase nothing.

    Raises:
        ValueError: naming the allowed kinds.
    """
    if isinstance(kind, ErasureKind):
        return kind
    if not isinstance(kind, str):
        allowed = ", ".join(member.value for member in ErasureKind)
        msg = f"kind must be one of: {allowed}; got {kind!r}"
        raise ValueError(msg)
    try:
        return ErasureKind(kind)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in ErasureKind)
        msg = f"kind must be one of: {allowed}; got {kind!r}"
        raise ValueError(msg) from exc


class Redactor:
    """Turns a subject into the tombstone written in its place.

    One derivation for every store, so the same subject has the same tombstone in
    the entity table and in any future store, and a second request is
    recognisably the same person without the plaintext being anywhere.
    """

    __slots__ = ("_key",)

    def __init__(self, app_secret: str) -> None:
        """Derive the tombstone key.

        Raises:
            ValueError: if the application secret is too short to be a key source.
        """
        if len(app_secret) < 32:
            msg = "app_secret must be at least 32 characters to derive a tombstone key"
            raise ValueError(msg)
        self._key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"aegis.erasure.tombstone.v1",
            info=b"erasure-tombstone",
        ).derive(app_secret.encode())

    def tombstone(self, subject: ErasureSubject) -> str:
        """The value that replaces the identifier, prefixed so it is recognisable.

        The kind is part of the MAC input, so a user named ``bob`` and an entity
        named ``bob`` do not collide on one tombstone.
        """
        digest = hmac.new(
            self._key, f"{subject.kind.value}:{subject.value}".encode(), hashlib.sha256
        ).hexdigest()
        return f"erased:{digest[:32]}"

    def matches(self, subject: ErasureSubject, tombstone: str) -> bool:
        """Whether a subject is the one a tombstone was derived from, in constant time."""
        return hmac.compare_digest(self.tombstone(subject), tombstone)


class ErasureTarget(Protocol):
    """One store the erasure service can cascade into.

    An implementation is deliberately narrow: it erases one subject by kind and
    reports how many rows it changed. It must be idempotent -- erasing a subject
    it has already erased returns ``0`` and is not an error -- because the service
    relies on that when the ledger is empty (a restored database, a fresh
    process) and a report of ``0`` is the honest answer.
    """

    name: str

    def kind(self) -> ErasureKind:
        """Which kind of subject this target holds."""
        ...

    def erase(self, subject: ErasureSubject, *, replacement: str) -> int:
        """Remove the subject's identifier from this store; return rows changed."""
        ...


class ErasureLedger(Protocol):
    """Append-only storage for the fact that a subject was erased.

    There is no ``delete``: a ledger whose entries could be removed would be a
    way to claim an erasure that never happened. Entries hold tombstones only.
    """

    def has(self, tombstone: str) -> bool:
        """Whether this tombstone has been recorded."""
        ...

    def append(self, entry: LedgerEntry) -> None:
        """Record one erasure. Appending is the only write."""
        ...

    def entries(self, *, limit: int, before: int | None = None) -> Sequence[LedgerEntry]:
        """The entries, newest first, before a sequence number if given."""
        ...


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One recorded erasure.

    Attributes:
        sequence: assigned by the ledger, 1-based.
        tombstone: what the subject became. Never the identifier.
        kind: user or entity.
        at: when it happened.
        requested_by: the authenticated subject that asked for it. This is the
            one identifier the ledger does hold, and it is held only because R-37
            requires the action to be attributable -- the audit trail holds it
            too, which is the same trade-off made twice and named in D-045.
        targets: per-target row counts, so the ledger answers "what was erased",
            not only "an erasure happened".
    """

    sequence: int
    tombstone: str
    kind: ErasureKind
    at: datetime
    requested_by: str
    targets: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        """Refuse an entry that could not be trusted or read back."""
        if self.sequence < 1:
            raise ValueError(f"sequence must be 1-based, got {self.sequence}")
        if not self.tombstone.startswith("erased:"):
            raise ValueError("tombstone must be an 'erased:' pseudonym, not an identifier")
        if self.at.tzinfo is None or self.at.utcoffset() is None:
            raise ValueError("at must be timezone-aware, got a naive timestamp")
        if not self.requested_by.strip():
            raise ValueError("an erasure must name who requested it")


class InMemoryErasureLedger:
    """An :class:`ErasureLedger` in a list, for tests and single-process runs.

    Not durable: a restart would forget which subjects were already erased, and
    the next request for one would cascade again. The stores are idempotent, so
    the outcome is still correct -- but the ledger's own answer changes from
    ``already_erased`` to a live cascade, which is why the persistent ledger is a
    table and is named as a gap rather than left implied.
    """

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        """Start empty."""
        self._entries: list[LedgerEntry] = []

    def has(self, tombstone: str) -> bool:
        """Whether this tombstone has been recorded."""
        return any(entry.tombstone == tombstone for entry in self._entries)

    def append(self, entry: LedgerEntry) -> None:
        """Record one erasure."""
        self._entries.append(entry)

    def entries(self, *, limit: int, before: int | None = None) -> tuple[LedgerEntry, ...]:
        """The entries, newest first, before a sequence number if given."""
        if limit < 1:
            raise ValueError(f"limit must be at least 1, got {limit}")
        ordered = sorted(self._entries, key=lambda entry: entry.sequence, reverse=True)
        if before is not None:
            ordered = [entry for entry in ordered if entry.sequence < before]
        return tuple(ordered[:limit])

    def next_sequence(self) -> int:
        """The sequence number an append would receive."""
        return len(self._entries) + 1

    def __len__(self) -> int:
        """How many erasures have been recorded."""
        return len(self._entries)


@dataclass(frozen=True, slots=True)
class TargetOutcome:
    """What one target did.

    Attributes:
        name: the target's name.
        affected: rows whose identifier was removed. ``0`` is a normal answer --
            the subject may have had nothing in that store.
    """

    name: str
    affected: int


@dataclass(frozen=True, slots=True)
class PreservedLedger:
    """An append-only store the service did not rewrite, and why.

    Reported in every erasure because a report that lists only what changed reads
    as "nothing else holds this subject".
    """

    name: str
    reason: str


@dataclass(frozen=True, slots=True)
class ErasureReport:
    """The result of one erasure request.

    Attributes:
        kind: what kind of subject was erased.
        tombstone: what the subject became. The report never carries the value.
        at: when the request was handled.
        outcomes: one :class:`TargetOutcome` per target, in registration order.
        preserved: append-only stores that were deliberately not rewritten.
        already_erased: whether the ledger already held this tombstone, in which
            case no target was touched and nothing was appended.
        ledger_sequence: the entry that recorded it, or ``None`` when the request
            was a repeat and appended nothing.
    """

    kind: ErasureKind
    tombstone: str
    at: datetime
    outcomes: tuple[TargetOutcome, ...]
    preserved: tuple[PreservedLedger, ...]
    already_erased: bool
    ledger_sequence: int | None

    @property
    def affected(self) -> int:
        """Total rows changed across every target."""
        return sum(outcome.affected for outcome in self.outcomes)

    @property
    def changed_anything(self) -> bool:
        """Whether the request changed any store."""
        return self.affected > 0


class ErasureService:
    """Cascades an erasure across every registered target, and records it.

    The service owns three things worth naming: the order of the cascade, the
    ledger that makes a repeat a no-op, and the list of stores it deliberately
    does not touch. It does not own the stores -- each target does -- so adding a
    store to the cascade is adding a target, and forgetting to is visible in the
    report rather than silent.
    """

    __slots__ = ("_ledger", "_preserved", "_redactor", "_targets")

    #: Append-only stores this service will not rewrite. Class-level because the
    #: decision is a property of the system, not of a deployment: any instance
    #: that omitted them would produce a misleading report.
    PRESERVED: tuple[PreservedLedger, ...] = (
        PreservedLedger(
            name="audit_log",
            reason=(
                "append-only by R-31: the trail records that this erasure happened "
                "and cannot be rewritten. Erasing an actor from history is a "
                "deliberate non-goal; the mechanism for it is the trail's own "
                "retention window"
            ),
        ),
        PreservedLedger(
            name="verdicts",
            reason=(
                "append-only by D-038: a verdict is a decision about an alert and "
                "its history is the point of keeping it. Analyst notes are the one "
                "field that could carry a subject's data and are not searchable, "
                "so they are left and named here rather than silently kept"
            ),
        ),
    )

    def __init__(
        self,
        targets: Sequence[ErasureTarget],
        *,
        ledger: ErasureLedger,
        redactor: Redactor,
    ) -> None:
        """Build the cascade.

        Raises:
            ValueError: if no target is registered, or two targets share a name.
                An empty cascade would report a successful erasure of nothing --
                the one outcome a privacy service must never produce.
        """
        if not targets:
            raise ValueError(
                "an erasure service with no targets would report success while "
                "erasing nothing; register at least one target"
            )
        names = [target.name for target in targets]
        if len(set(names)) != len(names):
            raise ValueError(f"target names must be unique, got {sorted(names)}")
        self._targets = tuple(targets)
        self._ledger = ledger
        self._redactor = redactor

    @property
    def targets(self) -> tuple[str, ...]:
        """The registered target names, in cascade order."""
        return tuple(target.name for target in self._targets)

    def erase(self, subject: ErasureSubject, *, requested_by: str, at: datetime) -> ErasureReport:
        """Erase a subject everywhere the cascade reaches, once.

        Args:
            subject: the identifier and its kind.
            requested_by: the authenticated principal asking. Recorded in the
                ledger and in the audit entry (the endpoint appends that); a
                privacy request with no owner is not actionable.
            at: timezone-aware time.

        Returns:
            The report. A second call for the same subject touches no target,
            appends nothing and reports ``already_erased``.

        Raises:
            ValueError: if ``requested_by`` is blank or ``at`` is naive.
        """
        if not requested_by.strip():
            raise ValueError("an erasure must name who requested it")
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("at must be timezone-aware, got a naive timestamp")

        tombstone = self._redactor.tombstone(subject)
        if self._ledger.has(tombstone):
            return ErasureReport(
                kind=subject.kind,
                tombstone=tombstone,
                at=at,
                outcomes=tuple(
                    TargetOutcome(name=target.name, affected=0) for target in self._targets
                ),
                preserved=self.PRESERVED,
                already_erased=True,
                ledger_sequence=None,
            )

        outcomes: list[TargetOutcome] = []
        for target in self._targets:
            if target.kind() is not subject.kind:
                # A target holds one kind; skipping is not a failure. It is
                # reported with 0 so the report still names every store.
                outcomes.append(TargetOutcome(name=target.name, affected=0))
                continue
            outcomes.append(
                TargetOutcome(
                    name=target.name, affected=target.erase(subject, replacement=tombstone)
                )
            )

        sequence = self._next_sequence()
        self._ledger.append(
            LedgerEntry(
                sequence=sequence,
                tombstone=tombstone,
                kind=subject.kind,
                at=at,
                requested_by=requested_by,
                targets=tuple((outcome.name, outcome.affected) for outcome in outcomes),
            )
        )
        return ErasureReport(
            kind=subject.kind,
            tombstone=tombstone,
            at=at,
            outcomes=tuple(outcomes),
            preserved=self.PRESERVED,
            already_erased=False,
            ledger_sequence=sequence,
        )

    def _next_sequence(self) -> int:
        """The next sequence number, from the ledger when it can say."""
        next_sequence = getattr(self._ledger, "next_sequence", None)
        if callable(next_sequence):
            value: int = next_sequence()
            return value
        return len(self._ledger.entries(limit=MAX_LEDGER_LIMIT)) + 1

    def histogram(
        self, *, limit: int = DEFAULT_LEDGER_LIMIT, before: int | None = None
    ) -> tuple[LedgerEntry, ...]:
        """The erasure ledger, newest first.

        Raises:
            ValueError: if ``limit`` is outside ``1..MAX_LEDGER_LIMIT``. A caller
                that wants more than the ceiling is asking for a scan.
        """
        if not 1 <= limit <= MAX_LEDGER_LIMIT:
            raise ValueError(f"limit must be 1..{MAX_LEDGER_LIMIT}, got {limit}")
        return tuple(self._ledger.entries(limit=limit, before=before))


# --- targets -----------------------------------------------------------------


class EntityStore(Protocol):
    """Storage for entity rows: hosts, addresses, users and services.

    Narrow on purpose: erasure needs to replace one identifier with a tombstone
    and count what changed. It does not need to read the entity, and a target that
    could would be tempted to log it.
    """

    def redact_value(self, value: str, *, replacement: str, kind: str | None = None) -> int:
        """Replace every entity whose ``value`` is exactly ``value``.

        ``kind`` scopes it to one kind when given. It matters because the schema's
        identity for an entity is ``(kind, value)``: a user called ``bob`` and a
        host called ``bob`` are two rows about two things, and an erasure request
        names which one it is about.
        """
        ...


class InMemoryEntityStore:
    """An :class:`EntityStore` in a dictionary keyed by ``(kind, value)``."""

    __slots__ = ("_entities",)

    def __init__(self) -> None:
        """Start empty."""
        self._entities: dict[tuple[str, str], dict[str, object]] = {}

    def add(self, kind: str, value: str, **meta: object) -> None:
        """Register an entity, as ingest does on first sight."""
        if not value.strip():
            raise ValueError("an entity needs a value")
        self._entities[(kind, value)] = {"kind": kind, "value": value, **meta}

    def redact_value(self, value: str, *, replacement: str, kind: str | None = None) -> int:
        """Replace every entity whose value matches, in one kind or in all.

        Two rows in different kinds do not collide: the store's key is
        ``(kind, value)``, which is the schema's identity for an entity
        (``uq_entities_kind_value``).
        """
        affected = 0
        for key, entity in list(self._entities.items()):
            if entity["value"] != value:
                continue
            if kind is not None and key[0] != kind:
                continue
            entity["value"] = replacement
            self._entities[(key[0], replacement)] = entity
            if key[1] != replacement:
                del self._entities[key]
            affected += 1
        return affected

    def values(self) -> tuple[str, ...]:
        """Every value currently stored, for assertions."""
        return tuple(sorted(str(entity["value"]) for entity in self._entities.values()))

    def __len__(self) -> int:
        """How many entities exist."""
        return len(self._entities)


class UserStore(Protocol):
    """Storage for user rows, whose deletion cascades to what they owned.

    Narrow for the same reason :class:`EntityStore` is: erasure deletes and
    counts. ``api_keys.owner_id`` carries ``ON DELETE CASCADE`` in the schema, so
    an implementation of this protocol that talked to PostgreSQL would delete the
    subject's keys as a side effect of the row delete, and a test asserts the
    in-memory model does the same rather than leaving the keys behind.
    """

    def erase_owner(self, owner: str, *, replacement: str) -> int:
        """Delete the subject's user row; return the users removed."""
        ...


class InMemoryUserStore:
    """A :class:`UserStore` over a set of identifiers, with a cascade to keys.

    Models the schema's own behaviour rather than inventing a policy: deleting a
    user cascades to ``api_keys``, because ``owner_id`` is a foreign key with
    ``ON DELETE CASCADE``. Without that cascade, an erased user's machine
    credentials would outlive them -- which is exactly the leak a privacy request
    is about.
    """

    __slots__ = ("_keys", "_users")

    def __init__(self, *, keys: object | None = None) -> None:
        """Start empty; ``keys`` is the store the cascade reaches, if any."""
        self._users: set[str] = set()
        self._keys = keys

    def add(self, value: str) -> None:
        """Register a user, as account creation does."""
        if not value.strip():
            raise ValueError("a user needs an identifier")
        self._users.add(value)

    def erase_owner(self, owner: str, *, replacement: str) -> int:
        """Delete the user and cascade to their API keys.

        ``replacement`` is ignored: a deleted row has nowhere to carry a
        tombstone, and the ledger is what records that the erasure happened.
        """
        if owner not in self._users:
            return 0
        self._users.discard(owner)
        cascade = getattr(self._keys, "erase_owner", None)
        if callable(cascade):
            cascade(owner, replacement="")
        return 1

    def __len__(self) -> int:
        """How many users exist."""
        return len(self._users)


class UserDeletionTarget:
    """An :class:`ErasureTarget` over a :class:`UserStore`.

    Unlike the entity target this one deletes rather than redacts: a user row is
    the account, and an account whose identifier is a pseudonym is not deleted in
    any sense a data subject would recognise. What must survive is the *history*
    of what the account did, and that lives in stores this service reports as
    preserved rather than rewrites.
    """

    def __init__(self, store: UserStore, *, name: str = "users") -> None:
        """Wrap a store under a name that appears in the report."""
        self._store = store
        self.name = name

    def kind(self) -> ErasureKind:
        """Users, not entities."""
        return ErasureKind.user

    def erase(self, subject: ErasureSubject, *, replacement: str) -> int:
        """Delete the user row and anything that cascades from it."""
        if subject.kind is not ErasureKind.user:
            return 0
        return self._store.erase_owner(subject.value, replacement=replacement)


class EntityRedactionTarget:
    """An :class:`ErasureTarget` over an :class:`EntityStore`.

    Redaction rather than deletion: alerts reference the entity row, so removing
    it would either cascade into alert history -- destroying the record of an
    incident that an operator may still be investigating -- or leave the alerts
    pointing at nothing. The identifier is what the request is about; the alert
    count is not.
    """

    def __init__(self, store: EntityStore, *, name: str = "entities") -> None:
        """Wrap a store under a name that appears in the report."""
        self._store = store
        self.name = name

    def kind(self) -> ErasureKind:
        """Entities, not users."""
        return ErasureKind.entity

    def erase(self, subject: ErasureSubject, *, replacement: str) -> int:
        """Replace the entity's identifier with the tombstone."""
        if subject.kind is not ErasureKind.entity:
            return 0
        return self._store.redact_value(subject.value, replacement=replacement)
