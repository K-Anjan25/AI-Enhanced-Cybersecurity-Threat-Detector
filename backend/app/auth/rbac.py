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
from datetime import UTC, datetime
from enum import StrEnum

from fastapi import HTTPException, Request, status
from fastapi.params import Depends as DependsParam

from app.auth.api_keys import (
    ApiKeyRecord,
    ApiKeyStore,
    InvalidKeyFormat,
    KeyDigest,
    Scope,
    looks_like_key,
    verify_key,
)
from app.auth.tokens import MalformedToken, TokenService

__all__ = [
    "API_KEY_ROUTES",
    "ROLE_CAPABILITIES",
    "ROUTE_MATRIX",
    "SCOPE_CAPABILITIES",
    "UNAUTHENTICATED_ROUTES",
    "ApiKeysNotAccepted",
    "Capability",
    "Forbidden",
    "KeyScopeRefused",
    "Principal",
    "PrincipalKind",
    "Role",
    "Scope",
    "Unauthenticated",
    "authenticate",
    "authenticate_request",
    "capabilities_of",
    "capabilities_of_principal",
    "classify",
    "key_route_scope",
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
    #: Also not named by R-53: managing machine credentials is not managing
    #: users, and it is not something every route that reads a user should imply.
    #: Held by admin alone. See D-042.
    # The value is a name, not a secret; the scanner keys on the identifier
    # "api_key", which is exactly what this capability is called.
    API_KEYS = "api_keys"  # pragma: allowlist secret


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
            Capability.API_KEYS,
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
#: Routes that answer without a credential. `/metrics` is here on purpose: a
#: scraper is a process, and what it reads are counters and durations with no
#: alert content and no identifiers (R-58, D-050). Everything else needs a token.
UNAUTHENTICATED_ROUTES: frozenset[str] = frozenset({"/healthz", "/readyz", "/metrics"})

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
    # One alert and its explanation, evidence and context: the detail behind the
    # list, so it is the same read the list is (FR-51, T-404).
    "/api/v1/alerts/{alert_id}": frozenset(Role),
    # Setting a verdict is an analyst action; R-53 makes viewer read-only, so
    # viewer is deliberately absent from the POST.
    "/api/v1/alerts/{alert_id}/verdict": frozenset({Role.ANALYST, Role.RESPONDER, Role.ADMIN}),
    # Reading the verdict history is reading.
    "/api/v1/alerts/{alert_id}/verdicts": frozenset(Role),
    # The log tail and the raw lines behind one cluster (T-407). Reading logs is
    # reading: R-53 gives viewer the read capability, and a log line is the same
    # class of data the alert list already shows a viewer.
    "/api/v1/logs": frozenset(Role),
    "/api/v1/logs/lines": frozenset(Role),
    # Webhook configuration is responder-and-above (R-53). Reading the list is
    # as sensitive as writing it: a target's URL names internal infrastructure.
    "/api/v1/webhooks": frozenset({Role.RESPONDER, Role.ADMIN}),
    "/api/v1/webhooks/{webhook_id}": frozenset({Role.RESPONDER, Role.ADMIN}),
    # API key management is admin-only (D-042). A key is a credential, and
    # issuing one is minting authority: the same decision as creating a user,
    # which R-53 already reserves for admin.
    "/api/v1/keys": frozenset({Role.ADMIN}),
    "/api/v1/keys/{key_id}": frozenset({Role.ADMIN}),
    "/api/v1/keys/scopes": frozenset({Role.ADMIN}),
    # Retention and erasure are R-53's "retention" authority: dropping a month of
    # alerts and erasing a person are both destructive, and both are admin's.
    "/api/v1/retention": frozenset({Role.ADMIN}),
    "/api/v1/retention/run": frozenset({Role.ADMIN}),
    "/api/v1/privacy/erasure": frozenset({Role.ADMIN}),
    "/api/v1/privacy/erasures": frozenset({Role.ADMIN}),
    # Which model is serving, and what it scored, is operational information every
    # role needs to interpret an alert. Changing it is admin's per R-53, which
    # names a `models` capability and gives it to admin alone.
    "/api/v1/models": frozenset(Role),
    "/api/v1/models/{model_id}/metrics": frozenset(Role),
    "/api/v1/models/{model_id}/promote": frozenset({Role.ADMIN}),
    "/api/v1/models/{kind}/rollback": frozenset({Role.ADMIN}),
    # The hunt console's export (T-408). R-53 gives `export` to responder and
    # above, and this is a route that hands a window's worth of alert rows out of
    # the system, so viewer and analyst are deliberately absent: reading is the
    # viewer's job, taking a copy is not.
    "/api/v1/hunt/export": frozenset({Role.RESPONDER, Role.ADMIN}),
    # The triage queue's batch export (T-415, FR-23). The same capability and the
    # same two roles as the hunt export, because it is the same act -- a window's
    # worth of alert rows leaving the system -- and two exports with two role rules
    # would be a way around the stricter one.
    "/api/v1/alerts/export": frozenset({Role.RESPONDER, Role.ADMIN}),
    # User and role administration (T-410). R-53 reserves it for admin alone, and
    # the capability is `users` rather than `read`: the directory names every
    # account and what it may do, which is reconnaissance for anyone planning an
    # escalation.
    "/api/v1/users": frozenset({Role.ADMIN}),
    "/api/v1/users/roles": frozenset({Role.ADMIN}),
    "/api/v1/users/{user_id}/role": frozenset({Role.ADMIN}),
    # The audit trail is read by every role (FR-42, FR-43 reserves the *export*
    # for responder and above). Reading it is reading: no capability beyond the
    # one every authenticated role already holds.
    "/api/v1/audit": frozenset(Role),
    # Thresholds (T-322, FR-18, R-69). The values in force are read by every role:
    # an analyst interprets a score against the bar it was compared to, and a bar
    # nobody can see is a number nobody can check. Moving one is R-53's `models`
    # capability, which admin alone holds -- a recalibration changes what the
    # system alerts on, exactly as a promotion changes what scores it.
    "/api/v1/thresholds": frozenset(Role),
    "/api/v1/thresholds/preview": frozenset(Role),
    "/api/v1/thresholds/recalibrate": frozenset({Role.ADMIN}),
    "/api/v1/thresholds/{family}/{band}": frozenset({Role.ADMIN}),
    # The stream is read-only for every role, viewer included (FR-20). The
    # WebSocket handshake is checked by `authenticate` rather than by the HTTP
    # dependency, because a socket is not a Request -- but it is the same table
    # and the same capabilities, so a socket is not a way around the matrix.
    "/api/v1/alerts/notifications": frozenset(Role),
    "/api/v1/alerts/stream": frozenset(Role),
    "/api/v1/alerts/ws": frozenset(Role),
}


