"""Password sign-in, refresh rotation, and first-admin setup (T-417).

The first administrator either comes from deployment-supplied bootstrap
credentials or from the one-shot setup route, which is disabled unless an
operator explicitly enables it in development. Login and refresh are public
routes in the RBAC sense, but each requires a password or a single-use refresh
token; there is no anonymous session or demo credential.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from app.api.v1.deps import audit_trail, client_ip
from app.auth.oidc import OidcError, OidcSignIn, OidcUnavailable, verified_email
from app.auth.rbac import Role
from app.auth.tokens import MalformedToken, TokenPair, TokenService
from app.core.config import Environment
from app.schemas.auth import AuthStatusOut, CredentialsIn, RefreshIn, TokenPairOut
from app.services.audit_log import AuditAction, record_action
from app.services.auth_accounts import (
    AccountAlreadyProvisioned,
    AuthAccountStore,
    normalise_email,
)
from app.services.login_throttle import LoginThrottle
from app.services.user_directory import UserRecord

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
_log = logging.getLogger(__name__)


def _no_store(response: Response) -> None:
    """Prevent credentials and authentication state from entering HTTP caches."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _accounts(request: Request) -> AuthAccountStore:
    """The shared account store; it is also the backing admin directory."""
    return cast(AuthAccountStore, request.app.state.auth_accounts)


def _tokens(request: Request) -> TokenService:
    """The application-wide JWT service installed by the composition root."""
    return cast(TokenService, request.app.state.token_service)


def _token_response(pair: TokenPair, account: UserRecord) -> TokenPairOut:
    """Serialise a token pair without exposing any stored password material."""
    return TokenPairOut(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
        subject=account.email,
        role=account.role.value,
    )


def _issue(request: Request, account: UserRecord) -> TokenPairOut:
    """Issue a new session for the account's current role."""
    if account.role.value not in {role.value for role in Role}:
        raise HTTPException(status_code=403, detail="account role is not permitted")
    return _token_response(_tokens(request).issue(account.email, account.role.value), account)


@router.get(
    "/status",
    response_model=AuthStatusOut,
    summary="Whether first-admin setup is available",
)
def auth_status(request: Request, response: Response) -> AuthStatusOut:
    """Report local setup availability without returning account identifiers."""
    _no_store(response)
    settings = request.app.state.settings
    setup_enabled = settings.env is Environment.DEVELOPMENT and settings.dev_auth_setup_enabled
    account_exists = _accounts(request).account_count() > 0
    return AuthStatusOut(
        setup_enabled=setup_enabled,
        setup_available=setup_enabled and not account_exists,
        account_exists=account_exists,
    )


@router.post(
    "/setup",
    response_model=TokenPairOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create the first local development administrator",
)
def setup_first_admin(
    body: CredentialsIn,
    request: Request,
    response: Response,
) -> TokenPairOut:
    """Create the first admin only when the development-only switch is enabled.

    The operator-provided password is hashed with Argon2id. The account and hash
    are held in memory and disappear when this process stops; deployments that
    need durable accounts must supply bootstrap credentials or a database adapter.
    """
    _no_store(response)
    settings = request.app.state.settings
    if settings.env is not Environment.DEVELOPMENT or not settings.dev_auth_setup_enabled:
        raise HTTPException(status_code=404, detail="not found")
    try:
        account = _accounts(request).create_initial_admin(
            body.email,
            body.password.get_secret_value(),
        )
    except AccountAlreadyProvisioned as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="the first administrator is already provisioned",
        ) from exc
    pair = _tokens(request).issue(account.email, account.role.value)
    record_action(
        audit_trail(request),
        action=AuditAction.auth_setup,
        actor=account.email,
        target_type="user",
        target_id=str(account.id),
        at=datetime.now(UTC),
        detail={"role": account.role.value},
        ip=client_ip(request),
    )
    return _token_response(pair, account)


@router.post(
    "/login",
    response_model=TokenPairOut,
    summary="Sign in with an account password",
)
def login(body: CredentialsIn, request: Request, response: Response) -> TokenPairOut:
    """Authenticate an account without disclosing whether its email exists."""
    _no_store(response)
    throttle: LoginThrottle = request.app.state.login_throttle
    # A request with no peer address shares one bucket: stricter than skipping the count.
    address = client_ip(request) or "unknown"
    # Keyed on the canonical address, so "Admin@x" and "admin@x" share one counter. An
    # address that cannot be normalised is refused like any other bad password below,
    # but it is still counted against the source address.
    try:
        key_email = normalise_email(body.email)
    except ValueError:
        key_email = body.email.strip().lower()
    decision = throttle.check(key_email, address)
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many sign-in attempts; try again later",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
    account = _accounts(request).authenticate(body.email, body.password.get_secret_value())
    if account is None:
        throttle.record_failure(key_email, address)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="email or password is incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    throttle.record_success(key_email)
    result = _issue(request, account)
    record_action(
        audit_trail(request),
        action=AuditAction.auth_login,
        actor=account.email,
        target_type="user",
        target_id=str(account.id),
        at=datetime.now(UTC),
        ip=client_ip(request),
    )
    return result


