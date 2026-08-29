"""Phase 74: HA Event Bus endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models.user import User
from app.services.ha_eventbus_service import get_event_bus, serialize_message, serialize_node

router = APIRouter(prefix="/ha", tags=["HA EventBus (Phase 74)"])

class PublishIn(BaseModel):
    channel: str
    event_type: str
    payload: Dict[str, Any] = {}
    region: str = "us-east-1"

class HeartbeatIn(BaseModel):
    node_id: str
    region: str = "us-east-1"
    role: str = "primary"

@router.post("/publish")
def publish(payload: PublishIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        bus = get_event_bus()
        msg = bus.publish(db, channel=payload.channel, event_type=payload.event_type, payload=payload.payload, org_id=current_user.org_id, region=payload.region)
        return serialize_message(msg)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/messages")
def list_messages(channel: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        bus = get_event_bus()
        msgs = bus.list_messages(db, org_id=current_user.org_id, channel=channel, limit=limit)
        return [serialize_message(m) for m in msgs]
    except Exception:
        return []

@router.post("/heartbeat")
def heartbeat(payload: HeartbeatIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        bus = get_event_bus()
        node = bus.heartbeat(db, node_id=payload.node_id, region=payload.region, role=payload.role)
        return serialize_node(node)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/nodes")
def list_nodes(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        bus = get_event_bus()
        nodes = bus.list_nodes(db)
        return [serialize_node(n) for n in nodes]
    except Exception:
        return []

@router.get("/status")
def ha_status(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    bus = get_event_bus()
    redis_ok = bus.redis_client is not None
    try:
        if redis_ok:
            bus.redis_client.ping()
    except Exception:
        redis_ok = False
    return {"redis_connected": redis_ok, "fallback": "DB persistence", "regions": ["us-east-1", "eu-west-1", "ap-south-1"], "note": "HA via Redis pub/sub + DB persistence, multi-region ready"}
