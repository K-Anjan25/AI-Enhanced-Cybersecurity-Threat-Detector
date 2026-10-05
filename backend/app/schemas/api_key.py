"""Wire contracts for API keys (FR-44, T-313).

The split is the same one :mod:`app.schemas.webhook` makes for signing secrets,
and for the same reason: the plaintext key is a field of the creation response
and of nothing else. :class:`ApiKeyOut` has no field that could hold it, so a
listing cannot leak one by being written carelessly, and the record a store keeps
cannot either.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "MAX_KEY_NAME_LENGTH",
    "ApiKeyCreate",
    "ApiKeyIssuedOut",
    "ApiKeyListOut",
    "ApiKeyOut",
    "ScopeOut",
    "ScopeListOut",
]

#: A label an operator recognises in a list, not a description field.
MAX_KEY_NAME_LENGTH = 120


class ScopeListOut(BaseModel):
    """The scopes a key may be issued with, and what each one grants."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[ScopeOut]


class ScopeOut(BaseModel):
    """One scope, with the capabilities it grants.

    The capabilities are shown because a scope's name is not a permission model:
    an operator choosing between two of them should be able to see that one
    reads alerts and the other writes ingested data.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    capabilities: list[str]


class ApiKeyCreate(BaseModel):
    """A key to issue."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_KEY_NAME_LENGTH)
    #: Required and non-empty. Omitted scopes are a 422 at the edge rather than a
    #: key that silently means "everything" or "nothing".
    scopes: list[str] = Field(min_length=1)


class ApiKeyOut(BaseModel):
    """An issued key, **without** its secret.

    ``prefix`` is what remains visible of the key string: ``aegis_sk_<id>_``, the
    public half. It is shown so an operator can match a listing row to a key they
    hold, and it discloses nothing -- the id is in the key anyway.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int
    name: str
    prefix: str
    owner: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyIssuedOut(ApiKeyOut):
    """A newly issued key, with its secret shown exactly once.

    There is no route that returns this schema twice for one key: the secret is
    not stored in a recoverable form, so a lost key is re-issued, not re-read.
    """

    secret: str = Field(description="The API key. Shown once; store it now.")


class ApiKeyListOut(BaseModel):
    """Every key, revoked ones included, so the list is the record of what existed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[ApiKeyOut]
