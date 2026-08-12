from app.services.item_service import (
    get_engine_settings,
    update_engine_settings,
    create_rule,
    get_rule,
    upsert_ip_reputation,
    get_ip_reputation,
)
from app.models import SecurityAlert


def test_engine_settings_defaults_and_update(db_session):
    settings = get_engine_settings(db_session)
    assert settings.detectionSensitivity == "MEDIUM"
    assert settings.maxConcurrentScans > 0

    updated = update_engine_settings(db_session, {"detectionSensitivity": "HIGH", "logRetentionDays": 60})
    assert updated.detectionSensitivity == "HIGH"
    assert updated.logRetentionDays == 60

    persisted = get_engine_settings(db_session)
    assert persisted.detectionSensitivity == "HIGH"


def test_detection_rule_crud(db_session):
    rule = create_rule(db_session, {"name": "SSH brute force", "severity": "HIGH", "description": "Repeated SSH failures"})
    assert rule.id is not None

    fetched = get_rule(db_session, rule.id)
    assert fetched.name == "SSH brute force"
    assert fetched.severity == "HIGH"


def test_ip_reputation_upsert(db_session):
    row = upsert_ip_reputation(db_session, {"ip_address": "192.168.1.99", "threat_score": 0.8, "is_blocked": True})
    assert row.is_blocked is True

    fetched = get_ip_reputation(db_session, "192.168.1.99")
    assert fetched.threat_score == 0.8


def test_alert_model_persists(db_session):
    alert = SecurityAlert(alert_type="network", source_ip="10.0.0.1", severity="HIGH", score=0.9, message="Test alert")
    db_session.add(alert)
    db_session.commit()
    assert alert.id is not None
