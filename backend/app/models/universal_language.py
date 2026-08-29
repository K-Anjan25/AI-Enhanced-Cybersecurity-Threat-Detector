"""Phase 137: Universal Language - universal threat language."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class UniversalLanguageModel(Base):
    __tablename__ = "universal_language_models"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    language_type = Column(String(50), default="threat")  # threat, protocol, species, machine
    supported_formats = Column(JSON, default=list)  # ["stix","misp","ocsf","sigma","yara","custom_alien"]
    translation_accuracy = Column(Float, default=94.0)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class Translation(Base):
    __tablename__ = "translations"
    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, ForeignKey("universal_language_models.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    source_format = Column(String(50), nullable=False)
    target_format = Column(String(50), nullable=False)
    source_content = Column(JSON, default=dict)
    translated_content = Column(JSON, default=dict)
    confidence = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)

class UniversalThreat(Base):
    __tablename__ = "universal_threats"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    universal_id = Column(String(100), nullable=False)  # universal threat ID
    threat_name = Column(String(500), nullable=False)
    representations_json = Column(JSON, default=dict)  # {stix: {}, sigma: {}, yara: {}, alien: {}}
    severity = Column(String(20), default="HIGH")
    created_at = Column(DateTime(timezone=True), default=_now)
