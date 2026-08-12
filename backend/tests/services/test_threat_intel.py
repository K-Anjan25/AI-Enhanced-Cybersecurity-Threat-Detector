"""Threat-intel enrichment service tests."""

from app.models import IpReputation
from app.services.threat_intel import band, enrich_alert
from app.services import alert_service
from app.services.mitre import map_alert


def test_band_thresholds():
    assert band(0.9) == "malicious"
    assert band(0.6) == "suspicious"
    assert band(0.2) == "low"
    assert band(0.0) == "unknown"


def test_enrich_unknown_ip_auto_registers(db_session):
    ctx = enrich_alert(db_session, "203.0.113.10")
    assert ctx["ip_address"] == "203.0.113.10"
    assert ctx["threat_score"] == 0.0
    assert ctx["is_blocked"] is False
    assert ctx["reputation_band"] == "unknown"

    row = db_session.query(IpReputation).filter(IpReputation.ip_address == "203.0.113.10").first()
    assert row is not None


def test_enrich_known_ip_returns_reputation(db_session):
    db_session.add(IpReputation(ip_address="198.51.100.7", threat_score=0.93, is_blocked=True, category="c2"))
    db_session.commit()

    ctx = enrich_alert(db_session, "198.51.100.7")
    assert ctx["threat_score"] == 0.93
    assert ctx["is_blocked"] is True
    assert ctx["category"] == "c2"
    assert ctx["reputation_band"] == "malicious"


def test_enrich_empty_ip_returns_empty(db_session):
    assert enrich_alert(db_session, None) == {}
    assert enrich_alert(db_session, "") == {}


def test_process_log_attaches_threat_intel(db_session, monkeypatch):
    # Force ML path to return an anomaly without hitting a real service.
    monkeypatch.setattr(
        alert_service, "predict_log",
        lambda log: {"anomaly_score": 0.9, "is_anomaly": True, "fallback": True},
    )
    db_session.add(IpReputation(ip_address="203.0.113.55", threat_score=0.88, is_blocked=True, category="scanner"))
    db_session.commit()

    result = alert_service.process_log(
        {"message": "Failed password for root", "source": "203.0.113.55"},
        produce_kafka=False,
        db=db_session,
    )
    assert result["is_anomaly"] is True
    assert result["fallback"] is True
    assert map_alert("system_log", "Failed password for root", "203.0.113.55")["technique_id"] == "T1110"
