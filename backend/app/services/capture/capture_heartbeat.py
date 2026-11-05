#!/usr/bin/env python3
"""Report real liveness from the supervised Docker capture container to AEGIS."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
import threading
import urllib.error
import urllib.request
from collections.abc import Sequence

API_URL = os.environ.get("AEGIS_API_URL", "http://localhost:8000")
EMAIL = os.environ.get("AEGIS_EMAIL", "admin@aegis.local")
PASSWORD = os.environ.get("AEGIS_PASSWORD", "")
SENSOR_ID = os.environ.get("AEGIS_CAPTURE_SENSOR_ID", "docker-host-capture")
ENGINES = os.environ.get("AEGIS_CAPTURE_ENGINES", "zeek,suricata,tshark")
HEARTBEAT_SECONDS = os.environ.get("AEGIS_CAPTURE_HEARTBEAT_SECONDS", "15")
_SUPPORTED_ENGINES = frozenset({"zeek", "suricata", "tshark"})
_SENSOR_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class HeartbeatReporter:
    """Authenticate once, then send a small heartbeat with bounded retry delays."""

    def __init__(
        self, api_url: str, email: str, password: str, sensor_id: str, engines: Sequence[str]
    ) -> None:
        """Store only the fields needed to report this process's configured engines."""
        self.api_url = api_url.rstrip("/")
        self.email = email
        self.password = password
        self.sensor_id = sensor_id
        self.engines = list(engines)
        self.token = ""  # nosec B105 - no access token has been obtained yet

    def _login(self) -> bool:
        """Obtain a normal access token; capture startup seeds this admin in Compose."""
        body = json.dumps({"email": self.email, "password": self.password}).encode()
        request = urllib.request.Request(  # noqa: S310 - API URL is operator-configured
            f"{self.api_url}/api/v1/auth/login",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310  # nosec B310
                payload = json.loads(response.read())
            token = payload.get("access_token")
            if not isinstance(token, str) or not token:
                return False
            self.token = token
            return True
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            print(f"[CAPTURE-HEARTBEAT] login unavailable: {exc}", file=sys.stderr)
            return False

    def send_once(self) -> bool:
        """Send a heartbeat; a 401 clears the token so the next pass reauthenticates."""
        if not self.token and not self._login():
            return False
        body = json.dumps({"sensor_id": self.sensor_id, "engines": self.engines}).encode()
        request = urllib.request.Request(  # noqa: S310 - API URL is operator-configured
            f"{self.api_url}/api/v1/capture/heartbeat",
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310  # nosec B310
                response_status = response.status
                return isinstance(response_status, int) and response_status == 200
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                self.token = ""  # nosec B105 - discard an expired access token
            print(f"[CAPTURE-HEARTBEAT] report refused: HTTP {exc.code}", file=sys.stderr)
            return False
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(f"[CAPTURE-HEARTBEAT] report unavailable: {exc}", file=sys.stderr)
            return False


def main() -> int:
    """Validate configuration and report until the container is asked to stop."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default=API_URL)
    parser.add_argument("--email", default=EMAIL)
    parser.add_argument("--password", default=PASSWORD)
    parser.add_argument("--sensor-id", default=SENSOR_ID)
    parser.add_argument("--engines", default=ENGINES)
    parser.add_argument("--interval", type=float, default=HEARTBEAT_SECONDS)
    args = parser.parse_args()
    engines = [engine.strip() for engine in args.engines.split(",") if engine.strip()]
    if (
        not args.password
        or not 1 <= args.interval <= 30
        or not engines
        or len(set(engines)) != len(engines)
        or not set(engines).issubset(_SUPPORTED_ENGINES)
        or _SENSOR_ID_PATTERN.fullmatch(args.sensor_id) is None
    ):
        print("[CAPTURE-HEARTBEAT] invalid heartbeat configuration", file=sys.stderr)
        return 2

    reporter = HeartbeatReporter(args.api, args.email, args.password, args.sensor_id, engines)
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stopped.set())
    signal.signal(signal.SIGINT, lambda _signum, _frame: stopped.set())
    print(
        f"[CAPTURE-HEARTBEAT] reporting sensor {args.sensor_id} every {args.interval:g}s",
        file=sys.stderr,
    )

    retry_seconds = min(2.0, args.interval)
    while not stopped.is_set():
        if reporter.send_once():
            retry_seconds = min(2.0, args.interval)
            stopped.wait(args.interval)
        else:
            stopped.wait(retry_seconds)
            retry_seconds = min(max(retry_seconds * 2, 1.0), args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
