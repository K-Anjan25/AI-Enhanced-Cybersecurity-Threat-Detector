"""Phase 95: Security Data Fabric."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class DataFabricSource(Base):
    __tablename__ = "data_fabric_sources"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    source_type = Column(String(50), default="siem")  # siem, data_lake, edr, cloud, tip
    # Connection
    connection_json = Column(JSON, default=dict)  # {url, bucket, table, etc}
    is_active = Column(Boolean, default=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class DataFabricQuery(Base):
    __tablename__ = "data_fabric_queries"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    query = Column(Text, nullable=False)  # unified SQL across sources
    # Sources involved
    sources_json = Column(JSON, default=list)  # [source_ids]
    status = Column(String(20), default="completed")
    result_count = Column(Integer, default=0)
    results_json = Column(JSON, default=dict)
    execution_time_ms = Column(Integer, default=0)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class DataFabricView(Base):
    __tablename__ = "data_fabric_views"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    # View definition: unified query
    query = Column(Text, nullable=False)
    is_materialized = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_now)
