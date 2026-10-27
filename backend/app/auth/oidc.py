"""OpenID Connect sign-in (FR-43): authorization code flow with PKCE.

The deployment's identity provider authenticates the person; this module decides
whether the answer is trustworthy and who it names. Every check below is a
separate, tested rule, because each one closes a known way that OIDC
integrations are broken in practice:

* **Authorization code with PKCE (S256).** The code is useless without the
  verifier, which never leaves this process, so an intercepted redirect cannot
  be redeemed by another client.
* **Single-use, expiring state.** ``state`` binds the callback to a login this
  process started (CSRF). It is removed on first use, so a replayed callback
  fails, and it expires after ``state_ttl_seconds``.
* **Nonce.** The ID token must echo the nonce from the authorization request, so
  a token minted for another login cannot be substituted into this one.
* **Algorithm allowlist.** Only asymmetric algorithms named in configuration are
  accepted. ``none`` is refused, and HS256 is refused, which closes the classic
  attack where a public key is presented as an HMAC secret.
* **Issuer, audience and ``azp``.** The token must be issued by the configured
  issuer (exact match against discovery) and be addressed to this client.
* **Verified email only.** Identity is matched on ``email`` and only when the
  provider asserts ``email_verified`` as the boolean ``true``.

What this module does *not* decide is authority. Roles come from the local
account store, never from IdP claims, and sign-in is refused for an email with
no active local account (no just-in-time provisioning). An IdP that reassigns an
email address to a new person can therefore reach the account of the old one; the
remedy is binding the account to the ``sub`` claim on first sign-in, which needs
persistent storage and is recorded as a gap in memory.md, not silently assumed.

The state store is in process. A multi-replica deployment needs sticky sessions
or a shared store behind the same interface; that is deployment configuration,
named here rather than implied.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

__all__ = [
    "OidcConfig",
    "OidcError",
    "OidcRejected",
    "OidcSignIn",
    "OidcUnavailable",
    "PendingLogin",
    "PendingLoginStore",
    "generate_pkce",
    "verified_email",
]

#: Algorithms accepted when the deployment names none. Asymmetric only.
DEFAULT_ALGORITHMS: tuple[str, ...] = ("RS256", "ES256")
#: Algorithms that are never accepted, whatever the configuration says.
FORBIDDEN_ALGORITHMS: frozenset[str] = frozenset({"none", "HS256", "HS384", "HS512"})
#: Minimum gap between forced JWKS refetches.
_JWKS_REFRESH_FLOOR_SECONDS = 30.0


class OidcError(Exception):
    """Base class for sign-in failures. The message is for logs, never for clients."""


class OidcUnavailable(OidcError):
    """The identity provider could not be reached or returned something unusable (502)."""


class OidcRejected(OidcError):
    """The identity provider's answer failed a check (401 or 403 at the edge)."""


@dataclass(frozen=True, slots=True)
class OidcConfig:
    """What this deployment needs to talk to exactly one identity provider."""

    issuer: str
    client_id: str
    client_secret: str = field(repr=False)
    redirect_uri: str
    scopes: tuple[str, ...] = ("openid", "email", "profile")
    algorithms: tuple[str, ...] = DEFAULT_ALGORITHMS
    leeway_seconds: int = 60
    state_ttl_seconds: int = 600
    discovery_ttl_seconds: int = 3600
    jwks_ttl_seconds: int = 300
    http_timeout_seconds: float = 5.0
    max_pending_logins: int = 10_000

    def __post_init__(self) -> None:
        """Refuse configurations that would weaken a check below."""
        if not self.issuer or not self.client_id or not self.redirect_uri:
            raise ValueError("issuer, client_id and redirect_uri are required")
        if not self.client_secret:
            raise ValueError("client_secret is required for the confidential client")
        if "openid" not in self.scopes:
            raise ValueError("scopes must include 'openid'")
        if not self.algorithms:
            raise ValueError("at least one signing algorithm must be allowed")
        forbidden = FORBIDDEN_ALGORITHMS.intersection(self.algorithms)
        if forbidden:
            raise ValueError(f"signing algorithms not permitted: {sorted(forbidden)}")
        if self.leeway_seconds < 0 or self.leeway_seconds > 300:
            raise ValueError("leeway_seconds must be between 0 and 300")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_pkce() -> tuple[str, str]:
    """Return ``(verifier, challenge)`` for the S256 method (RFC 7636)."""
    verifier = secrets.token_urlsafe(64)  # 86 characters, inside the 43-128 range
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


