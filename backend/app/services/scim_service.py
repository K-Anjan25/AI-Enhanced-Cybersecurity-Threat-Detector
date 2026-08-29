"""SCIM 2.0 provisioning — Users + Groups minimal.

Implements:
- ServiceProviderConfig, ResourceTypes, Schemas (discovery)
- Users: GET /Users, POST /Users, GET /Users/{id}, PUT /Users/{id}, PATCH /Users/{id}, DELETE /Users/{id}
- Groups: GET /Groups (minimal list)

Auth: Bearer token hashed at rest in ScimToken table, plus fallback SCIM_TOKEN env var.
Tokens are per-org, so a token from org A cannot provision users in org B.

Honest gaps:
- Filtering is limited to userName and email eq, not full SCIM filter grammar
- Groups membership update not implemented (returns empty members)
- Bulk extension not implemented
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Org, User
from app.models.sso import ScimToken
from app.core.security import get_password_hash

_LOGGER = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_scim_token(
    db: Session,
    org_id: int | None,
    name: str = "SCIM Provisioning Token",
    created_by: str | None = None,
) -> tuple[ScimToken, str]:
    """Create a token, return (row, raw_token). Raw token shown once."""
    raw = f"scim_{secrets.token_urlsafe(32)}"
    token_hash = hash_token(raw)
    prefix = raw[:8]

    row = ScimToken(
        org_id=org_id,
        token_hash=token_hash,
        token_prefix=prefix,
        name=name,
        created_by=created_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, raw


def verify_scim_token(db: Session, bearer: str) -> tuple[ScimToken, int | None] | None:
    """Verify Bearer token, return (token_row, org_id) or None."""
    if not bearer:
        return None

    # Fallback global token from env
    if settings.SCIM_TOKEN and secrets.compare_digest(bearer, settings.SCIM_TOKEN):
        # Global token -> default org
        default_org = db.query(Org).filter(Org.slug == "default").first()
        # Create a synthetic token row for audit? No, return None token but org
        # For simplicity, return a dummy with org_id = default_org.id
        return None, (default_org.id if default_org else None)

    h = hash_token(bearer)
    row = db.query(ScimToken).filter(ScimToken.token_hash == h, ScimToken.is_active.is_(True)).first()
    if not row:
        return None
    # Check expiry
    if row.expires_at and row.expires_at < _now():
        return None
    # Update last used
    row.last_used_at = _now()
    db.commit()
    return row, row.org_id


def list_scim_tokens(db: Session, org_id: int | None) -> List[Dict[str, Any]]:
    q = db.query(ScimToken)
    if org_id is not None:
        q = q.filter(ScimToken.org_id == org_id)
    rows = q.order_by(ScimToken.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "prefix": r.token_prefix,
            "created_by": r.created_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
            "is_active": r.is_active,
        }
        for r in rows
    ]


def delete_scim_token(db: Session, org_id: int | None, token_id: int) -> dict:
    q = db.query(ScimToken).filter(ScimToken.id == token_id)
    if org_id is not None:
        q = q.filter(ScimToken.org_id == org_id)
    row = q.first()
    if not row:
        raise ValueError("Token not found")
    db.delete(row)
    db.commit()
    return {"deleted": token_id}


# SCIM serialization

def _scim_user_from_model(u: User) -> dict:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id": str(u.id),
        "userName": u.username,
        "externalId": u.scim_external_id or u.external_id,
        "name": {
            "givenName": u.username,
            "familyName": "",
        },
        "emails": [{"value": u.email, "primary": True}],
        "active": bool(u.is_active and not u.is_blocked),
        "meta": {
            "resourceType": "User",
            "created": u.created_at.isoformat() if u.created_at else None,
            "location": f"/scim/v2/Users/{u.id}",
        },
        "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
            "department": u.department,
        },
        "groups": [],
        "roles": [{"value": u.role}],
    }


def list_users(
    db: Session,
    org_id: int | None,
    filter_str: str | None = None,
    start_index: int = 1,
    count: int = 100,
) -> dict:
    q = db.query(User)
    if org_id is not None:
        q = q.filter(User.org_id == org_id)

    # Very limited filter parsing: userName eq "xxx" or emails.value eq "xxx"
    if filter_str:
        f = filter_str.strip()
        # userName eq "bob"
        if "userName" in f and "eq" in f:
            try:
                val = f.split('"')[1]
                q = q.filter(User.username == val)
            except Exception:
                pass
        elif "emails" in f and "eq" in f:
            try:
                val = f.split('"')[1]
                q = q.filter(User.email == val)
            except Exception:
                pass
        elif "externalId" in f and "eq" in f:
            try:
                val = f.split('"')[1]
                q = q.filter((User.scim_external_id == val) | (User.external_id == val))
            except Exception:
                pass

    total = q.count()
    users = q.offset(max(0, start_index - 1)).limit(min(count, 100)).all()

    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": total,
        "startIndex": start_index,
        "itemsPerPage": len(users),
        "Resources": [_scim_user_from_model(u) for u in users],
    }


def get_user(db: Session, org_id: int | None, user_id: int) -> dict:
    q = db.query(User).filter(User.id == user_id)
    if org_id is not None:
        q = q.filter(User.org_id == org_id)
    u = q.first()
    if not u:
        raise ValueError("User not found")
    return _scim_user_from_model(u)


def create_user(db: Session, org_id: int | None, payload: dict) -> dict:
    user_name = payload.get("userName")
    if not user_name:
        raise ValueError("userName is required")

    emails = payload.get("emails") or []
    email = None
    if emails:
        email = emails[0].get("value") if isinstance(emails[0], dict) else emails[0]

    if not email:
        email = payload.get("email")

    if not email:
        raise ValueError("email is required")

    external_id = payload.get("externalId")

    # Check existing
    existing = db.query(User).filter((User.username == user_name) | (User.email == email)).first()
    if existing:
        raise ValueError("User already exists")

    # Determine org
    if org_id is None:
        default_org = db.query(Org).filter(Org.slug == "default").first()
        if default_org is None:
            default_org = Org(name="Default Organization", slug="default")
            db.add(default_org)
            db.flush()
        org_id = default_org.id

    # Roles
    roles = payload.get("roles") or []
    role = "USER"
    if roles:
        r = roles[0].get("value") if isinstance(roles[0], dict) else roles[0]
        if r and str(r).upper() in ("USER", "ANALYST", "ADMIN"):
            role = str(r).upper()

    # Active
    active = payload.get("active", True)

    user = User(
        username=user_name,
        email=email,
        password=get_password_hash(secrets.token_urlsafe(16)),
        role=role,
        org_id=org_id,
        scim_external_id=external_id,
        is_active=bool(active),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _scim_user_from_model(user)


def update_user(db: Session, org_id: int | None, user_id: int, payload: dict) -> dict:
    q = db.query(User).filter(User.id == user_id)
    if org_id is not None:
        q = q.filter(User.org_id == org_id)
    u = q.first()
    if not u:
        raise ValueError("User not found")

    if "userName" in payload:
        u.username = payload["userName"]
    if "externalId" in payload:
        u.scim_external_id = payload["externalId"]
    if "active" in payload:
        u.is_active = bool(payload["active"])
    if "emails" in payload:
        emails = payload["emails"]
        if emails and isinstance(emails[0], dict):
            u.email = emails[0].get("value") or u.email

    # Enterprise extension
    ent = payload.get("urn:ietf:params:scim:schemas:extension:enterprise:2.0:User")
    if ent and isinstance(ent, dict) and "department" in ent:
        u.department = ent["department"]

    db.commit()
    db.refresh(u)
    return _scim_user_from_model(u)


def patch_user(db: Session, org_id: int | None, user_id: int, payload: dict) -> dict:
    # SCIM PATCH is complex; implement minimal active + userName
    q = db.query(User).filter(User.id == user_id)
    if org_id is not None:
        q = q.filter(User.org_id == org_id)
    u = q.first()
    if not u:
        raise ValueError("User not found")

    ops = payload.get("Operations") or []
    for op in ops:
        path = (op.get("path") or "").lower()
        value = op.get("value")
        if path == "active":
            u.is_active = bool(value)
        elif "username" in path:
            if isinstance(value, str):
                u.username = value
        elif "emails" in path:
            if isinstance(value, list) and value and isinstance(value[0], dict):
                u.email = value[0].get("value") or u.email

    db.commit()
    db.refresh(u)
    return _scim_user_from_model(u)


def delete_user(db: Session, org_id: int | None, user_id: int) -> None:
    q = db.query(User).filter(User.id == user_id)
    if org_id is not None:
        q = q.filter(User.org_id == org_id)
    u = q.first()
    if not u:
        raise ValueError("User not found")
    # Soft delete: deactivate
    u.is_active = False
    db.commit()


# Discovery

def service_provider_config() -> dict:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "documentationUri": "https://www.rfc-editor.org/rfc/rfc7644",
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": 100},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [
            {
                "type": "oauthbearertoken",
                "name": "OAuth Bearer Token",
                "description": "SCIM Bearer token",
                "specUri": "https://www.rfc-editor.org/rfc/rfc6750",
            }
        ],
    }


def resource_types() -> dict:
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": 2,
        "Resources": [
            {
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"],
                "id": "User",
                "name": "User",
                "endpoint": "/Users",
                "description": "User Account",
                "schema": "urn:ietf:params:scim:schemas:core:2.0:User",
                "schemaExtensions": [
                    {
                        "schema": "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User",
                        "required": False,
                    }
                ],
            },
            {
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"],
                "id": "Group",
                "name": "Group",
                "endpoint": "/Groups",
                "description": "Group",
                "schema": "urn:ietf:params:scim:schemas:core:2.0:Group",
            },
        ],
    }


def schemas() -> dict:
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": 2,
        "Resources": [
            {
                "id": "urn:ietf:params:scim:schemas:core:2.0:User",
                "name": "User",
                "description": "User Account",
            },
            {
                "id": "urn:ietf:params:scim:schemas:core:2.0:Group",
                "name": "Group",
                "description": "Group",
            },
        ],
    }


def list_groups(org_id: int | None) -> dict:
    # Minimal: return empty list, groups not yet implemented
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": 0,
        "startIndex": 1,
        "itemsPerPage": 0,
        "Resources": [],
    }
