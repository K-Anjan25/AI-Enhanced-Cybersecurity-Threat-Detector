from kafka import KafkaProducer
import json
from app.config import KAFKA_BOOTSTRAP_SERVERS, ALERT_TOPIC

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode()
)


def send_alert(alert):
    producer.send(ALERT_TOPIC, alert)
