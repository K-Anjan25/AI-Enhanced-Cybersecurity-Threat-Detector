"""Model registration service: fetches models from ML service and populates backend.

This makes the Models page show real model data by fetching from the ML service's
/models endpoint and registering them in the backend's ModelOpsService.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from typing import Any

import urllib.request
import urllib.error

from app.services.model_ops import ModelVersion

__all__ = ["ModelRegistrar"]


class ModelRegistrar:
    """Periodically fetches model info from ML service and registers in backend.

    This bridges the gap between:
    - ML service: knows what models exist and their metrics
    - Backend ModelOpsService: serves /api/v1/models to the dashboard
    """

    def __init__(
        self,
        ml_service_url: str,
        model_ops: Any,
        *,
        interval: float = 30.0,
    ) -> None:
        self._ml_url = ml_service_url.rstrip("/")
        self._model_ops = model_ops
        self._interval = interval
        self._running = False
        self._thread: threading.Thread | None = None
        self._registered: dict[str, Any] = {}
        self._stats = {"registrations": 0, "errors": 0}

    @property
    def stats(self) -> dict[str, Any]:
        return {**self._stats, "registered": list(self._registered.keys())}

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="model-registrar"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        # First attempt immediately
        self._register_models()
        while self._running:
            time.sleep(self._interval)
            try:
                self._register_models()
            except Exception:
                pass

    def _register_models(self) -> None:
        """Fetch models from ML service and register them."""
        try:
            req = urllib.request.Request(
                f"{self._ml_url}/models",
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())

            for model in data.get("models", []):
                model_id = model.get("model_id", "")
                if model_id and model_id not in self._registered:
                    # Create a ModelVersion and register it
                    try:
                        version = ModelVersion(
                            model_id=model_id,
                            kind=model.get("kind", "flow"),
                            status=model.get("status", "active"),
                            artifact_uri=model.get("artifact_uri", f"ml-service://{model_id}"),
                            sha256="",
                            manifest_present=True,
                        )
                        self._model_ops.register(version)
                        self._registered[model_id] = model
                        self._stats["registrations"] += 1
                    except Exception as e:
                        self._stats["errors"] += 1

        except Exception as e:
            self._stats["errors"] += 1