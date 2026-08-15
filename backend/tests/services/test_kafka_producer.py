"""Kafka producer wiring tests — FR-STREAM-01/02, FR-DETECT-12.

The producers no-op when ENABLE_KAFKA is falsy (local mode), so these tests
patch the module-level publish helpers in ``alert_service`` to assert the
raw -> normalized -> alert event chain is emitted by ``process_log`` exactly
when ``produce_kafka=True``.
"""

from app.services import alert_service, kafka_producer


def _patch_producers(monkeypatch):
    """Replace the kafka helpers in alert_service with recorders."""
    calls = {"raw_log": [], "raw_flow": [], "normalized": [], "alert": []}

    def rec(name):
        def _f(event):
            calls[name].append(event)
        return _f

    monkeypatch.setattr(alert_service, "send_raw_log", rec("raw_log"))
    monkeypatch.setattr(alert_service, "send_raw_flow", rec("raw_flow"))
    monkeypatch.setattr(alert_service, "send_normalized", rec("normalized"))
    monkeypatch.setattr(alert_service, "send_alert", rec("alert"))
    return calls


def test_process_log_publishes_raw_normalized_alert_chain(db_session, monkeypatch):
    monkeypatch.setattr(
        alert_service, "predict_log",
        lambda log: {"anomaly_score": 0.9, "is_anomaly": True, "fallback": True},
    )
    calls = _patch_producers(monkeypatch)

    alert_service.process_log(
        {"message": "Failed password for root", "source": "203.0.113.9", "timestamp": "T1"},
        produce_kafka=True,
        db=db_session,
        org_id=42,
    )

    # System-log path: exactly one raw log + one normalized + one alert event.
    assert len(calls["raw_log"]) == 1
    assert calls["raw_log"][0]["org_id"] == 42
    assert len(calls["raw_flow"]) == 0

    normalized = calls["normalized"][0]
    assert normalized["tenant_id"] == 42
    assert normalized["org_id"] == 42
    assert normalized["type"] == "system_log"
    assert normalized["is_anomaly"] is True
    assert normalized["anomaly_score"] == 0.9

    assert len(calls["alert"]) == 1
    assert calls["alert"][0]["org_id"] == 42


def test_process_log_publishes_raw_flow_for_network_records(db_session, monkeypatch):
    monkeypatch.setattr(
        alert_service, "predict_network",
        lambda log: {"anomaly_score": 0.7, "is_anomaly": True, "fallback": True},
    )
    calls = _patch_producers(monkeypatch)

    alert_service.process_log(
        {"src_ip": "203.0.113.9", "bytes": 1245, "duration": 2.1, "org_id": 7},
        produce_kafka=True,
        db=db_session,
        org_id=7,
    )

    assert len(calls["raw_flow"]) == 1
    assert calls["raw_flow"][0]["org_id"] == 7
    assert calls["normalized"][0]["type"] == "network"


def test_process_log_skips_publishing_when_kafka_off(db_session, monkeypatch):
    monkeypatch.setattr(
        alert_service, "predict_log",
        lambda log: {"anomaly_score": 0.9, "is_anomaly": True, "fallback": True},
    )
    calls = _patch_producers(monkeypatch)

    alert_service.process_log(
        {"message": "Failed password for root", "source": "203.0.113.9"},
        produce_kafka=False,
        db=db_session,
        org_id=42,
    )

    assert calls["raw_log"] == []
    assert calls["raw_flow"] == []
    assert calls["normalized"] == []
    assert calls["alert"] == []


def test_kafka_producer_exposes_normalized_helper():
    # Local-mode no-op must exist and be callable for the configured topic set.
    assert callable(kafka_producer.send_normalized)
    assert callable(kafka_producer.send_raw_log)
    assert callable(kafka_producer.send_raw_flow)
    assert callable(kafka_producer.send_alert)
    assert callable(kafka_producer.send_action)
    assert callable(kafka_producer.send_audit)
    # No-op must not raise.
    kafka_producer.send_normalized({"tenant_id": 1, "type": "system_log"})