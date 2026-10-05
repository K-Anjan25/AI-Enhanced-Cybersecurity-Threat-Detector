"""The API reference: the coverage rule and the renderer the build publishes (T-320).

The reference is *generated from the Pydantic schemas* -- the components FastAPI
builds from the response models and request bodies -- so it cannot describe a field
the code does not send. What it also has to be is **complete**, and completeness is
the part a hand-written document loses: :func:`documentation_problems` walks the
built application and returns every way it falls short, so a route that is added
without a request or response schema fails CI instead of surprising a client.

The rule, in full:

1. every registered route has an operation in the schema, or an entry on
   :data:`EXEMPT_ROUTES` that says why it cannot have one;
2. every operation has a summary and at least one documented success response;
3. every documented response is a schema, a declared no-content status, or a
   declared media type that carries no JSON model -- an *empty* JSON schema is
   what FastAPI emits for a route that declares no response model, so it does not
   count as documentation, and the same holds for a request body;
4. every body-accepting method documents a request body, unless the path is on
   :data:`BODYLESS_POSTS` -- which is asserted to be *needed*, because an
   exemption that stops being true is how a coverage rule rots (the pattern
   D-048 set for R-56);
5. every ``$ref`` resolves to a component, so the reference cannot print a name
   nothing defines.

The renderer is deterministic -- paths, methods and components sorted, nothing
stamped with a time -- and the committed ``api-reference.md`` is asserted equal to
a fresh render, so the published file cannot drift from the code (D-054).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from app.auth.rbac import ROUTE_MATRIX, UNAUTHENTICATED_ROUTES, registered_paths

__all__ = [
    "BODYLESS_POSTS",
    "EXEMPT_ROUTES",
    "declare_components",
    "documentation_problems",
    "ndjson_batch_body",
    "render_reference",
]

#: Routes that cannot appear in an OpenAPI document, each with the reason it
#: cannot. An entry that is no longer served is reported rather than tolerated.
EXEMPT_ROUTES: Mapping[str, str] = {
    "/api/v1/alerts/ws": "WebSocket: OpenAPI describes HTTP operations only",
    "/docs": "the framework's own documentation UI",
    "/docs/oauth2-redirect": "the framework's own documentation UI",
    "/openapi.json": "the schema this reference is rendered from",
    "/redoc": "the framework's own documentation UI",
}

#: POST routes that legitimately take no request body. Every other body method
#: must document one; the tests assert this set is still necessary.
BODYLESS_POSTS: frozenset[str] = frozenset({"/api/v1/retention/run"})

#: Methods whose request body the rule requires (the ones HTTP defines bodies for).
_BODY_METHODS = frozenset({"post", "put", "patch"})

#: Every HTTP method OpenAPI 3.1 defines for an operation.
_OPERATION_METHODS = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)

#: Response statuses that mean "nothing to describe", so no schema is expected.
_NO_CONTENT = frozenset({"204", "205", "304"})

#: Where a ``$ref`` points when it points at a schema this document defines.
_COMPONENT_PREFIX = "#/components/schemas/"


def ndjson_batch_body(model: type[BaseModel]) -> dict[str, Any]:
    """The declared request body for a route that reads the raw bytes (T-320).

    FastAPI cannot infer a body from ``await request.body()``, so the routes that
    parse the bytes themselves declare what they accept with ``openapi_extra``.
    The schema names the Pydantic model the parse path builds, so the reference
    documents the contract the route actually enforces rather than a copy of it.

    Args:
        model: the record schema one element of the batch must satisfy.
    """
    body = {
        "oneOf": [
            {"$ref": f"{_COMPONENT_PREFIX}{model.__name__}"},
            {"type": "array", "items": {"$ref": f"{_COMPONENT_PREFIX}{model.__name__}"}},
        ],
        "description": (
            "One record, a JSON array of records, or the same records one per line as "
            "`application/x-ndjson`."
        ),
    }
    return {
        "requestBody": {
            "required": True,
            "content": {
                "application/x-ndjson": {"schema": body},
                "application/json": {"schema": body},
            },
        }
    }


def declare_components(app: FastAPI, models: Iterable[type[BaseModel]]) -> None:
    """Add schemas a declared body references to the document (T-320).

    ``openapi_extra`` is passed through verbatim, so a ``$ref`` inside it does not
    make FastAPI generate the component: the schema would name a model nothing
    defines. This renders the models with Pydantic's own JSON-schema generator
    (nested models included) and folds them into ``components.schemas`` the first
    time the document is built, so ``/openapi.json`` stays self-contained for a
    client generating code from it -- and for the reference this module renders.

    Call it before the first request; the document is cached after it is built.
    """
    definitions: dict[str, Any] = {}
    for model in models:
        definition = model.model_json_schema(ref_template="{model}")
        for name, nested in definition.pop("$defs", {}).items():
            definitions.setdefault(name, _rewrite_refs(nested))
        definitions.setdefault(model.__name__, _rewrite_refs(definition))

    original = app.openapi

    def openapi() -> dict[str, Any]:
        """The framework's document, with the declared components folded in."""
        schema = original()
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for name, definition in definitions.items():
            components.setdefault(name, definition)
        return schema

    app.openapi = openapi  # type: ignore[method-assign]


