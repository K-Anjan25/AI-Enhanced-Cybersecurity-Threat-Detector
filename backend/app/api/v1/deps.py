"""Shared request-level helpers for the v1 endpoints (T-312, T-313).

Each helper is in one place for correctness rather than convenience:

* :func:`audit_trail` hands back the process-wide trail that every mutating route
  appends to. A route that built its own would write to a store nobody reads.
* :func:`client_ip` is the single definition of "the caller's address". FR-42
  records a source IP, and the failure mode is a route reading a header; one
  implementation is a place to get that wrong once rather than five places to get
  it wrong differently.
* :func:`api_key_store` and :func:`api_key_digest` are the two halves of the API
  key credential path (FR-44): where issued keys live, and the digest key that
  decides whether a presented string is one of them.
* :func:`alert_store` is where alert rows live (T-319): the query API reads back
  what the pipeline wrote, and both halves go through one composition root.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import Request

from app.auth.api_keys import ApiKeyStore, KeyDigest
from app.services.alert_store import AlertStore
from app.services.audit_log import AuditTrail
from app.services.erasure import ErasureService
from app.services.limits import AdmissionController
from app.services.model_ops import ModelOpsService
from app.services.recalibration import RecalibrationService
from app.services.retention import RetentionPolicy, StatementRunner

__all__ = [
    "admission",
    "alert_store",
    "api_key_digest",
    "api_key_store",
    "audit_trail",
    "client_ip",
    "erasure_service",
    "known_partitions",
    "model_ops",
    "parse_instant",
    "partition_runner",
    "recalibration_service",
    "retention_policy",
]


def audit_trail(request: Request) -> AuditTrail:
    """The application's audit trail.

    Raises:
        RuntimeError: if the composition root never installed one. Loudly, since
            a mutating route without a trail is the FR-42 gap this task exists to
            close, and a silent fallback would hide it.
    """
    trail: AuditTrail | None = getattr(request.app.state, "audit_trail", None)
    if trail is None:
        msg = "audit_trail is not configured on app.state"
        raise RuntimeError(msg)
    return trail


def alert_store(request: Request) -> AlertStore:
    """The store alert rows live in.

    Raises:
        RuntimeError: if the composition root never installed one. Loudly, because
            a query API reading an empty store that no one ever wrote to is
            indistinguishable from a quiet network -- the failure mode this seam
            exists to make visible.
    """
    store: AlertStore | None = getattr(request.app.state, "alert_store", None)
    if store is None:
        msg = "alert_store is not configured on app.state"
        raise RuntimeError(msg)
    return store


def api_key_store(request: Request) -> ApiKeyStore:
    """The store issued keys live in.

    Raises:
        RuntimeError: if the composition root never installed one. Loudly: the
            alternative is an ingest route that 401s every machine credential
            with no clue why, or -- worse -- one that skips key verification.
    """
    store: ApiKeyStore | None = getattr(request.app.state, "api_key_store", None)
    if store is None:
        msg = "api_key_store is not configured on app.state"
        raise RuntimeError(msg)
    return store


def api_key_digest(request: Request) -> KeyDigest:
    """The digest function for this deployment's application secret.

    Raises:
        RuntimeError: if it was never derived from the settings. The digest key
            comes from ``AEGIS_SECRET_KEY`` via HKDF, so it is per-deployment and
            it is not reachable from a request.
    """
    digest: KeyDigest | None = getattr(request.app.state, "api_key_digest", None)
    if digest is None:
        msg = "api_key_digest is not configured on app.state"
        raise RuntimeError(msg)
    return digest


def retention_policy(request: Request) -> RetentionPolicy:
    """The deployment's retention windows.

    Raises:
        RuntimeError: if none is installed. Loudly: a default policy invented here
            would quietly disagree with the settings an operator configured.
    """
    policy: RetentionPolicy | None = getattr(request.app.state, "retention_policy", None)
    if policy is None:
        msg = "retention_policy is not configured on app.state"
        raise RuntimeError(msg)
    return policy


def known_partitions(request: Request) -> set[tuple[str, int, int]]:
    """The monthly partitions this deployment can see, as ``(table, year, month)``.

    A dependency rather than a query in the route: there is no database session in
    the request path yet (D-030), and a test proving a boundary case should not
    need one. The wired implementation is the stand-in described in ``main.py``.

    Raises:
        RuntimeError: if nothing is wired, for the same reason as the policy.
    """
    provider: object = getattr(request.app.state, "known_partitions", None)
    if provider is None:
        msg = "known_partitions is not configured on app.state"
        raise RuntimeError(msg)
    if callable(provider):
        value: set[tuple[str, int, int]] = provider()
        return value
    if isinstance(provider, (set, frozenset, list, tuple)):
        return {(str(table), int(year), int(month)) for table, year, month in provider}
    msg = f"known_partitions must be a callable or a collection, got {type(provider).__name__}"
    raise RuntimeError(msg)


def partition_runner(request: Request) -> StatementRunner:
    """The callable that executes one DDL statement against the real database.

    Raises:
        RuntimeError: if none is wired. A retention run with no runner must fail
            loudly rather than report a clean run that dropped nothing.
    """
    runner: StatementRunner | None = getattr(request.app.state, "partition_runner", None)
    if runner is None:
        msg = (
            "partition_runner is not configured on app.state: the retention job "
            "refuses to report a run it cannot execute"
        )
        raise RuntimeError(msg)
    return runner


def erasure_service(request: Request) -> ErasureService:
    """The erasure cascade.

    Raises:
        RuntimeError: if none is installed. The alternative -- constructing one per
            request with no targets -- would report a successful erasure of
            nothing, and the service refuses to be built that way.
    """
    service: ErasureService | None = getattr(request.app.state, "erasure_service", None)
    if service is None:
        msg = "erasure_service is not configured on app.state"
        raise RuntimeError(msg)
    return service


def model_ops(request: Request) -> ModelOpsService:
    """The registry of model versions this deployment serves from.

    Raises:
        RuntimeError: if none is installed. The alternative -- an empty service
            built per request -- would answer "no models are registered" for a
            deployment that has some, which is the kind of confident wrong answer
            this codebase refuses.
    """
    service: ModelOpsService | None = getattr(request.app.state, "model_ops", None)
    if service is None:
        msg = "model_ops is not configured on app.state"
        raise RuntimeError(msg)
    return service


def admission(request: Request) -> AdmissionController:
    """The bounded in-flight budget the ingest API consults before accepting a batch.

    Raises:
        RuntimeError: if none is installed. An unwired budget must fail loudly: the
            alternative is an ingest path that accepts everything and drops later,
            which is the silent-loss failure architecture.md §12 names.
    """
    controller: AdmissionController | None = getattr(request.app.state, "admission", None)
    if controller is None:
        msg = "admission is not configured on app.state"
        raise RuntimeError(msg)
    return controller


def recalibration_service(request: Request) -> RecalibrationService:
    """The threshold job: the store in force, the feedback and the calibrator.

    Raises:
        RuntimeError: if none is installed. The alternative -- a service built per
            request over an empty store -- would report a clean run that read no
            feedback and moved nothing, which is indistinguishable from a quiet
            fortnight.
    """
    service: RecalibrationService | None = getattr(request.app.state, "recalibration", None)
    if service is None:
        msg = "recalibration is not configured on app.state"
        raise RuntimeError(msg)
    return service


def client_ip(request: Request) -> str | None:
    """The address the request arrived from, or ``None`` when there is none.

    ``request.client`` is the **peer** -- the socket -- never
    ``X-Forwarded-For``, which any client can set and which would therefore let
    the audited party choose what the record says about them. Behind a proxy the
    peer is the proxy; making this the real origin is uvicorn's
    ``--proxy-headers`` with ``--forwarded-allow-ips`` naming that proxy, which is
    deployment configuration and is named in the module docstring of
    ``app.services.audit_log`` rather than guessed at here.
    """
    client = request.client
    return client.host if client is not None else None


def parse_instant(value: str, *, name: str) -> datetime:
    """Parse an ISO-8601 instant, refusing anything unusable.

    Raises:
        ValueError: if the value is not a timestamp, or is naive. A naive
            timestamp against a ``timestamptz`` column is read in the session's
            zone, which silently shifts the window an auditor asked for.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        msg = f"{name} must be an ISO-8601 timestamp"
        raise ValueError(msg) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        msg = (
            f"{name} must carry a timezone; a naive timestamp means a different "
            "instant than the one the row was stored with"
        )
        raise ValueError(msg)
    return parsed
