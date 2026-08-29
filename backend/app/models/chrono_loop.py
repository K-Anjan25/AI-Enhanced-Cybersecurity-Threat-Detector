"""Phase 143: Chrono-Loop Defense - closed timelike curves, bootstrap paradox defense."""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class TimeLoop(Base):
    __tablename__ = "time_loops"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    loop_type = Column(String(50), default="closed_timelike")  # closed_timelike, bootstrap, predestination, grandfather
    start_time = Column(DateTime(timezone=True), default=_now)
    end_time = Column(DateTime(timezone=True), default=_now)
    iterations = Column(Integer, default=1)
    max_iterations = Column(Integer, default=1000)
    paradox_risk = Column(Float, default=0.1)
    status = Column(String(20), default="contained")
    created_at = Column(DateTime(timezone=True), default=_now)

class LoopIteration(Base):
    __tablename__ = "loop_iterations"
    id = Column(Integer, primary_key=True, index=True)
    loop_id = Column(Integer, ForeignKey("time_loops.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    iteration_number = Column(Integer, nullable=False)
    timeline_delta = Column(JSON, default=dict)  # what changed this iteration
    paradox_detected = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_now)

class ChronoDefense(Base):
    __tablename__ = "chrono_defenses"
    id = Column(Integer, primary_key=True, index=True)
    loop_id = Column(Integer, ForeignKey("time_loops.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    defense_type = Column(String(100), default="causality_anchor")
    config_json = Column(JSON, default=dict)
    effectiveness = Column(Float, default=99.5)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)
