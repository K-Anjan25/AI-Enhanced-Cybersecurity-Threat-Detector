"""T-410: user and role administration -- the last admin cannot be demoted (R-53).

The acceptance criterion has two clauses and both are asserted here against the
directory rather than against a return value:

**"A user cannot demote their own last admin."** The refusal is a 409 naming the
rule, the *role is unchanged* afterwards (asserted by reading the directory back,
not by trusting the response), and **no audit row was written** — a refusal that
logged would let anyone with the capability fill the trail. The rule is about the
outcome, so three cases are exercised separately: self-demotion, a demotion asked
for by a colleague, and a demotion asked for by a caller whose token claims admin
while the directory holds only the target — which is what a stale token looks like.

**The count the rule is decided by is the count the API returns.** ``active_admins``
is read from the same service method the refusal consults, and a disabled admin does
not count towards it: demoting an offboarded administrator is exactly how a
deployment recovers, and a rule that counted disabled accounts would refuse it.

The rest of the file is what only the application can be wrong about: who may reach
the routes at all (R-53's ``users`` capability, admin alone), that a role string
becomes a domain value at the edge rather than reaching the service, that a repeat is
a no-op with no audit row, and that no response can carry a credential.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.auth.rbac import ROLE_CAPABILITIES, Role
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.db.models import UserRole
from app.main import create_app
from app.services.audit_log import AuditAction, InMemoryAuditTrail
from app.services.user_directory import (
    InMemoryUserDirectory,
    LastActiveAdmin,
    RoleChangeRefused,
    UnknownUser,
    UserAdminService,
    UserRecord,
)
from fastapi.testclient import TestClient

SECRET = "s" * 48
APP_SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def user(
    user_id: int,
    *,
    role: UserRole = UserRole.analyst,
    email: str | None = None,
    disabled_at: datetime | None = None,
) -> UserRecord:
    """One directory row, with an address derived from the id unless one is given."""
    return UserRecord(
        id=user_id,
        email=email if email is not None else f"user{user_id}@corp.example",
        role=role,
        created_at=NOW - timedelta(days=30),
        disabled_at=disabled_at,
    )


def service(*records: UserRecord) -> UserAdminService:
    """A service over a directory holding exactly ``records``."""
    return UserAdminService(directory=InMemoryUserDirectory(records))


# --- the rule itself, without HTTP -----------------------------------------


def test_the_last_active_admin_cannot_be_demoted_by_anyone() -> None:
    """The acceptance criterion: the refusal, and the store untouched."""
    admin = user(1, role=UserRole.admin)
    directory = InMemoryUserDirectory([admin, user(2)])
    guarded = UserAdminService(directory=directory)

    with pytest.raises(LastActiveAdmin) as refusal:
        guarded.change_role(1, role=UserRole.analyst, actor="admin@corp", at=NOW)

    assert "last active admin" in str(refusal.value)
    assert "R-53" in str(refusal.value)
    # The role is unchanged, read back from the store rather than from a response.
    assert directory.get(1) is not None
    assert directory.get(1).role is UserRole.admin  # type: ignore[union-attr]


def test_a_second_admin_makes_the_demotion_possible() -> None:
    """The rule is a floor, not a prohibition: two admins, one may step down."""
    directory = InMemoryUserDirectory([user(1, role=UserRole.admin), user(2, role=UserRole.admin)])
    guarded = UserAdminService(directory=directory)

    change = guarded.change_role(1, role=UserRole.analyst, actor="admin@corp", at=NOW)

    assert change.changed is True
    assert change.previous is UserRole.admin
    assert change.applied is UserRole.analyst
    assert directory.get(1).role is UserRole.analyst  # type: ignore[union-attr]


def test_a_disabled_admin_does_not_count_towards_the_floor() -> None:
    """An offboarded administrator cannot be the last one — or block a recovery."""
    active = user(1, role=UserRole.admin)
    offboarded = user(2, role=UserRole.admin, disabled_at=NOW - timedelta(days=2))
    directory = InMemoryUserDirectory([active, offboarded])
    guarded = UserAdminService(directory=directory)

    # The only admin who can actually administer is user 1, so it is refused...
    with pytest.raises(LastActiveAdmin):
        guarded.change_role(1, role=UserRole.viewer, actor="someone@corp", at=NOW)
    # ...while the disabled account's role may be lowered, because it holds no
    # authority in force and clearing it is how an offboarding is completed.
    change = guarded.change_role(2, role=UserRole.viewer, actor="someone@corp", at=NOW)
    assert change.changed is True
    assert len(guarded.active_admins()) == 1


def test_promoting_a_user_into_the_admin_role_is_always_allowed() -> None:
    """The floor guards demotion only: a deployment can always add an admin."""
    guarded = service(user(1, role=UserRole.admin), user(2, role=UserRole.viewer))

    change = guarded.change_role(2, role=UserRole.admin, actor="admin@corp", at=NOW)

    assert change.applied is UserRole.admin
    assert len(guarded.active_admins()) == 2


def test_a_repeat_is_not_a_change() -> None:
    """Setting the role a user already holds writes nothing (D-038's rule)."""
    guarded = service(user(1, role=UserRole.admin), user(2, role=UserRole.analyst))

    change = guarded.change_role(2, role=UserRole.analyst, actor="admin@corp", at=NOW)

    assert change.changed is False
    assert change.previous is change.applied is UserRole.analyst


def test_an_unknown_user_is_a_lookup_failure_not_a_refusal() -> None:
    """404 and 409 are different answers: nothing was named versus nothing may be done."""
    with pytest.raises(UnknownUser):
        service(user(1, role=UserRole.admin)).change_role(
            99, role=UserRole.viewer, actor="a", at=NOW
        )
    assert not issubclass(UnknownUser, RoleChangeRefused)


def test_the_service_refuses_a_blank_actor_or_a_naive_instant() -> None:
    """A change must be attributable and datable, checked before the store is touched."""
    guarded = service(user(1, role=UserRole.admin), user(2))
    with pytest.raises(ValueError, match="actor"):
        guarded.change_role(2, role=UserRole.viewer, actor="  ", at=NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        guarded.change_role(2, role=UserRole.viewer, actor="a", at=datetime(2026, 10, 6, 12, 0))


def test_the_directory_orders_by_address_and_is_stable() -> None:
    """Two reads agree, so a page does not reshuffle between polls."""
    guarded = service(
        user(3, email="zoe@corp.example"),
        user(1, email="Ada@corp.example"),
        user(2, email="ada@corp.example"),
    )
    assert [record.id for record in guarded.users()] == [1, 2, 3]


def test_a_record_without_an_address_or_an_instant_is_refused() -> None:
    """The model is total: a row that cannot identify a person never exists."""
    with pytest.raises(ValueError, match="email"):
        user(1, email="   ")
    with pytest.raises(ValueError, match="created_at"):
        UserRecord(id=1, email="a@b", role=UserRole.viewer, created_at=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="positive"):
        user(0)


# --- through HTTP ------------------------------------------------------------


@pytest.fixture
def auth() -> TokenService:
    return TokenService(SECRET)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="test",
        service_name="aegis-backend-test",
        secret_key=APP_SECRET,
        log_level="WARNING",
    )


def build(settings: Settings, auth: TokenService, **state: Any) -> TestClient:
    """The real application, with any state seam a test wants to replace."""
    app = create_app(settings)
    app.state.token_service = auth
    for name, value in state.items():
        setattr(app.state, name, value)
    return TestClient(app)


def headers(auth: TokenService, role: str = "admin", subject: str | None = None) -> dict[str, str]:
    """An Authorization header for one role, naming ``subject`` as the actor."""
    pair = auth.issue(subject if subject is not None else f"{role}@corp", role)
    return {"Authorization": f"Bearer {pair.access_token}"}


def directory_of(client: TestClient) -> InMemoryUserDirectory:
    """The directory this app is serving from."""
    return client.app.state.user_admin.directory  # type: ignore[attr-defined]


def audit_rows(client: TestClient, action: AuditAction) -> list[Any]:
    """The audit entries this test's requests produced, for one action."""
    trail: InMemoryAuditTrail = client.app.state.audit_trail  # type: ignore[attr-defined]
    now = datetime.now(UTC)
    return [
        entry
        for entry in trail.entries(start=now - timedelta(hours=1), end=now + timedelta(hours=1))
        if entry.record.action is action
    ]


def test_self_demotion_of_the_last_admin_is_a_409_and_writes_nothing(
    settings: Settings, auth: TokenService
) -> None:
    """The acceptance criterion, through the route the screen calls."""
    alone = user(1, role=UserRole.admin, email="ana@corp.example")
    with build(
        settings, auth, user_admin=UserAdminService(InMemoryUserDirectory([alone]))
    ) as client:
        response = client.post(
            "/api/v1/users/1/role",
            json={"role": "analyst"},
            headers=headers(client.app.state.token_service, "admin", "ana@corp.example"),  # type: ignore[attr-defined]
        )

    assert response.status_code == 409
    body = response.json()
    assert "last active admin" in body["detail"]
    assert "R-53" in body["detail"]
    assert directory_of(client).get(1).role is UserRole.admin  # type: ignore[union-attr]
    assert audit_rows(client, AuditAction.user_role) == []


def test_a_stale_admin_token_cannot_demote_the_last_admin(
    settings: Settings, auth: TokenService
) -> None:
    """The rule reads the directory, not the token: a colleague's claim is not a fact."""
    target = user(1, role=UserRole.admin, email="ana@corp.example")
    with build(
        settings, auth, user_admin=UserAdminService(InMemoryUserDirectory([target]))
    ) as client:
        response = client.post(
            "/api/v1/users/1/role",
            json={"role": "viewer"},
            # A token that says admin while the directory holds exactly one admin:
            # the caller is a different person, and the refusal still applies.
            headers=headers(client.app.state.token_service, "admin", "departed@corp.example"),  # type: ignore[attr-defined]
        )

    assert response.status_code == 409
    assert directory_of(client).get(1).role is UserRole.admin  # type: ignore[union-attr]


def test_a_successful_change_is_audited_and_the_listing_agrees(
    settings: Settings, auth: TokenService
) -> None:
    """The listing's ``active_admins`` is the count the refusal consults."""
    trio = [
        user(1, role=UserRole.admin, email="ana@corp.example"),
        user(2, role=UserRole.admin, email="bo@corp.example"),
        user(3, role=UserRole.viewer, email="cy@corp.example"),
    ]
    with build(settings, auth, user_admin=UserAdminService(InMemoryUserDirectory(trio))) as client:
        before = client.get(
            "/api/v1/users",
            headers=headers(client.app.state.token_service, "admin"),  # type: ignore[attr-defined]
        )
        assert before.json()["active_admins"] == 2
        assert before.json()["count"] == 3

        response = client.post(
            "/api/v1/users/1/role",
            json={"role": "responder"},
            headers=headers(client.app.state.token_service, "admin", "bo@corp.example"),  # type: ignore[attr-defined]
        )
        after = client.get(
            "/api/v1/users",
            headers=headers(client.app.state.token_service, "admin"),  # type: ignore[attr-defined]
        )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": 1,
        "previous": "admin",
        "applied": "responder",
        "changed": True,
        "at": response.json()["at"],
        "actor": "bo@corp.example",
    }
    assert after.json()["active_admins"] == 1
    rows = audit_rows(client, AuditAction.user_role)
    assert len(rows) == 1
    assert rows[0].record.actor == "bo@corp.example"
    assert rows[0].record.target_id == "1"
    assert rows[0].record.detail == {"previous": "admin", "applied": "responder"}
    # The address is not in the trail: the trail is readable by every role (R-58).
    assert "ana@corp.example" not in str(rows[0].record.detail)


