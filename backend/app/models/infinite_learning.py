"""Phase 138: Infinite Learning - continual learning without forgetting."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class InfiniteLearner(Base):
    __tablename__ = "infinite_learners"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    learner_type = Column(String(50), default="continual")  # continual, meta, curriculum, self_supervised
    total_tasks_learned = Column(Integer, default=0)
    forgetting_rate = Column(Float, default=0.01)  # catastrophic forgetting low
    forward_transfer = Column(Float, default=0.85)
    backward_transfer = Column(Float, default=0.1)
    status = Column(String(20), default="learning")
    created_at = Column(DateTime(timezone=True), default=_now)

class LearningTask(Base):
    __tablename__ = "learning_tasks"
    id = Column(Integer, primary_key=True, index=True)
    learner_id = Column(Integer, ForeignKey("infinite_learners.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    task_name = Column(String(300), nullable=False)
    task_type = Column(String(50), default="classification")  # classification, detection, generation
    dataset_size = Column(Integer, default=10000)
    accuracy_before = Column(Float, default=0.0)
    accuracy_after = Column(Float, default=0.0)
    status = Column(String(20), default="completed")
    created_at = Column(DateTime(timezone=True), default=_now)

class MemoryConsolidation(Base):
    __tablename__ = "memory_consolidations"
    id = Column(Integer, primary_key=True, index=True)
    learner_id = Column(Integer, ForeignKey("infinite_learners.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    consolidation_type = Column(String(50), default="ewc")  # ewc, replay, progressive, packnet
    retained_knowledge = Column(Float, default=95.0)
    consolidated_at = Column(DateTime(timezone=True), default=_now)
