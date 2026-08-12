from typing import Callable

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.abac import require_permission, require_any_permission
from app.api.v1.endpoints.auth import get_current_user

__all__ = [
    "get_db",
    "get_current_user",
    "require_permission",
    "require_any_permission",
    "get_current_admin",
    "get_current_analyst",
]


def get_current_admin(current_user: object = Depends(require_permission("users:manage"))) -> object:
    """Subject must hold the users:manage permission."""
    return current_user


def get_current_analyst(current_user: object = Depends(require_any_permission("alerts:read", "analytics:read"))) -> object:
    """Subject must hold at least one analytics/alerts read permission."""
    return current_user
