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
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.services.limits import RateLimitPolicy

__all__ = [
    "BODY_METHODS",
    "BODY_TOO_LARGE_DETAIL",
    "RATE_LIMIT_DETAIL",
    "BodySizeLimitMiddleware",
    "RateLimitMiddleware",
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
