from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.model import NetworkInput, LogInput, EmailInput, DnsInput
from app.network_model import predict_network, model_status as network_status
from app.log_model import predict_log, model_status as log_status
from app.email_model import predict_email, model_status as email_status
from app.dns_model import predict_domain

app = FastAPI(
    title="AI Threat Detection Service",
    version="2.0.0",
    description="Anomaly detection and attack classification microservice.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/predict/network")
def network_prediction(data: NetworkInput):
    result = predict_network(data)
    return {
        "anomaly_score": result["anomaly_score"],
        "is_anomaly": result["is_anomaly"],
    }


@app.post("/predict/network/detail")
def network_prediction_detail(data: NetworkInput):
    return predict_network(data)


@app.post("/predict/log")
def log_prediction(data: LogInput):
    result = predict_log(data)
    return {
        "anomaly_score": result["anomaly_score"],
        "is_anomaly": result["is_anomaly"],
    }


@app.post("/predict/log/detail")
def log_prediction_detail(data: LogInput):
    return predict_log(data)


@app.post("/predict/email")
def email_prediction(data: EmailInput):
    return predict_email(data)


@app.post("/predict/dns")
def dns_prediction(data: DnsInput):
    return predict_domain(data)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/models")
def models_info():
    return {
        "network": network_status(),
        "log": log_status(),
        "email": email_status(),
        "dns": {"loaded": True, "error": None},
    }


@app.get("/info")
def info():
    return {
        "service": "ml-service",
        "version": app.version,
        "models": ["network_model", "log_model", "email_model", "dns_rules"],
    }


@app.post("/predict/network/batch")
def network_batch(inputs: list[NetworkInput]):
    return {"results": [predict_network(item) for item in inputs]}


@app.post("/predict/log/batch")
def log_batch(inputs: list[LogInput]):
    return {"results": [predict_log(item) for item in inputs]}
