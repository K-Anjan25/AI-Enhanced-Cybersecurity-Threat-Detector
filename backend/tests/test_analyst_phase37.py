"""Phase 37 — bulk decisions, chat rate-limit, scenario validation, encryption key decoupling."""

import pytest

from app.core.config import settings
from app.models import Org
from app.services import scenario, analyst_service
from app.core import secrets as secrets_mod


@pytest.fixture(autouse=True)
def _force_llm_fallback(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)
    monkeypatch.setattr(settings, "LLM_ENABLED", False)


@pytest.fixture()
def org(db_session):
    row = Org(name="Acme Inc", slug="acme")
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


@pytest.fixture(autouse=True)
def _reset_chat_limiter():
    analyst_service._chat_limiter.reset()
    yield
    analyst_service._chat_limiter.reset()


def test_bulk_decide_approves_pending_only(db_session, org):
    cases = [
        scenario.run_credential_leak(db_session, org_id=org.id, actor="analyst1")
        for _ in range(3)
    ]
    # approve one already
    analyst_service.approve_case(db_session, cases[0], actor="analyst1", actor_id=None)
    # bulk approve remaining + already approved + non-existent
    result = analyst_service.bulk_decide(
        db_session,
        org_id=org.id,
        case_ids=[cases[0].id, cases[1].id, cases[2].id, 999999],
        decision="approved",
        actor="analyst1",
        actor_id=None,
    )
    assert set(result["decided"]) == {cases[1].id, cases[2].id}
    assert len(result["failed"]) == 2
    failed_ids = {f["id"] for f in result["failed"]}
    assert 999999 in failed_ids
    assert cases[0].id in failed_ids
    assert result["decision"] == "approved"


def test_bulk_decide_invalid_decision_raises(db_session, org):
    case = scenario.run_credential_leak(db_session, org_id=org.id, actor="analyst1")
    with pytest.raises(ValueError):
        analyst_service.bulk_decide(
            db_session, org_id=org.id, case_ids=[case.id], decision="bogus", actor="a", actor_id=None
        )


def test_chat_rate_limited(db_session, org, monkeypatch):
    monkeypatch.setattr(settings, "ANALYST_CHAT_RATE_LIMIT", 2)
    # re-create limiter with small limit
    analyst_service._chat_limiter = analyst_service.RateLimiter(limit=2, window_seconds=60)
    case = scenario.run_credential_leak(db_session, org_id=org.id, actor="analyst1")
    analyst_service.chat_about_case(db_session, case, "q1", actor="analyst1", actor_id=1)
    analyst_service.chat_about_case(db_session, case, "q2", actor="analyst1", actor_id=1)
    with pytest.raises(analyst_service.ChatRateLimited):
        analyst_service.chat_about_case(db_session, case, "q3", actor="analyst1", actor_id=1)
    # different case id should still be allowed (key includes case)
    analyst_service.chat_about_case(db_session, case, "q3 different actor", actor="analyst1", actor_id=2)


def test_bulk_decide_http(client, auth_headers):
    # create 3 cases via API
    ids = []
    for _ in range(3):
        r = client.post("/api/v1/analyst/simulate?scenario_type=credential_leak", headers=auth_headers)
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    # bulk approve 2
    r = client.post(
        "/api/v1/analyst/bulk-decide",
        json={"case_ids": ids[:2], "decision": "approved"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["decided"]) == set(ids[:2])
    assert body["failed"] == []

    # bulk decline with one already decided should report failed
    r2 = client.post(
        "/api/v1/analyst/bulk-decide",
        json={"case_ids": ids, "decision": "declined"},
        headers=auth_headers,
    )
    assert r2.status_code == 200, r2.text
    b2 = r2.json()
    assert b2["decided"] == [ids[2]]
    assert len(b2["failed"]) == 2


def test_chat_rate_limit_http_429(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "ANALYST_CHAT_RATE_LIMIT", 2)
    analyst_service._chat_limiter = analyst_service.RateLimiter(limit=2, window_seconds=60)
    r = client.post("/api/v1/analyst/simulate?scenario_type=credential_leak", headers=auth_headers)
    assert r.status_code == 201
    cid = r.json()["id"]
    for i in range(2):
        cr = client.post(f"/api/v1/analyst/cases/{cid}/chat", json={"message": f"q{i}"}, headers=auth_headers)
        assert cr.status_code == 200, cr.text
    cr3 = client.post(f"/api/v1/analyst/cases/{cid}/chat", json={"message": "q3"}, headers=auth_headers)
    assert cr3.status_code == 429, cr3.text
    assert "Retry-After" in cr3.headers


def test_simulate_invalid_scenario_422(client, auth_headers):
    r = client.post("/api/v1/analyst/simulate?scenario_type=not_a_real_scenario", headers=auth_headers)
    assert r.status_code == 422
    assert "Unknown scenario_type" in r.text


def test_connector_encryption_key_decouples_from_jwt(monkeypatch):
    monkeypatch.setattr(settings, "CONNECTOR_ENCRYPTION_KEY", "connector-key-32-bytes-long-xxxxxx")
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "jwt-secret-different-32-bytes-xxx")
    import importlib
    importlib.reload(secrets_mod)
    enc = secrets_mod.encrypt_secret("super-secret-value")
    # rotate JWT
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "new-jwt-secret-32-bytes-rotation!")
    importlib.reload(secrets_mod)
    dec = secrets_mod.decrypt_secret(enc)
    assert dec == "super-secret-value"
    # cleanup: restore no dedicated key fallback path still works if set to None
    monkeypatch.setattr(settings, "CONNECTOR_ENCRYPTION_KEY", None)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "jwt-secret-different-32-bytes-xxx")
    importlib.reload(secrets_mod)
    # encrypt with JWT only
    enc2 = secrets_mod.encrypt_secret("fallback-secret")
    dec2 = secrets_mod.decrypt_secret(enc2)
    assert dec2 == "fallback-secret"
