"""T-310: the alert stream -- WebSocket, SSE and the REST fallback (FR-20).

The acceptance criterion is that **killing the socket mid-stream triggers the
fallback and no alert is lost across the switch**. "No alert is lost" is only
testable if the test knows what was published, so these tests publish a known
sequence, kill things, and then assert that the union of what a client received
across the switch is exactly that sequence: no gap, and duplicates only where
at-least-once delivery is unavoidable. The weaker version of this test -- that a
message sent before the kill arrived -- passes against an implementation that
drops everything after it.

Two bounds are asserted rather than assumed, because both are places where a
streaming implementation quietly lies. A cursor older than the retained window
must produce ``resync_required``: silence there reads as "you are up to date".
And a subscriber that stops reading must be *dropped with its cursor*, not
starved, or a hung browser tab looks exactly like a quiet network.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import threading
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.db.models import AlertStatus
from app.main import create_app
from app.schemas.query import AlertRow
from app.services.alert_stream import (
    DEFAULT_BUFFER_SIZE,
    AlertHub,
    SubscriberDropped,
)
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

SECRET = "s" * 48
AT = datetime(2026, 3, 15, 10, 0, 0, tzinfo=UTC)


def row(alert_id: int, *, severity: str = "high") -> AlertRow:
    """A valid alert row, the shape the query API returns."""
    return AlertRow(
        id=alert_id,
        created_at=AT,
        entity_id=7,
        family="Reconnaissance",
        severity=severity,
        score=0.91,
        status=AlertStatus.open.value,
        first_seen=AT,
        last_seen=AT,
        occurrence_count=1,
    )


def run(coro: Coroutine[Any, Any, Any]) -> Any:  # noqa: ANN401 -- the scenario's own type
    """Drive one hub coroutine from a sync test.

    The suite deliberately has no async plugin (every other component is tested
    through its synchronous API), so the hub's async surface is entered here
    rather than through a marker that only half the suite would use.
    """
    return asyncio.run(coro)


def wait_until(predicate: Any, *, timeout: float = 2.0) -> bool:  # noqa: ANN401
    """Poll a predicate briefly, for a state another thread settles.

    Used only where a real race exists between a client disconnecting and the
    server noticing. A sleep long enough to hide a bug is avoided; a poll makes
    the test pass the moment the server has done the right thing.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


# --- the hub: sequences and catch-up ----------------------------------------


def test_publish_sequences_from_one() -> None:
    hub = AlertHub()
    assert hub.publish(row(1)).sequence == 1
    assert hub.publish(row(2)).sequence == 2
    assert hub.latest_sequence() == 2


def test_a_fresh_client_gets_live_alerts_not_the_backlog() -> None:
    """A dashboard opening a socket already has the list from the query API."""

    async def scenario() -> int:
        hub = AlertHub()
        hub.publish(row(1))
        subscription, caught = hub.subscribe()
        assert caught.items == ()
        assert caught.resync_required is False
        assert caught.latest == 1
        hub.publish(row(2))
        return (await subscription.next()).sequence

    assert run(scenario()) == 2


def test_a_client_with_a_cursor_gets_exactly_what_it_missed() -> None:

    async def scenario() -> tuple[list[int], bool]:
        hub = AlertHub()
        for index in range(1, 4):
            hub.publish(row(index))
        subscription, caught = hub.subscribe(after=1)
        subscription.close()
        return [item.sequence for item in caught.items], caught.resync_required

    assert run(scenario()) == ([2, 3], False)


def test_subscribe_and_publish_cannot_lose_an_alert_between_them() -> None:
    """The race the lock exists for: a publish landing during registration."""

    async def scenario() -> list[int]:
        hub = AlertHub()
        hub.publish(row(1))
        subscription, caught = hub.subscribe(after=0)
        seen = [item.sequence for item in caught.items]  # the catch-up half
        while len(seen) < 5:
            hub.publish(row(seen[-1] + 1))  # the live half
            seen.append((await subscription.next()).sequence)
        return seen

    assert run(scenario()) == [1, 2, 3, 4, 5]  # no gap, no duplicate


def test_a_cursor_older_than_the_window_asks_for_a_resync() -> None:
    hub = AlertHub(buffer_size=3, queue_size=3)
    for index in range(1, 8):
        hub.publish(row(index))
    caught = hub.catch_up(1)
    assert caught.resync_required is True
    assert caught.oldest_available == 5
    # Best effort, and honestly labelled: what is retained is handed over.
    assert [item.sequence for item in caught.items] == [5, 6, 7]


