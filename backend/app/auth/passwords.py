"""Argon2id password hashing (R-51).

R-51 is not "use a strong hash" but "never MD5/SHA1/bcrypt-with-low-cost for new
code". A hashing function cannot enforce that, so the *verification* function
does: it refuses a hash that is not Argon2id rather than checking it. A legacy
hash that still verifies is a legacy hash still in use, and silently accepting
it is how a codebase ends up holding MD5 in production a decade after the rule
was written.

Argon2id is the argon2 reference variant: memory-hard, and resistant to both
GPU and side-channel attack in a way Argon2i and Argon2d each are only partly.
"""

from __future__ import annotations

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

__all__ = [
    "ARGON2_PREFIX",
    "NonArgon2Hash",
    "hash_password",
    "needs_rehash",
    "verify_password",
]

#: Every Argon2id hash starts with this. Argon2i and Argon2d hashes start with
#: ``$argon2i$`` and ``$argon2d$``, so this is a type check and not a guess.
ARGON2_PREFIX = "$argon2id$"

_hasher = PasswordHasher(type=Type.ID)


class NonArgon2Hash(ValueError):
    """The stored hash is not Argon2id. R-51 does not permit verifying it."""


def hash_password(plaintext: str) -> str:
    """Hash a password. The result embeds its own parameters and salt."""
    return _hasher.hash(plaintext)


def verify_password(plaintext: str, stored_hash: str) -> bool:
    """Verify a password against an Argon2id hash.

    Raises NonArgon2Hash for anything else rather than returning False. The
    distinction matters: False means "wrong password, try again", while a
    legacy hash means "this row must be rehashed", and conflating them turns a
    migration into an infinite stream of login failures.
    """
    if not stored_hash.startswith(ARGON2_PREFIX):
        msg = "stored hash is not Argon2id; R-51 forbids verifying it"
        raise NonArgon2Hash(msg)
    try:
        return _hasher.verify(stored_hash, plaintext)
    except VerifyMismatchError:
        return False
    except (InvalidHashError, VerificationError) as exc:
        # argon2-cffi raises VerificationError (not InvalidHashError) for some
        # malformed hashes, so catching only the narrower one would let a
        # corrupt stored hash surface as a 500 instead of "please rehash".
        msg = f"stored hash is not a valid Argon2id hash: {exc}"
        raise NonArgon2Hash(msg) from exc


def needs_rehash(stored_hash: str) -> bool:
    """Whether a hash predates the current parameters and should be upgraded.

    Argon2 parameters should rise as hardware does. This is checked on every
    successful login so rehashing happens when the password is in hand, which
    is the only moment it can be done without asking the user to reset it.
    """
    if not stored_hash.startswith(ARGON2_PREFIX):
        return True
    return _hasher.check_needs_rehash(stored_hash)
