KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
RAW_LOG_TOPIC = "raw-system-logs"
ALERT_TOPIC = "security-alerts"

ML_SERVICE_URL = "http://localhost:8001"

DATABASE_URL = "postgresql://threatuser:threatpass@localhost:5431/threatdb"

# MODE FLAGS
ENABLE_KAFKA = True   # set False for local-only mode