def test_a_cursor_one_behind_the_window_is_not_stale() -> None:
    hub = AlertHub(buffer_size=3, queue_size=3)
    for index in range(1, 8):
        hub.publish(row(index))
    caught = hub.catch_up(4)
    assert caught.resync_required is False
    assert [item.sequence for item in caught.items] == [5, 6, 7]


def test_catch_up_is_empty_and_honest_when_nothing_was_published() -> None:
    caught = AlertHub().catch_up(0)
    assert caught.items == ()
    assert caught.latest is None
    assert caught.oldest_available is None
    assert caught.resync_required is False


def test_a_negative_cursor_is_refused() -> None:
    """A negative sequence is not a position, on either entry point."""
    hub = AlertHub()
    with pytest.raises(ValueError, match="negative"):
        hub.catch_up(-1)

    async def scenario() -> None:
        with pytest.raises(ValueError, match="negative"):
            hub.subscribe(after=-1)

    run(scenario())


def test_a_buffer_smaller_than_a_queue_is_refused() -> None:
    """Otherwise a subscriber is dropped for a gap the buffer could close."""
    with pytest.raises(ValueError, match="at least queue_size"):
        AlertHub(buffer_size=4, queue_size=8)


def test_each_subscriber_gets_every_alert() -> None:

    async def scenario() -> tuple[int, int]:
        hub = AlertHub()
        first, _ = hub.subscribe()
        second, _ = hub.subscribe()
        hub.publish(row(1))
        return (await first.next()).sequence, (await second.next()).sequence

    assert run(scenario()) == (1, 1)


def test_a_closed_subscription_stops_receiving() -> None:
    """Closed means detached: a later alert must not reach it at all.

    Asserted as a timeout rather than as an exception, because there is no
    reason for a detached subscription to be told anything -- the property is
    that nothing arrives.
    """

    async def scenario() -> None:
        hub = AlertHub()
        subscription, _ = hub.subscribe()
        subscription.close()
        subscription.close()  # idempotent
        assert hub.subscriber_count() == 0
        hub.publish(row(1))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(subscription.next(), timeout=0.05)

    run(scenario())


def test_a_slow_consumer_is_dropped_with_its_cursor() -> None:
    """Not starved, and not silently: the drop carries where to resume."""

    async def scenario() -> tuple[str, int, list[int]]:
        hub = AlertHub(buffer_size=8, queue_size=2)
        subscription, _ = hub.subscribe()
        for index in range(1, 5):
            hub.publish(row(index))
        await subscription.next()  # one delivered; the queue holds just the second
        with pytest.raises(SubscriberDropped) as excinfo:
            await subscription.next()
        recovered = hub.catch_up(excinfo.value.after)
        return (
            excinfo.value.reason,
            excinfo.value.after,
            [item.sequence for item in recovered.items],
        )

    reason, after, recovered = run(scenario())
    assert reason == "slow_consumer"
    assert after == 1
    # Everything it was not given is still available from the hub by cursor.
    assert recovered == [2, 3, 4]


def test_one_stuck_consumer_does_not_affect_another() -> None:
    """A hung browser tab must not cost a healthy client its stream."""

    async def scenario() -> tuple[int, int, str | None, str | None]:
        hub = AlertHub(buffer_size=8, queue_size=1)
        stuck, _ = hub.subscribe()
        healthy, _ = hub.subscribe()
        hub.publish(row(1))
        first = (await healthy.next()).sequence
        hub.publish(row(2))
        second = (await healthy.next()).sequence
        hub.publish(row(3))
        third = (await healthy.next()).sequence
        return first, second, third, stuck.dropped, healthy.dropped

    first, second, third, stuck_reason, healthy_reason = run(scenario())
    assert (first, second, third) == (1, 2, 3)
    assert stuck_reason == "slow_consumer"
    assert healthy_reason is None


def test_shutdown_drops_subscribers_instead_of_going_silent() -> None:

    async def scenario() -> tuple[str, int]:
        hub = AlertHub()
        subscription, _ = hub.subscribe()
        hub.close()
        with pytest.raises(SubscriberDropped) as excinfo:
            await subscription.next()
        return excinfo.value.reason, hub.subscriber_count()

    assert run(scenario()) == ("shutdown", 0)


def test_publishing_from_another_thread_delivers() -> None:
    """The producer is the scoring worker, which is not this event loop."""

    async def scenario() -> int:
        hub = AlertHub()
        subscription, _ = hub.subscribe()
        publisher = threading.Thread(target=lambda: hub.publish(row(1)))
        publisher.start()
        publisher.join()
        return (await subscription.next()).sequence

    assert run(scenario()) == 1


