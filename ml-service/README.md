# ML Threat Detection Service

FastAPI-based microservice for anomaly detection in security logs.

## Features

- Feature extraction from logs
- Isolation Forest anomaly detection
- REST API (/predict)
- Docker-ready

## Run Locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```
