"""Role-based access control (R-53).

R-53 names four roles and says escalation paths are explicit. So capabilities
are declared per role in a table rather than derived from an ordering: a linear
``viewer < analyst < responder < admin`` hierarchy would let a new capability
slip into every role above some level by accident, and "explicit" would be a
claim rather than a property.

The matrix is **default-deny**. A route with no entry is refused, so the
mistake that matters — adding an endpoint and forgetting to classify it —
fails closed in production and fails loudly in CI, where ``test_rbac.py``
enumerates every registered route and asserts each one is classified.

The alternative would be a decorator on each route, which fails open: an
undecorated route is simply unprotected, and nothing notices until someone
reads the code looking for the omission.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from fastapi import HTTPException, Request, status
from fastapi.params import Depends as DependsParam

from app.auth.tokens import MalformedToken, TokenService

__all__ = [
    "ROLE_CAPABILITIES",
    "ROUTE_MATRIX",
    "UNAUTHENTICATED_ROUTES",
    "Capability",
    "Forbidden",
    "Principal",
    "Role",
    "Unauthenticated",
    "authenticate",
    "capabilities_of",
    "classify",
    "registered_paths",
    "require",
    "unclassified_routes",
]


class Role(StrEnum):
    """The four roles R-53 defines."""

    VIEWER = "viewer"
    ANALYST = "analyst"
    RESPONDER = "responder"
    ADMIN = "admin"


class Capability(StrEnum):
    """What a request is allowed to do, independent of which route asks."""

    READ = "read"
    VERDICT = "verdict"
    EXPORT = "export"
    WEBHOOK_CONFIG = "webhook_config"
    USERS = "users"
    MODELS = "models"
    RETENTION = "retention"
    #: Not named by R-53, which lists read/verdict/export/webhook/user/model/
    #: retention. Ingest is a write path that a read-only role must not reach,
    #: so it gets its own capability rather than borrowing READ. See D-033.
    INGEST = "ingest"


#: Explicit per R-53. Deliberately written out in full rather than built by
#: accumulating from the role below, so that adding a capability to one role
#: cannot silently grant it to another.
ROLE_CAPABILITIES: dict[Role, frozenset[Capability]] = {
    Role.VIEWER: frozenset({Capability.READ}),
    Role.ANALYST: frozenset({Capability.READ, Capability.VERDICT, Capability.INGEST}),
    Role.RESPONDER: frozenset(
        {
            Capability.READ,
            Capability.VERDICT,
            Capability.EXPORT,
            Capability.WEBHOOK_CONFIG,
            Capability.INGEST,
        }
    ),
    Role.ADMIN: frozenset(
        {
            Capability.READ,
            Capability.VERDICT,
            Capability.EXPORT,
            Capability.WEBHOOK_CONFIG,
            Capability.USERS,
            Capability.MODELS,
            Capability.RETENTION,
            Capability.INGEST,
        }
    ),
}

#: Routes that must be reachable without a token. Liveness and readiness only:
#: an orchestrator that has to authenticate before it can learn the process is
#: dead will restart it in a loop.
UNAUTHENTICATED_ROUTES: frozenset[str] = frozenset({"/healthz", "/readyz"})

#: Framework documentation endpoints. Excluded from the matrix because they are
#: mounted by FastAPI itself and are disabled outside development.
DOC_ROUTES: frozenset[str] = frozenset(
    {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
)

#: Route path to the roles permitted to call it. **Default-deny:** anything
#: absent is refused. Every new endpoint needs an entry here, and
#: ``test_rbac.py`` fails CI until it has one.
ROUTE_MATRIX: dict[str, frozenset[Role]] = {
    # Ingest is a write path: a viewer is read-only per R-53 and must not reach
    # it, so viewer is deliberately absent from both entries.
    "/api/v1/ingest/flows": frozenset({Role.ANALYST, Role.RESPONDER, Role.ADMIN}),
    "/api/v1/ingest/logs": frozenset({Role.ANALYST, Role.RESPONDER, Role.ADMIN}),
    # Reading alerts is the viewer's whole job, so viewer is present here.
    "/api/v1/alerts": frozenset(Role),
    # Setting a verdict is an analyst action; R-53 makes viewer read-only, so
    # viewer is deliberately absent from the POST.
    "/api/v1/alerts/{alert_id}/verdict": frozenset({Role.ANALYST, Role.RESPONDER, Role.ADMIN}),
    # Reading the verdict history is reading.
    "/api/v1/alerts/{alert_id}/verdicts": frozenset(Role),
    # Webhook configuration is responder-and-above (R-53). Reading the list is
    # as sensitive as writing it: a target's URL names internal infrastructure.
    "/api/v1/webhooks": frozenset({Role.RESPONDER, Role.ADMIN}),
    "/api/v1/webhooks/{webhook_id}": frozenset({Role.RESPONDER, Role.ADMIN}),
    # The audit trail is read by every role (FR-42, FR-43 reserves the *export*
    # for responder and above). Reading it is reading: no capability beyond the
    # one every authenticated role already holds.
    "/api/v1/audit": frozenset(Role),
    # The stream is read-only for every role, viewer included (FR-20). The
    # WebSocket handshake is checked by `authenticate` rather than by the HTTP
    # dependency, because a socket is not a Request -- but it is the same table
    # and the same capabilities, so a socket is not a way around the matrix.
    "/api/v1/alerts/notifications": frozenset(Role),
    "/api/v1/alerts/stream": frozenset(Role),
    "/api/v1/alerts/ws": frozenset(Role),
}


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller: their role, and the subject that names them.

    The subject is carried because a verdict has to record *who* decided, and
    the token is where that identity comes from. It is kept as the token's
    opaque string rather than coerced to an integer: resolving it to a row in
    ``users`` needs the users table, and an ``int()`` here would turn a token
    issued with an email subject into a runtime failure on the verdict path.
    """

    role: Role
    subject: str


