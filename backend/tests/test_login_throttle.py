"""Login throttle: per-account and per-address limits, shared across replicas."""

from __future__ import annotations

import pytest
from app.services import login_throttle as lt
from app.services.login_throttle import (
    LocalWindowCounter,
    LoginThrottle,
    RedisWindowCounter,
    ThrottleSettings,
)

SETTINGS = ThrottleSettings(account_max_failures=3, address_max_failures=5, window_seconds=60)


def _fail(throttle: LoginThrottle, email: str, address: str, times: int) -> None:
    for _ in range(times):
        throttle.record_failure(email, address)


def test_account_is_blocked_after_its_limit_and_reports_retry_after() -> None:
    throttle = LoginThrottle(SETTINGS)
    _fail(throttle, "admin@aegis.local", "10.0.0.1", 3)
    decision = throttle.check("admin@aegis.local", "10.0.0.2")
    assert not decision.allowed
    assert 1 <= decision.retry_after_seconds <= 60


def test_a_correct_password_clears_only_the_account_counter() -> None:
    throttle = LoginThrottle(SETTINGS)
    _fail(throttle, "a@x.io", "10.0.0.1", 2)
    throttle.record_success("a@x.io")
    _fail(throttle, "a@x.io", "10.0.0.1", 2)  # two more, still under three
    assert throttle.check("a@x.io", "10.0.0.1").allowed


def test_address_limit_stops_one_host_spraying_accounts() -> None:
    throttle = LoginThrottle(SETTINGS)
    for i in range(5):
        throttle.record_failure(f"user{i}@x.io", "203.0.113.9")
    assert not throttle.check("someone@x.io", "203.0.113.9").allowed
    assert throttle.check("someone@x.io", "203.0.113.10").allowed


def test_local_counter_expires_with_its_window(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(lt.time, "monotonic", lambda: now[0])
    counter = LocalWindowCounter()
    assert counter.add("k", 60) == 1
    assert counter.add("k", 60) == 2
    now[0] += 61
    assert counter.count("k") == 0


def test_local_counter_is_bounded() -> None:
    counter = LocalWindowCounter(max_keys=3)
    for i in range(10):
        counter.add(f"k{i}", 60)
    assert len(counter._entries) == 3  # noqa: SLF001 - the bound is the property under test


def test_two_replicas_share_one_redis_count() -> None:
    fakeredis = pytest.importorskip("fakeredis")
    server = fakeredis.FakeServer()
    replica_a = LoginThrottle(SETTINGS, RedisWindowCounter(fakeredis.FakeRedis(server=server)))
    replica_b = LoginThrottle(SETTINGS, RedisWindowCounter(fakeredis.FakeRedis(server=server)))
    _fail(replica_a, "admin@aegis.local", "10.0.0.1", 2)
    _fail(replica_b, "admin@aegis.local", "10.0.0.2", 1)
    assert not replica_a.check("admin@aegis.local", "10.0.0.3").allowed
    assert not replica_b.check("admin@aegis.local", "10.0.0.3").allowed
    assert replica_a.shared


def test_redis_counter_gets_an_expiry_so_it_cannot_grow_forever() -> None:
    fakeredis = pytest.importorskip("fakeredis")
    client = fakeredis.FakeRedis()
    throttle = LoginThrottle(SETTINGS, RedisWindowCounter(client))
    throttle.record_failure("a@x.io", "10.0.0.1")
    assert client.ttl("aegis:login:acct:a@x.io") > 0


class _DownRedis:
    def pipeline(self) -> object:
        raise ConnectionError("redis is down")

    def get(self, key: str) -> None:
        raise ConnectionError("redis is down")

    def delete(self, key: str) -> None:
        raise ConnectionError("redis is down")

    def ttl(self, key: str) -> None:
        raise ConnectionError("redis is down")


def test_an_unreachable_redis_degrades_to_the_local_limit_and_says_so() -> None:
    throttle = LoginThrottle(SETTINGS, RedisWindowCounter(_DownRedis()))
    _fail(throttle, "admin@aegis.local", "10.0.0.1", 3)
    assert throttle.backend_errors > 0
    assert not throttle.check("admin@aegis.local", "10.0.0.1").allowed


def test_limits_must_be_positive() -> None:
    with pytest.raises(ValueError):
        ThrottleSettings(account_max_failures=0)
    with pytest.raises(ValueError):
        ThrottleSettings(window_seconds=0)


def test_factory_without_a_url_is_local_only() -> None:
    throttle = lt.build_login_throttle(SETTINGS, redis_url="")
    assert not throttle.shared
