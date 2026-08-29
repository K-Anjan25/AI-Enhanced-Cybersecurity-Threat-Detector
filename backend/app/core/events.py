"""In-process pub/sub for live alert delivery.

Scope, stated plainly: this is a bus inside one API process. Events published
here reach subscribers connected to THIS process only. Run several uvicorn
workers and a browser connected to worker A will not see an event ingested by
worker B. That is fine for the single-process demo and for one worker; a
multi-worker deployment needs Redis pub/sub or a broker. The dashboard's
EventSource reconnects on its own, and every reconnect re-fetches, so a
restart or a lost event is visible rather than silent.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import Any


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
        """Thread-safe. Returns number of subscriber loops notified."""
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
