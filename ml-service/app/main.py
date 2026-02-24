from fastapi import FastAPI
from app.model import NetworkInput, LogInput
from app.network_model import predict_network
from app.log_model import predict_log

app = FastAPI()


@app.post("/predict/network")
def network_prediction(data: NetworkInput):
    score, is_anomaly = predict_network(data)
    return {
        "anomaly_score": score,
        "is_anomaly": is_anomaly
    }


@app.post("/predict/log")
def log_prediction(data: LogInput):
    probability, is_attack = predict_log(data)
    return {
        "anomaly_score": probability,
        "is_anomaly": is_attack
    }
