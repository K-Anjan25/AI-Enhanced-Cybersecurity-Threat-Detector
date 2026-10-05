"""T-303: RBAC and the route-role matrix (R-53).

The acceptance criterion is that adding a route without a matrix entry fails
CI, so the central test reads the *live application* rather than a list
someone maintains. A hand-maintained list of routes is exactly the thing that
drifts; enumerating ``app.routes`` cannot.
"""

from __future__ import annotations

import pytest
from app.auth.rbac import (
    DOC_ROUTES,
    ROLE_CAPABILITIES,
    ROUTE_MATRIX,
    UNAUTHENTICATED_ROUTES,
    Capability,
    Forbidden,
    Role,
    Unauthenticated,
    capabilities_of,
    classify,
    registered_paths,
    require,
    unclassified_routes,
)
from app.auth.tokens import TokenService
from app.core.config import Settings
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

SECRET = "r" * 48


@pytest.fixture
def token_service() -> TokenService:
    return TokenService(SECRET)


@pytest.fixture
def app(settings: Settings, token_service: TokenService) -> FastAPI:
    from app.main import create_app

    built = create_app(settings)
    built.state.token_service = token_service
    return built


def _auth(token_service: TokenService, role: str) -> dict[str, str]:
    pair = token_service.issue("alice", role)
    return {"Authorization": f"Bearer {pair.access_token}"}


# --- the matrix is complete -------------------------------------------------


def test_every_registered_route_is_classified(app: FastAPI) -> None:
    """The criterion. An unclassified route must fail here, in CI."""
    missing = unclassified_routes(app.routes)  # type: ignore[arg-type]
    assert missing == [], f"routes have no ROLE_MATRIX entry: {missing}"


def test_adding_a_route_without_an_entry_is_detected() -> None:
    """Proves the check above can actually fail.

    Without this, `test_every_registered_route_is_classified` could be passing
    because `unclassified_routes` always returns empty rather than because the
    matrix is complete.
    """
    rogue = FastAPI()

    @rogue.get("/api/v1/secret")
    def secret() -> dict[str, str]:
        return {"ok": "true"}

    assert unclassified_routes(rogue.routes) == ["/api/v1/secret"]


def test_a_new_route_in_the_real_app_is_detected(settings: Settings) -> None:
    """Same check against the real factory, which is what CI runs."""
    from app.main import create_app

    built = create_app(settings)
    router = APIRouter()

    @router.post("/api/v1/unclassified")
    def unclassified() -> dict[str, str]:
        return {"ok": "true"}

    built.include_router(router)
    assert "/api/v1/unclassified" in unclassified_routes(built.routes)  # type: ignore[arg-type]


def test_the_route_walk_is_not_vacuous(app: FastAPI) -> None:
    """Guards the guard.

    `include_router` does not flatten, so an earlier version of
    `unclassified_routes` read `app.routes`, saw only container objects, found
    no paths at all, and reported the matrix complete. The completeness test
    passed while enforcing nothing. This asserts the walk really reaches the
    endpoint paths, which is the only thing that makes the check above mean
    something.
    """
    paths = set(registered_paths(app.routes))
    assert "/healthz" in paths
    assert "/readyz" in paths
    assert len(paths) > len(UNAUTHENTICATED_ROUTES)


def test_health_probes_are_explicitly_exempt(app: FastAPI) -> None:
    """Not "unclassified" -- deliberately reachable without a token."""
    for path in ("/healthz", "/readyz"):
        assert path in UNAUTHENTICATED_ROUTES
        with TestClient(app) as client:
            assert client.get(path).status_code == 200


# --- the role model ---------------------------------------------------------


def test_the_four_roles_r53_names() -> None:
    assert {r.value for r in Role} == {"viewer", "analyst", "responder", "admin"}


def test_capabilities_are_declared_per_role_not_inherited() -> None:
    """R-53 says escalation is explicit, so the table is written out."""
    assert capabilities_of(Role.VIEWER) == frozenset({Capability.READ})
    assert capabilities_of(Role.ANALYST) == frozenset(
        {Capability.READ, Capability.VERDICT, Capability.INGEST}
    )
    assert capabilities_of(Role.RESPONDER) == frozenset(
        {
            Capability.READ,
            Capability.VERDICT,
            Capability.EXPORT,
            Capability.WEBHOOK_CONFIG,
            Capability.INGEST,
        }
    )
    assert capabilities_of(Role.ADMIN) == frozenset(
        {
            Capability.READ,
            Capability.VERDICT,
            Capability.EXPORT,
            Capability.WEBHOOK_CONFIG,
            Capability.USERS,
            Capability.MODELS,
            Capability.RETENTION,
            Capability.INGEST,
            # T-313: issuing a machine credential is an admin action, and the
            # capability is written into this row rather than inherited from
            # USERS -- the two are separate decisions (D-042).
            Capability.API_KEYS,
        }
    )


def test_every_capability_is_held_by_some_role() -> None:
    """A capability nobody holds is a route nobody can call."""
    held = set().union(*ROLE_CAPABILITIES.values())
    assert held == set(Capability)


def test_no_role_holds_a_capability_outside_the_enum() -> None:
    for caps in ROLE_CAPABILITIES.values():
        assert caps <= set(Capability)


# --- the dependency ---------------------------------------------------------


