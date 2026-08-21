"""Phase 18 - autonomous analyst walking skeleton.

Covers the product loop end-to-end with the LLM forced into its deterministic
templated fallback (no API key), plus the API surface:
    simulate (sense + reason) -> pending case -> approve (SOAR + report) / decline / revert.
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
# Scenario injector + service transitions (deterministic, no HTTP)
# ---------------------------------------------------------------------------

def test_simulate_opens_pending_analyst_case(db_session, org):
    case = scenario.run_credential_leak(db_session, org_id=org.id, actor="analyst1")

    assert case.kind == "analyst"
    assert case.decision == "pending"
    assert case.priority == "critical"
    assert case.source_alert_id is not None
    assert case.analysis and case.analysis["fallback"] is True
    assert case.proposed_action["action_type"] == "REVOKE_CREDENTIALS"
    # Blast radius reaches the account + host + attacker IP from the email root.
    assert case.blast_radius["root_entity_id"] is not None
    assert len(case.blast_radius["nodes"]) >= 3

    actions = {a.action for a in db_session.query(AuditLog).all()}
    assert "ANALYST_CASE_OPENED" in actions
    # No action executed yet.
    assert db_session.query(SoarAction).count() == 0


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
    assert soar_row.action_type == "REVOKE_CREDENTIALS"

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
    actions = {a.action for a in db_session.query(AuditLog).all()}
    assert "ANALYST_CASE_DECLINED" in actions


def test_revert_records_compensating_action(db_session, org):
    case = scenario.run_credential_leak(db_session, org_id=org.id, actor="analyst1")
    analyst_service.approve_case(db_session, case, actor="analyst1", actor_id=None)
    reverted = analyst_service.revert_case(db_session, case, actor="analyst1", actor_id=None)

    assert reverted.decision == "reverted"
    # One action for the approve, one compensating action for the revert.
    assert db_session.query(SoarAction).count() == 2
    actions = {a.action for a in db_session.query(AuditLog).all()}
    assert "ANALYST_CASE_REVERTED" in actions


def test_double_decision_is_rejected(db_session, org):
    case = scenario.run_credential_leak(db_session, org_id=org.id, actor="analyst1")
    analyst_service.approve_case(db_session, case, actor="analyst1", actor_id=None)
    with pytest.raises(ValueError):
        analyst_service.approve_case(db_session, case, actor="analyst1", actor_id=None)
    with pytest.raises(ValueError):
        analyst_service.decline_case(db_session, case, actor="analyst1", actor_id=None)


def test_revert_requires_prior_approval(db_session, org):
    case = scenario.run_credential_leak(db_session, org_id=org.id, actor="analyst1")
    with pytest.raises(ValueError):
        analyst_service.revert_case(db_session, case, actor="analyst1", actor_id=None)


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------

def test_analyst_flow_over_http(client, auth_headers):
    # Simulate -> pending analyst case.
    resp = client.post("/api/v1/analyst/simulate", headers=auth_headers)
    assert resp.status_code == 201, resp.text
    case = resp.json()
    case_id = case["id"]
    assert case["kind"] == "analyst"
    assert case["decision"] == "pending"
    assert case["analysis"]["fallback"] is True

    # Brief reflects the pending decision.
    brief = client.get("/api/v1/analyst/brief", headers=auth_headers)
    assert brief.status_code == 200
    assert brief.json()["pending_count"] >= 1

    # Feed lists it.
    feed = client.get("/api/v1/analyst/feed", headers=auth_headers)
    assert feed.status_code == 200
    assert feed.json()["total"] >= 1

    # Approve -> recorded + report.
    approve = client.post(f"/api/v1/analyst/cases/{case_id}/approve", headers=auth_headers)
    assert approve.status_code == 200, approve.text
    assert approve.json()["decision"] == "approved"

    report = client.get(f"/api/v1/analyst/cases/{case_id}/report", headers=auth_headers)
    assert report.status_code == 200
    assert report.json()["report"]

    # Approving again conflicts.
    again = client.post(f"/api/v1/analyst/cases/{case_id}/approve", headers=auth_headers)
    assert again.status_code == 409

    # Legacy cases endpoint still works (analyst case is visible, extra keys ignored).
    legacy = client.get("/api/v1/cases", headers=auth_headers)
    assert legacy.status_code == 200


def test_analyst_reads_require_auth(client):
    assert client.get("/api/v1/analyst/brief").status_code == 401
    assert client.post("/api/v1/analyst/simulate").status_code == 401