def test_a_repeat_writes_no_audit_row(settings: Settings, auth: TokenService) -> None:
    """A no-op is not an event, so a client retry cannot manufacture one."""
    rows_in = [user(1, role=UserRole.admin), user(2, role=UserRole.analyst)]
    with build(
        settings, auth, user_admin=UserAdminService(InMemoryUserDirectory(rows_in))
    ) as client:
        response = client.post(
            "/api/v1/users/2/role",
            json={"role": "analyst"},
            headers=headers(client.app.state.token_service, "admin"),  # type: ignore[attr-defined]
        )

    assert response.status_code == 200
    assert response.json()["changed"] is False
    assert audit_rows(client, AuditAction.user_role) == []


def test_an_unknown_user_is_a_404_and_an_unknown_role_is_a_400(
    settings: Settings, auth: TokenService
) -> None:
    """Two different mistakes, two different answers."""
    with build(
        settings,
        auth,
        user_admin=UserAdminService(InMemoryUserDirectory([user(1, role=UserRole.admin)])),
    ) as client:
        token = headers(client.app.state.token_service, "admin")  # type: ignore[attr-defined]
        missing = client.post("/api/v1/users/99/role", json={"role": "viewer"}, headers=token)
        bad_role = client.post("/api/v1/users/1/role", json={"role": "root"}, headers=token)

    assert missing.status_code == 404
    assert "99" in missing.json()["detail"]
    assert bad_role.status_code == 400
    assert "root" in bad_role.json()["detail"]
    assert "admin" in bad_role.json()["detail"]  # the allowed set is named