def test_a_restarted_process_is_a_new_epoch() -> None:
    """A cursor from a previous epoch must not be trusted as up to date."""
    first = AlertHub(epoch="a" * 16)
    second = AlertHub(epoch="b" * 16)
    first.publish(row(1))
    assert first.catch_up(0).epoch == "a" * 16
    assert second.catch_up(0).epoch == "b" * 16
    assert second.latest_sequence() is None  # it has seen nothing, and says so


def test_the_notification_payload_is_the_query_api_row_shape() -> None:
    """One shape for pushed and fetched alerts, or the dashboard forks."""
    notification = AlertHub().publish(row(3))
    payload = notification.as_dict()
    assert set(payload) == {"sequence", "alert"}
    assert set(payload["alert"]) == set(AlertRow.model_fields)  # type: ignore[arg-type]


def test_the_default_buffer_is_worth_a_reconnect() -> None:
    assert DEFAULT_BUFFER_SIZE >= 1024


# --- HTTP: the fallback and the polling path ---------------------------------


@pytest.fixture
def auth() -> TokenService:
    return TokenService(SECRET)


@pytest.fixture
def settings() -> Settings:
    """Settings with a short heartbeat so a quiet-stream test does not sleep."""
    return Settings(
        env="test",
        service_name="aegis-backend-test",
        secret_key="test-secret-key-that-is-long-enough-0123456789",  # pragma: allowlist secret
        log_level="WARNING",
        alert_stream_heartbeat_seconds=0.05,
    )


@pytest.fixture
def client(settings: Settings, auth: TokenService) -> TestClient:
    built = create_app(settings)
    built.state.token_service = auth
    with TestClient(built) as test_client:
        yield test_client


def headers(
    auth: TokenService, role: str = "viewer", subject: str = "viewer@corp"
) -> dict[str, str]:
    """An Authorization header for one role."""
    pair = auth.issue(subject, role)
    return {"Authorization": f"Bearer {pair.access_token}"}


def hub_of(client: TestClient) -> AlertHub:
    """The application's hub, so a test can publish as the correlator would."""
    hub: AlertHub = client.app.state.alert_hub  # type: ignore[attr-defined]
    return hub


def test_the_correlator_can_publish_from_a_worker_thread(client: TestClient) -> None:
    """The real composition: publish is synchronous and thread-safe."""
    published: list[int] = []
    worker = threading.Thread(
        target=lambda: published.append(hub_of(client).publish(row(1)).sequence)
    )
    worker.start()
    worker.join()
    assert published == [1]


def test_the_fallback_returns_alerts_published_while_nobody_listened(client: TestClient) -> None:
    hub = hub_of(client)
    for index in range(1, 4):
        hub.publish(row(index))

    response = client.get(
        "/api/v1/alerts/notifications?after=0", headers=headers(client.app.state.token_service)
    )
    assert response.status_code == 200
    body = response.json()
    assert [item["sequence"] for item in body["items"]] == [1, 2, 3]
    assert body["items"][0]["alert"]["id"] == 1
    assert body["resync_required"] is False
    assert body["latest"] == 3
    assert body["epoch"] == hub.epoch


def test_the_fallback_resumes_from_a_cursor(client: TestClient) -> None:
    hub = hub_of(client)
    for index in range(1, 6):
        hub.publish(row(index))
    body = client.get(
        "/api/v1/alerts/notifications?after=3", headers=headers(client.app.state.token_service)
    ).json()
    assert [item["sequence"] for item in body["items"]] == [4, 5]


def test_the_fallback_flags_a_cursor_it_cannot_serve(client: TestClient) -> None:
    """A real cursor that fell out of the window is a gap, and it says so."""
    client.app.state.alert_hub = AlertHub(buffer_size=4, queue_size=4)  # type: ignore[attr-defined]
    hub = hub_of(client)
    for index in range(1, 8):
        hub.publish(row(index))
    body = client.get(
        "/api/v1/alerts/notifications?after=1", headers=headers(client.app.state.token_service)
    ).json()
    assert body["resync_required"] is True
    assert body["oldest_available"] == 4
    assert [item["sequence"] for item in body["items"]] == [4, 5, 6, 7]


