"""The user directory: who exists, what role they hold, and who may change it (T-410).

Three rules live here rather than in the route, because all three are the kind a
route can only restate:

**A role change is audited, and a no-op is not a change.** Setting the role a user
already holds returns ``changed=False`` and writes nothing. The alternative is a
trail full of "changed analyst to analyst", which is how an audit log stops being
read (D-038 made the same call for a repeated verdict).

**The last active admin cannot be demoted.** R-53's admin is the only role that can
administer anything, so a change that would leave the deployment with no active
admin is refused — including the self-demotion the acceptance criterion names, and
including the same move made by a *different* admin, because the outcome is what
the rule is about. A disabled admin does not count: the role it holds cannot be
exercised, so an account with ``disabled_at`` set cannot be the last one standing.
That asymmetry is deliberate and tested — demoting a disabled admin is exactly how
a deployment recovers from an offboarded administrator.

**The authority is the server's, and the token subject is not an id.** A principal
carries the token's opaque ``sub`` (``app.auth.rbac.Principal``), and this module
never resolves it to a row: FR-42's trail records the subject as the actor, and the
numeric ``users.id`` mapping is the adapter's job (the seam D-038 names for
verdicts). So "self-demotion" is decided by the *rule* — would this leave zero
admins — rather than by comparing the actor to the target, which no code here could
do honestly.

**What is not here.** No create, no disable, no password reset: those need the
credential lifecycle (``app/auth/passwords.py``) and a session to write a ``users``
row through (D-030), neither of which is wired. The directory is a read model over
whatever the deployment registered, and ``InMemoryUserDirectory`` is what runs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.db.models import UserRole

__all__ = [
    "InMemoryUserDirectory",
    "LastActiveAdmin",
    "RoleChangeRefused",
    "UnknownUser",
    "UserAdminService",
    "UserDirectory",
    "UserRecord",
    "RoleChange",
]


class UnknownUser(LookupError):
    """No user has that id. Distinct from a refusal: the request named nothing."""


class RoleChangeRefused(ValueError):
    """The change is well formed and the directory refuses it.

    A conflict with the state rather than a malformed request, so the route maps it
    to a 409 (the same reading T-315 gave a refused promotion).
    """


class LastActiveAdmin(RoleChangeRefused):
    """The change would leave the deployment with no active administrator."""


@dataclass(frozen=True, slots=True)
class UserRecord:
    """One ``users`` row, as the admin screen needs it.

    Deliberately without ``argon2_hash``: a hash never leaves the store, not even
    into an in-process model that a route serialises. The field is not there to be
    forgotten.

    Attributes:
        id: the row id, which is also the trail's ``target_id`` for a role change.
        email: the address the user signs in with; the screen's display name.
        role: what the user may do (R-53).
        created_at: when the account was made, timezone-aware.
        disabled_at: when it stopped being usable, or ``None``. A disabled account
            holds its role but cannot exercise it, which is why it does not count
            towards the last-admin floor.
    """

    id: int
    email: str
    role: UserRole
    created_at: datetime
    disabled_at: datetime | None = None

    def __post_init__(self) -> None:
        """Refuse a record that cannot identify a person or a moment."""
        if self.id < 1:
            raise ValueError(f"a user id is a positive integer, got {self.id}")
        if not self.email.strip():
            raise ValueError("a user record must carry an email address")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if self.disabled_at is not None and (
            self.disabled_at.tzinfo is None or self.disabled_at.utcoffset() is None
        ):
            raise ValueError("disabled_at must be timezone-aware")

    @property
    def active(self) -> bool:
        """Whether the account can currently be used."""
        return self.disabled_at is None

    @property
    def is_admin(self) -> bool:
        """Whether the account holds the administrator role."""
        return self.role is UserRole.admin

    @property
    def counts_as_admin(self) -> bool:
        """Whether this account is an administrator *in force* — the floor's unit."""
        return self.is_admin and self.active


@dataclass(frozen=True, slots=True)
class RoleChange:
    """What a role change did.

    Attributes:
        user_id: whose role was addressed. Present even when nothing changed, so a
            caller can report a no-op without a second read.
        previous: the role before the call.
        applied: the role after it — equal to ``previous`` when ``changed`` is
            false.
        changed: false when the user already held the role, in which case nothing
            was written and the audit trail recorded nothing.
        at: when the change was decided, timezone-aware.
        actor: the principal that asked, as the token names it (FR-42).
    """

    user_id: int
    previous: UserRole
    applied: UserRole
    changed: bool
    at: datetime
    actor: str


