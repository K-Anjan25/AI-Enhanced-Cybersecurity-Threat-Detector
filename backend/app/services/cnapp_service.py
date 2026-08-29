"""Phase 98: CNAPP service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.cnapp import CNAPP_Cluster, CNAPP_Workload, CNAPP_Policy, CNAPP_Finding

def _now():
    return datetime.now(timezone.utc)

def create_cluster(db: Session, org_id: int, name: str, cluster_type: str = "kubernetes", provider: str = "aws", region: str = "us-east-1") -> CNAPP_Cluster:
    c = CNAPP_Cluster(org_id=org_id, name=name, cluster_type=cluster_type, provider=provider, region=region, node_count=3, is_active=True)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c

def list_clusters(db: Session, org_id: int) -> List[CNAPP_Cluster]:
    return db.query(CNAPP_Cluster).filter(CNAPP_Cluster.org_id == org_id, CNAPP_Cluster.is_active == True).all()

def seed_clusters(db: Session, org_id: int) -> List[CNAPP_Cluster]:
    existing = db.query(CNAPP_Cluster).filter(CNAPP_Cluster.org_id == org_id).count()
    if existing > 0:
        return list_clusters(db, org_id)
    c1 = create_cluster(db, org_id, "prod-k8s", "kubernetes", "aws", "us-east-1")
    c2 = create_cluster(db, org_id, "dev-k8s", "kubernetes", "gcp", "us-central1")
    # Seed workloads
    w1 = CNAPP_Workload(org_id=org_id, cluster_id=c1.id, name="api-deployment", namespace="prod", workload_type="deployment", image="noctra/api:1.2.3", is_privileged=False, has_host_network=False, vulnerabilities=[{"cve": "CVE-2023-1234", "severity": "HIGH"}], risk_score=7.5)
    w2 = CNAPP_Workload(org_id=org_id, cluster_id=c1.id, name="nginx", namespace="prod", workload_type="pod", image="nginx:latest", is_privileged=True, has_host_network=True, vulnerabilities=[], compliance_violations=["privileged container"], risk_score=9.0)
    db.add_all([w1, w2])
    db.commit()
    # Findings
    f1 = CNAPP_Finding(org_id=org_id, cluster_id=c1.id, workload_id=w2.id, title="Privileged container nginx", finding_type="misconfiguration", severity="HIGH", description="Container running privileged", remediation="Remove privileged flag")
    db.add(f1)
    db.commit()
    return [c1, c2]

def list_workloads(db: Session, org_id: int, cluster_id: int = None) -> List[CNAPP_Workload]:
    q = db.query(CNAPP_Workload).filter(CNAPP_Workload.org_id == org_id)
    if cluster_id:
        q = q.filter(CNAPP_Workload.cluster_id == cluster_id)
    return q.limit(100).all()

def list_findings(db: Session, org_id: int) -> List[CNAPP_Finding]:
    return db.query(CNAPP_Finding).filter(CNAPP_Finding.org_id == org_id, CNAPP_Finding.status == "open").order_by(CNAPP_Finding.severity.desc()).limit(50).all()

def get_summary(db: Session, org_id: int) -> Dict[str, Any]:
    total_clusters = db.query(CNAPP_Cluster).filter(CNAPP_Cluster.org_id == org_id).count()
    total_workloads = db.query(CNAPP_Workload).filter(CNAPP_Workload.org_id == org_id).count()
    privileged = db.query(CNAPP_Workload).filter(CNAPP_Workload.org_id == org_id, CNAPP_Workload.is_privileged == True).count()
    high_risk = db.query(CNAPP_Workload).filter(CNAPP_Workload.org_id == org_id, CNAPP_Workload.risk_score >= 7).count()
    findings = db.query(CNAPP_Finding).filter(CNAPP_Finding.org_id == org_id, CNAPP_Finding.status == "open").count()
    return {"total_clusters": total_clusters, "total_workloads": total_workloads, "privileged_workloads": privileged, "high_risk_workloads": high_risk, "open_findings": findings, "risk_score": min(100, privileged*10 + high_risk*5)}

def serialize_cluster(c: CNAPP_Cluster) -> Dict[str, Any]:
    return {"id": c.id, "name": c.name, "cluster_type": c.cluster_type, "provider": c.provider, "region": c.region, "node_count": c.node_count, "is_active": c.is_active}

def serialize_workload(w: CNAPP_Workload) -> Dict[str, Any]:
    return {"id": w.id, "cluster_id": w.cluster_id, "name": w.name, "namespace": w.namespace, "workload_type": w.workload_type, "image": w.image, "is_privileged": w.is_privileged, "has_host_network": w.has_host_network, "vulnerabilities": w.vulnerabilities, "risk_score": w.risk_score}
