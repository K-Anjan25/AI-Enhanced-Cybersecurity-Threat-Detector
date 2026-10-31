"""The Postgres user directory: accounts that survive a restart (T-417).

It implements :class:`app.services.user_directory.UserDirectory` over the ``users``
table that migration 0001 creates. It uses a synchronous engine on purpose: the
account endpoints are synchronous and run in FastAPI's thread pool, and the user table
is read a few times per sign-in, so a second async session pool would add complexity
without a benefit. The schema is created by ``alembic upgrade head``, never here.

Database ids come from the column's own sequence, so this directory never picks an id
itself; that is what keeps two processes from inserting the same one.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.models import User, UserRole
from app.services.user_directory import DuplicateAccount, UserRecord

__all__ = ["SqlUserDirectory"]


def _to_record(row: User) -> UserRecord:
    """Map one ``users`` row to the directory's record, without the hash."""
    return UserRecord(
        id=row.id,
        email=row.email,
        role=row.role,
        created_at=row.created_at,
        disabled_at=row.disabled_at,
    )


class SqlUserDirectory:
    """A :class:`UserDirectory` over Postgres, one short session per call."""

    def __init__(self, engine: Engine) -> None:
        """Bind the directory to an engine. No connection is opened here."""
        self._engine = engine
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    @classmethod
    def from_url(cls, url: str) -> SqlUserDirectory:
        """Build a directory from a ``postgresql+psycopg://`` URL.

        Lazy like every engine in this codebase: a database that is not up yet does not
        stop the process from starting; the first account read reports the failure.
        """
        return cls(create_engine(url, pool_pre_ping=True))

    def rows(self) -> Sequence[UserRecord]:
        """Every user, in id order."""
        with self._sessions() as session:
            users = session.scalars(select(User).order_by(User.id)).all()
            return tuple(_to_record(user) for user in users)

    def get(self, user_id: int) -> UserRecord | None:
        """One user, or ``None``."""
        with self._sessions() as session:
            user = session.get(User, user_id)
            return None if user is None else _to_record(user)

    def find_by_email(self, email: str) -> UserRecord | None:
        """The user with this normalised email address, or ``None``."""
        with self._sessions() as session:
            user = session.scalars(select(User).where(User.email == email)).first()
            return None if user is None else _to_record(user)

    def add_account(self, *, email: str, role: UserRole, argon2_hash: str) -> UserRecord:
        """Insert a user and its hash in one transaction.

        Raises:
            DuplicateAccount: if the unique email constraint refuses the row.
        """
        with self._sessions() as session:
            user = User(email=email, role=role, argon2_hash=argon2_hash)
            session.add(user)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise DuplicateAccount(email) from exc
            session.refresh(user)
            return _to_record(user)

    def password_hash(self, user_id: int) -> str | None:
        """The stored Argon2id hash for a user, or ``None``."""
        with self._sessions() as session:
            user = session.get(User, user_id)
            return None if user is None else user.argon2_hash

    def put(self, record: UserRecord) -> None:
        """Update one user's role, email and disabled state. The hash is not touched.

        Raises:
            KeyError: if no user has this id.
        """
        with self._sessions() as session:
            user = session.get(User, record.id)
            if user is None:
                raise KeyError(record.id)
            user.role = record.role
            user.email = record.email
            user.disabled_at = record.disabled_at
            session.commit()
