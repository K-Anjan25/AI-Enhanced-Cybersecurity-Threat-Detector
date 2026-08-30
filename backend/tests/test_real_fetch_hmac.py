"""Phase 42: real fetch + HMAC verification + incremental cursor."""

import hmac
import hashlib
import json
import time

from app.services import connector_service
from app.models import Org


def test_github_signature_verification():
    secret = "mysecret"
    body = b'{"events": [{"message": "x"}]}'
    expected = "sha256=" + hmac.new(secret.encode(), body, "sha256").hexdigest()
    assert connector_service.verify_github_signature(body, expected, secret) is True
    assert connector_service.verify_github_signature(body, "sha256=bad", secret) is False
    assert connector_service.verify_github_signature(body, None, secret) is False


def test_slack_signature_verification():
    secret = "slack_signing_secret"
    ts = str(int(time.time()))
    body = b'{"events": []}'
    basestring = f"v0:{ts}:{body.decode()}"
    sig = "v0=" + hmac.new(secret.encode(), basestring.encode(), "sha256").hexdigest()
    assert connector_service.verify_slack_signature(body, ts, sig, secret) is True
    # Old timestamp should fail
    old_ts = str(int(time.time()) - 400)
    old_basestring = f"v0:{old_ts}:{body.decode()}"
    old_sig = "v0=" + hmac.new(secret.encode(), old_basestring.encode(), "sha256").hexdigest()
    assert connector_service.verify_slack_signature(body, old_ts, old_sig, secret) is False


def test_normalize_github_alert():
    raw = {
        "rule": {"description": "SQL injection", "severity": "error"},
        "html_url": "https://github.com/org/repo/security/code-scanning/1",
        "repository": {"full_name": "org/repo"},
        "severity": "high",
    }
    norm = connector_service._normalize_github_alert(raw, "code-scanning")
    assert norm is not None
    assert "SQL injection" in norm["message"]
    assert norm["severity"] == "HIGH"
    assert "org/repo" in norm["message"]


def test_normalize_slack_audit():
    raw = {
        "action": "user_login_failed",
        "actor": {"email": "alice@example.com", "user_id": "U123"},
        "ip_address": "203.0.113.5",
    }
    norm = connector_service._normalize_slack_audit_event(raw)
    assert norm is not None
    assert "user_login_failed" in norm["message"]
    assert norm["severity"] == "HIGH"
    assert norm["source_ip"] == "203.0.113.5"


def test_fetch_github_events_with_mock(db_session, monkeypatch):
    org = Org(name="Test", slug="test-gh")
    db_session.add(org)
    db_session.commit()

    # Mock _fetch_events to return orgs and alerts
    def fake_fetch(url, headers=None, timeout=None):
        class Resp:
            status_code = 200
            headers = {}
            text = "[]"

            def raise_for_status(self):
                pass

            def json(self):
                if "user/orgs" in url:
                    return [{"login": "test-org"}]
                if "user" in url and "orgs" not in url:
                    return {"login": "test-user"}
                if "code-scanning" in url:
                    return [
                        {
                            "rule": {"description": "Test vuln", "severity": "error"},
                            "html_url": "https://github.com/test-org/repo/security/1",
                            "repository": {"full_name": "test-org/repo"},
                            "severity": "high",
                        }
                    ]
                return []

        return Resp()

    monkeypatch.setattr(connector_service, "_fetch_events", fake_fetch)

    events, cursor, state = connector_service._fetch_github_events("fake_token")
    assert len(events) >= 1
    assert events[0]["severity"] == "HIGH"


def test_ingest_with_github_hmac(db_session):
    org = Org(name="Acme", slug="acme-hmac")
    db_session.add(org)
    db_session.commit()

    connector_service.upsert_config(
        db_session, org.id, "github", {"mode": "push", "ingest_token": "webhook_secret"}, actor="admin"
    )

    body = json.dumps({"events": [{"message": "GitHub push event", "severity": "HIGH"}]}).encode()
    sig = "sha256=" + hmac.new(b"webhook_secret", body, "sha256").hexdigest()

    result = connector_service.ingest_push(
        db_session,
        "github",
        token="",
        events=[{"message": "GitHub push event", "severity": "HIGH"}],
        raw_body=body,
        github_signature=sig,
    )
    assert result["status"] == "ingested"
    assert result["ingested"] == 1


def test_incremental_cursor_persisted(db_session, monkeypatch):
    org = Org(name="Acme", slug="acme-cursor")
    db_session.add(org)
    db_session.commit()

    connector_service.upsert_config(
        db_session,
        org.id,
        "github",
        {"mode": "poll", "endpoint": "https://api.github.com/orgs/test-org/code-scanning/alerts", "auth_header": "Authorization", "auth_token": "Bearer fake"},
        actor="admin",
    )

    # Mock real fetch to return events with cursor
    def fake_github(token, since=None, cursor=None, max_pages=3, tz=None):
        return ([{"message": "Test alert", "severity": "HIGH"}], "2", {"orgs_fetched": 1})

    monkeypatch.setattr(connector_service, "_fetch_github_events", fake_github)

    # Mock oauth token retrieval
    monkeypatch.setattr(connector_service, "_fetch_events", lambda *a, **k: (_ for _ in ()).throw(Exception("should not be called")))

    # Need to mock get_oauth_token to return token
    import app.services.connector_oauth_service as oauth_svc

    monkeypatch.setattr(oauth_svc, "get_oauth_token", lambda db, org_id, connector_id: "fake_oauth_token")

    result = connector_service.sync(db_session, org_id=org.id, connector_id="github", actor="admin")
    assert result["status"] == "synced"
    assert result["ingested"] >= 0

    cfg = connector_service.get_config(db_session, org.id, "github")
    assert cfg.last_cursor == "2"
