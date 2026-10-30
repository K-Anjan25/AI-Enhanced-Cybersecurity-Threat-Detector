"""Capture bridges sign in with a reason on failure and back off on 429."""

from __future__ import annotations

import importlib.util
import io
import urllib.error
from pathlib import Path
from types import ModuleType

import pytest

_PATH = Path(__file__).resolve().parents[1] / "app/services/capture/bridges/login.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("capture_login", _PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


login = _load()


def _http(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    import email.message

    msg = email.message.Message()
    for key, value in headers.items():
        msg[key] = value
    return urllib.error.HTTPError("http://api/login", code, "err", msg, io.BytesIO(b""))


def _run(responses: list[object], attempts: int = 3) -> tuple[list[str], list[float], str]:
    logs: list[str] = []
    sleeps: list[float] = []
    queue = list(responses)

    def fake_post(api: str, email: str, password: str, timeout: float) -> dict[str, object]:
        item = queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item  # type: ignore[return-value]

    original = login._post_login
    login._post_login = fake_post
    try:
        return logs, sleeps, login.sign_in(
            "http://api",
            "admin@aegis.local",
            "pw",
            log=logs.append,
            attempts=attempts,
            sleep=sleeps.append,
        )
    finally:
        login._post_login = original


def test_success_returns_token_and_logs_subject() -> None:
    logs, sleeps, token = _run([{"access_token": "tok", "subject": "admin@aegis.local"}])
    assert token == "tok"
    assert logs == ["[AUTH] ✓ admin@aegis.local"]
    assert sleeps == []


def test_429_waits_for_retry_after_then_succeeds() -> None:
    logs, sleeps, token = _run(
        [_http(429, retry_after="7"), {"access_token": "tok", "subject": "a"}]
    )
    assert token == "tok"
    assert sleeps == [7.0]
    assert "rate-limited" in logs[0]


def test_401_fails_with_password_reason_and_never_logs_password() -> None:
    with pytest.raises(login.LoginFailed) as excinfo:
        _run([_http(401), _http(401), _http(401)], attempts=3)
    assert "AEGIS_BOOTSTRAP_ADMIN_PASSWORD" in str(excinfo.value)
    logs, _, _ = [], [], None
    assert "pw" not in str(excinfo.value)


def test_unreachable_api_reports_the_api_url() -> None:
    with pytest.raises(login.LoginFailed) as excinfo:
        _run([urllib.error.URLError("connection refused")] * 2, attempts=2)
    assert "cannot reach the API at http://api" in str(excinfo.value)
