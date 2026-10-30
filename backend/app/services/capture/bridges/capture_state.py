"""Read the desired capture state from the control plane, for the capture entrypoint.

Prints one line, ``<running 0|1> <version> <engines,csv or ->``, and exits 0. On failure
it prints the reason to stderr and exits 1, and the entrypoint keeps the engines it has.

The access token is cached in a file. Signing in on every poll would hit the login
throttle within minutes, so the token is reused and only fetched again after a 401.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from login import LoginFailed, sign_in

STATE_PATH = "/api/v1/capture/state"


def _get_state(api: str, token: str, timeout: float) -> dict[str, object]:
    request = urllib.request.Request(  # noqa: S310 - the API URL is operator-configured
        f"{api}{STATE_PATH}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310  # nosec B310
        parsed: dict[str, object] = json.loads(response.read())
        return parsed


def fetch_state(
    api: str,
    email: str,
    password: str,
    *,
    token_file: Path,
    log: Callable[[str], None],
    timeout: float = 5.0,
) -> str:
    """Return the state line. Raises on any failure, including a sign-in failure."""
    token = token_file.read_text().strip() if token_file.exists() else ""
    for attempt in (1, 2):
        if not token:
            token = sign_in(api, email, password, log=log, attempts=2, timeout=timeout)
            token_file.write_text(token)
            os.chmod(token_file, 0o600)
        try:
            state = _get_state(api, token, timeout)
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and attempt == 1:
                token = ""  # the cached token expired; sign in once more
                continue
            raise
        running = 1 if state["running"] else 0
        engines = ",".join(str(name) for name in state["engines"]) or "-"  # type: ignore[union-attr]
        return f"{running} {state['version']} {engines}"
    raise RuntimeError("capture state could not be read after re-signing in")


def main() -> int:
    """Entry point used by the capture entrypoint."""
    api = os.environ.get("AEGIS_API_URL", "http://localhost:8000")
    email = os.environ.get("AEGIS_EMAIL", "admin@aegis.local")
    password = os.environ.get("AEGIS_PASSWORD", "")
    token_file = Path(os.environ.get("AEGIS_CAPTURE_TOKEN_FILE", "/tmp/aegis-capture-token"))  # noqa: S108 - private, mode 0600
    try:
        line = fetch_state(
            api,
            email,
            password,
            token_file=token_file,
            log=lambda message: print(message, file=sys.stderr),
        )
    except (LoginFailed, urllib.error.URLError, OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"capture state unavailable: {exc}", file=sys.stderr)
        return 1
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
