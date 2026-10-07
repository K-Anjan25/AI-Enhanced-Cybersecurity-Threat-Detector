"""Alert query and verdict endpoints.

`start` and `end` are required query parameters, and so is `created_at` on the
verdict routes. They are not optional with a generous default, because a default
is how an unbounded scan of a partitioned table gets shipped -- R-34 -- and per
D-030 an alert id alone does not identify a row across partitions.

The routers stay thin (R-13): parse, call a service, serialise. Everything worth
testing about verdicts -- immutability, supersession, the repeat rule -- lives in
``app.services.verdict_service`` and is tested without an HTTP server.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.api.v1.deps import alert_store, audit_trail, client_ip, retention_policy
from app.auth.rbac import Capability, Principal, require
from app.schemas.alert_detail import AlertDetailOut
from app.schemas.alert_export import AlertExportRequest, ExportFormat
from app.schemas.hunt import CSV_MEDIA_TYPE
from app.schemas.query import MAX_PAGE_SIZE, AlertPage, AlertQuery, CursorError
from app.schemas.verdict import (
    VerdictHistoryOut,
    VerdictOutcomeOut,
    VerdictRecordOut,
    VerdictRequest,
)
from app.services.alert_detail import (
    FAMILY_HISTORY_DAYS,
    RELATED_LIMIT,
    detail_of,
    related_window,
)
from app.services.alert_export import (
    PDF_MEDIA_TYPE,
    alert_export_filename,
    now_utc,
    render_rows_pdf,
)
from app.services.audit_log import AuditAction, record_action
from app.services.query_service import paginate
from app.services.table_export import query_definition, render_rows_csv
from app.services.verdict_service import (
    InMemoryVerdictLedger,
    UnknownVerdict,
    VerdictAction,
    VerdictLedger,
    VerdictRecord,
    record_verdict,
)

router = APIRouter(prefix="/api/v1", tags=["alerts"])


#: The export's caller. The capability is declared here *and* in ``ROUTE_MATRIX``,
#: and ``test_rbac.py`` fails if the two disagree -- the same double check T-408's
#: hunt export makes, because an audited egress is the wrong place to be clever.
_Exporter = Annotated[Principal, require(Capability.EXPORT)]


@router.post(
    "/alerts/export",
    summary="Export an alert batch as CSV or PDF (FR-23)",
    response_class=Response,
    responses={
        200: {
            "description": (
                "The matching rows: RFC-4180 CSV, or a PDF report with the filter on the page"
            ),
            "content": {
                CSV_MEDIA_TYPE: {"schema": {"type": "string"}},
                PDF_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}},
            },
        }
    },
)
def export_alert_batch(
    body: AlertExportRequest,
    request: Request,
    caller: _Exporter,
) -> Response:
    """Render one bounded page of the queue's rows, and record that they were taken.

    The same contract as the hunt console's export, one screen over: the body *is*
    the filter definition, the rows are the rows the queue showed, and the audit row
    is written **after** the document is rendered -- a read that failed produced no
    file, so recording one would put a fiction in the trail.

    What the trail records is the definition, the row count and the format; never a
    row's content (R-58), because the trail is readable by every role while an alert
    batch may be scoped to one. ``truncated`` says whether the query held more rows
    than the export's limit, because "37 rows" and "37 of 4,000" are different
    disclosures and only one of them is what the file holds.

    The PDF prints the definition as well; the CSV does not, and that asymmetry is
    T-408's decision (a preamble would break every parser) with T-415's addition (a
    report read by a person without its window is not a report).
    """
    query = body.to_query()
    try:
        rows = alert_store(request).fetch(query)
    except ValueError as exc:
        # R-34's window rules are validated where the range is used, exactly as the
        # list route does it: a client error must not surface as a 500.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    page = paginate(rows, query)
    truncated = page.next_cursor is not None

    document: str | bytes
    if body.format is ExportFormat.PDF:
        document = render_rows_pdf(page.items, query, generated_at=now_utc(), truncated=truncated)
        media_type = PDF_MEDIA_TYPE
    else:
        document = render_rows_csv(page.items)
        media_type = CSV_MEDIA_TYPE

    record_action(
        audit_trail(request),
        action=AuditAction.alert_export,
        actor=caller.subject,
        target_type="alert_batch",
        target_id="export",
        at=datetime.now(UTC),
        detail={
            **query_definition(query),
            "rows": len(page.items),
            "truncated": truncated,
            "format": body.format.value,
        },
        ip=client_ip(request),
    )

    filename = alert_export_filename(query, body.format.value)
    return Response(
        content=document,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # How many rows the file carries, which is the same number the audit row
            # records. It is a header rather than something the client counts out of
            # the document, because a CSV re-parse would be work the server already
            # did and a PDF cannot be parsed by the dashboard at all -- and because
            # two counts that could disagree are worse than one that is stated.
            "X-Export-Rows": str(len(page.items)),
            # Whether the query held more rows than the file does. The trail records
            # it, and the operator is told as well: "100 rows" and "100 of 4,000" are
            # different answers to "did I get everything?".
            "X-Export-Truncated": "true" if truncated else "false",
        },
    )


def _ledger(request: Request) -> VerdictLedger:
    """The verdict store, from app state.

    The process-wide instance is in-memory in this environment and is replaced
    by the persistent ledger where the database is wired; the type is the
    protocol, so the route cannot tell which one it has.
    """
    ledger: VerdictLedger | None = getattr(request.app.state, "verdict_ledger", None)
    if ledger is None:
        ledger = InMemoryVerdictLedger()
        request.app.state.verdict_ledger = ledger
    return ledger


def _record_out(record: VerdictRecord) -> VerdictRecordOut:
    """Serialise one verdict record."""
    return VerdictRecordOut(
        id=record.id,
        alert_id=record.alert_id,
        verdict=record.verdict.value,
        actor=record.actor,
        at=record.at,
        note=record.note,
        supersedes=record.supersedes,
    )


def _parse_created_at(value: str) -> datetime:
    """Parse the alert's partition key, refusing anything unusable.

    A naive timestamp is refused rather than assumed to be UTC: it addresses a
    different instant than the aware value the row was written with, so the
    lookup would silently find nothing.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="created_at must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HTTPException(
            status_code=400,
            detail="created_at must carry a timezone; a naive timestamp addresses a "
            "different instant than the one the alert was stored with",
        )
    return parsed


