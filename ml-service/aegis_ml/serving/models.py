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
        "metrics": {},
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


def flownet_entry(directory: str | None = None) -> dict[str, Any] | None:
    """The FlowNet model as it exists on disk, or ``None`` when no checkpoint is there.

    The model id and content address come from the checkpoint itself (R-68). A
    model that has no checkpoint is not listed, rather than listed under a name
    that identifies nothing.
    """
    import json  # noqa: PLC0415
    import os  # noqa: PLC0415

    from aegis_ml.serving.flownet_scorer import (  # noqa: PLC0415
        CONFIG_FILE,
        WEIGHTS_FILE,
        sha256_file,
    )

    root = directory or os.environ.get("AEGIS_FLOWNET_CHECKPOINT_DIR", "/models/flownet")
    weights = os.path.join(root, WEIGHTS_FILE)
    config_path = os.path.join(root, CONFIG_FILE)
    if not (os.path.isfile(weights) and os.path.isfile(config_path)):
        return None
    with open(config_path, encoding="utf-8") as handle:
        config = json.load(handle)
    return {
        "model_id": config["model_id"],
        "kind": "flow",
        "status": "active",
        "description": "FlowNet transformer trained on flow@1 windows (see its eval@2 report).",
        "version": "0.1.0",
        "features": ["reconstruction_error", "anomaly_logits"],
        "artifact_uri": f"ml-service://{config['model_id']}",
        "sha256": sha256_file(weights),
        "metrics": {},
    }


@router.get(
    "/models",
    summary="List registered models in the ML service",
)
def list_models() -> dict[str, Any]:
    """Return all models registered in this ML service."""
    models = list(REGISTERED_MODELS)
    flownet = flownet_entry()
    if flownet is not None:
        # FlowNet first: it is the trained flow model, and the registrar treats the
        # first active flow model as the incumbent.
        models.insert(0, flownet)
    return {
        "models": models,
        "count": len(models),
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
