"""Model registration service: fetches models from ML service and populates backend."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import urllib.request
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from app.services.ml_auth import ml_request_headers
from app.services.model_ops import ModelVersion

logger = logging.getLogger(__name__)

__all__ = ["ModelRegistrar"]

#: Only these schemes may be fetched. The URL comes from configuration, but
#: ``urlopen`` also accepts ``file:`` and custom schemes, which must never be
#: reachable from a setting by accident.
_ALLOWED_SCHEMES = frozenset({"http", "https"})

#: A content address as R-68 defines it. The ML service must supply one.
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

#: Suffix of the ``eval@2`` report files the training run writes (see
#: ``scripts/train_flownet.py --checkpoint``). The run config sits beside each one.
_EVAL_SUFFIX = ".eval.json"
_CONFIG_SUFFIX = ".config.json"


def _fetch_json(url: str, timeout: float, token: str | None = None) -> dict[str, Any]:
    """Fetch one JSON document over http(s).

    Raises:
        ValueError: if the URL does not use http or https.
    """
    if urlsplit(url).scheme not in _ALLOWED_SCHEMES:
        msg = f"refusing to fetch {url!r}: only http and https are allowed"
        raise ValueError(msg)
    # The scheme is checked above, so neither call can open a file: or custom URL.
    request = urllib.request.Request(  # noqa: S310
        url, headers=ml_request_headers(token)
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
        eval_reports_dir: str | None = None,
        service_token: str | None = None,
    ) -> None:
        """Remember the model service, the poll interval, and where reports live.

        ``eval_reports_dir`` is optional. When set, every ``*.eval.json`` report whose
        ``model_id`` matches a registered version is attached to that version.
        """
        self._ml_url = ml_service_url.rstrip("/")
        self._token = service_token
        self._model_ops = model_ops
        self._interval = interval
        self._eval_dir = eval_reports_dir or None
        self._evaluated: set[str] = set()
        self._refused: set[str] = set()
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
            data = _fetch_json(url, timeout=10, token=self._token)
            models: list[dict[str, Any]] = list(data.get("models", []))
            logger.info("model_registrar_got_models count=%d", len(models))
        except Exception as exc:  # noqa: BLE001 - any fetch failure is recorded, not raised
            self._record_error(exc)
            logger.warning("model_registrar_fetch_failed error=%s url=%s", exc, url)
            return

        for model in models:
            self._register_one(model)
            model_id = str(model.get("model_id", ""))
            if model_id in self._registered:
                self._attach_evaluation(model_id)

    def _attach_evaluation(self, model_id: str) -> None:
        """Attach the matching ``eval@2`` report for a registered version, once.

        A report that does not match, or is malformed, is logged and skipped; it never
        stops registration. A version with no report stays without metrics, which is
        the honest state, not a zero.
        """
        if self._eval_dir is None or model_id in self._evaluated:
            return
        try:
            names = sorted(n for n in os.listdir(self._eval_dir) if n.endswith(_EVAL_SUFFIX))
        except OSError as exc:
            logger.warning(
                "model_registrar_eval_dir_unreadable dir=%s error=%s", self._eval_dir, exc
            )
            return
        for name in names:
            path = os.path.join(self._eval_dir, name)
            try:
                with open(path, encoding="utf-8") as handle:
                    report = json.load(handle)
            except (OSError, ValueError) as exc:
                logger.warning("model_registrar_eval_unreadable path=%s error=%s", path, exc)
                continue
            if not isinstance(report, dict) or report.get("model_id") != model_id:
                continue
            split = "unspecified"
            config_path = path[: -len(_EVAL_SUFFIX)] + _CONFIG_SUFFIX
            if os.path.isfile(config_path):
                try:
                    with open(config_path, encoding="utf-8") as handle:
                        split = str(json.load(handle).get("split_policy", split))
                except (OSError, ValueError):
                    logger.warning("model_registrar_config_unreadable path=%s", config_path)
            evaluated_at = datetime.fromtimestamp(os.path.getmtime(path), tz=UTC)
            try:
                self._model_ops.record_evaluation(
                    model_id,
                    report,
                    artifact=os.path.relpath(path, self._eval_dir),
                    split=split,
                    evaluated_at=evaluated_at,
                )
            except Exception as exc:  # noqa: BLE001 - a bad report must not stop the others
                self._record_error(exc)
                logger.warning(
                    "model_registrar_eval_rejected model_id=%s path=%s error=%s",
                    model_id,
                    path,
                    exc,
                )
                continue
            self._evaluated.add(model_id)
            logger.info("model_registrar_evaluation_attached model_id=%s split=%s", model_id, split)
            return

    def _register_one(self, model: dict[str, Any]) -> None:
        """Register and attempt to promote one model entry from the service."""
        model_id = str(model.get("model_id", ""))
        if not model_id or model_id in self._registered:
            return
        # R-68: a version is identified by its content address. An entry without a real
        # sha256 identifies nothing, so it is refused, not registered under a placeholder.
        sha256 = str(model.get("sha256", ""))
        if not _SHA256.match(sha256):
            if model_id not in self._refused:
                self._refused.add(model_id)
                logger.warning("model_registrar_refused_no_content_address model_id=%s", model_id)
            return
        kind = model.get("kind", "flow")
        status = model.get("status", "staging")
        # The ML service reports every model it can score with as "active", so it can
        # list two active flow models (the statistical fallback and FlowNet). The
        # registry allows one active version per kind. The first one listed becomes
        # the incumbent; any other "active" entry is registered as staging and is
        # not promoted, because promotion would retire the incumbent. Promoting is a
        # decision for an operator, not for this loop.
        incumbent = self._model_ops.active(kind) if status == "active" else None
        staged = incumbent is not None and incumbent.model_id != model_id
        if staged:
            status = "staging"
        try:
            version = ModelVersion(
                model_id=model_id,
                kind=kind,
                status=status,
                artifact_uri=model.get("artifact_uri", f"ml-service://{model_id}"),
                sha256=sha256,
                # R-63: the ML service reports whether the manifest is complete.
                manifest_present=model.get("manifest_present") is True,
            )
            self._model_ops.register(version)
        except Exception as exc:  # noqa: BLE001 - one bad entry must not stop the others
            self._record_error(exc)
            logger.warning("model_registrar_register_failed model_id=%s error=%s", model_id, exc)
            return

        if staged:
            logger.info(
                "model_registrar_staged model_id=%s kind=%s incumbent=%s",
                model_id,
                kind,
                incumbent.model_id if incumbent is not None else "",
            )
        else:
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
