"""Phase 61: ZTNA + microsegmentation service."""

from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.ztna import NetworkSegment, ZTNAPolicy, ZTNADecisionLog
from app.core.config import settings


def _now():
    return datetime.now(timezone.utc)


def list_segments(db: Session, org_id: int) -> List[NetworkSegment]:
    return db.query(NetworkSegment).filter(NetworkSegment.org_id == org_id).order_by(NetworkSegment.name).all()


def create_segment(db: Session, org_id: int, name: str, cidr: str, zone: str = "internal", description: str = None) -> NetworkSegment:
    # Validate CIDR
    try:
        ipaddress.ip_network(cidr, strict=False)
    except ValueError as exc:
        raise ValueError(f"Invalid CIDR {cidr}: {exc}")
    seg = NetworkSegment(org_id=org_id, name=name, cidr=cidr, zone=zone, description=description)
    db.add(seg)
    db.commit()
    db.refresh(seg)
    return seg


def list_policies(db: Session, org_id: int) -> List[ZTNAPolicy]:
    return db.query(ZTNAPolicy).filter(ZTNAPolicy.org_id == org_id).order_by(ZTNAPolicy.priority).all()


def create_policy(
    db: Session,
    org_id: int,
    name: str,
    policy_json: Dict[str, Any],
    src_segment_id: int = None,
    dst_segment_id: int = None,
    action: str = "deny",
    priority: int = 100,
    created_by_user_id: int = None,
) -> ZTNAPolicy:
    if action not in ("allow", "deny", "isolate", "require_mfa"):
        raise ValueError(f"Invalid action {action}")
    policy = ZTNAPolicy(
        org_id=org_id,
        name=name,
        policy_json=policy_json,
        src_segment_id=src_segment_id,
        dst_segment_id=dst_segment_id,
        action=action,
        priority=priority,
        created_by_user_id=created_by_user_id,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


def _ip_in_segment(ip_str: str, cidr: str) -> bool:
    try:
        net = ipaddress.ip_network(cidr, strict=False)
        ip = ipaddress.ip_address(ip_str)
        return ip in net
    except ValueError:
        return False


def evaluate_access(
    db: Session,
    org_id: int,
    src_ip: str,
    dst_ip: str,
    user_id: int = None,
    user_role: str = None,
) -> Dict[str, Any]:
    """Evaluate ZTNA policies for src->dst.

    Honest: returns matched policy + decision, logs to ZTNADecisionLog.
    If no policy matches, uses ZTNA_DEFAULT_ACTION (deny).
    """
    segments = list_segments(db, org_id)
    policies = list_policies(db, org_id)
    policies = [p for p in policies if p.is_active]
    policies.sort(key=lambda p: p.priority)

    src_seg = None
    dst_seg = None
    for seg in segments:
        if _ip_in_segment(src_ip, seg.cidr):
            src_seg = seg
        if _ip_in_segment(dst_ip, seg.cidr):
            dst_seg = seg

    matched_policy = None
    decision_action = getattr(settings, "ZTNA_DEFAULT_ACTION", "deny")
    reason = f"No policy matched, default {decision_action}"

    for policy in policies:
        # Check segment match if specified
        if policy.src_segment_id and src_seg and policy.src_segment_id != src_seg.id:
            continue
        if policy.dst_segment_id and dst_seg and policy.dst_segment_id != dst_seg.id:
            continue
        if policy.src_segment_id and not src_seg:
            continue
        if policy.dst_segment_id and not dst_seg:
            continue

        # Check conditions in policy_json
        conditions = policy.policy_json.get("conditions", {}) if policy.policy_json else {}
        if conditions:
            if "user_role" in conditions and user_role and conditions["user_role"] != user_role:
                continue
            # mfa_required check would need user context, simplified
        matched_policy = policy
        decision_action = policy.action
        reason = f"Matched policy {policy.name} (priority {policy.priority})"
        break

    # Log decision
    try:
        log = ZTNADecisionLog(
            org_id=org_id,
            policy_id=matched_policy.id if matched_policy else None,
            src_ip=src_ip,
            dst_ip=dst_ip,
            user_id=user_id,
            action=decision_action,
            reason=reason,
        )
        db.add(log)
        db.commit()
    except Exception:
        db.rollback()

    return {
        "src_ip": src_ip,
        "dst_ip": dst_ip,
        "src_segment": {"id": src_seg.id, "name": src_seg.name, "cidr": src_seg.cidr} if src_seg else None,
        "dst_segment": {"id": dst_seg.id, "name": dst_seg.name, "cidr": dst_seg.cidr} if dst_seg else None,
        "action": decision_action,
        "matched_policy": {"id": matched_policy.id, "name": matched_policy.name} if matched_policy else None,
        "reason": reason,
        "evaluated_at": _now().isoformat(),
    }


def get_microseg_graph(db: Session, org_id: int) -> Dict[str, Any]:
    """Build graph of segments + policies for visualization."""
    segments = list_segments(db, org_id)
    policies = list_policies(db, org_id)

    nodes = [{"id": s.id, "name": s.name, "cidr": s.cidr, "zone": s.zone, "risk_level": s.risk_level} for s in segments]
    edges = []
    for p in policies:
        if p.src_segment_id and p.dst_segment_id:
            edges.append(
                {
                    "id": p.id,
                    "src": p.src_segment_id,
                    "dst": p.dst_segment_id,
                    "action": p.action,
                    "name": p.name,
                    "priority": p.priority,
                }
            )
    return {"nodes": nodes, "edges": edges, "default_action": getattr(settings, "ZTNA_DEFAULT_ACTION", "deny")}


def serialize_segment(s: NetworkSegment) -> Dict[str, Any]:
    return {"id": s.id, "org_id": s.org_id, "name": s.name, "cidr": s.cidr, "zone": s.zone, "description": s.description, "risk_level": s.risk_level, "created_at": s.created_at.isoformat() if s.created_at else None}


def serialize_policy(p: ZTNAPolicy) -> Dict[str, Any]:
    return {
        "id": p.id,
        "org_id": p.org_id,
        "name": p.name,
        "policy_json": p.policy_json,
        "src_segment_id": p.src_segment_id,
        "dst_segment_id": p.dst_segment_id,
        "action": p.action,
        "priority": p.priority,
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
