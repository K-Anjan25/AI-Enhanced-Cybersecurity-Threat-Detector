"""Phase 72: Exec risk dashboard + board reporting + ROI."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float, ForeignKey, JSON
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class RiskMetric(Base):
    __tablename__ = "risk_metrics"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    metric_name = Column(String(100), nullable=False)  # mean_time_to_detect, mean_time_to_respond, risk_score, etc
    metric_value = Column(Float, nullable=False)
    # Trend: {"previous_value": 10, "change_percent": -5}
    trend_json = Column(JSON, default=dict)
    recorded_at = Column(DateTime(timezone=True), default=_now)

class ExecReport(Base):
    __tablename__ = "exec_reports"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    report_type = Column(String(50), default="board_pack")  # board_pack, weekly, monthly, roi
    # Report data: {"executive_summary": "...", "risk_trends": [...], "incidents": [...], "roi": {...}}
    report_json = Column(JSON, default=dict)
    generated_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class ROIMetric(Base):
    __tablename__ = "roi_metrics"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    # e.g. analyst hours saved, auto-triaged cases, mean time saved
    metric_name = Column(String(100), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(20), default="hours")  # hours, dollars, percent
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