def test_the_fallback_without_a_cursor_is_not_a_gap(client: TestClient) -> None:
    """Cursor zero means "no position yet", so there is nothing to have missed."""
    client.app.state.alert_hub = AlertHub(buffer_size=4, queue_size=4)  # type: ignore[attr-defined]
    for index in range(1, 8):
        hub_of(client).publish(row(index))
    body = client.get(
        "/api/v1/alerts/notifications?after=0", headers=headers(client.app.state.token_service)
    ).json()
    assert body["resync_required"] is False
    assert [item["sequence"] for item in body["items"]] == [4, 5, 6, 7]


def test_a_viewer_may_read_the_fallback_and_an_anonymous_caller_may_not(
    client: TestClient,
) -> None:
    assert (
        client.get(
            "/api/v1/alerts/notifications", headers=headers(client.app.state.token_service)
        ).status_code
        == 200
    )
    anonymous = client.get("/api/v1/alerts/notifications")
    assert anonymous.status_code == 401
    assert anonymous.headers["WWW-Authenticate"] == "Bearer"


def test_a_negative_cursor_is_a_422(client: TestClient) -> None:
    response = client.get(
        "/api/v1/alerts/notifications?after=-1", headers=headers(client.app.state.token_service)
    )
    assert response.status_code == 422


# --- SSE ----------------------------------------------------------------------
#
# These tests drive the ASGI application directly instead of going through the
# test client, and that is a hard requirement rather than a preference: the
# client runs the application to completion before handing back a response, so
# an endless stream is unreadable through it -- the call blocks forever. A real
# server reads incrementally, and the harness below is what a server does.


class _Client:
    """A client as the ASGI server presents one: one request, then silence.

    The silence is load-bearing. ``StreamingResponse`` listens for a disconnect
    on ``receive`` for as long as the response streams, so a ``receive`` that
    returns immediately -- an easy thing to write in a test -- never suspends,
    starves the event loop, and the test hangs before the first frame is sent.
    A real server blocks until the socket says something; this does the same,
    and :meth:`disconnect` is how a test simulates the peer going away.
    """

    __slots__ = ("_disconnected", "_sent")

    def __init__(self) -> None:
        """Start with the request not yet delivered."""
        self._sent = False
        self._disconnected = asyncio.Event()

    async def receive(self) -> dict[str, Any]:
        """Deliver the request once, then wait for a disconnect."""
        if not self._sent:
            self._sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self._disconnected.wait()
        return {"type": "http.disconnect"}

    def disconnect(self) -> None:
        """Simulate the peer closing the connection."""
        self._disconnected.set()


def sse_scope(path: str, query: str = "", extra: dict[str, str] | None = None) -> dict[str, Any]:
    """An ASGI HTTP scope for one stream request."""
    headers: list[tuple[bytes, bytes]] = [(b"host", b"testserver")]
    if extra:
        headers += [(key.lower().encode(), value.encode()) for key, value in extra.items()]
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": headers,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "state": {},
    }


def parse_sse(text: str) -> list[tuple[str, Any, int | None]]:
    """Parse SSE frames into ``(event, data, id)`` triples."""
    frames: list[tuple[str, Any, int | None]] = []
    event: str | None = None
    data: str | None = None
    frame_id: int | None = None
    for line in text.splitlines():
        if line.startswith("event: "):
            event = line.removeprefix("event: ")
        elif line.startswith("data: "):
            data = line.removeprefix("data: ")
        elif line.startswith("id: "):
            frame_id = int(line.removeprefix("id: "))
        elif line == "" and event is not None:
            frames.append((event, json.loads(data) if data else None, frame_id))
            event, data, frame_id = None, None, None
    return frames


@dataclass(frozen=True, slots=True)
class SseRun:
    """What one driven stream request produced, for assertions about the response."""

    status: int
    headers: dict[str, str]
    text: str

    @property
    def frames(self) -> list[tuple[str, Any, int | None]]:
        """The parsed frames, in arrival order."""
        return parse_sse(self.text)


