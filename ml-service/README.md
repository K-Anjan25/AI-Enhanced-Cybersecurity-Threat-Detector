# ML Threat Detection Service

FastAPI microservice providing AI-based threat detection for network traffic, security logs, email phishing, and DNS queries.

## Detection services

| Service | Model | Description |
| --- | --- | --- |
| `/predict/network` | IsolationForest | Network flow anomaly detection (trained on CICIDS2017) |
| `/predict/log` | TF-IDF + LogisticRegression | Security log attack classification |
| `/predict/email` | TF-IDF + LogisticRegression + heuristics | Phishing email detection |
| `/predict/dns` | Rule-based scoring | Suspicious domain / DNS query detection |

Each `/predict/*/detail` endpoint (and `/predict/email`, `/predict/dns`) returns:

```json
{
  "anomaly_score": 0.91,
  "is_anomaly": true,
  "severity": "CRITICAL",
  "confidence": 0.98,
  "indicators": ["..."]
}
```

## Endpoints

- `POST /predict/network` and `POST /predict/network/detail`
- `POST /predict/network/batch`
- `POST /predict/log` and `POST /predict/log/detail`
- `POST /predict/log/batch`
- `POST /predict/email`
- `POST /predict/dns`
- `GET /models` — model loading status
- `GET /health`, `GET /info`

## Explainability

Each detection family has a companion endpoint that explains *why* a decision
was reached — top contributing terms (TF-IDF coefficients) for the log/email
classifiers, per-feature deviation from the training centroid for the
IsolationForest, and the fired rules for DNS. All responses share a stable
shape that a UI can render generically:

```json
{
  "contributions": [
    { "term": "sql injection", "score": 0.42, "direction": "attack", "source": "keyword" }
  ],
  "summary": "Driven by: sql injection.",
  "method": "coefficients + keyword evidence",
  "model_error": null
}
```

- `GET /benchmark` — run a fresh evaluation of deployed artifacts against holdout sets
- `GET /benchmark/latest` — read the most recently persisted `model/benchmark.json`
- `POST /explain/log`, `POST /explain/email`, `POST /explain/network`, `POST /explain/dns`

Dependency-free: no SHAP or extra runtime deps; coefficient/centroid evidence is
extracted directly from the already-loaded sklearn pipelines.

## Run Locally

```bash
pip install -r requirements.txt

# (re)train models. Log/email come from built-in corpora (no data needed);
# network requires ../datasets/CICIDS2017 (skipped otherwise — train.py
# defaults to --require-network off).
python train.py

uvicorn app.main:app --reload --port 8001
```

Models are cached in `model/*.pkl` and loaded lazily. If a model file is missing, the service falls back to deterministic heuristics so it never fails at startup.

## Docker

The image is self-contained — the `Dockerfile` runs `python train.py` at build
time so log/email models are baked in (network skipped unless CICIDS2017 is in
the build context):

```bash
docker build -t ml-service .
docker run -p 8001:8001 ml-service
```
