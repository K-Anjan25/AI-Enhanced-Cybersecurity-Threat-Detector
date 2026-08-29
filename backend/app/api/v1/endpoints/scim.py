"""SCIM 2.0 provisioning endpoints — Users + Groups + Bulk (Phase 41).

Implements:
- ServiceProviderConfig, ResourceTypes, Schemas (unauthenticated)
- Users: list, create, get, update, patch, delete (Bearer auth)
- Groups: list, create, get, update, patch, delete with membership sync
- Bulk: POST /Bulk with operations (max 20)

Auth: Bearer token from ScimToken table (per-org) + fallback SCIM_TOKEN env var.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import require_role
from app.models import User
from app.services import scim_service

router = APIRouter(prefix="/scim/v2", tags=["SCIM"])


def _get_bearer_token(authorization: Optional[str] = Header(None)) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header — expected Bearer")
    return authorization[7:].strip()


def _verify_scim_auth(
    bearer: str,
    db: Session,
) -> tuple[Optional[int], Optional[int]]:
    result = scim_service.verify_scim_token(db, bearer)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid SCIM token")
    token_row, org_id = result
    token_id = token_row.id if token_row else None
    return token_id, org_id


# Discovery — no auth required per SCIM spec

@router.get("/ServiceProviderConfig")
def get_service_provider_config():
    return scim_service.service_provider_config()


@router.get("/ResourceTypes")
def get_resource_types():
    return scim_service.resource_types()


@router.get("/Schemas")
def get_schemas():
    return scim_service.schemas()


# Users

@router.get("/Users")
def list_users(
    request: Request,
    filter: Optional[str] = Query(None),
    startIndex: int = Query(1, ge=1),
    count: int = Query(100, ge=1, le=100),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    bearer = _get_bearer_token(authorization)
    _, org_id = _verify_scim_auth(bearer, db)
    return scim_service.list_users(db, org_id=org_id, filter_str=filter, start_index=startIndex, count=count)


@router.post("/Users", status_code=201)
def create_user(
    payload: dict,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    bearer = _get_bearer_token(authorization)
    _, org_id = _verify_scim_auth(bearer, db)
    try:
        return scim_service.create_user(db, org_id=org_id, payload=payload)
    except ValueError as exc:
        if "already exists" in str(exc).lower():
            raise HTTPException(status_code=409, detail=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/Users/{user_id}")
def get_user(
    user_id: int,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    bearer = _get_bearer_token(authorization)
    _, org_id = _verify_scim_auth(bearer, db)
    try:
        return scim_service.get_user(db, org_id=org_id, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/Users/{user_id}")
def update_user(
    user_id: int,
    payload: dict,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    bearer = _get_bearer_token(authorization)
    _, org_id = _verify_scim_auth(bearer, db)
    try:
        return scim_service.update_user(db, org_id=org_id, user_id=user_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/Users/{user_id}")
def patch_user(
    user_id: int,
    payload: dict,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    bearer = _get_bearer_token(authorization)
    _, org_id = _verify_scim_auth(bearer, db)
    try:
        return scim_service.patch_user(db, org_id=org_id, user_id=user_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/Users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    bearer = _get_bearer_token(authorization)
    _, org_id = _verify_scim_auth(bearer, db)
    try:
        scim_service.delete_user(db, org_id=org_id, user_id=user_id)
        return Response(status_code=204)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# Groups — Phase 41 membership sync

@router.get("/Groups")
def list_groups(
    filter: Optional[str] = Query(None),
    startIndex: int = Query(1, ge=1),
    count: int = Query(100, ge=1, le=100),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    bearer = _get_bearer_token(authorization)
    _, org_id = _verify_scim_auth(bearer, db)
    return scim_service.list_groups(db, org_id=org_id, filter_str=filter, start_index=startIndex, count=count)


@router.post("/Groups", status_code=201)
def create_group(
    payload: dict,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    bearer = _get_bearer_token(authorization)
    _, org_id = _verify_scim_auth(bearer, db)
    try:
        return scim_service.create_group(db, org_id=org_id, payload=payload)
    except ValueError as exc:
        if "already exists" in str(exc).lower():
            raise HTTPException(status_code=409, detail=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/Groups/{group_id}")
def get_group(
    group_id: int,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    bearer = _get_bearer_token(authorization)
    _, org_id = _verify_scim_auth(bearer, db)
    try:
        return scim_service.get_group(db, org_id=org_id, group_id=group_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/Groups/{group_id}")
def update_group(
    group_id: int,
    payload: dict,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    bearer = _get_bearer_token(authorization)
    _, org_id = _verify_scim_auth(bearer, db)
    try:
        return scim_service.update_group(db, org_id=org_id, group_id=group_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/Groups/{group_id}")
def patch_group(
    group_id: int,
    payload: dict,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    bearer = _get_bearer_token(authorization)
    _, org_id = _verify_scim_auth(bearer, db)
    try:
        return scim_service.patch_group(db, org_id=org_id, group_id=group_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/Groups/{group_id}", status_code=204)
def delete_group(
    group_id: int,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    bearer = _get_bearer_token(authorization)
    _, org_id = _verify_scim_auth(bearer, db)
    try:
        scim_service.delete_group(db, org_id=org_id, group_id=group_id)
        return Response(status_code=204)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# Bulk — Phase 41

@router.post("/Bulk")
def bulk_operations(
    payload: dict,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    bearer = _get_bearer_token(authorization)
    _, org_id = _verify_scim_auth(bearer, db)
    try:
        return scim_service.handle_bulk(db, org_id=org_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# Admin endpoints for SCIM token management

admin_router = APIRouter(prefix="/admin/scim", tags=["SCIM Admin"])


@admin_router.get("/tokens")
def list_tokens(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    return {"data": scim_service.list_scim_tokens(db, org_id=current_user.org_id)}


@admin_router.post("/tokens")
def create_token(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    name = payload.get("name") or "SCIM Provisioning Token"
    row, raw = scim_service.create_scim_token(
        db, org_id=current_user.org_id, name=name, created_by=current_user.username
    )
    return {
        "id": row.id,
        "name": row.name,
        "prefix": row.token_prefix,
        "token": raw,
        "message": "Token created — copy it now, it will not be shown again",
    }


@admin_router.delete("/tokens/{token_id}")
def delete_token(
    token_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    try:
        return scim_service.delete_scim_token(db, org_id=current_user.org_id, token_id=token_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# Groups → Roles mapping admin endpoints (Phase 43)


@admin_router.get("/groups/role-mappings")
def list_group_role_mappings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    return {"data": scim_service.get_group_role_mappings(db, org_id=current_user.org_id)}


@admin_router.post("/groups/role-mappings")
def upsert_group_role_mapping(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    group_name = payload.get("group_display_name") or payload.get("displayName") or payload.get("group")
    role = payload.get("role")
    if not group_name or not role:
        raise HTTPException(status_code=422, detail="group_display_name and role required")
    try:
        return scim_service.set_group_role_mapping(
            db, org_id=current_user.org_id, group_display_name=group_name, role=role
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@admin_router.delete("/groups/role-mappings/{mapping_id}")
def delete_group_role_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("ADMIN")),
):
    try:
        return scim_service.delete_group_role_mapping(db, org_id=current_user.org_id, mapping_id=mapping_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
