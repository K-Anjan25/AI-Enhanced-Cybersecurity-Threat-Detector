"""SCIM 2.0 provisioning — Users + Groups + Bulk.

Phase 40: Users minimal, Groups list empty
Phase 41: Groups CRUD + membership sync, Bulk extension

Implements:
- ServiceProviderConfig, ResourceTypes, Schemas (discovery)
- Users: GET /Users, POST /Users, GET /Users/{id}, PUT /Users/{id}, PATCH /Users/{id}, DELETE /Users/{id}
- Groups: GET /Groups, POST /Groups, GET /Groups/{id}, PUT /Groups/{id}, PATCH /Groups/{id}, DELETE /Groups/{id} with membership sync
- Bulk: POST /Bulk with operations

Auth: Bearer token hashed at rest in ScimToken table, plus fallback SCIM_TOKEN env var.
Tokens are per-org, so a token from org A cannot provision users in org B.

Honest gaps:
- Filtering limited to userName/email/externalId/displayName eq, not full SCIM filter grammar
- Bulk supports max 20 ops, fails fast on first error if failOnErrors >0
- Groups members are User ids, role mapping to NOCTRA roles not automatic (manual via User role)
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
from app.models.sso import ScimToken, ScimGroup
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

    if settings.SCIM_TOKEN and secrets.compare_digest(bearer, settings.SCIM_TOKEN):
        default_org = db.query(Org).filter(Org.slug == "default").first()
        return None, (default_org.id if default_org else None)

    h = hash_token(bearer)
    row = db.query(ScimToken).filter(ScimToken.token_hash == h, ScimToken.is_active.is_(True)).first()
    if not row:
        return None
    if row.expires_at and row.expires_at < _now():
        return None
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


# SCIM User serialization

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

    if filter_str:
        f = filter_str.strip()
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

    existing = db.query(User).filter((User.username == user_name) | (User.email == email)).first()
    if existing:
        raise ValueError("User already exists")

    if org_id is None:
        default_org = db.query(Org).filter(Org.slug == "default").first()
        if default_org is None:
            default_org = Org(name="Default Organization", slug="default")
            db.add(default_org)
            db.flush()
        org_id = default_org.id

    roles = payload.get("roles") or []
    role = "USER"
    if roles:
        r = roles[0].get("value") if isinstance(roles[0], dict) else roles[0]
        if r and str(r).upper() in ("USER", "ANALYST", "ADMIN"):
            role = str(r).upper()

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

    ent = payload.get("urn:ietf:params:scim:schemas:extension:enterprise:2.0:User")
    if ent and isinstance(ent, dict) and "department" in ent:
        u.department = ent["department"]

    db.commit()
    db.refresh(u)
    return _scim_user_from_model(u)


def patch_user(db: Session, org_id: int | None, user_id: int, payload: dict) -> dict:
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
    u.is_active = False
    db.commit()


# SCIM Group handling — Phase 41

def _scim_group_from_model(g: ScimGroup, db: Session | None = None) -> dict:
    members = g.members or []
    # Enrich with display if db available
    if db and members:
        user_ids = []
        for m in members:
            try:
                user_ids.append(int(m.get("value"))) if isinstance(m, dict) else None
            except Exception:
                pass
        if user_ids:
            users = db.query(User).filter(User.id.in_(user_ids)).all()
            user_map = {str(u.id): u.username for u in users}
            enriched = []
            for m in members:
                if isinstance(m, dict):
                    val = str(m.get("value"))
                    enriched.append({
                        "value": val,
                        "display": user_map.get(val, m.get("display", "")),
                        "$ref": f"/scim/v2/Users/{val}",
                    })
                else:
                    enriched.append(m)
            members = enriched

    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
        "id": str(g.id),
        "displayName": g.display_name,
        "externalId": g.external_id,
        "members": members,
        "meta": {
            "resourceType": "Group",
            "created": g.created_at.isoformat() if g.created_at else None,
            "location": f"/scim/v2/Groups/{g.id}",
        },
    }


def list_groups(
    db: Session,
    org_id: int | None,
    filter_str: str | None = None,
    start_index: int = 1,
    count: int = 100,
) -> dict:
    q = db.query(ScimGroup)
    if org_id is not None:
        q = q.filter(ScimGroup.org_id == org_id)

    if filter_str:
        f = filter_str.strip()
        if "displayName" in f and "eq" in f:
            try:
                val = f.split('"')[1]
                q = q.filter(ScimGroup.display_name == val)
            except Exception:
                pass
        elif "externalId" in f and "eq" in f:
            try:
                val = f.split('"')[1]
                q = q.filter(ScimGroup.external_id == val)
            except Exception:
                pass

    total = q.count()
    groups = q.offset(max(0, start_index - 1)).limit(min(count, 100)).all()

    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": total,
        "startIndex": start_index,
        "itemsPerPage": len(groups),
        "Resources": [_scim_group_from_model(g, db) for g in groups],
    }


def get_group(db: Session, org_id: int | None, group_id: int) -> dict:
    q = db.query(ScimGroup).filter(ScimGroup.id == group_id)
    if org_id is not None:
        q = q.filter(ScimGroup.org_id == org_id)
    g = q.first()
    if not g:
        raise ValueError("Group not found")
    return _scim_group_from_model(g, db)


def create_group(db: Session, org_id: int | None, payload: dict) -> dict:
    display_name = payload.get("displayName")
    if not display_name:
        raise ValueError("displayName is required")

    external_id = payload.get("externalId")

    existing = db.query(ScimGroup).filter(ScimGroup.display_name == display_name)
    if org_id is not None:
        existing = existing.filter(ScimGroup.org_id == org_id)
    if existing.first():
        raise ValueError("Group already exists")

    if org_id is None:
        default_org = db.query(Org).filter(Org.slug == "default").first()
        if default_org is None:
            default_org = Org(name="Default Organization", slug="default")
            db.add(default_org)
            db.flush()
        org_id = default_org.id

    members = payload.get("members") or []
    # Validate members exist
    valid_members = []
    for m in members:
        if isinstance(m, dict) and m.get("value"):
            try:
                uid = int(m["value"])
                u = db.query(User).filter(User.id == uid).first()
                if u:
                    valid_members.append({"value": str(uid), "display": u.username})
            except Exception:
                pass

    group = ScimGroup(
        display_name=display_name,
        external_id=external_id,
        org_id=org_id,
        members=valid_members,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return _scim_group_from_model(group, db)


def update_group(db: Session, org_id: int | None, group_id: int, payload: dict) -> dict:
    q = db.query(ScimGroup).filter(ScimGroup.id == group_id)
    if org_id is not None:
        q = q.filter(ScimGroup.org_id == org_id)
    g = q.first()
    if not g:
        raise ValueError("Group not found")

    if "displayName" in payload:
        g.display_name = payload["displayName"]
    if "externalId" in payload:
        g.external_id = payload["externalId"]
    if "members" in payload:
        members = payload["members"] or []
        valid_members = []
        for m in members:
            if isinstance(m, dict) and m.get("value"):
                try:
                    uid = int(m["value"])
                    u = db.query(User).filter(User.id == uid).first()
                    if u:
                        valid_members.append({"value": str(uid), "display": u.username})
                except Exception:
                    pass
        g.members = valid_members

    db.commit()
    db.refresh(g)
    return _scim_group_from_model(g, db)


def patch_group(db: Session, org_id: int | None, group_id: int, payload: dict) -> dict:
    q = db.query(ScimGroup).filter(ScimGroup.id == group_id)
    if org_id is not None:
        q = q.filter(ScimGroup.org_id == org_id)
    g = q.first()
    if not g:
        raise ValueError("Group not found")

    ops = payload.get("Operations") or []
    current_members = list(g.members or [])

    for op in ops:
        op_type = (op.get("op") or "").lower()
        path = (op.get("path") or "").lower()
        value = op.get("value")

        if "members" in path:
            if op_type == "add":
                # Add members
                to_add = value if isinstance(value, list) else [value] if value else []
                for m in to_add:
                    if isinstance(m, dict) and m.get("value"):
                        try:
                            uid = int(m["value"])
                            if not any(str(uid) == str(cm.get("value")) for cm in current_members if isinstance(cm, dict)):
                                u = db.query(User).filter(User.id == uid).first()
                                if u:
                                    current_members.append({"value": str(uid), "display": u.username})
                        except Exception:
                            pass
            elif op_type == "remove":
                # Remove members — value may be filter or list
                if isinstance(value, dict) and "value" in value:
                    # {"value": "123"}
                    rem_id = str(value["value"])
                    current_members = [cm for cm in current_members if not (isinstance(cm, dict) and str(cm.get("value")) == rem_id)]
                elif isinstance(value, list):
                    rem_ids = {str(m.get("value")) for m in value if isinstance(m, dict) and m.get("value")}
                    current_members = [cm for cm in current_members if not (isinstance(cm, dict) and str(cm.get("value")) in rem_ids)]
                else:
                    # No value means remove all? Per spec, if path is members and no value, remove all
                    current_members = []
            elif op_type == "replace":
                # Replace all members
                if isinstance(value, list):
                    new_members = []
                    for m in value:
                        if isinstance(m, dict) and m.get("value"):
                            try:
                                uid = int(m["value"])
                                u = db.query(User).filter(User.id == uid).first()
                                if u:
                                    new_members.append({"value": str(uid), "display": u.username})
                            except Exception:
                                pass
                    current_members = new_members

    g.members = current_members
    db.commit()
    db.refresh(g)
    return _scim_group_from_model(g, db)


def delete_group(db: Session, org_id: int | None, group_id: int) -> None:
    q = db.query(ScimGroup).filter(ScimGroup.id == group_id)
    if org_id is not None:
        q = q.filter(ScimGroup.org_id == org_id)
    g = q.first()
    if not g:
        raise ValueError("Group not found")
    db.delete(g)
    db.commit()


# Bulk — Phase 41

def handle_bulk(
    db: Session,
    org_id: int | None,
    payload: dict,
) -> dict:
    """Handle SCIM Bulk request — processes Operations array."""
    operations = payload.get("Operations") or []
    fail_on_errors = payload.get("failOnErrors")
    if fail_on_errors is None:
        fail_on_errors = 1

    if len(operations) > 20:
        raise ValueError("Bulk supports max 20 operations")

    results = []
    errors = 0

    for op in operations:
        method = (op.get("method") or "").upper()
        path = op.get("path") or ""
        bulk_id = op.get("bulkId")
        data = op.get("data") or {}
        op_id = op.get("bulkId") or f"op-{len(results)+1}"

        try:
            if method == "POST" and "/Users" in path:
                created = create_user(db, org_id=org_id, payload=data)
                results.append({
                    "method": method,
                    "bulkId": bulk_id,
                    "location": f"/scim/v2/Users/{created['id']}",
                    "status": {"code": "201"},
                    "response": created,
                })
            elif method == "POST" and "/Groups" in path:
                created = create_group(db, org_id=org_id, payload=data)
                results.append({
                    "method": method,
                    "bulkId": bulk_id,
                    "location": f"/scim/v2/Groups/{created['id']}",
                    "status": {"code": "201"},
                    "response": created,
                })
            elif method == "PUT" and "/Users/" in path:
                # Extract id from path /Users/{id}
                try:
                    uid = int(path.split("/")[-1])
                    updated = update_user(db, org_id=org_id, user_id=uid, payload=data)
                    results.append({
                        "method": method,
                        "bulkId": bulk_id,
                        "location": f"/scim/v2/Users/{uid}",
                        "status": {"code": "200"},
                        "response": updated,
                    })
                except ValueError as ve:
                    raise ve
                except Exception:
                    raise ValueError("Invalid User ID in path")
            elif method == "PATCH" and "/Users/" in path:
                try:
                    uid = int(path.split("/")[-1])
                    patched = patch_user(db, org_id=org_id, user_id=uid, payload=data)
                    results.append({
                        "method": method,
                        "bulkId": bulk_id,
                        "location": f"/scim/v2/Users/{uid}",
                        "status": {"code": "200"},
                        "response": patched,
                    })
                except Exception:
                    raise ValueError("Invalid User ID in path")
            elif method == "DELETE" and "/Users/" in path:
                try:
                    uid = int(path.split("/")[-1])
                    delete_user(db, org_id=org_id, user_id=uid)
                    results.append({
                        "method": method,
                        "bulkId": bulk_id,
                        "status": {"code": "204"},
                    })
                except Exception:
                    raise ValueError("Invalid User ID in path")
            elif method == "DELETE" and "/Groups/" in path:
                try:
                    gid = int(path.split("/")[-1])
                    delete_group(db, org_id=org_id, group_id=gid)
                    results.append({
                        "method": method,
                        "bulkId": bulk_id,
                        "status": {"code": "204"},
                    })
                except Exception:
                    raise ValueError("Invalid Group ID in path")
            else:
                raise ValueError(f"Unsupported bulk operation: {method} {path}")
        except Exception as exc:
            errors += 1
            results.append({
                "method": method,
                "bulkId": bulk_id,
                "status": {"code": "400" if "not found" not in str(exc).lower() else "404"},
                "response": {
                    "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
                    "detail": str(exc),
                    "status": "400",
                },
            })
            if fail_on_errors and errors >= fail_on_errors:
                break

    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:BulkResponse"],
        "Operations": results,
    }


# Discovery

def service_provider_config() -> dict:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "documentationUri": "https://www.rfc-editor.org/rfc/rfc7644",
        "patch": {"supported": True},
        "bulk": {"supported": True, "maxOperations": 20, "maxPayloadSize": 1048576},
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
