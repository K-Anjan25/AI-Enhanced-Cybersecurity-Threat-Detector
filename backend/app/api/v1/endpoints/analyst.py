"""Autonomous-analyst API (Phases 18-19, 36-37).

The product surface: simulate incidents, read the calm brief + decision feed,
open a case, make human decisions (approve / decline / revert / bulk), ask NOCTRA
questions, and monitor connected security integrations.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import (
    analyst_service,
    case_context,
    connector_service,
    scenario,
    verdict_reasoning,
)
from app.services.case_service import serialize_case

router = APIRouter(prefix="/analyst", tags=["Analyst"])


class ChatRequest(BaseModel):
    message: str


class BulkDecideRequest(BaseModel):
    case_ids: list[int] = Field(..., min_length=1, max_length=50, description="Case IDs to decide")
    decision: str = Field(..., description="approved | declined")


@router.get("/scenarios")
def list_scenarios(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List available simulation scenarios (Phase 36)."""
    return {"data": scenario.list_scenarios()}


@router.post("/simulate", status_code=201)
def simulate_incident(
    scenario_type: str = Query("credential_leak", description="Scenario: credential_leak, phishing_outbreak, data_exfiltration, compromised_api_key, insider_threat, ransomware_activity"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    """Inject a simulated incident scenario and open a pending analyst case."""
    valid = {c["id"] for c in scenario.list_scenarios()}
    if scenario_type not in valid:
        raise HTTPException(status_code=422, detail=f"Unknown scenario_type: {scenario_type}. Valid: {sorted(valid)}")
    case = scenario.run_scenario(
        db,
        scenario_type=scenario_type,
        org_id=current_user.org_id,
        actor=current_user.username,
        created_by_id=current_user.id,
    )
    return serialize_case(case)


@router.get("/brief")
def get_brief(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Calm summary for the analyst home screen."""
    return analyst_service.get_brief(db, org_id=current_user.org_id)


@router.get("/feed")
def get_feed(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Paginated feed of analyst decisions, newest first."""
    items, total = analyst_service.list_feed(db, org_id=current_user.org_id, page=page, limit=limit)
    return {
        "data": [serialize_case(c) for c in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/connectors")
def get_connectors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Status of integrated security tools, derived from real configuration and
    real sync state — a connector reads "connected" only if its last sync
    actually succeeded, and counts come from ingested rows."""
    return connector_service.list_connectors(db, org_id=current_user.org_id)


@router.post("/connectors/{connector_id}/sync")
def sync_connector(
    connector_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    """Run a sync for a security connector.

    Returns `synced` when a poll really fetched events, `recorded` when there
    was nothing to fetch (no config / disabled / push mode), and `error` with
    the reason when a poll was attempted and failed.
    """
    try:
        return connector_service.sync(
            db, connector_id=connector_id, org_id=current_user.org_id, actor=current_user.username
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/bulk-decide")
def bulk_decide(
    payload: BulkDecideRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    """Bulk approve or decline multiple pending cases (Phase 37).

    Honest: only pending cases are acted upon; already-decided or missing
    cases are returned in `failed` with a reason, never silently skipped.
    """
    try:
        return analyst_service.bulk_decide(
            db,
            org_id=current_user.org_id,
            case_ids=payload.case_ids,
            decision=payload.decision,
            actor=current_user.username,
            actor_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/cases/{case_id}")
def get_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full analyst case: analysis, blast radius, proposed action, decision, report.

    Also carries `context` — what this case means for *this* org (reach to
    crown jewels, posture at risk, already-leaked credentials). Absent keys
    mean the module had no real data, never that we guessed.
    """
    case = analyst_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    payload = serialize_case(case)
    context = case_context.build(db, case)
    payload["context"] = context
    payload["context_summary"] = case_context.summarize(context)
    return payload


@router.post("/cases/{case_id}/chat")
def chat_about_case(
    case_id: int,
    body: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Interactive NOCTRA Q&A regarding case context, MITRE mapping, or remediation."""
    case = analyst_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    try:
        return analyst_service.chat_about_case(
            db, case=case, question=body.message.strip(), actor=current_user.username, actor_id=current_user.id
        )
    except analyst_service.ChatRateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": str(exc.retry_after)})


@router.post("/cases/{case_id}/approve")
def approve_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    """Authorize the drafted action: execute via SOAR, record, generate report."""
    case = analyst_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        case = analyst_service.approve_case(db, case, actor=current_user.username, actor_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return serialize_case(case)


@router.post("/cases/{case_id}/decline")
def decline_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    """Dismiss the case with no system change."""
    case = analyst_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        case = analyst_service.decline_case(db, case, actor=current_user.username, actor_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return serialize_case(case)


@router.post("/cases/{case_id}/revert")
def revert_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("alerts:write")),
):
    """Roll back a previously approved action via a recorded compensating entry."""
    case = analyst_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        case = analyst_service.revert_case(db, case, actor=current_user.username, actor_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return serialize_case(case)


@router.get("/cases/{case_id}/report")
def get_report(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the stored markdown report for a case (empty until decided)."""
    case = analyst_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"case_id": case.id, "report": case.report or ""}


@router.get("/cases/{case_id}/timeline")
def get_timeline(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Server-side case record: entries composed from real rows only
    (source alert, case fields, recorded SOAR action, audit trail)."""
    case = analyst_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"case_id": case.id, "entries": analyst_service.case_timeline(db, case)}


@router.get("/cases/{case_id}/reasoning")
def get_reasoning(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Why this case carries the confidence it does.

    Returns each signal that contributed, what it was worth, and every signal
    that could not be consulted along with the reason. Recomputed live rather
    than read from the stored analysis, so the answer reflects the evidence
    available now — enrich an IP or add an asset and the reasoning changes.
    """
    case = analyst_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return verdict_reasoning.explain(db, case)


@router.get("/cases/{case_id}/export")
def export_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export a case as structured JSON for external systems (Phase 36).

    Includes analysis, blast radius, proposed action, timeline and audit refs.
    All fields are real rows — no synthesis.
    """
    case = analyst_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    serialized = serialize_case(case)
    timeline = analyst_service.case_timeline(db, case)
    return {
        "case": serialized,
        "timeline": timeline,
        "exported_at": analyst_service._now().isoformat(),
        "exported_by": current_user.username,
    }

@router.get("/cases/{case_id}/report.pdf")
def export_case_pdf(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export a decided case's markdown report as PDF (Phase 38).

    Honest: refuses with 409 if no report has been generated yet (pending case),
    501 if reportlab is not installed, and preserves the engine note including
    '(templated fallback)' so fallback reasoning is never presented as verified.
    """
    case = analyst_service.get_case(db, case_id, org_id=current_user.org_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if not case.report or not case.report.strip():
        raise HTTPException(
            status_code=409,
            detail="No report yet — a report is written when a decision is recorded (approve/decline/revert).",
        )
    try:
        from app.services.pdf_report import render_markdown_pdf
    except Exception as exc:
        raise HTTPException(status_code=501, detail=f"PDF export is not available: {exc}")
    try:
        pdf_bytes = render_markdown_pdf(case.report, case_id=case.id, title=case.title)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    filename = f"noctra-case-{case.id}-report.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/notifications")
def get_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Derived notification feed: pending decisions + outcomes from the last
    24 h. No unread-state table — clients track the last-seen timestamp."""
    return {"items": analyst_service.list_notifications(db, org_id=current_user.org_id)}
