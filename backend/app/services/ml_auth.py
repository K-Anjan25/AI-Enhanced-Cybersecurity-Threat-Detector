"""Headers for calls to the ML service, carrying its shared secret.

The backend image does not install the ML package, so the header name is kept here
too. It must match ``aegis_ml.serving.service_auth.SERVICE_TOKEN_HEADER``. A test
asserts that they agree.
"""

from __future__ import annotations

#: Header the ML service reads the shared secret from.
SERVICE_TOKEN_HEADER = "X-AEGIS-Service-Token"  # noqa: S105 - a header name, not a secret


def ml_request_headers(token: str | None) -> dict[str, str]:
    """JSON headers, plus the shared secret when one is configured."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers[SERVICE_TOKEN_HEADER] = token
    return headers
