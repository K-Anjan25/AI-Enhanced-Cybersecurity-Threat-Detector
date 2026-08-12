import pytest

from app.models import User


def test_health_check(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_liveness_probe(client):
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


def test_readiness_probe(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_register_login_me_flow(client, auth_headers):
    # /me with bearer token
    resp = client.get("/api/v1/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["username"] == "analyst1"
    assert "ANALYST" in body["roles"]


def test_login_rejects_bad_credentials(client):
    resp = client.post("/api/v1/login", data={"username": "nobody", "password": "wrong"})
    assert resp.status_code == 401


def test_login_locks_account_after_repeated_failures(client, db_session):
    """Brute-force protection: N consecutive failures block the account."""
    from app.core.config import settings

    client.post(
        "/api/v1/register",
        json={"username": "brutetarget", "email": "brute@example.com", "password": "secret123", "role": "USER"},
    )

    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        resp = client.post("/api/v1/login", data={"username": "brutetarget", "password": "wrong"})
        assert resp.status_code == 401

    user = db_session.query(User).filter(User.username == "brutetarget").first()
    assert user.is_blocked is True
    assert user.failed_login_attempts >= settings.LOGIN_MAX_ATTEMPTS

    # Even the correct password is now rejected.
    resp = client.post("/api/v1/login", data={"username": "brutetarget", "password": "secret123"})
    assert resp.status_code == 403


def test_login_success_resets_failed_counter(client, db_session):
    client.post(
        "/api/v1/register",
        json={"username": "resetme", "email": "resetme@example.com", "password": "secret123", "role": "USER"},
    )
    client.post("/api/v1/login", data={"username": "resetme", "password": "wrong"})
    user = db_session.query(User).filter(User.username == "resetme").first()
    assert user.failed_login_attempts == 1

    resp = client.post("/api/v1/login", data={"username": "resetme", "password": "secret123"})
    assert resp.status_code == 200
    db_session.refresh(user)
    assert user.failed_login_attempts == 0


def test_cookie_auth_flow(client, db_session):
    """With COOKIE_AUTH enabled, login sets httpOnly cookies and /me works
    without an Authorization header."""
    from app.core.config import settings

    original_cookie = settings.COOKIE_AUTH
    original_secure = settings.COOKIE_SECURE
    settings.COOKIE_AUTH = True
    settings.COOKIE_SECURE = False  # test client runs over http
    try:
        client.post(
            "/api/v1/register",
            json={"username": "cookieuser", "email": "cookie@example.com", "password": "secret123", "role": "USER"},
        )
        resp = client.post("/api/v1/login", data={"username": "cookieuser", "password": "secret123"})
        assert resp.status_code == 200
        assert resp.cookies.get("access_token")

        # /me authenticated purely by the cookie
        me = client.get("/api/v1/me")
        assert me.status_code == 200
        assert me.json()["user"]["username"] == "cookieuser"

        # logout clears the cookies
        out = client.post("/api/v1/logout")
        assert out.status_code == 200
        assert "access_token" not in out.cookies

        me = client.get("/api/v1/me")
        assert me.status_code == 401
    finally:
        settings.COOKIE_AUTH = original_cookie
        settings.COOKIE_SECURE = original_secure


def test_login_rate_limited(client, db_session):
    """In-memory limiter returns 429 after the per-minute budget is exhausted."""
    from app.api.v1.endpoints.auth import login_limiter
    from app.core.config import settings

    login_limiter.reset("login:testclient:ratelimit")

    client.post(
        "/api/v1/register",
        json={"username": "ratelimit", "email": "ratelimit@example.com", "password": "secret123", "role": "USER"},
    )

    statuses = set()
    for _ in range(settings.LOGIN_RATE_LIMIT_PER_MINUTE + 1):
        resp = client.post("/api/v1/login", data={"username": "ratelimit", "password": "wrong"})
        statuses.add(resp.status_code)
    assert 429 in statuses

    login_limiter.reset("login:testclient:ratelimit")


def test_refresh_token_flow(client, db_session):
    client.post(
        "/api/v1/register",
        json={"username": "user2", "email": "user2@example.com", "password": "secret123", "role": "USER"},
    )
    login = client.post("/api/v1/login", data={"username": "user2", "password": "secret123"})
    refresh_token = login.json()["refresh_token"]

    resp = client.post(
        "/api/v1/refresh",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_refresh_rejects_access_token(client, auth_headers):
    access_token = auth_headers["Authorization"].split(" ")[1]
    resp = client.post("/api/v1/refresh", headers={"Authorization": f"Bearer {access_token}"})
    assert resp.status_code == 401


def test_alerts_endpoint_requires_auth(client):
    resp = client.get("/api/v1/alerts")
    assert resp.status_code in (401, 403)


def test_alerts_endpoint_authenticated(client, auth_headers):
    resp = client.get("/api/v1/alerts", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)
    assert "items" in body
    assert "total" in body
    assert isinstance(body["items"], list)


def test_alerts_pagination(client, auth_headers, db_session):
    # Seed a handful of alerts directly so the endpoint response is deterministic
    from app.models import SecurityAlert

    for i in range(5):
        db_session.add(SecurityAlert(
            alert_type="network",
            source_ip=f"10.0.0.{i}",
            severity="HIGH",
            score=0.8,
            message=f"paginated alert {i}",
        ))
    db_session.commit()

    resp = client.get("/api/v1/alerts?page=1&limit=2", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["limit"] == 2

    page2 = client.get("/api/v1/alerts?page=3&limit=2", headers=auth_headers).json()
    assert len(page2["items"]) == 1


def test_upload_logs_background_scan_persists_history(client, auth_headers):
    """Uploading logs returns a batch id, completes via background scan, and
    the history/list endpoints read from the database."""
    content = (
        "Dec 05 10:00:01 host sshd[123]: Failed password for root from 10.0.0.1 port 22\n"
        "Dec 05 10:00:02 host app[456]: user logged in\n"
    )
    resp = client.post(
        "/api/v1/upload-logs",
        files={"log_file": ("auth.log", content, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["batch_id"] is not None
    assert body["totalLogsParsed"] == 2

    batch_id = body["batch_id"]

    # Background ran before the response returned, so status is terminal
    status = client.get(f"/api/v1/uploads/{batch_id}").json()["batch"]
    assert status["status"] in ("completed", "failed")
    assert status["filename"] == "auth.log"

    history = client.get("/api/v1/logs/history").json()["logs"]
    assert any(entry["filename"] == "auth.log" for entry in history)


def test_upload_batch_status_missing_returns_404(client):
    resp = client.get("/api/v1/uploads/999999")
    assert resp.status_code == 404


def test_engine_settings_requires_auth(client):
    resp = client.get("/api/v1/engine/settings")
    assert resp.status_code in (401, 403)


def test_engine_settings_get_put(client, auth_headers, admin_headers):
    # Analysts can read settings (engine:read) but may not update them.
    get_resp = client.get("/api/v1/engine/settings", headers=auth_headers)
    assert get_resp.status_code == 200

    forbidden = client.put(
        "/api/v1/engine/settings",
        json={"detectionSensitivity": "HIGH"},
        headers=auth_headers,
    )
    assert forbidden.status_code == 403

    # Updating settings requires engine:update (ADMIN).
    put_resp = client.put(
        "/api/v1/engine/settings",
        json={"detectionSensitivity": "HIGH"},
        headers=admin_headers,
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["settings"]["detectionSensitivity"] == "HIGH"


def test_analytics_overview(client, auth_headers):
    resp = client.get("/api/v1/analytics/overview", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "total" in body
    assert "severity_distribution" in body


def test_audit_logs_admin_only(client, auth_headers, admin_headers):
    # analyst forbidden
    forbidden = client.get("/api/v1/audit-logs", headers=auth_headers)
    assert forbidden.status_code == 403

    allowed = client.get("/api/v1/audit-logs", headers=admin_headers)
    assert allowed.status_code == 200
    assert "data" in allowed.json()


def test_rules_admin_crud(client, admin_headers):
    create_resp = client.post(
        "/api/v1/rules",
        json={"name": "RDP brute force", "severity": "CRITICAL", "description": "Repeated RDP login failures"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    rule_id = create_resp.json()["id"]

    list_resp = client.get("/api/v1/rules", headers=admin_headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1

    delete_resp = client.delete(f"/api/v1/rules/{rule_id}", headers=admin_headers)
    assert delete_resp.status_code == 200


def test_ip_reputation_flow(client, admin_headers):
    upsert = client.post(
        "/api/v1/reputation",
        json={"ip_address": "203.0.113.7", "threat_score": 0.9, "is_blocked": True},
        headers=admin_headers,
    )
    assert upsert.status_code == 200

    lookup = client.get("/api/v1/reputation/203.0.113.7", headers=admin_headers)
    assert lookup.status_code == 200
    assert lookup.json()["is_blocked"] is True


def test_audit_log_is_append_only(client, db_session):
    """AuditLog rows cannot be updated or deleted at the ORM layer."""
    from app.models import AuditLog

    entry = AuditLog(action="test", actor="admin1", resource="rules/1")
    db_session.add(entry)
    db_session.commit()

    with pytest.raises(Exception):
        entry.details = "tampered"
        db_session.commit()
    db_session.rollback()

    with pytest.raises(Exception):
        db_session.delete(entry)
        db_session.commit()
    db_session.rollback()

    still_there = db_session.query(AuditLog).filter(AuditLog.action == "test").count()
    assert still_there == 1


def test_forgot_password_reset_link_development_only(client, db_session, monkeypatch):
    """In development, when SMTP is off, a reset link is returned; but in
    production it must never leak through the API response."""
    from app.core.config import settings
    from app.api.v1.endpoints import auth as auth_endpoints

    monkeypatch.setattr(auth_endpoints, "send_email", lambda **kwargs: False)

    client.post(
        "/api/v1/register",
        json={"username": "resetlink", "email": "resetlink@example.com", "password": "secret123", "role": "USER"},
    )

    original = settings.ENVIRONMENT
    try:
        settings.ENVIRONMENT = "development"
        resp = client.post("/api/v1/forgot-password", json={"email": "resetlink@example.com"})
        assert resp.status_code == 200
        assert "reset_link" in resp.json()

        settings.ENVIRONMENT = "production"
        resp = client.post("/api/v1/forgot-password", json={"email": "resetlink@example.com"})
        assert resp.status_code == 200
        assert "reset_link" not in resp.json()
    finally:
        settings.ENVIRONMENT = original
