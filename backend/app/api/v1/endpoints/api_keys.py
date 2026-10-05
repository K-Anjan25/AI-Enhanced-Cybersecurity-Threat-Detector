"""API key management endpoints (FR-44, T-313).

Four routes, and the shape of the create response is the acceptance criterion.
``POST`` mints a key and returns it in :class:`ApiKeyIssuedOut`; the listing and
every other response use :class:`ApiKeyOut`, which has no field for a secret.
There is no route that re-reads one, and none could: only the digest is stored.

**Where a key is used.** Not here. A key authenticates *other* routes -- the
ingest writes (``Scope.ingest_write``) and the alert list (``Scope.alerts_read``)
-- by appearing in ``X-API-Key`` or as a Bearer token shaped like one, and
``app.auth.rbac`` resolves it. This module is only how a key comes to exist and
to stop existing.

**Revocation is immediate and idempotent.** ``DELETE`` sets ``revoked_at``; the
next request that presents the key is refused because verification reads the
store every time and refuses a record with ``revoked_at`` set. Revoking twice
keeps the first timestamp, because the fact being recorded is when the credential
stopped working.

**Why the delete is not a delete.** The row survives: it is the record of a
credential having existed, and an operator asking "was this key revoked, and
when" cannot ask a row that is gone.

**What is recorded.** Issue and revoke both append to the audit trail: the key's
id, its name and its scopes, never the secret -- which does not exist anywhere
after the response leaves this process.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.v1.deps import api_key_digest, api_key_store, audit_trail, client_ip
from app.auth.api_keys import ApiKeyRecord, Scope
from app.auth.api_keys import issue_key as mint_key
from app.auth.api_keys import revoke_key as drop_key
from app.auth.rbac import SCOPE_CAPABILITIES, Capability, Principal, require
from app.schemas.api_key import (
    ApiKeyCreate,
    ApiKeyIssuedOut,
    ApiKeyListOut,
    ApiKeyOut,
    ScopeListOut,
    ScopeOut,
)
from app.services.audit_log import AuditAction, record_action

router = APIRouter(prefix="/api/v1/keys", tags=["api-keys"])


def _out(record: ApiKeyRecord) -> ApiKeyOut:
    """Serialise a key record **without** any secret. There is none to include."""
    return ApiKeyOut(
        id=record.id,
        name=record.name,
        prefix=record.prefix,
        owner=record.owner,
        scopes=[scope.value for scope in sorted(record.scopes, key=str)],
        created_at=record.created_at,
        last_used_at=record.last_used_at,
        revoked_at=record.revoked_at,
    )


@router.get(
    "",
    response_model=ApiKeyListOut,
    summary="List API keys (FR-44)",
)
def list_keys(
    request: Request,
    _caller: Annotated[Principal, require(Capability.API_KEYS)],
) -> ApiKeyListOut:
    """Every key, revoked ones included: the list is the record, not the live set."""
    store = api_key_store(request)
    return ApiKeyListOut(items=[_out(record) for record in store.list()])


@router.post(
    "",
    response_model=ApiKeyIssuedOut,
    status_code=status.HTTP_201_CREATED,
    summary="Issue an API key (FR-44)",
)
def create_key(
    body: ApiKeyCreate,
    request: Request,
    response: Response,
    caller: Annotated[Principal, require(Capability.API_KEYS)],
) -> ApiKeyIssuedOut:
    """Issue a key and return its secret, which is never readable again.

    Raises:
        HTTPException: 400 when a scope is unknown, naming the allowed set. The
            message is about the request, never about the key that was minted.
    """
    try:
        scopes = frozenset(Scope(name.strip()) for name in body.scopes)
    except ValueError as exc:
        allowed = ", ".join(sorted(scope.value for scope in Scope))
        raise HTTPException(
            status_code=400, detail=f"unknown scope; allowed scopes are: {allowed}"
        ) from exc
    if not scopes:
        # Pydantic's min_length already refuses an empty list; this is the belt
        # for a caller that reaches the function another way.
        raise HTTPException(status_code=400, detail="at least one scope is required")

    store = api_key_store(request)
    try:
        issued = mint_key(
            store,
            api_key_digest(request),
            name=body.name.strip(),
            # The key belongs to the admin who issued it. The numeric users.id is
            # the persistent adapter's mapping (D-038); until then the subject
            # string is what the record carries, and it is the same string the
            # audit trail attributes the action to.
            owner=caller.subject,
            scopes=scopes,
            at=datetime.now(UTC),
        )
    except ValueError as exc:
        # A name that is blank once stripped, or a timestamp that cannot make a
        # record. The message names the field and never the key: nothing has been
        # minted yet, and the reason is about the request.
        raise HTTPException(status_code=400, detail=f"key refused: {exc}") from exc

    record_action(
        audit_trail(request),
        action=AuditAction.key_create,
        actor=caller.subject,
        target_type="api_key",
        target_id=str(issued.record.id),
        at=datetime.now(UTC),
        # The name and the scopes, never the key and never the digest. The trail
        # is readable by every role (T-312) while key management is admin-only:
        # a key's material recorded here would outlive the revocation that was
        # supposed to end it.
        detail={"name": issued.record.name, "scopes": sorted(scope.value for scope in scopes)},
        ip=client_ip(request),
    )
    response.headers["Location"] = f"/api/v1/keys/{issued.record.id}"
    return ApiKeyIssuedOut(**_out(issued.record).model_dump(), secret=issued.secret)


@router.get(
    "/scopes",
    response_model=ScopeListOut,
    summary="List the scopes a key may hold (FR-44)",
)
def list_scopes(
    _caller: Annotated[Principal, require(Capability.API_KEYS)],
) -> ScopeListOut:
    """What ``scopes`` accepts, and what each one grants.

    Read from the same table the authorisation path consults, so a screen built
    from this cannot offer a scope that would be refused at issue time -- the two
    answers come from one source. Declared before the ``{key_id}`` route so
    "scopes" is never read as an id.
    """
    return ScopeListOut(
        items=[
            ScopeOut(
                name=scope.value,
                capabilities=sorted(capability.value for capability in SCOPE_CAPABILITIES[scope]),
            )
            for scope in Scope
        ]
    )


@router.delete(
    "/{key_id}",
    response_model=ApiKeyOut,
    summary="Revoke an API key (FR-44)",
)
def revoke_key(
    key_id: int,
    request: Request,
    caller: Annotated[Principal, require(Capability.API_KEYS)],
) -> ApiKeyOut:
    """Revoke a key. The next request that presents it is refused.

    The response is the revoked row rather than 204: an operator needs the
    timestamp, and returning the record makes the change visible without a
    follow-up read.

    Raises:
        HTTPException: 404 when no such key exists. 409 is deliberately not used
            for an already-revoked key: revocation is a state, not a step, and a
            repeated call reporting success is the honest answer.
    """
    store = api_key_store(request)
    existing = store.get(key_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="no such API key")
    record = drop_key(store, key_id, at=datetime.now(UTC))
    if record is None:  # pragma: no cover - unreachable: the row was just read
        raise HTTPException(status_code=404, detail="no such API key")
    if existing.revoked_at is None:
        # Only the transition is audited. A repeated revoke changes nothing, and
        # a trail that logs non-events is a trail nobody reads.
        record_action(
            audit_trail(request),
            action=AuditAction.key_revoke,
            actor=caller.subject,
            target_type="api_key",
            target_id=str(record.id),
            at=datetime.now(UTC),
            detail={"name": record.name},
            ip=client_ip(request),
        )
    return _out(record)
