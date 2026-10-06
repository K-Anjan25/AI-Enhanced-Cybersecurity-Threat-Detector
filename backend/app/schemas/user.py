"""Wire contracts for the user and role endpoints (T-410, FR-42, R-53).

Two shapes say as much as the fields do:

**A user is serialised without anything that authenticates them.** There is no
field for a password hash and no field for a token. ``UserOut`` is what the admin
screen renders and what a response could leak, so the absence is the contract --
a hash is not "omitted", it is unrepresentable here.

**The listing carries the last-admin count.** The screen must mark which admins are
the last one standing, and the rule that decides it (an active admin, not a disabled
one, R-53) lives in the service. Returning the count means the client does not
restate it: the number on the wire and the number the refusal is decided by are the
same computation.

``role`` is a plain ``str`` rather than an enum here, for the reason
``app/schemas/query.py`` gives: the domain enum lives in the database module, which
imports SQLAlchemy, and schemas stay declarative. The route refuses an unknown role
against the domain enum, which is where a wire string becomes a domain value.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "RoleChangeOut",
    "RoleChangeRequest",
    "RoleNameOut",
    "RoleListOut",
    "UserListOut",
    "UserOut",
]


class UserOut(BaseModel):
    """One user, as the admin screen needs them. Never a credential."""

    model_config = ConfigDict(frozen=True)

    id: int
    email: str
    role: str
    created_at: datetime
    disabled_at: datetime | None = Field(
        default=None,
        description=(
            "When the account stopped being usable. A disabled admin is not an "
            "admin in force, so it neither holds the floor up nor counts towards it."
        ),
    )


class UserListOut(BaseModel):
    """The directory, in the order the screen renders it."""

    model_config = ConfigDict(frozen=True)

    items: list[UserOut]
    count: int
    active_admins: int = Field(
        description=(
            "How many accounts can currently administer the deployment. The same number "
            "the last-admin refusal is decided by."
        )
    )


class RoleChangeRequest(BaseModel):
    """A request to set one user's role.

    No ``reason`` field, deliberately: the trail is the widest-read table in the
    system (R-58) and a free-text note about a person is the wrong thing to put in
    it, while a note stored nowhere would be a field that silently does nothing.
    What a reviewer needs -- who changed whose role, from what to what, and when --
    is in the record itself.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: str = Field(min_length=1, max_length=40, description="One of R-53's four roles.")


class RoleChangeOut(BaseModel):
    """What a role change did, including when it did nothing."""

    model_config = ConfigDict(frozen=True)

    user_id: int
    previous: str
    applied: str
    changed: bool = Field(
        description="False when the user already held the role: nothing was written or audited."
    )
    at: datetime
    actor: str


class RoleNameOut(BaseModel):
    """One role, with what it may do, so the screen can explain the choice."""

    model_config = ConfigDict(frozen=True)

    role: str
    capabilities: list[str]


class RoleListOut(BaseModel):
    """R-53's four roles and their capabilities, read from the matrix itself."""

    model_config = ConfigDict(frozen=True)

    items: list[RoleNameOut]
