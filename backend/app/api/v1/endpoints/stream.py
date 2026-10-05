"""The alert stream: WebSocket, SSE, and the REST fallback (FR-20, T-310).

Three transports over one hub, in the order a dashboard uses them:

* ``GET /api/v1/alerts/ws`` — the WebSocket. Fastest, and the one the app shell
  holds open. The client's cursor is the ``after`` query parameter, so a
  reconnect is a new URL with the position it reached; ``Sec-WebSocket-Protocol``
  carries the bearer token because a browser cannot set a header on a WebSocket
  and the token must not go in the URL, where it would reach access logs.
* ``GET /api/v1/alerts/stream`` — Server-Sent Events. The fallback for a network
  that will not carry a WebSocket upgrade. ``Last-Event-ID`` is sent
  automatically by ``EventSource`` on reconnect, and the ``id:`` field of each
  alert frame is what makes that work; ``after`` is accepted for clients that do
  not send it.
* ``GET /api/v1/alerts/notifications`` — plain REST polling, at the 15 s cadence
  architecture.md §14 specifies for a dropped socket, and also the endpoint a
  client calls when the handshake says ``resync_required``.

The routes are thin (R-13): they frame what :mod:`app.services.alert_stream`
produces. Every rule about sequences, gaps, drops and epochs lives in the
service, where it is tested without a server.

**What a dropped connection does, and does not, cost.** The server detaches the
subscription the moment the peer goes away — the reader task in the WebSocket
route exists for exactly that, because a send loop alone never notices a client
that stopped listening — and alerts published while nobody is connected stay
retrievable from the hub by cursor. That is the server half of "no alert is lost
across the switch"; the browser half (banner, polling, resume) is E4's, and the
cursor this module hands out is what makes it possible.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, WebSocket
from fastapi.responses import StreamingResponse
from starlette.websockets import WebSocketDisconnect

from app.auth.rbac import Capability, Forbidden, Unauthenticated, authenticate, require
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.schemas.stream import AlertNotificationOut, AlertNotificationsOut
from app.services.alert_stream import (
    AlertHub,
    AlertNotification,
    AlertSubscription,
    CatchUp,
    SubscriberDropped,
)

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

#: One frame: its kind (``ready``, ``alert``, ``heartbeat``, ``dropped``) and its
#: payload. Named because both streaming transports and the sender share it.
Frame = tuple[str, dict[str, Any]]

#: The subprotocol prefix a browser sends to carry its bearer token. The value
#: the server echoes back is the bare prefix, since a WebSocket handshake fails
#: if the server selects a subprotocol the client did not offer.
SUBPROTOCOL_PREFIX = "aegis.bearer."

#: Sent on a dropped WebSocket before the close frame, so the client learns the
#: reason and its resume cursor even when it never reads the close code.
CLOSE_TRY_AGAIN_LATER = 1013

#: The app-specific close codes for a refused handshake, in the private range
#: RFC 6455 reserves for applications (4000-4999).
CLOSE_UNAUTHENTICATED = 4401
CLOSE_FORBIDDEN = 4403


def _hub(request_or_socket: Request | WebSocket) -> AlertHub:
    """The process-wide hub from application state."""
    hub: AlertHub | None = getattr(request_or_socket.app.state, "alert_hub", None)
    if hub is None:
        msg = "alert_hub is not configured on app.state"
        raise RuntimeError(msg)
    return hub


def _settings(request_or_socket: Request | WebSocket) -> Settings:
    """The application's settings."""
    settings: Settings = request_or_socket.app.state.settings
    return settings


def _notification_out(item: AlertNotification) -> AlertNotificationOut:
    """Serialise one hub notification into the wire model."""
    return AlertNotificationOut(sequence=item.sequence, alert=item.alert)


def _response(caught: CatchUp) -> AlertNotificationsOut:
    """Serialise a catch-up into the REST fallback's body."""
    return AlertNotificationsOut(
        items=[_notification_out(item) for item in caught.items],
        oldest_available=caught.oldest_available,
        latest=caught.latest,
        resync_required=caught.resync_required,
        epoch=caught.epoch,
    )


