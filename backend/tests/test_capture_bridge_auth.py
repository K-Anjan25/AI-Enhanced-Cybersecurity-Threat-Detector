"""A bridge that gets a 401 logs in again instead of reusing the expired token.

Regression: access tokens last 900 s. The bridges retried after a 401 by calling
``authenticate()``, which returned early because the stale token was still set,
so every later batch was refused until the bridge was restarted.
"""

from __future__ import annotations

import importlib.util
import io
import json
import urllib.error
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

BRIDGES = Path(__file__).resolve().parents[1] / "app" / "services" / "capture" / "bridges"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, BRIDGES / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Response:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = json.dumps(body).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


@pytest.mark.parametrize("name", ["zeek_bridge", "suricata_bridge", "tcpdump_bridge"])
def test_a_401_logs_in_again_and_the_next_batch_is_accepted(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge = _load(name)
    monkeypatch.setattr(bridge, "TOKEN", "expired-token")
    logins: list[str] = []

    def fake_urlopen(req: Any, timeout: float | None = None) -> _Response:
        if req.full_url.endswith("/api/v1/auth/login"):
            logins.append(req.full_url)
            return _Response({"access_token": "fresh-token", "subject": "bridge"})
        if req.get_header("Authorization") == "Bearer fresh-token":
            return _Response({"accepted": 1})
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(bridge.urllib.request, "urlopen", fake_urlopen)

    record = [{"ts": 1.0}]
    assert bridge.send_batch(record) == 0  # the expired token is refused once
    assert len(logins) == 1
    assert bridge.TOKEN == "fresh-token"
    assert bridge.send_batch(record) == 1  # and the fresh token is accepted
    assert len(logins) == 1
