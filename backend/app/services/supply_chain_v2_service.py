"""Phase 107: Supply Chain v2 service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.supply_chain_v2 import SupplyChainGraph, VendorRisk, Attestation

def _now():
    return datetime.now(timezone.utc)

def create_graph(db: Session, org_id: int, name: str, root: str = "noctra-api") -> SupplyChainGraph:
    graph = SupplyChainGraph(org_id=org_id, name=name, root_component=root, graph_json={"nodes": [{"id": root, "type": "app"}, {"id": "log4j:2.14", "type": "library", "risk": "critical"}], "edges": [{"from": root, "to": "log4j:2.14"}]}, depth=4, total_dependencies=150, risky_dependencies=3)
    db.add(graph)
    db.commit()
    db.refresh(graph)
    return graph

def list_graphs(db: Session, org_id: int) -> List[SupplyChainGraph]:
    return db.query(SupplyChainGraph).filter(SupplyChainGraph.org_id == org_id).order_by(SupplyChainGraph.created_at.desc()).all()

def assess_vendor(db: Session, org_id: int, vendor_name: str) -> VendorRisk:
    vr = VendorRisk(org_id=org_id, vendor_name=vendor_name, risk_score=65.0, risk_factors=["no SLSA attestation","recent CVE"], sbom_compliance=False, attestation_status="failed")
    db.add(vr)
    db.commit()
    db.refresh(vr)
    return vr

def list_vendors(db: Session, org_id: int) -> List[VendorRisk]:
    return db.query(VendorRisk).filter(VendorRisk.org_id == org_id).order_by(VendorRisk.risk_score.desc()).limit(20).all()

def serialize_graph(g: SupplyChainGraph) -> Dict[str, Any]:
    return {"id": g.id, "name": g.name, "root_component": g.root_component, "graph": g.graph_json, "depth": g.depth, "total_dependencies": g.total_dependencies, "risky_dependencies": g.risky_dependencies}

def serialize_vendor(v: VendorRisk) -> Dict[str, Any]:
    return {"id": v.id, "vendor_name": v.vendor_name, "risk_score": v.risk_score, "risk_factors": v.risk_factors, "sbom_compliance": v.sbom_compliance, "attestation_status": v.attestation_status}
