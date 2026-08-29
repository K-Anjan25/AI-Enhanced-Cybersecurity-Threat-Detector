"""Phase 54: Org hierarchy + invites + teams."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from app.models.org_invite import OrgInvite, Team, TeamMembership
from app.models import User, Org
from app.core.config import settings
from app.core.security import get_password_hash


def create_team(db: Session, org_id: int, name: str, description: str = None) -> Team:
    team = Team(org_id=org_id, name=name, description=description)
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


def list_teams(db: Session, org_id: int) -> List[Team]:
    return db.query(Team).filter(Team.org_id == org_id).order_by(Team.name).all()


def add_team_member(db: Session, org_id: int, team_id: int, user_id: int, role: str = "member") -> TeamMembership:
    # Verify team belongs to org
    team = db.query(Team).filter(Team.id == team_id, Team.org_id == org_id).first()
    if not team:
        raise ValueError("Team not found")
    user = db.query(User).filter(User.id == user_id, User.org_id == org_id).first()
    if not user:
        raise ValueError("User not found in org")
    existing = db.query(TeamMembership).filter(TeamMembership.team_id == team_id, TeamMembership.user_id == user_id).first()
    if existing:
        return existing
    membership = TeamMembership(team_id=team_id, user_id=user_id, role=role)
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


def list_team_members(db: Session, team_id: int) -> List[TeamMembership]:
    return db.query(TeamMembership).filter(TeamMembership.team_id == team_id).all()


def create_invite(
    db: Session,
    org_id: int,
    email: str,
    role: str = "USER",
    team_id: int = None,
    invited_by_user_id: int = None,
) -> OrgInvite:
    # Check max users per org
    max_users = getattr(settings, "MAX_USERS_PER_ORG", 100)
    current_count = db.query(User).filter(User.org_id == org_id, User.is_active == True).count()  # noqa: E712
    if current_count >= max_users:
        raise ValueError(f"Org user limit reached: {max_users}")

    # Check existing invite
    existing = db.query(OrgInvite).filter(OrgInvite.org_id == org_id, OrgInvite.email == email, OrgInvite.is_accepted == False).first()  # noqa: E712
    if existing:
        # If not expired, return existing
        if existing.expires_at and existing.expires_at > datetime.now(timezone.utc):
            return existing
        else:
            db.delete(existing)
            db.commit()

    token = OrgInvite.generate_token()
    expire_hours = getattr(settings, "INVITE_TOKEN_EXPIRE_HOURS", 72)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=expire_hours)

    invite = OrgInvite(
        org_id=org_id,
        email=email,
        role=role,
        team_id=team_id,
        token=token,
        invited_by_user_id=invited_by_user_id,
        expires_at=expires_at,
        is_accepted=False,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    # Try to send email if SMTP configured
    try:
        from app.services import user_service

        # We don't have email template, just log
        pass
    except Exception:
        pass

    return invite


def list_invites(db: Session, org_id: int) -> List[OrgInvite]:
    return db.query(OrgInvite).filter(OrgInvite.org_id == org_id).order_by(OrgInvite.created_at.desc()).all()


def accept_invite(db: Session, token: str, username: str, password: str) -> User:
    invite = db.query(OrgInvite).filter(OrgInvite.token == token).first()
    if not invite:
        raise ValueError("Invalid invite token")
    if invite.is_accepted:
        raise ValueError("Invite already accepted")
    if invite.expires_at < datetime.now(timezone.utc):
        raise ValueError("Invite expired")

    # Create user
    existing_user = db.query(User).filter(User.email == invite.email).first()
    if existing_user:
        raise ValueError("User with this email already exists")

    user = User(
        org_id=invite.org_id,
        username=username,
        password=get_password_hash(password),
        email=invite.email,
        role=invite.role,
        is_active=True,
    )
    db.add(user)
    db.flush()

    # Add to team if specified
    if invite.team_id:
        membership = TeamMembership(team_id=invite.team_id, user_id=user.id, role="member")
        db.add(membership)

    invite.is_accepted = True
    invite.accepted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


def revoke_invite(db: Session, org_id: int, invite_id: int) -> bool:
    invite = db.query(OrgInvite).filter(OrgInvite.id == invite_id, OrgInvite.org_id == org_id).first()
    if not invite:
        return False
    db.delete(invite)
    db.commit()
    return True


def serialize_team(t: Team) -> Dict[str, Any]:
    return {
        "id": t.id,
        "org_id": t.org_id,
        "name": t.name,
        "description": t.description,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def serialize_invite(i: OrgInvite) -> Dict[str, Any]:
    return {
        "id": i.id,
        "org_id": i.org_id,
        "email": i.email,
        "role": i.role,
        "team_id": i.team_id,
        "token": i.token[:8] + "..." if i.token else None,  # masked for list
        "is_accepted": i.is_accepted,
        "expires_at": i.expires_at.isoformat() if i.expires_at else None,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }
