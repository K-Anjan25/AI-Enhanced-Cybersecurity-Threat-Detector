"""Shared-secret authentication for the ML service's inference and model routes.

Every caller of the ML service is another AEGIS process: the backend's window
scorer, its model registrar, and the drift monitor. None of them is a person, so
the check is a shared secret sent in a header, ``AEGIS_ML_SERVICE_TOKEN`` on both
sides, compared in constant time.

The check fails closed. With no token configured, protected routes answer 503
rather than opening up, so a deployment that forgets the secret cannot quietly
serve unauthenticated scores. Liveness and readiness probes stay public: an
orchestrator must be able to see the process without the secret.
"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status

#: Header a caller presents the shared secret in.
SERVICE_TOKEN_HEADER = "X-AEGIS-Service-Token"  # noqa: S105 - a header name, not a secret
#: Environment variable both services read the secret from.
SERVICE_TOKEN_ENV = "AEGIS_ML_SERVICE_TOKEN"


def require_service_token(request: Request) -> None:
    """Admit a request only when it presents the configured shared secret."""
    expected: str | None = getattr(request.app.state, "service_token", None)
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="the ML service token is not configured; protected routes are disabled",
        )
    presented = request.headers.get(SERVICE_TOKEN_HEADER, "")
    if not hmac.compare_digest(presented.encode(), expected.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="a valid service token is required",
            headers={"WWW-Authenticate": "AEGIS-Service-Token"},
        )
