"""Phase 54: Org teams + invites."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.abac import require_permission
from app.models import User
from app.services import org_invite_service

router = APIRouter(prefix="/org", tags=["Org Teams & Invites (Phase 54)"])


class TeamCreate(BaseModel):
    name: str
    description: Optional[str] = None


class TeamMemberAdd(BaseModel):
    user_id: int
    role: str = "member"


class InviteCreate(BaseModel):
    email: EmailStr
    role: str = "USER"
    team_id: Optional[int] = None


class InviteAccept(BaseModel):
    token: str
    username: str
    password: str


@router.get("/teams")
def list_teams(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users:read")),
):
    rows = org_invite_service.list_teams(db, org_id=current_user.org_id)
    return [org_invite_service.serialize_team(t) for t in rows]


@router.post("/teams", status_code=201)
def create_team(
    payload: TeamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users:write")),
):
    team = org_invite_service.create_team(db, org_id=current_user.org_id, name=payload.name, description=payload.description)
    return org_invite_service.serialize_team(team)


@router.post("/teams/{team_id}/members", status_code=201)
def add_member(
    team_id: int,
    payload: TeamMemberAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users:write")),
):
    try:
        m = org_invite_service.add_team_member(db, org_id=current_user.org_id, team_id=team_id, user_id=payload.user_id, role=payload.role)
        return {"team_id": team_id, "user_id": m.user_id, "role": m.role}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/invites")
def list_invites(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users:read")),
):
    rows = org_invite_service.list_invites(db, org_id=current_user.org_id)
    return [org_invite_service.serialize_invite(i) for i in rows]


@router.post("/invites", status_code=201)
def create_invite(
    payload: InviteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users:write")),
):
    try:
        invite = org_invite_service.create_invite(
            db,
            org_id=current_user.org_id,
            email=payload.email,
            role=payload.role,
            team_id=payload.team_id,
            invited_by_user_id=current_user.id,
        )
        # Return full token once (not masked) for demo
        data = org_invite_service.serialize_invite(invite)
        data["raw_token"] = invite.token
        data["warning"] = "Share this token securely — it expires in 72h"
        return data
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/invites/accept", status_code=201)
def accept_invite(
    payload: InviteAccept,
    db: Session = Depends(get_db),
):
    try:
        user = org_invite_service.accept_invite(db, token=payload.token, username=payload.username, password=payload.password)
        return {"status": "accepted", "user_id": user.id, "username": user.username, "org_id": user.org_id}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete("/invites/{invite_id}")
def revoke_invite(
    invite_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("users:write")),
):
    ok = org_invite_service.revoke_invite(db, org_id=current_user.org_id, invite_id=invite_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Invite not found")
    return {"status": "revoked"}