class UserDirectory(Protocol):
    """Where user rows live.

    Mirrors the ``users`` table's addressable columns. The persistent adapter is a
    session over that table -- unwired because no session exists (D-030) -- and the
    in-memory implementation is what runs.
    """

    def rows(self) -> Sequence[UserRecord]:
        """Every user, in no particular order."""
        ...

    def get(self, user_id: int) -> UserRecord | None:
        """One user, or ``None``."""
        ...

    def put(self, record: UserRecord) -> None:
        """Insert or replace one user row."""
        ...


class InMemoryUserDirectory:
    """A :class:`UserDirectory` in a dictionary, for tests and single-process runs.

    Starts **empty**, like the model registry (D-047): a deployment's users are its
    own, and a directory seeded from code would put an identity nobody chose into
    the table that decides who can administer the system. What that costs is named
    on the screen rather than hidden: an unseeded deployment shows an empty
    directory and cannot demonstrate the last-admin rule until its users exist.
    """

    __slots__ = ("_rows",)

    def __init__(self, users: Sequence[UserRecord] = ()) -> None:
        """Start from ``users``, refusing a duplicate id."""
        self._rows: dict[int, UserRecord] = {}
        for record in users:
            if record.id in self._rows:
                raise ValueError(f"user id {record.id} appears twice")
            self._rows[record.id] = record

    def rows(self) -> tuple[UserRecord, ...]:
        """Every user, in id order so two reads agree on a page."""
        return tuple(self._rows[key] for key in sorted(self._rows))

    def get(self, user_id: int) -> UserRecord | None:
        """One user, or ``None``."""
        return self._rows.get(user_id)

    def put(self, record: UserRecord) -> None:
        """Insert or replace one user row."""
        self._rows[record.id] = record

    def __len__(self) -> int:
        """How many users are registered."""
        return len(self._rows)


@dataclass(frozen=True, slots=True)
class UserAdminService:
    """The directory plus the rules that guard a role change.

    Frozen and injected, so the route holds no arithmetic and the tests run the real
    rule against a real directory rather than a mock that agrees with them.
    """

    directory: UserDirectory

    def users(self) -> tuple[UserRecord, ...]:
        """Every user, ordered by address so the screen is stable between reads."""
        return tuple(
            sorted(self.directory.rows(), key=lambda record: (record.email.casefold(), record.id))
        )

    def active_admins(self) -> tuple[UserRecord, ...]:
        """The accounts that can currently administer the deployment."""
        return tuple(record for record in self.users() if record.counts_as_admin)

    def change_role(self, user_id: int, *, role: UserRole, actor: str, at: datetime) -> RoleChange:
        """Set one user's role, or refuse without touching the directory.

        Args:
            user_id: whose role to change.
            role: the role to apply.
            actor: the authenticated principal, recorded on the change.
            at: the decision instant. Time comes in rather than from the clock so a
                boundary case is testable and a run is reproducible.

        Returns:
            The change, with ``changed=False`` when the user already held the role.

        Raises:
            UnknownUser: when no user has that id.
            LastActiveAdmin: when the change would leave no active administrator.
            ValueError: when ``actor`` is blank or ``at`` is naive.
        """
        if not actor.strip():
            raise ValueError("a role change must name the actor that asked for it")
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("a role change needs a timezone-aware instant")
        record = self.directory.get(user_id)
        if record is None:
            raise UnknownUser(f"no user has id {user_id}")

        if record.role is role:
            # A repeat is not a change. Nothing is written and nothing is audited,
            # so a client retry cannot manufacture an event (D-038's rule).
            return RoleChange(
                user_id=user_id,
                previous=record.role,
                applied=role,
                changed=False,
                at=at,
                actor=actor,
            )

        demotes_an_admin = record.counts_as_admin and role is not UserRole.admin
        if demotes_an_admin and len(self.active_admins()) == 1:
            raise LastActiveAdmin(
                f"user {user_id} is the deployment's last active admin; changing their role "
                "would leave nobody able to administer users, keys, retention or models (R-53). "
                "Give another account the admin role first, then change this one."
            )

        self.directory.put(
            UserRecord(
                id=record.id,
                email=record.email,
                role=role,
                created_at=record.created_at,
                disabled_at=record.disabled_at,
            )
        )
        return RoleChange(
            user_id=user_id, previous=record.role, applied=role, changed=True, at=at, actor=actor
        )