def _rewrite_refs(node: Any) -> Any:  # noqa: ANN401 -- rewrites arbitrary JSON
    """Point a Pydantic JSON schema's ``$ref`` values at this document's components."""
    if isinstance(node, Mapping):
        return {
            key: (
                f"{_COMPONENT_PREFIX}{value}"
                if key == "$ref" and isinstance(value, str)
                else _rewrite_refs(value)
            )
            for key, value in node.items()
        }
    if isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        return [_rewrite_refs(item) for item in node]
    return node


def documentation_problems(
    app: FastAPI,
    *,
    exempt: Mapping[str, str] = EXEMPT_ROUTES,
    bodyless: frozenset[str] = BODYLESS_POSTS,
) -> list[str]:
    """Every way the built application's API falls short of being documented.

    The sets are parameters so a test can hand in a defective one and assert the
    rule bites, rather than trusting that it would.

    Args:
        app: the built application, whose ``openapi()`` document is inspected.
        exempt: routes that cannot have an operation, each with a reason.
        bodyless: body-method paths that legitimately accept no body.

    Returns:
        One message per problem, sorted, empty when the document is complete.
    """
    schema = app.openapi()
    paths: Mapping[str, Mapping[str, Any]] = schema.get("paths", {})
    components: Mapping[str, Any] = schema.get("components", {}).get("schemas", {})
    problems: list[str] = []

    for path in sorted(registered_paths(app.routes)):
        if path not in paths and path not in exempt:
            problems.append(f"{path} is served but has no operation in the schema")

    for path, operations in sorted(paths.items()):
        for method, operation in sorted(operations.items()):
            if method in _OPERATION_METHODS:
                problems.extend(_operation_problems(path, method, operation, bodyless))

    for ref in sorted(set(_iter_refs(schema))):
        if ref.startswith(_COMPONENT_PREFIX) and ref[len(_COMPONENT_PREFIX) :] not in components:
            problems.append(f"schema reference {ref} does not resolve to a component")

    problems.extend(
        _exemption_problems(paths, exempt, bodyless, served=set(registered_paths(app.routes)))
    )
    return sorted(problems)


def _operation_problems(
    path: str, method: str, operation: Mapping[str, Any], bodyless: frozenset[str]
) -> list[str]:
    """Every problem one operation has, naming it in the message."""
    label = f"{method.upper()} {path}"
    problems: list[str] = []
    if not str(operation.get("summary", "")).strip():
        problems.append(f"{label} has no summary")

    responses = operation.get("responses", {})
    success = [str(code) for code in responses if str(code).startswith(("2", "3"))]
    if not success:
        problems.append(f"{label} documents no success response")
    for code in sorted(success):
        content = responses[code].get("content", {})
        if not content:
            if code not in _NO_CONTENT:
                problems.append(
                    f"{label} documents {code} with neither a schema nor a no-content status"
                )
            continue
        problems.extend(_schema_problems(f"{label} documents {code}", content))

    if method in _BODY_METHODS and path not in bodyless:
        body = operation.get("requestBody")
        if not isinstance(body, Mapping) or not body.get("content"):
            problems.append(f"{label} accepts a body but documents no request schema")
        else:
            problems.extend(
                _schema_problems(f"{label} documents its request body", body["content"])
            )
    return problems


