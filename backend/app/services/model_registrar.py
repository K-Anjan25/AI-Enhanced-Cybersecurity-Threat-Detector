"""Model registration service: fetches models from ML service and populates backend."""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import UTC, datetime
from typing import Any

import urllib.request
import urllib.error

from app.services.model_ops import ModelVersion

logger = logging.getLogger(__name__)

__all__ = ["ModelRegistrar"]


class ModelRegistrar:
    """Periodically fetches model info from ML service and registers in backend."""

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
        self._stats = {"registrations": 0, "errors": 0, "last_error": None}

    @property
    def stats(self) -> dict[str, Any]:
        return {**self._stats, "registered": list(self._registered.keys())}

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._register_models()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="model-registrar"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while self._running:
            time.sleep(self._interval)
            self._register_models()

    def _register_models(self) -> None:
        try:
            url = f"{self._ml_url}/models"
            logger.info("model_registrar_fetching url=%s", url)
            req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            logger.info("model_registrar_got_models count=%d", len(data.get("models", [])))

            for model in data.get("models", []):
                model_id = model.get("model_id", "")
                if not model_id or model_id in self._registered:
                    continue
                try:
                    version = ModelVersion(
                        model_id=model_id,
                        kind=model.get("kind", "flow"),
                        status=model.get("status", "staging"),
                        artifact_uri=model.get("artifact_uri", f"ml-service://{model_id}"),
                        sha256="0" * 64,
                        manifest_present=True,
                    )
                    self._model_ops.register(version)
                    try:
                        self._model_ops.promote(
                            model_id,
                            actor="model-registrar",
                            justification="Auto-registered from ML service",
                            at=datetime.now(UTC),
                        )
                    except Exception:
                        pass

                    self._registered[model_id] = model
                    self._stats["registrations"] += 1
                    logger.info("model_registrar_registered model_id=%s", model_id)
                except Exception as e:
                    self._stats["errors"] += 1
                    self._stats["last_error"] = str(e)
                    logger.warning("model_registrar_register_failed model_id=%s error=%s", model_id, str(e))

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["last_error"] = str(e)
            logger.warning("model_registrar_fetch_failed error=%s url=%s/models", str(e), self._ml_url)