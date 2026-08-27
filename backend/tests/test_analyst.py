"""Phases 18-19 - autonomous analyst loop & interactive chat.

Covers:
    - Multi-scenario simulation (credential leak, phishing outbreak, data exfiltration, compromised API key)
    - NOCTRA interactive case chat
    - Security connectors status & manual sync
    - API surface & transitions (simulate -> pending -> approve/decline/revert -> report).
"""

import pytest

from app.core.config import settings
from app.models import Org, Case, SoarAction, AuditLog
from app.services import scenario, analyst_service, llm_client
from app.services.soar import SUPPORTED_ACTIONS


@pytest.fixture(autouse=True)
def _force_llm_fallback(monkeypatch):
    """Force the deterministic templated path so tests never hit the network."""
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)
    monkeypatch.setattr(settings, "LLM_ENABLED", False)


@pytest.fixture()
def org(db_session):
    row = Org(name="Acme Inc", slug="acme")
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


# ---------------------------------------------------------------------------
# LLM client contract
# ---------------------------------------------------------------------------

def test_llm_fallback_returns_full_contract():
    result = llm_client.analyze_incident(
        {
            "alert_type": "credential_leak",
            "severity": "CRITICAL",
            "source_ip": "203.0.113.66",
            "mitre_technique_id": "T1078",
            "message": "leaked credential in use",
        },
        [{"entity_type": "account", "value": "jdoe"}],
    )
    assert result["fallback"] is True
    for key in (
        "headline",
        "what_happened",
        "why_it_matters",
        "blast_radius_summary",
        "recommended_action",
        "confidence",
        "model",
    ):
        assert key in result
    action = result["recommended_action"]
    assert action["action_type"] in SUPPORTED_ACTIONS
    assert action["action_type"] == "REVOKE_CREDENTIALS"
    assert 0.0 <= result["confidence"] <= 1.0
    assert action["undo"]


# ---------------------------------------------------------------------------
# Multi-Scenario Injectors (Phase 19)
# ---------------------------------------------------------------------------

def test_simulate_multi_scenarios(db_session, org):
    # Test each scenario type
    scenarios = ["credential_leak", "phishing_outbreak", "data_exfiltration", "compromised_api_key"]
    for s_type in scenarios:
        case = scenario.run_scenario(db_session, s_type, org_id=org.id, actor="analyst1")
        assert case.kind == "analyst"
        assert case.decision == "pending"
        assert case.source_alert_id is not None
        assert case.blast_radius["nodes"]
        assert case.proposed_action["action_type"] in SUPPORTED_ACTIONS


# ---------------------------------------------------------------------------
# Interactive Case Chat & Connectors (Phase 19)
# ---------------------------------------------------------------------------

def test_case_chat_returns_contextual_answer(db_session, org):
    case = scenario.run_credential_leak(db_session, org_id=org.id, actor="analyst1")
    
    # Question about blast radius
    res1 = analyst_service.chat_about_case(db_session, case, "What is in the blast radius?", actor="analyst1")
    assert "blast radius" in res1["answer"].lower() or "entities" in res1["answer"].lower()

    # Question about recommendation
    res2 = analyst_service.chat_about_case(db_session, case, "Why revoke credentials?", actor="analyst1")
    assert "recommended action" in res2["answer"].lower() or "revoke" in res2["answer"].lower()

    actions = {a.action for a in db_session.query(AuditLog).all()}
    assert "ANALYST_CHAT_QUESTION" in actions


def test_connectors_status_and_sync(db_session, org):
    connectors = analyst_service.get_connectors_status()
    assert len(connectors) >= 4
    ids = [c["id"] for c in connectors]
    assert "okta" in ids
    assert "sentinel" in ids

    # Sync a connector
    sync_res = analyst_service.sync_connector(db_session, "okta", actor="analyst1")
    assert sync_res["status"] == "success"
    assert "Okta Identity Cloud" in sync_res["message"]

    actions = {a.action for a in db_session.query(AuditLog).all()}
    assert "CONNECTOR_SYNC_TRIGGERED" in actions


# ---------------------------------------------------------------------------
# Transitions & HTTP API Surface
# ---------------------------------------------------------------------------

def test_approve_executes_soar_records_report_and_audit(db_session, org):
    case = scenario.run_credential_leak(db_session, org_id=org.id, actor="analyst1")
    approved = analyst_service.approve_case(db_session, case, actor="analyst1", actor_id=None)

    assert approved.decision == "approved"
    assert approved.status == "resolved"
    assert approved.soar_action_id
    assert approved.report and f"Case #{approved.id}" in approved.report

    soar_row = (
        db_session.query(SoarAction)
        .filter(SoarAction.action_id == approved.soar_action_id)
        .first()
    )
    assert soar_row is not None
    assert soar_row.status == "executed"

    actions = {a.action for a in db_session.query(AuditLog).all()}
    assert "ANALYST_CASE_OPENED" in actions
    assert "ANALYST_CASE_APPROVED" in actions


def test_decline_makes_no_system_change(db_session, org):
    case = scenario.run_credential_leak(db_session, org_id=org.id, actor="analyst1")
    declined = analyst_service.decline_case(db_session, case, actor="analyst1", actor_id=None)

    assert declined.decision == "declined"
    assert declined.status == "closed"
    assert declined.report
    assert db_session.query(SoarAction).count() == 0


def test_revert_records_compensating_action(db_session, org):
    case = scenario.run_credential_leak(db_session, org_id=org.id, actor="analyst1")
    analyst_service.approve_case(db_session, case, actor="analyst1", actor_id=None)
    reverted = analyst_service.revert_case(db_session, case, actor="analyst1", actor_id=None)

    assert reverted.decision == "reverted"
    assert db_session.query(SoarAction).count() == 2


def test_analyst_http_flow_including_chat_and_connectors(client, auth_headers):
    # 1. Multi-scenario simulation endpoint
    resp = client.post("/api/v1/analyst/simulate?scenario_type=phishing_outbreak", headers=auth_headers)
    assert resp.status_code == 201, resp.text
    case = resp.json()
    case_id = case["id"]
    assert case["kind"] == "analyst"

    # 2. NOCTRA chat
    chat_resp = client.post(
        f"/api/v1/analyst/cases/{case_id}/chat",
        json={"message": "What is the recommended action for this phishing alert?"},
        headers=auth_headers,
    )
    assert chat_resp.status_code == 200, chat_resp.text
    assert "answer" in chat_resp.json()

    # 3. Connectors
    conn_resp = client.get("/api/v1/analyst/connectors", headers=auth_headers)
    assert conn_resp.status_code == 200
    assert len(conn_resp.json()) >= 4

    sync_resp = client.post("/api/v1/analyst/connectors/sentinel/sync", headers=auth_headers)
    assert sync_resp.status_code == 200
    assert sync_resp.json()["status"] == "success"

    # 4. Approve
    approve = client.post(f"/api/v1/analyst/cases/{case_id}/approve", headers=auth_headers)
    assert approve.status_code == 200
    assert approve.json()["decision"] == "approved"
