"""ASGI middleware for request size caps and rate limiting (R-56, T-316).

Two middlewares, both pure ASGI rather than ``BaseHTTPMiddleware``: the base class
runs the response through a task group that holds chunks until more arrive, which
is why T-310's stream had to avoid it, and a body-counting wrapper is exactly the
kind of thing that must not be rewritten as a buffered one.

**The size cap rejects before parsing.** A declared ``Content-Length`` over the
limit is answered with 413 and the request body is never read. A body that arrives
without a length, or with one that lies, is counted as it streams: the middleware
wraps ``receive`` and answers 413 the moment the count crosses the limit, so no
parser sees more than the cap. Both halves matter -- the header check is an
optimisation for honest clients, the counting is the control.

**The rate limit sits in front of routing but behind nothing.** It runs for every
request R-56 covers -- every write method and every unauthenticated route -- using
``app.services.limits`` for the policy, so the same rules are testable without an
HTTP layer. Identity comes from the presented credential when there is one, and
from the client address otherwise; the credential is turned into a keyed
fingerprint immediately and never stored, logged or echoed (R-58).

The middleware reads the live policy from ``app.state.rate_limit_policy`` when it
is present, so a test or an operator can change the limits without rebuilding the
application, and falls back to the policy it was constructed with.
"""

from __future__ import annotations

import json
import time
from typing import Any

from opentelemetry.trace import SpanKind
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_500_INTERNAL_SERVER_ERROR
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import bind_trace_id, get_logger, unbind_trace_id
from app.observability import metrics
from app.observability.tracing import span, traceparent_for
from app.services.limits import RateLimitPolicy

__all__ = [
    "BODY_METHODS",
    "BODY_TOO_LARGE_DETAIL",
    "RATE_LIMIT_DETAIL",
    "BodySizeLimitMiddleware",
    "MetricsMiddleware",
    "route_template",
    "RateLimitMiddleware",
    "TracingMiddleware",
]

#: Methods whose bodies are capped. A GET or DELETE with a body is unusual enough
#: that capping it would mostly be a way to break an odd client; a write is where
#: the cost of parsing is, and every ingest route is a POST.
BODY_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH"})

RATE_LIMIT_DETAIL = "rate limit exceeded"
BODY_TOO_LARGE_DETAIL = "request body is larger than this service accepts"


class BodyTooLarge(Exception):  # noqa: N818 -- it is a signal, not an error response
    """Raised into the application to abort a body that crossed the cap."""


def _request_headers(scope: Scope) -> dict[str, str]:
    """The request headers, lower-cased, without constructing a ``Request``.

    The middleware runs before routing, so it should not depend on anything the
    routing layer sets up; reading ``scope["headers"]`` directly keeps it to the
    ASGI contract.
    """
    headers: dict[str, str] = {}
    for name, value in scope.get("headers", []):
        try:
            text = value.decode("latin-1")
        except UnicodeDecodeError:  # pragma: no cover - latin-1 decodes any bytes
            continue
        headers[name.decode("latin-1").lower()] = text
    return headers


def _credential(headers: dict[str, str]) -> str | None:
    """The presented credential, if any, for bucketing and for authentication.

    ``X-API-Key`` wins over a bearer token so a client that sets both is binned by
    the key it named; the authentication layer refuses that combination outright,
    and this only has to avoid putting two requests with one credential into two
    different buckets.
    """
    explicit = headers.get("x-api-key")
    if explicit:
        return explicit.strip()
    authorization = headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


async def _respond(
    send: Send, status: int, detail: str, *, extra: dict[str, str] | None = None
) -> None:
    """Send a minimal JSON response, with no body content from the request in it."""
    payload = json.dumps({"detail": detail}).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(payload)).encode()),
    ]
    for name, value in (extra or {}).items():
        headers.append((name.encode(), value.encode()))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})


