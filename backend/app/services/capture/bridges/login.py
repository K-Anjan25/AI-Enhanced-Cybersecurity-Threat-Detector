"""Sign a capture bridge in to the AEGIS API, reporting why a sign-in failed.

The bridges used to swallow every HTTP error and exit, so a 401 (wrong password), a
429 (login throttle) and an unreachable API all looked the same, and the container
restarted in a loop. This module reports the actual reason, waits out a 429 using
Retry-After, and backs off between attempts. It never logs the password.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable

#: Longest wait between attempts, in seconds.
MAX_BACKOFF = 60.0


class LoginFailed(RuntimeError):
    """Every attempt failed. The message says why the last one did."""


def _post_login(api: str, email: str, password: str, timeout: float) -> dict[str, object]:
    body = json.dumps({"email": email, "password": password}).encode()
    request = urllib.request.Request(  # noqa: S310 - the API URL is operator-configured
        f"{api}/api/v1/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310  # nosec B310
        parsed: dict[str, object] = json.loads(response.read())
        return parsed


def _retry_after(error: urllib.error.HTTPError, fallback: float) -> float:
    raw = error.headers.get("Retry-After") if error.headers else None
    try:
        return min(float(raw), MAX_BACKOFF) if raw is not None else fallback
    except ValueError:
        return fallback


def sign_in(
    api: str,
    email: str,
    password: str,
    *,
    log: Callable[[str], None],
    attempts: int = 8,
    timeout: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Return an access token, or raise :class:`LoginFailed` with the last reason."""
    reason = "no attempt was made"
    for attempt in range(1, attempts + 1):
        wait = min(2.0**attempt, MAX_BACKOFF)
        try:
            result = _post_login(api, email, password, timeout)
            token = result["access_token"]
            if not isinstance(token, str):
                raise ValueError("access_token is not a string")
            log(f"[AUTH] ✓ {result.get('subject', email)}")
            return token
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                wait = _retry_after(exc, fallback=wait)
                reason = "the API rate-limited sign-in (429); the login throttle is active"
            elif exc.code == 401:
                reason = (
                    "the API rejected the email or password (401). AEGIS_PASSWORD must "
                    "match the backend's AEGIS_BOOTSTRAP_ADMIN_PASSWORD"
                )
            elif exc.code == 404:
                reason = f"{api}/api/v1/auth/login was not found (404); check AEGIS_API_URL"
            else:
                reason = f"the API answered HTTP {exc.code} to sign-in"
        except urllib.error.URLError as exc:
            reason = f"cannot reach the API at {api} ({exc.reason})"
        except (OSError, ValueError, KeyError, TypeError) as exc:
            reason = f"unexpected sign-in response ({type(exc).__name__})"
        log(f"[AUTH] attempt {attempt}/{attempts} failed: {reason}")
        if attempt < attempts:
            sleep(wait)
    raise LoginFailed(reason)