class Unauthenticated(HTTPException):
    """No usable credential was presented."""

    def __init__(self) -> None:
        """Raise a 401 that advertises the Bearer scheme."""
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )


class Forbidden(HTTPException):
    """The credential is valid but the role is not allowed here."""

    def __init__(self, role: str, required: Iterable[Capability]) -> None:
        """Raise a 403 naming the caller's role.

        The capability is deliberately not echoed, so a response cannot be used
        to enumerate which capabilities exist behind a route.
        """
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"role {role!r} is not permitted on this route",
        )
        self.required = frozenset(required)


def capabilities_of(role: Role) -> frozenset[Capability]:
    """The capabilities a role holds."""
    return ROLE_CAPABILITIES[role]


def classify(path: str) -> frozenset[Capability] | None:
    """The capabilities a route requires, or None if it is unclassified.

    None is not "open to everyone". It means nobody classified this route, and
    callers must refuse.
    """
    roles = ROUTE_MATRIX.get(path)
    if roles is None:
        return None
    intersection: frozenset[Capability] | None = None
    for role in roles:
        caps = ROLE_CAPABILITIES[role]
        intersection = caps if intersection is None else intersection & caps
    return frozenset() if intersection is None else intersection


def registered_paths(routes: Iterable[object]) -> list[str]:
    """Every HTTP path reachable on the application, walking nested routers.

    ``include_router`` does not flatten: the parent holds an ``_IncludedRouter``
    container whose ``original_router`` holds the real routes. Reading
    ``route.path`` over ``app.routes`` therefore yields the documentation
    endpoints and nothing else, and a completeness check built on it passes
    vacuously -- which is worse than failing, because it looks like coverage.
    """
    paths: list[str] = []
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.append(path)
        nested = getattr(route, "original_router", None) or getattr(route, "router", None)
        if nested is not None:
            paths.extend(registered_paths(getattr(nested, "routes", [])))
    return paths


def unclassified_routes(routes: Iterable[object]) -> list[str]:
    """Every registered route that is neither classified nor explicitly exempt.

    This is what makes "adding a route without a matrix entry fails CI" true:
    the check reads the live application rather than a list someone maintains.
    """
    classified = ROUTE_MATRIX.keys() | UNAUTHENTICATED_ROUTES | DOC_ROUTES
    return sorted({p for p in registered_paths(routes) if p not in classified})


def _token_service(request: Request) -> TokenService:
    service: TokenService | None = getattr(request.app.state, "token_service", None)
    if service is None:
        msg = "token_service is not configured on app.state"
        raise RuntimeError(msg)
    return service


def _principal_from_request(request: Request) -> Principal:
    """Extract and validate the caller's identity from the bearer token."""
    return _principal_from_headers(request.headers, _token_service(request))


def _principal_from_headers(headers: Mapping[str, str], token_service: TokenService) -> Principal:
    """Verify a bearer token and describe its holder.

    Takes a header mapping rather than a Request so the WebSocket handshake,
    which has no Request, authenticates through exactly this code.
    """
    header = headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Unauthenticated
    try:
        claims = token_service.verify_access(token)
    except MalformedToken as exc:
        raise Unauthenticated from exc
    raw_role = str(claims.get("role", ""))
    try:
        role = Role(raw_role)
    except ValueError as exc:
        # An unknown role is not a privilege. Refuse rather than default.
        raise Forbidden(raw_role, ()) from exc
    return Principal(role=role, subject=str(claims.get("sub", "")))


def authenticate(
    headers: Mapping[str, str],
    token_service: TokenService,
    *capabilities: Capability,
) -> Principal:
    """Resolve and authorise a caller from headers and a token service.

    The non-Request entry point to the same check :func:`require` performs, for
    a transport that has no Request -- the WebSocket handshake. Sharing the
    implementation is the point: a second copy of "is this token valid, does
    this role hold this capability" is how a socket ends up being the way around
    a route's permissions.

    Raises:
        Unauthenticated: no usable bearer token was presented.
        Forbidden: the token is valid but the role lacks a capability.
    """
    caller = _principal_from_headers(headers, token_service)
    if not set(capabilities) <= ROLE_CAPABILITIES[caller.role]:
        raise Forbidden(caller.role.value, capabilities)
    return caller


def require(*capabilities: Capability) -> DependsParam:
    """Build a dependency that demands every named capability.

    Usage::

        @router.post("/verdict", dependencies=[Depends(require(Capability.VERDICT))])

    The route must also appear in ROUTE_MATRIX; the dependency checks the
    caller's capabilities and the matrix is what CI checks for completeness.

    Returns the :class:`Principal` so a route that needs to record *who* acted
    -- a verdict, an audit entry -- can take ``caller: Annotated[Principal,
    require(...)]`` and get it without decoding the token a second time.
    """

    def dependency(request: Request) -> Principal:
        return authenticate(request.headers, _token_service(request), *capabilities)

    # Constructed directly rather than via Depends(): the helper is typed to
    # return Any, which would leak an untyped value into every route signature.
    return DependsParam(dependency)