class BodySizeLimitMiddleware:
    """Reject a body larger than ``max_bytes`` without handing it to the app (R-56)."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        """Wrap the application with a byte cap."""
        if max_bytes < 1:
            msg = f"a body size limit must accept at least one byte, got {max_bytes}"
            raise ValueError(msg)
        self.app = app
        self.max_bytes = max_bytes

    def _limit(self, scope: Scope) -> int:
        """The cap for this request: the state override when a test set one."""
        app: Any = scope.get("app")
        override = getattr(getattr(app, "state", None), "max_request_bytes", None)
        if isinstance(override, int) and override > 0:
            return override
        return self.max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Count the body as it arrives and abort past the cap."""
        if scope["type"] != "http" or scope.get("method", "").upper() not in BODY_METHODS:
            await self.app(scope, receive, send)
            return

        limit = self._limit(scope)
        declared = _request_headers(scope).get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            # Rejected on the header alone: the body is not read, so nothing
            # downstream parses any part of an oversized request.
            await _respond(
                send,
                413,
                f"{BODY_TOO_LARGE_DETAIL}: at most {limit} bytes",
                extra={"connection": "close"},
            )
            return

        received = 0
        response_started = False

        async def counted_receive() -> Message:
            """Pass the body through while the running total stays under the cap."""
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooLarge
            return message

        async def tracked_send(message: Message) -> None:
            """Remember whether a response has begun, so a late abort cannot double-send."""
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counted_receive, tracked_send)
        except BodyTooLarge:
            if response_started:  # pragma: no cover - a route that streams a response and reads on
                raise
            # `connection: close` because the rest of the request body was never
            # read: the connection cannot be reused for another request, and
            # saying so is what stops an intermediary from trying.
            await _respond(
                send,
                413,
                f"{BODY_TOO_LARGE_DETAIL}: at most {limit} bytes",
                extra={"connection": "close"},
            )


class RateLimitMiddleware:
    """Apply R-56's rate limits before the request reaches a route (T-316)."""

    def __init__(self, app: ASGIApp, *, policy: RateLimitPolicy) -> None:
        """Wrap the application with a rate limit policy."""
        self.app = app
        self.policy = policy

    def _policy(self, scope: Scope) -> RateLimitPolicy:
        """The live policy: the state override when set, else the constructed one."""
        app: Any = scope.get("app")
        override = getattr(getattr(app, "state", None), "rate_limit_policy", None)
        if isinstance(override, RateLimitPolicy):
            return override
        return self.policy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Take a token for the request's identity or answer 429."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        policy = self._policy(scope)
        method = scope.get("method", "")
        path = scope.get("path", "")
        headers = _request_headers(scope)
        decision = policy.check(
            method=method,
            path=path,
            credential=_credential(headers),
            client_ip=_client_ip(scope),
        )
        if not decision.allowed:
            # Retry-After is whole seconds (RFC 9110). No identity is echoed and no
            # limit is disclosed: the response says what to do, not who was counted.
            await _respond(
                send,
                429,
                RATE_LIMIT_DETAIL,
                extra={"retry-after": str(decision.retry_after)},
            )
            return
        await self.app(scope, receive, send)


def _client_ip(scope: Scope) -> str | None:
    """The peer address, as ASGI reports it: never a forwarded header.

    ``request.client`` is what the kernel saw. An ``X-Forwarded-For`` value is
    attacker-controlled unless a trusted proxy is known to set it, and a rate
    limiter keyed on a spoofable value is worse than one keyed on nothing -- a
    client could rotate the header to obtain a fresh bucket per request.
    """
    client = scope.get("client")
    if isinstance(client, (tuple, list)) and client:
        host = client[0]
        return str(host) if host else None
    return None


def route_template(scope: Scope) -> str | None:
    """The route template Starlette matched, or ``None`` if nothing matched.

    Read from the scope *after* the application has run: the router writes
    ``scope["route"]`` when it matches, and the same dict is mutated in place, so
    a middleware holding the reference can see it later. A request to a path no
    route claims stays ``None`` and is reported under one label.
    """
    template = getattr(scope.get("route"), "path", None)
    return template if isinstance(template, str) and template else None


