"""Phase 76: LLM fine-tune on SOC data."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class FineTuneJob(Base):
    __tablename__ = "finetune_jobs"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    base_model = Column(String(100), default="claude-sonnet-5")
    dataset_type = Column(String(50), default="cases")  # cases, alerts, hunts, combined
    dataset_size = Column(Integer, default=0)
    # Training config
    config_json = Column(JSON, default=dict)  # epochs, learning_rate, etc
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    progress = Column(Float, default=0.0)  # 0-100
    metrics_json = Column(JSON, default=dict)  # loss, accuracy
    result_model_id = Column(String(200), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

class FineTuneDataset(Base):
    __tablename__ = "finetune_datasets"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    source = Column(String(50), default="cases")  # cases, alerts
    record_count = Column(Integer, default=0)
    s3_key = Column(String(500), nullable=True)
    preview_json = Column(JSON, default=dict)  # sample records
    created_at = Column(DateTime(timezone=True), default=_now)
