#from kafka import KafkaProducer
import json
from app.config import KAFKA_BOOTSTRAP_SERVERS, ALERT_TOPIC, ENABLE_KAFKA

if ENABLE_KAFKA:
    from kafka import KafkaProducer
    producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode()
    )
    
    def send_alert(alert):
        producer.send(ALERT_TOPIC, alert)
        producer.flush()
    
else:
    
    print("⚠️ Kafka disabled - running in local mode")
    def send_alert(alert):
        print("Mock alert (Kafka disabled):", alert)
    
    
