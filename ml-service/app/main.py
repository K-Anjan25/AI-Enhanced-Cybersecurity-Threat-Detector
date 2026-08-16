from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.model import NetworkInput, LogInput, EmailInput, DnsInput
from app.network_model import predict_network, model_status as network_status, reload as network_reload
from app.log_model import predict_log, model_status as log_status, reload as log_reload
from app.email_model import predict_email, model_status as email_status, reload as email_reload
from app.dns_model import predict_domain
from app.explain import explain_log, explain_email, explain_network, explain_dns
from app.benchmark import run_benchmark
from app import training

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


@app.post("/explain/log")
def log_explanation(data: LogInput):
    return explain_log(data)


@app.post("/explain/email")
def email_explanation(data: EmailInput):
    return explain_email(data)


@app.post("/explain/network")
def network_explanation(data: NetworkInput):
    return explain_network(data)


@app.post("/explain/dns")
def dns_explanation(data: DnsInput):
    return explain_dns(data)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/models")
def models_info():
    manifest = training.load_manifest()
    return {
        "network": network_status(),
        "log": log_status(),
        "email": email_status(),
        "dns": {"loaded": True, "error": None},
        "manifest": manifest,
    }


@app.post("/retrain")
def retrain_models(request: dict | None = None):
    """Retrain all models on demand and hot-swap the in-memory artifacts.

    Used by the scheduled training CronJob (k8s/training.yaml). The network
    model is skipped (status ``skipped``) when the CICIDS dataset is absent, so
    a retrain never fails just because training data is not mounted. Returns the
    new versioned manifest after reloading serving models.
    """
    if isinstance(request, dict):
        require_network = bool(request.get("require_network", False))
    else:
        require_network = False

    manifest = training.run_training(require_network=require_network)

    # Hot-swap in-memory artifacts so the next /predict calls use the new files.
    network_reload()
    log_reload()
    email_reload()

    return {"status": "ok", "manifest": manifest}


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


@app.get("/benchmark")
def benchmark_report():
    """Evaluate deployed artifacts against holdout sets (see app/benchmark.py)."""
    return run_benchmark()


@app.get("/benchmark/latest")
def last_benchmark():
    """Read the most recent persisted benchmark report (None if never run)."""
    return training.load_manifest_benchmark()