@dataclass(frozen=True, slots=True)
class PendingLogin:
    """What a sign-in started by this process must carry to its callback."""

    state: str = field(repr=False)
    nonce: str = field(repr=False)
    verifier: str = field(repr=False)
    created_at: float = 0.0


class PendingLoginStore:
    """Single-use, expiring record of sign-ins this process has started.

    ``take`` removes the entry, so a callback can be redeemed once. Expired and
    excess entries are dropped, so a flood of abandoned starts cannot grow the
    store without bound.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int,
        max_entries: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Bound the store by age and by count; ``clock`` is injectable for tests."""
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock
        self._entries: dict[str, PendingLogin] = {}
        self._lock = threading.Lock()

    def create(self) -> PendingLogin:
        """Start a sign-in: fresh state, nonce and PKCE verifier."""
        pending = PendingLogin(
            state=secrets.token_urlsafe(32),
            nonce=secrets.token_urlsafe(32),
            verifier=generate_pkce()[0],
            created_at=self._clock(),
        )
        with self._lock:
            self._prune_locked(self._clock())
            while len(self._entries) >= self._max:
                # Dict order is insertion order, so this drops the oldest entry.
                del self._entries[next(iter(self._entries))]
            self._entries[pending.state] = pending
        return pending

    def take(self, state: str) -> PendingLogin | None:
        """Remove and return the pending login for ``state``, or None if unusable."""
        now = self._clock()
        with self._lock:
            pending = self._entries.pop(state, None)
            self._prune_locked(now)
        if pending is None or now - pending.created_at > self._ttl:
            return None
        return pending

    def __len__(self) -> int:
        """How many sign-ins are waiting for a callback."""
        with self._lock:
            return len(self._entries)

    def _prune_locked(self, now: float) -> None:
        """Drop entries older than the TTL. The caller holds the lock."""
        expired = [s for s, p in self._entries.items() if now - p.created_at > self._ttl]
        for state in expired:
            del self._entries[state]


def verified_email(claims: dict[str, Any]) -> str:
    """The email the provider vouches for, or :class:`OidcRejected`.

    Only the boolean ``true`` counts. A string ``"true"`` or a missing claim is
    refused, because accepting an unverified address is an account-takeover path.
    """
    email = claims.get("email")
    if not isinstance(email, str) or not email.strip():
        raise OidcRejected("id token has no email claim")
    if claims.get("email_verified") is not True:
        raise OidcRejected("email is not verified by the identity provider")
    return email.strip()


