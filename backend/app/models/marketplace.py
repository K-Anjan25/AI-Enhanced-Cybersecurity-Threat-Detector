"""Phase 75: SOAR Playbook Marketplace."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class MarketplacePlaybook(Base):
    __tablename__ = "marketplace_playbooks"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), default="response")  # response, enrichment, containment
    author = Column(String(200), default="NOCTRA")
    version = Column(String(20), default="1.0.0")
    # Playbook definition
    playbook_json = Column(JSON, default=dict)  # steps, conditions, actions
    tags = Column(JSON, default=list)
    downloads = Column(Integer, default=0)
    rating = Column(Float, default=4.5)
    is_verified = Column(Boolean, default=False)
    is_public = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_now)

class MarketplaceInstall(Base):
    __tablename__ = "marketplace_installs"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    playbook_id = Column(Integer, ForeignKey("marketplace_playbooks.id"), nullable=False, index=True)
    installed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Local copy of playbook after install
    local_playbook_id = Column(Integer, ForeignKey("soar_playbooks.id"), nullable=True)
    installed_at = Column(DateTime(timezone=True), default=_now)