def test_only_admin_reaches_the_user_routes(settings: Settings, auth: TokenService) -> None:
    """R-53's ``users`` capability is the administrator's alone."""
    with build(
        settings,
        auth,
        user_admin=UserAdminService(InMemoryUserDirectory([user(1, role=UserRole.admin)])),
    ) as client:
        for role in ("viewer", "analyst", "responder"):
            token = headers(client.app.state.token_service, role)  # type: ignore[attr-defined]
            assert client.get("/api/v1/users", headers=token).status_code == 403
            assert client.get("/api/v1/users/roles", headers=token).status_code == 403
            assert (
                client.post(
                    "/api/v1/users/1/role", json={"role": "viewer"}, headers=token
                ).status_code
                == 403
            )
        assert client.get("/api/v1/users").status_code == 401


def test_the_role_listing_is_the_matrix_itself(settings: Settings, auth: TokenService) -> None:
    """The screen cannot describe a role differently from the way it is enforced."""
    with build(settings, auth) as client:
        response = client.get(
            "/api/v1/users/roles",
            headers=headers(client.app.state.token_service, "admin"),  # type: ignore[attr-defined]
        )

    assert response.status_code == 200
    listed = {item["role"]: item["capabilities"] for item in response.json()["items"]}
    assert set(listed) == {role.value for role in Role}
    for role in Role:
        assert listed[role.value] == sorted(
            capability.value for capability in ROLE_CAPABILITIES[role]
        )


