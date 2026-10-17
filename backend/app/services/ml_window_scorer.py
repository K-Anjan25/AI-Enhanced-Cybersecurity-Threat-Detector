"""Client for the ML service's ``POST /score/windows`` (2b, backend half).

The rule detector hands this client one source window of ingested ``flow@1`` dicts. The
client sends the most recent flows (the model's window length) and returns the trained
flow model's score with the features behind it.

Failure is never a score. A timeout, a refused connection, a 503 (no checkpoint loaded)
or a malformed reply returns ``None``, and the caller counts it. Reporting zero for an
unreachable model would show a detector outage as a clean network.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from app.core.logging import get_logger
from app.services.rule_detector import MlWindowResult

logger = get_logger("aegis.ml_window_scorer")

__all__ = ["MlWindowScorer"]

#: The model's window length. Longer windows are sent as their most recent flows.
MAX_FLOWS = 50
_ALLOWED_SCHEMES = frozenset({"http", "https"})


def _encode(value: object) -> str:
    """ISO-8601 for datetimes (what ``flow@1`` expects), text for everything else."""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _jsonable(value: object) -> object:
    """Make a stored ``flow@1`` value JSON-safe (IP addresses and datetimes arrive as objects)."""
    return json.loads(json.dumps(value, default=_encode))


def _recent(flows: list[dict[str, object]]) -> list[dict[str, Any]]:
    """The most recent ``MAX_FLOWS`` flows, oldest first, as JSON-safe dicts."""
    ordered = sorted(flows, key=lambda f: str(f.get("timestamp", f.get("ts", ""))))
    return [_jsonable(dict(f)) for f in ordered[-MAX_FLOWS:]]  # type: ignore[misc]


class MlWindowScorer:
    """Scores one window by calling the ML service over HTTP."""

    def __init__(self, base_url: str, *, timeout: float = 2.0) -> None:
        """Remember the ML service URL. Only http(s) is accepted."""
        scheme = urlsplit(base_url).scheme
        if scheme not in _ALLOWED_SCHEMES:
            raise ValueError(f"ML service URL must be http or https, got {scheme!r}")
        self._url = base_url.rstrip("/") + "/score/windows"
        self._timeout = timeout

    def score(self, flows: list[dict[str, object]]) -> MlWindowResult | None:
        """Score one window, or return None when the model could not give a score."""
        if not flows:
            return None
        body = json.dumps({"flows": _recent(flows)}).encode()
        request = urllib.request.Request(  # noqa: S310 - scheme checked in __init__
            self._url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310  # nosec B310
                payload = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            logger.warning("ml_window_scorer_refused status=%d", exc.code)
            return None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            logger.warning("ml_window_scorer_unreachable error=%s", str(exc))
            return None
        return _parse(payload)


def _parse(payload: object) -> MlWindowResult | None:
    """Read the reply, refusing anything that is not a score in [0, 1] with a model id."""
    if not isinstance(payload, dict):
        return None
    score = payload.get("score")
    model_id = payload.get("model_id")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        return None
    if not 0.0 <= float(score) <= 1.0 or not isinstance(model_id, str) or not model_id:
        return None
    raw_reasons = payload.get("reasons", [])
    reasons = tuple(str(r) for r in raw_reasons) if isinstance(raw_reasons, list) else ()
    return MlWindowResult(
        score=float(score),
        model_id=model_id,
        reasons=reasons,
        # The flow model is the only model serving; the log model is not in this path.
        partial_evidence=True,
    )