def _schema_problems(subject: str, content: Mapping[str, Any]) -> list[str]:
    """Every media type in a content map that claims a JSON model with no schema.

    FastAPI emits an empty schema when a route has no model, and a client cannot
    generate anything from ``any JSON``; the reference must not claim otherwise
    (T-320). A media type that carries no JSON model -- ``text/event-stream``,
    ``text/plain`` -- is documented by being declared.
    """
    problems: list[str] = []
    for media_type, media in sorted(content.items()):
        schema = media.get("schema") if isinstance(media, Mapping) else None
        if _is_json_media_type(media_type) and (not isinstance(schema, Mapping) or not schema):
            problems.append(f"{subject} as {media_type} with no schema")
    return problems


def _is_json_media_type(media_type: str) -> bool:
    """Whether a media type carries a JSON model, which has to be described."""
    return media_type == "application/json" or media_type.endswith("+json")


def _exemption_problems(
    paths: Mapping[str, Mapping[str, Any]],
    exempt: Mapping[str, str],
    bodyless: frozenset[str],
    *,
    served: set[str],
) -> list[str]:
    """Report exemptions that are unnecessary, stale or wrong.

    A coverage rule is only as good as its exceptions: an exemption nobody removed
    after the route was fixed turns "every route is documented" into a slogan.
    """
    problems: list[str] = []
    for path, reason in sorted(exempt.items()):
        if not reason.strip():
            problems.append(f"{path} is exempt from the schema without a reason")
        if path in paths:
            problems.append(f"{path} is exempt but has an operation in the schema")
        elif path not in served:
            problems.append(f"{path} is exempt from the schema but is not served")
    for path in sorted(bodyless):
        if path not in paths:
            problems.append(f"{path} is exempt from a request body but is not documented")
            continue
        operations = paths[path]
        if any(method in _BODY_METHODS for method in operations):
            if any("requestBody" in operation for operation in operations.values()):
                problems.append(f"{path} is exempt from a request body but documents one")
        else:
            problems.append(f"{path} is exempt from a request body but takes none")
    return problems


def _iter_refs(node: Any) -> Iterator[str]:  # noqa: ANN401 -- walks arbitrary JSON
    """Yield every ``$ref`` string anywhere in a JSON document."""
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from _iter_refs(value)
    elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        for item in node:
            yield from _iter_refs(item)


