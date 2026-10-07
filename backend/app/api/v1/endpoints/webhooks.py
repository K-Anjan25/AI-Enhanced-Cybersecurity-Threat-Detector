"""Webhook configuration and delivery endpoints (FR-21, R-55, T-311, T-422).

Registering a target is where R-55 is enforced, and it is enforced *here* rather
than at delivery time: a URL that fails the allowlist or resolves into a private
range is refused when an operator submits it, with the reason, instead of every
alert after a breach quietly failing to leave the building. The validation is
the same function the delivery path would call, so there is one definition of
"may we send this".

T-422 adds the *read* half: ``GET /deliveries`` serves the attempts the sender has
recorded, and ``POST /{webhook_id}/test`` makes one, so an operator who has just
provisioned an endpoint can see whether it takes a signed event. The test route is
honest about the one thing this build does not have -- an HTTP transport, which
T-311 deliberately left unwritten because there is no network here to verify it
against -- and it does not pretend otherwise: with no sender configured it answers
503 naming that, and the read route's caveats say the same thing in words.

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

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from app.api.v1.deps import audit_trail, client_ip
from app.auth.rbac import Capability, Principal, require
from app.schemas.webhook import (
    DeliveryListOut,
    DeliveryOut,
    WebhookCreate,
    WebhookCreatedOut,
    WebhookListOut,
    WebhookOut,
)
from app.services.audit_log import AuditAction, record_action
from app.services.correlator import Severity
from app.services.webhook_deliveries import (
    DEFAULT_READ_LIMIT,
    MAX_READ_LIMIT,
    DeliveryLog,
    DeliveryRecord,
    delivery_caveats,
    probe_notification,
)
from app.services.webhook_delivery import WebhookSender
from app.services.webhook_targets import (
    BlockedTarget,
    SecretUnreadable,
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


def _deliveries(request: Request) -> DeliveryLog:
    """The delivery read model, from application state (T-422)."""
    log: DeliveryLog | None = getattr(request.app.state, "webhook_deliveries", None)
    if log is None:
        msg = "webhook_deliveries is not configured on app.state"
        raise RuntimeError(msg)
    return log


def _sender(request: Request) -> WebhookSender | None:
    """The delivery machinery, or ``None`` when this deployment has none.

    ``None`` is the honest answer for a build without an HTTP transport, and it
    is reported rather than hidden: the read route says the list is empty by
    construction, and the test route refuses with the same reason.
    """
    sender: WebhookSender | None = getattr(request.app.state, "webhook_sender", None)
    return sender


def _delivery_out(record: DeliveryRecord) -> DeliveryOut:
    """Serialise one delivery record. It carries no URL and no secret."""
    return DeliveryOut(
        delivery_id=record.delivery_id,
        target_id=record.target_id,
        at=record.at,
        delivered=record.delivered,
        attempt_count=record.attempt_count,
        waited_seconds=record.waited_seconds,
        outcome=record.outcome,
        status=record.status,
        reason=record.reason,
    )


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


@router.get(
    "/deliveries",
    response_model=DeliveryListOut,
    summary="Recent delivery attempts, newest first (T-422)",
    dependencies=[require(Capability.WEBHOOK_CONFIG)],
)
def list_deliveries(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=MAX_READ_LIMIT)] = DEFAULT_READ_LIMIT,
) -> DeliveryListOut:
    """The delivery attempts this process has made, and what qualifies them.

    The records come from the sender's own sink rather than from anything this
    route does, so a delivery made by the alert pipeline appears here exactly as a
    test send does. ``dispatch_configured`` is what lets a screen tell an empty
    list from an endpoint nothing has reached: a deployment with no sender cannot
    have recorded anything, and its caveats say so in words.
    """
    log = _deliveries(request)
    records = log.recent(limit=limit)
    configured = _sender(request) is not None
    return DeliveryListOut(
        items=[_delivery_out(record) for record in records],
        held=log.held,
        recorded=log.recorded,
        dispatch_configured=configured,
        caveats=delivery_caveats(log=log, shown=len(records), dispatch_configured=configured),
    )


@router.post(
    "/{webhook_id}/test",
    response_model=DeliveryOut,
    summary="Attempt one delivery to a target (T-422)",
)
def test_webhook(
    webhook_id: str,
    request: Request,
    caller: Annotated[Principal, require(Capability.WEBHOOK_CONFIG)],
) -> DeliveryOut:
    """Send one signed event to a target, and return what happened.

    One attempt, no retries, at the deployment's own transport and with R-55's
    checks re-run exactly as a real delivery runs them, so the outcome means the
    same thing a delivery would. The attempt is recorded by the sender's sink, so
    it appears in ``GET /deliveries`` whether or not this response is read.

    Raises:
        HTTPException: 404 when no target has that id; 409 when the target's
            sealed secret cannot be opened with the current application key,
            which no number of attempts fixes; 503 when this deployment has no
            outbound transport, which is what T-311 left unwritten because there
            was no network here to verify one against.
    """
    target = next((item for item in _store(request).list() if item.id == webhook_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="no webhook with that id")

    sender = _sender(request)
    if sender is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "no outbound transport is configured in this deployment, so a delivery "
                "cannot be attempted; attempts already made are readable from "
                "GET /api/v1/webhooks/deliveries"
            ),
        )

    try:
        report = sender.probe(target, probe_notification(target.severity_floor))
    except SecretUnreadable as exc:
        # The reason is a short code, never a message built from the secret.
        raise HTTPException(
            status_code=409,
            detail=(
                "this target's signing secret cannot be opened with the current application "
                "key; it was sealed with a different one, so re-issue the target"
            ),
        ) from exc

    record = _deliveries(request).record(report, at=datetime.now(UTC))
    record_action(
        audit_trail(request),
        action=AuditAction.webhook_test,
        actor=caller.subject,
        target_type="webhook",
        target_id=target.id,
        at=datetime.now(UTC),
        # The outcome and nothing else: no URL, no host, no secret (R-53, R-58),
        # the same rule the create and delete records follow. A test send is a
        # request that left the building, so it is attributed like one.
        detail={"delivered": report.delivered, "attempts": report.attempt_count},
        ip=client_ip(request),
    )
    return _delivery_out(record)


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