class OidcSignIn:
    """One identity provider, its cached metadata and keys, and the sign-in steps.

    ``transport`` exists so tests can run a mock issuer; production passes
    nothing and gets httpx's default network transport.
    """

    def __init__(
        self,
        config: OidcConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create the client; no network call happens until the first sign-in."""
        self.config = config
        self.store = PendingLoginStore(
            ttl_seconds=config.state_ttl_seconds,
            max_entries=config.max_pending_logins,
            clock=clock,
        )
        self._http = httpx.Client(
            timeout=config.http_timeout_seconds,
            transport=transport,
            follow_redirects=False,
            headers={"Accept": "application/json"},
        )
        self._clock = clock
        self._lock = threading.Lock()
        self._discovery: dict[str, Any] | None = None
        self._discovery_at = 0.0
        self._jwks: jwt.PyJWKSet | None = None
        self._jwks_at = 0.0

    # -- metadata -------------------------------------------------------------

    def discovery(self) -> dict[str, Any]:
        """The provider's metadata, fetched and checked against the issuer."""
        with self._lock:
            now = self._clock()
            if self._discovery is not None and now - self._discovery_at < (
                self.config.discovery_ttl_seconds
            ):
                return self._discovery
        url = self.config.issuer.rstrip("/") + "/.well-known/openid-configuration"
        doc = self._get_json(url)
        if doc.get("issuer") != self.config.issuer:
            raise OidcUnavailable("discovery document names a different issuer")
        for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            value = doc.get(key)
            if not isinstance(value, str) or not value.startswith("https://"):
                raise OidcUnavailable(f"discovery document has no https {key}")
        with self._lock:
            self._discovery = doc
            self._discovery_at = self._clock()
        return doc

    def _signing_keys(self, *, force: bool = False) -> jwt.PyJWKSet:
        """Return the provider's keys, cached.

        ``force`` refetches for key rotation, at most once per
        ``_JWKS_REFRESH_FLOOR_SECONDS``, so bogus ``kid`` values cannot make this
        process hammer the provider.
        """
        with self._lock:
            now = self._clock()
            age = now - self._jwks_at
            keys = self._jwks
            fresh = keys is not None and age < self.config.jwks_ttl_seconds
            if keys is not None and fresh and (not force or age < _JWKS_REFRESH_FLOOR_SECONDS):
                return keys
        doc = self._get_json(str(self.discovery()["jwks_uri"]))
        try:
            keys = jwt.PyJWKSet.from_dict(doc)
        except (jwt.PyJWKError, jwt.PyJWKSetError, ValueError, TypeError) as exc:
            raise OidcUnavailable("jwks document is unusable") from exc
        with self._lock:
            self._jwks = keys
            self._jwks_at = self._clock()
        return keys

    def _get_json(self, url: str) -> dict[str, Any]:
        """GET a JSON object from the provider, or raise :class:`OidcUnavailable`."""
        try:
            response = self._http.get(url)
        except httpx.HTTPError as exc:
            raise OidcUnavailable(f"identity provider unreachable: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise OidcUnavailable(f"identity provider returned HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            raise OidcUnavailable("identity provider returned non-JSON") from exc
        if not isinstance(body, dict):
            raise OidcUnavailable("identity provider returned a non-object document")
        return body

    # -- the sign-in steps ----------------------------------------------------

    def authorization_url(self, pending: PendingLogin) -> str:
        """Where to send the browser to sign in. The challenge is derived from the verifier."""
        challenge = _b64url(hashlib.sha256(pending.verifier.encode("ascii")).digest())
        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": " ".join(self.config.scopes),
            "state": pending.state,
            "nonce": pending.nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{self.discovery()['authorization_endpoint']}?{urlencode(params)}"

    def exchange_code(self, code: str, pending: PendingLogin) -> str:
        """Redeem the authorization code and return the raw ID token."""
        endpoint = str(self.discovery()["token_endpoint"])
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "code_verifier": pending.verifier,
        }
        try:
            response = self._http.post(endpoint, data=form)
        except httpx.HTTPError as exc:
            raise OidcUnavailable(f"token endpoint unreachable: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise OidcRejected(f"token endpoint refused the code (HTTP {response.status_code})")
        try:
            body = response.json()
        except ValueError as exc:
            raise OidcRejected("token endpoint returned non-JSON") from exc
        id_token = body.get("id_token") if isinstance(body, dict) else None
        if not isinstance(id_token, str) or not id_token:
            raise OidcRejected("token response carries no id_token")
        return id_token

    def verify_id_token(self, token: str, *, nonce: str) -> dict[str, Any]:
        """Return the verified claims of ``token``, or raise :class:`OidcRejected`."""
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            raise OidcRejected("id token is malformed") from exc
        alg = header.get("alg")
        if alg not in self.config.algorithms:
            raise OidcRejected(f"id token signed with a disallowed algorithm: {alg!r}")
        key = self._key_for(header.get("kid"))
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,
                algorithms=list(self.config.algorithms),
                audience=self.config.client_id,
                issuer=self.config.issuer,
                leeway=self.config.leeway_seconds,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.InvalidTokenError as exc:
            raise OidcRejected(f"id token failed verification: {type(exc).__name__}") from exc
        audiences = claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]]
        if len(audiences) > 1 and claims.get("azp") != self.config.client_id:
            raise OidcRejected("multi-audience id token without matching azp")
        if "azp" in claims and claims["azp"] != self.config.client_id:
            raise OidcRejected("id token azp names another client")
        supplied = claims.get("nonce")
        if not isinstance(supplied, str) or not hmac.compare_digest(supplied, nonce):
            raise OidcRejected("id token nonce does not match this sign-in")
        return claims

    def _key_for(self, kid: object) -> Any:
        """Find the signing key, refreshing the JWKS once if the key is new (rotation)."""
        for force in (False, True):
            keys = self._signing_keys(force=force)
            candidates = [k for k in keys.keys if kid is None or k.key_id == kid]
            if len(candidates) == 1 and (kid is not None or len(keys.keys) == 1):
                return candidates[0].key
        raise OidcRejected("no signing key matches the id token")

    def complete(self, code: str, pending: PendingLogin) -> dict[str, Any]:
        """Exchange, verify and return claims. The caller owns the local account decision."""
        id_token = self.exchange_code(code, pending)
        return self.verify_id_token(id_token, nonce=pending.nonce)
