"""Phase 105: Quantum Comms endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import quantum_comms_service

router = APIRouter(prefix="/quantum-comms", tags=["Quantum Comms P105"])

class ChannelIn(BaseModel):
    name: str
    channel_type: str = "hybrid"

class MsgIn(BaseModel):
    channel_id: int
    sender: str = "soc-primary"
    recipient: str = "soc-dr"
    payload: str = "TOP SECRET INCIDENT DATA"

@router.get("/channels")
def list_channels(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        chans = quantum_comms_service.list_channels(db, current_user.org_id)
        return [quantum_comms_service.serialize_channel(c) for c in chans]
    except Exception:
        return []

@router.post("/channels")
def create_channel(payload: ChannelIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        ch = quantum_comms_service.create_channel(db, current_user.org_id, payload.name, payload.channel_type)
        return quantum_comms_service.serialize_channel(ch)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/send")
def send_msg(payload: MsgIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        msg = quantum_comms_service.send_secure_message(db, current_user.org_id, payload.channel_id, payload.sender, payload.recipient, payload.payload)
        return quantum_comms_service.serialize_message(msg)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))

@router.get("/messages")
def list_msgs(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        msgs = quantum_comms_service.list_messages(db, current_user.org_id)
        return [quantum_comms_service.serialize_message(m) for m in msgs]
    except Exception:
        return []