@router.get(
    "/alerts/{alert_id}",
    response_model=AlertDetailOut,
    summary="Read one alert with its explanation, evidence, verdict and context (FR-51)",
    dependencies=[require(Capability.READ)],
)
def get_alert(
    alert_id: int,
    request: Request,
    created_at: str = Query(
        description="The alert's created_at, which addresses its partition (D-030)."
    ),
) -> AlertDetailOut:
    """Return everything the triage screen's four zones render.

    Four bounded reads, one response: the alert itself, alerts on the same entity
    around it, alerts on the same entity and family before it, and the verdict
    ledger. The triage screen is where a second round trip is most expensive, and
    each window is small enough to answer from one partition.

    A missing row is a 404, and it is the *pair* that is missing: the same id in
    another month is a different alert, so the lookup uses both halves of the key.
    """
    partition_key = _parse_created_at(created_at)
    store = alert_store(request)
    alert = store.get(alert_id, partition_key)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"no alert {alert_id} at that created_at")

    start, end = related_window(alert)
    # The store returns up to ``limit + 1`` rows by contract, which is how the
    # caller learns that a next page exists; asking for one more again would be a
    # second copy of a rule the store already owns.
    related_rows = store.fetch(
        AlertQuery(start=start, end=end, entity_id=alert.entity_id, limit=RELATED_LIMIT)
    )
    history_start = alert.created_at - timedelta(days=FAMILY_HISTORY_DAYS)
    family_rows = store.fetch(
        AlertQuery(
            start=history_start,
            end=alert.created_at,
            entity_id=alert.entity_id,
            limit=MAX_PAGE_SIZE,
        )
    )
    return detail_of(
        alert,
        ledger=_ledger(request),
        related_rows=related_rows,
        family_rows=family_rows,
        now=datetime.now(UTC),
        policy=retention_policy(request),
        related_truncated=len(related_rows) > RELATED_LIMIT,
    )


