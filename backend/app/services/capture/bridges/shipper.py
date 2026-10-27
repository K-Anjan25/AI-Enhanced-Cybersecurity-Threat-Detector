"""Delivery of capture records to the AEGIS ingest API.

Shared by the Zeek, Suricata and tshark bridges. Each bridge is copied into its
container on its own (capture/Dockerfile.capture), so this module is copied beside
them and imported as a sibling.

What it does, and why each part is there:

* **Batches of up to 1,000 records per request.** The ingest API accepts at most
  ``MAX_FLOW_RECORDS`` (1,000) per request. The bridges used to post 100 at a time,
  which is ten times the round trips for the same records: the throughput ceiling
  the capture rate reports came from.
* **Bounded retry with jittered backoff** for transient failures: network errors,
  408, 425, 429 and 5xx. Full jitter stops every bridge retrying in lockstep after a
  backend restart. Other 4xx responses are not retried, because the same bytes would
  be refused again.
* **A spool on disk during an outage.** When retries are exhausted the batch is
  appended to a size-capped NDJSON file and drained, oldest first, before new records
  are sent. A backend restart therefore loses nothing up to the cap. The cap keeps a
  long outage from filling the host's disk; past it the newest records are dropped and
  counted, never silently.
* **Counters for every outcome** (sent, accepted, retried, spooled, drained, dropped,
  rejected), so a capture rate that looks low can be explained from the logs.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The ingest API's per-request cap (app/schemas/ingest.py, MAX_FLOW_RECORDS).
MAX_BATCH = 1000

#: HTTP statuses worth retrying: the request might succeed later.
TRANSIENT_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

#: The longest wait a server's Retry-After may impose. The ingest buffer answers 503
#: with a short hint; a larger value is treated as a misconfiguration, not obeyed.
MAX_RETRY_AFTER = 60.0


def parse_retry_after(value: str | None) -> float | None:
    """Seconds from a Retry-After header, or ``None`` when it is absent or not a number.

    HTTP-date values are not used by the ingest API, so anything that is not a
    plain non-negative number is ignored and the caller falls back to its backoff.
    """
    if value is None:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    if seconds != seconds or seconds < 0:  # NaN or negative
        return None
    return min(seconds, MAX_RETRY_AFTER)


class AuthRefused(Exception):
    """The API answered 401: the bearer token is missing or expired."""


class TransientFailure(Exception):
    """A failure that a later attempt may not repeat (network, 429, 5xx).

    ``retry_after`` carries the server's own wait when it sent one (503 from the
    ingest buffer does), so the shipper waits as the server asked rather than
    guessing with its backoff.
    """

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        """Carry the message and the server's ``Retry-After`` hint, if it sent one."""
        super().__init__(message)
        self.retry_after = retry_after


class Rejected(Exception):
    """The API refused these exact records (a non-retryable 4xx). Do not resend."""


@dataclass
class ShipStats:
    """Counts of what happened to every record handed to the shipper."""

    submitted: int = 0
    accepted: int = 0
    retried: int = 0
    spooled: int = 0
    drained: int = 0
    dropped: int = 0
    rejected: int = 0
    last_error: str = ""

    def as_dict(self) -> dict[str, int | str]:
        """Return the counters as a plain mapping, for logs and tests."""
        return {
            "submitted": self.submitted,
            "accepted": self.accepted,
            "retried": self.retried,
            "spooled": self.spooled,
            "drained": self.drained,
            "dropped": self.dropped,
            "rejected": self.rejected,
            "last_error": self.last_error,
        }


def post_ndjson(
    api_base: str,
    modality: str,
    records: list[dict[str, Any]],
    token: str,
    *,
    timeout: float = 10.0,
) -> int:
    """POST one batch and return the accepted count.

    Raises ``AuthRefused``, ``TransientFailure`` or ``Rejected`` so the caller decides
    what to do with the batch.
    """
    body = "\n".join(json.dumps(r) for r in records).encode()
    req = urllib.request.Request(  # noqa: S310 - api_base is operator-configured
        f"{api_base}/api/v1/ingest/{modality}",
        data=body,
        headers={"Content-Type": "application/x-ndjson", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310  # nosec B310
            payload = json.loads(resp.read())
            return int(payload.get("accepted", 0))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:200] if exc.fp else ""
        if exc.code == 401:
            raise AuthRefused(detail) from exc
        if exc.code in TRANSIENT_STATUSES:
            hint = parse_retry_after(exc.headers.get("Retry-After") if exc.headers else None)
            raise TransientFailure(f"HTTP {exc.code}: {detail}", retry_after=hint) from exc
        raise Rejected(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise TransientFailure(str(exc)) from exc
    except ValueError as exc:  # a malformed success body
        raise TransientFailure(f"unreadable ingest response: {exc}") from exc


class Spool:
    """Store-and-forward: NDJSON files on disk, one per modality, size-capped."""

    def __init__(self, directory: Path, max_bytes: int) -> None:
        """Create the spool directory. ``max_bytes`` caps each modality's file."""
        self._dir = directory
        self._max_bytes = max_bytes
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, modality: str) -> Path:
        return self._dir / f"{modality}.ndjson"

    def append(self, modality: str, records: list[dict[str, Any]]) -> tuple[int, int]:
        """Store records. Returns ``(stored, dropped)``; dropped is past the cap."""
        path = self._path(modality)
        current = path.stat().st_size if path.exists() else 0
        stored = 0
        with path.open("a", encoding="utf-8") as fh:
            for record in records:
                line = json.dumps(record) + "\n"
                size = len(line.encode())
                if current + size > self._max_bytes:
                    break
                fh.write(line)
                current += size
                stored += 1
        return stored, len(records) - stored

    def pending(self, modality: str) -> int:
        """How many records are waiting on disk for ``modality``."""
        path = self._path(modality)
        if not path.exists():
            return 0
        with path.open(encoding="utf-8") as fh:
            return sum(1 for _ in fh)

    def prepend(self, modality: str, records: list[dict[str, Any]]) -> None:
        """Put ``records`` back at the front, ahead of anything already stored."""
        path = self._path(modality)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            "".join(json.dumps(r) + "\n" for r in records) + existing,
            encoding="utf-8",
        )
        os.replace(tmp, path)

    def take(self, modality: str, limit: int) -> list[dict[str, Any]]:
        """Remove and return up to ``limit`` of the oldest stored records."""
        path = self._path(modality)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        head, rest = lines[:limit], lines[limit:]
        tmp = path.with_suffix(".tmp")
        tmp.write_text("".join(line + "\n" for line in rest), encoding="utf-8")
        os.replace(tmp, path)
        return [json.loads(line) for line in head if line]


