"""The hunt console's export route (T-408, design.md §4.6, FR-23).

One route, and three things about it are rules rather than plumbing:

* **It is a ``POST``, and that is not an accident of the client.** The trail
  records changes, not requests (D-041), so a *read* does not belong in it -- but an
  export is not only a read: it is data leaving the system, and "who took what out"
  is precisely what the trail exists to answer. A route that writes an audit row
  changes state by the same rule the ingest routes do, which is why the coverage
  walk in ``test_audit.py`` finds it without being told about exports.
* **The body is the query, verbatim.** Re-using ``AlertQuery`` means the rows in the
  file are the rows the view showed, and the audit entry's definition is the
  definition that ran. A cursor is refused rather than ignored.
* **The capability is ``EXPORT``, which only ``responder`` and ``admin`` hold**
  (R-53). It is checked twice on purpose: the route declares the capability and
  ``ROUTE_MATRIX`` names the roles, and ``test_rbac.py`` fails if the two disagree.
  API keys are not accepted here at all -- a key is a machine credential for
  ingestion (FR-44), and an audited egress should carry a human actor.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.v1.deps import alert_store, audit_trail, client_ip
from app.auth.rbac import Capability, Principal, require
from app.schemas.hunt import CSV_MEDIA_TYPE, HuntExportRequest
from app.services.audit_log import AuditAction, record_action
from app.services.hunt_export import export_filename, query_definition, render_rows_csv
from app.services.query_service import paginate

__all__ = ["router"]

router = APIRouter(prefix="/api/v1", tags=["hunt"])

#: The dependency, named once: the docstring above says the capability is checked
#: here *and* in ``ROUTE_MATRIX``, and this is the half that returns the actor.
_Caller = Annotated[Principal, require(Capability.EXPORT)]


@router.post(
    "/hunt/export",
    summary="Export the alerts matching a hunt as CSV (FR-23)",
    response_class=Response,
    responses={
        200: {
            "description": "The matching rows as RFC-4180 CSV, in the published column order",
            "content": {CSV_MEDIA_TYPE: {"schema": {"type": "string"}}},
        }
    },
)
def export_hunt_results(
    body: HuntExportRequest,
    request: Request,
    caller: _Caller,
) -> Response:
    """Render one bounded page of a hunt's rows, and record that it was taken.

    The audit row is written **after** the rows are rendered and only then: a read
    that failed produced no file, so recording one would put a fiction in the
    trail. What it records is the definition, the row count and whether the query
    held more rows than the limit -- never a row's content (R-58), because the
    trail is readable by every role while a hunt may be scoped to one.

    The row count is the *exported* count, and ``truncated`` says whether the query
    had more. Both matter to a reviewer: "37 rows" and "37 of 4,000" are different
    disclosures, and only one of them is what the file holds.
    """
    query = body.to_query()
    try:
        rows = alert_store(request).fetch(query)
    except ValueError as exc:
        # The window's rules -- naive, inverted, or wider than R-34's span -- are
        # validated where the range is used, exactly as the list route does it. A
        # client error must not surface as a 500 from inside a store.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    page = paginate(rows, query)
    document = render_rows_csv(page.items)

    record_action(
        audit_trail(request),
        action=AuditAction.hunt_export,
        actor=caller.subject,
        target_type="hunt",
        target_id="export",
        at=datetime.now(UTC),
        detail={
            **query_definition(query),
            "rows": len(page.items),
            "truncated": page.next_cursor is not None,
            "format": "csv",
        },
        ip=client_ip(request),
    )

    return Response(
        content=document,
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{export_filename(query)}"'},
    )
