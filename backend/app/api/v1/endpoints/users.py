"""User and role administration (T-410, R-53, FR-42).

Three routes, and the third is the acceptance criterion:

* ``GET /api/v1/users`` -- the directory, plus the **active admin count** the
  last-admin rule is decided by. Disabled accounts are included and labelled,
  because a directory that hid them would make "who has access" unanswerable.
* ``GET /api/v1/users/roles`` -- R-53's four roles with their capabilities, read
  from the matrix itself so the screen cannot describe a role differently from the
  way the server enforces it.
* ``POST /api/v1/users/{user_id}/role`` -- set one role. **A change that would
  leave no active admin is refused**, whether the caller is the person being
  demoted or a colleague; the outcome is what the rule is about, and self-demotion
  is the case that arrives by accident.

**A refusal writes nothing.** No role is stored and no audit row is appended: the
trail records changes (D-041), and a row per attempt would let anyone with the
capability fill it. A no-op -- setting the role the user already holds -- is
reported as ``changed=false`` with the same consequence.

**What is deliberately absent.** No create, no disable, no invitation, no password
reset: each needs the credential lifecycle (``app.auth.passwords``) and a session to
write a ``users`` row through (D-030), and a route that accepted them would be
claiming an identity lifecycle this build does not have.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request

from app.api.v1.deps import audit_trail, client_ip, user_admin
from app.auth.rbac import ROLE_CAPABILITIES, Capability, Principal, Role, require
from app.db.models import UserRole
from app.schemas.user import (
    RoleChangeOut,
    RoleChangeRequest,
    RoleListOut,
    RoleNameOut,
    UserListOut,
    UserOut,
)
from app.services.audit_log import AuditAction, record_action
from app.services.user_directory import (
    LastActiveAdmin,
    RoleChange,
    UnknownUser,
    UserRecord,
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _out(record: UserRecord) -> UserOut:
    """Serialise one user. There is no credential field to include."""
    return UserOut(
        id=record.id,
        email=record.email,
        role=record.role.value,
        created_at=record.created_at,
        disabled_at=record.disabled_at,
    )


def _change_out(change: RoleChange) -> RoleChangeOut:
    """Serialise what a role change did."""
    return RoleChangeOut(
        user_id=change.user_id,
        previous=change.previous.value,
        applied=change.applied.value,
        changed=change.changed,
        at=change.at,
        actor=change.actor,
    )


@router.get(
    "",
    response_model=UserListOut,
    summary="The user directory and how many admins are active (T-410, R-53)",
    dependencies=[require(Capability.USERS)],
)
def list_users(request: Request) -> UserListOut:
    """Every user, with the count the last-admin rule is decided by."""
    service = user_admin(request)
    records = service.users()
    return UserListOut(
        items=[_out(record) for record in records],
        count=len(records),
        active_admins=len(service.active_admins()),
    )


@router.get(
    "/roles",
    response_model=RoleListOut,
    summary="R-53's roles and what each may do",
    dependencies=[require(Capability.USERS)],
)
def list_roles() -> RoleListOut:
    """The roles, read from the capability matrix rather than restated here."""
    return RoleListOut(
        items=[
            RoleNameOut(
                role=role.value,
                capabilities=sorted(capability.value for capability in ROLE_CAPABILITIES[role]),
            )
            for role in Role
        ]
    )


@router.post(
    "/{user_id}/role",
    response_model=RoleChangeOut,
    summary="Set one user's role, refusing to empty the admin role (T-410, R-53)",
)
def change_role(
    user_id: int,
    body: RoleChangeRequest,
    request: Request,
    caller: Annotated[Principal, require(Capability.USERS)],
) -> RoleChangeOut:
    """Change a user's role, or refuse with the rule that refused it.

    Raises:
        HTTPException: 400 for a role that is not one of R-53's four; 404 for an
            unknown user; 409 when the change would leave the deployment with no
            active admin. A conflict with the directory's own state is 409, not 400:
            the request is well formed and the answer is "not from here" -- the same
            reading T-315 gave a refused promotion.
    """
    try:
        role = UserRole(body.role)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in UserRole)
        raise HTTPException(
            status_code=400,
            detail=f"unknown role {body.role!r}; R-53's roles are: {allowed}",
        ) from exc

    service = user_admin(request)
    try:
        change = service.change_role(user_id, role=role, actor=caller.subject, at=datetime.now(UTC))
    except UnknownUser as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LastActiveAdmin as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if change.changed:
        record_action(
            audit_trail(request),
            action=AuditAction.user_role,
            actor=caller.subject,
            target_type="user",
            target_id=str(change.user_id),
            at=change.at,
            # The move, not the person: the trail is readable by every role (R-58),
            # so it records which role changed to which and leaves the address to the
            # directory read that already has an access check on it.
            detail={"previous": change.previous.value, "applied": change.applied.value},
            ip=client_ip(request),
        )
    return _change_out(change)
