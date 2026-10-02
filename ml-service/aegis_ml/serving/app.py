"""Inference application factory for the AEGIS model service.

Scoring endpoints arrive in T-209; this skeleton establishes the app shape, the
model registry, and the health contract that the backend probes.
"""

from __future__ import annotations

from fastapi import FastAPI, Request

from aegis_ml.registry.model_registry import ModelRegistry
from aegis_ml.serving.health import ServiceHealth, build_health

__version__ = "0.1.0"


def create_app(registry: ModelRegistry | None = None) -> FastAPI:
    """Build the inference FastAPI application.

    Args:
        registry: model registry to expose. When omitted an empty one is
            created, so a freshly started process reports ``no_model_loaded``.
    """
    app = FastAPI(
        title="AEGIS ML Service",
        description="Transformer inference for flow and log anomaly scoring. See architecture.md.",
        version=__version__,
    )
    app.state.registry = registry if registry is not None else ModelRegistry()
    app.state.version = __version__

    @app.get(
        "/internal/healthz",
        response_model=ServiceHealth,
        summary="Inference process health",
    )
    def healthz(request: Request) -> ServiceHealth:
        """Report process health and which model versions are resident."""
        return build_health(version=request.app.state.version, registry=request.app.state.registry)

    return app
