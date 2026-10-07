"""Authentication wire contracts (T-417).

A token pair is the only credential-bearing response. Passwords are secret input
fields, never output fields; the user-directory schema remains unable to represent
a password hash.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.auth.identity import normalise_email

__all__ = [
    "AuthStatusOut",
    "CredentialsIn",
    "RefreshIn",
    "TokenPairOut",
]


class AuthStatusOut(BaseModel):
    """Whether the explicitly enabled local first-admin setup is still available."""

    model_config = ConfigDict(frozen=True)

    setup_available: bool = Field(
        description=(
            "True only when development-only setup is enabled and no account exists. "
            "The first account is an administrator and is held in memory."
        )
    )
    setup_enabled: bool = Field(
        description="Whether AEGIS_DEV_AUTH_SETUP_ENABLED is enabled for this process."
    )
    account_exists: bool = Field(
        description="Whether an administrator has been provisioned in this process."
    )


class CredentialsIn(BaseModel):
    """Email and password for local account setup or sign-in."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=12, max_length=256)

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        """Store a stable case-folded address and refuse malformed identifiers."""
        try:
            return normalise_email(value)
        except ValueError as exc:
            raise ValueError("email must be a valid address") from exc


class RefreshIn(BaseModel):
    """A single-use refresh token presented for rotation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    refresh_token: SecretStr = Field(min_length=1, max_length=4096)


class TokenPairOut(BaseModel):
    """The bearer pair returned after setup, login or refresh rotation."""

    model_config = ConfigDict(frozen=True)

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105  # scheme name, not a credential
    expires_in: int = Field(gt=0, description="Access-token lifetime in seconds.")
    subject: str
    role: str
