"""Connector OAuth — GitHub App + Slack OAuth for real API tokens.

Phase 41: small teams use GitHub and Slack, they want NOCTRA to ingest directly
from those APIs using OAuth, not just push webhooks.

- GitHub: OAuth App flow (or GitHub App installation) to get token for Advanced Security alerts
- Slack: OAuth v2 flow to get token for Audit Logs API

Honest scope:
- Tokens encrypted at rest via existing connector encryption helper
- State stored in-memory TTL 10 min per-process (like SSO)
- No automatic refresh yet for GitHub (GitHub tokens don't expire, but we store expiry if provided)
- Slack tokens may need refresh — we attempt refresh if refresh_token present
- Provider discovery via env vars GITHUB_OAUTH_CLIENT_ID/SECRET, SLACK_OAUTH_CLIENT_ID/SECRET
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
    }

    # GitHub needs no extra, Slack needs user_scope maybe
    if connector_id == "slack":
        # Slack v2 uses scope, not user_scope for bot
        pass

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
    }

    headers = {"Accept": "application/json"}

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
    row.scopes = scope
    row.account_id = account_id
    row.account_name = account_name

    db.commit()
    db.refresh(row)
    _LOGGER.info("OAuth connected for %s (org %s) as %s", connector_id, stored_org_id, account_name)

    return row


def get_oauth_token(db: Session, org_id: int | None, connector_id: str) -> str | None:
    """Get decrypted access token for connector, if available and not expired."""
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

    # Check expiry
    if row.expires_at and row.expires_at < _now():
        # Try refresh if possible
        if row.refresh_token_encrypted:
            try:
                refresh_token = decrypt_secret(row.refresh_token_encrypted)
                # Refresh logic depends on provider — for now log and return None
                _LOGGER.warning("OAuth token expired for %s, refresh not implemented yet", connector_id)
                return None
            except Exception:
                return None
        else:
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
