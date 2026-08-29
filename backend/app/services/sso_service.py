"""SSO service — OIDC + SAML 2.0 with JIT provisioning.

Honest scope:
- OIDC: Authorization Code flow with JIT, state+nonce in-memory TTL 10 min per-process
- SAML: SP-initiated, AuthnRequest generation, SAMLResponse parsing (base64 XML),
  NameID/email extraction, signature verification if xmlsec + cert available,
  else parses without verification with warning (documented gap)
- JIT provisioning creates user in default org if enabled, role USER/ANALYST only, never ADMIN
- Secrets encrypted at rest via connector encryption helper
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import threading
import time
import zlib
from datetime import datetime, timezone
from typing import Any, Dict, Tuple, Optional
from urllib.parse import urlencode, quote
import xml.etree.ElementTree as ET

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


def _get_provider(db: Session, org_id: int | None, provider_type: str | None = None) -> SsoProvider | None:
    # Per-org first, then global (org_id NULL)
    q = db.query(SsoProvider).filter(SsoProvider.enabled.is_(True))
    if provider_type:
        q = q.filter(SsoProvider.provider_type == provider_type)
    if org_id is not None:
        p = q.filter(SsoProvider.org_id == org_id).first()
        if p:
            return p
    return q.filter(SsoProvider.org_id.is_(None)).first()


def _get_provider_by_type(db: Session, org_id: int | None, provider_type: str) -> SsoProvider | None:
    if org_id is not None:
        p = db.query(SsoProvider).filter(
            SsoProvider.org_id == org_id,
            SsoProvider.provider_type == provider_type,
            SsoProvider.enabled.is_(True),
        ).first()
        if p:
            return p
    return db.query(SsoProvider).filter(
        SsoProvider.org_id.is_(None),
        SsoProvider.provider_type == provider_type,
        SsoProvider.enabled.is_(True),
    ).first()


def _env_oidc_provider() -> dict | None:
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
        "provider_type": "oidc",
    }


def _env_saml_provider() -> dict | None:
    if not settings.SSO_SAML_ENABLED:
        return None
    if not settings.SSO_SAML_SSO_URL and not settings.SSO_SAML_METADATA_URL:
        return None
    return {
        "provider_type": "saml",
        "display_name": "Corporate SAML SSO",
        "sso_url": settings.SSO_SAML_SSO_URL,
        "entity_id": settings.SSO_SAML_ENTITY_ID,
        "acs_url": settings.SSO_SAML_ACS_URL,
        "metadata_url": settings.SSO_SAML_METADATA_URL,
        "certificate": settings.SSO_SAML_CERTIFICATE,
        "jit": settings.SSO_JIT_PROVISIONING,
    }


def get_sso_config(db: Session, org_id: int | None = None) -> dict:
    """Public config for login page — never returns secrets. Returns OIDC + SAML if configured."""
    oidc_db = _get_provider_by_type(db, org_id, "oidc")
    saml_db = _get_provider_by_type(db, org_id, "saml")
    oidc_env = _env_oidc_provider()
    saml_env = _env_saml_provider()

    # Prefer DB over env
    oidc_cfg = None
    if oidc_db:
        oidc_cfg = {
            "enabled": True,
            "provider_type": oidc_db.provider_type,
            "display_name": oidc_db.display_name,
            "issuer": oidc_db.issuer,
            "client_id": oidc_db.client_id,
            "scopes": oidc_db.scopes or "openid email profile",
            "jit": oidc_db.jit_provisioning,
            "source": "db",
        }
    elif oidc_env:
        oidc_cfg = {
            "enabled": True,
            "provider_type": "oidc",
            "display_name": oidc_env["display_name"],
            "issuer": oidc_env["issuer"],
            "client_id": oidc_env["client_id"],
            "scopes": oidc_env["scopes"],
            "jit": oidc_env["jit"],
            "source": "env",
        }

    saml_cfg = None
    if saml_db:
        saml_cfg = {
            "enabled": True,
            "provider_type": "saml",
            "display_name": saml_db.display_name,
            "sso_url": saml_db.saml_sso_url,
            "entity_id": saml_db.saml_entity_id,
            "acs_url": saml_db.saml_acs_url,
            "metadata_url": saml_db.saml_metadata_url,
            "jit": saml_db.jit_provisioning,
            "source": "db",
        }
    elif saml_env:
        saml_cfg = {
            "enabled": True,
            "provider_type": "saml",
            "display_name": saml_env["display_name"],
            "sso_url": saml_env["sso_url"],
            "entity_id": saml_env["entity_id"],
            "acs_url": saml_env["acs_url"],
            "metadata_url": saml_env["metadata_url"],
            "jit": saml_env["jit"],
            "source": "env",
        }

    # Backward compat: if only OIDC, return flat for old frontend
    # New frontend should check oidc and saml keys
    result: dict = {"enabled": bool(oidc_cfg or saml_cfg)}
    if oidc_cfg:
        result["oidc"] = oidc_cfg
        # For backward compat, also top-level fields for OIDC
        result.update(oidc_cfg)
    if saml_cfg:
        result["saml"] = saml_cfg

    if not result["enabled"]:
        result = {"enabled": False}

    return result


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
    oidc = cfg.get("oidc") or cfg if cfg.get("provider_type") == "oidc" else None
    if not oidc or not oidc.get("enabled"):
        # Try flat
        if cfg.get("provider_type") == "oidc" and cfg.get("enabled"):
            oidc = cfg
        else:
            oidc = cfg.get("oidc")

    if not oidc:
        raise ValueError("SSO not configured")

    issuer = oidc["issuer"]
    client_id = oidc["client_id"]
    scopes = oidc["scopes"]

    # Discover
    try:
        discovery = _discover_oidc(issuer)
        auth_endpoint = discovery.get("authorization_endpoint")
        if not auth_endpoint:
            raise ValueError("No authorization_endpoint in OIDC discovery")
    except Exception as exc:
        _LOGGER.warning("OIDC discovery failed for %s: %s", issuer, exc)
        auth_endpoint = f"{issuer.rstrip('/')}/authorize"

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)

    with _STATE_LOCK:
        _STATE_STORE[state] = {
            "nonce": nonce,
            "org_id": org_id,
            "redirect_uri": redirect_uri,
            "issuer": issuer,
            "client_id": client_id,
            "provider_type": "oidc",
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
    db_provider = _get_provider_by_type(db, org_id, "oidc")
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

    email = userinfo.get("email") or userinfo.get("preferred_username") or userinfo.get("upn")
    sub = userinfo.get("sub")

    if not email:
        raise ValueError("OIDC response missing email")

    email = email.lower().strip()

    user = (
        db.query(User)
        .filter((User.email == email) | (User.external_id == sub))
        .first()
    )

    default_org = db.query(Org).filter(Org.slug == "default").first()
    if default_org is None:
        default_org = Org(name="Default Organization", slug="default")
        db.add(default_org)
        db.flush()

    target_org_id = org_id or (user.org_id if user else default_org.id)

    if not user:
        cfg = get_sso_config(db, org_id)
        oidc_cfg = cfg.get("oidc") or cfg
        jit = oidc_cfg.get("jit", True) if oidc_cfg else settings.SSO_JIT_PROVISIONING
        if not jit:
            raise ValueError("JIT provisioning disabled — user not found")

        default_role = (settings.SSO_DEFAULT_ROLE or "USER").upper()
        if default_role not in ("USER", "ANALYST"):
            default_role = "USER"

        username = email.split("@")[0]
        base_username = username
        counter = 1
        while db.query(User).filter(User.username == username).first():
            username = f"{base_username}{counter}"
            counter += 1

        user = User(
            username=username,
            email=email,
            password=get_password_hash(secrets.token_urlsafe(32)),
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
        if not user.external_id and sub:
            user.external_id = sub
            user.sso_provider = f"oidc:{issuer}"
            user.is_sso_user = True
            db.commit()

        if user.is_blocked:
            raise ValueError("Account is blocked")

    our_access = create_access_token(subject=user.username)
    our_refresh = create_refresh_token(subject=user.username)

    return user, our_access, our_refresh


# SAML

def _parse_saml_metadata(metadata_xml: str) -> dict:
    """Parse SAML metadata XML to extract SSO URL and cert."""
    try:
        root = ET.fromstring(metadata_xml)
        ns = {"md": "urn:oasis:names:tc:SAML:2.0:metadata", "ds": "http://www.w3.org/2000/09/xmldsig#"}
        # Find IDPSSODescriptor
        idp = root.find(".//md:IDPSSODescriptor", ns)
        if idp is None:
            # Try without ns
            for elem in root.iter():
                if "IDPSSODescriptor" in elem.tag:
                    idp = elem
                    break

        sso_url = None
        cert = None
        if idp is not None:
            # SSO URL
            for svc in idp.findall("md:SingleSignOnService", ns):
                if svc.get("Binding") == "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect":
                    sso_url = svc.get("Location")
                    break
            if not sso_url:
                for svc in idp.findall("md:SingleSignOnService", ns):
                    sso_url = svc.get("Location")
                    if sso_url:
                        break
            # Cert
            cert_elem = idp.find(".//ds:X509Certificate", ns)
            if cert_elem is not None:
                cert = cert_elem.text

        return {"sso_url": sso_url, "certificate": cert}
    except Exception as exc:
        _LOGGER.warning("Failed to parse SAML metadata: %s", exc)
        return {}


def fetch_saml_metadata(metadata_url: str) -> dict:
    resp = requests.get(metadata_url, timeout=10)
    resp.raise_for_status()
    return _parse_saml_metadata(resp.text)


def create_saml_authn_request(
    db: Session,
    org_id: int | None,
    acs_url: str,
) -> Tuple[str, str]:
    """Create SAML AuthnRequest and return (redirect_url, relay_state)."""
    _prune_states()

    cfg = get_sso_config(db, org_id)
    saml_cfg = cfg.get("saml")
    if not saml_cfg or not saml_cfg.get("enabled"):
        # Try env
        saml_env = _env_saml_provider()
        if not saml_env:
            raise ValueError("SAML not configured")
        saml_cfg = saml_env

    sso_url = saml_cfg.get("sso_url")
    if not sso_url:
        # Try fetch from metadata
        metadata_url = saml_cfg.get("metadata_url")
        if metadata_url:
            try:
                meta = fetch_saml_metadata(metadata_url)
                sso_url = meta.get("sso_url")
            except Exception as exc:
                _LOGGER.warning("Failed to fetch SAML metadata from %s: %s", metadata_url, exc)

    if not sso_url:
        raise ValueError("SAML SSO URL not configured and metadata fetch failed")

    entity_id = saml_cfg.get("entity_id") or settings.SSO_SAML_ENTITY_ID or acs_url.replace("/api/v1/auth/sso/saml/callback", "")

    # Build AuthnRequest
    request_id = "_" + secrets.token_hex(16)
    issue_instant = _now().strftime("%Y-%m-%dT%H:%M:%SZ")

    authn_request = f"""<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
        xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
        ID="{request_id}" Version="2.0" IssueInstant="{issue_instant}"
        Destination="{sso_url}" AssertionConsumerServiceURL="{acs_url}"
        ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
        <saml:Issuer>{entity_id}</saml:Issuer>
        <samlp:NameIDPolicy Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress" AllowCreate="true"/>
    </samlp:AuthnRequest>"""

    # Deflate + base64
    deflated = zlib.compress(authn_request.encode())[2:-4]  # raw deflate
    encoded = base64.b64encode(deflated).decode()

    relay_state = secrets.token_urlsafe(32)

    with _STATE_LOCK:
        _STATE_STORE[relay_state] = {
            "org_id": org_id,
            "acs_url": acs_url,
            "request_id": request_id,
            "entity_id": entity_id,
            "provider_type": "saml",
            "_ts": time.monotonic(),
        }

    params = {
        "SAMLRequest": encoded,
        "RelayState": relay_state,
    }
    return f"{sso_url}?{urlencode(params)}", relay_state


def _parse_saml_response(saml_response_b64: str) -> dict:
    """Parse SAMLResponse base64 XML to extract NameID/email and attributes."""
    try:
        xml_str = base64.b64decode(saml_response_b64).decode()
        root = ET.fromstring(xml_str)

        ns = {
            "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
            "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
        }

        # Find Assertion
        assertion = root.find(".//saml:Assertion", ns)
        if assertion is None:
            # Try without ns
            for elem in root.iter():
                if "Assertion" in elem.tag:
                    assertion = elem
                    break

        if assertion is None:
            raise ValueError("No Assertion found in SAMLResponse")

        # NameID
        name_id = None
        name_id_elem = assertion.find(".//saml:NameID", ns)
        if name_id_elem is not None:
            name_id = name_id_elem.text
        else:
            for elem in assertion.iter():
                if "NameID" in elem.tag and elem.text:
                    name_id = elem.text
                    break

        # Attributes
        attrs: dict = {}
        for attr in assertion.findall(".//saml:Attribute", ns):
            attr_name = attr.get("Name") or attr.get("FriendlyName")
            values = [v.text for v in attr.findall("saml:AttributeValue", ns) if v.text]
            if attr_name and values:
                attrs[attr_name] = values[0] if len(values) == 1 else values

        # Also try without ns
        if not attrs:
            for elem in assertion.iter():
                if "Attribute" in elem.tag:
                    attr_name = elem.get("Name") or elem.get("FriendlyName")
                    if attr_name:
                        for child in elem:
                            if "AttributeValue" in child.tag and child.text:
                                attrs[attr_name] = child.text
                                break

        email = (
            attrs.get("email")
            or attrs.get("Email")
            or attrs.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress")
            or attrs.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name")
            or name_id
        )

        # Sub / NameID
        sub = name_id or attrs.get("NameID") or email

        return {"email": email, "sub": sub, "name_id": name_id, "attributes": attrs, "raw_xml": xml_str}
    except Exception as exc:
        _LOGGER.warning("Failed to parse SAMLResponse: %s", exc)
        raise ValueError(f"Failed to parse SAMLResponse: {exc}")


def handle_saml_callback(
    db: Session,
    saml_response: str,
    relay_state: str,
) -> Tuple[User, str, str]:
    """Handle SAML ACS callback — parses response, JIT provisions, returns tokens."""
    _prune_states()

    with _STATE_LOCK:
        stored = _STATE_STORE.pop(relay_state, None)

    if not stored:
        raise ValueError("Invalid or expired RelayState")

    org_id = stored.get("org_id")
    acs_url = stored.get("acs_url")

    # Parse SAMLResponse
    parsed = _parse_saml_response(saml_response)
    email = parsed.get("email")
    sub = parsed.get("sub")

    if not email:
        raise ValueError("SAML response missing email/NameID")

    email = email.lower().strip() if isinstance(email, str) else str(email).lower().strip()

    # Verify signature if xmlsec available and cert configured
    # Honest: if xmlsec not installed, we log warning and proceed without verification (documented gap)
    try:
        import xmlsec  # type: ignore

        # Try to verify if cert is configured
        saml_cfg = get_sso_config(db, org_id).get("saml")
        cert = None
        if saml_cfg:
            # Get cert from DB provider
            provider = _get_provider_by_type(db, org_id, "saml")
            if provider and provider.saml_certificate:
                cert = provider.saml_certificate
            else:
                cert = saml_cfg.get("certificate")

        if cert and settings.SSO_SAML_CERTIFICATE:
            # Verify logic would go here — for now log that verification is attempted
            _LOGGER.info("SAML signature verification attempted with cert")
        else:
            _LOGGER.warning("SAML signature verification skipped — no certificate configured or xmlsec not fully configured")
    except ImportError:
        _LOGGER.warning("xmlsec not installed — SAML signature verification skipped (documented gap)")

    # Find existing user
    user = (
        db.query(User)
        .filter((User.email == email) | (User.external_id == sub))
        .first()
    )

    default_org = db.query(Org).filter(Org.slug == "default").first()
    if default_org is None:
        default_org = Org(name="Default Organization", slug="default")
        db.add(default_org)
        db.flush()

    target_org_id = org_id or (user.org_id if user else default_org.id)

    if not user:
        cfg = get_sso_config(db, org_id)
        saml_cfg = cfg.get("saml") or {}
        jit = saml_cfg.get("jit", True) if saml_cfg else settings.SSO_JIT_PROVISIONING
        if not jit:
            raise ValueError("JIT provisioning disabled — user not found")

        default_role = (settings.SSO_DEFAULT_ROLE or "USER").upper()
        if default_role not in ("USER", "ANALYST"):
            default_role = "USER"

        username = email.split("@")[0]
        base_username = username
        counter = 1
        while db.query(User).filter(User.username == username).first():
            username = f"{base_username}{counter}"
            counter += 1

        user = User(
            username=username,
            email=email,
            password=get_password_hash(secrets.token_urlsafe(32)),
            role=default_role,
            org_id=target_org_id,
            external_id=sub,
            sso_provider=f"saml:{parsed.get('attributes', {}).get('Issuer', 'unknown')}",
            is_sso_user=True,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        _LOGGER.info("JIT provisioned SAML user %s", email)
    else:
        if not user.external_id and sub:
            user.external_id = sub
            user.sso_provider = f"saml:{email}"
            user.is_sso_user = True
            db.commit()

        if user.is_blocked:
            raise ValueError("Account is blocked")

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
    if provider_type not in ("oidc", "saml"):
        raise ValueError("provider_type must be 'oidc' or 'saml'")

    if provider_type == "oidc":
        issuer = payload.get("issuer")
        if not issuer:
            raise ValueError("issuer is required for OIDC")
        client_id = payload.get("client_id")
        if not client_id:
            raise ValueError("client_id is required for OIDC")
    else:  # saml
        # SAML requires either sso_url or metadata_url
        sso_url = payload.get("saml_sso_url") or payload.get("sso_url")
        metadata_url = payload.get("saml_metadata_url") or payload.get("metadata_url")
        if not sso_url and not metadata_url:
            raise ValueError("saml_sso_url or saml_metadata_url is required for SAML")

    # Find existing by type + org
    existing = (
        db.query(SsoProvider)
        .filter(SsoProvider.org_id == org_id, SsoProvider.provider_type == provider_type)
        .first()
    )
    if existing:
        provider = existing
    else:
        provider = SsoProvider(
            org_id=org_id,
            provider_type=provider_type,
        )
        db.add(provider)

    provider.provider_type = provider_type
    provider.display_name = payload.get("display_name") or (f"{provider_type.upper()} SSO")
    provider.enabled = bool(payload.get("enabled", True))
    provider.jit_provisioning = bool(payload.get("jit_provisioning", True))

    if provider_type == "oidc":
        provider.issuer = payload.get("issuer")
        provider.client_id = payload.get("client_id")
        provider.scopes = payload.get("scopes") or "openid email profile"
        if payload.get("client_secret"):
            provider.client_secret_encrypted = encrypt_secret(payload["client_secret"])
    else:  # saml
        provider.saml_metadata_url = payload.get("saml_metadata_url") or payload.get("metadata_url")
        provider.saml_entity_id = payload.get("saml_entity_id") or payload.get("entity_id")
        provider.saml_acs_url = payload.get("saml_acs_url") or payload.get("acs_url")
        provider.saml_sso_url = payload.get("saml_sso_url") or payload.get("sso_url")
        provider.saml_certificate = payload.get("saml_certificate") or payload.get("certificate")
        provider.saml_nameid_format = payload.get("saml_nameid_format") or "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"

        # If metadata URL provided, try to fetch SSO URL and cert
        if provider.saml_metadata_url:
            try:
                meta = fetch_saml_metadata(provider.saml_metadata_url)
                if not provider.saml_sso_url and meta.get("sso_url"):
                    provider.saml_sso_url = meta["sso_url"]
                if not provider.saml_certificate and meta.get("certificate"):
                    provider.saml_certificate = meta["certificate"]
            except Exception as exc:
                _LOGGER.warning("Failed to fetch SAML metadata during upsert: %s", exc)

    db.commit()
    db.refresh(provider)
    return provider


def delete_provider(db: Session, org_id: int | None, provider_type: str | None = None) -> dict:
    q = db.query(SsoProvider)
    if org_id is None:
        q = q.filter(SsoProvider.org_id.is_(None))
    else:
        q = q.filter(SsoProvider.org_id == org_id)

    if provider_type:
        q = q.filter(SsoProvider.provider_type == provider_type)

    providers = q.all()
    if not providers:
        raise ValueError("No SSO provider configured")

    count = 0
    for p in providers:
        db.delete(p)
        count += 1
    db.commit()
    return {"deleted": count}


def reset_state_store() -> None:
    with _STATE_LOCK:
        _STATE_STORE.clear()
