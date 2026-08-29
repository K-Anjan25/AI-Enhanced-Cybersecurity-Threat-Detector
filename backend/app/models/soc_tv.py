"""Phase 84: Real-time SOC TV wall."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class SOCWallConfig(Base):
    __tablename__ = "soc_wall_configs"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    # Layout: list of widgets
    widgets_json = Column(JSON, default=list)  # [{type: "alert_feed", position: {x,y,w,h}, config: {...}}]
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class SOCWallMetric(Base):
    __tablename__ = "soc_wall_metrics"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    metric_name = Column(String(100), nullable=False)  # alerts_per_minute, open_cases, mttd, etc
    metric_value = Column(Float, nullable=False)
    # For time-series
    recorded_at = Column(DateTime(timezone=True), default=_now)
    metadata_json = Column(JSON, default=dict)
