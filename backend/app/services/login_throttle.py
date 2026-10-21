"""Login throttling: a failed-password counter shared across replicas.

Credential abuse (threat family T4) needs a limit per account and per source address.
An in-process counter is not enough once the backend runs more than one replica: each
pod would allow its own N guesses, so the effective limit is N times the replica
count. This module keeps the counters in Redis when ``AEGIS_REDIS_URL`` is set, so
every replica shares one count.

Design choices, each deliberate:

* **Fixed windows with an expiry on the key.** A failure does ``INCR`` and, on the first
  one, ``EXPIRE`` for the window length. Redis then forgets the counter by itself and
  the store never grows without bound, which matters on a small host.
* **Two keys per attempt.** One for the account (stops a password-guessing run against
  one user) and one for the source address (stops one host spraying many accounts).
  The address limit is larger, because many users can sit behind one NAT address.
* **Degrade, do not fail closed.** If Redis is unreachable the throttle falls back to
  a bounded in-process counter and records the error. Failing closed would lock every
  administrator out of the dashboard whenever the cache restarts; failing open with no
  limit would be worse. The fallback still enforces the limit per replica.
* **Successful sign-in clears the account counter**, so a legitimate user who mistyped
  a few times is not locked out after the next correct password.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Protocol

__all__ = [
    "LoginDecision",
    "LoginThrottle",
    "LocalWindowCounter",
    "RedisWindowCounter",
    "ThrottleSettings",
]

#: Upper bound on distinct keys held by the in-process fallback. Eviction drops the
#: least recently touched key, so an attacker cycling addresses cannot grow memory.
_LOCAL_MAX_KEYS = 10_000


@dataclass(frozen=True)
class ThrottleSettings:
    """How many failures are allowed, and over what window."""

    account_max_failures: int = 5
    address_max_failures: int = 100
    window_seconds: int = 900

    def __post_init__(self) -> None:
        """Reject limits that would lock everyone out or disable the check."""
        if self.account_max_failures < 1 or self.address_max_failures < 1:
            raise ValueError("login failure limits must be at least 1")
        if self.window_seconds < 1:
            raise ValueError("login failure window must be at least 1 second")


@dataclass(frozen=True)
class LoginDecision:
    """Whether a sign-in attempt may proceed, and how long to wait if not."""

    allowed: bool
    retry_after_seconds: int = 0


class WindowCounter(Protocol):
    """Counts events per key inside a fixed time window."""

    def count(self, key: str) -> int:
        """Return the failures recorded for ``key`` in its current window."""
        ...

    def add(self, key: str, window_seconds: int) -> int:
        """Record one failure for ``key`` and return the new count."""
        ...

    def clear(self, key: str) -> None:
        """Forget ``key`` (used after a successful sign-in)."""
        ...

    def ttl(self, key: str) -> int:
        """Seconds until ``key`` expires, or 0 if it has none."""
        ...


class LocalWindowCounter:
    """Bounded in-process counter used when Redis is absent or unreachable."""

    def __init__(self, max_keys: int = _LOCAL_MAX_KEYS) -> None:
        """Create an empty counter that holds at most ``max_keys`` keys."""
        self._max_keys = max_keys
        self._entries: OrderedDict[str, tuple[int, float]] = OrderedDict()
        self._lock = Lock()

    def _live(self, key: str, now: float) -> tuple[int, float] | None:
        entry = self._entries.get(key)
        if entry is None or entry[1] <= now:
            self._entries.pop(key, None)
            return None
        return entry

    def count(self, key: str) -> int:
        """Return the live count for ``key``, or 0 once its window has passed."""
        with self._lock:
            entry = self._live(key, time.monotonic())
            return entry[0] if entry else 0

    def add(self, key: str, window_seconds: int) -> int:
        """Record one failure. The window starts at the first failure."""
        now = time.monotonic()
        with self._lock:
            entry = self._live(key, now)
            if entry is None:
                entry = (0, now + window_seconds)
            entry = (entry[0] + 1, entry[1])
            self._entries[key] = entry
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_keys:
                self._entries.popitem(last=False)
            return entry[0]

    def clear(self, key: str) -> None:
        """Drop ``key`` so its next failure starts a fresh window."""
        with self._lock:
            self._entries.pop(key, None)

    def ttl(self, key: str) -> int:
        """Seconds left in ``key``'s window, rounded up."""
        with self._lock:
            entry = self._live(key, time.monotonic())
            if entry is None:
                return 0
            return max(1, int(entry[1] - time.monotonic() + 0.999))


