"""Phase 56: ATT&CK Navigator + threat actor attribution."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.attack import ThreatActor, AttackHeatmap
from app.models import SecurityAlert

# Simplified ATT&CK matrix (tactic -> techniques)
ATTACK_MATRIX = {
    "Initial Access": ["T1078", "T1190", "T1566"],
    "Execution": ["T1059", "T1204"],
    "Persistence": ["T1098", "T1136"],
    "Privilege Escalation": ["T1068", "T1078"],
    "Defense Evasion": ["T1027", "T1070"],
    "Credential Access": ["T1003", "T1110"],
    "Discovery": ["T1083", "T1018"],
    "Lateral Movement": ["T1021", "T1091"],
    "Collection": ["T1005", "T1114"],
    "Exfiltration": ["T1048", "T1041"],
    "Impact": ["T1486", "T1490"],
}


def list_threat_actors(db: Session, org_id: int = None) -> List[ThreatActor]:
    q = db.query(ThreatActor).order_by(ThreatActor.name)
    if org_id is not None:
        q = q.filter((ThreatActor.org_id == org_id) | (ThreatActor.org_id.is_(None)))
    return q.all()


def create_threat_actor(
    db: Session,
    name: str,
    aliases: List[str] = None,
    description: str = None,
    country: str = None,
    techniques: List[str] = None,
    org_id: int = None,
) -> ThreatActor:
    actor = ThreatActor(
        name=name,
        aliases=aliases or [],
        description=description,
        country=country,
        techniques=techniques or [],
        org_id=org_id,
    )
    db.add(actor)
    db.commit()
    db.refresh(actor)
    return actor


def get_attack_heatmap(db: Session, org_id: int) -> Dict[str, Any]:
    """Build ATT&CK heatmap from alerts and heatmap table."""
    # Update heatmap from recent alerts
    alerts = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id).all()
    technique_counts: Dict[str, int] = {}
    for alert in alerts:
        tech = getattr(alert, "mitre_technique_id", None)
        if tech:
            technique_counts[tech] = technique_counts.get(tech, 0) + 1

    # Persist counts
    for tech_id, count in technique_counts.items():
        existing = db.query(AttackHeatmap).filter(AttackHeatmap.org_id == org_id, AttackHeatmap.technique_id == tech_id).first()
        if existing:
            existing.count = count
            existing.last_seen_at = datetime.now(timezone.utc)
        else:
            hm = AttackHeatmap(
                org_id=org_id,
                technique_id=tech_id,
                count=count,
                last_seen_at=datetime.now(timezone.utc),
            )
            db.add(hm)
    db.commit()

    # Build matrix with scores
    heatmap = db.query(AttackHeatmap).filter(AttackHeatmap.org_id == org_id).all()
    heatmap_dict = {h.technique_id: h.count for h in heatmap}

    matrix = []
    for tactic, techniques in ATTACK_MATRIX.items():
        row = {"tactic": tactic, "techniques": []}
        for tech in techniques:
            row["techniques"].append(
                {
                    "technique_id": tech,
                    "count": heatmap_dict.get(tech, 0),
                    "score": min(heatmap_dict.get(tech, 0) * 10, 100),
                }
            )
        matrix.append(row)

    return {
        "org_id": org_id,
        "total_techniques_observed": len(heatmap_dict),
        "matrix": matrix,
        "heatmap": [{"technique_id": h.technique_id, "count": h.count, "tactic": h.tactic} for h in heatmap],
    }


def attribute_actor(db: Session, org_id: int, technique_ids: List[str]) -> List[Dict[str, Any]]:
    """Attribute threat actors based on observed techniques."""
    actors = list_threat_actors(db, org_id=org_id)
    results = []
    for actor in actors:
        actor_techs = set(actor.techniques or [])
        observed = set(technique_ids)
        overlap = actor_techs & observed
        if overlap:
            score = len(overlap) / len(actor_techs) if actor_techs else 0
            results.append(
                {
                    "actor": actor.name,
                    "aliases": actor.aliases,
                    "country": actor.country,
                    "matched_techniques": list(overlap),
                    "score": score,
                    "description": actor.description,
                }
            )
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def serialize_actor(a: ThreatActor) -> Dict[str, Any]:
    return {
        "id": a.id,
        "name": a.name,
        "aliases": a.aliases,
        "description": a.description,
        "country": a.country,
        "techniques": a.techniques,
        "is_active": a.is_active,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
