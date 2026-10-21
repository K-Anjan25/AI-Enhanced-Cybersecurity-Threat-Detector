"""The shared capture shipper: batching, retries, spooling and counters."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path
from typing import Any

import pytest

BRIDGES = Path(__file__).resolve().parents[1] / "app" / "services" / "capture" / "bridges"


def _load_shipper() -> Any:
    spec = importlib.util.spec_from_file_location("shipper_under_test", BRIDGES / "shipper.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: dataclasses look the module up by name while building.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


shipper = _load_shipper()


class _Ok(io.BytesIO):
    def __enter__(self) -> _Ok:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://api", code, "x", {}, io.BytesIO(b"nope"))  # type: ignore[arg-type]


def _flow(i: int) -> dict[str, Any]:
    return {"schema_version": "flow@1", "src_ip": "10.0.0.1", "dst_port": i}


class _Api:
    """Scripted ingest endpoint: each call pops the next outcome from ``script``."""

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[int] = []  # batch sizes that reached the wire
        self.received: list[dict[str, Any]] = []

    def __call__(self, req: Any, timeout: float | None = None) -> _Ok:
        body = [json.loads(line) for line in req.data.decode().splitlines()]
        self.calls.append(len(body))
        outcome = self.script.pop(0) if self.script else "ok"
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome == "ok":
            self.received.extend(body)
            return _Ok(json.dumps({"accepted": len(body)}).encode())
        raise outcome


def _make(
    monkeypatch: pytest.MonkeyPatch,
    api: _Api,
    *,
    spool_dir: Path | None = None,
    spool_bytes: int = 10_000_000,
    token: str = "t1",  # noqa: S107
    reauth_ok: bool = True,
    attempts: int = 3,
) -> tuple[Any, list[float]]:
    monkeypatch.setattr(shipper.urllib.request, "urlopen", api)
    sleeps: list[float] = []
    spool = shipper.Spool(spool_dir, spool_bytes) if spool_dir is not None else None
    state = {"token": token}

    def reauth() -> bool:
        if reauth_ok:
            state["token"] = "t2"
        return reauth_ok

    ship = shipper.Shipper(
        "http://api",
        token=lambda: state["token"],
        reauthenticate=reauth,
        spool=spool,
        attempts=attempts,
        backoff_base=0.5,
        backoff_cap=2.0,
        sleep=sleeps.append,
        rng=lambda: 1.0,  # full jitter at its ceiling, so the test is deterministic
        log=lambda _msg: None,
    )
    return ship, sleeps


def test_records_are_sent_in_batches_no_larger_than_the_api_cap(monkeypatch, tmp_path) -> None:
    api = _Api([])
    ship, _ = _make(monkeypatch, api)
    accepted = ship.send([_flow(i) for i in range(2500)])
    assert accepted == 2500
    assert api.calls == [1000, 1000, 500]
    assert ship.stats.accepted == 2500


def test_transient_failures_are_retried_with_bounded_backoff(monkeypatch) -> None:
    api = _Api([_http_error(503), _http_error(429), "ok"])
    ship, sleeps = _make(monkeypatch, api, attempts=3)
    assert ship.send([_flow(1), _flow(2)]) == 2
    assert ship.stats.retried == 2
    assert len(sleeps) == 2
    assert all(0 <= s <= 2.0 for s in sleeps)  # never beyond the cap


def test_a_rejected_batch_is_counted_and_never_retried(monkeypatch) -> None:
    api = _Api([_http_error(422)])
    ship, sleeps = _make(monkeypatch, api)
    assert ship.send([_flow(1), _flow(2), _flow(3)]) == 0
    assert api.calls == [3]  # one attempt only
    assert sleeps == []
    assert ship.stats.rejected == 3
    assert ship.stats.dropped == 0


def test_an_outage_is_spooled_and_drained_oldest_first_on_recovery(monkeypatch, tmp_path) -> None:
    down = [_http_error(503)] * 3  # all three attempts of the first send fail
    api = _Api(down)
    ship, _ = _make(monkeypatch, api, spool_dir=tmp_path, attempts=3)
    ship.send([_flow(i) for i in range(4)])
    assert ship.stats.spooled == 4
    assert ship.stats.dropped == 0

    # Backend is back. The next send drains the spool first, then sends the new record.
    api.script = []
    ship.send([_flow(99)])
    assert [r["dst_port"] for r in api.received] == [0, 1, 2, 3, 99]
    assert ship.stats.drained == 4


def test_the_spool_is_capped_and_overflow_is_counted_not_hidden(monkeypatch, tmp_path) -> None:
    one = len((json.dumps(_flow(0)) + "\n").encode())
    api = _Api([_http_error(503)] * 3)
    ship, _ = _make(monkeypatch, api, spool_dir=tmp_path, spool_bytes=one * 2, attempts=3)
    ship.send([_flow(i) for i in range(5)])
    assert ship.stats.spooled == 2
    assert ship.stats.dropped == 3


def test_an_expired_token_is_refreshed_and_the_batch_still_lands(monkeypatch) -> None:
    api = _Api([_http_error(401), "ok"])
    ship, _ = _make(monkeypatch, api)
    assert ship.send([_flow(1)]) == 1
    assert api.calls == [1, 1]


def test_a_second_refusal_after_refresh_is_spooled_not_looped(monkeypatch, tmp_path) -> None:
    api = _Api([_http_error(401), _http_error(401)])
    ship, _ = _make(monkeypatch, api, spool_dir=tmp_path)
    assert ship.send([_flow(1)]) == 0
    assert ship.stats.spooled == 1


def test_a_missing_login_is_spooled_when_it_cannot_be_recovered(monkeypatch, tmp_path) -> None:
    api = _Api([])
    ship, _ = _make(monkeypatch, api, spool_dir=tmp_path, token="", reauth_ok=False)
    assert ship.send([_flow(1)]) == 0
    assert ship.stats.spooled == 1
    assert api.calls == []


def test_spool_prepend_keeps_order(tmp_path) -> None:
    spool = shipper.Spool(tmp_path, 10_000)
    spool.append("flows", [_flow(3), _flow(4)])
    spool.prepend("flows", [_flow(1), _flow(2)])
    assert [r["dst_port"] for r in spool.take("flows", 10)] == [1, 2, 3, 4]
    assert spool.pending("flows") == 0


def test_attempts_must_be_positive() -> None:
    with pytest.raises(ValueError):
        shipper.Shipper("http://api", token=lambda: "t", reauthenticate=lambda: True, attempts=0)


def test_the_shipper_reports_its_counters_as_a_plain_mapping(monkeypatch) -> None:
    api = _Api([])
    ship, _ = _make(monkeypatch, api)
    ship.send([_flow(1)])
    counters: dict[str, int | str] = ship.stats.as_dict()
    assert counters["accepted"] == 1 and counters["dropped"] == 0
