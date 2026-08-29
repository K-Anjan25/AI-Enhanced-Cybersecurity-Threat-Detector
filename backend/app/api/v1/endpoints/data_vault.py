"""Phase 114: Data Vault endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import data_vault_service

router = APIRouter(prefix="/data-vault", tags=["Data Vault P114"])

class VaultIn(BaseModel):
    name: str
    vault_type: str = "confidential"

class SecretIn(BaseModel):
    vault_id: int
    secret_name: str
    secret_value: str

@router.get("/vaults")
def list_vaults(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        vaults = data_vault_service.list_vaults(db, current_user.org_id)
        return [data_vault_service.serialize_vault(v) for v in vaults]
    except Exception:
        return []

@router.post("/vaults")
def create_vault(payload: VaultIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        v = data_vault_service.create_vault(db, current_user.org_id, payload.name, payload.vault_type)
        return data_vault_service.serialize_vault(v)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/secrets")
def store_secret(payload: SecretIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        s = data_vault_service.store_secret(db, current_user.org_id, payload.vault_id, payload.secret_name, payload.secret_value)
        return data_vault_service.serialize_secret(s)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))

@router.get("/secrets")
def list_secrets(vault_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        secrets = data_vault_service.list_secrets(db, current_user.org_id, vault_id)
        return [data_vault_service.serialize_secret(s) for s in secrets]
    except Exception:
        return []
