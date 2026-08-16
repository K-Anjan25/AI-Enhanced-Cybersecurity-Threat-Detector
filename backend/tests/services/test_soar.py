"""SOAR action executor tests."""

import pytest

from app.models import DetectionRule, Org, SecurityAlert, SoarAction, SoarPlaybook
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


# ---------------------------------------------------------------------------
# Playbooks (explicit rule -> action overrides)
# ---------------------------------------------------------------------------


def _persisted_rules(db_session, org):
    rules = [
        DetectionRule(name="Brute Force Login", severity="HIGH", pattern="brute force", is_active=True),
        DetectionRule(name="Port Scan", severity="HIGH", pattern="port scan", is_active=True),
    ]
    db_session.add_all(rules)
    db_session.commit()
    for r in rules:
        db_session.refresh(r)
    return rules


def test_playbook_overrides_default_action(db_session, org):
    rules = _persisted_rules(db_session, org)
    brute = rules[0]
    playbook = soar.create_playbook(
        db_session, org_id=org.id, rule_id=brute.id,
        name="Escalate brute force", action_type="DISABLE_ACCOUNT",
    )

    # Previously heuristic mapped "brute" -> REVOKE_CREDENTIALS; playbook wins.
    alert = {"message": "brute force detected", "severity": "HIGH", "alert_type": "log"}
    with_playbook = soar.evaluate_alert(alert, rules, playbooks=[playbook])
    without = soar.evaluate_alert(alert, rules)
    assert without[0]["action_type"] == "REVOKE_CREDENTIALS"
    assert with_playbook[0]["action_type"] == "DISABLE_ACCOUNT"
    assert with_playbook[0]["playbook"] == "Escalate brute force"


def test_playbook_inactive_falls_back_to_heuristic(db_session, org):
    rules = _persisted_rules(db_session, org)
    playbook = soar.create_playbook(
        db_session, org_id=org.id, rule_id=rules[0].id,
        name="Off", action_type="BLOCK_SOURCE_IP",
    )
    playbook.is_active = False
    db_session.commit()

    alert = {"message": "brute force detected", "severity": "HIGH", "alert_type": "log"}
    actions = soar.evaluate_alert(alert, rules, playbooks=[playbook])
    assert actions[0]["action_type"] == "REVOKE_CREDENTIALS"


def test_playbook_rejected_unsupported_action(db_session, org):
    with pytest.raises(ValueError):
        soar.create_playbook(
            db_session, org_id=org.id, rule_id=99999,
            name="Bad", action_type="DELETE_EVERYTHING",
        )


def test_playbook_crud(db_session, org):
    rules = _persisted_rules(db_session, org)

    created = soar.create_playbook(
        db_session, org_id=org.id, rule_id=rules[0].id,
        name="Override", action_type="ALERT_OPERATOR",
    )
    assert created.action_type == "ALERT_OPERATOR"

    updated = soar.update_playbook(
        db_session, org.id, created.id, action_type="BLOCK_SOURCE_IP", is_active=False
    )
    assert updated.action_type == "BLOCK_SOURCE_IP"
    assert updated.is_active is False

    items, total = soar.list_playbooks(db_session, org_id=org.id)
    assert total == 1
    assert soar.serialize_playbook(items[0])["rule_name"] == "Brute Force Login"

    assert soar.delete_playbook(db_session, org.id, created.id) is True
    assert soar.delete_playbook(db_session, org.id, created.id) is False


def test_playbook_endpoints(client, auth_headers, db_session):
    from app.models import User

    admin = db_session.query(User).filter(User.username == "admin1").first()
    if admin is None:
        import pytest as _p
        _p.skip("requires admin fixture")
    org_id = admin.org_id

    rule = DetectionRule(name="Brute Force Login", severity="HIGH", pattern="brute force", is_active=True)
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)

    resp = client.post(
        "/api/v1/soar/playbooks",
        json={"rule_id": rule.id, "name": "IP block brute", "action_type": "BLOCK_SOURCE_IP"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    pb = resp.json()
    assert pb["action_type"] == "BLOCK_SOURCE_IP"
    assert pb["rule_name"] == "Brute Force Login"

    listed = client.get("/api/v1/soar/playbooks", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    patched = client.patch(
        f"/api/v1/soar/playbooks/{pb['id']}",
        json={"is_active": False, "action_type": "REVIEW_ONLY"},
        headers=auth_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["is_active"] is False

    deleted = client.delete(f"/api/v1/soar/playbooks/{pb['id']}", headers=auth_headers)
    assert deleted.status_code == 200

    gone = client.delete(f"/api/v1/soar/playbooks/{pb['id']}", headers=auth_headers)
    assert gone.status_code == 404
