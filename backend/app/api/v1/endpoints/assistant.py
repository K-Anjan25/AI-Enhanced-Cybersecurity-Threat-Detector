"""The embedded assistant: read-only questions about alerts and capture.

Any signed-in role with READ may ask. The assistant can refuse, and it cannot write:
its tools read the alert store and the capture request, and nothing else.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request, Response

from app.api.v1.deps import alert_store
from app.auth.rbac import Capability, require
from app.schemas.assistant import AskOut
from app.services.assistant.engine import AssistantConfig, answer_question
from app.services.assistant.tools import Context

router = APIRouter(tags=["assistant"])


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get(
    "/api/v1/assistant/ask",
    response_model=AskOut,
    summary="Ask the assistant a read-only question about alerts or capture",
    dependencies=[require(Capability.READ)],
)
def ask(
    request: Request,
    response: Response,
    question: str = Query(
        min_length=1, max_length=500, description="The question, in plain words."
    ),
) -> AskOut:
    """Answer from the alert store and the capture request. A GET: asking changes nothing."""
    _no_store(response)
    settings = request.app.state.settings
    config = AssistantConfig(
        backend=settings.assistant_backend,
        base_url=settings.assistant_base_url,
        model=settings.assistant_model,
        timeout_seconds=settings.assistant_timeout_seconds,
    )
    ctx = Context(
        alert_store=alert_store(request),
        capture_control=request.app.state.capture_control,
        now=datetime.now(UTC),
    )
    answer = answer_question(question, ctx, config)
    return AskOut(answer=answer.text, backend=answer.backend, sources=list(answer.sources))
