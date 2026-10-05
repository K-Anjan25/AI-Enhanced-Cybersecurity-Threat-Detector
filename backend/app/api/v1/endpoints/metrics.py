"""The Prometheus scrape endpoint (NFR-07, T-317).

``GET /metrics`` returns the text exposition format the Prometheus client
generates from the process registry, which is where every metric in this service
lands -- the domain counters in :mod:`app.observability.metrics` and the consumer
lag gauge in :mod:`app.messaging.lag`.

**It is unauthenticated, and that is a decision rather than an oversight.** A
scrape endpoint is read by a process, not by a person, and the alternatives are
all worse here: a token in the scraper's config is a credential to rotate and
leak, and the endpoint exposes counters and durations only -- no alert content,
no identifiers, no addresses, no tokens (R-58), which is asserted rather than
assumed. It is in ``UNAUTHENTICATED_ROUTES``, so R-56's rate limit covers it like
every other unauthenticated route, and the deployment that wants it closed can
put it behind the same network policy that fronts the service itself.

The response is cached for nothing and generated per scrape: the registry is
already in memory, and a cached exposition would report a moment that has passed.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

__all__ = ["router"]

router = APIRouter(tags=["observability"])


@router.get(
    "/metrics",
    summary="Prometheus metrics",
    response_class=Response,
    responses={200: {"content": {"text/plain": {}}, "description": "Prometheus exposition format"}},
)
def prometheus_metrics() -> Response:
    """Every metric this process exports, in the exposition format.

    Deliberately synchronous: it reads a registry and serialises it, which is CPU
    work with no I/O, and FastAPI runs a sync endpoint in its thread pool rather
    than blocking the event loop.
    """
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
