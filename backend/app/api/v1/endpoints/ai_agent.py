"""Phase 70: AI SOC Agent autonomous analyst v2."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import ai_agent_service

router = APIRouter(prefix="/ai-agent", tags=["AI SOC Agent (Phase 70)"])


class InvestigateRequest(BaseModel):
    case_id: int


class ChatRequest(BaseModel):
    case_id: int
    message: str


class ConfigUpdate(BaseModel):
    auto_approve_low_risk: Optional[bool] = None


@router.post("/investigate", status_code=201)
def investigate(payload: InvestigateRequest, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:read"))):
    try:
        result = ai_agent_service.autonomous_investigate(db, org_id=current_user.org_id, case_id=payload.case_id, actor=current_user.username)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/chat")
def chat(payload: ChatRequest, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:read"))):
    """Dedicated chat with streaming-ready response, tool use parsing (Anthropic tool_use blocks)."""
    try:
        # Use same investigate but with user message as extra context
        result = ai_agent_service.autonomous_investigate(db, org_id=current_user.org_id, case_id=payload.case_id, actor=current_user.username, user_message=payload.message)
        # Format as chat response
        return {
            "response": result.get("final_answer"),
            "tool_calls": result.get("tools_used"),
            "memories": result.get("memories"),
            "llm_used": result.get("llm_used"),
            "task_id": result.get("task_id"),
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as e:
        return {"response": f"Error: {str(e)}", "tool_calls": [], "memories": []}


@router.post("/config")
def update_config(payload: ConfigUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    """Toggle auto-approve LOW for demo (doubt #1)."""
    from app.core.config import settings
    if payload.auto_approve_low_risk is not None:
        settings.AI_AGENT_AUTO_APPROVE_LOW_RISK = payload.auto_approve_low_risk
    return {"auto_approve_low_risk": getattr(settings, "AI_AGENT_AUTO_APPROVE_LOW_RISK", False), "note": "Set via env AI_AGENT_AUTO_APPROVE_LOW_RISK for persistence, this toggle is runtime only"}


@router.get("/memories")
def list_memories(case_id: Optional[int] = None, limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:read"))):
    rows = ai_agent_service.list_agent_memories(db, org_id=current_user.org_id, case_id=case_id, limit=limit)
    return [
        {
            "id": r.id,
            "case_id": r.case_id,
            "role": r.role,
            "content": r.content[:500] if r.content else "",
            "tool_name": r.tool_name,
            "step": r.step,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/status")
def get_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.core.config import settings

    return {
        "ai_agent_enabled": getattr(settings, "AI_AGENT_ENABLED", True),
        "llm_enabled": getattr(settings, "LLM_ENABLED", True),
        "llm_model": getattr(settings, "ANTHROPIC_MODEL", "claude-sonnet-5"),
        "auto_approve_low_risk": getattr(settings, "AI_AGENT_AUTO_APPROVE_LOW_RISK", False),
        "tool_use": getattr(settings, "AI_AGENT_TOOL_USE", True),
        "max_steps": getattr(settings, "AI_AGENT_MAX_STEPS", 5),
        "tools": list(ai_agent_service.TOOL_REGISTRY.keys()),
        "honest_note": "Agent uses LLM when key configured, else deterministic fallback with tool execution. Never auto-executes SOAR unless flag enabled + LOW severity.",
    }
