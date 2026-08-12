"""
ABAC (Attribute-Based Access Control) policy engine.

Access decisions are evaluated from ATTRIBUTES rather than a hard-coded role:

  Subject attributes  : role, clearance_level, department, is_active, is_blocked
  Resource attributes : resource type, resource sensitivity (e.g. severity)
  Action              : read / write / delete / manage / export ...
  Environment         : (future) time-of-day, source IP, session context

A subject is granted a permission when BOTH:
  1. The permission is granted by their subject attributes (role base-set
     combined with any clearance / department overrides), AND
  2. The resource attribute condition (if any) for that permission passes.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import User

# ---------------------------------------------------------------------------
# Permission catalog: <resource>:<action>
# ---------------------------------------------------------------------------

PERMISSIONS = {
    # Alerts
    "alerts:read",
    "alerts:write",      # submit logs / analyze
    "alerts:delete",     # clear alerts
    "alerts:export",
    # Analytics
    "analytics:read",
    # Detection engine settings
    "engine:read",
    "engine:update",
    # Detection rules
    "rules:read",
    "rules:write",
    "rules:delete",
    # IP reputation
    "reputation:read",
    "reputation:write",
    "reputation:block",
    # Audit trail
    "audit:read",
    # User administration
    "users:read",
    "users:write",
    "users:manage",
}

# ---------------------------------------------------------------------------
# Base permission set per role.
# ---------------------------------------------------------------------------

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "ADMIN": set(PERMISSIONS),
    "ANALYST": {
        "alerts:read",
        "alerts:write",
        "alerts:export",
        "analytics:read",
        "engine:read",
        "rules:read",
        "reputation:read",
    },
    "USER": {
        "alerts:read",
        "alerts:write",
        "analytics:read",
        "engine:read",
    },
}

# ---------------------------------------------------------------------------
# Subject attribute requirements (clearance levels).
# Higher sensitivity actions demand a higher clearance_level.
# ---------------------------------------------------------------------------

CLEARANCE_REQUIREMENTS: dict[str, int] = {
    "engine:update": 4,
    "audit:read": 4,
    "users:manage": 4,
    "alerts:delete": 3,
    "rules:write": 3,
    "rules:delete": 3,
    "reputation:write": 3,
    "reputation:block": 3,
}

DEFAULT_CLEARANCE_BY_ROLE: dict[str, int] = {
    "ADMIN": 4,
    "ANALYST": 2,
    "USER": 1,
}


def effective_clearance(user: User) -> int:
    """Resolve the subject's clearance_level, falling back to role default."""
    if user.clearance_level is not None:
        return user.clearance_level
    role = (getattr(user, "role", None) or "USER").upper()
    return DEFAULT_CLEARANCE_BY_ROLE.get(role, 1)


def effective_department(user: User) -> Optional[str]:
    return getattr(user, "department", None)


def base_permissions_for_role(role: Optional[str]) -> set[str]:
    role = (role or "USER").upper()
    return set(ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["USER"]))


def subject_is_active(user: User) -> bool:
    if getattr(user, "is_blocked", False):
        return False
    if hasattr(user, "is_active"):
        return bool(user.is_active)
    return True


def subject_permissions(user: User) -> set[str]:
    """
    Evaluate the SUBJECT-side of the policy:
    base role permissions, minus any denied by subject attributes
    (e.g. blocked accounts, low clearance).
    """
    if not subject_is_active(user):
        return set()

    role = (getattr(user, "role", None) or "USER").upper()
    perms = base_permissions_for_role(role)
    clearance = effective_clearance(user)

    for perm in list(perms):
        required = CLEARANCE_REQUIREMENTS.get(perm)
        if required is not None and clearance < required:
            perms.discard(perm)
    return perms


def resource_condition_passes(permission: str, resource: Optional[dict] = None) -> bool:
    """
    Evaluate the RESOURCE-side of the policy.

    A resource may carry attributes (e.g. {'severity': 'CRITICAL'}). Rules here
    describe which resource attributes are permitted for a given action. Resource
    attribute rules are evaluated in addition to the subject's clearance level.

    When no resource is supplied, the condition trivially passes.
    """
    if resource is None:
        return True

    severity = (resource.get("severity") or "").upper()
    # Example policy: analysts may not export/clear alerts for CRITICAL hosts.
    if permission == "alerts:export" and severity == "CRITICAL":
        return False
    if permission == "alerts:delete" and severity == "CRITICAL":
        return False
    return True


def can(user: User, permission: str, resource: Optional[dict] = None) -> bool:
    """Full ABAC decision for `user` doing `permission` on `resource`."""
    if permission not in PERMISSIONS:
        return False
    if permission not in subject_permissions(user):
        return False
    return resource_condition_passes(permission, resource)


# ---------------------------------------------------------------------------
# FastAPI dependency helpers
# ---------------------------------------------------------------------------

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_bearer = HTTPBearer()


def _resolve_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated subject by delegating to auth.get_current_user.

    Imported lazily inside the function to avoid a module-level circular
    dependency between core/abac and api/v1/endpoints/auth.
    """
    from app.api.v1.endpoints.auth import get_current_user

    return get_current_user(request=None, credentials=credentials, db=db)


def require_permission(permission: str):
    """
    Dependency factory: requires the current subject to hold `permission`
    (subject attributes only; resource-level checks happen in the endpoint).
    """

    def _checker(current_user: User = Depends(_resolve_current_user)) -> User:
        if not can(current_user, permission):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user

    return _checker


def require_any_permission(*permissions: str):
    """Dependency factory: allow if the subject holds ANY of `permissions`."""

    def _checker(current_user: User = Depends(_resolve_current_user)) -> User:
        subject = subject_permissions(current_user)
        if not (set(permissions) & subject):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user

    return _checker