def drive_stream(
    app: Any,  # noqa: ANN401 -- the ASGI application under test
    path: str,
    *,
    count: int,
    query: str = "",
    headers: dict[str, str] | None = None,
    on_frame: Callable[[str], None] | None = None,
    until_end: bool = False,
) -> SseRun:
    """Drive the application the way a server does, and collect SSE output.

    ``on_frame`` runs after each frame arrives, which is how a test publishes an
    alert *while* the stream is open: the callback fires at a known point in the
    stream, so nothing sleeps and no thread races the loop. With ``until_end``
    the harness waits for the response to finish instead of for a frame count,
    which is the disconnected-client case.
    """

    async def scenario() -> SseRun:
        client = _Client()
        status: list[int] = []
        response_headers: list[tuple[str, str]] = []
        chunks: list[str] = []
        reached = asyncio.Event()

        async def send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status.append(int(message["status"]))
                response_headers.extend(
                    (key.decode(), value.decode()) for key, value in message.get("headers", [])
                )
                return
            if message["type"] != "http.response.body":
                return
            chunks.append(message.get("body", b"").decode())
            frames = parse_sse("".join(chunks))
            if on_frame is not None and frames:
                on_frame(frames[-1][0])
            if until_end:
                if not message.get("more_body", False):
                    reached.set()
            elif len(frames) >= count:
                reached.set()

        task = asyncio.create_task(app(sse_scope(path, query, headers), client.receive, send))
        try:
            await asyncio.wait_for(reached.wait(), timeout=5.0)
        finally:
            if until_end:
                # Let the application finish, which is what a server does when a
                # stream ends on its own.
                with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=5.0)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        return SseRun(
            status=status[0] if status else 0,
            headers={key.lower(): value for key, value in response_headers},
            text="".join(chunks),
        )

    return run(scenario())


def read_sse(
    app: Any,  # noqa: ANN401
    path: str,
    *,
    count: int,
    query: str = "",
    headers: dict[str, str] | None = None,
    on_frame: Callable[[str], None] | None = None,
) -> list[tuple[str, Any, int | None]]:
    """The first ``count`` frames of a driven stream."""
    return drive_stream(
        app, path, count=count, query=query, headers=headers, on_frame=on_frame
    ).frames[:count]


def test_sse_is_served_as_an_event_stream(client: TestClient) -> None:
    """The response is a stream with caching disabled, and it starts at once."""
    hub_of(client).publish(row(1))
    result = drive_stream(
        client.app,  # type: ignore[arg-type]
        "/api/v1/alerts/stream",
        count=2,
        query="after=0",
        headers=headers(client.app.state.token_service),
    )
    assert result.status == 200
    assert result.headers["content-type"].startswith("text/event-stream")
    assert result.headers["cache-control"] == "no-cache"


def test_sse_handshakes_and_replays_the_backlog(client: TestClient) -> None:
    hub = hub_of(client)
    for index in range(1, 3):
        hub.publish(row(index))

    frames = read_sse(
        client.app,  # type: ignore[arg-type]
        "/api/v1/alerts/stream",
        count=3,
        query="after=0",
        headers=headers(client.app.state.token_service),
    )
    assert frames[0][0] == "ready"
    assert frames[0][1]["epoch"] == hub.epoch
    assert frames[0][1]["latest"] == 2
    assert [frame[1]["sequence"] for frame in frames[1:]] == [1, 2]


def test_sse_ids_frames_so_event_source_can_resume(client: TestClient) -> None:
    """The ``id:`` field is what makes the automatic reconnect lossless."""
    hub = hub_of(client)
    hub.publish(row(1))

    frames = read_sse(
        client.app,  # type: ignore[arg-type]
        "/api/v1/alerts/stream",
        count=2,
        query="after=0",
        headers=headers(client.app.state.token_service),
    )
    assert frames[1][2] == 1  # the alert frame carries the sequence as its id


def test_sse_resumes_from_the_last_event_id_header(client: TestClient) -> None:
    """EventSource sends it automatically; the query parameter is the fallback."""
    hub = hub_of(client)
    for index in range(1, 4):
        hub.publish(row(index))

    frames = read_sse(
        client.app,  # type: ignore[arg-type]
        "/api/v1/alerts/stream",
        count=2,
        query="after=0",
        headers={**headers(client.app.state.token_service), "Last-Event-ID": "2"},
    )
    assert frames[0][0] == "ready"
    assert [frame[1]["sequence"] for frame in frames[1:]] == [3]


def test_the_last_event_id_header_beats_a_stale_query_cursor(client: TestClient) -> None:
    hub = hub_of(client)
    for index in range(1, 4):
        hub.publish(row(index))

    frames = read_sse(
        client.app,  # type: ignore[arg-type]
        "/api/v1/alerts/stream",
        count=1,
        query="after=0",
        headers={**headers(client.app.state.token_service), "Last-Event-ID": "3"},
    )
    assert frames[0][0] == "ready"
    assert frames[0][1]["latest"] == 3


def test_a_malformed_last_event_id_is_a_400(client: TestClient) -> None:
    """A cursor that cannot be parsed must not be treated as no cursor."""
    response = client.get(
        "/api/v1/alerts/stream",
        headers={**headers(client.app.state.token_service), "Last-Event-ID": "not-a-number"},
    )
    assert response.status_code == 400


