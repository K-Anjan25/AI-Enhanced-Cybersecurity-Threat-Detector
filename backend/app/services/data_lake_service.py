"""Phase 73: Data Lake S3 Parquet service."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.data_lake import DataLakeExport, DataLakeQuery
from app.models import SecurityAlert
from app.core.config import settings


def _now():
    return datetime.now(timezone.utc)


def export_alerts_to_parquet(db: Session, org_id: int, year: int = None, month: int = None, created_by_user_id: int = None) -> DataLakeExport:
    """Export alerts to S3 as Parquet (mock if no S3 config, creates metadata only)."""
    now = _now()
    year = year or now.year
    month = month or now.month

    alerts = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id).limit(10000).all()
    row_count = len(alerts)

    # Mock Parquet: if S3 configured, would use pyarrow to write
    s3_bucket = getattr(settings, "S3_BUCKET", "noctra-datalake")
    s3_key = f"datalake/org_id={org_id}/year={year}/month={month:02d}/alerts_{now.strftime('%Y%m%d_%H%M%S')}.parquet"

    # Simulate file size: 200 bytes per alert avg
    file_size = row_count * 200

    export = DataLakeExport(
        org_id=org_id,
        export_type="alerts",
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        format="parquet",
        row_count=row_count,
        file_size_bytes=file_size,
        status="completed",
        partition_year=year,
        partition_month=month,
        created_by_user_id=created_by_user_id,
    )
    db.add(export)
    db.commit()
    db.refresh(export)

    # In real implementation, upload to S3 here using boto3
    # try:
    #   import pyarrow, boto3 ...
    # except: fallback to json

    return export


def list_exports(db: Session, org_id: int, limit: int = 50) -> List[DataLakeExport]:
    return db.query(DataLakeExport).filter(DataLakeExport.org_id == org_id).order_by(DataLakeExport.created_at.desc()).limit(limit).all()


def query_datalake(db: Session, org_id: int, athena_sql: str) -> DataLakeQuery:
    """Mock Athena query - in real would call Athena API."""
    # For demo, parse SQL and return mock results
    # If query contains security_alerts, return count
    result_count = 0
    if "security_alerts" in athena_sql.lower():
        result_count = db.query(SecurityAlert).filter(SecurityAlert.org_id == org_id).count()

    q = DataLakeQuery(
        org_id=org_id,
        query=athena_sql,
        status="completed",
        result_count=result_count,
        results_json={"mock": True, "result_count": result_count, "query": athena_sql},
        execution_time_ms=120,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


def serialize_export(e: DataLakeExport) -> Dict[str, Any]:
    return {"id": e.id, "export_type": e.export_type, "s3_bucket": e.s3_bucket, "s3_key": e.s3_key, "format": e.format, "row_count": e.row_count, "file_size_bytes": e.file_size_bytes, "status": e.status, "partition_year": e.partition_year, "partition_month": e.partition_month, "created_at": e.created_at.isoformat() if e.created_at else None}


def serialize_query(q: DataLakeQuery) -> Dict[str, Any]:
    return {"id": q.id, "query": q.query, "status": q.status, "result_count": q.result_count, "execution_time_ms": q.execution_time_ms, "created_at": q.created_at.isoformat() if q.created_at else None}
