"""OpenID Connect sign-in (FR-43), tested against a mock issuer with a real RSA key.

Nothing here reaches the network. The mock issuer answers discovery, JWKS and the
token endpoint through httpx's MockTransport, so the signature path, the key
selection and the claim checks run for real, against tokens the tests mint. The
attack cases are crafted by hand: an ``alg: none`` token, a key-confusion HS256
token built from the public key, a token signed by a different key, and so on.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from app.auth.oidc import (
    OidcConfig,
    OidcRejected,
    OidcSignIn,
    OidcUnavailable,
    PendingLogin,
    PendingLoginStore,
    generate_pkce,
    verified_email,
)
from app.core.config import Environment, Settings
from app.main import build_oidc_sign_in, create_app
from app.services.audit_log import AuditAction
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

ISSUER = "https://idp.test"
CLIENT_ID = "aegis-console"
CLIENT_SECRET = "oidc-client-secret-for-tests-0123456789"  # pragma: allowlist secret
REDIRECT = "https://aegis.test/api/v1/auth/oidc/callback"
SECRET = "auth-test-signing-key-with-enough-entropy-2026"  # pragma: allowlist secret
PASSWORD = "a-strong-test-password-for-auth"  # pragma: allowlist secret
ADMIN_EMAIL = "operator@localhost"
ADMIN_SUB = "00u-operator"


def _config(**overrides: Any) -> OidcConfig:
    values: dict[str, Any] = {
        "issuer": ISSUER,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT,
    }
    values.update(overrides)
    return OidcConfig(**values)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class MockIssuer:
    """A minimal OpenID provider: discovery, JWKS and a token endpoint."""

    def __init__(self) -> None:
        """Start with one published RSA key and a healthy provider."""
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "key-1"
        self.published: list[tuple[str, Any]] = [(self.kid, self.key)]
        self.nonce = ""
        self.email: str | None = ADMIN_EMAIL
        self.email_verified: Any = True
        self.token_status = 200
        self.token_body: dict[str, Any] | None = None
        self.discovery_issuer = ISSUER
        self.jwks_uri = ISSUER + "/jwks"
        self.jwks_fetches = 0
        self.unreachable = False
        self.token_requests: list[dict[str, str]] = []

    # -- minting --------------------------------------------------------------

    def claims(self, **overrides: Any) -> dict[str, Any]:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": ADMIN_SUB,
            "iat": now,
            "exp": now + 300,
            "nonce": self.nonce,
            "email": self.email,
            "email_verified": self.email_verified,
        }
        for name, value in overrides.items():
            if value is _DROP:
                claims.pop(name, None)
            else:
                claims[name] = value
        return claims

    def mint(self, key: Any = None, kid: str | None = None, **overrides: Any) -> str:
        return jwt.encode(
            self.claims(**overrides),
            key if key is not None else self.key,
            algorithm="RS256",
            headers={"kid": self.kid if kid is None else kid},
        )

    def jwks(self) -> dict[str, Any]:
        keys = []
        for kid, key in self.published:
            jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
            jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
            keys.append(jwk)
        return {"keys": keys}

    # -- transport ------------------------------------------------------------

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.unreachable:
            raise httpx.ConnectError("identity provider is down", request=request)
        path = request.url.path
        if path == "/.well-known/openid-configuration":
            return httpx.Response(
                200,
                json={
                    "issuer": self.discovery_issuer,
                    "authorization_endpoint": ISSUER + "/authorize",
                    "token_endpoint": ISSUER + "/token",
                    "jwks_uri": self.jwks_uri,
                },
            )
        if path == "/jwks":
            self.jwks_fetches += 1
            return httpx.Response(200, json=self.jwks())
        if path == "/token":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            self.token_requests.append(form)
            if self.token_body is not None:
                return httpx.Response(self.token_status, json=self.token_body)
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"id_token": self.mint(), "token_type": "Bearer"})
        return httpx.Response(404)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)


_DROP = object()


@pytest.fixture
def issuer() -> MockIssuer:
    return MockIssuer()


@pytest.fixture
def oidc(issuer: MockIssuer) -> OidcSignIn:
    return OidcSignIn(_config(), transport=issuer.transport)


def _pending(oidc: OidcSignIn, issuer: MockIssuer) -> PendingLogin:
    pending = oidc.store.create()
    issuer.nonce = pending.nonce
    return pending


# -- configuration and small rules ----------------------------------------------


def test_pkce_challenge_matches_the_rfc_7636_vector() -> None:
    # RFC 7636, appendix B: a published test vector, not a credential.
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"  # pragma: allowlist secret
    pending = PendingLogin(state="s", nonce="n", verifier=verifier)
    # Serve a real discovery document. Setting ``_discovery`` directly relied on the
    # cache's timestamp being fresh, which depends on the wall clock; the transport
    # answers the request whatever the clock says.
    discovery = {
        "issuer": ISSUER,
        "authorization_endpoint": ISSUER + "/authorize",
        "token_endpoint": ISSUER + "/token",
        "jwks_uri": ISSUER + "/jwks",
    }
    oidc = OidcSignIn(
        _config(),
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=discovery)),
    )
    query = parse_qs(urlsplit(oidc.authorization_url(pending)).query)
    assert query["code_challenge"] == [
        "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"  # pragma: allowlist secret
    ]
    assert query["code_challenge_method"] == ["S256"]


def test_generated_pkce_pair_is_consistent_and_fresh() -> None:
    verifier, challenge = generate_pkce()
    assert 43 <= len(verifier) <= 128
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    assert challenge == expected.rstrip(b"=").decode()
    assert generate_pkce()[0] != verifier


@pytest.mark.parametrize(
    "overrides",
    [
        {"algorithms": ("HS256",)},
        {"algorithms": ("none",)},
        {"algorithms": ()},
        {"scopes": ("email",)},
        {"client_secret": ""},
        {"issuer": ""},
        {"leeway_seconds": 301},
    ],
)
def test_config_refuses_unsafe_or_incomplete_values(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        _config(**overrides)


def test_client_secret_is_not_shown_in_repr() -> None:
    assert CLIENT_SECRET not in repr(_config())


def test_pending_login_is_single_use() -> None:
    store = PendingLoginStore(ttl_seconds=60, max_entries=10)
    pending = store.create()
    assert store.take(pending.state) is not None
    assert store.take(pending.state) is None


def test_pending_login_expires() -> None:
    now = [1000.0]
    store = PendingLoginStore(ttl_seconds=60, max_entries=10, clock=lambda: now[0])
    pending = store.create()
    now[0] += 61
    assert store.take(pending.state) is None


def test_pending_store_is_bounded_and_drops_the_oldest() -> None:
    store = PendingLoginStore(ttl_seconds=600, max_entries=2)
    first, second, third = store.create(), store.create(), store.create()
    assert len(store) == 2
    assert store.take(first.state) is None
    assert store.take(second.state) is not None
    assert store.take(third.state) is not None


def test_verified_email_accepts_only_the_boolean_true() -> None:
    assert verified_email({"email": " a@b.test ", "email_verified": True}) == "a@b.test"
    for claims in (
        {"email": "a@b.test", "email_verified": "true"},
        {"email": "a@b.test", "email_verified": False},
        {"email": "a@b.test"},
        {"email_verified": True},
        {"email": "", "email_verified": True},
    ):
        with pytest.raises(OidcRejected):
            verified_email(claims)


# -- token verification ---------------------------------------------------------


def test_valid_id_token_yields_its_claims(oidc: OidcSignIn, issuer: MockIssuer) -> None:
    pending = _pending(oidc, issuer)
    claims = oidc.verify_id_token(issuer.mint(), nonce=pending.nonce)
    assert claims["sub"] == ADMIN_SUB
    assert claims["email"] == ADMIN_EMAIL


@pytest.mark.parametrize(
    "override",
    [
        {"iss": "https://evil.test"},
        {"aud": "some-other-client"},
        {"exp": int(time.time()) - 3600},
        {"iat": int(time.time()) + 3600},
        {"sub": _DROP},
        {"nonce": "a-nonce-from-another-login"},
        {"nonce": _DROP},
        {"azp": "some-other-client"},
    ],
)
def test_claim_violations_are_rejected(
    oidc: OidcSignIn, issuer: MockIssuer, override: dict[str, Any]
) -> None:
    pending = _pending(oidc, issuer)
    with pytest.raises(OidcRejected):
        oidc.verify_id_token(issuer.mint(**override), nonce=pending.nonce)


def test_multi_audience_token_needs_a_matching_azp(oidc: OidcSignIn, issuer: MockIssuer) -> None:
    pending = _pending(oidc, issuer)
    with pytest.raises(OidcRejected):
        oidc.verify_id_token(issuer.mint(aud=[CLIENT_ID, "other"]), nonce=pending.nonce)
    accepted = oidc.verify_id_token(
        issuer.mint(aud=[CLIENT_ID, "other"], azp=CLIENT_ID), nonce=pending.nonce
    )
    assert accepted["azp"] == CLIENT_ID


def test_unsigned_alg_none_token_is_rejected(oidc: OidcSignIn, issuer: MockIssuer) -> None:
    pending = _pending(oidc, issuer)
    header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    body = _b64(json.dumps(issuer.claims()).encode())
    with pytest.raises(OidcRejected):
        oidc.verify_id_token(f"{header}.{body}.", nonce=pending.nonce)


def test_hs256_key_confusion_with_the_public_key_is_rejected(
    oidc: OidcSignIn, issuer: MockIssuer
) -> None:
    """The classic attack: sign HS256 with the published public key as the HMAC secret."""
    pending = _pending(oidc, issuer)
    public_pem = issuer.key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    # PyJWT will not sign HS256 with a public key, so the forgery is built by hand.
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": issuer.kid}).encode())
    body = _b64(json.dumps(issuer.claims()).encode())
    signing_input = f"{header}.{body}".encode()
    forged = f"{header}.{body}.{_b64(hmac.new(public_pem, signing_input, hashlib.sha256).digest())}"
    with pytest.raises(OidcRejected, match="disallowed algorithm"):
        oidc.verify_id_token(forged, nonce=pending.nonce)


def test_token_signed_by_an_unpublished_key_is_rejected(
    oidc: OidcSignIn, issuer: MockIssuer
) -> None:
    pending = _pending(oidc, issuer)
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(OidcRejected):
        oidc.verify_id_token(issuer.mint(key=attacker), nonce=pending.nonce)


def test_key_rotation_is_picked_up_after_the_refresh_floor(issuer: MockIssuer) -> None:
    now = [1000.0]
    oidc = OidcSignIn(_config(), transport=issuer.transport, clock=lambda: now[0])
    pending = _pending(oidc, issuer)
    oidc.verify_id_token(issuer.mint(), nonce=pending.nonce)
    now[0] += 31  # past the floor, so a new kid may trigger a refetch
    rotated = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer.published = [("key-2", rotated)]
    issuer.kid = "key-2"
    claims = oidc.verify_id_token(issuer.mint(key=rotated), nonce=pending.nonce)
    assert claims["sub"] == ADMIN_SUB


def test_unknown_kid_refetches_jwks_at_most_once_per_floor(
    oidc: OidcSignIn, issuer: MockIssuer
) -> None:
    pending = _pending(oidc, issuer)
    oidc.verify_id_token(issuer.mint(), nonce=pending.nonce)
    before = issuer.jwks_fetches
    for _ in range(5):
        with pytest.raises(OidcRejected):
            oidc.verify_id_token(issuer.mint(kid="attacker-chosen"), nonce=pending.nonce)
    assert issuer.jwks_fetches - before <= 1


# -- the provider, and its failure modes ----------------------------------------


def test_discovery_must_name_the_configured_issuer(issuer: MockIssuer) -> None:
    issuer.discovery_issuer = "https://impostor.test"
    oidc = OidcSignIn(_config(), transport=issuer.transport)
    with pytest.raises(OidcUnavailable, match="different issuer"):
        oidc.discovery()


def test_non_https_endpoints_are_refused(issuer: MockIssuer) -> None:
    issuer.jwks_uri = "http://idp.test/jwks"
    oidc = OidcSignIn(_config(), transport=issuer.transport)
    with pytest.raises(OidcUnavailable, match="https jwks_uri"):
        oidc.discovery()


def test_unreachable_provider_is_unavailable_not_a_crash(issuer: MockIssuer) -> None:
    issuer.unreachable = True
    oidc = OidcSignIn(_config(), transport=issuer.transport)
    with pytest.raises(OidcUnavailable, match="unreachable"):
        oidc.discovery()


def test_token_endpoint_refusal_is_rejected(oidc: OidcSignIn, issuer: MockIssuer) -> None:
    pending = _pending(oidc, issuer)
    issuer.token_status = 400
    with pytest.raises(OidcRejected, match="refused the code"):
        oidc.exchange_code("code", pending)


def test_token_response_without_an_id_token_is_rejected(
    oidc: OidcSignIn, issuer: MockIssuer
) -> None:
    pending = _pending(oidc, issuer)
    issuer.token_body = {"access_token": "x"}
    with pytest.raises(OidcRejected, match="no id_token"):
        oidc.exchange_code("code", pending)


def test_code_exchange_sends_the_pkce_verifier_that_matches_the_challenge(
    oidc: OidcSignIn, issuer: MockIssuer
) -> None:
    pending = _pending(oidc, issuer)
    query = parse_qs(urlsplit(oidc.authorization_url(pending)).query)
    oidc.exchange_code("the-code", pending)
    sent = issuer.token_requests[-1]
    assert sent["code_verifier"] == pending.verifier
    assert sent["client_secret"] == CLIENT_SECRET
    assert sent["grant_type"] == "authorization_code"
    recomputed = base64.urlsafe_b64encode(
        hashlib.sha256(sent["code_verifier"].encode()).digest()
    ).rstrip(b"=")
    assert recomputed.decode() == query["code_challenge"][0]


def test_complete_returns_verified_claims_end_to_end(oidc: OidcSignIn, issuer: MockIssuer) -> None:
    pending = _pending(oidc, issuer)
    claims = oidc.complete("code", pending)
    assert verified_email(claims) == ADMIN_EMAIL


# -- wiring ---------------------------------------------------------------------


def test_oidc_is_off_by_default_and_builds_nothing() -> None:
    assert build_oidc_sign_in(Settings(env=Environment.TEST, secret_key=SECRET)) is None


def test_enabling_oidc_requires_every_connection_setting() -> None:
    with pytest.raises(ValidationError, match="AEGIS_OIDC_ENABLED requires"):
        Settings(env=Environment.TEST, secret_key=SECRET, oidc_enabled=True)


def test_enabling_oidc_outside_development_requires_https() -> None:
    with pytest.raises(ValidationError, match="must be an https URL"):
        Settings(
            env=Environment.PRODUCTION,
            secret_key=SECRET,
            bootstrap_admin_email="a@b.test",
            bootstrap_admin_password="a-strong-test-password",  # pragma: allowlist secret
            oidc_enabled=True,
            oidc_issuer="http://idp.test",
            oidc_client_id=CLIENT_ID,
            oidc_client_secret=CLIENT_SECRET,
            oidc_redirect_uri=REDIRECT,
        )


# -- end to end through the application -----------------------------------------


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "env": Environment.TEST,
        "secret_key": SECRET,
        "bootstrap_admin_email": ADMIN_EMAIL,
        "bootstrap_admin_password": PASSWORD,
    }
    values.update(overrides)
    return Settings(**values)


def _oidc_settings() -> dict[str, Any]:
    return {
        "oidc_enabled": True,
        "oidc_issuer": ISSUER,
        "oidc_client_id": CLIENT_ID,
        "oidc_client_secret": CLIENT_SECRET,
        "oidc_redirect_uri": REDIRECT,
    }


def _app(issuer: MockIssuer, **overrides: Any) -> FastAPI:
    app = create_app(_settings(**_oidc_settings(), **overrides))
    app.state.oidc = OidcSignIn(_config(), transport=issuer.transport)
    return app


def _start(client: TestClient, issuer: MockIssuer) -> dict[str, list[str]]:
    response = client.get("/api/v1/auth/oidc/start", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["cache-control"] == "no-store"
    query = parse_qs(urlsplit(response.headers["location"]).query)
    issuer.nonce = query["nonce"][0]
    return query


def _audit_actions(app: FastAPI) -> list[AuditAction]:
    from datetime import UTC, datetime

    entries = app.state.audit_trail.entries(
        start=datetime.min.replace(tzinfo=UTC), end=datetime.max.replace(tzinfo=UTC)
    )
    return [entry.record.action for entry in reversed(entries)]


def test_routes_are_404_when_oidc_is_disabled() -> None:
    app = create_app(_settings())
    with TestClient(app) as client:
        assert client.get("/api/v1/auth/oidc/start").status_code == 404
        assert client.get("/api/v1/auth/oidc/callback?code=x&state=y").status_code == 404


def test_full_sign_in_issues_the_same_session_a_password_login_does(
    issuer: MockIssuer,
) -> None:
    app = _app(issuer)
    with TestClient(app) as client:
        query = _start(client, issuer)
        assert query["code_challenge_method"] == ["S256"]
        assert query["scope"] == ["openid email profile"]
        response = client.get(
            "/api/v1/auth/oidc/callback",
            params={"code": "the-code", "state": query["state"][0]},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["subject"] == ADMIN_EMAIL
        assert body["role"] == "admin"
        assert response.headers["cache-control"] == "no-store"
        access = {"Authorization": f"Bearer {body['access_token']}"}
        assert client.get("/api/v1/models", headers=access).status_code == 200
        assert AuditAction.auth_login in _audit_actions(app)


def test_a_callback_can_be_redeemed_only_once(issuer: MockIssuer) -> None:
    app = _app(issuer)
    with TestClient(app) as client:
        state = _start(client, issuer)["state"][0]
        first = client.get("/api/v1/auth/oidc/callback", params={"code": "c", "state": state})
        replay = client.get("/api/v1/auth/oidc/callback", params={"code": "c", "state": state})
        assert first.status_code == 200
        assert replay.status_code == 401


def test_unknown_state_is_refused_before_any_exchange(issuer: MockIssuer) -> None:
    app = _app(issuer)
    with TestClient(app) as client:
        response = client.get("/api/v1/auth/oidc/callback", params={"code": "c", "state": "forged"})
        assert response.status_code == 401
        assert issuer.token_requests == []


def test_a_consumed_state_is_not_revived_by_a_failed_verification(issuer: MockIssuer) -> None:
    app = _app(issuer)
    with TestClient(app) as client:
        state = _start(client, issuer)["state"][0]
        issuer.email_verified = False
        refused = client.get("/api/v1/auth/oidc/callback", params={"code": "c", "state": state})
        issuer.email_verified = True
        retried = client.get("/api/v1/auth/oidc/callback", params={"code": "c", "state": state})
        assert refused.status_code == 401
        assert retried.status_code == 401


def test_provider_error_parameter_is_refused_without_detail(issuer: MockIssuer) -> None:
    app = _app(issuer)
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/auth/oidc/callback", params={"error": "access_denied", "state": "x"}
        )
        assert response.status_code == 401
        assert "access_denied" not in response.text


def test_missing_code_or_state_is_a_bad_request(issuer: MockIssuer) -> None:
    app = _app(issuer)
    with TestClient(app) as client:
        assert client.get("/api/v1/auth/oidc/callback").status_code == 400
        assert client.get("/api/v1/auth/oidc/callback?code=c").status_code == 400


def test_unverified_email_is_refused(issuer: MockIssuer) -> None:
    app = _app(issuer)
    with TestClient(app) as client:
        state = _start(client, issuer)["state"][0]
        issuer.email_verified = "true"  # a string is not verification
        response = client.get("/api/v1/auth/oidc/callback", params={"code": "c", "state": state})
        assert response.status_code == 401


def test_verified_identity_with_no_local_account_creates_nothing(issuer: MockIssuer) -> None:
    app = _app(issuer)
    issuer.email = "stranger@elsewhere.test"
    with TestClient(app) as client:
        state = _start(client, issuer)["state"][0]
        response = client.get("/api/v1/auth/oidc/callback", params={"code": "c", "state": state})
        assert response.status_code == 403
        assert "access_token" not in response.text
        assert app.state.auth_accounts.active_account("stranger@elsewhere.test") is None


def test_unreachable_provider_at_start_is_502(issuer: MockIssuer) -> None:
    app = _app(issuer)
    issuer.unreachable = True
    with TestClient(app) as client:
        assert client.get("/api/v1/auth/oidc/start").status_code == 502


def test_both_oidc_routes_are_declared_public_for_the_route_matrix() -> None:
    from app.auth.rbac import UNAUTHENTICATED_ROUTES
    from app.services.limits import LIMITED_UNAUTHENTICATED_ROUTES

    for path in ("/api/v1/auth/oidc/start", "/api/v1/auth/oidc/callback"):
        assert path in UNAUTHENTICATED_ROUTES
        assert path in LIMITED_UNAUTHENTICATED_ROUTES