def render_reference(app: FastAPI) -> str:
    """Render the API reference markdown from the application's schemas.

    The output is a pure function of the schema and the route matrix, so the
    committed file can be asserted equal to a fresh render (T-320).
    """
    schema = app.openapi()
    info: Mapping[str, Any] = schema.get("info", {})
    paths: Mapping[str, Mapping[str, Any]] = schema.get("paths", {})
    components: Mapping[str, Any] = schema.get("components", {}).get("schemas", {})

    lines: list[str] = [
        "# AEGIS API reference",
        "",
        "> Generated from the application's Pydantic schemas by",
        "> `scripts/generate_api_reference.py`; do not edit by hand. CI renders this",
        "> document again and fails when the two differ (T-320, D-054).",
        "",
        f"**{info.get('title', 'AEGIS Backend')}** — API version "
        f"`{info.get('version', 'unversioned')}`. Every request and response named below is a",
        "Pydantic schema in `backend/app/schemas/`, and every path is one the application",
        "actually serves.",
        "",
        "## Authentication",
        "",
        "One credential per request (R-53, FR-44): a bearer token as",
        "`Authorization: Bearer <token>`, or an issued API key as `X-API-Key: <key>` or as a",
        "bearer token. The roles column is the route matrix `test_rbac.py` asserts is",
        "complete, so a route cannot be added without one.",
        "",
        "Every operation answers `422` with `HTTPValidationError` when its query parameters",
        "or body do not match the schema below.",
        "",
        "## Routes",
        "",
        "| Method | Path | Summary | Roles | Success | Request body |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for path, operations in sorted(paths.items()):
        for method, operation in sorted(operations.items()):
            lines.append(_route_row(path, method, operation))

    lines.extend(["", "## Schemas", ""])
    for name in sorted(components):
        lines.extend(_schema_section(name, components[name]))
    # Exactly one trailing newline, nothing more: a blank line at the end of the
    # file is what the end-of-file hook strips, and this render has to be
    # byte-identical to the committed file for the drift check to mean anything.
    return "\n".join(lines).rstrip("\n") + "\n"


def _route_row(path: str, method: str, operation: Mapping[str, Any]) -> str:
    """One row of the routes table."""
    success = ", ".join(
        f"`{code}` {_schema_names(operation['responses'][code])}".rstrip()
        for code in sorted(operation.get("responses", {}))
        if str(code).startswith(("2", "3"))
    )
    body = operation.get("requestBody")
    request = _schema_names(body) if isinstance(body, Mapping) else ""
    return (
        f"| `{method.upper()}` | `{path}` | {_cell(str(operation.get('summary', '')))} "
        f"| {_roles_for(path)} | {success} | {request or '—'} |"
    )


def _schema_names(node: Mapping[str, Any]) -> str:
    """What a response's content is: the schema names it refers to, or its media type."""
    names: list[str] = []
    media_types: list[str] = []
    for media_type, media in sorted(node.get("content", {}).items()):
        media_types.append(media_type)
        for name in _names_of(media.get("schema", {})):
            if name not in names:
                names.append(name)
    if names:
        return ", ".join(f"`{name}`" for name in names)
    # A response with no named model -- the Prometheus scrape, the SSE stream --
    # is still described by the media type it is served as.
    return ", ".join(f"`{media_type}`" for media_type in media_types)


def _names_of(schema: Any) -> list[str]:  # noqa: ANN401 -- a JSON schema fragment
    """The component names a JSON schema fragment names, in order, without repeats."""
    if not isinstance(schema, Mapping):
        return []
    names: list[str] = []
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith(_COMPONENT_PREFIX):
        names.append(ref[len(_COMPONENT_PREFIX) :])
    for key in ("oneOf", "anyOf", "allOf"):
        for option in schema.get(key, []):
            names.extend(name for name in _names_of(option) if name not in names)
    items = schema.get("items")
    if isinstance(items, Mapping):
        names.extend(name for name in _names_of(items) if name not in names)
    return names


def _roles_for(path: str) -> str:
    """The roles the route matrix permits, or how the route is reached instead."""
    roles = ROUTE_MATRIX.get(path)
    if roles is not None:
        return ", ".join(sorted(role.value for role in roles))
    return "unauthenticated" if path in UNAUTHENTICATED_ROUTES else "—"


def _schema_section(name: str, schema: Mapping[str, Any]) -> list[str]:
    """A field table for one component schema."""
    description = str(schema.get("description", "")).strip().splitlines()
    lines = [f"### `{name}`", ""]
    if description:
        lines.extend([description[0], ""])
    properties: Mapping[str, Any] = schema.get("properties", {})
    required = set(schema.get("required", []))
    if not properties:
        lines.extend([f"Types: {_type_of(schema)}.", ""])
        return lines
    lines.extend(
        [
            "| Field | Type | Required | Description |",
            "| --- | --- | --- | --- |",
        ]
    )
    for field, spec in properties.items():
        lines.append(
            f"| `{field}` | {_type_of(spec)} | {'yes' if field in required else 'no'} "
            f"| {_cell(str(spec.get('description', '')) or '—')} |"
        )
    lines.append("")
    return lines


def _type_of(schema: Mapping[str, Any]) -> str:
    """Render one JSON schema fragment as a readable type."""
    for key in ("anyOf", "oneOf", "allOf"):
        options = schema.get(key)
        if isinstance(options, Sequence) and not isinstance(options, (str, bytes)):
            rendered: list[str] = []
            for option in options:
                text = _type_of(option) if isinstance(option, Mapping) else "`any`"
                if text not in rendered:
                    rendered.append(text)
            if rendered:
                return " or ".join(rendered)
    names = _names_of(schema)
    if names:
        return ", ".join(f"`{name}`" for name in names)
    if "enum" in schema:
        values = [str(value) for value in schema["enum"]]
        return " or ".join(f"`{value}`" for value in values)
    kind = str(schema.get("type", "any"))
    if kind == "array":
        items = schema.get("items", {})
        inner = _type_of(items) if isinstance(items, Mapping) else "any"
        return f"list of {inner}"
    extra = schema.get("additionalProperties")
    if isinstance(extra, Mapping):
        return f"map of string to {_type_of(extra)}"
    fmt = schema.get("format")
    return f"`{kind} ({fmt})`" if fmt else f"`{kind}`"


def _cell(text: str) -> str:
    """One table cell's text: single line, pipes escaped, empty as an em dash."""
    single = " ".join(text.split())
    return single.replace("|", "\\|") or "—"
