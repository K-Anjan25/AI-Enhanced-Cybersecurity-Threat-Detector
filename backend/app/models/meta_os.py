"""Phase 120: NOCTRA Singularity OS v2 - Meta-OS that rewrites itself."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class MetaOSConfig(Base):
    __tablename__ = "meta_os_configs"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    version = Column(String(50), default="2.0.0")
    # Meta-OS config: self-evolution
    evolution_enabled = Column(Boolean, default=True)
    evolution_strategy = Column(String(50), default="genetic")  # genetic, reinforcement, llm_guided
    autonomy_level = Column(String(20), default="fully_autonomous")
    # Which modules can be rewritten
    rewritable_modules_json = Column(JSON, default=list)  # ["detection", "response", "hunting"]
    # Safety constraints
    safety_constraints_json = Column(JSON, default=dict)  # {max_code_change: "10%", require_approval: true}
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), default=_now)

class CodeEvolution(Base):
    __tablename__ = "code_evolutions"
    id = Column(Integer, primary_key=True, index=True)
    meta_os_id = Column(Integer, ForeignKey("meta_os_configs.id"), nullable=False)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    module_name = Column(String(200), nullable=False)
    previous_version = Column(String(50), nullable=True)
    new_version = Column(String(50), nullable=False)
    change_description = Column(Text, nullable=True)
    diff_json = Column(JSON, default=dict)  # {files_changed, lines_added, lines_removed}
    performance_improvement = Column(Float, default=0.0)  # % improvement
    safety_score = Column(Float, default=100.0)
    status = Column(String(20), default="proposed")  # proposed, testing, deployed, rolled_back
    created_at = Column(DateTime(timezone=True), default=_now)

class SelfRewriteLog(Base):
    __tablename__ = "self_rewrite_logs"
    id = Column(Integer, primary_key=True, index=True)
    evolution_id = Column(Integer, ForeignKey("code_evolutions.id"), nullable=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    log_type = Column(String(50), default="rewrite")  # rewrite, test, deploy, rollback
    title = Column(String(500), nullable=False)
    details_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=_now)
