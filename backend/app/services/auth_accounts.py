"""In-process authentication accounts for the bootstrap and local console (T-417, T-424).

The credential hash is deliberately separate from ``UserRecord``: the user API's
serialisable directory model cannot carry a password hash. One first administrator
can be seeded from deployment secrets, or (only when explicitly enabled in a
private development environment) created through the local setup screen. Neither
path invents credentials. Self-service registration (FR-45, D-082) is the third
path: once any account exists, anyone may register one, and it is created in the
least-privileged role. This store is process-local; a database-backed account
adapter is still required for durable multi-process user management.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from functools import lru_cache
from threading import RLock

from app.auth.identity import normalise_email
from app.auth.passwords import hash_password, verify_password
from app.db.models import UserRole
from app.services.user_directory import UserDirectory, UserRecord

__all__ = [
    "AccountAlreadyExists",
    "AccountAlreadyProvisioned",
    "AuthAccountStore",
    "RegistrationRefused",
    "normalise_email",
]


class AccountAlreadyProvisioned(RuntimeError):
    """The first administrator already exists; setup is deliberately one-shot."""


class RegistrationRefused(RuntimeError):
    """No account is provisioned yet, so self-service registration is closed.

    Registration before bootstrap would consume the one-shot first-admin path:
    ``create_initial_admin`` refuses the moment any account exists, so an
    address registered first would lock the deployment out of its own setup
    screen. Administrators come from bootstrap credentials or the development
    setup route; registration is for accounts joining a deployment that
    already has one (FR-45, D-082).
    """


class AccountAlreadyExists(ValueError):
    """Self-service registration named an address that already holds an account."""


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    """One throwaway Argon2id hash keeps unknown-account login timing comparable."""
    return hash_password(secrets.token_urlsafe(32))


class AuthAccountStore:
    """A process-local account store backed by the same directory the admin API reads.

    Password hashes stay in this credential store, not in ``UserRecord``; role
    changes made through the admin API are therefore reflected on the next login.
    The store is intentionally single-process and makes no persistence claim.
    """

    def __init__(self, directory: UserDirectory) -> None:
        """Bind credentials to the application's user directory."""
        self._directory = directory
        self._password_hashes: dict[int, str] = {}
        self._email_to_id: dict[str, int] = {}
        self._lock = RLock()

    def account_count(self) -> int:
        """Return how many account records are currently provisioned."""
        with self._lock:
            return len(self._email_to_id)

    def create_initial_admin(self, email: str, password: str) -> UserRecord:
        """Create the first administrator from user-supplied credentials.

        Raises:
            AccountAlreadyProvisioned: if an account already exists.
            ValueError: if the email cannot be used as a login identifier.
        """
        normalised = normalise_email(email)
        with self._lock:
            if self._email_to_id or self._directory.rows():
                raise AccountAlreadyProvisioned("the first administrator is already provisioned")
            record = UserRecord(
                id=1,
                email=normalised,
                role=UserRole.admin,
                created_at=datetime.now(UTC),
            )
            # Hash before publishing the user row. If Argon2 fails, no half-created
            # account is visible to either the login or user-directory endpoint.
            password_hash = hash_password(password)
            self._directory.put(record)
            self._password_hashes[record.id] = password_hash
            self._email_to_id[normalised] = record.id
            return record

    def sign_up(self, email: str, password: str) -> UserRecord:
        """Create a self-service account in the least-privileged role (FR-45, D-082).

        The new account is a ``viewer``: R-53's read-only role, so the person
        who chose their own credentials starts with no authority an admin did
        not grant them. Promotion happens through the role-change route, which
        is audited; registration itself never grants anything above viewer.

        Raises:
            RegistrationRefused: when no account is provisioned yet, because a
                registration must not consume the one-shot first-admin setup.
            AccountAlreadyExists: when the address already holds an account.
            ValueError: if the email cannot be used as a login identifier.
        """
        normalised = normalise_email(email)
        with self._lock:
            if not self._email_to_id and not self._directory.rows():
                raise RegistrationRefused("no account is provisioned yet")
            if normalised in self._email_to_id:
                raise AccountAlreadyExists("an account with that email already exists")
            record = UserRecord(
                id=self._next_id_locked(),
                email=normalised,
                role=UserRole.viewer,
                created_at=datetime.now(UTC),
            )
            # Hash before publishing the user row, as create_initial_admin does:
            # if Argon2 fails, no half-created account is visible to either the
            # login or the user-directory endpoint.
            password_hash = hash_password(password)
            self._directory.put(record)
            self._password_hashes[record.id] = password_hash
            self._email_to_id[normalised] = record.id
            return record

    def _next_id_locked(self) -> int:
        """The next free directory id. Callers hold ``self._lock``."""
        taken = {record.id for record in self._directory.rows()} | set(self._email_to_id.values())
        return max(taken, default=0) + 1

    def authenticate(self, email: str, password: str) -> UserRecord | None:
        """Return an active account only when its Argon2id password matches."""
        try:
            normalised = normalise_email(email)
        except ValueError:
            normalised = ""
        with self._lock:
            user_id = self._email_to_id.get(normalised)
            record = self._directory.get(user_id) if user_id is not None else None
            stored_hash = self._password_hashes.get(user_id) if user_id is not None else None
        # Do an Argon2 verification even for an unknown email. The UI receives the
        # same 401 for either case, and response timing does not reveal an account.
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
            user_id = self._email_to_id.get(normalised)
            record = self._directory.get(user_id) if user_id is not None else None
        return record if record is not None and record.active else None
