"""Password sign-in, refresh rotation, and first-admin setup (T-417).

The first administrator either comes from deployment-supplied bootstrap
credentials or from the one-shot setup route, which is disabled unless an
operator explicitly enables it in development. Login and refresh are public
routes in the RBAC sense, but each requires a password or a single-use refresh
token; there is no anonymous session or demo credential.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.v1.deps import audit_trail, client_ip
from app.auth.rbac import Role
from app.auth.tokens import MalformedToken, TokenPair, TokenService
from app.core.config import Environment
from app.schemas.auth import AuthStatusOut, CredentialsIn, RefreshIn, TokenPairOut
from app.services.audit_log import AuditAction, record_action
from app.services.auth_accounts import AccountAlreadyProvisioned, AuthAccountStore
from app.services.user_directory import UserRecord

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


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
    account = _accounts(request).authenticate(body.email, body.password.get_secret_value())
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="email or password is incorrect",
            headers={"WWW-Authenticate": "Bearer"},
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