#: Routes an API key may call, and the scope each one needs. **Default-deny**, and
#: a new route is not key-reachable until it appears here -- a key is a machine
#: credential for ingestion (FR-44), so its reach is a decision someone makes
#: rather than a side effect of the role matrix.
API_KEY_ROUTES: dict[tuple[str, str], Scope] = {
    ("POST", "/api/v1/ingest/flows"): Scope.ingest_write,
    ("POST", "/api/v1/ingest/logs"): Scope.ingest_write,
    # A machine that ingests and cannot check that its data landed is half a
    # feature; reading the alert list is the smallest thing that closes the loop.
    ("GET", "/api/v1/alerts"): Scope.alerts_read,
}

#: Which capabilities each scope grants. A key reaches a route only when this
#: grants the capability the route's role matrix requires, so **a key can never
#: hold more than the least-privileged role allowed on that route** -- asserted
#: in the tests rather than left as an intention.
SCOPE_CAPABILITIES: dict[Scope, frozenset[Capability]] = {
    Scope.ingest_write: frozenset({Capability.INGEST}),
    Scope.alerts_read: frozenset({Capability.READ}),
}


class PrincipalKind(StrEnum):
    """What kind of credential authenticated the caller.

    Two kinds, because they are authorised differently and must not be
    conflated: a **user** holds a role and the role's capabilities; an **api
    key** holds scopes and grants only what those scopes map to. A key that
    borrowed a role would be a machine holding a human's authority.
    """

    user = "user"
    api_key = "api_key"  # pragma: allowlist secret


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller: who they are, and what authorised them.

    The subject is carried because a verdict has to record *who* decided, and
    the token is where that identity comes from. It is kept as the token's
    opaque string rather than coerced to an integer: resolving it to a row in
    ``users`` needs the users table, and an ``int()`` here would turn a token
    issued with an email subject into a runtime failure on the verdict path.

    Attributes:
        role: the role a user principal holds, or ``None`` for an API key. A key
            has no role, and the absence is deliberate -- filling it in with the
            owner's role would give a machine more authority than its scopes.
        subject: who the credential names. For a key this is ``api-key:<id>``,
            which identifies the credential in an audit row without carrying
            anything secret.
        kind: which credential produced this principal.
        scopes: the scopes an API key holds; empty for a user.
        key_id: the key's row id, or ``None`` for a user.
    """

    role: Role | None
    subject: str
    kind: PrincipalKind = PrincipalKind.user
    scopes: frozenset[Scope] = frozenset()
    key_id: int | None = None


class Unauthenticated(HTTPException):
    """No usable credential was presented."""

    def __init__(self) -> None:
        """Raise a 401 that advertises the Bearer scheme."""
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )


class ApiKeysNotAccepted(HTTPException):
    """An API key was presented to a route that does not take them.

    403 rather than 401: the credential may be perfectly good, and telling an
    operator that this route speaks a different authentication scheme is not a
    disclosure -- it is a property of the route, not of the key. The alternative
    (verifying the key first and then refusing) would spend a store read to learn
    something the route table already knows.
    """

    def __init__(self) -> None:
        """Raise a 403 that names the scheme mismatch and nothing else."""
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this route does not accept API keys",
        )


class KeyScopeRefused(HTTPException):
    """A key reached a route that takes keys, but not with the scope it needs.

    Distinct from :class:`ApiKeysNotAccepted` because the two are fixed
    differently: one is "use a token here", the other is "issue this key another
    scope". 403 either way, and the detail names the capability rather than the
    secret or the key's id.
    """

    def __init__(self, capability: Capability) -> None:
        """Raise a 403 naming the missing capability."""
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"this API key lacks a scope granting {capability.value!r}",
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


def capabilities_of_principal(principal: Principal) -> frozenset[Capability]:
    """The capabilities a principal holds.

    A user holds their role's; a key holds the union of its scopes' mappings.
    This is the only place authorisation capability is resolved, so a route
    cannot accidentally apply one rule to users and another to keys.

    Raises:
        ValueError: if a principal claims to be a user and carries no role. That
            cannot happen through the two constructors in this module, and
            failing loudly is better than treating a missing role as no
            capabilities *or* as all of them.
    """
    if principal.kind is PrincipalKind.api_key:
        granted: frozenset[Capability] = frozenset()
        for scope in principal.scopes:
            granted |= SCOPE_CAPABILITIES[scope]
        return granted
    if principal.role is None:
        msg = "a user principal must carry a role"
        raise ValueError(msg)
    return ROLE_CAPABILITIES[principal.role]


def key_route_scope(method: str, route_path: str) -> Scope | None:
    """The scope an API key needs for a route, or ``None`` if keys are not accepted."""
    return API_KEY_ROUTES.get((method.upper(), route_path))


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
    if not set(capabilities) <= capabilities_of_principal(caller):
        raise Forbidden(_name_of(caller), capabilities)
    return caller


def _name_of(principal: Principal) -> str:
    """How a refusal names the caller: their role, or the credential kind."""
    return principal.role.value if principal.role is not None else principal.kind.value


def _api_key_headers(headers: Mapping[str, str]) -> tuple[str | None, bool]:
    """Find the API key a request presents, and whether it presented two credentials.

    Returns ``(key, ambiguous)``. A key arrives either as ``X-API-Key`` or as a
    Bearer token shaped like one, because both are things collectors do. One
    header at a time: an ``Authorization`` alongside an ``X-API-Key`` is two
    credentials from one caller, and the failure mode of resolving that by
    precedence is a request authorised by the credential the operator did not
    mean. The request is refused instead, whatever either credential would have
    been good for.
    """
    header_key = headers.get("x-api-key", "").strip()
    scheme, _, bearer = headers.get("authorization", "").partition(" ")
    bearer = bearer.strip() if scheme.lower() == "bearer" else ""
    if header_key and headers.get("authorization", "").strip():
        return None, True
    return header_key or (bearer if looks_like_key(bearer) else None), False


def authenticate_request(request: Request, *capabilities: Capability) -> Principal:
    """Resolve and authorise the caller of an HTTP request.

    The Request-shaped counterpart to :func:`authenticate`, and the one that
    knows about API keys: a key is a credential with a scope, not a role, so it
    needs the route (to check keys are accepted here at all), the store (to
    resolve the digest) and the digest key.

    Raises:
        Unauthenticated: no usable credential, a key that is unknown or revoked,
            or an API-key-shaped string on a route that takes keys when the
            deployment has no key store -- which is a configuration error, but
            answering it as 401 keeps the response shape uniform.
        ApiKeysNotAccepted: an API key presented to a route that does not take them.
        Forbidden: the credential is valid but lacks a capability.
    """
    presented, ambiguous = _api_key_headers(request.headers)
    if ambiguous:
        raise Unauthenticated
    if presented is None:
        return authenticate(request.headers, _token_service(request), *capabilities)

    # API-key path. `scope["route"].path` is the *template* the router matched,
    # which is what API_KEY_ROUTES is keyed by; url.path would carry the ids.
    route_path = getattr(request.scope.get("route"), "path", request.url.path)
    required_scope = key_route_scope(request.method, route_path)
    if required_scope is None:
        raise ApiKeysNotAccepted

    store: ApiKeyStore | None = getattr(request.app.state, "api_key_store", None)
    digest: KeyDigest | None = getattr(request.app.state, "api_key_digest", None)
    if store is None or digest is None:
        msg = "api_key_store and api_key_digest are not configured on app.state"
        raise RuntimeError(msg)
    try:
        record = verify_key(store, digest, presented, at=datetime.now(UTC))
    except InvalidKeyFormat:
        # A key the router accepted as one but the parser rejects: same answer as
        # a wrong secret, because the caller is not entitled to the difference.
        raise Unauthenticated from None
    if record is None:
        raise Unauthenticated

    caller = _principal_from_key(record)
    granted = capabilities_of_principal(caller)
    missing = set(capabilities) - granted
    if missing:
        # One capability or several; the first in declaration order is stable and
        # is the one the route actually demanded.
        raise KeyScopeRefused(min(missing, key=lambda capability: capability.value))
    return caller


def _principal_from_key(record: ApiKeyRecord) -> Principal:
    """Describe an API key as a principal.

    The subject is ``api-key:<id>``, which is what lands in an audit row: it
    identifies the credential, carries nothing secret, and is stable across
    rotations of the key's scopes. It is deliberately not the owner's subject --
    an action taken with a machine credential should read as having been taken
    by that credential, and the admin view is where the two are joined.
    """
    return Principal(
        role=None,
        subject=f"api-key:{record.id}",
        kind=PrincipalKind.api_key,
        scopes=record.scopes,
        key_id=record.id,
    )


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
        return authenticate_request(request, *capabilities)

    # Constructed directly rather than via Depends(): the helper is typed to
    # return Any, which would leak an untyped value into every route signature.
    return DependsParam(dependency)
