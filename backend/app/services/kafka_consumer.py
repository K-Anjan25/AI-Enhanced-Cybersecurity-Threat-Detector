import json
from app.core.config import settings
from app.services.alert_service import process_log

if settings.ENABLE_KAFKA:
    from kafka import KafkaConsumer
    consumer = KafkaConsumer(
        settings.RAW_LOG_TOPIC,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        value_deserializer=lambda m: json.loads(m.decode())
    )
    def start_consumer():
        for msg in consumer:
            process_log(msg.value, produce_kafka=True)
else:
    def start_consumer():
        print("Kafka consumer not started (disabled)")