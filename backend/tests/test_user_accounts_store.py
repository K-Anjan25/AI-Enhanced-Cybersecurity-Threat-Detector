"""Account storage: the rules every user directory must keep (T-417).

The in-memory directory runs everywhere. The Postgres directory runs the same rules
against the real ``users`` table, and is skipped unless ``AEGIS_DATABASE_URL`` names a
PostgreSQL server that has had ``alembic upgrade head`` applied.
"""

from __future__ import annotations

import os

import pytest
from app.db.models import UserRole
from app.services.auth_accounts import AccountAlreadyProvisioned, AuthAccountStore
from app.services.user_directory import DuplicateAccount, InMemoryUserDirectory, UserRecord


def _fresh_store() -> AuthAccountStore:
    return AuthAccountStore(InMemoryUserDirectory())


def test_in_memory_directory_assigns_ids_and_refuses_a_duplicate_email() -> None:
    directory = InMemoryUserDirectory()
    first = directory.add_account(email="a@example.com", role=UserRole.viewer, argon2_hash="h1")
    second = directory.add_account(email="b@example.com", role=UserRole.viewer, argon2_hash="h2")
    assert (first.id, second.id) == (1, 2)
    assert directory.password_hash(first.id) == "h1"
    assert directory.find_by_email("b@example.com") == second
    with pytest.raises(DuplicateAccount):
        directory.add_account(email="a@example.com", role=UserRole.viewer, argon2_hash="h3")


def test_the_hash_never_appears_on_the_user_record() -> None:
    directory = InMemoryUserDirectory()
    record = directory.add_account(email="a@example.com", role=UserRole.viewer, argon2_hash="h")
    assert not hasattr(record, "argon2_hash")


def test_signup_creates_a_viewer_and_a_taken_address_answers_none() -> None:
    store = _fresh_store()
    record = store.register_viewer("New@Example.com", "a-long-enough-passphrase")
    assert record is not None
    assert record.role is UserRole.viewer
    assert record.email == "new@example.com"
    assert store.register_viewer("new@example.com", "another-passphrase") is None


def test_the_first_administrator_is_provisioned_once() -> None:
    store = _fresh_store()
    admin = store.create_initial_admin("admin@example.com", "a-long-enough-passphrase")
    assert admin.role is UserRole.admin
    with pytest.raises(AccountAlreadyProvisioned):
        store.create_initial_admin("other@example.com", "a-long-enough-passphrase")


def test_authenticate_accepts_only_the_right_password_for_an_active_account() -> None:
    store = _fresh_store()
    store.register_viewer("viewer@example.com", "a-long-enough-passphrase")
    assert store.authenticate("viewer@example.com", "a-long-enough-passphrase") is not None
    assert store.authenticate("viewer@example.com", "wrong-passphrase-here") is None
    assert store.authenticate("nobody@example.com", "a-long-enough-passphrase") is None


def test_a_disabled_account_cannot_sign_in() -> None:
    directory = InMemoryUserDirectory()
    store = AuthAccountStore(directory)
    record = store.register_viewer("viewer@example.com", "a-long-enough-passphrase")
    assert record is not None
    directory.put(
        UserRecord(
            id=record.id,
            email=record.email,
            role=record.role,
            created_at=record.created_at,
            disabled_at=record.created_at,
        )
    )
    assert store.authenticate("viewer@example.com", "a-long-enough-passphrase") is None


def _live_url() -> str | None:
    url = os.environ.get("AEGIS_DATABASE_URL", "")
    return url if url.startswith("postgresql") else None


@pytest.mark.skipif(_live_url() is None, reason="needs a migrated PostgreSQL database")
def test_postgres_directory_keeps_accounts_across_a_new_directory_object() -> None:
    from app.db.user_store import SqlUserDirectory

    url = _live_url()
    assert url is not None
    email = "persist-check@example.invalid"
    first = SqlUserDirectory.from_url(url)
    existing = first.find_by_email(email)
    if existing is None:
        AuthAccountStore(first).register_viewer(email, "a-long-enough-passphrase")
    # A second directory object, as a restarted process would build, sees the account.
    second = SqlUserDirectory.from_url(url)
    account = second.find_by_email(email)
    assert account is not None
    assert second.password_hash(account.id) is not None
    assert AuthAccountStore(second).authenticate(email, "a-long-enough-passphrase") is not None
