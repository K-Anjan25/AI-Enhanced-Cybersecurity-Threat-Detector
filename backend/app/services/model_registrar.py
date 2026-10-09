"""Model registration service: fetches models from ML service and populates backend."""

from __future__ import annotations

import json
import logging
import threading
import urllib.request
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from app.services.model_ops import ModelVersion

logger = logging.getLogger(__name__)

__all__ = ["ModelRegistrar"]

#: Only these schemes may be fetched. The URL comes from configuration, but
#: ``urlopen`` also accepts ``file:`` and custom schemes, which must never be
#: reachable from a setting by accident.
_ALLOWED_SCHEMES = frozenset({"http", "https"})


def _fetch_json(url: str, timeout: float) -> dict[str, Any]:
    """Fetch one JSON document over http(s).

    Raises:
        ValueError: if the URL does not use http or https.
    """
    if urlsplit(url).scheme not in _ALLOWED_SCHEMES:
        msg = f"refusing to fetch {url!r}: only http and https are allowed"
        raise ValueError(msg)
    # The scheme is checked above, so neither call can open a file: or custom URL.
    request = urllib.request.Request(  # noqa: S310
        url, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310  # nosec B310
        document: dict[str, Any] = json.loads(response.read())
    return document


class ModelRegistrar:
    """Periodically fetches model info from ML service and registers in backend."""

    def __init__(
        self,
        ml_service_url: str,
        model_ops: Any,
        *,
        interval: float = 30.0,
    ) -> None:
        """Remember where the model service is and how often to ask it."""
        self._ml_url = ml_service_url.rstrip("/")
        self._model_ops = model_ops
        self._interval = interval
        self._running = False
        # An event, not a bare sleep, so stop() wakes the loop immediately
        # instead of holding shutdown for the whole join timeout.
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._registered: dict[str, Any] = {}
        self._stats: dict[str, Any] = {"registrations": 0, "errors": 0, "last_error": None}

    @property
    def stats(self) -> dict[str, Any]:
        """Registration counters and the ids registered so far."""
        return {**self._stats, "registered": list(self._registered.keys())}

    def start(self) -> None:
        """Register once immediately, then keep polling on a daemon thread."""
        if self._running:
            return
        self._running = True
        self._register_models()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="model-registrar")
        self._thread.start()

    def stop(self) -> None:
        """Stop polling and wait briefly for the thread to exit."""
        self._running = False
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        """Poll until stopped."""
        while self._running:
            if self._wake.wait(self._interval):
                break
            self._register_models()

    def _register_models(self) -> None:
        """Fetch the model list and register any id not yet seen."""
        url = f"{self._ml_url}/models"
        try:
            logger.info("model_registrar_fetching url=%s", url)
            data = _fetch_json(url, timeout=10)
            models: list[dict[str, Any]] = list(data.get("models", []))
            logger.info("model_registrar_got_models count=%d", len(models))
        except Exception as exc:  # noqa: BLE001 - any fetch failure is recorded, not raised
            self._record_error(exc)
            logger.warning("model_registrar_fetch_failed error=%s url=%s", exc, url)
            return

        for model in models:
            self._register_one(model)

    def _register_one(self, model: dict[str, Any]) -> None:
        """Register and attempt to promote one model entry from the service."""
        model_id = str(model.get("model_id", ""))
        if not model_id or model_id in self._registered:
            return
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
        except Exception as exc:  # noqa: BLE001 - one bad entry must not stop the others
            self._record_error(exc)
            logger.warning("model_registrar_register_failed model_id=%s error=%s", model_id, exc)
            return

        try:
            self._model_ops.promote(
                model_id,
                actor="model-registrar",
                justification="Auto-registered from ML service",
                at=datetime.now(UTC),
            )
        except Exception as exc:  # noqa: BLE001 - promotion is optional; registration stands
            logger.info("model_registrar_not_promoted model_id=%s reason=%s", model_id, exc)

        self._registered[model_id] = model
        self._stats["registrations"] += 1
        logger.info("model_registrar_registered model_id=%s", model_id)

    def _record_error(self, exc: BaseException) -> None:
        """Count one failure and remember its message."""
        self._stats["errors"] += 1
        self._stats["last_error"] = str(exc)
