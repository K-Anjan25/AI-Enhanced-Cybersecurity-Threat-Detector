"""Certificate Transparency client.

The property that matters most: a lookup that could not complete must never be
reported as "checked and clean". Everything else follows from that.
"""

import pytest
import requests

from app.core.config import settings
from app.services import ct_log_client


@pytest.fixture
def ct_enabled(monkeypatch):
    monkeypatch.setattr(settings, "DRP_CT_ENABLED", True, raising=False)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else ("[]" if payload is None else "x")

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _row(name_value, common_name=None, serial="aa", issuer="C=US, O=Let's Encrypt, CN=R3",
         not_before="2026-01-01T00:00:00", cert_id=1):
    return {
        "id": cert_id,
        "issuer_name": issuer,
        "common_name": common_name if common_name is not None else name_value,
        "name_value": name_value,
        "not_before": not_before,
        "not_after": "2026-04-01T00:00:00",
        "serial_number": serial,
    }


# ---------------------------------------------------------------------------
# The honesty contract
# ---------------------------------------------------------------------------

def test_disabled_is_not_a_clean_result():
    result = ct_log_client.lookup_domain("acme.com")
    assert result.ok is False
    assert result.registered is False
    assert "DRP_CT_ENABLED" in result.reason


@pytest.mark.parametrize(
    "exc, expected",
    [
        (requests.Timeout("slow"), "timed out"),
        (requests.ConnectionError("no route"), "unreachable"),
    ],
)
def test_network_failure_is_reported_not_swallowed(monkeypatch, ct_enabled, exc, expected):
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(exc))
    result = ct_log_client.lookup_domain("acme.com")
    assert result.ok is False
    assert expected in result.reason


def test_rate_limit_is_distinguished_from_no_results(monkeypatch, ct_enabled):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(status_code=429))
    result = ct_log_client.lookup_domain("acme.com")
    assert result.ok is False
    assert "rate limited" in result.reason


def test_server_error_is_not_a_clean_result(monkeypatch, ct_enabled):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(status_code=503))
    result = ct_log_client.lookup_domain("acme.com")
    assert result.ok is False
    assert "503" in result.reason


def test_empty_body_means_genuinely_no_certificates(monkeypatch, ct_enabled):
    """crt.sh returns an empty body for no records — that IS a clean result."""
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(text=""))
    result = ct_log_client.lookup_domain("acme.com")
    assert result.ok is True
    assert result.registered is False


def test_non_json_body_is_a_failure(monkeypatch, ct_enabled):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(text="<html>error</html>"))
    result = ct_log_client.lookup_domain("acme.com")
    assert result.ok is False
    assert "non-JSON" in result.reason


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_registered_domain_returns_issuer_and_first_seen(monkeypatch, ct_enabled):
    payload = [
        _row("acme-login.com", serial="s2", not_before="2026-03-01T00:00:00", cert_id=2),
        _row("acme-login.com", serial="s1", not_before="2026-01-15T00:00:00", cert_id=1),
    ]
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(payload=payload))

    result = ct_log_client.lookup_domain("acme-login.com")
    assert result.ok is True
    assert result.registered is True
    assert result.first_seen == "2026-01-15T00:00:00", "earliest issuance, not newest"
    assert result.issuers == ["Let's Encrypt"]


def test_precertificate_and_certificate_are_counted_once(monkeypatch, ct_enabled):
    """CT logs both; they share a serial and must not double-count."""
    payload = [_row("acme-login.com", serial="same", cert_id=1),
               _row("acme-login.com", serial="same", cert_id=2)]
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(payload=payload))

    result = ct_log_client.lookup_domain("acme-login.com")
    assert len(result.certificates) == 1


def test_loose_server_side_match_is_rejected(monkeypatch, ct_enabled):
    """crt.sh matches broadly; a cert for another domain must not count."""
    payload = [_row("totally-different.com", serial="s1")]
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(payload=payload))

    result = ct_log_client.lookup_domain("acme-login.com")
    assert result.ok is True
    assert result.registered is False


def test_domain_found_in_san_list_counts(monkeypatch, ct_enabled):
    payload = [_row("other.com\nacme-login.com\nwww.acme-login.com",
                    common_name="other.com", serial="s1")]
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(payload=payload))

    result = ct_log_client.lookup_domain("acme-login.com")
    assert result.registered is True


def test_wildcard_certificate_matches_base_domain(monkeypatch, ct_enabled):
    payload = [_row("*.acme-login.com", serial="s1")]
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(payload=payload))

    result = ct_log_client.lookup_domain("acme-login.com")
    assert result.registered is True


# ---------------------------------------------------------------------------
# Batch behaviour
# ---------------------------------------------------------------------------

def test_lookup_many_aborts_on_rate_limit(monkeypatch, ct_enabled):
    """Do not hammer a free service once it has said no."""
    calls = []

    def fake_get(*a, **k):
        calls.append(k.get("params", {}).get("q"))
        return FakeResponse(status_code=429)

    monkeypatch.setattr(requests, "get", fake_get)
    results = ct_log_client.lookup_many(["a.com", "b.com", "c.com"])

    assert len(calls) == 1, "stopped after the first rate limit"
    assert len(results) == 1


def test_lookup_many_continues_past_a_clean_miss(monkeypatch, ct_enabled):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(text=""))
    results = ct_log_client.lookup_many(["a.com", "b.com", "c.com"])
    assert len(results) == 3
    assert all(r.ok and not r.registered for r in results)
