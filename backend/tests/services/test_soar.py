"""SOAR action executor tests."""

import pytest

from app.models import DetectionRule, Org, SecurityAlert, SoarAction
from app.services import soar


@pytest.fixture
def org(db_session):
    org = Org(name="SoarCo", slug="soco")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def rules(db_session):
    return [
        DetectionRule(name="Brute Force Login", severity="HIGH", pattern="brute force", is_active=True),
        DetectionRule(name="Ransomware", severity="CRITICAL", pattern="ransomware", is_active=True),
        DetectionRule(name="Disabled", severity="LOW", pattern="anything", is_active=False),
    ]


def test_evaluate_alert_matches_rule(rules):
    alert = {"message": "brute force detected", "severity": "HIGH", "alert_type": "log"}
    actions = soar.evaluate_alert(alert, rules)
    assert len(actions) == 1
    assert actions[0]["action_type"] == "REVOKE_CREDENTIALS"
    assert actions[0]["rule_name"] == "Brute Force Login"


def test_evaluate_alert_matches_mitre_technique(rules):
    # Rule pattern == a MITRE technique ID token matches via mitre_technique_id.
    mitre_rule = DetectionRule(name="Ransomware", severity="CRITICAL", pattern="t1486", is_active=True)
    alert = {"message": "files encrypted", "mitre_technique_id": "T1486", "severity": "CRITICAL"}
    actions = soar.evaluate_alert(alert, [mitre_rule])
    assert len(actions) == 1
    assert actions[0]["action_type"] == "QUARANTINE_ENDPOINT"


def test_evaluate_alert_inactive_rules_ignored(rules):
    alert = {"message": "anything", "severity": "HIGH"}
    actions = soar.evaluate_alert(alert, rules)
    # Inactive rule skipped; grave default kicks in
    assert len(actions) == 1
    assert actions[0]["action_type"] == "ALERT_OPERATOR"


def test_evaluate_low_severity_no_match_is_empty(rules):
    alert = {"message": "benign stuff", "severity": "LOW"}
    assert soar.evaluate_alert(alert, rules) == []


def test_respond_to_alert_records_action(db_session, org, rules):
    db_session.add_all(rules)
    db_session.commit()

    alert = {
        "id": 1,
        "alert_type": "log",
        "source_ip": "203.0.113.9",
        "severity": "HIGH",
        "message": "brute force detected",
        "org_id": org.id,
    }
    results = soar.respond_to_alert(db_session, alert, rules)
    db_session.commit()
    assert len(results) == 1
    row = db_session.query(SoarAction).first()
    assert row is not None
    assert row.action_type == "REVOKE_CREDENTIALS"
    assert row.org_id == org.id
    assert results[0]["status"] == "executed"


def test_trigger_endpoint_org_scoped(client, auth_headers, db_session):
    from app.models import User

    admin = db_session.query(User).filter(User.username == "admin1").first()
    if admin is None:
        import pytest as _p
        _p.skip("requires admin fixture")

    alert = SecurityAlert(
        org_id=admin.org_id,
        alert_type="system_log",
        source_ip="203.0.113.9",
        severity="HIGH",
        score=0.9,
        message="brute force on admin account",
    )
    db_session.add(alert)
    db_session.commit()
    db_session.refresh(alert)

    resp = client.post(f"/api/v1/soar/trigger/{alert.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] >= 1
