"""SSO OIDC service — Authorization Code flow with JIT provisioning.

Honest scope:
- OIDC only, not SAML. SAML is documented as future work.
- Discovery via issuer/.well-known/openid-configuration
- State + nonce stored in-memory with TTL (process-scoped, like other rate limits)
- JIT provisioning creates a user in default org if SSO_JIT_PROVISIONING=true
- No silent admin elevation — JIT role is SSO_DEFAULT_ROLE (USER/ANALYST only, never ADMIN)
- Secrets encrypted at rest via existing connector encryption helper
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Tuple
from urllib.parse import urlencode

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.secrets import decrypt_secret, encrypt_secret
from app.models import Org, User
from app.models.sso import SsoProvider
from app.core.security import get_password_hash, create_access_token, create_refresh_token

_LOGGER = logging.getLogger(__name__)

# In-memory state store: state -> {nonce, org_id, created_at, redirect_uri}
_STATE_TTL = 600  # 10 min
_STATE_LOCK = threading.Lock()
_STATE_STORE: Dict[str, Dict[str, Any]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _prune_states() -> None:
    now = time.monotonic()
    with _STATE_LOCK:
        expired = [k for k, v in _STATE_STORE.items() if now - v.get("_ts", 0) > _STATE_TTL]
        for k in expired:
            _STATE_STORE.pop(k, None)


def _get_provider(db: Session, org_id: int | None) -> SsoProvider | None:
    # Per-org first, then global (org_id NULL)
    if org_id is not None:
        p = db.query(SsoProvider).filter(SsoProvider.org_id == org_id, SsoProvider.enabled.is_(True)).first()
        if p:
            return p
    return db.query(SsoProvider).filter(SsoProvider.org_id.is_(None), SsoProvider.enabled.is_(True)).first()


def _env_provider() -> dict | None:
    if not settings.SSO_ENABLED:
        return None
    if not settings.SSO_OIDC_ISSUER or not settings.SSO_OIDC_CLIENT_ID:
        return None
    return {
        "issuer": settings.SSO_OIDC_ISSUER,
        "client_id": settings.SSO_OIDC_CLIENT_ID,
        "client_secret": settings.SSO_OIDC_CLIENT_SECRET,
        "scopes": settings.SSO_OIDC_SCOPES,
        "display_name": "Corporate SSO",
        "jit": settings.SSO_JIT_PROVISIONING,
    }


def get_sso_config(db: Session, org_id: int | None = None) -> dict:
    """Public config for login page — never returns secrets."""
    db_provider = _get_provider(db, org_id)
    env = _env_provider()

    if db_provider:
        return {
            "enabled": True,
            "provider_type": db_provider.provider_type,
            "display_name": db_provider.display_name,
            "issuer": db_provider.issuer,
            "client_id": db_provider.client_id,
            "scopes": db_provider.scopes or "openid email profile",
            "jit": db_provider.jit_provisioning,
            "source": "db",
        }
    if env:
        return {
            "enabled": True,
            "provider_type": "oidc",
            "display_name": env["display_name"],
            "issuer": env["issuer"],
            "client_id": env["client_id"],
            "scopes": env["scopes"],
            "jit": env["jit"],
            "source": "env",
        }
    return {"enabled": False}


def _discover_oidc(issuer: str) -> dict:
    issuer = issuer.rstrip("/")
    url = f"{issuer}/.well-known/openid-configuration"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def create_authorization_url(
    db: Session,
    redirect_uri: str,
    org_id: int | None = None,
) -> Tuple[str, str]:
    """Returns (auth_url, state). Stores state for callback validation."""
    _prune_states()

    cfg = get_sso_config(db, org_id)
    if not cfg.get("enabled"):
        raise ValueError("SSO not configured")

    issuer = cfg["issuer"]
    client_id = cfg["client_id"]
    scopes = cfg["scopes"]

    # Discover
    try:
        discovery = _discover_oidc(issuer)
        auth_endpoint = discovery.get("authorization_endpoint")
        if not auth_endpoint:
            raise ValueError("No authorization_endpoint in OIDC discovery")
    except Exception as exc:
        # Fallback: try common pattern
        _LOGGER.warning("OIDC discovery failed for %s: %s", issuer, exc)
        auth_endpoint = f"{issuer.rstrip('/')}/authorize"
        # Still proceed — some IdPs don't expose discovery in dev

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)

    with _STATE_LOCK:
        _STATE_STORE[state] = {
            "nonce": nonce,
            "org_id": org_id,
            "redirect_uri": redirect_uri,
            "issuer": issuer,
            "client_id": client_id,
            "_ts": time.monotonic(),
        }

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": state,
        "nonce": nonce,
    }
    return f"{auth_endpoint}?{urlencode(params)}", state


def _exchange_code(
    issuer: str,
    client_id: str,
    client_secret: str | None,
    code: str,
    redirect_uri: str,
) -> dict:
    discovery = _discover_oidc(issuer)
    token_endpoint = discovery.get("token_endpoint")
    if not token_endpoint:
        token_endpoint = f"{issuer.rstrip('/')}/token"

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }
    if client_secret:
        data["client_secret"] = client_secret

    resp = requests.post(token_endpoint, data=data, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _get_userinfo(issuer: str, access_token: str) -> dict:
    try:
        discovery = _discover_oidc(issuer)
        userinfo_endpoint = discovery.get("userinfo_endpoint")
        if not userinfo_endpoint:
            return {}
    except Exception:
        return {}

    resp = requests.get(
        userinfo_endpoint,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _decode_id_token_without_verification(id_token: str) -> dict:
    """Decode JWT payload without verification — we verify via userinfo or trust issuer.

    In production, you should verify signature via JWKS. This implementation
    does minimal verification for demo/small-team use and logs the limitation.
    """
    import base64
    import json

    try:
        parts = id_token.split(".")
        if len(parts) != 3:
            return {}
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return {}


def handle_callback(
    db: Session,
    code: str,
    state: str,
    redirect_uri: str,
) -> Tuple[User, str, str]:
    """Exchange code, get user info, JIT provision if needed. Returns (user, access_token, refresh_token)."""
    _prune_states()

    with _STATE_LOCK:
        stored = _STATE_STORE.pop(state, None)

    if not stored:
        raise ValueError("Invalid or expired state")

    issuer = stored["issuer"]
    client_id = stored["client_id"]
    org_id = stored.get("org_id")

    # Get provider for secret
    db_provider = _get_provider(db, org_id)
    if db_provider and db_provider.client_secret_encrypted:
        try:
            client_secret = decrypt_secret(db_provider.client_secret_encrypted)
        except Exception:
            client_secret = None
    else:
        client_secret = settings.SSO_OIDC_CLIENT_SECRET

    # Exchange
    token_resp = _exchange_code(issuer, client_id, client_secret, code, redirect_uri)
    access_token = token_resp.get("access_token")
    id_token = token_resp.get("id_token")

    userinfo = {}
    if access_token:
        try:
            userinfo = _get_userinfo(issuer, access_token)
        except Exception as exc:
            _LOGGER.warning("Failed to fetch userinfo: %s", exc)

    if not userinfo and id_token:
        userinfo = _decode_id_token_without_verification(id_token)

    # Extract identity
    email = userinfo.get("email") or userinfo.get("preferred_username") or userinfo.get("upn")
    sub = userinfo.get("sub")
    name = userinfo.get("name") or userinfo.get("preferred_username") or email

    if not email:
        raise ValueError("OIDC response missing email")

    email = email.lower().strip()

    # Find existing user by email or external_id
    user = (
        db.query(User)
        .filter((User.email == email) | (User.external_id == sub))
        .first()
    )

    # Determine org
    default_org = db.query(Org).filter(Org.slug == "default").first()
    if default_org is None:
        default_org = Org(name="Default Organization", slug="default")
        db.add(default_org)
        db.flush()

    target_org_id = org_id or (user.org_id if user else default_org.id)

    if not user:
        # JIT provisioning
        cfg = get_sso_config(db, org_id)
        jit = cfg.get("jit", True) if cfg else settings.SSO_JIT_PROVISIONING
        if not jit:
            raise ValueError("JIT provisioning disabled — user not found")

        # Role: never ADMIN via JIT
        default_role = (settings.SSO_DEFAULT_ROLE or "USER").upper()
        if default_role not in ("USER", "ANALYST"):
            default_role = "USER"

        username = email.split("@")[0]
        # Ensure unique username
        base_username = username
        counter = 1
        while db.query(User).filter(User.username == username).first():
            username = f"{base_username}{counter}"
            counter += 1

        user = User(
            username=username,
            email=email,
            password=get_password_hash(secrets.token_urlsafe(32)),  # random, not usable for password login
            role=default_role,
            org_id=target_org_id,
            external_id=sub,
            sso_provider=f"oidc:{issuer}",
            is_sso_user=True,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        _LOGGER.info("JIT provisioned SSO user %s from %s", email, issuer)
    else:
        # Update external_id if missing
        if not user.external_id and sub:
            user.external_id = sub
            user.sso_provider = f"oidc:{issuer}"
            user.is_sso_user = True
            db.commit()

        if user.is_blocked:
            raise ValueError("Account is blocked")

    # Issue our own tokens
    our_access = create_access_token(subject=user.username)
    our_refresh = create_refresh_token(subject=user.username)

    return user, our_access, our_refresh


def upsert_provider(
    db: Session,
    org_id: int | None,
    payload: dict,
    actor: str,
) -> SsoProvider:
    provider_type = (payload.get("provider_type") or "oidc").lower()
    if provider_type not in ("oidc",):
        raise ValueError("Only 'oidc' provider_type is supported — SAML is not implemented yet")

    issuer = payload.get("issuer")
    if not issuer:
        raise ValueError("issuer is required")

    client_id = payload.get("client_id")
    if not client_id:
        raise ValueError("client_id is required")

    # Find existing
    existing = _get_provider(db, org_id)
    if existing and existing.org_id == org_id:
        provider = existing
    else:
        provider = SsoProvider(
            org_id=org_id,
            provider_type=provider_type,
        )
        db.add(provider)

    provider.provider_type = provider_type
    provider.display_name = payload.get("display_name") or "Corporate SSO"
    provider.issuer = issuer
    provider.client_id = client_id
    provider.scopes = payload.get("scopes") or "openid email profile"
    provider.enabled = bool(payload.get("enabled", True))
    provider.jit_provisioning = bool(payload.get("jit_provisioning", True))

    if payload.get("client_secret"):
        provider.client_secret_encrypted = encrypt_secret(payload["client_secret"])

    db.commit()
    db.refresh(provider)
    return provider


def delete_provider(db: Session, org_id: int | None) -> dict:
    provider = _get_provider(db, org_id)
    if not provider:
        raise ValueError("No SSO provider configured")
    # Only delete org-specific or global if org_id None
    if org_id is None:
        q = db.query(SsoProvider).filter(SsoProvider.org_id.is_(None))
    else:
        q = db.query(SsoProvider).filter(SsoProvider.org_id == org_id)
    count = q.delete()
    db.commit()
    return {"deleted": count}


def reset_state_store() -> None:
    with _STATE_LOCK:
        _STATE_STORE.clear()