@router.post(
    "/refresh",
    response_model=TokenPairOut,
    summary="Rotate a single-use refresh token",
)
def refresh(body: RefreshIn, request: Request, response: Response) -> TokenPairOut:
    """Rotate once, using the account's current role rather than a stale claim."""
    _no_store(response)
    refresh_token = body.refresh_token.get_secret_value()
    token_service = _tokens(request)
    try:
        claims = token_service.verify_refresh(refresh_token)
        account = _accounts(request).active_account(str(claims.get("sub", "")))
        if account is None:
            # A valid but no-longer-provisioned account must not retain a session.
            token_service.revoke(refresh_token)
            raise MalformedToken("refresh account is unavailable")
        pair = token_service.rotate(refresh_token, role=account.role.value)
    except MalformedToken as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="refresh token is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    record_action(
        audit_trail(request),
        action=AuditAction.auth_refresh,
        actor=account.email,
        target_type="user",
        target_id=str(account.id),
        at=datetime.now(UTC),
        ip=client_ip(request),
    )
    return _token_response(pair, account)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the refresh-token family",
)
def logout(body: RefreshIn, request: Request, response: Response) -> None:
    """Revoke a session's refresh family; invalid tokens are already logged out."""
    _no_store(response)
    # Logout is idempotent from the client's perspective. The browser clears its
    # tab-scoped pair even when the refresh token was expired or replayed; only a
    # valid revocation is an audit event, and neither token is written to the trail.
    token_service = _tokens(request)
    try:
        claims = token_service.verify_refresh(body.refresh_token.get_secret_value())
        actor = claims.get("sub")
        family = claims.get("fam")
        if not isinstance(actor, str) or not isinstance(family, str):
            raise MalformedToken("refresh token is missing its session identity")
        token_service.revoke(body.refresh_token.get_secret_value())
    except MalformedToken:
        pass
    else:
        record_action(
            audit_trail(request),
            action=AuditAction.auth_logout,
            actor=actor,
            target_type="session",
            target_id=family,
            at=datetime.now(UTC),
            ip=client_ip(request),
        )
    response.status_code = status.HTTP_204_NO_CONTENT


def _oidc(request: Request) -> OidcSignIn:
    """The OIDC client, or 404: a deployment that did not enable OIDC has no such route."""
    oidc: OidcSignIn | None = getattr(request.app.state, "oidc", None)
    if oidc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return oidc


@router.get(
    "/oidc/start",
    summary="Start an OpenID Connect sign-in (FR-43)",
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
    responses={
        status.HTTP_302_FOUND: {
            "description": "Redirect to the identity provider's authorization endpoint",
            "content": {"text/plain": {"schema": {"type": "string", "maxLength": 0}}},
        },
        status.HTTP_404_NOT_FOUND: {"description": "OIDC is not enabled on this deployment"},
        status.HTTP_502_BAD_GATEWAY: {"description": "The identity provider could not be reached"},
    },
)
def oidc_start(request: Request) -> RedirectResponse:
    """Redirect the browser to the identity provider with PKCE, state and nonce."""
    oidc = _oidc(request)
    try:
        url = oidc.authorization_url(oidc.store.create())
    except OidcUnavailable as exc:
        _log.warning("oidc start failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="identity provider unavailable"
        ) from exc
    response = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    _no_store(response)
    return response


@router.get(
    "/oidc/callback",
    response_model=TokenPairOut,
    summary="Complete an OpenID Connect sign-in (FR-43)",
)
def oidc_callback(
    request: Request,
    response: Response,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> TokenPairOut:
    """Redeem the code, verify the ID token, and issue the same session a password login would.

    Identity comes from the provider; authority comes from the local account. A
    verified email with no active local account is refused, so sign-in never
    creates a user.
    """
    _no_store(response)
    oidc = _oidc(request)
    if error is not None:
        _log.info("oidc callback carried provider error")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="identity provider did not complete sign-in",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="code and state are required"
        )
    # Taken, not read: a callback can be redeemed once, whatever the outcome below.
    pending = oidc.store.take(state)
    if pending is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="sign-in expired or already used; start again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = oidc.complete(code, pending)
        email = verified_email(claims)
    except OidcUnavailable as exc:
        _log.warning("oidc callback failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="identity provider unavailable"
        ) from exc
    except OidcError as exc:
        _log.info("oidc sign-in refused: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="sign-in could not be verified",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    account = _accounts(request).active_account(email)
    if account is None:
        _log.info("oidc sign-in with no active local account")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="no active account is provisioned for this identity",
        )
    result = _issue(request, account)
    record_action(
        audit_trail(request),
        action=AuditAction.auth_login,
        actor=account.email,
        target_type="user",
        target_id=str(account.id),
        at=datetime.now(UTC),
        ip=client_ip(request),
    )
    return result
