"""Authentication accounts for the bootstrap and the local console (T-417).

The password hash is kept beside the user row in the user directory, not in
``UserRecord``: the user API's serialisable model cannot carry a hash. One first
administrator can be seeded from deployment secrets, or (only when explicitly enabled
in a private development environment) created through the local setup screen. Neither
path invents credentials.

Every operation goes through the directory, so the same logic runs on the in-memory
directory (tests, single-process runs) and on the Postgres directory (accounts survive
a restart). The lock only orders checks and inserts inside this process; the email
uniqueness of the store is what protects concurrent processes.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from threading import RLock

from app.auth.identity import normalise_email
from app.auth.passwords import hash_password, verify_password
from app.db.models import UserRole
from app.services.user_directory import DuplicateAccount, UserDirectory, UserRecord

__all__ = [
    "AccountAlreadyProvisioned",
    "AuthAccountStore",
    "normalise_email",
]


class AccountAlreadyProvisioned(RuntimeError):
    """The first administrator already exists; setup is deliberately one-shot."""


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    """One throwaway Argon2id hash keeps unknown-account login timing comparable."""
    return hash_password(secrets.token_urlsafe(32))


class AuthAccountStore:
    """Accounts and their password hashes, held in a :class:`UserDirectory`.

    Password hashes stay in the directory's credential side, never in ``UserRecord``,
    so role changes made through the admin API are reflected on the next login.
    """

    def __init__(self, directory: UserDirectory) -> None:
        """Bind credentials to the application's user directory."""
        self._directory = directory
        self._lock = RLock()

    def account_count(self) -> int:
        """Return how many account records are currently provisioned."""
        with self._lock:
            return len(self._directory.rows())

    def create_initial_admin(self, email: str, password: str) -> UserRecord:
        """Create the first administrator from user-supplied credentials.

        Raises:
            AccountAlreadyProvisioned: if an account already exists.
            ValueError: if the email cannot be used as a login identifier.
        """
        normalised = normalise_email(email)
        with self._lock:
            if self._directory.rows():
                raise AccountAlreadyProvisioned("the first administrator is already provisioned")
            # Hash before the row is written. If Argon2 fails, no half-created account
            # is visible to either the login or the user-directory endpoint.
            password_hash = hash_password(password)
            try:
                return self._directory.add_account(
                    email=normalised, role=UserRole.admin, argon2_hash=password_hash
                )
            except DuplicateAccount as exc:
                raise AccountAlreadyProvisioned(
                    "the first administrator is already provisioned"
                ) from exc

    def register_viewer(self, email: str, password: str) -> UserRecord | None:
        """Create a viewer account, or return ``None`` if the address is taken.

        Self-service signup can only ever create a viewer, the least-privileged role.
        Elevation stays with an administrator through the users API. A taken address
        returns ``None`` rather than raising, so the caller can answer the same way for
        new and existing addresses (no account enumeration).
        """
        normalised = normalise_email(email)
        with self._lock:
            if self._directory.find_by_email(normalised) is not None:
                return None
            password_hash = hash_password(password)
            try:
                return self._directory.add_account(
                    email=normalised, role=UserRole.viewer, argon2_hash=password_hash
                )
            except DuplicateAccount:
                return None

    def authenticate(self, email: str, password: str) -> UserRecord | None:
        """Return an active account only when its Argon2id password matches."""
        try:
            normalised = normalise_email(email)
        except ValueError:
            normalised = ""
        with self._lock:
            record = self._directory.find_by_email(normalised) if normalised else None
            stored_hash = self._directory.password_hash(record.id) if record else None
        # Do an Argon2 verification even for an unknown email. The UI receives the same
        # 401 for either case, and response timing does not reveal an account.
        valid = verify_password(password, stored_hash or _dummy_password_hash())
        if not valid or record is None or not record.active:
            return None
        return record

    def active_account(self, email: str) -> UserRecord | None:
        """Resolve an active account for refresh, using its current directory role."""
        try:
            normalised = normalise_email(email)
        except ValueError:
            return None
        with self._lock:
            record = self._directory.find_by_email(normalised)
        return record if record is not None and record.active else None
