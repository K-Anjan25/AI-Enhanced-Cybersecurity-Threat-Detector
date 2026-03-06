#from kafka import KafkaConsumer
import json
from app.config import KAFKA_BOOTSTRAP_SERVERS, RAW_LOG_TOPIC, ENABLE_KAFKA
from app.service import process_log

if ENABLE_KAFKA:
    from kafka import KafkaConsumer
    consumer = KafkaConsumer(
        RAW_LOG_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_deserializer=lambda m: json.loads(m.decode())
    )
    def start_consumer():
        for msg in consumer:
            process_log(msg.value, produce_kafka=True)
else:
    def start_consumer():
        print("kafaka consumer not started (disabled)")
