from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.abac import require_permission
from app.models import User
from app.services import item_service
from app.schemas.item import EngineSettings, SettingsResponse

router = APIRouter(prefix="/engine", tags=["Engine Settings"])


@router.get("/settings")
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("engine:read")),
) -> EngineSettings:
    """Return the current threat detection engine settings."""
    return item_service.get_engine_settings(db)


@router.put("/settings")
def update_settings(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("engine:update")),
) -> SettingsResponse:
    """Update threat detection engine settings (requires engine:update)."""
    settings_out = item_service.update_engine_settings(db, payload)
    item_service.audit(
        db,
        action="ENGINE_SETTINGS_UPDATED",
        actor=current_user.username,
        resource="engine",
        details=str(payload),
    )
    return SettingsResponse(message="Engine settings updated successfully", settings=settings_out)
