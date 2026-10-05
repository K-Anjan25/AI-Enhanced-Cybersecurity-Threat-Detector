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
"""

from __future__ import annotations

from datetime import datetime

from fastapi import Request

from app.auth.api_keys import ApiKeyStore, KeyDigest
from app.services.audit_log import AuditTrail

__all__ = [
    "api_key_digest",
    "api_key_store",
    "audit_trail",
    "client_ip",
    "parse_instant",
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
