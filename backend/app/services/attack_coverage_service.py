"""Phase 82: ATT&CK Coverage Dashboard service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, List

from sqlalchemy.orm import Session

from app.models.attack_coverage import AttackCoverage, AttackCoverageReport
from app.models import SecurityAlert
from app.models.hunt import Hunt
from app.models.soar import SoarPlaybook
from app.models.purple_team import PurpleTeamExercise
from app.models.item import DetectionRule


def _now():
    return datetime.now(timezone.utc)


# Simplified ATT&CK matrix (subset)
ATTACK_TECHNIQUES = [
    {"tactic": "initial-access", "technique_id": "T1078", "name": "Valid Accounts"},
    {"tactic": "initial-access", "technique_id": "T1190", "name": "Exploit Public-Facing Application"},
    {"tactic": "execution", "technique_id": "T1059.001", "name": "PowerShell"},
    {"tactic": "execution", "technique_id": "T1059.007", "name": "JavaScript"},
    {"tactic": "persistence", "technique_id": "T1053.005", "name": "Scheduled Task"},
    {"tactic": "persistence", "technique_id": "T1547.001", "name": "Registry Run Keys"},
    {"tactic": "privilege-escalation", "technique_id": "T1068", "name": "Exploitation for Privilege Escalation"},
    {"tactic": "defense-evasion", "technique_id": "T1027", "name": "Obfuscated Files"},
    {"tactic": "credential-access", "technique_id": "T1003.001", "name": "LSASS Memory"},
    {"tactic": "discovery", "technique_id": "T1083", "name": "File and Directory Discovery"},
    {"tactic": "lateral-movement", "technique_id": "T1021.001", "name": "Remote Desktop Protocol"},
    {"tactic": "collection", "technique_id": "T1005", "name": "Data from Local System"},
    {"tactic": "exfiltration", "technique_id": "T1041", "name": "Exfiltration Over C2 Channel"},
    {"tactic": "impact", "technique_id": "T1486", "name": "Data Encrypted for Impact"},
]

def evaluate_coverage(db: Session, org_id: int) -> List[AttackCoverage]:
    """Evaluate ATT&CK coverage based on existing rules, hunts, playbooks, exercises."""
    # Get existing artifacts
    alerts = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id).all()
    alert_techniques = {a.mitre_technique_id for a in alerts if a.mitre_technique_id}

    hunts = db.query(Hunt).filter(Hunt.org_id == org_id).all()
    hunt_text = " ".join([h.query or "" for h in hunts]).lower()

    playbooks = db.query(SoarPlaybook).filter(SoarPlaybook.org_id == org_id).all()
    playbook_text = " ".join([p.name or "" for p in playbooks]).lower()

    exercises = db.query(PurpleTeamExercise).filter(PurpleTeamExercise.org_id == org_id).all()
    exercise_techniques = {e.mitre_technique_id for e in exercises if e.mitre_technique_id}

    rules = db.query(DetectionRule).filter(DetectionRule.org_id == org_id).all() if hasattr(DetectionRule, 'org_id') else []
    # For simplicity, check if rule name contains technique

    results = []
    for tech in ATTACK_TECHNIQUES:
        tid = tech["technique_id"]
        # Check coverage
        has_rule = any(tid.lower() in (r.name or "").lower() for r in rules) or tid in alert_techniques
        has_hunt = tid.lower() in hunt_text or tid.split(".")[0].lower() in hunt_text
        has_playbook = tid.lower() in playbook_text
        has_exercise = tid in exercise_techniques

        detection_count = sum(1 for a in alerts if a.mitre_technique_id == tid)

        # Score: 25 per coverage type
        score = 0
        if has_rule:
            score += 25
        if has_hunt:
            score += 25
        if has_playbook:
            score += 25
        if has_exercise:
            score += 25
        if detection_count > 0:
            score = min(100, score + 10)

        # Gap analysis
        gap_reason = None
        recommendation = None
        if score < 50:
            gap_reason = f"Low coverage for {tid} {tech['name']}"
            recommendation = f"Create detection rule and hunt for {tid}, add purple team exercise"

        # Upsert
        existing = db.query(AttackCoverage).filter(AttackCoverage.org_id == org_id, AttackCoverage.mitre_technique_id == tid).first()
        if existing:
            existing.has_detection_rule = has_rule
            existing.has_hunt = has_hunt
            existing.has_playbook = has_playbook
            existing.has_purple_exercise = has_exercise
            existing.detection_count = detection_count
            existing.coverage_score = score
            existing.gap_reason = gap_reason
            existing.recommendation = recommendation
            existing.last_evaluated_at = _now()
            db.commit()
            results.append(existing)
        else:
            cov = AttackCoverage(
                org_id=org_id,
                mitre_tactic=tech["tactic"],
                mitre_technique_id=tid,
                mitre_technique_name=tech["name"],
                has_detection_rule=has_rule,
                has_hunt=has_hunt,
                has_playbook=has_playbook,
                has_purple_exercise=has_exercise,
                detection_count=detection_count,
                coverage_score=score,
                gap_reason=gap_reason,
                recommendation=recommendation,
            )
            db.add(cov)
            db.commit()
            db.refresh(cov)
            results.append(cov)

    return results

def generate_report(db: Session, org_id: int) -> AttackCoverageReport:
    coverages = evaluate_coverage(db, org_id)
    total = len(ATTACK_TECHNIQUES)
    covered = len([c for c in coverages if c.coverage_score >= 50])
    percent = (covered / total * 100) if total > 0 else 0

    # Tactic breakdown
    tactics = {}
    for tech in ATTACK_TECHNIQUES:
        tactic = tech["tactic"]
        if tactic not in tactics:
            tactics[tactic] = {"total": 0, "covered": 0}
        tactics[tactic]["total"] += 1
        cov = next((c for c in coverages if c.mitre_technique_id == tech["technique_id"]), None)
        if cov and cov.coverage_score >= 50:
            tactics[tactic]["covered"] += 1
    for tactic in tactics:
        t = tactics[tactic]
        t["percent"] = (t["covered"] / t["total"] * 100) if t["total"] > 0 else 0

    gaps = [{"technique_id": c.mitre_technique_id, "name": c.mitre_technique_name, "score": c.coverage_score, "recommendation": c.recommendation} for c in coverages if c.coverage_score < 50]

    report = AttackCoverageReport(org_id=org_id, total_techniques=total, covered_techniques=covered, coverage_percent=percent, tactic_breakdown_json=tactics, gaps_json=gaps)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report

def list_coverage(db: Session, org_id: int) -> List[AttackCoverage]:
    return db.query(AttackCoverage).filter(AttackCoverage.org_id == org_id).order_by(AttackCoverage.coverage_score.asc()).all()

def serialize_coverage(c: AttackCoverage) -> Dict[str, Any]:
    return {"id": c.id, "tactic": c.mitre_tactic, "technique_id": c.mitre_technique_id, "technique_name": c.mitre_technique_name, "has_rule": c.has_detection_rule, "has_hunt": c.has_hunt, "has_playbook": c.has_playbook, "has_exercise": c.has_purple_exercise, "detection_count": c.detection_count, "coverage_score": c.coverage_score, "gap_reason": c.gap_reason, "recommendation": c.recommendation, "last_evaluated_at": c.last_evaluated_at.isoformat() if c.last_evaluated_at else None}

def serialize_report(r: AttackCoverageReport) -> Dict[str, Any]:
    return {"id": r.id, "total_techniques": r.total_techniques, "covered_techniques": r.covered_techniques, "coverage_percent": r.coverage_percent, "tactic_breakdown": r.tactic_breakdown_json, "gaps": r.gaps_json, "created_at": r.created_at.isoformat() if r.created_at else None}
