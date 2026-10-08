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

from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Annotated, TypeVar

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.api.openapi_docs import ndjson_batch_body
from app.api.v1.deps import admission, audit_trail, client_ip, flow_source, log_source
from app.auth.rbac import Capability, Principal, require
from app.observability import metrics
from app.schemas.ingest import (
    MAX_FLOW_RECORDS,
    MAX_LOG_LINES,
    FlowRecordIn,
    IngestResponse,
    LogRecordIn,
    RecordError,
)
from app.services.audit_log import AuditAction, record_action
from app.services.flow_store import FlowStoreUnavailable
from app.services.ingest_service import BatchTooLarge, UnsupportedMediaType, ingest_batch
from app.services.log_store import LogStoreUnavailable

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])

#: The ingest routes are generic over the record model they validate (flow@1, log@1);
#: ``keep`` is the one hook that receives them, and it is typed by the call site.
_T = TypeVar("_T", bound=BaseModel)

#: FR-01/FR-02 accept JSON or NDJSON. NDJSON is the streaming form and is what
#: collectors send; JSON is what a human debugging with curl will send.
_NDJSON = "application/x-ndjson"


async def _ingest(
    request: Request,
    response: Response,
    body: bytes,
    model: type[_T],
    limit: int,
    *,
    caller: Principal,
    action: AuditAction,
    modality: str,
    keep: Callable[[Sequence[_T]], Awaitable[int]] | None = None,
) -> IngestResponse:
    """Run one ingest, translate batch-level failures into status codes, audit it.

    ``keep`` is where accepted records go to be *shown* rather than scored -- the
    log read model (T-407's tail, or T-419's store, whichever the deployment
    configured). It is an awaitable callable rather than a store lookup so this
    helper keeps knowing nothing about what a deployment hangs off an ingest, and it
    is called after the hand-off, beside the audit row, so a request that failed on
    its way out kept nothing. It is awaited for the same reason it is called here
    rather than later: a store write that has not committed when the response is sent
    is a line the caller was told was taken in and cannot read back.

    These are the failures that have no record to attribute them to, so they
    cannot be expressed as entries in a per-record error list.

    The audit entry is written here and not by the caller, and only when the
    batch put something into the system. A refused, oversized or entirely
    rejected batch changed nothing, so recording it would let any client grow the
    trail with rows of its choosing -- the access log already holds that the
    request was made. A partly-bad batch *is* recorded, carrying both counts:
    what the trail refuses to keep is the record content, not the fact that some
    records were turned away.
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
    # Accepted records are handed to the broker by the composition root's
    # publisher when one is wired (T-319). With no publisher -- no consumer in this
    # process -- the count is still the contract and the records stop here, which
    # is what every deployment before the pipeline had.
    request.state.accepted_records = accepted
    publisher = getattr(request.app.state, "flow_publisher", None)
    traceparent = getattr(request.state, "traceparent", None)
    # Back-pressure (architecture.md §12, T-316). The budget is taken for the
    # records this batch puts in flight and returned when the request ends; a
    # producer would release on delivery instead, which is D-039's decision. A
    # batch that does not fit is refused **whole** -- admitting the part that fits
    # and failing the request would be the silent partial write the trail exists to
    # prevent -- and the client is told to retry rather than left to guess.
    controller = admission(request)
    admitted = controller.admit(result.accepted)
    # Counters move after validation and admission: the rejections happened
    # whether or not the batch fit, and nothing counts as ingested that the
    # buffer refused, or "flows ingested" would include records that were
    # turned away and will be retried.
    metrics.observe_ingest(
        modality,
        accepted=result.accepted if admitted else 0,
        rejected=_rejected_by_stage(result.errors),
    )
    if not admitted:
        raise HTTPException(
            status_code=503,
            detail=(
                "ingest buffer is full; the batch was refused whole so it can be "
                "retried without duplicating records"
            ),
            headers={"Retry-After": str(controller.retry_after())},
        )
    try:
        if result.accepted == 0:
            return result
        if publisher is not None:
            # Before the audit row, deliberately: a record is not audited as taken
            # in unless it was handed on.
            publisher.publish(accepted, traceparent=traceparent)
        if keep is not None:
            # Fed where the trail is fed, and after the hand-off for the same
            # reason: a request that failed before publishing kept nothing, so the
            # read model never shows a line the pipeline never saw. Awaited, so a
            # line the caller is told was taken in is a line the next read can find;
            # a store that cannot write fails the request rather than losing the
            # batch quietly -- the records were enqueued, so a retry duplicates
            # rather than loses, which is T-307's rule for the worker applied here.
            await keep(accepted)
        # Feed accepted flows to the rule-based detection engine.
        detection_engine = getattr(request.app.state, "detection_engine", None)
        if detection_engine is not None and modality == "flow" and accepted:
            detection_engine.feed([r.model_dump() for r in accepted])
        record_action(
            audit_trail(request),
            action=action,
            actor=caller.subject,
            target_type="ingest",
            target_id=action.value,
            at=datetime.now(UTC),
            # Counts and a media type: enough to know what was taken in, with no
            # record content and no source addresses (R-54, R-58).
            detail={
                "received": result.received,
                "accepted": result.accepted,
                "rejected": result.rejected,
            },
            ip=client_ip(request),
        )
        return result
    finally:
        controller.release(result.accepted)


def _rejected_by_stage(errors: Sequence[RecordError]) -> dict[str, int]:
    """How many records each validation stage refused, for the rejection counter.

    The unit is the **record**, not the error: a record missing three fields
    appears three times in ``errors``, and a counter that iterated the list would
    report three records where the collector has one to fix. The stage comes from
    the ingest service's own vocabulary (``parse`` when a line is not JSON,
    ``validation`` when it is JSON that fails the schema), so the label cannot be
    chosen by the sender.
    """
    seen: set[tuple[int, str]] = set()
    counts: dict[str, int] = {}
    for error in errors:
        key = (error.index, error.stage)
        if key in seen:
            continue
        seen.add(key)
        counts[error.stage] = counts.get(error.stage, 0) + 1
    return counts


@router.post(
    "/flows",
    response_model=IngestResponse,
    summary="Ingest flow records (flow@1)",
    # The route reads the bytes itself, so FastAPI cannot infer the body; the
    # declared contract names the schema the parse path enforces (T-320).
    openapi_extra=ndjson_batch_body(FlowRecordIn),
)
async def ingest_flows(
    request: Request,
    response: Response,
    caller: Annotated[Principal, require(Capability.INGEST)],
) -> IngestResponse:
    """Accept up to 1,000 flow records as JSON or NDJSON (FR-01)."""
    body = await request.body()
    try:
        return await _ingest(
            request,
            response,
            body,
            FlowRecordIn,
            MAX_FLOW_RECORDS,
            caller=caller,
            action=AuditAction.ingest_flows,
            modality="flow",
            # The read model the traffic explorer reads (T-418): the store when the
            # deployment configured one, the in-process rollup otherwise. A flow record
            # has no line to fold, so this is the flow route's own hook and not the
            # log tail's.
            keep=flow_source(request).append,
        )
    except FlowStoreUnavailable as exc:
        # The batch was validated and handed to the broker, and the store refused it.
        # 503 rather than 200: the caller would otherwise be told the traffic was taken
        # in while the next read cannot find it. A retry duplicates on the broker rather
        # than losing traffic, which is T-307's rule for the worker.
        raise HTTPException(
            status_code=503,
            detail=f"the batch was accepted but could not be stored: {exc}",
        ) from exc


@router.post(
    "/logs",
    response_model=IngestResponse,
    summary="Ingest log lines (log@1)",
    openapi_extra=ndjson_batch_body(LogRecordIn),
)
async def ingest_logs(
    request: Request,
    response: Response,
    caller: Annotated[Principal, require(Capability.INGEST)],
) -> IngestResponse:
    """Accept up to 5,000 log lines as JSON or NDJSON (FR-02)."""
    body = await request.body()
    try:
        return await _ingest(
            request,
            response,
            body,
            LogRecordIn,
            MAX_LOG_LINES,
            caller=caller,
            action=AuditAction.ingest_logs,
            modality="log",
            # The read model the explorer reads (T-407's tail, or T-419's store when
            # the deployment configured one). Only log batches are kept: a flow record
            # has no line to show, and the traffic explorer reads its own set.
            keep=log_source(request).append,
        )
    except LogStoreUnavailable as exc:
        # The batch was validated and handed to the broker, and the store refused it.
        # 503 rather than 200: the caller would otherwise be told the records were
        # taken in while the next read cannot find them. A retry duplicates on the
        # broker rather than losing a line, which is T-307's rule for the worker.
        raise HTTPException(
            status_code=503,
            detail=f"the batch was accepted but could not be stored: {exc}",
        ) from exc


def ndjson_media_type() -> str:
    """The media type collectors should send."""
    return _NDJSON
