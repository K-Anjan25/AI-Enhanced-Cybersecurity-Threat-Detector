"""Webhook configuration endpoints (FR-21, R-55, T-311).

Registering a target is where R-55 is enforced, and it is enforced *here* rather
than at delivery time: a URL that fails the allowlist or resolves into a private
range is refused when an operator submits it, with the reason, instead of every
alert after a breach quietly failing to leave the building. The validation is
the same function the delivery path would call, so there is one definition of
"may we send this".

Reading configuration needs the same capability as writing it (R-53 puts webhook
config at responder and above) -- a target's URL names internal infrastructure,
so a viewer has no more business reading the list than changing it.

Rate limiting the write endpoint is R-56 and belongs to T-316; recorded there
rather than half-done here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.v1.deps import audit_trail, client_ip
from app.auth.rbac import Capability, Principal, require
from app.schemas.webhook import WebhookCreate, WebhookCreatedOut, WebhookListOut, WebhookOut
from app.services.audit_log import AuditAction, record_action
from app.services.correlator import Severity
from app.services.webhook_targets import (
    BlockedTarget,
    SecretVault,
    WebhookStore,
    WebhookTarget,
    resolve_host,
    validate_webhook_url,
)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


def _store(request: Request) -> WebhookStore:
    """The configured targets, from application state."""
    store: WebhookStore | None = getattr(request.app.state, "webhook_store", None)
    if store is None:
        msg = "webhook_store is not configured on app.state"
        raise RuntimeError(msg)
    return store


def _vault(request: Request) -> SecretVault:
    """The secret sealing key, from application state."""
    vault: SecretVault | None = getattr(request.app.state, "secret_vault", None)
    if vault is None:
        msg = "secret_vault is not configured on app.state"
        raise RuntimeError(msg)
    return vault


def _allowlist(request: Request) -> tuple[str, ...]:
    """The permitted webhook hosts, parsed at startup (R-55)."""
    return tuple(getattr(request.app.state, "webhook_allowlist", ()))


def _resolver(request: Request) -> Callable[[str, int], Sequence[str]]:
    """The DNS lookup, from application state so a test can pin it."""
    resolver: Callable[[str, int], Sequence[str]] = getattr(
        request.app.state, "webhook_resolver", resolve_host
    )
    return resolver


def _out(target: WebhookTarget) -> WebhookOut:
    """Serialise a target **without** its secret."""
    return WebhookOut(
        id=target.id,
        url=target.url,
        description=target.description,
        severity_floor=target.severity_floor.value,
        active=target.active,
        created_at=target.created_at,
    )


@router.post(
    "",
    response_model=WebhookCreatedOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register an outbound webhook (FR-21)",
)
def create_webhook(
    body: WebhookCreate,
    request: Request,
    response: Response,
    caller: Annotated[Principal, require(Capability.WEBHOOK_CONFIG)],
) -> WebhookCreatedOut:
    """Validate and register a target, returning its signing secret once.

    Raises:
        HTTPException: 400 when the severity floor is unknown, 400 with R-55's
            reason when the URL is refused, 409 when the URL is already
            registered. A duplicate would deliver every alert twice, which reads
            as a receiver problem rather than a configuration one.
    """
    try:
        floor = Severity(body.severity_floor.strip().lower())
    except ValueError as exc:
        allowed = ", ".join(member.value for member in Severity)
        raise HTTPException(
            status_code=400, detail=f"severity_floor must be one of: {allowed}"
        ) from exc

    try:
        validated = validate_webhook_url(
            body.url, allowlist=_allowlist(request), resolver=_resolver(request)
        )
    except BlockedTarget as exc:
        # The reason code is safe to return; the URL never appears in it.
        detail = f"webhook URL refused: {exc.reason}"
        if exc.detail:
            detail = f"{detail} ({exc.detail})"
        raise HTTPException(status_code=400, detail=detail) from exc

    store = _store(request)
    if any(existing.url == validated.url for existing in store.list()):
        raise HTTPException(status_code=409, detail="this webhook URL is already registered")

    vault = _vault(request)
    secret = SecretVault.generate_secret()
    target = WebhookTarget(
        id=_new_id(store),
        url=validated.url,
        description=body.description.strip() if body.description else None,
        severity_floor=floor,
        secret_token=vault.seal(secret),
        created_at=datetime.now(UTC),
    )
    store.add(target)
    record_action(
        audit_trail(request),
        action=AuditAction.webhook_create,
        actor=caller.subject,
        target_type="webhook",
        target_id=target.id,
        at=datetime.now(UTC),
        # Neither the URL nor its host is recorded. A webhook URL can carry a
        # token in its path, and the trail is readable by every role while
        # webhook configuration is responder-and-above (R-53) -- mirroring
        # internal infrastructure into a wider-read log is a privilege leak, and
        # the target id is enough to join this row to the configuration. The
        # signing secret is never recorded anywhere.
        detail={"severity_floor": floor.value},
        ip=client_ip(request),
    )
    response.headers["Location"] = f"/api/v1/webhooks/{target.id}"
    return WebhookCreatedOut(**_out(target).model_dump(), secret=secret)


@router.get(
    "",
    response_model=WebhookListOut,
    summary="List registered webhooks, without secrets",
    dependencies=[require(Capability.WEBHOOK_CONFIG)],
)
def list_webhooks(request: Request) -> WebhookListOut:
    """Every registered target, oldest first, never with a secret."""
    return WebhookListOut(items=[_out(target) for target in _store(request).list()])


@router.delete(
    "/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a webhook",
)
def delete_webhook(
    webhook_id: str,
    request: Request,
    caller: Annotated[Principal, require(Capability.WEBHOOK_CONFIG)],
) -> Response:
    """Remove a target.

    Raises:
        HTTPException: 404 when no target has that id.
    """
    if not _store(request).remove(webhook_id):
        raise HTTPException(status_code=404, detail="no webhook with that id")
    record_action(
        audit_trail(request),
        action=AuditAction.webhook_delete,
        actor=caller.subject,
        target_type="webhook",
        target_id=webhook_id,
        at=datetime.now(UTC),
        # The target id only, for the same reason the create record carries no
        # host: the trail is read by more roles than may read the configuration.
        detail={"deleted": True},
        ip=client_ip(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _new_id(store: WebhookStore) -> str:
    """A short id, derived from nothing the URL contains.

    The URL may carry a token, so it is not an id source: ``wh_1``, ``wh_2``. A
    persistent store would take this from a sequence; the shape is the same.
    """
    used = {target.id for target in store.list()}
    candidate = 1
    while f"wh_{candidate}" in used:
        candidate += 1
    return f"wh_{candidate}"
