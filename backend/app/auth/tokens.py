"""JWT issue, verification and refresh rotation (R-51, architecture.md:357).

Two properties carry the security here, and both are enforced structurally
rather than by a note:

**Short-lived access tokens.** 15 minutes, per architecture.md:357. An access
token is a bearer credential that cannot be revoked without consulting state on
every request, so the only honest mitigation is that it stops working quickly.

**Refresh rotation with replay detection.** Every refresh token is single-use:
``rotate`` marks the presented token as spent and issues a new one. If a spent
token is presented again, that is not a retry, it is two parties holding the
same credential, so the entire token family is revoked and the legitimate user
must log in again. Rotation alone without replay detection would let a stolen
refresh token be used once by an attacker and still look healthy.

The store is a protocol rather than a database so the revocation rule can be
tested without one. Production supplies a persistent store (T-303); the default
in-memory one is for tests and single-process use only.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Protocol

import jwt

__all__ = [
    "ACCESS_TOKEN_TTL_SECONDS",
    "ALGORITHM",
    "ExpiredToken",
    "InMemoryRefreshStore",
    "MalformedToken",
    "RefreshStore",
    "RevokedFamily",
    "ReusedRefreshToken",
    "TokenPair",
    "TokenService",
]

#: architecture.md:357 -- short-lived JWTs (15 min).
ACCESS_TOKEN_TTL_SECONDS = 900
REFRESH_TOKEN_TTL_SECONDS = 14 * 24 * 3600
ALGORITHM = "HS256"


class MalformedToken(ValueError):
    """The token is not a valid signed JWT, or is not the kind expected."""


class ExpiredToken(MalformedToken):
    """The token was valid but is no longer within its lifetime."""


class ReusedRefreshToken(MalformedToken):
    """A spent refresh token was presented again. The family is now revoked."""


class RevokedFamily(MalformedToken):
    """The token belongs to a family that has been revoked."""


@dataclass(frozen=True, slots=True)
class TokenPair:
    """An access token and the single-use refresh token that replaces it."""

    access_token: str
    refresh_token: str
    expires_in: int = ACCESS_TOKEN_TTL_SECONDS


class RefreshStore(Protocol):
    """Where spent refresh token ids and revoked families are remembered."""

    def is_spent(self, jti: str) -> bool:
        """Whether this token id has already been used to rotate."""
        ...

    def mark_spent(self, jti: str, family: str, expires_at: int) -> None:
        """Record that a token id has been used."""
        ...

    def is_family_revoked(self, family: str) -> bool:
        """Whether every token descended from one login is invalid."""
        ...

    def revoke_family(self, family: str) -> None:
        """Invalidate every token descended from one login."""
        ...


class InMemoryRefreshStore:
    """A RefreshStore for tests and single-process use.

    Deliberately not for production: rotation state that vanishes on restart
    means a spent token can be replayed against a fresh process.
    """

    __slots__ = ("_revoked", "_spent")

    def __init__(self) -> None:
        """Create an empty store."""
        self._spent: dict[str, tuple[str, int]] = {}
        self._revoked: set[str] = set()

    def is_spent(self, jti: str) -> bool:
        """Whether this token id has already been used to rotate."""
        entry = self._spent.get(jti)
        if entry is None:
            return False
        _, expires_at = entry
        if expires_at <= time.time():
            # A spent token past its own expiry can never be replayed usefully;
            # forgetting it keeps this dict from growing without bound.
            del self._spent[jti]
            return False
        return True

    def mark_spent(self, jti: str, family: str, expires_at: int) -> None:
        """Record that a token id has been used, until it expires anyway."""
        self._spent[jti] = (family, expires_at)

    def is_family_revoked(self, family: str) -> bool:
        """Whether every token descended from this login has been invalidated."""
        return family in self._revoked

    def revoke_family(self, family: str) -> None:
        """Invalidate every token descended from one login."""
        self._revoked.add(family)


class TokenService:
    """Issues and verifies tokens, and enforces single-use refresh."""

    __slots__ = ("_access_ttl", "_algorithm", "_refresh_ttl", "_secret", "_store")

    def __init__(
        self,
        secret: str,
        *,
        store: RefreshStore | None = None,
        access_ttl: int = ACCESS_TOKEN_TTL_SECONDS,
        refresh_ttl: int = REFRESH_TOKEN_TTL_SECONDS,
        algorithm: str = ALGORITHM,
    ) -> None:
        """Build a service. The secret must be long enough to resist guessing."""
        if len(secret) < 32:
            msg = "secret must be at least 32 characters; a short HMAC key is guessable"
            raise ValueError(msg)
        self._secret = secret
        self._store: RefreshStore = store if store is not None else InMemoryRefreshStore()
        self._access_ttl = access_ttl
        self._refresh_ttl = refresh_ttl
        self._algorithm = algorithm

    def issue(self, subject: str, role: str) -> TokenPair:
        """Issue a fresh access/refresh pair for a new login."""
        return self._pair(subject, role, family=uuid.uuid4().hex)

    def verify_access(self, token: str) -> dict[str, object]:
        """Verify an access token and return its claims."""
        claims = self._decode(token)
        if claims.get("typ") != "access":
            msg = "token is not an access token"
            raise MalformedToken(msg)
        return claims

    def verify_refresh(self, token: str) -> dict[str, object]:
        """Verify a refresh token's signature and lifetime, without spending it."""
        claims = self._decode(token)
        if claims.get("typ") != "refresh":
            msg = "token is not a refresh token"
            raise MalformedToken(msg)
        return claims

    def rotate(self, refresh_token: str, *, role: str | None = None) -> TokenPair:
        """Spend a refresh token and return a new pair.

        The presented token stops working the moment this returns. Presenting it
        again revokes the whole family, because two holders of one single-use
        credential means at least one of them is not the user. A user-directory
        adapter may pass the account's current role so a refresh observes a recent
        demotion rather than extending the role captured at login.
        """
        claims = self.verify_refresh(refresh_token)
        family = str(claims["fam"])
        jti = str(claims["jti"])

        if self._store.is_family_revoked(family):
            msg = f"token family {family[:8]} has been revoked"
            raise RevokedFamily(msg)

        if self._store.is_spent(jti):
            # Not a retry. Revoke everything descended from this login.
            self._store.revoke_family(family)
            msg = "refresh token has already been used; family revoked"
            raise ReusedRefreshToken(msg)

        self._store.mark_spent(jti, family, self._int_claim(claims, "exp"))
        current_role = role if role is not None else str(claims.get("role", ""))
        return self._pair(str(claims["sub"]), current_role, family=family)

    def revoke(self, refresh_token: str) -> None:
        """Invalidate a whole session on logout."""
        claims = self.verify_refresh(refresh_token)
        self._store.revoke_family(str(claims["fam"]))

    def _pair(self, subject: str, role: str, *, family: str) -> TokenPair:
        now = int(time.time())
        access = self._encode(
            {
                "sub": subject,
                "role": role,
                "typ": "access",
                "iat": now,
                "exp": now + self._access_ttl,
                "jti": uuid.uuid4().hex,
            }
        )
        refresh = self._encode(
            {
                "sub": subject,
                "role": role,
                "typ": "refresh",
                "fam": family,
                "iat": now,
                "exp": now + self._refresh_ttl,
                "jti": uuid.uuid4().hex,
            }
        )
        return TokenPair(access_token=access, refresh_token=refresh, expires_in=self._access_ttl)

    @staticmethod
    def _int_claim(claims: dict[str, object], name: str) -> int:
        """Read an integer claim, refusing a token that does not carry one."""
        value = claims.get(name)
        if not isinstance(value, int) or isinstance(value, bool):
            msg = f"claim {name!r} is not an integer"
            raise MalformedToken(msg)
        return value

    def _encode(self, payload: dict[str, object]) -> str:
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def _decode(self, token: str) -> dict[str, object]:
        try:
            return jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.ExpiredSignatureError as exc:
            msg = "token has expired"
            raise ExpiredToken(msg) from exc
        except jwt.InvalidTokenError as exc:
            msg = f"token is not valid: {exc}"
            raise MalformedToken(msg) from exc
