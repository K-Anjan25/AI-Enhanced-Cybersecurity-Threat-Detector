import json
from app.core.config import settings

if settings.ENABLE_KAFKA:
    from kafka import KafkaProducer

    producer = KafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v, default=str).encode(),
    )

    def _publish(topic: str, event: dict, key: str | None = None) -> None:
        """Publish a JSON event to a topic, optionally keyed (tenant/entity)."""
        producer.send(topic, event, key=key.encode() if key else None)
        producer.flush()

    def send_alert(alert: dict) -> None:
        _publish(settings.ALERT_TOPIC, alert, key=alert.get("org_id"))

    def send_raw_log(record: dict) -> None:
        _publish(settings.RAW_LOG_TOPIC, record, key=record.get("org_id"))

    def send_raw_flow(record: dict) -> None:
        _publish(settings.RAW_FLOW_TOPIC, record, key=record.get("org_id"))

    def send_action(event: dict) -> None:
        _publish(settings.ACTION_TOPIC, event, key=event.get("org_id"))

    def send_audit(event: dict) -> None:
        _publish(settings.AUDIT_TOPIC, event, key=event.get("org_id"))

else:
    def _noop(_event: dict, **kwargs) -> None:  # pragma: no cover - local mode
        print("[INFO] Kafka disabled - running in local mode")

    def send_alert(alert):
        _noop(alert)

    def send_raw_log(record):
        _noop(record)

    def send_raw_flow(record):
        _noop(record)

    def send_action(event):
        _noop(event)

    def send_audit(event):
        _noop(event)