def _guard_app(token_service: TokenService, *caps: Capability) -> FastAPI:
    probe = FastAPI()
    probe.state.token_service = token_service

    @probe.get("/guarded", dependencies=[require(*caps)])
    def guarded() -> dict[str, str]:
        return {"ok": "true"}

    return probe


def test_a_role_holding_the_capability_passes(token_service: TokenService) -> None:
    with TestClient(_guard_app(token_service, Capability.READ)) as client:
        response = client.get("/guarded", headers=_auth(token_service, "viewer"))
    assert response.status_code == 200


def test_a_role_lacking_the_capability_is_refused(token_service: TokenService) -> None:
    """A viewer must not reach an admin capability."""
    with TestClient(_guard_app(token_service, Capability.USERS)) as client:
        response = client.get("/guarded", headers=_auth(token_service, "viewer"))
    assert response.status_code == 403


def test_an_analyst_cannot_configure_webhooks(token_service: TokenService) -> None:
    """R-53 puts webhook config at responder, not analyst."""
    with TestClient(_guard_app(token_service, Capability.WEBHOOK_CONFIG)) as client:
        response = client.get("/guarded", headers=_auth(token_service, "analyst"))
    assert response.status_code == 403


def test_a_responder_can_export_and_an_analyst_cannot(token_service: TokenService) -> None:
    with TestClient(_guard_app(token_service, Capability.EXPORT)) as client:
        assert client.get("/guarded", headers=_auth(token_service, "responder")).status_code == 200
        assert client.get("/guarded", headers=_auth(token_service, "analyst")).status_code == 403


def test_every_role_is_checked_against_every_capability(token_service: TokenService) -> None:
    """The full matrix, not a sample.

    A route x role test that spot-checks a few cells will pass while a whole
    row is wrong.
    """
    for capability in Capability:
        with TestClient(_guard_app(token_service, capability)) as client:
            for role in Role:
                response = client.get("/guarded", headers=_auth(token_service, role.value))
                expected = 200 if capability in ROLE_CAPABILITIES[role] else 403
                assert response.status_code == expected, f"{role} x {capability}"


def test_no_token_is_a_401_not_a_403(token_service: TokenService) -> None:
    with TestClient(_guard_app(token_service, Capability.READ)) as client:
        response = client.get("/guarded")
    assert response.status_code == 401


def test_a_non_bearer_scheme_is_refused(token_service: TokenService) -> None:
    pair = token_service.issue("alice", "admin")
    with TestClient(_guard_app(token_service, Capability.READ)) as client:
        response = client.get("/guarded", headers={"Authorization": f"Basic {pair.access_token}"})
    assert response.status_code == 401


def test_a_tampered_token_is_a_401(token_service: TokenService) -> None:
    pair = token_service.issue("alice", "viewer")
    forged = pair.access_token[:-4] + "AAAA"
    with TestClient(_guard_app(token_service, Capability.READ)) as client:
        response = client.get("/guarded", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_a_forged_admin_role_from_another_key_is_a_401(token_service: TokenService) -> None:
    attacker = TokenService("a" * 48)
    forged = attacker.issue("mallory", "admin")
    with TestClient(_guard_app(token_service, Capability.USERS)) as client:
        response = client.get(
            "/guarded", headers={"Authorization": f"Bearer {forged.access_token}"}
        )
    assert response.status_code == 401


def test_an_unknown_role_is_refused_rather_than_defaulted(token_service: TokenService) -> None:
    """A role string nobody defined is not a privilege."""
    pair = token_service.issue("alice", "superuser")
    with TestClient(_guard_app(token_service, Capability.READ)) as client:
        response = client.get("/guarded", headers={"Authorization": f"Bearer {pair.access_token}"})
    assert response.status_code == 403


def test_a_missing_token_service_fails_loudly() -> None:
    """A misconfigured app must not silently allow everything."""
    probe = FastAPI()

    @probe.get("/guarded", dependencies=[require(Capability.READ)])
    def guarded() -> dict[str, str]:
        return {"ok": "true"}

    with TestClient(probe, raise_server_exceptions=False) as client:
        response = client.get("/guarded", headers={"Authorization": "Bearer " + "a" * 20})
    assert response.status_code == 500


# --- default-deny -----------------------------------------------------------


def test_an_unclassified_route_has_no_capabilities() -> None:
    assert classify("/api/v1/never-registered") is None


def test_classify_never_returns_open_access_for_an_unknown_route() -> None:
    """None must not be read as "everyone". Callers refuse."""
    assert classify("/api/v1/nope") is None
    assert classify("/healthz") is None


def test_the_matrix_keys_are_real_paths_or_documented(settings: Settings) -> None:
    """A typo in the matrix would silently protect nothing."""
    from app.main import create_app

    # Must walk nested routers exactly as the source does, or the routes added
    # by include_router are invisible and this check passes vacuously.
    known = set(registered_paths(create_app(settings).routes))
    for path in ROUTE_MATRIX:
        assert path in known or path in DOC_ROUTES, f"matrix names an unknown route: {path}"


def test_the_exceptions_carry_the_right_status() -> None:
    assert Unauthenticated().status_code == 401
    assert Forbidden("viewer", ()).status_code == 403


def test_a_403_does_not_leak_the_missing_capability(token_service: TokenService) -> None:
    """Echoing it would let a caller enumerate what sits behind a route."""
    with TestClient(_guard_app(token_service, Capability.USERS)) as client:
        response = client.get("/guarded", headers=_auth(token_service, "viewer"))
    assert "users" not in response.text.lower()
    assert "viewer" in response.text