def test_no_response_carries_a_credential(settings: Settings, auth: TokenService) -> None:
    """A hash is unrepresentable, not merely omitted."""
    with build(
        settings,
        auth,
        user_admin=UserAdminService(
            InMemoryUserDirectory([user(1, role=UserRole.admin, email="ana@corp.example")])
        ),
    ) as client:
        response = client.get(
            "/api/v1/users",
            headers=headers(client.app.state.token_service, "admin"),  # type: ignore[attr-defined]
        )

    assert response.status_code == 200
    body = response.text
    assert "hash" not in body
    assert "password" not in body
    assert "argon2" not in body
    assert set(response.json()["items"][0]) == {"id", "email", "role", "created_at", "disabled_at"}


def test_a_missing_directory_fails_loudly(settings: Settings, auth: TokenService) -> None:
    """An unwired directory must not read as "nobody is registered"."""
    with build(settings, auth) as client:
        del client.app.state.user_admin  # type: ignore[attr-defined]
        token = headers(client.app.state.token_service, "admin")  # type: ignore[attr-defined]
        with pytest.raises(RuntimeError, match="user_admin"):
            client.get("/api/v1/users", headers=token)


def test_an_empty_directory_says_so_rather_than_inventing_an_admin(
    settings: Settings, auth: TokenService
) -> None:
    """The build ships no bootstrap account, and the empty state is a fact."""
    with build(settings, auth) as client:
        response = client.get(
            "/api/v1/users",
            headers=headers(client.app.state.token_service, "admin"),  # type: ignore[attr-defined]
        )

    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0, "active_admins": 0}
