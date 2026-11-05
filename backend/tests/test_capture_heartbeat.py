"""The Docker capture reporter sends authenticated liveness, not traffic."""

from __future__ import annotations

import io
import json
import urllib.error

from app.services.capture import capture_heartbeat
from app.services.capture.capture_heartbeat import HeartbeatReporter


class _Response:
    def __init__(self, payload: dict[str, str] | None = None, status: int = 200) -> None:
        self.payload = payload or {}
        self.status = status

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def test_reporter_logs_in_and_posts_configured_engine_heartbeat(monkeypatch) -> None:
    requests = []

    def fake_urlopen(request, timeout: int) -> _Response:
        requests.append((request, timeout))
        if request.full_url.endswith("/api/v1/auth/login"):
            return _Response({"access_token": "session-token"})
        return _Response()

    monkeypatch.setattr(capture_heartbeat.urllib.request, "urlopen", fake_urlopen)
    reporter = HeartbeatReporter(
        "http://backend:8000/",
        "sensor@corp",
        "fixture-credential",
        "edge-01",
        ["zeek", "suricata", "tshark"],
    )

    assert reporter.send_once()
    assert len(requests) == 2
    login, heartbeat = [request for request, _timeout in requests]
    assert login.full_url == "http://backend:8000/api/v1/auth/login"
    assert json.loads(login.data) == {
        "email": "sensor@corp",
        "password": "fixture-credential",  # pragma: allowlist secret
    }
    assert heartbeat.full_url == "http://backend:8000/api/v1/capture/heartbeat"
    assert heartbeat.get_header("Authorization") == "Bearer session-token"
    assert json.loads(heartbeat.data) == {
        "sensor_id": "edge-01",
        "engines": ["zeek", "suricata", "tshark"],
    }
    assert all(timeout == 5 for _request, timeout in requests)


def test_reporter_discards_expired_token_and_reauthenticates(monkeypatch) -> None:
    next_token = 0
    heartbeat_attempts = 0

    def fake_urlopen(request, timeout: int) -> _Response:
        nonlocal next_token, heartbeat_attempts
        if request.full_url.endswith("/api/v1/auth/login"):
            next_token += 1
            return _Response({"access_token": f"session-token-{next_token}"})
        heartbeat_attempts += 1
        if heartbeat_attempts == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                401,
                "expired",
                hdrs=None,
                fp=io.BytesIO(b"expired"),
            )
        return _Response()

    monkeypatch.setattr(capture_heartbeat.urllib.request, "urlopen", fake_urlopen)
    reporter = HeartbeatReporter(
        "http://backend:8000",
        "sensor@corp",
        "fixture-credential",
        "edge-01",
        ["zeek"],
    )

    assert not reporter.send_once()
    assert reporter.token == ""
    assert reporter.send_once()
    assert reporter.token == "session-token-2"
    assert heartbeat_attempts == 2
