"""Phase 77: Risk-based alerting."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.risk_based import Asset, RiskBasedRule, RiskScoreLog
from app.models import SecurityAlert


def _now():
    return datetime.now(timezone.utc)


def create_asset(db: Session, org_id: int, name: str, asset_type: str = "host", ip_address: str = None, hostname: str = None, criticality: int = 3, business_unit: str = None, owner: str = None, tags: List[str] = None) -> Asset:
    asset = Asset(org_id=org_id, name=name, asset_type=asset_type, ip_address=ip_address, hostname=hostname, criticality=criticality, business_unit=business_unit, owner=owner, tags=tags or [])
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def list_assets(db: Session, org_id: int, criticality: int = None) -> List[Asset]:
    q = db.query(Asset).filter(Asset.org_id == org_id)
    if criticality:
        q = q.filter(Asset.criticality >= criticality)
    return q.order_by(Asset.criticality.desc()).limit(100).all()


def seed_assets(db: Session, org_id: int) -> List[Asset]:
    existing = db.query(Asset).filter(Asset.org_id == org_id).count()
    if existing > 0:
        return list_assets(db, org_id)
    defaults = [
        {"name": "Domain Controller", "asset_type": "host", "ip_address": "10.0.0.1", "hostname": "dc01", "criticality": 5, "business_unit": "IT"},
        {"name": "Prod DB", "asset_type": "host", "ip_address": "10.0.0.10", "hostname": "prod-db", "criticality": 5, "business_unit": "Engineering"},
        {"name": "CEO Laptop", "asset_type": "host", "ip_address": "10.0.0.50", "hostname": "ceo-laptop", "criticality": 4, "business_unit": "Executive"},
        {"name": "Web Server", "asset_type": "host", "ip_address": "10.0.1.10", "hostname": "web01", "criticality": 3, "business_unit": "Engineering"},
    ]
    created = []
    for d in defaults:
        a = create_asset(db, org_id=org_id, **d)
        created.append(a)
    return created


def create_risk_rule(db: Session, org_id: int, name: str, conditions: Dict[str, Any], action: str = "escalate", risk_multiplier: float = 1.5) -> RiskBasedRule:
    rule = RiskBasedRule(org_id=org_id, name=name, conditions_json=conditions, action=action, risk_multiplier=risk_multiplier)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def list_risk_rules(db: Session, org_id: int) -> List[RiskBasedRule]:
    return db.query(RiskBasedRule).filter(RiskBasedRule.org_id == org_id, RiskBasedRule.is_active == True).all()


def calculate_risk_score(db: Session, org_id: int, alert_id: int) -> RiskScoreLog:
    """Calculate risk score based on asset criticality + alert severity."""
    alert = db.query(SecurityAlert).filter(SecurityAlert.id == alert_id, SecurityAlert.org_id == org_id).first()
    if not alert:
        raise ValueError("Alert not found")

    base_score_map = {"LOW": 2, "MEDIUM": 5, "HIGH": 8, "CRITICAL": 10}
    base_score = base_score_map.get((alert.severity or "MEDIUM").upper(), 5)

    # Find asset by IP
    asset = None
    if alert.source_ip:
        asset = db.query(Asset).filter(Asset.org_id == org_id, Asset.ip_address == alert.source_ip).first()
    if not asset:
        # Use highest criticality asset as fallback for demo
        asset = db.query(Asset).filter(Asset.org_id == org_id).order_by(Asset.criticality.desc()).first()

    adjusted = base_score
    reason = f"Base score {base_score} from severity {alert.severity}"
    if asset:
        # Multiply by criticality factor: criticality 5 = 2x, 1 = 0.5x
        factor = 0.5 + (asset.criticality * 0.3)  # 1->0.8, 5->2.0
        adjusted = base_score * factor
        reason += f", asset {asset.name} criticality {asset.criticality} factor {factor:.1f}"

        # Apply risk rules
        rules = list_risk_rules(db, org_id)
        for rule in rules:
            cond = rule.conditions_json or {}
            min_sev = cond.get("min_severity")
            min_crit = cond.get("min_criticality")
            sev_ok = True
            if min_sev:
                sev_order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
                sev_ok = sev_order.get(alert.severity.upper(), 2) >= sev_order.get(min_sev.upper(), 2)
            crit_ok = True
            if min_crit and asset:
                crit_ok = asset.criticality >= min_crit
            if sev_ok and crit_ok:
                adjusted *= rule.risk_multiplier
                reason += f", rule {rule.name} x{rule.risk_multiplier}"

    log = RiskScoreLog(org_id=org_id, alert_id=alert_id, asset_id=asset.id if asset else None, base_score=base_score, adjusted_score=min(10, adjusted), reason=reason)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def serialize_asset(a: Asset) -> Dict[str, Any]:
    return {"id": a.id, "name": a.name, "asset_type": a.asset_type, "ip_address": a.ip_address, "hostname": a.hostname, "criticality": a.criticality, "business_unit": a.business_unit, "owner": a.owner, "tags": a.tags, "created_at": a.created_at.isoformat() if a.created_at else None}


def serialize_rule(r: RiskBasedRule) -> Dict[str, Any]:
    return {"id": r.id, "name": r.name, "conditions": r.conditions_json, "action": r.action, "risk_multiplier": r.risk_multiplier, "is_active": r.is_active}


def serialize_score_log(l: RiskScoreLog) -> Dict[str, Any]:
    return {"id": l.id, "alert_id": l.alert_id, "asset_id": l.asset_id, "base_score": l.base_score, "adjusted_score": l.adjusted_score, "reason": l.reason, "created_at": l.created_at.isoformat() if l.created_at else None}