@router.post(
    "/alerts/{alert_id}/verdict",
    response_model=VerdictOutcomeOut,
    summary="Record an analyst verdict on an alert (FR-16)",
)
def record_alert_verdict(
    alert_id: int,
    body: VerdictRequest,
    request: Request,
    # Annotated rather than a `dependencies=[...]` list: the route needs *who*
    # acted as well as that they may, and this is the shape that returns it.
    caller: Annotated[Principal, require(Capability.VERDICT)],
) -> VerdictOutcomeOut:
    """Append the analyst's verdict, superseding any current one.

    A repeat of the verdict already current, by the same analyst, returns
    ``unchanged`` instead of appending: a client retry must not manufacture a
    reconsideration that never happened.

    The audit entry records the *decision*, not the analyst's reasoning: the
    verdict value and the record it superseded, never the note text (FR-42, R-58).
    An ``unchanged`` outcome wrote nothing, so it is not audited -- a row per
    re-sent request would be a log the client controls.
    """
    try:
        outcome = record_verdict(
            _ledger(request),
            alert_id=alert_id,
            alert_created_at=body.created_at,
            verdict=body.verdict,
            actor=caller.subject,
            at=datetime.now(UTC),
            note=body.note,
        )
    except UnknownVerdict as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        # A naive timestamp, an empty actor or an over-long note.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if outcome.action is VerdictAction.recorded:
        record_action(
            audit_trail(request),
            action=AuditAction.alert_verdict,
            actor=caller.subject,
            target_type="alert",
            target_id=str(alert_id),
            at=datetime.now(UTC),
            detail={
                "verdict": outcome.record.verdict.value,
                "record": outcome.record.id,
                "superseded": outcome.superseded.id if outcome.superseded else None,
            },
            ip=client_ip(request),
        )
    return VerdictOutcomeOut(
        action=outcome.action.value,
        record=_record_out(outcome.record),
        superseded=_record_out(outcome.superseded) if outcome.superseded else None,
    )


@router.get(
    "/alerts/{alert_id}/verdicts",
    response_model=VerdictHistoryOut,
    summary="Read an alert's verdict history, oldest first (FR-16, FR-18)",
    dependencies=[require(Capability.READ)],
)
def list_alert_verdicts(
    alert_id: int,
    request: Request,
    created_at: str = Query(
        description="The alert's created_at, which addresses its partition (D-030)."
    ),
) -> VerdictHistoryOut:
    """Return every verdict on one alert, and the current one."""
    partition_key = _parse_created_at(created_at)
    history = _ledger(request).history(alert_id, partition_key)
    current = history[-1] if history else None
    return VerdictHistoryOut(
        alert_id=alert_id,
        created_at=partition_key,
        current=_record_out(current) if current else None,
        items=[_record_out(record) for record in history],
    )


@router.get(
    "/alerts",
    response_model=AlertPage,
    summary="Query alerts within a time window",
    dependencies=[require(Capability.READ)],
)
def list_alerts(
    request: Request,
    start: str = Query(description="Inclusive lower bound, ISO-8601 with timezone."),
    end: str = Query(description="Exclusive upper bound, ISO-8601 with timezone."),
    severity: str | None = None,
    status: str | None = None,
    family: str | None = None,
    entity_id: int | None = None,
    min_score: float | None = Query(default=None, ge=0.0, le=1.0),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=100, ge=1, le=1_000),
    cursor: str | None = None,
) -> AlertPage:
    """Return one page of alerts matching the filters, newest first by default."""
    from datetime import datetime  # noqa: PLC0415

    try:
        query = AlertQuery(
            start=datetime.fromisoformat(start),
            end=datetime.fromisoformat(end),
            severity=severity,
            status=status,
            family=family,
            entity_id=entity_id,
            min_score=min_score,
            order=order,
            limit=limit,
            cursor=cursor,
        )
    except CursorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        # A naive or inverted range, or one wider than the R-34 span limit.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        rows = alert_store(request).fetch(query)
    except ValueError as exc:
        # The range is validated where it is used (R-34), so a naive, inverted or
        # over-wide window is a client error rather than a 500.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return paginate(rows, query)
