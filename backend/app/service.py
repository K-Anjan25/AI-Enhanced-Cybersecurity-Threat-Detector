import os
import socket
from app.ml_client import predict_network, predict_log
from app.kafka_producer import send_alert
from app.database import SessionLocal
from app.models import SecurityAlert


def process_log(log: dict, produce_kafka: bool = True):

    # Detect type
    if "bytes" in log and "duration" in log:
        result = predict_network(log)
        source_ip = log.get("src_ip")
        message = "Network traffic anomaly detected"
        alert_type = "network"
    else:
        result = predict_log(log)
        source_ip = log.get("source")
        message = log.get("message")
        alert_type = "system_log"

    score = result.get("anomaly_score")
    is_anomaly = result.get("is_anomaly")

    # severity = "HIGH" if score < 0 else "LOW"

    # if not is_anomaly:
    #     severity = "LOW"
    # else:
    #     if score < 0:
    #         severity = "MEDIUM"
    #     elif score < -0.02:
    #         severity = "HIGH"
    #     else:
    #         severity = "CRITICAL"

    if alert_type == "network":
        # IsolationForest → negative means anomaly
        if score >= 0:
            severity = "LOW"
        elif score > -0.15:
            severity = "MEDIUM"
        elif score > -0.4:
            severity = "HIGH"
        else:
            severity = "CRITICAL"

    else:  # system_log (probability based)
        if score < 0.4:
            severity = "LOW"
        elif score < 0.7:
            severity = "MEDIUM"
        elif score < 0.9:
            severity = "HIGH"
        else:
            severity = "CRITICAL"

    alert = {
        "alert_type": alert_type,
        "source_ip": source_ip,
        "severity": severity,
        "score": score,
        "message": message
    }

    if is_anomaly:
        db = SessionLocal()
        db.add(SecurityAlert(**alert))
        db.commit()
        db.close()

        if produce_kafka:
            send_alert(alert)

    return {
        "anomaly_score": score,
        "is_anomaly": is_anomaly,
        "type": alert_type
    }
