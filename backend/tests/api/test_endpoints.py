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


def test_x_request_id_tracing_echoes_header(client):
    resp = client.get("/health/live", headers={"X-Request-ID": "trace-abc123"})
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"] == "trace-abc123"


def test_x_request_id_generated_when_absent(client):
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    assert resp.headers["X-Request-ID"]


def test_register_login_me_flow(client, auth_headers):
    # /me with bearer token
    resp = client.get("/api/v1/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["username"] == "analyst1"
    assert "ANALYST" in body["roles"]


def test_me_returns_permissions_for_abac_gating(client, auth_headers, admin_headers):
    """The /me payload must include permissions so the dashboard can gate the
    admin routes (users:manage / audit:read) instead of redirecting to alerts."""
    analyst = client.get("/api/v1/me", headers=auth_headers).json()
    assert "permissions" in analyst
    assert "alerts:read" in analyst["permissions"]
    assert "users:manage" not in analyst["permissions"]

    admin = client.get("/api/v1/me", headers=admin_headers).json()
    assert "users:manage" in admin["permissions"]
    assert "audit:read" in admin["permissions"]


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


def test_self_registration_cannot_grant_admin(client, db_session):
    """Self-registration is ABAC-restricted: privileged roles must be rejected.

    ADMIN accounts are provisioned only through the admin-only /users endpoint.
    """
    resp = client.post(
        "/api/v1/register",
        json={"username": "escaler", "email": "esc@example.com", "password": "secret123", "role": "ADMIN"},
    )
    assert resp.status_code == 400
    assert db_session.query(User).filter(User.username == "escaler").first() is None

    # Non-privileged roles (any casing) still register fine.
    resp = client.post(
        "/api/v1/register",
        json={"username": "tierone", "email": "tierone@example.com", "password": "secret123", "role": "analyst"},
    )
    assert resp.status_code == 201
    user = db_session.query(User).filter(User.username == "tierone").first()
    assert user.role == "ANALYST"


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


def test_admin_orgs_cross_tenant_listing(client, admin_headers, db_session):
    """FR-TENANT-06: admins can list all orgs cross-tenant with user counts."""
    from app.models import Org, User
    from app.core.security import get_password_hash

    org_a = Org(name="Alpha Corp", slug="alpha")
    db_session.add(org_a)
    db_session.flush()
    org_b = Org(name="Beta LLC", slug="beta")
    db_session.add(org_b)
    db_session.flush()

    db_session.add_all([
        User(username="alpha1", email="a1@example.com", password=get_password_hash("pw"), role="ANALYST", org_id=org_a.id),
        User(username="alpha2", email="a2@example.com", password=get_password_hash("pw"), role="ANALYST", org_id=org_a.id),
        User(username="beta1", email="b1@example.com", password=get_password_hash("pw"), role="USER", org_id=org_b.id),
    ])
    db_session.commit()

    resp = client.get("/api/v1/admin/orgs", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    by_slug = {o["slug"]: o for o in body["data"]}
    assert by_slug["alpha"]["user_count"] == 2
    assert by_slug["beta"]["user_count"] == 1
    assert "default" in by_slug  # the seeded default tenant is visible too


def test_admin_orgs_requires_admin(client, auth_headers):
    resp = client.get("/api/v1/admin/orgs", headers=auth_headers)
    assert resp.status_code == 403


def test_user_roster_requires_admin(client, auth_headers, admin_headers):
    anon = client.get("/api/v1/users")
    assert anon.status_code in (401, 403)

    forbidden = client.get("/api/v1/users", headers=auth_headers)
    assert forbidden.status_code == 403

    allowed = client.get("/api/v1/users", headers=admin_headers)
    assert allowed.status_code == 200
    assert isinstance(allowed.json(), list)


def test_user_roster_filters_and_org_info(client, admin_headers, db_session):
    """FR-TENANT-06: roster supports org/role/search filters + org context."""
    from app.models import Org, User
    from app.core.security import get_password_hash

    org_a = Org(name="Alpha Corp", slug="alpha2")
    db_session.add(org_a)
    db_session.flush()

    db_session.add_all([
        User(username="tier1", email="t1@example.com", password=get_password_hash("pw"), role="ANALYST", org_id=org_a.id),
        User(username="tier2", email="t2@example.com", password=get_password_hash("pw"), role="ANALYST", org_id=org_a.id),
        User(username="watcher", email="w1@example.com", password=get_password_hash("pw"), role="USER", org_id=org_a.id),
    ])
    db_session.commit()

    by_org = client.get(f"/api/v1/users?org_id={org_a.id}", headers=admin_headers).json()
    assert len(by_org) == 3
    assert all(u["org_id"] == org_a.id for u in by_org)
    assert all(u["org_name"] == "Alpha Corp" for u in by_org)

    by_role = client.get(f"/api/v1/users?org_id={org_a.id}&role=ANALYST", headers=admin_headers).json()
    assert len(by_role) == 2

    by_search = client.get(f"/api/v1/users?search=tier", headers=admin_headers).json()
    assert {u["username"] for u in by_search} == {"tier1", "tier2"}


def test_admin_roles_matrix(client, admin_headers):
    """FR-UI-06: admins can render the ABAC role->permission matrix."""
    resp = client.get("/api/v1/admin/roles", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    roles = {r["role"] for r in body["data"]}
    assert {"ADMIN", "ANALYST", "USER"} <= roles
    admin_row = next(r for r in body["data"] if r["role"] == "ADMIN")
    assert "audit:read" in admin_row["permissions"]
    assert admin_row["clearance"] == 4


def test_admin_create_user_sets_org(client, admin_headers, db_session):
    from app.models import Org, User

    org_a = Org(name="Alpha Corp", slug="alpha3")
    db_session.add(org_a)
    db_session.flush()
    db_session.commit()

    resp = client.post(
        "/api/v1/users",
        json={"username": "provisioned", "email": "p@example.com", "password": "secret123", "role": "ANALYST", "org_id": org_a.id},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["org_id"] == org_a.id

    created = db_session.query(User).filter(User.username == "provisioned").first()
    assert created is not None and created.org_id == org_a.id


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


def test_entity_graph_summary_endpoint(client, db_session, auth_headers):
    from app.models import SecurityAlert
    from app.services import entity_graph

    alert = SecurityAlert(
        alert_type="system_log",
        source_ip="203.0.113.5",
        severity="HIGH",
        score=0.87,
        message="Malicious payload deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        org_id=1,
    )
    db_session.add(alert)
    db_session.flush()
    entity_graph.index_alert(db_session, alert)
    db_session.commit()

    resp = client.get("/api/v1/entities/summary", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["nodes"] >= 2
    assert "by_type" in body and "ip" in body["by_type"]
    assert len(body["hubs"]) >= 1


def test_entity_graph_path_endpoint(client, db_session, auth_headers):
    from app.models import SecurityAlert
    from app.services import entity_graph

    alert = SecurityAlert(
        alert_type="system_log",
        source_ip="203.0.113.5",
        severity="HIGH",
        score=0.87,
        message="Malicious payload deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        org_id=1,
    )
    db_session.add(alert)
    db_session.flush()
    entity_graph.index_alert(db_session, alert)
    db_session.commit()

    from app.models import Entity

    ip = db_session.query(Entity).filter(Entity.entity_type == "ip").first()
    hsh = db_session.query(Entity).filter(Entity.entity_type == "hash").first()

    resp = client.get(
        f"/api/v1/entities/path?from_id={ip.id}&to_id={hsh.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reachable"] is True
    assert body["hops"] == 1
    assert len(body["path"]) == 2


def test_entity_graph_path_invalid_id(client, auth_headers):
    resp = client.get(
        "/api/v1/entities/path?from_id=999999&to_id=888888",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["reachable"] is False


def test_ml_benchmark_proxies_to_ml_service(client, auth_headers, monkeypatch):
    from app.services import ml_client
    import requests

    def _fake_get(url, timeout=None):
        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"version": "x", "models": [{"model": "log_model", "status": "ok"}]}

        return _Resp()

    monkeypatch.setattr(ml_client.requests, "get", _fake_get)
    resp = client.get("/api/v1/ml/benchmark", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["models"][0]["model"] == "log_model"


def test_ml_explain_log_proxies_payload(client, auth_headers, monkeypatch):
    from app.services import ml_client

    captured = {}

    def _fake_post(url, json=None, timeout=None, max_retries=None):
        captured["url"] = url
        captured["payload"] = json

        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"contributions": [{"term": "sql injection", "direction": "attack"}]}

        return _Resp()

    monkeypatch.setattr(ml_client.requests, "post", _fake_post)
    resp = client.post(
        "/api/v1/ml/explain/log",
        headers=auth_headers,
        json={"message": "SQL injection exploit detected", "level": "ERROR"},
    )
    assert resp.status_code == 200
    assert resp.json()["contributions"][0]["term"] == "sql injection"
    assert captured["url"].endswith("/explain/log")
    assert captured["payload"]["message"] == "SQL injection exploit detected"


def test_ml_explain_network_requires_payload_auth(client, db_session):
    resp = client.post("/api/v1/ml/explain/network", json={"dst_port": 3389})
    assert resp.status_code in (401, 403)


def test_client_error_telemetry_records_audit(client, db_session, auth_headers):
    from app.models import AuditLog

    resp = client.post(
        "/api/v1/telemetry/client-error",
        headers=auth_headers,
        json={
            "message": "TypeError: x is undefined",
            "component_stack": "at AlertsPage",
            "url": "http://localhost:3000/alerts",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["recorded"] is True

    entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "CLIENT_ERROR")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert entry is not None
    assert entry.resource == "dashboard"
    assert entry.actor == "analyst1"
    assert "TypeError: x is undefined" in entry.details


def test_client_error_telemetry_requires_auth(client, db_session):
    resp = client.post(
        "/api/v1/telemetry/client-error",
        json={"message": "TypeError: x is undefined"},
    )
    assert resp.status_code in (401, 403)
