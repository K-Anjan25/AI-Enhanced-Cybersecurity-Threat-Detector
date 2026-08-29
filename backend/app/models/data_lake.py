"""Phase 73: Data Lake S3 Parquet + Athena."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class DataLakeExport(Base):
    __tablename__ = "data_lake_exports"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    export_type = Column(String(50), default="alerts")  # alerts, audit_logs, cases, vulns
    s3_bucket = Column(String(200), nullable=True)
    s3_key = Column(String(500), nullable=True)  # e.g. datalake/org_id=1/year=2026/month=08/alerts.parquet
    format = Column(String(20), default="parquet")  # parquet, json, csv
    row_count = Column(Integer, default=0)
    file_size_bytes = Column(Integer, default=0)
    status = Column(String(20), default="completed")  # pending, completed, failed
    # Partition info
    partition_year = Column(Integer, nullable=True)
    partition_month = Column(Integer, nullable=True)
    partition_day = Column(Integer, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class DataLakeQuery(Base):
    __tablename__ = "data_lake_queries"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    query = Column(Text, nullable=False)  # Athena SQL
    status = Column(String(20), default="completed")
    result_count = Column(Integer, default=0)
    results_json = Column(JSON, default=dict)
    execution_time_ms = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=_now)