@router.get(
    "/notifications",
    response_model=AlertNotificationsOut,
    summary="Alerts published after a stream cursor (FR-20 fallback)",
    dependencies=[require(Capability.READ)],
)
def notifications(
    request: Request,
    after: int | None = Query(
        default=None,
        ge=0,
        description="The last sequence the client processed; omit for the retained window.",
    ),
) -> AlertNotificationsOut:
    """Return alerts published after ``after``, bounded by the retained window.

    This is the polling fallback and the resync target. ``resync_required`` in
    the body is the part that matters: when it is true, the cursor predates the
    window, so the client must re-query alerts rather than believe it has
    everything.
    """
    return _response(_hub(request).catch_up(after))


async def _frames(
    subscription: AlertSubscription,
    caught: CatchUp,
    *,
    heartbeat_seconds: float,
) -> AsyncIterator[Frame]:
    """Yield ``(kind, payload)`` for one subscription, until it is dropped.

    Shared by both streaming transports so the WebSocket and SSE paths cannot
    disagree about ordering, heartbeats or the drop signal.
    """
    yield (
        "ready",
        {
            "epoch": caught.epoch,
            "latest": caught.latest,
            "oldest_available": caught.oldest_available,
            "resync_required": caught.resync_required,
            "after": subscription.after,
            "heartbeat_seconds": heartbeat_seconds,
        },
    )
    for item in caught.items:
        yield "alert", item.as_dict()
    while True:
        try:
            notification = await asyncio.wait_for(subscription.next(), timeout=heartbeat_seconds)
        except TimeoutError:
            yield "heartbeat", {"at": datetime.now(UTC).isoformat()}
            continue
        except SubscriberDropped as exc:
            # A heartbeat above would have hidden this: the client is told the
            # reason and where to resume, never left to assume it caught up.
            yield "dropped", {"reason": exc.reason, "after": exc.after}
            return
        yield "alert", notification.as_dict()


def _sse(kind: str, payload: Mapping[str, Any], *, sequence: int | None = None) -> str:
    """Render one Server-Sent Events frame, with ``id:`` when it is an alert."""
    lines = []
    if sequence is not None:
        lines.append(f"id: {sequence}")
    lines.append(f"event: {kind}")
    lines.append(f"data: {json.dumps(payload, separators=(',', ':'))}")
    return "\n".join(lines) + "\n\n"


