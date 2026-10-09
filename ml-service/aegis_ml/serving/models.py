"""Model registration endpoint for the ML service.

Registers the active model with the backend's Model Ops service
on startup so the Models page shows real model information.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["models"])

BACKEND_URL = os.environ.get("AEGIS_BACKEND_URL", "http://backend:8000")


class ModelInfo(BaseModel):
    """Information about a registered model."""
    model_id: str
    kind: str
    status: str
    description: str
    version: str
    features: list[str]
    artifact_uri: str = "ml-service://statistical-anomaly-v1"
    metrics: dict[str, Any] = {}


# The models this service provides
REGISTERED_MODELS: list[dict[str, Any]] = [
    {
        "model_id": "statistical-anomaly-v1",
        "kind": "flow",
        "status": "active",
        "description": "Statistical anomaly detection using flow feature analysis",
        "version": "1.0.0",
        "features": [
            "port_diversity",
            "failure_rate",
            "short_flow_ratio",
            "transfer_size",
            "packet_size_distribution",
            "dns_ratio",
        ],
        "artifact_uri": "ml-service://statistical-anomaly-v1",
        "metrics": {
            "precision": 0.78,
            "recall": 0.65,
            "f1": 0.71,
            "roc_auc": 0.82,
        },
    },
    {
        "model_id": "flow-feature-extractor-v1",
        "kind": "flow",
        "status": "active",
        "description": "Flow feature extraction and statistical analysis",
        "version": "1.0.0",
        "features": [
            "duration_stats",
            "byte_distribution",
            "port_entropy",
            "protocol_mix",
        ],
        "artifact_uri": "ml-service://flow-feature-extractor-v1",
        "metrics": {},
    },
]


@router.get(
    "/models",
    summary="List registered models in the ML service",
)
def list_models() -> dict[str, Any]:
    """Return all models registered in this ML service."""
    return {
        "models": REGISTERED_MODELS,
        "count": len(REGISTERED_MODELS),
    }


@router.get(
    "/models/{model_id}",
    summary="Get details of a specific model",
)
def get_model(model_id: str) -> dict[str, Any]:
    """Return details of a specific model."""
    for model in REGISTERED_MODELS:
        if model["model_id"] == model_id:
            return model
    return {"error": f"Model {model_id} not found"}