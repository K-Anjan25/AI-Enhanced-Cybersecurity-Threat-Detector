"""Phase 89: Federated Learning across orgs."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class FederatedJob(Base):
    __tablename__ = "federated_jobs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    # Model type: threat_detection, anomaly_detection, etc
    model_type = Column(String(50), default="threat_detection")
    base_model = Column(String(100), default="noctra-ml-v1")
    # Federated config
    config_json = Column(JSON, default=dict)  # {rounds: 5, min_orgs: 3, aggregation: fedavg, dp_noise: 0.1}
    status = Column(String(20), default="pending")  # pending, running, aggregating, completed, failed
    current_round = Column(Integer, default=0)
    total_rounds = Column(Integer, default=5)
    # Results
    global_model_id = Column(String(200), nullable=True)
    global_metrics_json = Column(JSON, default=dict)  # {accuracy, f1, loss}
    participating_orgs = Column(JSON, default=list)  # list of org_ids
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

class FederatedRound(Base):
    __tablename__ = "federated_rounds"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("federated_jobs.id"), nullable=False, index=True)
    round_number = Column(Integer, default=1)
    status = Column(String(20), default="pending")  # pending, training, aggregating, completed
    # Aggregated metrics for round
    metrics_json = Column(JSON, default=dict)
    participating_orgs = Column(JSON, default=list)
    started_at = Column(DateTime(timezone=True), default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

class OrgModelUpdate(Base):
    __tablename__ = "org_model_updates"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("federated_jobs.id"), nullable=False, index=True)
    round_id = Column(Integer, ForeignKey("federated_rounds.id"), nullable=False, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    # Model update (not raw data) - weights delta, metrics
    update_json = Column(JSON, default=dict)  # {weights_hash, sample_count, loss}
    metrics_json = Column(JSON, default=dict)  # {accuracy, f1}
    status = Column(String(20), default="pending")  # pending, submitted, aggregated
    # Privacy: DP noise added, secure aggregation
    is_private = Column(Boolean, default=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class FederatedModel(Base):
    __tablename__ = "federated_models"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("federated_jobs.id"), nullable=False, index=True)
    round_id = Column(Integer, ForeignKey("federated_rounds.id"), nullable=True)
    version = Column(String(50), default="v1")
    model_id = Column(String(200), nullable=False)
    # Model metadata
    metrics_json = Column(JSON, default=dict)
    s3_key = Column(String(500), nullable=True)
    is_global = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_now)
