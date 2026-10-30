"""The capture sensor reads the desired state and reuses its token between polls."""

from __future__ import annotations

import importlib.util
import io
import sys
import urllib.error
from pathlib import Path
from types import ModuleType

import pytest

BRIDGES = Path(__file__).resolve().parents[1] / "app" / "services" / "capture" / "bridges"


def _load(name: str) -> ModuleType:
    if str(BRIDGES) not in sys.path:
        sys.path.insert(0, str(BRIDGES))
    spec = importlib.util.spec_from_file_location(name, BRIDGES / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


state_mod = _load("capture_state")
login_mod = sys.modules["login"]


def _state(running: bool, engines: list[str], version: int = 3) -> dict[str, object]:
    return {"running": running, "engines": engines, "version": version}


def _patch(monkeypatch: pytest.MonkeyPatch, get_results: list[object]) -> dict[str, int]:
    calls = {"login": 0, "get": 0}
    queue = list(get_results)

    def fake_login(api: str, email: str, password: str, timeout: float) -> dict[str, object]:
        calls["login"] += 1
        return {"access_token": f"tok{calls['login']}", "subject": email}

    def fake_get(api: str, token: str, timeout: float) -> dict[str, object]:
        calls["get"] += 1
        item = queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item  # type: ignore[return-value]

    monkeypatch.setattr(login_mod, "_post_login", fake_login)
    monkeypatch.setattr(state_mod, "_get_state", fake_get)
    return calls


def test_formats_running_state_with_engines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch(monkeypatch, [_state(True, ["zeek", "suricata"], version=7)])
    line = state_mod.fetch_state(
        "http://api", "a@b", "pw", token_file=tmp_path / "t", log=lambda _: None
    )
    assert line == "1 7 zeek,suricata"


def test_stopped_state_reports_no_engines(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch(monkeypatch, [_state(False, [])])
    line = state_mod.fetch_state(
        "http://api", "a@b", "pw", token_file=tmp_path / "t", log=lambda _: None
    )
    assert line == "0 3 -"


def test_token_is_reused_between_polls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = _patch(monkeypatch, [_state(False, []), _state(False, [])])
    token_file = tmp_path / "t"
    for _ in range(2):
        state_mod.fetch_state("http://api", "a@b", "pw", token_file=token_file, log=lambda _: None)
    assert calls["login"] == 1
    assert calls["get"] == 2


def test_expired_token_signs_in_again(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    expired = urllib.error.HTTPError("http://api", 401, "expired", None, io.BytesIO(b""))  # type: ignore[arg-type]
    calls = _patch(monkeypatch, [expired, _state(True, ["zeek"])])
    token_file = tmp_path / "t"
    token_file.write_text("old-token")
    line = state_mod.fetch_state(
        "http://api", "a@b", "pw", token_file=token_file, log=lambda _: None
    )
    assert line == "1 3 zeek"
    assert calls["login"] == 1
    assert token_file.read_text() == "tok1"


def test_unreachable_api_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch(monkeypatch, [])
    monkeypatch.setattr(
        login_mod,
        "_post_login",
        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("refused")),
    )
    with pytest.raises(login_mod.LoginFailed):
        state_mod.fetch_state(
            "http://api",
            "a@b",
            "pw",
            token_file=tmp_path / "t",
            log=lambda _: None,
        )