class MetricsMiddleware:
    """Record golden signals per request, and log the request as one event (T-317, T-318).

    The route template, not the path: see :mod:`app.observability.metrics` for why
    a request-derived label is a memory-growth vector, and the same reasoning
    applies to the access line -- a path or a query string can carry an
    identifier, so neither is logged. The template is read from the scope after
    the application has run, and a request that matched no route logs
    ``unmatched``.

    A request that never produced a response start is recorded as 500, because
    that is what the client sees -- a connection that closes with no status is a
    failure from the client's side, and recording it as a success would hide
    exactly the requests worth looking at.

    The log line lives here rather than in a middleware of its own because this is
    the only layer that knows the status *and* the duration while both correlation
    ids are still bound: ``request_id`` from the outermost middleware and
    ``trace_id`` from the tracing middleware just outside this one. The level
    follows the outcome -- a 5xx is an error, a 4xx a warning -- so an alerting
    rule can be written against the level without parsing the status.
    """

    def __init__(self, app: ASGIApp, *, scrape_path: str = "/metrics") -> None:
        """Wrap the application, ignoring its own scrape traffic."""
        self.app = app
        self.scrape_path = scrape_path
        self._logger = get_logger("aegis.request")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Time the request and record its outcome, whatever the outcome is."""
        if scope["type"] != "http" or scope.get("path") == self.scrape_path:
            # A scrape is the observer, not the observed: counting it would make
            # the scrape interval a term in the service's own metrics.
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        started = time.perf_counter()
        status = 500

        async def tracked_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        finally:
            # `finally`, not `else`: a client that disconnects mid-request is a
            # request this process spent time on, and the duration histogram is
            # how that time becomes visible.
            route = route_template(scope)
            elapsed = max(0.0, time.perf_counter() - started)
            metrics.observe_http_request(method, route, status, elapsed)
            self._log_request(method, route, status, elapsed)

    def _log_request(self, method: str, route: str | None, status: int, elapsed: float) -> None:
        """Write the one structured line this request produces.

        Only labels and numbers: the route *template*, the status, the duration.
        No path, no query string, no identifier -- the correlation ids arrive from
        the context and the redaction processors of R-54 are the backstop.
        """
        fields: dict[str, Any] = {
            "method": method.upper(),
            "route": route or metrics.UNMATCHED_ROUTE,
            "status": status,
            "duration_ms": round(elapsed * 1000, 3),
        }
        if status >= HTTP_500_INTERNAL_SERVER_ERROR:
            self._logger.error("request", **fields)
        elif status >= HTTP_400_BAD_REQUEST:
            self._logger.warning("request", **fields)
        else:
            self._logger.info("request", **fields)


class TracingMiddleware:
    """Start a server span per request and carry the trace id both ways (T-317).

    Inbound: a valid W3C ``traceparent`` continues the caller's trace, so the
    collector's span and this request's span are the same trace. Outbound: the
    response carries ``traceparent`` and ``x-trace-id``, which is what makes the
    trace id of an ingest request available to the client that sent it -- and what
    the acceptance criterion reads back from the alert record.

    A malformed header is ignored rather than refused: refusing a batch of
    security telemetry over a broken tracing header trades the data for the
    telemetry. The span starts under a constant name and is renamed once the
    router has chosen a route, so a client-supplied path never becomes a span
    name it chose.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Open a span around the request and stamp the ids on the response."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        inbound = _request_headers(scope).get("traceparent")
        status = 0
        with span(f"{method} request", parent_traceparent=inbound, kind=SpanKind.SERVER) as active:
            traceparent = traceparent_for(active)
            trace_id = traceparent.split("-")[1] if traceparent else None
            if trace_id:
                # Bound for the whole request so every log line it produces can be
                # joined to the trace (T-318); unbound below, never left behind.
                bind_trace_id(trace_id)

            async def traced_send(message: Message) -> None:
                nonlocal status
                if message["type"] == "http.response.start":
                    status = int(message["status"])
                    if traceparent and trace_id:
                        headers = [*message["headers"], (b"traceparent", traceparent.encode())]
                        headers.append((b"x-trace-id", trace_id.encode()))
                        message = {**message, "headers": headers}
                await send(message)

            try:
                await self.app(scope, receive, traced_send)
            finally:
                unbind_trace_id()
                route = route_template(scope)
                active.update_name(f"{method} {route or 'unmatched'}")
                active.set_attribute("http.request.method", method)
                active.set_attribute("http.response.status_code", status)
                if route:
                    active.set_attribute("http.route", route)
