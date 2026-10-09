"""PostgreSQL-backed user directory.

Replaces InMemoryUserDirectory with persistent storage using the users table.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import User, UserRole
from app.services.user_directory import UserDirectory, UserRecord, DuplicateEmail

__all__ = ["PostgresUserDirectory", "UserDirectoryUnavailable"]


class UserDirectoryUnavailable(RuntimeError):
    """Raised when the user directory cannot fulfill a request."""


class PostgresUserDirectory:
    """Persistent user directory backed by PostgreSQL."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def create(self, email: str, argon2_hash: str, role: str = "viewer") -> UserRecord:
        """Create a new user."""
        try:
            async with self._sessions() as session:
                # Check for duplicate
                existing = await session.execute(
                    select(User).where(User.email == email)
                )
                if existing.scalar_one_or_none() is not None:
                    raise DuplicateEmail(email)

                stmt = insert(User).values(
                    email=email,
                    argon2_hash=argon2_hash,
                    role=UserRole(role),
                ).returning(User)
                result = await session.execute(stmt)
                await session.commit()
                row = result.scalar_one()
                return UserRecord(
                    id=row.id,
                    email=row.email,
                    role=row.role.value,
                    created_at=row.created_at,
                    disabled_at=row.disabled_at,
                )
        except SQLAlchemyError as exc:
            raise UserDirectoryUnavailable(str(exc)) from exc

    async def get_by_email(self, email: str) -> UserRecord | None:
        """Find a user by email."""
        try:
            async with self._sessions() as session:
                result = await session.execute(
                    select(User).where(User.email == email)
                )
                row = result.scalar_one_or_none()
                if row is None:
                    return None
                return UserRecord(
                    id=row.id,
                    email=row.email,
                    role=row.role.value,
                    created_at=row.created_at,
                    disabled_at=row.disabled_at,
                    argon2_hash=row.argon2_hash,
                )
        except SQLAlchemyError as exc:
            raise UserDirectoryUnavailable(str(exc)) from exc

    async def list_all(self) -> list[UserRecord]:
        """List all users."""
        try:
            async with self._sessions() as session:
                result = await session.execute(
                    select(User).order_by(User.created_at.desc())
                )
                return [
                    UserRecord(
                        id=row.id,
                        email=row.email,
                        role=row.role.value,
                        created_at=row.created_at,
                        disabled_at=row.disabled_at,
                    )
                    for row in result.scalars()
                ]
        except SQLAlchemyError as exc:
            raise UserDirectoryUnavailable(str(exc)) from exc

    async def disable(self, user_id: int) -> None:
        """Disable a user."""
        try:
            async with self._sessions() as session:
                await session.execute(
                    update(User).where(User.id == user_id).values(
                        disabled_at=datetime.now(UTC)
                    )
                )
                await session.commit()
        except SQLAlchemyError as exc:
            raise UserDirectoryUnavailable(str(exc)) from exc