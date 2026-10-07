"""Rate limiting, request size caps and admission control (R-56, T-316).

The policy lives here, purely: no ASGI, no FastAPI, no clocks of its own. The
middleware that applies it is in ``app/api/middleware.py``, and the split is what
makes every rule below testable with an injected clock and a couple of integers.

**R-56 is a coverage rule, not a feature.** "Rate limiting on every unauthenticated
and every write endpoint" means the *set of endpoints in scope* is the thing to get
right: a limiter that protects the ingest routes and forgets ``/readyz``, or that
misses the next write endpoint somebody adds, satisfies the feature and fails the
rule. So the classification is written out (:data:`WRITE_METHODS` and
:data:`LIMITED_UNAUTHENTICATED_ROUTES`) rather than derived from the request, and a
test walks the live application and compares the two -- the same table-plus-walk
shape T-312 used for the audit trail. :data:`EXEMPT_ROUTES` is empty and its
emptiness is asserted, because an exemption is exactly how a coverage rule rots.

**Identity is a fingerprint, never a credential.** A bucket is keyed by a keyed
digest of the presented credential under its own HKDF purpose, so the limiter never
holds or logs a raw key or token (R-58), and two purposes cannot be cross-matched
because the digest key is derived separately from the api-key digest key. A request
with no credential is bucketed by client address, which is the flood R-56 names.

**Buckets are bounded in number as well as in rate.** An attacker rotating
credentials would otherwise create one bucket per request and turn a defence into a
memory leak, so idle buckets are pruned. The token bucket itself is refilled by
elapsed time, not by a timer: no background task exists to fail quietly.

**Back-pressure is explicit or it is not back-pressure.** :class:`AdmissionController`
bounds how many records may be in flight at once and *refuses* rather than queueing
without limit; the caller answers 503 with ``Retry-After``. A silent drop would look
like success to the client, which is the failure architecture.md §12 names.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

__all__ = [
    "BUCKET_TTL_SECONDS",
    "DEFAULT_CREDENTIAL_PER_MINUTE",
    "DEFAULT_ANONYMOUS_PER_MINUTE",
    "EXEMPT_ROUTES",
    "LIMITED_UNAUTHENTICATED_ROUTES",
    "MAX_TRACKED_IDENTITIES",
    "WRITE_METHODS",
    "AdmissionController",
    "RateLimitDecision",
    "RateLimitPolicy",
    "TokenBucket",
    "fingerprint",
]

#: Method set R-56 covers. Written out rather than derived from one of the other
#: tables in the codebase, so a new write method is an explicit decision.
WRITE_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: The unauthenticated endpoints R-56 covers: liveness, readiness, the public
#: credential-exchange/bootstrap routes, and the framework's own documentation
#: routes when they are mounted (development only).
#: A test asserts this equals ``UNAUTHENTICATED_ROUTES | DOC_ROUTES`` from
#: ``app.auth.rbac``, so the two cannot drift; it is written as literals here
#: because ``app.services`` must not import from the HTTP layer.
LIMITED_UNAUTHENTICATED_ROUTES: frozenset[str] = frozenset(
    {
        "/healthz",
        "/readyz",
        "/metrics",
        "/api/v1/auth/status",
        "/api/v1/auth/setup",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }
)

#: Routes deliberately outside R-56. Empty, and asserted empty: an exemption is how
#: a coverage rule stops being one. A route that must be exempt needs a decision
#: recorded in memory.md first.
EXEMPT_ROUTES: frozenset[tuple[str, str]] = frozenset()

#: Requests per minute allowed for one credential (an API key or a user token).
#: Ten per second sustained, which is far above a collector's rate and far below
#: what it takes to make the service work at refusing.
DEFAULT_CREDENTIAL_PER_MINUTE = 600

#: Requests per minute allowed from one client address when no credential is
#: presented. Lower, because this is the unauthenticated flood R-56 names.
DEFAULT_ANONYMOUS_PER_MINUTE = 120

#: Idle buckets are pruned after this long, and the table is capped, so rotating
#: identities cannot make the limiter a memory leak.
BUCKET_TTL_SECONDS = 600.0
MAX_TRACKED_IDENTITIES = 50_000

#: HKDF purpose for the fingerprint. Distinct from the api-key digest's purpose so
#: the two cannot be cross-matched.
_FINGERPRINT_INFO = b"rate-limit-fingerprint"


def fingerprint(secret: str, presented: str) -> str:
    """A stable, non-reversible name for one presented credential.

    Keyed per deployment, like the api-key digest and for the same reason: a stolen
    table of fingerprints is not a table of credentials [D-042]. The purpose string
    differs from the digest's, so a fingerprint cannot be compared with a stored
    key digest even if both were leaked.

    Args:
        secret: the application secret (``AEGIS_SECRET_KEY``).
        presented: the raw credential. It is not stored, logged or returned.
    """
    if len(secret) < 32:
        msg = "the application secret must be at least 32 characters to derive a fingerprint key"
        raise ValueError(msg)
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"aegis.ratelimit.fingerprint.v1",
        info=_FINGERPRINT_INFO,
    ).derive(secret.encode())
    return hmac.new(key, presented.encode(), hashlib.sha256).hexdigest()


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """The answer for one request.

    Attributes:
        allowed: whether it may proceed.
        retry_after: whole seconds to wait, at least 1 when refused and 0 when
            allowed. Whole seconds because that is what ``Retry-After`` carries.
        remaining: tokens left in the bucket after this decision.
    """

    allowed: bool
    retry_after: int
    remaining: int


class TokenBucket:
    """A token bucket refilled by elapsed time.

    Capacity and refill rate are the same number of requests per minute, so a
    client that has been idle may burst its full minute's allowance and one that has
    been hammering gets the same long-run rate. Time is passed in rather than read,
    so a test can move a bucket's clock by an hour in one line.
    """

    __slots__ = ("_capacity", "_per_second", "_tokens", "_updated")

    def __init__(self, per_minute: int, *, now: float) -> None:
        """Start full, so a fresh client is not throttled before it has done anything."""
        if per_minute < 1:
            msg = f"a rate limit must allow at least one request per minute, got {per_minute}"
            raise ValueError(msg)
        self._capacity = float(per_minute)
        self._per_second = per_minute / 60.0
        self._tokens = float(per_minute)
        self._updated = now

    def _refill(self, now: float) -> None:
        """Add the tokens elapsed time has earned, capped at capacity."""
        elapsed = max(0.0, now - self._updated)
        self._updated = max(self._updated, now)
        self._tokens = min(self._capacity, self._tokens + elapsed * self._per_second)

    @property
    def last_seen(self) -> float:
        """The last time this bucket was consulted, for idle pruning."""
        return self._updated

    def take(self, *, now: float) -> RateLimitDecision:
        """Consume one token if there is one.

        A refused request consumes nothing -- it could not -- so a client that keeps
        retrying inside the window neither extends its own wait nor is punished for
        the retry beyond the wait it was told to take.
        """
        self._refill(now)
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return RateLimitDecision(allowed=True, retry_after=0, remaining=int(self._tokens))
        deficit = 1.0 - self._tokens
        # Round up: telling a client to retry in zero seconds would be a lie, and
        # truncating would make every refusal a promise the client can disprove.
        wait = max(1, math.ceil(deficit / self._per_second))
        return RateLimitDecision(allowed=False, retry_after=wait, remaining=0)


class RateLimitPolicy:
    """Which requests are limited, by whose identity, and how much.

    One bucket per identity, and an identity is either a credential fingerprint or,
    for a request with no credential, the client address. A request that presents a
    credential is judged by that credential's bucket alone: the limit belongs to the
    account or the key, and a shared office address should not make two operators
    compete for one bucket.
    """

    __slots__ = ("_anonymous_per_minute", "_buckets", "_credential_per_minute", "_secret")

    def __init__(
        self,
        *,
        credential_per_minute: int = DEFAULT_CREDENTIAL_PER_MINUTE,
        anonymous_per_minute: int = DEFAULT_ANONYMOUS_PER_MINUTE,
        secret: str,
    ) -> None:
        """Build a policy. Both limits must allow at least one request per minute."""
        self._credential_per_minute = credential_per_minute
        self._anonymous_per_minute = anonymous_per_minute
        self._secret = secret
        self._buckets: dict[str, TokenBucket] = {}
        # Fail at construction rather than at the first refusal: a zero limit would
        # read as "everything is limited" and a negative one as "nothing is".
        TokenBucket(credential_per_minute, now=0.0)
        TokenBucket(anonymous_per_minute, now=0.0)

    def is_limited(self, method: str, path: str) -> bool:
        """Whether R-56 puts this request in scope.

        Every write method, and every unauthenticated route whatever its method.
        Reads that need a credential are out of scope: they are cheap, they already
        require a token, and a long-lived stream -- the alert SSE and WebSocket
        routes -- must not be counted as traffic while it stays open.
        """
        if (method.upper(), path) in EXEMPT_ROUTES:
            return False
        return method.upper() in WRITE_METHODS or path in LIMITED_UNAUTHENTICATED_ROUTES

    def identity(self, *, credential: str | None, client_ip: str | None) -> str:
        """The bucket this request belongs to.

        The credential wins when one is presented; otherwise the client address. An
        address-less, credential-less request (a test client, an in-process call)
        shares one bucket rather than escaping the limit.
        """
        if credential:
            return fingerprint(self._secret, f"credential:{credential}")
        return f"address:{client_ip or 'unknown'}"

    def check(
        self,
        *,
        method: str,
        path: str,
        credential: str | None,
        client_ip: str | None,
        now: float | None = None,
    ) -> RateLimitDecision:
        """Take a token for this request if it is in scope.

        An out-of-scope request is allowed without touching a bucket, so reads do not
        consume a write allowance.
        """
        if not self.is_limited(method, path):
            return RateLimitDecision(allowed=True, retry_after=0, remaining=0)
        when = time.monotonic() if now is None else now
        identity = self.identity(credential=credential, client_ip=client_ip)
        bucket = self._buckets.get(identity)
        if bucket is None:
            self._prune(when)
            rate = self._credential_per_minute if credential else self._anonymous_per_minute
            bucket = TokenBucket(rate, now=when)
            self._buckets[identity] = bucket
        return bucket.take(now=when)

    def _prune(self, now: float) -> None:
        """Drop buckets that have been idle past their TTL, then enforce the cap.

        Called only when a new identity arrives, which is the only moment the table
        can grow. A bucket idle for the TTL is full again anyway, so dropping it
        loses no state a client can observe.
        """
        idle = [
            name
            for name, bucket in self._buckets.items()
            if now - bucket.last_seen > BUCKET_TTL_SECONDS
        ]
        for name in idle:
            del self._buckets[name]
        while len(self._buckets) >= MAX_TRACKED_IDENTITIES:
            oldest = min(self._buckets.items(), key=lambda item: item[1].last_seen)[0]
            del self._buckets[oldest]

    @property
    def tracked(self) -> int:
        """How many identities hold a bucket. Exposed so the cap can be asserted."""
        return len(self._buckets)


class AdmissionController:
    """A bounded in-flight budget, refusing explicitly when it is full.

    The unit is records, not requests, because a batch is one request carrying up to
    a thousand records and the buffer that matters downstream holds records. Until
    the producer exists [D-039] the budget is held for the duration of the request;
    when a producer is wired it is released on delivery instead, and that is the
    decision the wiring will have to make.
    """

    __slots__ = ("_capacity", "_in_flight")

    def __init__(self, capacity: int) -> None:
        """Build a controller with a hard ceiling on records in flight."""
        if capacity < 1:
            msg = f"an admission capacity must hold at least one record, got {capacity}"
            raise ValueError(msg)
        self._capacity = capacity
        self._in_flight = 0

    @property
    def capacity(self) -> int:
        """The ceiling."""
        return self._capacity

    @property
    def backlog(self) -> int:
        """Records currently admitted and not yet released."""
        return self._in_flight

    def admit(self, records: int) -> bool:
        """Admit ``records`` if they fit, and report the answer without partial admission.

        All-or-nothing: a batch that does not fit is refused whole, because admitting
        the part that fits and then failing the request would be the silent partial
        write the audit trail exists to prevent.
        """
        if records < 0:
            msg = f"cannot admit a negative number of records: {records}"
            raise ValueError(msg)
        if self._in_flight + records > self._capacity:
            return False
        self._in_flight += records
        return True

    def release(self, records: int) -> None:
        """Return admitted records to the budget. Never goes below zero."""
        if records < 0:
            msg = f"cannot release a negative number of records: {records}"
            raise ValueError(msg)
        self._in_flight = max(0, self._in_flight - records)

    def retry_after(self) -> int:
        """A ``Retry-After`` to send with a refusal.

        One second: the budget is released as work completes, and guessing a longer
        wait from a backlog with no arrival-rate estimate would be a fabricated
        number. The client is told to retry, not told a lie about when.
        """
        return 1
