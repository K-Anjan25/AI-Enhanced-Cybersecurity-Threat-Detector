"""Phase 86: Threat Hunting Notebook (Jupyter-like)."""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON
from datetime import datetime, timezone
from app.core.database import Base

def _now():
    return datetime.now(timezone.utc)

class HuntNotebook(Base):
    __tablename__ = "hunt_notebooks"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    # Kernel: python, kql, sql
    kernel = Column(String(20), default="python")
    # Tags for hunting
    tags = Column(JSON, default=list)
    is_public = Column(Boolean, default=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

class NotebookCell(Base):
    __tablename__ = "notebook_cells"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    notebook_id = Column(Integer, ForeignKey("hunt_notebooks.id"), nullable=False, index=True)
    cell_type = Column(String(20), default="code")  # code, markdown, kql, sql
    position = Column(Integer, default=0)
    source = Column(Text, nullable=False)  # code content
    # Execution result
    output_json = Column(JSON, default=dict)  # {stdout, stderr, result_count, results}
    execution_count = Column(Integer, default=0)
    status = Column(String(20), default="idle")  # idle, running, completed, failed
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

class NotebookExecution(Base):
    __tablename__ = "notebook_executions"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("orgs.id"), nullable=False, index=True)
    notebook_id = Column(Integer, ForeignKey("hunt_notebooks.id"), nullable=False, index=True)
    status = Column(String(20), default="completed")
    # Results summary
    results_json = Column(JSON, default=dict)
    executed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    started_at = Column(DateTime(timezone=True), default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