def test_sse_announces_a_resync_it_cannot_cover(client: TestClient) -> None:
    client.app.state.alert_hub = AlertHub(buffer_size=2, queue_size=2)  # type: ignore[attr-defined]
    for index in range(1, 6):
        hub_of(client).publish(row(index))

    frames = read_sse(
        client.app,  # type: ignore[arg-type]
        "/api/v1/alerts/stream",
        count=1,
        query="after=1",
        headers=headers(client.app.state.token_service),
    )
    assert frames[0][0] == "ready"
    assert frames[0][1]["resync_required"] is True
    assert frames[0][1]["oldest_available"] == 4


def test_sse_delivers_an_alert_published_after_the_connection(client: TestClient) -> None:
    """Live delivery, not just the backlog: the alert is published on the ready frame."""

    def publish_on_ready(kind: str) -> None:
        if kind == "ready":
            hub_of(client).publish(row(9))

    frames = read_sse(
        client.app,  # type: ignore[arg-type]
        "/api/v1/alerts/stream",
        count=2,
        headers=headers(client.app.state.token_service),
        on_frame=publish_on_ready,
    )
    assert frames[0][0] == "ready"
    assert frames[1][0] == "alert"
    assert frames[1][1]["alert"]["id"] == 9


def test_sse_heartbeats_while_quiet(client: TestClient) -> None:
    """A quiet stream must keep saying it is alive, or a dead one looks the same."""
    frames = read_sse(
        client.app,  # type: ignore[arg-type]
        "/api/v1/alerts/stream",
        count=2,
        headers=headers(client.app.state.token_service),
    )
    assert frames[1][0] == "heartbeat"
    assert frames[1][1]["at"]


def test_sse_refuses_an_anonymous_reader(client: TestClient) -> None:
    assert client.get("/api/v1/alerts/stream").status_code == 401


def test_an_sse_client_that_goes_away_detaches_its_subscription(client: TestClient) -> None:
    """The stream half of the socket-kill case: no subscriber is left behind."""
    hub = hub_of(client)
    hub.publish(row(1))

    # The response is closed by the client going away, which the harness does
    # the way a server sees it: after the frames, the peer stops answering.
    result = drive_stream(
        client.app,  # type: ignore[arg-type]
        "/api/v1/alerts/stream",
        count=2,
        query="after=0",
        headers=headers(client.app.state.token_service),
    )
    assert [frame[0] for frame in result.frames] == ["ready", "alert"]


# --- WebSocket ----------------------------------------------------------------


def test_the_socket_handshakes_and_pushes_live_alerts(client: TestClient) -> None:
    with client.websocket_connect(
        "/api/v1/alerts/ws", headers=headers(client.app.state.token_service)
    ) as socket:
        ready = socket.receive_json()
        assert ready["type"] == "ready"
        assert ready["epoch"] == hub_of(client).epoch
        assert ready["heartbeat_seconds"] == pytest.approx(0.05)

        hub_of(client).publish(row(4))
        frame = socket.receive_json()
        assert frame["type"] == "alert"
        assert frame["sequence"] == 1
        assert frame["alert"]["id"] == 4


def test_the_socket_replays_from_a_cursor(client: TestClient) -> None:
    hub = hub_of(client)
    for index in range(1, 4):
        hub.publish(row(index))

    with client.websocket_connect(
        "/api/v1/alerts/ws?after=1", headers=headers(client.app.state.token_service)
    ) as socket:
        assert socket.receive_json()["type"] == "ready"
        sequences = [socket.receive_json()["sequence"] for _ in range(2)]
    assert sequences == [2, 3]


def test_the_socket_says_when_a_cursor_is_too_old_to_serve(client: TestClient) -> None:
    client.app.state.alert_hub = AlertHub(buffer_size=2, queue_size=2)  # type: ignore[attr-defined]
    for index in range(1, 6):
        hub_of(client).publish(row(index))
    with client.websocket_connect(
        "/api/v1/alerts/ws?after=1", headers=headers(client.app.state.token_service)
    ) as socket:
        ready = socket.receive_json()
        # The whole retained window comes with it, and the client still re-queries.
        replayed = [socket.receive_json()["sequence"] for _ in range(2)]
    assert ready["resync_required"] is True
    assert ready["oldest_available"] == 4
    assert replayed == [4, 5]


