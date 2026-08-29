"""Phase 95: Data Fabric service."""

from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models.data_fabric import DataFabricSource, DataFabricQuery, DataFabricView

def _now():
    return datetime.now(timezone.utc)

def create_source(db: Session, org_id: int, name: str, source_type: str = "siem", connection: Dict = None) -> DataFabricSource:
    src = DataFabricSource(org_id=org_id, name=name, source_type=source_type, connection_json=connection or {})
    db.add(src)
    db.commit()
    db.refresh(src)
    return src

def list_sources(db: Session, org_id: int) -> List[DataFabricSource]:
    return db.query(DataFabricSource).filter(DataFabricSource.org_id == org_id, DataFabricSource.is_active == True).all()

def seed_sources(db: Session, org_id: int) -> List[DataFabricSource]:
    existing = db.query(DataFabricSource).filter(DataFabricSource.org_id == org_id).count()
    if existing > 0:
        return list_sources(db, org_id)
    defaults = [
        {"name": "SIEM - threatdb", "source_type": "siem", "connection": {"table": "security_alerts"}},
        {"name": "Data Lake - S3 Parquet", "source_type": "data_lake", "connection": {"bucket": "noctra-datalake", "format": "parquet"}},
        {"name": "EDR - CrowdStrike", "source_type": "edr", "connection": {"api": "crowdstrike"}},
        {"name": "Cloud - AWS CloudTrail", "source_type": "cloud", "connection": {"service": "cloudtrail"}},
        {"name": "TIP - MISP", "source_type": "tip", "connection": {"feed": "misp"}},
    ]
    created = []
    for d in defaults:
        src = create_source(db, org_id, d["name"], d["source_type"], d["connection"])
        created.append(src)
    return created

def query_fabric(db: Session, org_id: int, query: str, sources: List[int] = None, created_by_user_id: int = None) -> DataFabricQuery:
    """Unified query across sources - mock federated query."""
    # Mock: if query mentions alerts, count from security_alerts
    from app.models import SecurityAlert
    result_count = 0
    if "alert" in query.lower():
        result_count = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id).count()

    q = DataFabricQuery(org_id=org_id, query=query, sources_json=sources or [], status="completed", result_count=result_count, results_json={"mock": True, "sources_queried": sources or [], "result_count": result_count}, execution_time_ms=150, created_by_user_id=created_by_user_id)
    db.add(q)
    db.commit()
    db.refresh(q)
    return q

def serialize_source(s: DataFabricSource) -> Dict[str, Any]:
    return {"id": s.id, "name": s.name, "source_type": s.source_type, "connection": s.connection_json, "is_active": s.is_active}

def serialize_query(q: DataFabricQuery) -> Dict[str, Any]:
    return {"id": q.id, "query": q.query, "sources": q.sources_json, "status": q.status, "result_count": q.result_count, "execution_time_ms": q.execution_time_ms, "created_at": q.created_at.isoformat() if q.created_at else None}
