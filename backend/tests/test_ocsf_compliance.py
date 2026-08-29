"""Phase 44/45: OCSF normalization + compliance evidence."""

from app.models import Org, SecurityAlert, AuditLog
from app.services import ocsf_service, compliance_service
from datetime import datetime, timezone


def test_ocsf_normalization(db_session):
    org = Org(name="Test", slug="test-ocsf")
    db_session.add(org)
    db_session.commit()

    alert = SecurityAlert(
        org_id=org.id,
        source="github",
        source_ip="203.0.113.5",
        alert_type="log",
        severity="HIGH",
        message="SQL injection detected in repo org/repo",
        mitre_technique_id="T1190",
        mitre_technique="Exploit Public-Facing Application",
        mitre_tactic="Initial Access",
        score=8.5,
    )
    db_session.add(alert)
    db_session.commit()

    ocsf = ocsf_service.alert_to_ocsf_finding(alert)
    assert ocsf["class_uid"] == 2001
    assert ocsf["severity"] == "High"
    assert ocsf["severity_id"] == 4
    assert "T1190" in str(ocsf.get("attack", {}))
    assert ocsf["src_endpoint"]["ip"] == "203.0.113.5"


def test_ocsf_batch():
    from app.models import SecurityAlert

    alerts = [
        SecurityAlert(id=1, source="github", severity="CRITICAL", message="Critical vuln", alert_type="log"),
        SecurityAlert(id=2, source="slack", severity="MEDIUM", message="Login failed", alert_type="log"),
    ]
    batch = ocsf_service.alerts_to_ocsf_batch(alerts)
    assert batch["count"] == 2
    assert batch["ocsf_version"] == "1.1.0"
    assert len(batch["findings"]) == 2


def test_compliance_hash_chain(db_session):
    # Create some audit logs with tamper-evident hashing
    log1 = compliance_service.create_tamper_evident_audit_log(
        db_session, action="TEST_ACTION_1", actor="alice", resource="test:1", details="first log"
    )
    log2 = compliance_service.create_tamper_evident_audit_log(
        db_session, action="TEST_ACTION_2", actor="bob", resource="test:2", details="second log"
    )

    assert "[audit_hash:" in log1.details
    assert "[audit_hash:" in log2.details

    # Verify chain
    result = compliance_service.verify_audit_chain(db_session, limit=10)
    assert result["chain_valid"] is True
    assert result["verified"] >= 2


def test_soc2_evidence_bundle(db_session):
    # Create some logs for SOC2
    compliance_service.create_tamper_evident_audit_log(
        db_session, action="CONNECTOR_CONFIGURED", actor="admin", resource="connector:okta", details="configured okta"
    )
    compliance_service.create_tamper_evident_audit_log(
        db_session, action="ANALYST_CASE_APPROVED", actor="analyst", resource="case:1", details="approved case"
    )

    bundle = compliance_service.get_soc2_evidence_bundle(db_session, days=1)
    assert "controls" in bundle
    assert "CC6.1" in bundle["controls"]
    assert "chain_integrity" in bundle
    assert bundle["chain_integrity"]["chain_valid"] is True


def test_case_chain_of_custody(db_session):
    org = Org(name="Test", slug="test-coc")
    db_session.add(org)
    db_session.commit()

    from app.models import Case

    case = Case(
        title="Test case",
        description="Test",
        status="open",
        priority="high",
        org_id=org.id,
        kind="analyst",
        analysis={"what_happened": "Test", "confidence": 0.9},
        decision="pending",
    )
    db_session.add(case)
    db_session.commit()

    coc = compliance_service.get_case_chain_of_custody(db_session, case)
    assert coc["case_id"] == case.id
    assert "chain" in coc
    assert coc["verified"] is True