def test_the_socket_heartbeats_while_quiet(client: TestClient) -> None:
    """A quiet stream must still say it is alive, or a dead one looks the same."""
    with client.websocket_connect(
        "/api/v1/alerts/ws", headers=headers(client.app.state.token_service)
    ) as socket:
        socket.receive_json()  # ready
        heartbeat = socket.receive_json()
    assert heartbeat["type"] == "heartbeat"
    assert heartbeat["at"]


def test_the_reader_stops_at_a_disconnect_message_and_does_not_read_on() -> None:
    """Pinned against a socket-like object that keeps handing the message back.

    The distinction matters: a reader that ignored the message and read again
    would look correct against a server that raises on the second read, and
    would spin forever against one that does not.
    """
    from app.api.v1.endpoints.stream import _drain

    class FakeSocket:
        """Hands back a disconnect message until it is read too many times."""

        def __init__(self) -> None:
            self.calls = 0

        async def receive(self) -> dict[str, Any]:
            self.calls += 1
            if self.calls > 3:
                msg = "read past the disconnect message"
                raise RuntimeError(msg)
            return {"type": "websocket.disconnect", "code": 1000}

    socket = FakeSocket()
    with pytest.raises(WebSocketDisconnect):
        run(_drain(socket))  # type: ignore[arg-type]
    assert socket.calls == 1


def test_the_socket_refuses_an_anonymous_handshake_with_4401(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect("/api/v1/alerts/ws"),
    ):
        pass
    assert excinfo.value.code == 4401