class Shipper:
    """Send batches with retries, a disk spool, and counters.

    The caller supplies ``token`` (returns the current bearer token, or "") and
    ``reauthenticate`` (refreshes it and returns True on success). Both are injected so
    the bridges' own login code stays where it is, and tests can drive every branch.
    """

    def __init__(
        self,
        api_base: str,
        *,
        token: Callable[[], str],
        reauthenticate: Callable[[], bool],
        spool: Spool | None = None,
        attempts: int = 3,
        backoff_base: float = 0.5,
        backoff_cap: float = 8.0,
        sleep: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] = random.random,
        log: Callable[[str], None] | None = None,
    ) -> None:
        """Bind the shipper to one API base and its retry policy."""
        if attempts < 1:
            raise ValueError("attempts must be at least 1")
        self._api = api_base.rstrip("/")
        self._token = token
        self._reauth = reauthenticate
        self._spool = spool
        self._attempts = attempts
        self._base = backoff_base
        self._cap = backoff_cap
        self._sleep = sleep
        self._rng = rng
        self._log = log or (lambda msg: print(msg, file=sys.stderr))
        self.stats = ShipStats()

    def _backoff(self, attempt: int) -> float:
        """Full-jitter exponential backoff, capped."""
        ceiling = min(self._cap, self._base * (2**attempt))
        return float(self._rng() * ceiling)

    def _send_once(self, modality: str, batch: list[dict[str, Any]]) -> int:
        """One logical delivery: retries transient failures, re-logs in on 401 once."""
        refreshed = False
        for attempt in range(self._attempts):
            token = self._token()
            if not token:
                if not self._reauth():
                    raise TransientFailure("not authenticated")
                continue
            try:
                return post_ndjson(self._api, modality, batch, token)
            except AuthRefused:
                if refreshed or not self._reauth():
                    raise
                refreshed = True
                self._log("[SHIP] token refused; signed in again and retrying the batch")
            except TransientFailure as exc:
                self.stats.last_error = str(exc)[:200]
                if attempt + 1 >= self._attempts:
                    raise
                self.stats.retried += 1
                self._sleep(
                    exc.retry_after if exc.retry_after is not None else self._backoff(attempt)
                )
        raise TransientFailure("retries exhausted")

    def send(self, records: Iterable[dict[str, Any]], modality: str = "flows") -> int:
        """Deliver records in batches. Returns the number the API accepted.

        Anything not delivered is spooled when a spool is configured, or dropped and
        counted when it is not. Records the API rejects outright are counted as
        ``rejected`` and never retried.
        """
        pending = list(records)
        self.stats.submitted += len(pending)
        if self._spool is not None:
            self._drain(modality)
        accepted = 0
        for start in range(0, len(pending), MAX_BATCH):
            batch = pending[start : start + MAX_BATCH]
            try:
                got = self._send_once(modality, batch)
            except Rejected as exc:
                self.stats.rejected += len(batch)
                self.stats.last_error = str(exc)[:200]
                self._log(f"[SHIP] {len(batch)} {modality} rejected: {exc}")
                continue
            except (TransientFailure, AuthRefused) as exc:
                self._keep(modality, batch, str(exc))
                continue
            accepted += got
            self.stats.accepted += got
        return accepted

    def _keep(self, modality: str, batch: list[dict[str, Any]], reason: str) -> None:
        """Hand a batch that could not be sent to the spool, or count it dropped."""
        self._log(f"[SHIP] {len(batch)} {modality} not sent ({reason}); keeping them")
        if self._spool is None:
            self.stats.dropped += len(batch)
            return
        stored, dropped = self._spool.append(modality, batch)
        self.stats.spooled += stored
        self.stats.dropped += dropped
        if dropped:
            self._log(f"[SHIP] spool full: dropped {dropped} {modality} records")

    def _drain(self, modality: str) -> None:
        """Send spooled records, oldest first, before new ones. Stops at first failure."""
        spool = self._spool
        if spool is None:  # no spool configured: nothing is ever stored, so nothing to drain
            return
        while spool.pending(modality):
            batch = spool.take(modality, MAX_BATCH)
            try:
                self._send_once(modality, batch)
            except Rejected as exc:
                self.stats.rejected += len(batch)
                self.stats.last_error = str(exc)[:200]
                continue
            except (TransientFailure, AuthRefused) as exc:
                # Put the batch back at the front: it is still the oldest data.
                spool.prepend(modality, batch)
                self.stats.last_error = str(exc)[:200]
                return
            self.stats.drained += len(batch)
            self.stats.accepted += len(batch)
