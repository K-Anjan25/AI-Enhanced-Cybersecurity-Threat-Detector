"""Phase 93: Attack Path Analysis."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class AttackPath(Base):
    __tablename__ = "attack_paths"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    # Path: list of nodes (asset -> exposure -> asset)
    path_json = Column(JSON, default=list)  # [{asset_id, exposure_id, technique_id, cost}]
    # Risk
    risk_score = Column(Float, default=0.0)  # 0-100
    # Path type: internet_to_crown_jewel, lateral_movement, etc
    path_type = Column(String(50), default="internet_to_crown_jewel")
    # Crown jewel
    crown_jewel_asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    status = Column(String(20), default="active")  # active, mitigated
    created_at = Column(DateTime(timezone=True), default=_now)

class AttackPathFinding(Base):
    __tablename__ = "attack_path_findings"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    path_id = Column(Integer, ForeignKey("attack_paths.id"), nullable=False)
    title = Column(String(500), nullable=False)
    # Choke point: where to break path
    choke_point_asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    choke_point_exposure_id = Column(Integer, ForeignKey("asm_asset_exposures.id"), nullable=True)
    severity = Column(String(20), default="HIGH")
    remediation = Column(Text, nullable=True)
    status = Column(String(20), default="open")
    created_at = Column(DateTime(timezone=True), default=_now)
