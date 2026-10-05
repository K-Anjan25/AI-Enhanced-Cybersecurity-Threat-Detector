"""Application factory and process entry point for the AEGIS backend.

Run with ``uvicorn app.main:app`` in development. Configuration errors are
reported as a single actionable line rather than a traceback (rule R-06).
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.middleware import (
    BodySizeLimitMiddleware,
    MetricsMiddleware,
    RateLimitMiddleware,
    TracingMiddleware,
)
from app.api.v1.endpoints import (
    alerts,
    api_keys,
    audit,
    health,
    ingest,
    metrics,
    models,
    privacy,
    stream,
    webhooks,
)
from app.auth.api_keys import InMemoryApiKeyStore, KeyDigest
from app.core.config import ConfigurationError, Settings, get_settings
from app.core.logging import bind_request_id, clear_request_context, configure_logging, get_logger
from app.db.models import PARTITIONED_TABLES
from app.observability.tracing import configure_tracing, exporter_for
from app.services.alert_stream import AlertHub
from app.services.audit_log import InMemoryAuditTrail
from app.services.erasure import (
    EntityRedactionTarget,
    ErasureService,
    InMemoryEntityStore,
    InMemoryErasureLedger,
    InMemoryUserStore,
    Redactor,
    UserDeletionTarget,
)
from app.services.health_service import ReadinessRegistry
from app.services.limits import AdmissionController, RateLimitPolicy
from app.services.model_ops import ModelOpsService
from app.services.retention import RetentionPolicy
from app.services.webhook_targets import (
    InMemoryWebhookStore,
    SecretVault,
    parse_allowlist,
    resolve_host,
)

__version__ = "0.1.0"

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware:
    """Attach a correlation id to every request and every log line it produces.

    Reuses an inbound ``X-Request-ID`` when present so a trace can be followed
    across services (NFR-07), and always echoes the id back on the response.

    Written as pure ASGI rather than with ``BaseHTTPMiddleware``, and that is a
    correctness requirement rather than a style choice: the base class runs the
    response through a task group that holds chunks until more arrive, so a
    response that does not end -- the SSE alert stream of T-310 -- never reaches
    the client at all. Pure ASGI passes messages through, so a frame is sent when
    it is produced.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Bind the id for this request and stamp it on the response."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        clear_request_context()
        bind_request_id(request_id)
        # The route's Request shares this scope, so `request.state.request_id`
        # is the same value the header gets.
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            """Echo the id on the response's first message."""
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            # The contextvars belong to the task that served this request; clear
            # them so a reused worker task cannot inherit the previous ids.
            clear_request_context()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure logging and declare startup/shutdown in one place."""
    settings: Settings = app.state.settings
    configure_logging(settings)
    logger = get_logger("aegis.backend")
    logger.info(
        "startup",
        service=settings.service_name,
        environment=settings.env.value,
        version=__version__,
    )
    try:
        yield
    finally:
        # Drop connected dashboards so they fall back to REST rather than
        # holding a socket that will never speak again (FR-20).
        app.state.alert_hub.close()
        logger.info("shutdown", service=settings.service_name)


def _known_partitions_stand_in() -> set[tuple[str, int, int]]:
    """The monthly partitions a deployment that has run for a while would have.

    A stand-in for the catalog query, and named as one. The real implementation
    reads ``pg_class`` for partitions of the tables in ``PARTITIONED_TABLES``; it
    is not written here because no session is wired into the request path (D-030),
    and a query that cannot be executed is better named than faked. What this
    returns is enough for the preview to show the boundary rule honestly: the last
    36 months for each partitioned table.
    """
    today = datetime.now(UTC).date()
    year, month = today.year, today.month - 35
    while month < 1:
        month += 12
        year -= 1
    present: set[tuple[str, int, int]] = set()
    cursor_year, cursor_month = year, month
    while (cursor_year, cursor_month) <= (today.year, today.month):
        for table in PARTITIONED_TABLES:
            present.add((table, cursor_year, cursor_month))
        cursor_month += 1
        if cursor_month == 13:
            cursor_year, cursor_month = cursor_year + 1, 1
    return present


def _no_runner(statement: str) -> bool:
    """Refuse to execute DDL, naming the missing wiring.

    Raise:
        RuntimeError: always. A retention run must not appear to succeed when the
            deployment has no database session to drop partitions through.
    """
    msg = (
        f"no partition runner is wired, so {statement!r} was not executed; "
        "wire app.state.partition_runner to a session-backed runner"
    )
    raise RuntimeError(msg)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application.

    Args:
        settings: configuration to use. When omitted, settings are loaded from
            the environment via :func:`app.core.config.get_settings`.

    Returns:
        A configured application with probes mounted at the root path.
    """
    resolved = settings if settings is not None else get_settings()

    app = FastAPI(
        title="AEGIS Backend",
        description=(
            "AI-Enhanced Cybersecurity Threat Detector — ingest and query API. "
            "See prd.md for requirements and architecture.md for design."
        ),
        version=__version__,
        lifespan=lifespan,
        # The application instruments itself (T-317). FastAPI >= 0.142 traces,
        # measures and logs every request natively; left on, a request would
        # produce a second server span under the same name, a second set of HTTP
        # metrics under the OpenTelemetry semantic-convention names rather than
        # the ones architecture.md §13 specifies, and -- worse for a deployment --
        # a second export path configured from ``OTEL_*`` environment variables
        # instead of from this application's settings. One instrumentation, and
        # this is it.
        telemetry={
            "tracing": False,
            "metrics": False,
            "logs": False,
            "auto_configure": False,
        },
    )

    app.state.settings = resolved
    app.state.service_name = resolved.service_name
    app.state.version = __version__
    app.state.environment = resolved.env.value
    # Dependencies register probes here as they are introduced (T-301, T-307).
    app.state.readiness = ReadinessRegistry()
    # One hub per process, because the sequences a client resumes from are
    # per-process; a multi-replica deployment needs a shared bus behind this
    # interface, which is named in the module docstring rather than implied.
    app.state.alert_hub = AlertHub()
    # Webhook configuration (T-311). The allowlist is parsed here, at startup,
    # so a malformed entry stops the process with a clear message instead of
    # failing the first alert delivery of the day (R-55).
    app.state.webhook_store = InMemoryWebhookStore()
    app.state.webhook_allowlist = parse_allowlist(resolved.webhook_allowlist)
    app.state.secret_vault = SecretVault(resolved.secret_key)
    # The audit trail (T-312, FR-42). Every mutating route appends here after its
    # work succeeded: a refused request changed nothing, and a row per attempt
    # would let a client fill the trail at will.
    app.state.audit_trail = InMemoryAuditTrail()
    # API keys (T-313, FR-44). The digest key is derived from the application
    # secret, so keys issued in this environment do not verify in another -- the
    # same per-deployment consequence the webhook vault documents. The store is
    # in-memory while no database session is wired into the request path (the gap
    # D-030 names); ``api_keys`` has its table and index in migration 0001, so
    # persistence is an adapter over ApiKeyStore rather than a schema change.
    app.state.api_key_store = InMemoryApiKeyStore()
    app.state.api_key_digest = KeyDigest(resolved.secret_key)
    # Retention and erasure (T-314, NFR-05, R-37). The policy comes from settings
    # and is validated here, at startup, so an inverted pair of windows stops the
    # process instead of failing the first retention run in production.
    app.state.retention_policy = RetentionPolicy(
        raw_records_days=resolved.retention_raw_records_days,
        alerts_days=resolved.retention_alerts_days,
        stats_days=resolved.retention_stats_days,
    )
    # The catalog and the statement runner are seams, not stand-ins that pretend:
    # nothing here can query pg_class or execute DDL without a session (D-030), so
    # the app is wired with a catalog of the months a deployment that has run for
    # a while would have, and a runner that refuses. The retention route fails
    # loudly rather than reporting a clean run it did not perform.
    app.state.known_partitions = _known_partitions_stand_in
    app.state.partition_runner = _no_runner
    # Erasure (NFR-05). Entity redaction and account deletion, over the in-memory
    # models of both stores, because neither table has an adapter here yet. The
    # ledger holds tombstones; the redactor derives them from AEGIS_SECRET_KEY.
    app.state.entity_store = InMemoryEntityStore()
    app.state.user_store = InMemoryUserStore(keys=app.state.api_key_store)
    app.state.erasure_ledger = InMemoryErasureLedger()
    # Model ops (T-315). Empty on purpose: R-74 forbids inventing a metric, so
    # nothing is registered until the model service registers a version, and the
    # endpoints are the contract the model service will be called through. The
    # authority for the lifecycle rules is ml-service's registry (T-212); this
    # restates them at the edge, which is a named gap, not a hidden duplicate.
    app.state.model_ops = ModelOpsService()
    app.state.erasure_service = ErasureService(
        [
            EntityRedactionTarget(app.state.entity_store),
            UserDeletionTarget(app.state.user_store),
        ],
        ledger=app.state.erasure_ledger,
        redactor=Redactor(resolved.secret_key),
    )
    # The one DNS seam (R-55). Production resolves for real; a test replaces this
    # attribute so a URL's fate is decided by the test rather than by whether a
    # name happens to resolve on the machine running the suite.
    app.state.webhook_resolver = resolve_host

    # Limits and back-pressure (R-56, T-316). The policy and the budget live on
    # app.state as well as in the middleware, so a test can tighten a limit without
    # rebuilding the application and an operator can change one without a deploy.
    app.state.rate_limit_policy = RateLimitPolicy(
        credential_per_minute=resolved.rate_limit_requests_per_minute,
        anonymous_per_minute=resolved.rate_limit_anonymous_per_minute,
        secret=resolved.secret_key,
    )
    app.state.max_request_bytes = resolved.max_request_bytes
    app.state.admission = AdmissionController(resolved.ingest_max_in_flight_records)

    # Tracing (NFR-07, T-317). Configured once per process and idempotent: empty
    # endpoint means no exporter, so ids are generated and propagated while
    # nothing leaves the process until a deployment names a collector.
    configure_tracing(
        exporter_for(resolved.otel_exporter_endpoint), service_name=resolved.service_name
    )

    # Order matters, and the last one added is outermost. The request id is bound
    # first, so a 429 or a 413 still carries X-Request-ID; tracing comes next so
    # its trace id is bound before the request observer writes the access line;
    # metrics and tracing sit outside the limiters so a refusal is counted and
    # traced like any other request; and the body cap is innermost because it must
    # not read a byte more than it has to.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=resolved.max_request_bytes)
    app.add_middleware(RateLimitMiddleware, policy=app.state.rate_limit_policy)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(TracingMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router)
    app.include_router(metrics.router)
    app.include_router(ingest.router)
    app.include_router(alerts.router)
    app.include_router(stream.router)
    app.include_router(webhooks.router)
    app.include_router(audit.router)
    app.include_router(api_keys.router)
    app.include_router(privacy.router)
    app.include_router(models.router)
    return app


def main() -> int:
    """Console entry point. Returns a process exit code."""
    try:
        settings = get_settings()
    except ConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.env.value == "development",
    )
    return 0


def __getattr__(name: str) -> object:
    """Build the ASGI app lazily so importing this module has no side effects.

    ``uvicorn app.main:app`` resolves the attribute and triggers configuration
    loading; merely importing the module (tests, linters, docs builds) does not.
    """
    if name == "app":
        try:
            return create_app()
        except ConfigurationError as exc:
            # Fail with an actionable message naming the bad variable.
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    raise SystemExit(main())
