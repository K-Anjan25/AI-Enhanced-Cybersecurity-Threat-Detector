"""The alert stream: sequenced notifications, with the gap made visible (T-310).

FR-20 pushes new alerts to the dashboard over a WebSocket with a REST/SSE
fallback. The acceptance criterion is that killing the socket mid-stream
triggers the fallback and that **no alert is lost across the switch**, so this
module is built around one idea: every notification carries a sequence number,
and a client that reconnects says where it got to.

Four decisions carry the criterion.

**The stream is not the system of record, and it says so.** The `alerts` table is
the record; this hub holds a bounded window of recent notifications so a client
that missed a minute can be brought up to date without re-querying. When a
client's cursor has fallen out of that window the hub does not quietly skip the
missing alerts: it reports ``resync_required`` and hands over whatever it still
has. A gap that is announced can be repaired by the REST query; a gap that is
skipped cannot.

**A slow consumer is dropped, not silently starved.** Each subscription has a
bounded queue. If a client stops reading, its queue fills, the subscription is
marked dropped with the reason and the last sequence it actually received, and
the connection is closed with that cursor in hand — so the client resumes from
its true position instead of appearing to have received everything. The
alternative, an unbounded queue, turns one hung browser tab into a memory leak.

**Publishing is safe from any thread.** The producer is not necessarily the
event loop: the correlator runs inside the scoring worker, which is synchronous.
So :meth:`AlertHub.publish` is a plain synchronous call that may be made from a
worker thread, and delivery hops onto each subscription's own loop with
``call_soon_threadsafe``. Subscribe and publish both take one lock, so a publish
either lands in the buffer — and is therefore part of a catch-up — or lands
after registration — and is therefore delivered live. There is no third outcome,
and that is what makes "no alert is lost" a property rather than a hope.

**A cursor from another process is not a cursor.** Sequences are per-process, so
a restart renumbers from one and a client holding ``after=57`` from the previous
process would be told it is up to date when it has history it never saw. Each
hub therefore carries an :attr:`AlertHub.epoch`, sent in every handshake; a
client whose epoch changed must resync through the REST query rather than trust
its cursor. That is D-036's rule — identity must come from data, not from
process state — applied to the stream.

**What is not here.** The buffer is in memory, so it does not survive a restart
and is not shared between replicas; the honest statement is that a deployment
with more than one backend replica needs a shared bus (Redis or Kafka) behind
this interface, and that is named in the docs rather than implied. Wiring the
correlator's output into :meth:`AlertHub.publish` belongs to the composition root
that owns both (T-319).
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import threading
from collections import deque
from dataclasses import dataclass

from app.schemas.query import AlertRow

__all__ = [
    "DEFAULT_BUFFER_SIZE",
    "DEFAULT_QUEUE_SIZE",
    "AlertHub",
    "AlertNotification",
    "AlertSubscription",
    "CatchUp",
    "SubscriberDropped",
]

#: How many recent notifications the hub keeps for catch-up. Bounded because
#: this is a convenience window, not the record: an unbounded stream of alerts
#: held in memory is a memory leak that grows with traffic.
DEFAULT_BUFFER_SIZE = 1024

#: How many notifications may be outstanding for one subscriber before it is
#: considered stuck and dropped. Sized for a burst, not for a client that has
#: stopped reading.
DEFAULT_QUEUE_SIZE = 256

#: Reasons a subscription can end without the client asking.
DROP_SLOW_CONSUMER = "slow_consumer"
DROP_SHUTDOWN = "shutdown"
DROP_LOOP_CLOSED = "loop_closed"


class SubscriberDropped(RuntimeError):
    """The subscription ended because the hub stopped delivering to it.

    Carries the reason and ``after``: the sequence of the last notification the
    subscriber actually received. A client that reconnects with that cursor
    resumes exactly where it stopped, which is why the drop can afford to be
    abrupt.
    """

    def __init__(self, reason: str, after: int) -> None:
        """Record the reason and the last delivered sequence."""
        super().__init__(f"subscription dropped: {reason} (last received: {after})")
        self.reason = reason
        self.after = after


@dataclass(frozen=True, slots=True)
class AlertNotification:
    """One alert, with the position it occupies in this stream.

    Attributes:
        sequence: monotonic within the hub's epoch, starting at 1.
        alert: the alert as the query API returns it — deliberately the *same*
            row model, so a client renders a pushed alert and a fetched alert
            with one code path and cannot drift from the REST shape.
    """

    sequence: int
    alert: AlertRow

    def as_dict(self) -> dict[str, object]:
        """The JSON shape sent on every transport.

        One method for the WebSocket frame, the SSE ``data:`` payload and the
        REST fallback item, so the three cannot drift into three slightly
        different shapes.
        """
        return {"sequence": self.sequence, "alert": self.alert.model_dump(mode="json")}


@dataclass(frozen=True, slots=True)
class CatchUp:
    """What a (re)connecting client missed, and whether that is all of it.

    Attributes:
        items: notifications after the client's cursor, oldest first, bounded
            by what the buffer still holds. When a resync is required these are
            the whole retained window rather than the (incomplete) tail, because
            the client is out of step either way and the buffer is the best
            account of what happened that this process can still give.
        resync_required: True when the cursor is not a position in this
            stream — it predates the retained window, or it is *ahead* of
            everything published here (a cursor from another process, or from a
            replica that has not seen it). Either way ``items`` is not the whole
            story and the client must re-query the alerts API rather than
            assume continuity.
        oldest_available: the oldest sequence the buffer holds, or ``None``.
        latest: the newest sequence published, or ``None``.
        epoch: the publishing process's stream identity. A client that sees a
            different epoch must resync regardless of ``resync_required``,
            because its cursor came from a different numbering.
    """

    items: tuple[AlertNotification, ...]
    resync_required: bool
    oldest_available: int | None
    latest: int | None
    epoch: str


class _Dropped:
    """Sentinel queued to wake a waiter whose subscription was dropped."""

    __slots__ = ()


_DROPPED = _Dropped()


class AlertSubscription:
    """One consumer's view of the stream: a bounded queue and a cursor.

    Created by :meth:`AlertHub.subscribe`; the client-facing transports (the
    WebSocket route and the SSE route) call :meth:`next` until it raises
    :class:`SubscriberDropped`.
    """

    __slots__ = (
        "_after",
        "_closed",
        "_drop_reason",
        "_hub",
        "_lock",
        "_loop",
        "_queue",
        "_received",
    )

    def __init__(self, hub: AlertHub, *, after: int, queue_size: int) -> None:
        """Create a subscription owned by the calling loop."""
        self._hub = hub
        self._after = after
        self._received = 0
        self._closed = False
        self._drop_reason: str | None = None
        self._queue: asyncio.Queue[AlertNotification | _Dropped] = asyncio.Queue(maxsize=queue_size)
        self._loop = asyncio.get_running_loop()
        # Guards the flags below, which a transport thread and the hub may touch
        # concurrently; the queue itself is only ever touched on its own loop.
        self._lock = threading.Lock()

    @property
    def after(self) -> int:
        """The sequence of the last notification delivered, 0 before any."""
        return self._after

    @property
    def received(self) -> int:
        """How many notifications this subscription has delivered."""
        return self._received

    @property
    def dropped(self) -> str | None:
        """The drop reason, or ``None`` while the subscription is live."""
        with self._lock:
            return self._drop_reason

    @property
    def closed(self) -> bool:
        """Whether the subscription has been closed, by either side."""
        with self._lock:
            return self._closed

    async def next(self) -> AlertNotification:
        """The next notification, waiting for one if necessary.

        Returns:
            The notification, in publish order.

        Raises:
            SubscriberDropped: when the hub stopped delivering — a slow consumer
                or a shutdown. ``after`` on the exception is the resume cursor.
        """
        while True:
            reason = self.dropped
            if reason is not None:
                raise SubscriberDropped(reason, self._after)
            item = await self._queue.get()
            if isinstance(item, _Dropped):
                raise SubscriberDropped(self.dropped or DROP_SHUTDOWN, self._after)
            self._after = item.sequence
            self._received += 1
            return item

    def close(self) -> None:
        """Stop delivering and detach from the hub.

        Synchronous so a transport can call it from a ``finally`` block, and
        idempotent because both a clean close and a drop can race to be first.
        """
        with self._lock:
            already_closed = self._closed
            self._closed = True
        if not already_closed:
            self._hub.detach(self)

    def _mark_dropped(self, reason: str) -> None:
        """Record a drop, and wake a waiter so it does not sit until timeout.

        Called from the hub, which may be on another thread; the flag write is
        guarded, and the queue is only touched by the loop callback.
        """
        with self._lock:
            if self._drop_reason is None:
                self._drop_reason = reason
        self._wake()

    def _wake(self) -> None:
        """Queue the sentinel on the subscription's own loop."""
        with contextlib.suppress(RuntimeError):  # loop already closed
            self._loop.call_soon_threadsafe(self._enqueue_sentinel)

    def _enqueue_sentinel(self) -> None:
        """Put the sentinel if there is room; a full queue already has work."""
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait(_DROPPED)

    def _deliver(self, notification: AlertNotification) -> None:
        """Hand a notification to this subscriber from any thread.

        The overflow decision must be made on the subscription's own loop,
        because that is where the queue lives, so the check happens in
        :meth:`_enqueue`.
        """
        with self._lock:
            if self._closed or self._drop_reason is not None:
                return
        try:
            self._loop.call_soon_threadsafe(self._enqueue, notification)
        except RuntimeError:
            # The loop is gone; the client is unreachable and will resync.
            self._mark_dropped(DROP_LOOP_CLOSED)

    def _enqueue(self, notification: AlertNotification) -> None:
        """Queue a notification, dropping a subscriber that cannot keep up."""
        with self._lock:
            if self._closed or self._drop_reason is not None:
                return
        try:
            self._queue.put_nowait(notification)
        except asyncio.QueueFull:
            self._mark_dropped(DROP_SLOW_CONSUMER)