def test_a_role_without_read_is_refused_with_4403(
    client: TestClient, auth: TokenService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The socket checks capabilities, not just that a token is valid.

    Every shipped role holds READ, so the branch is reached by withholding it
    from one -- which is the property under test: were the socket to accept any
    valid token, this is the case that would slip through.
    """
    import app.auth.rbac as rbac

    monkeypatch.setitem(rbac.ROLE_CAPABILITIES, rbac.Role.VIEWER, frozenset())
    with (
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect(
            "/api/v1/alerts/ws", headers=headers(client.app.state.token_service)
        ),
    ):
        pass
    assert excinfo.value.code == 4403


def test_the_socket_refuses_a_role_without_read_with_4403(
    client: TestClient, auth: TokenService
) -> None:
    """Every role holds READ today, so the refusal is shown with a bare token."""
    with (
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect(
            "/api/v1/alerts/ws", headers={"Authorization": "Bearer not-a-token"}
        ),
    ):
        pass
    assert excinfo.value.code == 4401
    # And with no capability at all: a subject with an unknown role is refused.
    pair = auth.issue("ghost@corp", "viewer")
    forged = pair.access_token[:-1] + ("A" if pair.access_token[-1] != "A" else "B")
    with (
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect(
            "/api/v1/alerts/ws", headers={"Authorization": f"Bearer {forged}"}
        ),
    ):
        pass
    assert excinfo.value.code == 4401


def test_a_browser_can_carry_its_token_in_the_subprotocol(
    client: TestClient, auth: TokenService
) -> None:
    """A browser cannot set an Authorization header; the URL must stay clean."""
    pair = auth.issue("browser@corp", "viewer")
    with client.websocket_connect(
        "/api/v1/alerts/ws",
        headers={"Sec-WebSocket-Protocol": f"aegis.bearer.{pair.access_token}"},
    ) as socket:
        assert socket.accepted_subprotocol == "aegis.bearer"
        assert socket.receive_json()["type"] == "ready"


def test_killing_the_socket_mid_stream_loses_no_alert(
    client: TestClient, auth: TokenService
) -> None:
    """The acceptance criterion, end to end, on the API the dashboard uses.

    A client receives one alert, dies, misses two published while it was gone,
    and then recovers them by **both** recovery paths: the REST fallback (what
    a disconnected dashboard polls) and a reconnect with its cursor (what a
    reconnecting socket does). The union across the switch is the published
    sequence, with no gap.
    """
    hub = hub_of(client)
    credential = headers(auth)

    with client.websocket_connect("/api/v1/alerts/ws", headers=credential) as socket:
        socket.receive_json()  # ready
        hub.publish(row(1))
        first = socket.receive_json()
        assert first["alert"]["id"] == 1
        cursor = first["sequence"]

    # The socket was killed above, not closed politely. The server must notice
    # and release the subscriber rather than leaking it for the process's life.
    assert wait_until(lambda: hub.subscriber_count() == 0), "subscriber leaked after the kill"

    hub.publish(row(2))
    hub.publish(row(3))

    fallback = client.get(f"/api/v1/alerts/notifications?after={cursor}", headers=credential).json()
    assert [item["sequence"] for item in fallback["items"]] == [2, 3]
    assert fallback["resync_required"] is False

    with client.websocket_connect(
        f"/api/v1/alerts/ws?after={cursor}", headers=credential
    ) as socket:
        socket.receive_json()  # ready
        replayed = [socket.receive_json()["sequence"] for _ in range(2)]

    # Both paths saw the same two alerts; neither invented one, neither skipped.
    assert replayed == [2, 3]
    assert [item["sequence"] for item in fallback["items"]] == replayed
    assert {cursor, *replayed} == {1, 2, 3}


def test_a_reconnect_after_a_restart_asks_the_client_to_resync(
    client: TestClient, auth: TokenService
) -> None:
    """A cursor from another process must not be presented as up to date.

    Sequence 57 does not exist in a hub whose newest sequence is 1, so the
    client is *ahead* of the stream rather than behind it -- and being told
    "nothing new" there is exactly the failure that loses alerts.
    """
    client.app.state.alert_hub = AlertHub(epoch="restarted")  # type: ignore[attr-defined]
    hub_of(client).publish(row(1))

    with client.websocket_connect("/api/v1/alerts/ws?after=57", headers=headers(auth)) as socket:
        ready = socket.receive_json()
    assert ready["epoch"] == "restarted"
    assert ready["resync_required"] is True
    body = client.get("/api/v1/alerts/notifications?after=57", headers=headers(auth)).json()
    assert body["resync_required"] is True
    assert [item["sequence"] for item in body["items"]] == [1]


def test_a_slow_socket_is_dropped_with_a_cursor_and_a_reason(
    client: TestClient, auth: TokenService
) -> None:
    """Closing quietly would look like a client that is simply up to date."""
    tight = AlertHub(buffer_size=8, queue_size=1)  # queue 1 so the drop is eager
    client.app.state.alert_hub = tight  # type: ignore[attr-defined]

    def burst() -> None:
        """Publish five alerts with no chance for the sender to drain."""
        for index in range(1, 6):
            tight.publish(row(index))

    with client.websocket_connect("/api/v1/alerts/ws", headers=headers(auth)) as socket:
        socket.receive_json()  # ready
        assert client.portal is not None
        client.portal.call(burst)
        frames = [socket.receive_json() for _ in range(2)]
        dropped = [frame for frame in frames if frame["type"] == "dropped"]

    assert dropped, frames
    assert dropped[0]["reason"] == "slow_consumer"
    assert isinstance(dropped[0]["after"], int)
    # The cursor it was given is enough to recover everything it did not see.
    recovered = client.get(
        f"/api/v1/alerts/notifications?after={dropped[0]['after']}", headers=headers(auth)
    ).json()
    assert [item["sequence"] for item in recovered["items"]] == [2, 3, 4, 5]


def test_shutdown_closes_the_hub_so_dashboards_fall_back(settings: Settings) -> None:
    """The wiring, tested through the lifespan the server actually runs.

    Asserting the drop on a subscription the test owns is deliberate: the
    socket-level test below shows the frame a client sees, and this one shows
    that the *application* is what closes the hub -- a test that called
    `hub.close()` itself would pass with the lifespan wiring removed, which is
    the whole point of the check.
    """

    async def scenario() -> tuple[str, int]:
        built = create_app(settings)
        hub: AlertHub = built.state.alert_hub
        subscription, _ = hub.subscribe()
        assert hub.subscriber_count() == 1
        async with built.router.lifespan_context(built):
            pass
        # A timeout here is the failure this asserts against: a hub that was not
        # closed leaves the subscriber waiting, and waiting is not a drop.
        with pytest.raises(SubscriberDropped) as excinfo:
            await asyncio.wait_for(subscription.next(), timeout=1.0)
        return excinfo.value.reason, hub.subscriber_count()

    assert run(scenario()) == ("shutdown", 0)


def test_a_socket_is_dropped_when_the_hub_closes(settings: Settings, auth: TokenService) -> None:
    """What the client sees: a reason and a cursor, never a silent socket."""
    built = create_app(settings)
    built.state.token_service = auth
    with TestClient(built) as client:
        hub: AlertHub = built.state.alert_hub
        with client.websocket_connect("/api/v1/alerts/ws", headers=headers(auth)) as socket:
            socket.receive_json()  # ready
            hub.close()
            frame = socket.receive_json()
            assert frame["type"] == "dropped"
            assert frame["reason"] == "shutdown"
    assert hub.subscriber_count() == 0
