"""Scoped API keys for machine-to-machine ingestion (FR-44, T-313).

A machine credential is not a password and not a session token, and the three
decisions that matter here follow from that.

**The secret is a high-entropy random string and is stored only as a keyed
digest.** 32 bytes of :mod:`secrets` is not guessable, so the slow, memory-hard
hashing R-51 requires *for passwords* would buy nothing here and would cost a
64 MiB allocation on every ingest request -- a denial-of-service vector wearing a
hardening costume. What is stored is ``HMAC-SHA256`` over the *whole presented
key* under a key derived from ``AEGIS_SECRET_KEY``: 64 hex characters, which is
exactly the width of the ``api_keys.key_hash`` column. It is HMAC rather than a
plain digest so a stolen database on its own is not an offline oracle, and the
cost is named rather than hidden: rotating the application secret invalidates
every issued key at once, the same consequence the webhook vault documents.

**The key carries a public identifier, and nothing else about it is recoverable.**
The format is ``aegis_sk_<id>_<secret>``. The ``<id>`` is the row's primary key,
so the listing and the design's "only a prefix is stored" are satisfied without a
second column: the prefix an operator sees is ``aegis_sk_<id>_``, and the rest of
the string exists nowhere but in the digest. Lookup is by id, comparison is
:func:`hmac.compare_digest` over the full presentation, and a wrong *prefix* fails
the digest just as a wrong secret does -- the id routes, the MAC decides.

**The id is not a secret, and no answer depends on it.** Presenting a key whose
id does not exist computes the digest anyway and compares against a dummy, so
"no such key" and "wrong secret" cost the same work and return the same 401. The
residual is named: an attacker can still learn which ids *exist* by timing a
database lookup, and that is metadata, not credential material.

**Scopes are explicit and default-deny.** A key holds a set of scopes drawn from
:class:`Scope`; a request is allowed when the route is one keys may call *and*
the key's scopes grant that route's capability. An empty scope set is refused at
issue time rather than meaning "everything", because the only thing worse than a
key that cannot do its job is one that can do someone else's.

**Revocation is a column, not a deletion, and it takes effect on the next
request.** There is no delete: the row is the record of a credential having
existed, and R-31's reasoning about history applies to it even though the rule
names only ``audit_log``. Verification reads the store every time -- there is no
cache to go stale -- because "revoked immediately" is the criterion, and a cache
is exactly how a revoked key keeps working for a while.

**What is not here.** The persistent store. :class:`ApiKeyStore` is a protocol and
the in-memory implementation is what runs in this environment;
:func:`api_key_insert`, :func:`api_key_select`, :func:`api_key_revoke` and
:func:`api_key_touch` are the statements the adapter will run, written as
functions so they compile and can be asserted without a database. ``owner_id`` is
a numeric ``users.id`` while the token subject is an opaque string -- the same
mapping gap D-038 names for ``alerts.verdict_by``, so the statements take the
integer and the records carry the string.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import Insert, Select, Update, insert, select, update
from sqlalchemy import or_ as sql_or

from app.db.models import ApiKey

__all__ = [
    "API_KEY_PREFIX",
    "DEFAULT_TOUCH_INTERVAL_SECONDS",
    "KEY_SECRET_BYTES",
    "ApiKeyRecord",
    "ApiKeyStore",
    "InMemoryApiKeyStore",
    "InvalidKeyFormat",
    "IssuedKey",
    "KeyDigest",
    "ParsedKey",
    "Scope",
    "api_key_insert",
    "api_key_revoke",
    "api_key_select",
    "api_key_touch",
    "format_key",
    "issue_key",
    "looks_like_key",
    "parse_key",
    "revoke_key",
    "scopes_from_names",
    "verify_key",
]

#: The public prefix every key carries, so a leaked string is recognisable in a
#: secret scanner's output and a human sees immediately what kind of credential it is.
API_KEY_PREFIX = "aegis_sk_"  # pragma: allowlist secret -- a public prefix, not a credential

#: 32 bytes of urandom, base64url-encoded: 256 bits of entropy, and 43 characters
#: that survive copy-paste through a shell, a YAML file and an HTTP header.
KEY_SECRET_BYTES = 32

#: A key's last-used timestamp answers "is this credential still in use", which
#: does not need second precision. Writing a row on every ingest request would be
#: write amplification and a hot row; the store refuses to update more often than
#: this, and the SQL does that decision in the database rather than read-modify-write.
DEFAULT_TOUCH_INTERVAL_SECONDS = 60

_SECRET_ALPHABET = re.compile(r"^[A-Za-z0-9_-]+$")
_KEY_PATTERN = re.compile(
    rf"^{re.escape(API_KEY_PREFIX)}(?P<id>\d{{1,19}})_(?P<secret>[A-Za-z0-9_-]+)$"
)

#: Compared against when the id is unknown, so a missing row costs the same MAC
#: computation as a wrong secret. Not a real digest of anything.
_DUMMY_DIGEST = "0" * 64


class Scope(StrEnum):
    """What an API key may do, independently of any human role.

    Dotted ``noun:verb`` strings: they are persisted in an array column, filtered
    on and rendered, so a rename would be a data migration. Kept deliberately few
    -- FR-44 is about ingestion, and a second scope exists because a machine that
    ingests and cannot check that its data landed is half a feature.
    """

    ingest_write = "ingest:write"
    alerts_read = "alerts:read"


class InvalidKeyFormat(ValueError):
    """A presented string is not shaped like an API key.

    Not a credential failure: it means the caller did not present a key at all,
    and the caller distinguishes the cases so a JWT is never mistaken for one.
    """


#: The example key in the docstring is assembled, not typed, so it is not a
#: literal that a secret scanner has to be told about.
_KEY_EXAMPLE = f"{API_KEY_PREFIX}7_" + "x" * 43


@dataclass(frozen=True, slots=True)
class ParsedKey:
    """The two halves of a presented key.

    Attributes:
        key_id: the public identifier, as it appeared -- digits only, and *not*
            normalised, because the digest covers the string as presented.
        secret: the secret half.
    """

    key_id: int
    secret: str


def generate_secret() -> str:
    """A fresh secret half, shown to the operator exactly once."""
    return secrets.token_urlsafe(KEY_SECRET_BYTES)


def format_key(key_id: int, secret: str) -> str:
    """Assemble a key from its public id and its secret half.

    Raises:
        ValueError: if the id is not positive, or the secret half is not in the
            alphabet the format allows. A key that cannot be parsed back would be
            issued and then never work, which is worse than refusing it.
    """
    if key_id < 1:
        raise ValueError(f"key_id must be a positive row id, got {key_id}")
    if not secret or not _SECRET_ALPHABET.match(secret):
        raise ValueError("the secret half must be non-empty url-safe base64")
    return f"{API_KEY_PREFIX}{key_id}_{secret}"


def parse_key(presented: str) -> ParsedKey:
    """Split a presented key into its id and secret halves.

    Raises:
        InvalidKeyFormat: if the string is not a key. Strict on purpose: the
            shape decides which credential path a request takes, so a permissive
            parser would let a mistyped token be treated as a key and fail later
            with the wrong diagnosis.
    """
    match = _KEY_PATTERN.match(presented.strip())
    if match is None:
        msg = f"not an AEGIS API key: expected {_KEY_EXAMPLE!r} shape"
        raise InvalidKeyFormat(msg)
    return ParsedKey(key_id=int(match.group("id")), secret=match.group("secret"))


def looks_like_key(presented: str) -> bool:
    """Whether a string is shaped like a key, without parsing it.

    Used to choose a credential path. Deliberately the same pattern
    :func:`parse_key` uses, so the two cannot disagree about what a key is.
    """
    return _KEY_PATTERN.match(presented.strip()) is not None


class KeyDigest:
    """Computes the stored digest of a presented key.

    The derivation is HKDF-SHA256 from the application secret with a purpose
    salt, so the digest key is not the signing key, the sealing key or the JWT
    key -- each purpose gets its own derived key from one root secret.
    """

    __slots__ = ("_key",)

    def __init__(self, app_secret: str) -> None:
        """Derive the digest key.

        Raises:
            ValueError: if the application secret is too short to be a key source.
        """
        if len(app_secret) < 32:
            msg = "app_secret must be at least 32 characters to derive a digest key"
            raise ValueError(msg)
        self._key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"aegis.apikey.digest.v1",
            info=b"api-key-digest",
        ).derive(app_secret.encode())

    def digest(self, presented: str) -> str:
        """The 64-character digest of a whole presented key.

        Over the *whole* string, prefix included: the id half is public, but
        covering it means a key with its id rewritten is refused by the MAC and
        not merely by a lookup miss.
        """
        return hmac.new(self._key, presented.encode(), hashlib.sha256).hexdigest()

    def matches(self, presented: str, stored: str | None) -> bool:
        """Whether a presented key matches a stored digest, in constant time.

        A missing row is compared against a dummy of the same length rather than
        short-circuited, so the work done does not announce whether the id exists.
        """
        return hmac.compare_digest(self.digest(presented), stored or _DUMMY_DIGEST)


@dataclass(frozen=True, slots=True)
class ApiKeyRecord:
    """One issued key, as stored. It cannot hold the secret: there is no field for it.

    Attributes:
        id: the public identifier, embedded in the key. Assigned by the store.
        name: what the operator called it.
        owner: the principal the key belongs to, as the token names them. The
            numeric ``users.id`` the column wants is the adapter's mapping (D-038).
        scopes: what the key may do. Never empty: a key that can do nothing is a
            misconfiguration, and an empty set read as "all" is how that becomes
            a vulnerability.
        digest: the stored digest of the full key string.
        created_at: timezone-aware.
        revoked_at: when it was revoked, or ``None`` while it is live.
        last_used_at: the coarse last-seen stamp, or ``None`` if never used.
    """

    id: int
    name: str
    owner: str
    scopes: frozenset[Scope]
    digest: str
    created_at: datetime
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None

    def __post_init__(self) -> None:
        """Refuse a record that cannot be identified, attributed or trusted."""
        if self.id < 1:
            raise ValueError(f"id must be a positive row id, got {self.id}")
        if not self.name.strip():
            raise ValueError(
                "an API key must be named; an unnamed credential cannot be revoked on purpose"
            )
        if not self.owner.strip():
            raise ValueError("an API key must name its owner")
        if not self.scopes:
            raise ValueError(
                "an API key must carry at least one scope: an empty set would have to "
                "mean either 'nothing' (useless) or 'everything' (unacceptable)"
            )
        if len(self.digest) != 64 or not all(char in "0123456789abcdef" for char in self.digest):
            raise ValueError("digest must be 64 lowercase hex characters, the width of key_hash")
        for name in ("created_at", "revoked_at", "last_used_at"):
            value = getattr(self, name)
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{name} must be timezone-aware, got a naive timestamp")
        if self.revoked_at is not None and self.revoked_at < self.created_at:
            raise ValueError("revoked_at cannot precede created_at")

    @property
    def prefix(self) -> str:
        """What an operator sees of this key: the public half, and nothing more."""
        return f"{API_KEY_PREFIX}{self.id}_"

    @property
    def active(self) -> bool:
        """Whether the key may still be used."""
        return self.revoked_at is None

    def grants(self, scope: Scope) -> bool:
        """Whether a live key holds a scope. A revoked key grants nothing."""
        return self.active and scope in self.scopes


@dataclass(frozen=True, slots=True)
class IssuedKey:
    """A new key and the secret an operator sees exactly once.

    The plaintext is deliberately not a field on :class:`ApiKeyRecord`: the row
    the store keeps cannot leak what it does not hold. This mirrors T-311's
    ``RegisteredTarget``, and for the same reason.
    """

    record: ApiKeyRecord
    secret: str


class ApiKeyStore(Protocol):
    """Storage for API keys.

    There is deliberately no ``delete``. A revoked key is a row with
    ``revoked_at`` set: the credential existed, it was used or it was not, and
    someone revoked it -- all of which is history, and deleting it would erase
    the answer to "was this key revoked, and when". R-31 names only
    ``audit_log``; the reasoning is not specific to that table.
    """

    def create(self, build: Callable[[int], ApiKeyRecord]) -> ApiKeyRecord:
        """Assign an id, store the record ``build`` produces for it, return it.

        The callback exists because a key's digest covers its id: the record
        cannot be built until the id is known, and the store is what knows it.
        A SQL adapter implements this by taking the next value from the id
        sequence, calling ``build`` and inserting the row with that id -- one
        write, and no placeholder row to clean up if the second write fails.
        """
        ...

    def get(self, key_id: int) -> ApiKeyRecord | None:
        """The record with this id, revoked or not."""
        ...

    def list(self) -> Sequence[ApiKeyRecord]:
        """Every record, oldest first."""
        ...

    def revoke(self, key_id: int, *, at: datetime) -> ApiKeyRecord | None:
        """Mark a key revoked. Idempotent: an existing revocation keeps its timestamp."""
        ...

    def touch(self, key_id: int, *, at: datetime) -> bool:
        """Record a use, at most once per touch interval."""
        ...


class InMemoryApiKeyStore:
    """An :class:`ApiKeyStore` in a dictionary, for tests and single-process runs.

    Not durable, and therefore not the store a deployment runs: a restart would
    forget every issued key while the machines holding them keep sending.
    """

    __slots__ = ("_by_id", "_next_id", "_touch_interval")

    def __init__(self, *, touch_interval: timedelta | None = None) -> None:
        """Start empty."""
        self._by_id: dict[int, ApiKeyRecord] = {}
        self._next_id = 1
        self._touch_interval = touch_interval or timedelta(seconds=DEFAULT_TOUCH_INTERVAL_SECONDS)

    def create(self, build: Callable[[int], ApiKeyRecord]) -> ApiKeyRecord:
        """Assign the next id, store the record built for it, return it.

        Raises:
            ValueError: propagated from ``build`` or the record's validation; the
                id is not consumed, so a refused issue leaves no gap that would
                make two keys look like they were created out of order.
        """
        candidate = self._next_id
        stored = build(candidate)
        if stored.id != candidate:
            msg = f"build() returned id {stored.id} for the assigned id {candidate}"
            raise ValueError(msg)
        self._by_id[stored.id] = stored
        self._next_id += 1
        return stored

    def get(self, key_id: int) -> ApiKeyRecord | None:
        """The record with this id, revoked or not."""
        return self._by_id.get(key_id)

    def list(self) -> tuple[ApiKeyRecord, ...]:
        """Every record, oldest first."""
        return tuple(self._by_id[key] for key in sorted(self._by_id))

    def revoke(self, key_id: int, *, at: datetime) -> ApiKeyRecord | None:
        """Mark a key revoked, keeping the first revocation timestamp."""
        existing = self._by_id.get(key_id)
        if existing is None:
            return None
        return self._write(existing, revoked_at=existing.revoked_at or at)

    def touch(self, key_id: int, *, at: datetime) -> bool:
        """Record a use, unless one was recorded within the touch interval."""
        existing = self._by_id.get(key_id)
        if existing is None:
            return False
        if existing.last_used_at is not None and at - existing.last_used_at < self._touch_interval:
            return False
        self._write(existing, last_used_at=at)
        return True

    def _write(
        self,
        existing: ApiKeyRecord,
        *,
        revoked_at: datetime | None = None,
        last_used_at: datetime | None = None,
    ) -> ApiKeyRecord:
        """Replace a record with a copy carrying the changed fields."""
        updated = ApiKeyRecord(
            id=existing.id,
            name=existing.name,
            owner=existing.owner,
            scopes=existing.scopes,
            digest=existing.digest,
            created_at=existing.created_at,
            revoked_at=existing.revoked_at if revoked_at is None else revoked_at,
            last_used_at=existing.last_used_at if last_used_at is None else last_used_at,
        )
        self._by_id[existing.id] = updated
        return updated

    def erase_owner(self, owner: str, *, replacement: str) -> int:
        """Remove the keys belonging to a subject being erased (T-314, R-37).

        **This is not the revocation path.** Revocation sets ``revoked_at`` and
        keeps the row, because the row is the record of a credential having
        existed (D-043). Erasure is a different request with a different answer:
        the rows go, because the *owner identifier* on them is the subject's data
        and the requirement is that it stops existing. The schema already takes
        this position -- ``api_keys.owner_id`` cascades from ``users``
        ``ON DELETE CASCADE`` -- and this models that cascade for the in-memory
        store. Records with no owner left to erase are returned untouched.
        """
        affected = 0
        for key_id, record in list(self._by_id.items()):
            if record.owner != owner:
                continue
            if replacement:
                # A caller that wants the row kept and the identifier gone says so
                # by passing the tombstone; an empty string means delete outright.
                self._by_id[key_id] = ApiKeyRecord(
                    id=record.id,
                    name=record.name,
                    owner=replacement,
                    scopes=record.scopes,
                    digest=record.digest,
                    created_at=record.created_at,
                    revoked_at=record.revoked_at or record.created_at,
                    last_used_at=record.last_used_at,
                )
            else:
                del self._by_id[key_id]
            affected += 1
        return affected

    def __len__(self) -> int:
        """How many keys exist, revoked ones included."""
        return len(self._by_id)


def issue_key(
    store: ApiKeyStore,
    digest: KeyDigest,
    *,
    name: str,
    owner: str,
    scopes: frozenset[Scope],
    at: datetime,
) -> IssuedKey:
    """Mint a key, store its digest and return the plaintext once.

    Args:
        store: where the record goes; it assigns the id.
        digest: the digest function for the deployment's application secret.
        name: what the operator will call it.
        owner: the principal it belongs to.
        scopes: what it may do. Required and non-empty -- see :class:`Scope`.
        at: creation time, timezone-aware.

    Returns:
        The stored record and the plaintext key, which exists in this return
        value and in no store anywhere.

    Raises:
        ValueError: if the name, owner, scopes or timestamp cannot make a record.
    """
    secret = generate_secret()

    def build(key_id: int) -> ApiKeyRecord:
        """The record for an assigned id: the digest covers the whole key string."""
        return ApiKeyRecord(
            id=key_id,
            name=name,
            owner=owner,
            scopes=scopes,
            digest=digest.digest(format_key(key_id, secret)),
            created_at=at,
        )

    record = store.create(build)
    return IssuedKey(record=record, secret=format_key(record.id, secret))


def verify_key(
    store: ApiKeyStore,
    digest: KeyDigest,
    presented: str,
    *,
    at: datetime,
) -> ApiKeyRecord | None:
    """Resolve a presented key to a live record, or ``None``.

    Args:
        store: where the records are.
        digest: the digest function for this deployment.
        presented: the key string as it arrived.
        at: the current time, used to stamp a use.

    Returns:
        The record when the key is genuinely issued and not revoked, else
        ``None``. The caller turns ``None`` into a 401 and must not tell the two
        failures apart: "no such key" and "wrong secret" are the same fact to a
        caller who is not entitled to either.

    Raises:
        InvalidKeyFormat: if the string is not shaped like a key at all.
    """
    parsed = parse_key(presented)
    record = store.get(parsed.key_id)
    if not digest.matches(presented, record.digest if record is not None else None):
        return None
    if record is None or not record.active:
        # A revoked key fails here, on the request that presents it, with no
        # cache in between -- "revoked immediately" is the acceptance criterion.
        return None
    store.touch(record.id, at=at)
    return store.get(record.id) or record


def revoke_key(store: ApiKeyStore, key_id: int, *, at: datetime) -> ApiKeyRecord | None:
    """Revoke a key, reporting whether it was already revoked.

    Returns the record, whose ``revoked_at`` is the *first* revocation: revoking
    twice does not move the timestamp, because the question it answers is when
    the credential stopped working, not when someone last clicked.
    """
    return store.revoke(key_id, at=at)


def api_key_insert(record: ApiKeyRecord, *, owner_id: int) -> Insert:
    """The INSERT the persistent store runs for a new key.

    Args:
        record: the key, whose ``digest`` is the only trace of the secret.
        owner_id: the numeric ``users.id`` behind the owner string.

    Returns:
        An ``INSERT`` naming every column :func:`issue_key` fills. The plaintext
        is not a parameter and has no column to go in.
    """
    return insert(ApiKey).values(
        owner_id=owner_id,
        name=record.name,
        key_hash=record.digest,
        scopes=sorted(scope.value for scope in record.scopes),
        last_used_at=record.last_used_at,
        revoked_at=record.revoked_at,
    )


def api_key_select(*, owner_id: int | None = None, include_revoked: bool = True) -> Select[ApiKey]:
    """The SELECT the persistent store runs for a listing or a lookup.

    A revoked key is returned by default: the admin screen shows what happened to
    it, and verification needs the row to *know* it was revoked rather than to be
    unable to find it.
    """
    statement = select(ApiKey)
    if owner_id is not None:
        statement = statement.where(ApiKey.owner_id == owner_id)
    if not include_revoked:
        statement = statement.where(ApiKey.revoked_at.is_(None))
    return statement.order_by(ApiKey.id)


def api_key_revoke(key_id: int, *, at: datetime) -> Update:
    """The UPDATE that revokes a key.

    The ``revoked_at IS NULL`` guard is what makes revocation idempotent without
    a read: a second call matches no row and leaves the original timestamp alone.
    """
    return (
        update(ApiKey).where(ApiKey.id == key_id, ApiKey.revoked_at.is_(None)).values(revoked_at=at)
    )


def api_key_touch(
    key_id: int,
    *,
    at: datetime,
    interval_seconds: int = DEFAULT_TOUCH_INTERVAL_SECONDS,
) -> Update:
    """The UPDATE that stamps a use, at most once per interval.

    The interval test lives in the WHERE clause rather than in application code,
    so there is no read-modify-write race when several ingest requests for one key
    arrive at once -- and no write at all for the second and later requests inside
    the window.
    """
    if interval_seconds < 0:
        raise ValueError(f"interval_seconds must not be negative, got {interval_seconds}")
    cutoff = at - timedelta(seconds=interval_seconds)
    return (
        update(ApiKey)
        .where(
            ApiKey.id == key_id,
            sql_or(ApiKey.last_used_at.is_(None), ApiKey.last_used_at < cutoff),
        )
        .values(last_used_at=at)
    )


# --- the admin surface's view of a key ---------------------------------------


def scopes_from_names(names: Sequence[str]) -> frozenset[Scope]:
    """Parse scope names, refusing anything outside :class:`Scope`.

    Raises:
        ValueError: naming the offending value. An unknown scope is refused and
            never ignored: accepting a typo would issue a key that is quietly
            narrower than the operator asked for, and the collector's first
            request would fail with no clue why.
    """
    parsed: set[Scope] = set()
    for name in names:
        try:
            parsed.add(Scope(name.strip()))
        except ValueError as exc:
            allowed = ", ".join(sorted(scope.value for scope in Scope))
            msg = f"unknown scope {name!r}; allowed scopes are: {allowed}"
            raise ValueError(msg) from exc
    return frozenset(parsed)
