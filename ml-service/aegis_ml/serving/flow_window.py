"""``POST /score/windows``: score one ``flow@1`` window with the trained FlowNet.

This is the endpoint the backend calls for each closed per-source window. It takes
the canonical ``flow@1`` records (the same shape the backend validates on ingest),
scores them with the checkpoint, and returns the score with the top features behind
it (FR-14). When no checkpoint is loaded it refuses with 503 rather than returning
a zero, because a zero would read as a clean network.
"""

from __future__ import annotations

import os
import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aegis_ml.data.records import FlowRecord
from aegis_ml.serving.flownet_scorer import CheckpointError, FlowNetScorer

router = APIRouter(tags=["scoring"])

_lock = threading.Lock()
_scorer: FlowNetScorer | None = None
_load_error: str | None = None


class FlowWindowRequest(BaseModel):
    """One closed window of canonical flows, all from one source entity."""

    flows: list[FlowRecord] = Field(min_length=1, max_length=5_000)
    window_id: str | None = None


class FlowWindowScore(BaseModel):
    """The score for one window, with the evidence behind it."""

    score: float = Field(ge=0.0, le=1.0)
    model_id: str
    window_id: str | None = None
    scoring_method: str = "flownet"
    reasons: list[str] = []
    explanation_unavailable: bool = False
    flows: int


def _checkpoint_dir() -> str:
    return os.environ.get("AEGIS_FLOWNET_CHECKPOINT_DIR", "/models/flownet")


def get_scorer() -> FlowNetScorer:
    """Load the checkpoint once. Raises 503 if it is absent or does not load."""
    global _scorer, _load_error  # noqa: PLW0603
    with _lock:
        if _scorer is None and _load_error is None:
            try:
                _scorer = FlowNetScorer.load(_checkpoint_dir())
            except (CheckpointError, OSError, ValueError, KeyError, RuntimeError) as error:
                _load_error = f"{type(error).__name__}: {error}"
        if _scorer is None:
            raise HTTPException(
                status_code=503,
                detail={"error": "model_not_loaded", "reason": _load_error or "no checkpoint"},
            )
        return _scorer


def reset_scorer() -> None:
    """Forget the loaded checkpoint so the next request re-reads it. Used by tests."""
    global _scorer, _load_error  # noqa: PLW0603
    with _lock:
        _scorer = None
        _load_error = None


@router.post(
    "/score/windows",
    response_model=FlowWindowScore,
    summary="Score one flow@1 window with the trained FlowNet",
)
def score_flow_window(request: FlowWindowRequest) -> FlowWindowScore:
    """Score a window and explain it. The score is the highest chunk score (see scorer)."""
    scorer = get_scorer()
    try:
        result = scorer.score(request.flows)
    except ValueError as exc:
        # A window the model cannot be given (for example one that mixes sources) is a
        # bad request. It is not a server fault, so it must not come back as a 500.
        raise HTTPException(
            status_code=422, detail={"error": "invalid_window", "reason": str(exc)}
        ) from exc
    return FlowWindowScore(
        score=result.score,
        model_id=result.model_id,
        window_id=request.window_id,
        reasons=[reason.render() for reason in result.reasons],
        explanation_unavailable=result.explanation_unavailable,
        flows=result.flows,
    )