@router.get(
    "/stream",
    summary="Server-Sent Events alert stream (FR-20 fallback)",
    dependencies=[require(Capability.READ)],
)
async def stream(
    request: Request,
    after: int | None = Query(default=None, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Stream alerts as SSE, resuming from the client's last seen sequence.

    ``async def`` is required, not stylistic: a sync endpoint runs in a worker
    thread, and a subscription has to belong to the event loop that will deliver
    to it.

    The ``Last-Event-ID`` header wins when both it and ``after`` are present: a
    reconnecting ``EventSource`` sets the header from the last ``id:`` it saw,
    while a query parameter may be left over from the original request and is
    therefore the more likely of the two to be stale.
    """
    cursor = _cursor_from_header(last_event_id, fallback=after)
    hub = _hub(request)
    subscription, caught = hub.subscribe(after=cursor)
    heartbeat = _settings(request).alert_stream_heartbeat_seconds

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for kind, payload in _frames(subscription, caught, heartbeat_seconds=heartbeat):
                sequence = payload.get("sequence") if kind == "alert" else None
                yield _sse(kind, payload, sequence=sequence if isinstance(sequence, int) else None)
        finally:
            # Also runs when the client disconnects mid-stream, which is the
            # case this exists for: a closed generator must not leave a
            # subscriber attached to the hub.
            subscription.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Proxies that buffer would defeat the point of a stream.
            "X-Accel-Buffering": "no",
        },
    )


def _cursor_from_header(last_event_id: str | None, *, fallback: int | None) -> int | None:
    """Resolve a resume cursor from the SSE header, falling back to the query."""
    if last_event_id is None:
        return fallback
    try:
        value = int(last_event_id.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Last-Event-ID must be an integer sequence"
        ) from exc
    if value < 0:
        raise HTTPException(status_code=400, detail="Last-Event-ID must not be negative")
    return value


async def _drain(websocket: WebSocket) -> None:
    """Read until the client goes away, so a disconnect is noticed promptly.

    A send-only loop learns about a dead peer only when the TCP stack gives up,
    which is far longer than an analyst will wait for a banner to appear.

    The disconnect message is checked for explicitly rather than relied on to
    raise: a server that hands the same message back on every read would turn
    this into a busy loop that never ends, and the reader is the one place in
    the route where a leak costs a loop's worth of CPU.
    """
    while True:
        message = await websocket.receive()
        if message.get("type") == "websocket.disconnect":
            raise WebSocketDisconnect(message.get("code") or 1000)


async def _send_frames(
    websocket: WebSocket,
    frames: AsyncIterator[Frame],
) -> None:
    """Forward frames to the socket until the subscription ends."""
    async for kind, payload in frames:
        await websocket.send_json({"type": kind, **payload})
        if kind == "dropped":
            await websocket.close(code=CLOSE_TRY_AGAIN_LATER)
            return


@router.websocket("/ws")
async def alert_socket(
    websocket: WebSocket,
    after: int | None = Query(default=None, ge=0),
) -> None:
    """Push alerts over a WebSocket, resuming from the client's cursor.

    The handshake is authenticated before it is accepted, with the same
    capability table the HTTP dependency uses, and refused with 4401/4403 so a
    client can tell "log in again" from "you may not read alerts".
    """
    try:
        authenticate(
            _socket_headers(websocket),
            _socket_token_service(websocket),
            Capability.READ,
        )
    except Unauthenticated:
        await websocket.close(code=CLOSE_UNAUTHENTICATED)
        return
    except Forbidden:
        # Deliberately not caught class-by-class above: the handshake reuses the
        # same refusal types the HTTP dependency raises, so the socket refuses
        # for the same reasons a request does.
        await websocket.close(code=CLOSE_FORBIDDEN)
        return

    offered = websocket.headers.get("sec-websocket-protocol", "")
    accepted = SUBPROTOCOL_PREFIX.rstrip(".") if SUBPROTOCOL_PREFIX in offered else None
    await websocket.accept(subprotocol=accepted)

    subscription, caught = _hub(websocket).subscribe(after=after)
    heartbeat = _settings(websocket).alert_stream_heartbeat_seconds
    frames = _frames(subscription, caught, heartbeat_seconds=heartbeat)
    sender = asyncio.create_task(_send_frames(websocket, frames))
    reader = asyncio.create_task(_drain(websocket))
    try:
        done, pending = await asyncio.wait({sender, reader}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            for task in pending:
                await task
        for task in done:
            task.result()
    except (WebSocketDisconnect, RuntimeError):
        # A client that disconnects, or a socket that errors, has no channel
        # left to be told anything on. What matters is that the subscription is
        # released below and that the cursor was in the last frame it received.
        pass
    finally:
        subscription.close()


def _socket_headers(websocket: WebSocket) -> Mapping[str, str]:
    """The handshake headers, with a browser's token subprotocol as a fallback.

    A browser cannot set an ``Authorization`` header on a WebSocket, and the
    token must not travel in the URL. The subprotocol header is the one place a
    browser *can* put it, so ``Sec-WebSocket-Protocol: aegis.bearer.<token>`` is
    accepted as a credential. It is a header, so it is as private as any other.
    """
    headers = dict(websocket.headers)
    if "authorization" in headers:
        return headers
    for offered in headers.get("sec-websocket-protocol", "").split(","):
        candidate = offered.strip()
        if candidate.startswith(SUBPROTOCOL_PREFIX):
            token = candidate[len(SUBPROTOCOL_PREFIX) :]
            headers["authorization"] = f"Bearer {token}"
            break
    return headers


def _socket_token_service(websocket: WebSocket) -> TokenService:
    """The token service, from application state."""
    service: TokenService | None = getattr(websocket.app.state, "token_service", None)
    if service is None:
        msg = "token_service is not configured on app.state"
        raise RuntimeError(msg)
    return service
