"""Phase 74: HA Redis Event Bus + multi-region."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.ha_eventbus import EventBusMessage, HANode
from app.core.config import settings


def _now():
    return datetime.now(timezone.utc)


class EventBus:
    """HA Event Bus with Redis fallback to DB persistence."""

    def __init__(self):
        self.redis_client = None
        try:
            import redis
            redis_url = getattr(settings, "REDIS_URL", None)
            if redis_url:
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
        except Exception:
            self.redis_client = None

    def publish(self, db: Session, channel: str, event_type: str, payload: Dict[str, Any], org_id: int = None, region: str = "us-east-1") -> EventBusMessage:
        """Publish event to Redis (if available) and persist to DB."""
        msg = EventBusMessage(org_id=org_id, channel=channel, event_type=event_type, payload_json=payload, region=region, is_persisted=True)
        db.add(msg)
        db.commit()
        db.refresh(msg)

        if self.redis_client:
            try:
                self.redis_client.publish(channel, json.dumps({"id": msg.id, "event_type": event_type, "payload": payload, "org_id": org_id, "region": region}))
            except Exception:
                pass
        return msg

    def list_messages(self, db: Session, org_id: int = None, channel: str = None, limit: int = 50) -> List[EventBusMessage]:
        q = db.query(EventBusMessage)
        if org_id:
            q = q.filter(EventBusMessage.org_id == org_id)
        if channel:
            q = q.filter(EventBusMessage.channel == channel)
        return q.order_by(EventBusMessage.created_at.desc()).limit(limit).all()

    def heartbeat(self, db: Session, node_id: str, region: str = "us-east-1", role: str = "primary") -> HANode:
        node = db.query(HANode).filter(HANode.node_id == node_id).first()
        if not node:
            node = HANode(node_id=node_id, region=region, role=role, status="active", last_heartbeat_at=_now())
            db.add(node)
        else:
            node.last_heartbeat_at = _now()
            node.status = "active"
        db.commit()
        db.refresh(node)
        return node

    def list_nodes(self, db: Session) -> List[HANode]:
        return db.query(HANode).order_by(HANode.last_heartbeat_at.desc()).all()


_event_bus = EventBus()


def get_event_bus() -> EventBus:
    return _event_bus


def serialize_message(m: EventBusMessage) -> Dict[str, Any]:
    return {"id": m.id, "channel": m.channel, "event_type": m.event_type, "payload": m.payload_json, "region": m.region, "created_at": m.created_at.isoformat() if m.created_at else None}


def serialize_node(n: HANode) -> Dict[str, Any]:
    return {"id": n.id, "node_id": n.node_id, "region": n.region, "role": n.role, "status": n.status, "last_heartbeat_at": n.last_heartbeat_at.isoformat() if n.last_heartbeat_at else None}
