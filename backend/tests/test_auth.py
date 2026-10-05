"""T-302: Argon2id hashing and JWT refresh rotation (R-51).

The acceptance criterion is that refresh rotation invalidates the previous
token, so that is what most of these tests attack. A rotation that issues a new
token without killing the old one is not rotation; it is just issuing twice.
"""

from __future__ import annotations

import hashlib
import time

import jwt as pyjwt
import pytest
from app.auth.passwords import (
    ARGON2_PREFIX,
    NonArgon2Hash,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.auth.tokens import (
    ALGORITHM,
    ExpiredToken,
    InMemoryRefreshStore,
    MalformedToken,
    ReusedRefreshToken,
    RevokedFamily,
    TokenService,
)

SECRET = "s" * 48


@pytest.fixture
def service() -> TokenService:
    return TokenService(SECRET)


# --- Argon2id -------------------------------------------------------------


def test_the_hash_is_argon2id() -> None:
    """R-51 names the variant, so the variant is asserted and not assumed."""
    assert hash_password("hunter2").startswith(ARGON2_PREFIX)


def test_correct_and_incorrect_passwords() -> None:
    stored = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", stored)
    assert not verify_password("correct horse battery stapIe", stored)


def test_two_hashes_of_one_password_differ() -> None:
    """A per-hash salt is what stops rainbow tables and reveals reuse."""
    assert hash_password("same") != hash_password("same")


def test_md5_and_sha1_are_refused_not_verified() -> None:
    """R-51 forbids them. Returning False would hide a row that must migrate."""
    for legacy in (
        # These are the hashes R-51 forbids; constructing one is the test.
        hashlib.md5(b"pw").hexdigest(),  # noqa: S324
        hashlib.sha1(b"pw").hexdigest(),  # noqa: S324
    ):
        with pytest.raises(NonArgon2Hash):
            verify_password("pw", legacy)


def test_bcrypt_and_argon2i_are_refused_too() -> None:
    """The rule is Argon2id specifically, not "some argon2"."""
    bcrypt = "$2b$12$" + "a" * 53
    argon2i = "$argon2i$v=19$m=65536,t=3,p=4$c2FsdA$abc"
    for legacy in (bcrypt, argon2i):
        with pytest.raises(NonArgon2Hash):
            verify_password("pw", legacy)


def test_a_malformed_argon2id_hash_is_refused() -> None:
    with pytest.raises(NonArgon2Hash):
        verify_password("pw", ARGON2_PREFIX + "not-a-real-hash")


def test_a_current_hash_does_not_need_rehashing() -> None:
    assert not needs_rehash(hash_password("pw"))
    assert needs_rehash(hashlib.md5(b"pw").hexdigest())  # noqa: S324


# --- issuing and verifying -------------------------------------------------


def test_an_access_token_carries_subject_role_and_type(service: TokenService) -> None:
    pair = service.issue("alice", "analyst")
    claims = service.verify_access(pair.access_token)
    assert claims["sub"] == "alice"
    assert claims["role"] == "analyst"
    assert claims["typ"] == "access"


def test_the_access_token_is_short_lived(service: TokenService) -> None:
    """Short-lived, per architecture.md:357.

    A bearer token that lives longer cannot be revoked, only waited out.
    """
    pair = service.issue("alice", "analyst")
    claims = service.verify_access(pair.access_token)
    assert int(claims["exp"]) - int(claims["iat"]) == 900  # type: ignore[arg-type]


def test_an_expired_token_is_rejected() -> None:
    service = TokenService(SECRET, access_ttl=-1)
    pair = service.issue("alice", "analyst")
    with pytest.raises(ExpiredToken):
        service.verify_access(pair.access_token)


def test_a_tampered_payload_is_rejected(service: TokenService) -> None:
    """Editing the payload without re-signing must fail.

    Re-signing with the correct key would not be tampering at all, it would be
    issuing a token, so this edits the payload segment and keeps the original
    signature.
    """
    import base64
    import json

    pair = service.issue("alice", "analyst")
    header, payload, signature = pair.access_token.split(".")
    decoded = json.loads(base64.urlsafe_b64decode(payload + "=="))
    decoded["role"] = "admin"
    forged_payload = base64.urlsafe_b64encode(json.dumps(decoded).encode()).rstrip(b"=")
    forged = ".".join([header, forged_payload.decode(), signature])

    with pytest.raises(MalformedToken):
        service.verify_access(forged)


def test_a_re_signed_forged_token_still_works_and_that_is_the_point(
    service: TokenService,
) -> None:
    """HS256 is a symmetric MAC, so the secret is the whole boundary.

    Anyone holding it can mint any token. That is why a short secret is refused
    and why this one comes from the environment rather than the code.
    """
    claims = service.verify_access(service.issue("alice", "analyst").access_token)
    claims["role"] = "admin"
    minted = pyjwt.encode(claims, SECRET, algorithm=ALGORITHM)
    assert service.verify_access(minted)["role"] == "admin"


def test_a_token_signed_with_another_key_is_rejected() -> None:
    attacker = TokenService("a" * 48)
    forged = attacker.issue("alice", "admin")
    with pytest.raises(MalformedToken):
        TokenService(SECRET).verify_access(forged.access_token)


def test_a_refresh_token_cannot_be_used_as_an_access_token(
    service: TokenService,
) -> None:
    """Both are signed by the same key, so type confusion is the real risk."""
    pair = service.issue("alice", "analyst")
    with pytest.raises(MalformedToken):
        service.verify_access(pair.refresh_token)


def test_an_access_token_cannot_be_used_to_rotate(service: TokenService) -> None:
    pair = service.issue("alice", "analyst")
    with pytest.raises(MalformedToken):
        service.rotate(pair.access_token)


def test_a_short_secret_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 32"):
        TokenService("short")


# --- rotation: the acceptance criterion ------------------------------------


def test_rotation_issues_a_different_token(service: TokenService) -> None:
    first = service.issue("alice", "analyst")
    second = service.rotate(first.refresh_token)
    assert second.refresh_token != first.refresh_token
    assert second.access_token != first.access_token


def test_the_previous_refresh_token_stops_working(service: TokenService) -> None:
    """The criterion. Presenting the spent token again must fail."""
    first = service.issue("alice", "analyst")
    service.rotate(first.refresh_token)
    with pytest.raises(ReusedRefreshToken):
        service.rotate(first.refresh_token)


def test_replay_revokes_the_whole_family(service: TokenService) -> None:
    """Replay means two parties hold one single-use credential.

    At least one of them is not the user, so the legitimate token must die too.
    """
    first = service.issue("alice", "analyst")
    second = service.rotate(first.refresh_token)

    with pytest.raises(ReusedRefreshToken):
        service.rotate(first.refresh_token)

    with pytest.raises(RevokedFamily):
        service.rotate(second.refresh_token)


def test_a_repeated_rotation_chain_stays_valid(service: TokenService) -> None:
    """Rotation must not break ordinary use: N rotations, N valid tokens."""
    pair = service.issue("alice", "analyst")
    for _ in range(5):
        pair = service.rotate(pair.refresh_token)
    assert service.verify_access(pair.access_token)["sub"] == "alice"


def test_rotation_preserves_subject_and_role(service: TokenService) -> None:
    pair = service.issue("alice", "analyst")
    rotated = service.rotate(pair.refresh_token)
    claims = service.verify_access(rotated.access_token)
    assert claims["sub"] == "alice"
    assert claims["role"] == "analyst"


def test_each_token_in_a_family_shares_its_family_id(service: TokenService) -> None:
    pair = service.issue("alice", "analyst")
    family = service.verify_refresh(pair.refresh_token)["fam"]
    rotated = service.rotate(pair.refresh_token)
    assert service.verify_refresh(rotated.refresh_token)["fam"] == family


def test_two_logins_get_independent_families(service: TokenService) -> None:
    """Revoking one stolen session must not lock the user out everywhere."""
    stolen = service.issue("alice", "analyst")
    legitimate = service.issue("alice", "analyst")
    service.revoke(stolen.refresh_token)

    assert service.rotate(legitimate.refresh_token) is not None


def test_logout_invalidates_the_session(service: TokenService) -> None:
    pair = service.issue("alice", "analyst")
    service.revoke(pair.refresh_token)
    with pytest.raises(RevokedFamily):
        service.rotate(pair.refresh_token)


def test_an_expired_refresh_token_cannot_be_rotated() -> None:
    service = TokenService(SECRET, refresh_ttl=-1)
    pair = service.issue("alice", "analyst")
    with pytest.raises(ExpiredToken):
        service.rotate(pair.refresh_token)


# --- the store -------------------------------------------------------------


def test_spent_ids_are_forgotten_once_they_expire() -> None:
    """Otherwise the store grows for the lifetime of the process."""
    store = InMemoryRefreshStore()
    store.mark_spent("jti", "fam", int(time.time()) - 1)
    assert not store.is_spent("jti")


def test_a_custom_store_is_used_rather_than_the_default() -> None:
    """T-303 supplies a persistent one; this proves the seam is real."""
    calls: list[str] = []

    class Recording(InMemoryRefreshStore):
        def mark_spent(self, jti: str, family: str, expires_at: int) -> None:
            calls.append(jti)
            super().mark_spent(jti, family, expires_at)

    service = TokenService(SECRET, store=Recording())
    pair = service.issue("alice", "analyst")
    service.rotate(pair.refresh_token)
    assert calls


def test_rotation_is_single_use_even_across_a_clock_tick(service: TokenService) -> None:
    """Spending is not time-based, so no amount of waiting re-enables a token."""
    pair = service.issue("alice", "analyst")
    service.rotate(pair.refresh_token)
    time.sleep(0.01)
    with pytest.raises(ReusedRefreshToken):
        service.rotate(pair.refresh_token)