class AlertHub:
    """A bounded, sequenced fan-out of alert notifications.

    The hub is deliberately synchronous on the producing side: :meth:`publish`
    is a plain call any thread may make, and delivery is pushed onto each
    subscriber's event loop.
    """

    __slots__ = ("_buffer", "_buffer_size", "_epoch", "_lock", "_next", "_queue_size", "_subs")

    def __init__(
        self,
        *,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        queue_size: int = DEFAULT_QUEUE_SIZE,
        epoch: str | None = None,
    ) -> None:
        """Create an empty hub.

        Args:
            buffer_size: how many notifications to retain for catch-up.
            queue_size: per-subscriber backlog before that subscriber is dropped.
            epoch: stream identity; generated when omitted. Injectable so a test
                can simulate a restart while keeping the same process.

        Raises:
            ValueError: if either bound is not positive, or the buffer is smaller
                than a per-subscriber queue — a client one publish behind would
                then be told to resync for an alert the hub still holds.
        """
        if buffer_size < 1:
            raise ValueError(f"buffer_size must be at least 1, got {buffer_size}")
        if queue_size < 1:
            raise ValueError(f"queue_size must be at least 1, got {queue_size}")
        if buffer_size < queue_size:
            raise ValueError(
                f"buffer_size ({buffer_size}) must be at least queue_size ({queue_size}): "
                "a subscriber must never be dropped for a gap the buffer could still close"
            )
        self._buffer: deque[AlertNotification] = deque(maxlen=buffer_size)
        self._buffer_size = buffer_size
        self._queue_size = queue_size
        self._epoch = epoch or secrets.token_hex(8)
        self._next = 1
        self._subs: list[AlertSubscription] = []
        self._lock = threading.Lock()

    @property
    def epoch(self) -> str:
        """This stream's identity, changing on every process start."""
        return self._epoch

    def publish(self, alert: AlertRow) -> AlertNotification:
        """Sequence an alert and deliver it to every subscriber.

        Safe to call from any thread. Returns the notification so a caller can
        log or forward the sequence it just produced.

        Args:
            alert: the alert, in the same shape the query API returns.

        Returns:
            The notification, carrying its stream position.
        """
        with self._lock:
            notification = AlertNotification(sequence=self._next, alert=alert)
            self._next += 1
            self._buffer.append(notification)
            subscribers = tuple(self._subs)
        for subscription in subscribers:
            subscription._deliver(notification)  # noqa: SLF001
        return notification

    def subscribe(self, *, after: int | None = None) -> tuple[AlertSubscription, CatchUp]:
        """Attach a consumer and hand it everything after its cursor.

        Reading the buffer and registering the subscriber happen under one lock,
        so a concurrent :meth:`publish` either joins the catch-up or arrives
        live — never both, and never neither.

        Args:
            after: the last sequence the client processed. ``None`` means a fresh
                client that wants live alerts only, not the backlog.

        Returns:
            The subscription and the catch-up computed at registration.

        Raises:
            ValueError: if ``after`` is negative.
        """
        if after is not None and after < 0:
            raise ValueError(f"after must not be negative, got {after}")
        subscription = AlertSubscription(self, after=after or 0, queue_size=self._queue_size)
        with self._lock:
            catch_up = self._catch_up_locked(after)
            self._subs.append(subscription)
        return subscription, catch_up

    def catch_up(self, after: int | None = None) -> CatchUp:
        """What a client with this cursor has missed (no subscription created).

        Raises:
            ValueError: if the cursor is negative.
        """
        if after is not None and after < 0:
            raise ValueError(f"after must not be negative, got {after}")
        with self._lock:
            return self._catch_up_locked(after)

    def detach(self, subscription: AlertSubscription) -> None:
        """Remove a subscription. Idempotent."""
        with self._lock, contextlib.suppress(ValueError):
            self._subs.remove(subscription)

    def close(self) -> None:
        """Drop every subscriber with the ``shutdown`` reason.

        Called by the application on shutdown so a connected dashboard learns to
        fall back to REST instead of holding a socket that will never speak
        again.
        """
        with self._lock:
            subscribers, self._subs = tuple(self._subs), []
        for subscription in subscribers:
            subscription._mark_dropped(DROP_SHUTDOWN)  # noqa: SLF001

    def subscriber_count(self) -> int:
        """How many subscribers are attached, for diagnostics and tests."""
        with self._lock:
            return len(self._subs)

    def latest_sequence(self) -> int | None:
        """The newest sequence published, or ``None`` if nothing has been."""
        with self._lock:
            return self._buffer[-1].sequence if self._buffer else None

    def oldest_sequence(self) -> int | None:
        """The oldest sequence still retained, or ``None`` if the buffer is empty."""
        with self._lock:
            return self._buffer[0].sequence if self._buffer else None

    def _catch_up_locked(self, after: int | None) -> CatchUp:
        """Compute a catch-up. Caller holds the lock.

        A cursor is unusable in two directions. Behind the retained window, some
        notifications are gone. Ahead of this stream's newest sequence, the
        cursor came from somewhere else — another process's numbering, or
        another replica — and "nothing new for you" would be a false statement
        about a stream that has not met the client's history. Cursor ``0`` is
        neither: sequences start at one, so it means "no position yet" and is
        how a client asks for whatever the buffer holds.
        """
        oldest = self._buffer[0].sequence if self._buffer else None
        latest = self._buffer[-1].sequence if self._buffer else None
        behind = after is not None and oldest is not None and 0 < after < oldest - 1
        ahead = after is not None and after > 0 and (latest is None or after > latest)
        if behind or ahead:
            # Out of step in either direction: hand over everything retained and
            # say so, rather than a tail the client might read as complete.
            items = tuple(self._buffer)
        else:
            items = tuple(
                item for item in self._buffer if after is not None and item.sequence > after
            )
        return CatchUp(
            items=items,
            resync_required=behind or ahead,
            oldest_available=oldest,
            latest=latest,
            epoch=self._epoch,
        )