class RedisWindowCounter:
    """Shared counter in Redis. ``INCR`` is atomic, so replicas never race a count."""

    def __init__(self, client: object, prefix: str = "aegis:login") -> None:
        """Wrap a redis-py client (or a compatible fake) under a key ``prefix``."""
        self._client = client
        self._prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def count(self, key: str) -> int:
        """Return the shared count for ``key`` (0 if expired or never set)."""
        value = self._client.get(self._key(key))  # type: ignore[attr-defined]
        return int(value) if value is not None else 0

    def add(self, key: str, window_seconds: int) -> int:
        """Increment the shared count, starting the window on the first failure."""
        full = self._key(key)
        pipe = self._client.pipeline()  # type: ignore[attr-defined]
        pipe.incr(full)
        pipe.expire(full, window_seconds, nx=True)
        value, _ = pipe.execute()
        return int(value)

    def clear(self, key: str) -> None:
        """Delete the shared count for ``key``."""
        self._client.delete(self._key(key))  # type: ignore[attr-defined]

    def ttl(self, key: str) -> int:
        """Seconds until the shared count expires, or 0 when it has no expiry."""
        remaining = int(self._client.ttl(self._key(key)))  # type: ignore[attr-defined]
        return remaining if remaining > 0 else 0


class LoginThrottle:
    """Decide whether a sign-in may proceed, and record its outcome.

    Holds a primary counter (Redis when configured) and always a local fallback, so a
    Redis outage changes the scope of the limit, not whether it exists.
    """

    def __init__(
        self,
        settings: ThrottleSettings,
        primary: WindowCounter | None = None,
    ) -> None:
        """Build a throttle over ``primary`` with the local fallback always present."""
        self._settings = settings
        self._primary = primary
        self._fallback = LocalWindowCounter()
        self.backend_errors = 0

    @property
    def settings(self) -> ThrottleSettings:
        """The limits in force."""
        return self._settings

    @property
    def shared(self) -> bool:
        """True when a shared (cross-replica) counter is configured."""
        return self._primary is not None

    def _counter(self) -> WindowCounter:
        """Return the shared counter, or the fallback if it is not configured."""
        return self._primary if self._primary is not None else self._fallback

    def _call(self, op: str, key: str, *args: int) -> int:
        """Run a counter call; on a backend error, fall back and count the error."""
        counter = self._counter()
        try:
            return int(getattr(counter, op)(key, *args))
        except Exception:
            if counter is self._fallback:
                raise
            self.backend_errors += 1
            return int(getattr(self._fallback, op)(key, *args))

    @staticmethod
    def _account_key(email: str) -> str:
        return f"acct:{email}"

    @staticmethod
    def _address_key(address: str) -> str:
        return f"ip:{address}"

    def check(self, email: str, address: str) -> LoginDecision:
        """Refuse the attempt when the account or the address is over its limit."""
        account_key = self._account_key(email)
        address_key = self._address_key(address)
        account_failures = self._call("count", account_key)
        address_failures = self._call("count", address_key)
        if account_failures >= self._settings.account_max_failures:
            return LoginDecision(False, self._retry_after(account_key))
        if address_failures >= self._settings.address_max_failures:
            return LoginDecision(False, self._retry_after(address_key))
        return LoginDecision(True)

    def _retry_after(self, key: str) -> int:
        remaining = self._call("ttl", key)
        return remaining if remaining > 0 else self._settings.window_seconds

    def record_failure(self, email: str, address: str) -> None:
        """Count one failed password for the account and the address."""
        window = self._settings.window_seconds
        self._call("add", self._account_key(email), window)
        self._call("add", self._address_key(address), window)

    def record_success(self, email: str) -> None:
        """A correct password clears the account's failures (not the address's)."""
        counter = self._counter()
        try:
            counter.clear(self._account_key(email))
        except Exception:
            if counter is self._fallback:
                raise
            self.backend_errors += 1
        self._fallback.clear(self._account_key(email))


def build_login_throttle(settings: ThrottleSettings, redis_url: str = "") -> LoginThrottle:
    """Build the throttle, using Redis when a URL is configured and the client imports.

    An unreachable or missing Redis does not stop the process: the throttle still runs
    on its local fallback, and ``backend_errors`` shows the degradation. A missing
    ``redis`` package is reported in the same way, so a misconfigured image is visible.
    """
    if not redis_url:
        return LoginThrottle(settings)
    try:
        import redis  # type: ignore[import-not-found]
    except ImportError:
        return LoginThrottle(settings)
    client = redis.Redis.from_url(redis_url, socket_timeout=0.5, socket_connect_timeout=0.5)
    return LoginThrottle(settings, primary=RedisWindowCounter(client))
