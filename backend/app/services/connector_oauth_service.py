"""Connector OAuth — GitHub App + Slack OAuth + Google Workspace + AzureAD for real API tokens.

Phase 41: GitHub and Slack
Phase 46: Google Workspace, AzureAD (Entra ID) + refresh + secret rotation

Honest scope:
- Tokens encrypted at rest via existing connector encryption helper
- State stored in-memory TTL 10 min per-process (like SSO)
- Refresh implemented for providers that support refresh_token (Google, AzureAD, Slack if provided)
- Provider discovery via env vars *_OAUTH_CLIENT_ID/SECRET
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Tuple, Optional, Any
from urllib.parse import urlencode

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.secrets import decrypt_secret, encrypt_secret
from app.models.sso import ConnectorOAuth

_LOGGER = logging.getLogger(__name__)

_STATE_TTL = 600
_STATE_LOCK = threading.Lock()
_STATE_STORE: Dict[str, Dict[str, Any]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _prune_states():
    now = time.monotonic()
    with _STATE_LOCK:
        expired = [k for k, v in _STATE_STORE.items() if now - v.get("_ts", 0) > _STATE_TTL]
        for k in expired:
            _STATE_STORE.pop(k, None)


def _get_oauth_config(connector_id: str) -> dict | None:
    if connector_id == "github":
        if not settings.GITHUB_OAUTH_CLIENT_ID:
            return None
        return {
            "client_id": settings.GITHUB_OAUTH_CLIENT_ID,
            "client_secret": settings.GITHUB_OAUTH_CLIENT_SECRET,
            "authorize_url": "https://github.com/login/oauth/authorize",
            "token_url": "https://github.com/login/oauth/access_token",
            "scopes": "security_events read:org",
            "provider": "github",
        }
    elif connector_id == "slack":
        if not settings.SLACK_OAUTH_CLIENT_ID:
            return None
        return {
            "client_id": settings.SLACK_OAUTH_CLIENT_ID,
            "client_secret": settings.SLACK_OAUTH_CLIENT_SECRET,
            "authorize_url": "https://slack.com/oauth/v2/authorize",
            "token_url": "https://slack.com/api/oauth.v2.access",
            "scopes": "auditlogs:read",
            "provider": "slack",
        }
    elif connector_id == "gworkspace":
        if not settings.GOOGLE_OAUTH_CLIENT_ID:
            return None
        return {
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "scopes": "https://www.googleapis.com/auth/admin.reports.audit.readonly https://www.googleapis.com/auth/admin.directory.user.readonly",
            "provider": "gworkspace",
        }
    elif connector_id == "azuread":
        if not settings.AZUREAD_OAUTH_CLIENT_ID:
            return None
        tenant = settings.AZUREAD_OAUTH_TENANT_ID or "common"
        return {
            "client_id": settings.AZUREAD_OAUTH_CLIENT_ID,
            "client_secret": settings.AZUREAD_OAUTH_CLIENT_SECRET,
            "authorize_url": f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
            "token_url": f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            "scopes": "https://graph.microsoft.com/AuditLog.Read.All https://graph.microsoft.com/User.Read.All offline_access",
            "provider": "azuread",
        }
    return None


def get_connector_oauth_status(db: Session, org_id: int | None, connector_id: str) -> dict:
    row = (
        db.query(ConnectorOAuth)
        .filter(ConnectorOAuth.org_id == org_id, ConnectorOAuth.connector_id == connector_id)
        .first()
    )
    if not row:
        # Try global
        row = (
            db.query(ConnectorOAuth)
            .filter(ConnectorOAuth.org_id.is_(None), ConnectorOAuth.connector_id == connector_id)
            .first()
        )
    if not row:
        return {"connected": False, "connector_id": connector_id}

    return {
        "connected": True,
        "connector_id": connector_id,
        "provider": row.provider,
        "account_name": row.account_name,
        "account_id": row.account_id,
        "scopes": row.scopes,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "has_refresh_token": bool(row.refresh_token_encrypted),
    }


def create_oauth_authorization_url(
    db: Session,
    org_id: int | None,
    connector_id: str,
    redirect_uri: str,
) -> Tuple[str, str]:
    _prune_states()

    cfg = _get_oauth_config(connector_id)
    if not cfg:
        raise ValueError(f"OAuth not configured for connector {connector_id} — set {connector_id.upper()}_OAUTH_CLIENT_ID")

    state = secrets.token_urlsafe(32)

    with _STATE_LOCK:
        _STATE_STORE[state] = {
            "org_id": org_id,
            "connector_id": connector_id,
            "redirect_uri": redirect_uri,
            "_ts": time.monotonic(),
        }

    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": cfg["scopes"],
        "response_type": "code",
        "access_type": "offline" if connector_id in ("gworkspace", "azuread") else "online",
        "prompt": "consent" if connector_id in ("gworkspace", "azuread") else "consent",
    }

    # GitHub needs no extra, Slack needs user_scope maybe
    if connector_id == "slack":
        # Slack v2 uses scope, not user_scope for bot
        params.pop("response_type", None)
        params.pop("access_type", None)
        params.pop("prompt", None)
    elif connector_id == "github":
        params.pop("response_type", None)
        params.pop("access_type", None)
        params.pop("prompt", None)

    return f"{cfg['authorize_url']}?{urlencode(params)}", state


def exchange_oauth_code(
    db: Session,
    org_id: int | None,
    code: str,
    state: str,
) -> ConnectorOAuth:
    _prune_states()

    with _STATE_LOCK:
        stored = _STATE_STORE.pop(state, None)

    if not stored:
        raise ValueError("Invalid or expired OAuth state")

    connector_id = stored["connector_id"]
    redirect_uri = stored["redirect_uri"]
    stored_org_id = stored.get("org_id") or org_id

    cfg = _get_oauth_config(connector_id)
    if not cfg:
        raise ValueError(f"OAuth not configured for {connector_id}")

    # Exchange
    data = {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    headers = {"Accept": "application/json"}

    # For Google and AzureAD, token endpoint expects form-encoded
    if connector_id in ("gworkspace", "azuread"):
        headers = {}

    resp = requests.post(cfg["token_url"], data=data, headers=headers, timeout=10)
    resp.raise_for_status()
    token_data = resp.json()

    # GitHub returns access_token, Slack returns access_token + authed_user etc
    if "error" in token_data:
        raise ValueError(f"OAuth error: {token_data.get('error')} {token_data.get('error_description', '')}")

    access_token = token_data.get("access_token")
    if not access_token:
        # GitHub may return as urlencoded if Accept not json? We set Accept json, so should be json
        raise ValueError("No access_token in OAuth response")

    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")
    scope = token_data.get("scope") or cfg["scopes"]

    account_id = None
    account_name = None

    if connector_id == "github":
        # Get user/org info
        try:
            user_resp = requests.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
                timeout=10,
            )
            user_resp.raise_for_status()
            user_info = user_resp.json()
            account_id = str(user_info.get("id"))
            account_name = user_info.get("login")
        except Exception as exc:
            _LOGGER.warning("Failed to fetch GitHub user info: %s", exc)

    elif connector_id == "slack":
        # Slack response contains team info
        team = token_data.get("team") or {}
        account_id = team.get("id") or token_data.get("team_id")
        account_name = team.get("name")

    elif connector_id == "gworkspace":
        try:
            # Get user info via Google
            user_resp = requests.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            if user_resp.status_code == 200:
                user_info = user_resp.json()
                account_id = user_info.get("id")
                account_name = user_info.get("email")
        except Exception as exc:
            _LOGGER.warning("Failed to fetch Google user info: %s", exc)

    elif connector_id == "azuread":
        try:
            user_resp = requests.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            if user_resp.status_code == 200:
                user_info = user_resp.json()
                account_id = user_info.get("id")
                account_name = user_info.get("userPrincipalName") or user_info.get("mail")
        except Exception as exc:
            _LOGGER.warning("Failed to fetch AzureAD user info: %s", exc)

    # Upsert
    existing = (
        db.query(ConnectorOAuth)
        .filter(ConnectorOAuth.org_id == stored_org_id, ConnectorOAuth.connector_id == connector_id)
        .first()
    )
    if existing:
        row = existing
    else:
        row = ConnectorOAuth(
            org_id=stored_org_id,
            connector_id=connector_id,
            provider=connector_id,
        )
        db.add(row)

    row.provider = connector_id
    row.access_token_encrypted = encrypt_secret(access_token)
    if refresh_token:
        row.refresh_token_encrypted = encrypt_secret(refresh_token)
    row.token_type = token_data.get("token_type", "Bearer")
    if expires_in:
        try:
            row.expires_at = _now() + timedelta(seconds=int(expires_in))
        except Exception:
            row.expires_at = None
    else:
        # For providers that don't return expires_in, set default 1h for refreshable tokens
        if refresh_token:
            row.expires_at = _now() + timedelta(seconds=3600)
    row.scopes = scope
    row.account_id = account_id
    row.account_name = account_name

    db.commit()
    db.refresh(row)
    _LOGGER.info("OAuth connected for %s (org %s) as %s", connector_id, stored_org_id, account_name)

    return row


def _refresh_oauth_token(db: Session, row: ConnectorOAuth) -> str | None:
    """Refresh an expired OAuth token using refresh_token. Returns new access token or None."""
    if not row.refresh_token_encrypted:
        return None

    cfg = _get_oauth_config(row.connector_id)
    if not cfg:
        return None

    try:
        refresh_token = decrypt_secret(row.refresh_token_encrypted)
    except Exception:
        _LOGGER.error("Failed to decrypt refresh token for %s", row.connector_id)
        return None

    data = {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    try:
        resp = requests.post(cfg["token_url"], data=data, timeout=10)
        resp.raise_for_status()
        token_data = resp.json()

        if "error" in token_data:
            _LOGGER.warning("OAuth refresh error for %s: %s", row.connector_id, token_data.get("error"))
            return None

        new_access = token_data.get("access_token")
        if not new_access:
            return None

        new_refresh = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")

        row.access_token_encrypted = encrypt_secret(new_access)
        if new_refresh:
            row.refresh_token_encrypted = encrypt_secret(new_refresh)
        if expires_in:
            try:
                row.expires_at = _now() + timedelta(seconds=int(expires_in))
            except Exception:
                pass
        else:
            row.expires_at = _now() + timedelta(seconds=3600)

        db.commit()
        _LOGGER.info("OAuth token refreshed for %s (org %s)", row.connector_id, row.org_id)
        return new_access
    except Exception as exc:
        _LOGGER.warning("OAuth refresh failed for %s: %s", row.connector_id, exc)
        return None


def get_oauth_token(db: Session, org_id: int | None, connector_id: str) -> str | None:
    """Get decrypted access token for connector, refresh if expired and possible."""
    row = (
        db.query(ConnectorOAuth)
        .filter(ConnectorOAuth.org_id == org_id, ConnectorOAuth.connector_id == connector_id)
        .first()
    )
    if not row:
        row = (
            db.query(ConnectorOAuth)
            .filter(ConnectorOAuth.org_id.is_(None), ConnectorOAuth.connector_id == connector_id)
            .first()
        )
    if not row or not row.access_token_encrypted:
        return None

    # Check expiry — if expired, try refresh (handle naive vs aware)
    if row.expires_at:
        exp = row.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < _now():
            if row.refresh_token_encrypted:
                refreshed = _refresh_oauth_token(db, row)
                if refreshed:
                    return refreshed
                _LOGGER.warning("OAuth token expired for %s and refresh failed", connector_id)
                return None
            else:
                # No refresh token — for GitHub tokens that don't expire, we still return if no refresh
                # But if expires_at is set and no refresh, treat as expired
                if row.connector_id in ("github", "slack") and not row.refresh_token_encrypted:
                    # GitHub/Slack tokens often don't expire — allow if no refresh but expired_at past
                    # For safety, still try to return decrypted token if it's GitHub (they don't expire)
                    if row.connector_id == "github":
                        try:
                            return decrypt_secret(row.access_token_encrypted)
                        except Exception:
                            return None
                return None

    try:
        return decrypt_secret(row.access_token_encrypted)
    except Exception:
        _LOGGER.error("Failed to decrypt OAuth token for %s", connector_id)
        return None


def disconnect_oauth(db: Session, org_id: int | None, connector_id: str) -> dict:
    q = db.query(ConnectorOAuth).filter(ConnectorOAuth.connector_id == connector_id)
    if org_id is not None:
        q = q.filter(ConnectorOAuth.org_id == org_id)
    else:
        q = q.filter(ConnectorOAuth.org_id.is_(None))

    row = q.first()
    if not row:
        raise ValueError(f"No OAuth connection for {connector_id}")

    db.delete(row)
    db.commit()
    return {"disconnected": connector_id}


def reset_state_store():
    with _STATE_LOCK:
        _STATE_STORE.clear()

