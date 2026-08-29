"""Phase 97: DRP service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.drp import DRP_Monitor, DRP_Finding, DRP_Takedown

def _now():
    return datetime.now(timezone.utc)

def create_monitor(db: Session, org_id: int, name: str, monitor_type: str, keyword: str) -> DRP_Monitor:
    m = DRP_Monitor(org_id=org_id, name=name, monitor_type=monitor_type, keyword=keyword, is_active=True)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m

def list_monitors(db: Session, org_id: int) -> List[DRP_Monitor]:
    return db.query(DRP_Monitor).filter(DRP_Monitor.org_id == org_id, DRP_Monitor.is_active == True).all()

def seed_monitors(db: Session, org_id: int) -> List[DRP_Monitor]:
    existing = db.query(DRP_Monitor).filter(DRP_Monitor.org_id == org_id).count()
    if existing > 0:
        return list_monitors(db, org_id)
    defaults = [
        {"name": "Company Domain", "monitor_type": "domain", "keyword": "example.com"},
        {"name": "Brand Monitoring", "monitor_type": "brand", "keyword": "NOCTRA"},
        {"name": "CEO Email", "monitor_type": "email", "keyword": "ceo@example.com"},
        {"name": "Dark Web - Credentials", "monitor_type": "dark_web", "keyword": "example.com credentials"},
    ]
    created = []
    for d in defaults:
        m = create_monitor(db, org_id, d["name"], d["monitor_type"], d["keyword"])
        created.append(m)
    return created

def scan_drp(db: Session, org_id: int) -> List[DRP_Finding]:
    """Mock dark web scan."""
    monitors = list_monitors(db, org_id)
    findings = []
    for mon in monitors[:2]:
        # Mock finding
        if mon.monitor_type == "domain":
            finding = DRP_Finding(org_id=org_id, monitor_id=mon.id, finding_type="brand_impersonation", severity="HIGH", title=f"Fake domain {mon.keyword.replace('example', 'examp1e')}.com detected", description=f"Impersonating domain {mon.keyword} found on dark web", evidence_json={"url": f"http://examp1e.com", "source": "dark_web_forum"}, source="dark_web", status="open")
            db.add(finding)
            findings.append(finding)
        elif mon.monitor_type == "email":
            finding = DRP_Finding(org_id=org_id, monitor_id=mon.id, finding_type="leaked_credential", severity="CRITICAL", title=f"Leaked credential for {mon.keyword}", description=f"Credential for {mon.keyword} found in paste site", evidence_json={"paste_url": "https://pastebin.com/abc", "password_hash": "5f4dcc3b5aa765d61d8327deb882cf99"}, source="paste_site", status="open")
            db.add(finding)
            findings.append(finding)
    db.commit()
    for f in findings:
        db.refresh(f)
    return findings

def list_findings(db: Session, org_id: int) -> List[DRP_Finding]:
    return db.query(DRP_Finding).filter(DRP_Finding.org_id == org_id, DRP_Finding.status == "open").order_by(DRP_Finding.created_at.desc()).limit(50).all()

def serialize_monitor(m: DRP_Monitor) -> Dict[str, Any]:
    return {"id": m.id, "name": m.name, "monitor_type": m.monitor_type, "keyword": m.keyword, "is_active": m.is_active}

def serialize_finding(f: DRP_Finding) -> Dict[str, Any]:
    return {"id": f.id, "monitor_id": f.monitor_id, "finding_type": f.finding_type, "severity": f.severity, "title": f.title, "description": f.description, "evidence": f.evidence_json, "source": f.source, "status": f.status}
