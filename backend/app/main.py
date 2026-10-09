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
from app.api.openapi_docs import declare_components
from app.api.v1.endpoints import (
    alerts,
    api_keys,
    audit,
    auth,
    flows,
    health,
    hunt,
    ingest,
    logs,
    metrics,
    models,
    overview,
    privacy,
    stream,
    thresholds,
    users,
    webhooks,
)
from app.auth.api_keys import InMemoryApiKeyStore, KeyDigest
from app.auth.tokens import TokenService
from app.core.config import ConfigurationError, Settings, get_settings
from app.core.logging import bind_request_id, clear_request_context, configure_logging, get_logger
from app.db.engine import async_session_factory, create_async_database_engine
from app.db.models import PARTITIONED_TABLES
from app.observability.tracing import configure_tracing, exporter_for
from app.schemas.ingest import FlowRecordIn, LogRecordIn
from app.services.alert_store import InMemoryAlertStore
from app.services.alert_stream import AlertHub
from app.services.detection_engine import DetectionEngine
from app.services.drift_monitor import DriftMonitor
from app.services.model_registrar import ModelRegistrar
from app.services.audit_log import InMemoryAuditTrail
from app.services.auth_accounts import AuthAccountStore
from app.services.entity_registry import EntityRegistry
from app.services.erasure import (
    EntityRedactionTarget,
    ErasureService,
    InMemoryEntityStore,
    InMemoryErasureLedger,
    InMemoryUserStore,
    Redactor,
    UserDeletionTarget,
)
from app.services.flow_read_model import InProcessFlowRollup
from app.services.flow_source import RollupFlowSource, flow_rollup_reason
from app.services.flow_store import PostgresFlowStore
from app.services.health_service import ReadinessRegistry
from app.services.limits import AdmissionController, RateLimitPolicy
from app.services.log_source import TailLogSource, store_requested, tail_reason
from app.services.log_store import PostgresLogStore
from app.services.log_tail import LogTail
from app.services.ml_calibration import MlCalibrator
from app.services.model_ops import ModelOpsService
from app.services.recalibration import (
    DEFAULT_TENANT_ID,
    AlertVerdictFeedback,
    InMemoryThresholdStore,
    RecalibrationService,
)
from app.services.retention import RetentionPolicy
from app.services.threshold_admin import ThresholdAdminService, ThresholdImpactReader
from app.services.user_directory import InMemoryUserDirectory, UserAdminService
from app.services.verdict_service import (
    InMemoryVerdictLedger,
)
from app.services.webhook_deliveries import InMemoryDeliveryLog
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
    # Start the rule-based detection engine
    detection_engine = getattr(app.state, "detection_engine", None)
    if detection_engine is not None:
        detection_engine.start()
        logger.info("detection_engine_started", interval=15)
    # Start the drift monitor (T-421)
    drift_monitor = getattr(app.state, "drift_monitor", None)
    if drift_monitor is not None:
        drift_monitor.start()
        logger.info("drift_monitor_started")
    # Start the model registrar (model_ops exists now, created in create_app)
    ml_url = getattr(app.state.settings, 'ml_service_url', None) or "http://ml-service:8001"
    model_registrar = ModelRegistrar(
        ml_service_url=ml_url,
        model_ops=app.state.model_ops,
        interval=30.0,
    )
    app.state.model_registrar = model_registrar
    model_registrar.start()
    logger.info("model_registrar_started")
    try:
        yield
    finally:
        # Stop the detection engine
        if detection_engine is not None:
            detection_engine.stop()
        # Stop the drift monitor
        if drift_monitor is not None:
            drift_monitor.stop()
        # Stop the model registrar
        if model_registrar is not None:
            model_registrar.stop()
        # Drop connected dashboards so they fall back to REST rather than
        # holding a socket that will never speak again (FR-20).
        app.state.alert_hub.close()
        # Close the read models' pooled connections (T-418/T-419). A deployment that
        # configured a store opened them; leaving them to the garbage collector on a
        # rolling restart is how a database accumulates half-closed sessions.
        engine = getattr(app.state, "store_engine", None)
        if engine is not None:
            await engine.dispose()
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
    # Protected routes used to reach RBAC without the composition root installing
    # its token verifier, turning every authenticated request into a 500. Make the
    # same signed-token service available to REST, WebSocket and auth endpoints.
    app.state.token_service = TokenService(resolved.secret_key)
    app.state.service_name = resolved.service_name
    app.state.version = __version__
    app.state.environment = resolved.env.value
    # Dependencies register probes here as they are introduced (T-301, T-307).
    app.state.readiness = ReadinessRegistry()
    # One hub per process, because the sequences a client resumes from are
    # per-process; a multi-replica deployment needs a shared bus behind this
    # interface, which is named in the module docstring rather than implied.
    app.state.alert_hub = AlertHub()
    # The store the query API reads and the pipeline writes (T-319). In memory
    # here, like every other store in this environment; D-053 records the
    # PostgreSQL adapter as unwired and the case-id column it would need.
    app.state.alert_store = InMemoryAlertStore()
    # Rule-based detection engine: runs in background, reads buffered flows,
    # applies heuristic rules, and writes alerts to the alert store.
    app.state.detection_engine = DetectionEngine(
        app.state.alert_store,
        interval=15.0,
        max_buffer=10_000,
    )
    # Drift monitor (T-421): computes PSI from recent flows and publishes
    # aegis_drift_psi{feature} gauges to /metrics so the DriftPage draws bars.
    ml_service_url = getattr(resolved, 'ml_service_url', None) or "http://ml-service:8001"
    app.state.drift_monitor = DriftMonitor(
        interval=60.0,
        ml_service_url=ml_service_url,
    )
    # The entity registry (T-416). The same object type the pipeline allocates ids
    # from, so an alert written by this process can be rendered by name: the
    # overview resolves `entity_id` through it. D-053 records the persistent
    # writer (`entities`) as unwired, like the store above.
    app.state.entity_registry = EntityRegistry()
    # The log tail (T-407). A bounded in-process copy of the accepted lines, for the
    # deployment that has no log store -- and the thing the store's own wiring below
    # replaces when the deployment configures one.
    app.state.log_tail = LogTail(
        max_lines=resolved.log_tail_lines,
        max_age_seconds=resolved.log_tail_max_age_seconds,
    )
    # The log read model (T-419). Which of the two answers is decided here, once, and
    # it is a question about configuration rather than a probe: `auto` uses the store
    # when the deployment *named* a database URL, and the tail when only the built-in
    # default exists. A store that was configured and is unreachable raises on read
    # rather than falling back -- answering a 92-day window from a 15-minute buffer
    # would look exactly like "nothing matched", which is what R-70 forbids.
    #
    # The engine is built here but opens nothing: SQLAlchemy connects on first use, so
    # a process whose database is not up yet still starts and reports it through
    # readiness rather than refusing to boot.
    named_url = "database_url" in resolved.model_fields_set
    log_store_on = store_requested(resolved.log_store, database_url_named=named_url)
    flow_store_on = store_requested(resolved.flow_store, database_url_named=named_url)
    # One engine for both read models: two stores with one database is one pool, and a
    # deployment that has only one of them switched on still opens only one. It is built
    # (lazily -- ``create_async_engine`` opens nothing) and then judged, so a deployment
    # whose database is down still starts and answers 503 on the routes that need it.
    app.state.store_engine = (
        create_async_database_engine(resolved.database_url)
        if log_store_on or flow_store_on
        else None
    )
    if log_store_on:
        app.state.log_source = PostgresLogStore(
            async_session_factory(app.state.store_engine),
            coverage_ttl_seconds=resolved.log_store_coverage_ttl_seconds,
        )
    else:
        app.state.log_source = TailLogSource(
            app.state.log_tail, reason=tail_reason(resolved.log_store)
        )
    if flow_store_on:
        app.state.flow_source = PostgresFlowStore(
            async_session_factory(app.state.store_engine),
            coverage_ttl_seconds=resolved.log_store_coverage_ttl_seconds,
        )
    else:
        app.state.flow_source = RollupFlowSource(
            InProcessFlowRollup(retention_minutes=resolved.flow_rollup_minutes),
            reason=flow_rollup_reason(resolved.flow_store),
        )
    # Webhook configuration (T-311). The allowlist is parsed here, at startup,
    # so a malformed entry stops the process with a clear message instead of
    # failing the first alert delivery of the day (R-55).
    app.state.webhook_store = InMemoryWebhookStore()
    app.state.webhook_allowlist = parse_allowlist(resolved.webhook_allowlist)
    app.state.secret_vault = SecretVault(resolved.secret_key)
    # The delivery read model (T-422): where every attempt the sender makes is
    # recorded, so the connectors screen can answer "did that endpoint take
    # anything, and if not, why not". In-memory and bounded, like the store it
    # describes, and the route says both in its caveats.
    #
    # No sender is built, and that is T-311's decision rather than an omission:
    # the HTTP transport was deliberately left unwritten because there is no
    # network in this environment to verify one against, so ``webhook_sender`` is
    # absent and the test route refuses with that reason. When a transport exists,
    # it is built here with ``on_report=sender_sink(app.state.webhook_deliveries)``
    # and every attempt -- pipeline or probe -- lands in this log.
    app.state.webhook_deliveries = InMemoryDeliveryLog()
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
    # Verdicts (T-309) live on app.state rather than being created on first use by
    # the route, so the recalibration job (T-322) reads the same ledger the verdict
    # route writes. Two instances would mean a weekly job fitting on feedback that
    # never arrives, and nothing would look wrong.
    app.state.verdict_ledger = InMemoryVerdictLedger()
    # Thresholds (T-322, FR-18). The store holds the values in force, starting
    # empty: R-69's documented initial values are FR-13's band edges, which the
    # job falls back to per family and the listing returns as `defaults`, so no
    # family is invented before there is feedback for it. The feedback is the
    # verdict ledger joined to the alert store through the query API's own paging,
    # and the calibrator is T-207's, reached through the ML package this image
    # does not install (MlCalibrator names that dependency when it is called). The
    # tenant is a stand-in for attribution the alert row cannot supply yet: it has
    # no tenant column, so the source refuses to serve any tenant but this one
    # rather than mixing two.
    app.state.threshold_store = InMemoryThresholdStore()
    app.state.recalibration = RecalibrationService(
        store=app.state.threshold_store,
        feedback=AlertVerdictFeedback(
            app.state.alert_store,
            app.state.verdict_ledger,
            tenant_id=DEFAULT_TENANT_ID,
        ),
        calibrator=MlCalibrator(),
    )
    # Model ops (T-315). Empty on purpose: R-74 forbids inventing a metric, so
    # nothing is registered until the model service registers a version, and the
    # endpoints are the contract the model service will be called through. The
    # authority for the lifecycle rules is ml-service's registry (T-212); this
    # restates them at the edge, which is a named gap, not a hidden duplicate.
    app.state.model_ops = ModelOpsService()
    # The user directory and authentication accounts (T-410/T-417). The default
    # is still empty; there is no built-in demo identity. An operator can seed the
    # initial administrator from environment-provided credentials, or explicitly
    # enable the development-only first-account form. Both use the same in-memory
    # directory, and both remain process-local until the database adapter lands.
    user_directory = InMemoryUserDirectory()
    app.state.auth_accounts = AuthAccountStore(user_directory)
    if resolved.bootstrap_admin_email is not None and resolved.bootstrap_admin_password is not None:
        app.state.auth_accounts.create_initial_admin(
            resolved.bootstrap_admin_email,
            resolved.bootstrap_admin_password.get_secret_value(),
        )
    app.state.user_admin = UserAdminService(directory=user_directory)
    # The hand-set threshold panel (T-410). It reads and writes the same store the
    # recalibration job does, so a value a person set and a value the job fitted
    # cannot live in two places -- and the preview counts against the alert store
    # the query API reads.
    app.state.threshold_admin = ThresholdAdminService(
        store=app.state.threshold_store, tenant_id=DEFAULT_TENANT_ID
    )
    app.state.threshold_impact = ThresholdImpactReader(
        alerts=app.state.alert_store, admin=app.state.threshold_admin
    )
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
    # The ingest routes read their bytes and declare their body schema with
    # ``openapi_extra``; this adds the record models that body references, so the
    # generated `/openapi.json` -- and the reference rendered from it -- names a
    # schema that exists (T-320).
    declare_components(app, (FlowRecordIn, LogRecordIn))
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(metrics.router)
    app.include_router(ingest.router)
    # ``stream`` comes first because its paths are literal where ``alerts`` now has
    # a parameterised one (``/alerts/{alert_id}``, T-404): Starlette matches in
    # registration order and a literal path never falls through a converter that
    # failed on it, so ``/alerts/stream`` would otherwise be read as an alert id.
    app.include_router(stream.router)
    app.include_router(logs.router)
    # The flow read route (T-418) shares ``/api/v1/flows`` with the ingest route and
    # differs by method, so it must be registered with the same path and not shadowed:
    # ``ingest`` owns POST, this owns GET.
    app.include_router(flows.router)
    app.include_router(hunt.router)
    app.include_router(alerts.router)
    app.include_router(overview.router)
    app.include_router(webhooks.router)
    app.include_router(audit.router)
    app.include_router(api_keys.router)
    app.include_router(privacy.router)
    app.include_router(models.router)
    app.include_router(thresholds.router)
    app.include_router(users.router)
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
