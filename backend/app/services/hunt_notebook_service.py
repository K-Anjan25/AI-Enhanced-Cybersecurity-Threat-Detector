"""Phase 86: Threat Hunting Notebook service."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.models.hunt_notebook import HuntNotebook, NotebookCell, NotebookExecution


def _now():
    return datetime.now(timezone.utc)


def create_notebook(db: Session, org_id: int, name: str, description: str = None, kernel: str = "python", tags: List[str] = None, created_by_user_id: int = None) -> HuntNotebook:
    nb = HuntNotebook(org_id=org_id, name=name, description=description, kernel=kernel, tags=tags or [], created_by_user_id=created_by_user_id)
    db.add(nb)
    db.commit()
    db.refresh(nb)
    return nb


def list_notebooks(db: Session, org_id: int) -> List[HuntNotebook]:
    return db.query(HuntNotebook).filter(HuntNotebook.org_id == org_id).order_by(HuntNotebook.updated_at.desc()).all()


def add_cell(db: Session, org_id: int, notebook_id: int, cell_type: str = "code", source: str = "", position: int = None) -> NotebookCell:
    nb = db.query(HuntNotebook).filter(HuntNotebook.id == notebook_id, HuntNotebook.org_id == org_id).first()
    if not nb:
        raise ValueError("Notebook not found")
    if position is None:
        max_pos = db.query(NotebookCell).filter(NotebookCell.notebook_id == notebook_id).count()
        position = max_pos
    cell = NotebookCell(org_id=org_id, notebook_id=notebook_id, cell_type=cell_type, position=position, source=source)
    db.add(cell)
    db.commit()
    db.refresh(cell)
    nb.updated_at = _now()
    db.commit()
    return cell


def list_cells(db: Session, org_id: int, notebook_id: int) -> List[NotebookCell]:
    return db.query(NotebookCell).filter(NotebookCell.org_id == org_id, NotebookCell.notebook_id == notebook_id).order_by(NotebookCell.position.asc()).all()


def execute_cell(db: Session, org_id: int, cell_id: int) -> NotebookCell:
    """Execute a single cell - supports python (mock), kql, sql."""
    cell = db.query(NotebookCell).filter(NotebookCell.id == cell_id, NotebookCell.org_id == org_id).first()
    if not cell:
        raise ValueError("Cell not found")
    cell.status = "running"
    cell.execution_count += 1
    db.commit()

    start = time.time()
    output = {}
    try:
        if cell.cell_type == "kql":
            # Execute as hunt query
            from app.services import hunt_service
            result = hunt_service.execute_hunt_query(db, org_id, cell.source, limit=20)
            output = {"stdout": f"Found {result['result_count']} results", "result_count": result["result_count"], "results": result["results"][:5], "duration_ms": result["duration_ms"]}
            cell.status = "completed"
        elif cell.cell_type == "python":
            # Mock python execution - in real would use jupyter kernel
            # For safety, only allow simple expressions
            if "import os" in cell.source or "import sys" in cell.source:
                output = {"stderr": "Import os/sys not allowed", "stdout": ""}
                cell.status = "failed"
            else:
                # Simulate execution
                output = {"stdout": f"Executed python cell: {cell.source[:100]}", "result": "mock_result", "execution_time_ms": int((time.time()-start)*1000)}
                cell.status = "completed"
        elif cell.cell_type == "markdown":
            output = {"stdout": cell.source, "rendered": True}
            cell.status = "completed"
        else:
            output = {"stdout": f"Executed {cell.cell_type} cell", "source": cell.source[:200]}
            cell.status = "completed"
    except Exception as e:
        output = {"stderr": str(e), "stdout": ""}
        cell.status = "failed"

    cell.output_json = output
    db.commit()
    db.refresh(cell)
    return cell


def execute_notebook(db: Session, org_id: int, notebook_id: int, executed_by_user_id: int = None) -> NotebookExecution:
    nb = db.query(HuntNotebook).filter(HuntNotebook.id == notebook_id, HuntNotebook.org_id == org_id).first()
    if not nb:
        raise ValueError("Notebook not found")

    exec_log = NotebookExecution(org_id=org_id, notebook_id=notebook_id, status="running", executed_by_user_id=executed_by_user_id)
    db.add(exec_log)
    db.commit()

    cells = list_cells(db, org_id, notebook_id)
    results = []
    for cell in cells:
        if cell.cell_type != "markdown":
            try:
                executed = execute_cell(db, org_id, cell.id)
                results.append({"cell_id": cell.id, "status": executed.status, "output": executed.output_json})
            except Exception as e:
                results.append({"cell_id": cell.id, "status": "failed", "error": str(e)})

    exec_log.status = "completed"
    exec_log.results_json = {"cell_results": results, "total_cells": len(cells)}
    exec_log.completed_at = _now()
    db.commit()
    db.refresh(exec_log)
    return exec_log


def seed_notebooks(db: Session, org_id: int) -> List[HuntNotebook]:
    existing = db.query(HuntNotebook).filter(HuntNotebook.org_id == org_id).count()
    if existing > 0:
        return list_notebooks(db, org_id)
    nb = create_notebook(db, org_id, "Threat Hunting Starter", "Starter notebook with KQL examples", kernel="python", tags=["starter", "kql"])
    add_cell(db, org_id, nb.id, cell_type="markdown", source="# Threat Hunting Starter\nThis notebook demonstrates KQL hunting + Python enrichment", position=0)
    add_cell(db, org_id, nb.id, cell_type="kql", source="severity:CRITICAL AND source:okta", position=1)
    add_cell(db, org_id, nb.id, cell_type="python", source="alerts = hunt_results\nprint(f'Found {len(alerts)} critical alerts')", position=2)
    return [nb]


def serialize_notebook(n: HuntNotebook) -> Dict[str, Any]:
    return {"id": n.id, "name": n.name, "description": n.description, "kernel": n.kernel, "tags": n.tags, "is_public": n.is_public, "created_at": n.created_at.isoformat() if n.created_at else None, "updated_at": n.updated_at.isoformat() if n.updated_at else None}


def serialize_cell(c: NotebookCell) -> Dict[str, Any]:
    return {"id": c.id, "notebook_id": c.notebook_id, "cell_type": c.cell_type, "position": c.position, "source": c.source, "output": c.output_json, "execution_count": c.execution_count, "status": c.status}
