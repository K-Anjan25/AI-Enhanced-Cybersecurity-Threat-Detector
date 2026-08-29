"""Phase 99: Posture Score v2 service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.posture_score import PostureScore, PostureFinding, PostureRecommendation
from app.models import SecurityAlert, Case
from app.models.vuln import Vulnerability
from app.models.cspm import CSPMViolation

def _now():
    return datetime.now(timezone.utc)

def calculate_posture(db: Session, org_id: int) -> PostureScore:
    # Detect score: based on detection rules, hunts, coverage
    from app.models.hunt import Hunt
    from app.models.attack_coverage import AttackCoverage

    total_alerts = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id).count()
    open_cases = db.query(Case).filter(Case.org_id == org_id, Case.status != "closed").count()
    vuln_critical = db.query(Vulnerability).filter(Vulnerability.org_id == org_id, Vulnerability.severity == "CRITICAL", Vulnerability.status == "open").count()
    cspm_critical = db.query(CSPMViolation).filter(CSPMViolation.org_id == org_id, CSPMViolation.severity == "CRITICAL", CSPMViolation.status == "open").count()
    hunts = db.query(Hunt).filter(Hunt.org_id == org_id).count()
    coverage = db.query(AttackCoverage).filter(AttackCoverage.org_id == org_id).all()
    avg_coverage = sum(c.coverage_score for c in coverage) / max(1, len(coverage)) if coverage else 50

    # Calculate breakdown
    detect_score = min(100, avg_coverage + hunts*2)
    protect_score = max(0, 100 - (vuln_critical*10 + cspm_critical*15))
    respond_score = max(0, 100 - open_cases*2)
    recover_score = 80  # mock
    governance_score = 75  # mock

    overall = (detect_score + protect_score + respond_score + recover_score + governance_score) / 5

    # Previous
    prev = db.query(PostureScore).filter(PostureScore.org_id == org_id).order_by(PostureScore.created_at.desc()).first()
    previous_score = prev.overall_score if prev else None
    trend = "stable"
    if previous_score:
        if overall > previous_score + 5:
            trend = "improving"
        elif overall < previous_score - 5:
            trend = "degrading"

    score = PostureScore(org_id=org_id, overall_score=overall, breakdown_json={"detect": detect_score, "protect": protect_score, "respond": respond_score, "recover": recover_score, "governance": governance_score}, business_context_json={"crown_jewels_protected": protect_score, "compliance": governance_score, "total_alerts": total_alerts}, previous_score=previous_score, trend=trend)
    db.add(score)
    db.commit()
    db.refresh(score)

    # Create findings for low scores
    if protect_score < 70:
        finding = PostureFinding(org_id=org_id, category="protect", title=f"Protection score low: {protect_score:.0f}", severity="HIGH" if protect_score < 50 else "MEDIUM", description=f"Critical vulns {vuln_critical}, CSPM critical {cspm_critical}", impact="high", remediation="Patch critical vulns, fix CSPM violations", crown_jewel_affected=True)
        db.add(finding)
        db.commit()

    # Recommendations
    if protect_score < 70:
        rec = PostureRecommendation(org_id=org_id, title="Fix critical CSPM violations", description="Auto-remediate CIS violations via Compliance Autopilot", priority="high", effort="low", impact_score=15, estimated_cost=0, estimated_benefit=50000)
        db.add(rec)
        db.commit()

    return score

def list_scores(db: Session, org_id: int) -> List[PostureScore]:
    return db.query(PostureScore).filter(PostureScore.org_id == org_id).order_by(PostureScore.created_at.desc()).limit(20).all()

def list_findings(db: Session, org_id: int) -> List[PostureFinding]:
    return db.query(PostureFinding).filter(PostureFinding.org_id == org_id, PostureFinding.status == "open").order_by(PostureFinding.severity.desc()).limit(50).all()

def list_recommendations(db: Session, org_id: int) -> List[PostureRecommendation]:
    return db.query(PostureRecommendation).filter(PostureRecommendation.org_id == org_id).order_by(PostureRecommendation.impact_score.desc()).limit(20).all()

def serialize_score(s: PostureScore) -> Dict[str, Any]:
    return {"id": s.id, "overall_score": s.overall_score, "breakdown": s.breakdown_json, "business_context": s.business_context_json, "previous_score": s.previous_score, "trend": s.trend, "created_at": s.created_at.isoformat() if s.created_at else None}

def serialize_finding(f: PostureFinding) -> Dict[str, Any]:
    return {"id": f.id, "category": f.category, "title": f.title, "severity": f.severity, "description": f.description, "impact": f.impact, "remediation": f.remediation, "crown_jewel_affected": f.crown_jewel_affected, "status": f.status}

def serialize_recommendation(r: PostureRecommendation) -> Dict[str, Any]:
    return {"id": r.id, "title": r.title, "description": r.description, "priority": r.priority, "effort": r.effort, "impact_score": r.impact_score, "estimated_cost": r.estimated_cost, "estimated_benefit": r.estimated_benefit}
