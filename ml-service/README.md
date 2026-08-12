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

## Run Locally

```bash
pip install -r requirements.txt

# (re)train the models (requires ../datasets/CICIDS2017)
python train.py

uvicorn app.main:app --reload --port 8001
```

Models are cached in `model/*.pkl` and loaded lazily. If a model file is missing, the service falls back to deterministic heuristics so it never fails at startup.

## Docker

```bash
docker build -t ml-service .
docker run -p 8001:8001 ml-service
```
