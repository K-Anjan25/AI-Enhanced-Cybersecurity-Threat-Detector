from kafka import KafkaConsumer
import json
from app.config import KAFKA_BOOTSTRAP_SERVERS, RAW_LOG_TOPIC
from app.service import process_log

consumer = KafkaConsumer(
    RAW_LOG_TOPIC,
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_deserializer=lambda m: json.loads(m.decode())
)


def start_consumer():
    for msg in consumer:
        process_log(msg.value, produce_kafka=True)
