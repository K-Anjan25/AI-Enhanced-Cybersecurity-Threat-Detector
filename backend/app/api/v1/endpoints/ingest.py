"""Ingest endpoints (FR-01, FR-02, FR-04).

Thin by design (R-13): read the body, hand it to the service, serialise the
result. The service owns the batch semantics so they are testable without an
HTTP layer.

A batch that is partly bad returns **207-style information in a 200 body**
rather than a 4xx, because the request did succeed for most of its records and
a client that sees 422 will reasonably retry the whole batch and duplicate the
records that were accepted. The counts in the body are the contract.

Batch-level failures are the exception and do return an error status: an
oversized batch has no record to attribute the problem to.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.auth.rbac import Capability, require
from app.schemas.ingest import (
    MAX_FLOW_RECORDS,
    MAX_LOG_LINES,
    FlowRecordIn,
    IngestResponse,
    LogRecordIn,
)
from app.services.ingest_service import BatchTooLarge, UnsupportedMediaType, ingest_batch

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])

#: FR-01/FR-02 accept JSON or NDJSON. NDJSON is the streaming form and is what
#: collectors send; JSON is what a human debugging with curl will send.
_NDJSON = "application/x-ndjson"


def _ingest(
    request: Request,
    response: Response,
    body: bytes,
    model: type[BaseModel],
    limit: int,
) -> IngestResponse:
    """Run one ingest, translating batch-level failures into status codes.

    These are the failures that have no record to attribute them to, so they
    cannot be expressed as entries in a per-record error list.
    """
    content_type = request.headers.get("content-type", "")
    try:
        result, accepted = ingest_batch(body, model, limit=limit, content_type=content_type)
    except BatchTooLarge as exc:
        # 413 rather than 422: the problem is the size of the request, and a
        # client that sees 422 will retry the same oversized batch.
        raise HTTPException(
            status_code=413,
            detail=f"batch of {exc.received} records exceeds the limit of {exc.limit}",
        ) from exc
    except UnsupportedMediaType as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    # Accepted records are handed to the persistence layer by T-307; until then
    # the count is the contract and the records are validated and discarded.
    request.state.accepted_records = accepted
    return result


@router.post(
    "/flows",
    response_model=IngestResponse,
    summary="Ingest flow records (flow@1)",
    dependencies=[require(Capability.INGEST)],
)
async def ingest_flows(request: Request, response: Response) -> IngestResponse:
    """Accept up to 1,000 flow records as JSON or NDJSON (FR-01)."""
    body = await request.body()
    return _ingest(request, response, body, FlowRecordIn, MAX_FLOW_RECORDS)


@router.post(
    "/logs",
    response_model=IngestResponse,
    summary="Ingest log lines (log@1)",
    dependencies=[require(Capability.INGEST)],
)
async def ingest_logs(request: Request, response: Response) -> IngestResponse:
    """Accept up to 5,000 log lines as JSON or NDJSON (FR-02)."""
    body = await request.body()
    return _ingest(request, response, body, LogRecordIn, MAX_LOG_LINES)


def ndjson_media_type() -> str:
    """The media type collectors should send."""
    return _NDJSON
