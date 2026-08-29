"""In-process pub/sub for live alert delivery + Phase 58 Redis EventBus.

Scope, stated plainly: default is in-process bus. When REDIS_EVENTBUS_ENABLED=true
and REDIS_URL set, publish also goes to Redis channel `noctra:events` so multiple
workers can receive. Subscriber side still uses in-process queue; a background
task would be needed to subscribe to Redis and re-publish locally (honest gap
documented in ha_status). For now, publish to both local and Redis.

Phase 58 honest notes:
- Without Redis, multi-worker fan-out is per-process only.
- With Redis, publish is cross-worker but subscribe still local; full cross-worker
  SSE requires a Redis listener loop per worker (future).
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

_LOGGER = logging.getLogger(__name__)


@dataclass(eq=False)  # identity-keyed: two streams for one user are distinct
class Subscriber:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue
    org_id: int | None
    dropped: int = 0

    def deliver(self, event: dict[str, Any]) -> None:
        """Runs on the subscriber's loop."""
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            self.dropped += 1


def _deliver(sub: Subscriber, event: dict[str, Any]) -> None:
    sub.deliver(event)


class EventBus:
    def __init__(self, queue_size: int = 100):
        self.queue_size = queue_size
        self._subscribers: set[Subscriber] = set()

    def subscribe(self, org_id: int | None = None, queue_size: int | None = None) -> Subscriber:
        sub = Subscriber(
            loop=asyncio.get_running_loop(),
            queue=asyncio.Queue(maxsize=queue_size or self.queue_size),
            org_id=org_id,
        )
        self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        self._subscribers.discard(sub)

    def publish(self, event: dict[str, Any]) -> int:
        """Thread-safe. Returns number of subscriber loops notified.
        Phase 58: if REDIS_EVENTBUS_ENABLED, also publish to Redis.
        """
        delivered = 0
        for sub in list(self._subscribers):
            if sub.org_id is not None and event.get("org_id") not in (None, sub.org_id):
                continue
            try:
                sub.loop.call_soon_threadsafe(_deliver, sub, event)
                delivered += 1
            except RuntimeError:
                # loop closed
                self._subscribers.discard(sub)

        # Phase 58: Redis fan-out
        try:
            from app.core.config import settings

            if getattr(settings, "REDIS_EVENTBUS_ENABLED", False) and getattr(settings, "REDIS_URL", None):
                try:
                    import redis as _redis

                    r = _redis.from_url(settings.REDIS_URL, decode_responses=False)
                    # Serialize with default str for datetime
                    payload = json.dumps(event, default=str).encode("utf-8")
                    r.publish("noctra:events", payload)
                    r.close()
                except Exception as exc:
                    _LOGGER.debug("Redis EventBus publish failed: %s", exc)
        except Exception:
            pass

        return delivered

    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def reset(self) -> None:
        self._subscribers.clear()


@dataclass
class _Ticket:
    org_id: int | None
    expires_at: float


class TicketStore:
    def __init__(self, ttl_seconds: int = 30, max_tickets: int = 1000):
        self.ttl_seconds = ttl_seconds
        self.max_tickets = max_tickets
        self._tickets: dict[str, _Ticket] = {}

    def _prune(self) -> None:
        now = time.monotonic()
        expired = [k for k, v in self._tickets.items() if v.expires_at <= now]
        for k in expired:
            self._tickets.pop(k, None)

    def issue(self, org_id: int | None) -> str:
        self._prune()
        if len(self._tickets) >= self.max_tickets:
            # drop oldest 20%
            oldest = sorted(self._tickets.items(), key=lambda kv: kv[1].expires_at)[: max(1, self.max_tickets // 5)]
            for k, _ in oldest:
                self._tickets.pop(k, None)
        token = secrets.token_urlsafe(32)
        self._tickets[token] = _Ticket(org_id=org_id, expires_at=time.monotonic() + self.ttl_seconds)
        return token

    def redeem(self, token: str) -> int | None:
        self._prune()
        ticket = self._tickets.pop(token, None)  # single-use
        if not ticket:
            return None
        if ticket.expires_at <= time.monotonic():
            return None
        return ticket.org_id

    def reset(self) -> None:
        self._tickets.clear()

    def count(self) -> int:
        self._prune()
        return len(self._tickets)


# Module singletons
bus = EventBus()
tickets = TicketStore()


def alert_event_from_row(alert) -> dict[str, Any]:
    """Build a compact alert payload from a SecurityAlert row (duck-typed, no model import)."""
    return {
        "type": "alert",
        "id": getattr(alert, "id", None),
        "source": getattr(alert, "source", None),
        "source_ip": getattr(alert, "source_ip", None),
        "severity": getattr(alert, "severity", None),
        "score": getattr(alert, "score", None),
        "message": getattr(alert, "message", None),
        "mitre_tactic": getattr(alert, "mitre_tactic", None),
        "mitre_technique_id": getattr(alert, "mitre_technique_id", None),
        "mitre_technique": getattr(alert, "mitre_technique", None),
        "created_at": getattr(alert, "created_at", None).isoformat() if getattr(alert, "created_at", None) else None,
        "org_id": getattr(alert, "org_id", None),
    }
