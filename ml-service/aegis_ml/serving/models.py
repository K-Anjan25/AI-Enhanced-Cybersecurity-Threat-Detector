"""Model registration endpoint for the ML service.

Returns all models available in this ML service. The backend's ModelRegistrar
fetches this endpoint and registers them in ModelOpsService so the Models
page shows real model information.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["models"])


class ModelInfo(BaseModel):
    """Information about a registered model."""

    model_id: str
    kind: str
    status: str
    description: str
    version: str
    features: list[str]
    artifact_uri: str
    metrics: dict[str, Any] = {}


# All models this service provides
REGISTERED_MODELS: list[dict[str, Any]] = [
    {
        "model_id": "statistical-anomaly-v1",
        "kind": "flow",
        "status": "active",
        "description": "Statistical anomaly detection using flow feature analysis. Always available as safety net.",  # noqa: E501
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
        "model_id": "flownet-v1",
        "kind": "flow",
        "status": "active",
        "description": "FlowNet transformer: 4-layer encoder with reconstruction + anomaly heads (~1.2M params). Detects novel patterns via reconstruction error.",  # noqa: E501
        "version": "1.0.0",
        "features": [
            "reconstruction_error",
            "anomaly_logits",
            "composite_score",
        ],
        "artifact_uri": "ml-service://flownet-v1",
        "metrics": {
            "architecture": "Transformer encoder (4 layers, d_model=176, 8 heads)",
            "parameters": "1,158,840",
            "training": "Self-supervised reconstruction + supervised anomaly head",
        },
    },
    {
        "model_id": "lognet-v1",
        "kind": "log",
        "status": "active",
        "description": "LogNet transformer: 6-layer encoder with masked-template prediction + hypersphere objective. Detects anomalous log sequences.",  # noqa: E501
        "version": "1.0.0",
        "features": [
            "masked_template_prediction",
            "hypersphere_distance",
        ],
        "artifact_uri": "ml-service://lognet-v1",
        "metrics": {
            "architecture": "Transformer encoder (6 layers)",
            "training": "Self-supervised masked-template + hypersphere",
        },
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
