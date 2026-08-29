"""Phase 102: Predictive SOC endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.core.abac import require_permission
from app.models.user import User
from app.services import predictive_soc_service

router = APIRouter(prefix="/predictive-soc", tags=["Predictive SOC P102"])

class ModelIn(BaseModel):
    name: str
    model_type: str = "breach_likelihood"

@router.get("/models")
def list_models(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        models = predictive_soc_service.list_models(db, current_user.org_id)
        return [predictive_soc_service.serialize_model(m) for m in models]
    except Exception:
        return []

@router.post("/models")
def create_model(payload: ModelIn, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        m = predictive_soc_service.create_model(db, current_user.org_id, payload.name, payload.model_type)
        return predictive_soc_service.serialize_model(m)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.post("/forecast")
def forecast(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        fcs = predictive_soc_service.forecast_threats(db, current_user.org_id)
        return [predictive_soc_service.serialize_forecast(f) for f in fcs]
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@router.get("/forecasts")
def list_forecasts(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit:read"))):
    try:
        fcs = predictive_soc_service.list_forecasts(db, current_user.org_id)
        return [predictive_soc_service.serialize_forecast(f) for f in fcs]
    except Exception:
        return []
