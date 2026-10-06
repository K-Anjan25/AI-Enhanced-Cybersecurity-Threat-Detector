"""T-320: the API reference is generated from the schemas and cannot drift.

The acceptance criterion is that a route missing a request or response schema
fails CI. It is asserted two ways: the real application must have no problems at
all, and small applications built to break exactly one rule at a time must be
caught -- a rule whose negative case is never exercised is a rule nobody knows
still works (the same reason the exemption sets are parameters).

The published ``api-reference.md`` is asserted byte-equal to a fresh render,
which is exactly the check ``scripts/generate_api_reference.py --check`` runs in
CI, so the file the build ships cannot describe a field the code does not send.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from app.api.openapi_docs import (
    BODYLESS_POSTS,
    EXEMPT_ROUTES,
    documentation_problems,
    ndjson_batch_body,
    render_reference,
)
from app.auth.rbac import registered_paths
from app.core.config import Settings
from fastapi import FastAPI, Response
from pydantic import BaseModel

REFERENCE = Path(__file__).resolve().parents[2] / "api-reference.md"
GENERATOR = Path(__file__).resolve().parents[2] / "scripts" / "generate_api_reference.py"


class Record(BaseModel):
    """A minimal body and response for the small applications below."""

    name: str


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """The real application, built the way the tests build it."""
    from app.main import create_app

    return create_app(settings)


def _generator() -> ModuleType:
    """The generator script, imported without running it."""
    spec = importlib.util.spec_from_file_location("generate_api_reference", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _problems(app: FastAPI, bodyless: frozenset[str] = frozenset()) -> list[str]:
    """The rule's verdict on a small application.

    A small application serves the framework's own ``/docs`` and friends, so the
    exemptions that apply are the ones for the routes it really has; ``bodyless``
    defaults to empty because it has none of this service's routes.
    """
    served = set(registered_paths(app.routes))
    exempt = {path: reason for path, reason in EXEMPT_ROUTES.items() if path in served}
    return documentation_problems(app, exempt=exempt, bodyless=bodyless)


def _documented_app() -> FastAPI:
    """A small application that satisfies every part of the rule."""
    app = FastAPI(title="Small", version="1.0.0")

    @app.get("/records/{record_id}", summary="Read one record")
    async def read_record(record_id: str) -> Record:
        return Record(name=record_id)

    @app.post("/records", summary="Create one record")
    async def create_record(record: Record) -> Record:
        return record

    return app


# --- the real application ---------------------------------------------------


def test_the_real_application_documents_every_operation(app: FastAPI) -> None:
    """The criterion, applied to the application the build ships."""
    assert documentation_problems(app) == []


def test_a_route_added_without_a_schema_fails(settings: Settings) -> None:
    """A new route that documents nothing must fail, not slip through."""
    from app.main import create_app

    app = create_app(settings)

    @app.post("/api/v1/undocumented")
    async def undocumented() -> Response:  # pragma: no cover - never called
        return Response()

    problems = documentation_problems(app)
    assert "POST /api/v1/undocumented documents 200 as application/json with no schema" in problems
    assert "POST /api/v1/undocumented accepts a body but documents no request schema" in problems


def test_a_documented_small_application_passes() -> None:
    """The other direction: the rule is capable of reporting nothing."""
    assert _problems(_documented_app()) == []


# --- the rule's negative cases ----------------------------------------------


def test_a_route_without_a_response_schema_fails() -> None:
    """A raw ``Response`` has no model, and an empty JSON schema is not one."""
    app = FastAPI()

    @app.get("/bytes", summary="Raw bytes")
    async def raw() -> Response:
        return Response(content=b"")

    assert _problems(app) == ["GET /bytes documents 200 as application/json with no schema"]


@pytest.mark.parametrize("method", ["post", "put", "patch"])
def test_a_body_method_without_a_body_fails(method: str) -> None:
    """Every body method documents a body, not just POST."""
    app = FastAPI()

    @app.api_route("/ping", methods=[method], summary="Ping")
    async def ping() -> Record:
        return Record(name="pong")

    assert _problems(app) == [
        f"{method.upper()} /ping accepts a body but documents no request schema"
    ]


def test_an_operation_without_a_summary_fails() -> None:
    """Each operation has to say what it does."""
    app = FastAPI()

    @app.get("/quiet", summary=" ", response_model=Record)
    async def quiet() -> Record:
        return Record(name="x")

    assert _problems(app) == ["GET /quiet has no summary"]


def test_a_reference_to_a_missing_component_fails() -> None:
    """A body declared with ``openapi_extra`` still has to name a real schema."""
    app = FastAPI()

    @app.post(
        "/records",
        summary="Create one record",
        openapi_extra={
            "requestBody": {
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/Missing"}}
                }
            }
        },
    )
    async def create_record(record: Record) -> Record:
        return record

    assert _problems(app) == [
        "schema reference #/components/schemas/Missing does not resolve to a component"
    ]


def test_a_served_route_with_no_operation_fails() -> None:
    """``include_in_schema=False`` serves a route the document does not describe."""
    app = FastAPI()

    @app.get("/hidden", include_in_schema=False)
    async def hidden() -> Record:
        return Record(name="x")

    assert _problems(app) == ["/hidden is served but has no operation in the schema"]


def test_an_operation_with_no_success_response_fails() -> None:
    """A route that only documents a failure is not a contract anyone can use."""
    app = FastAPI()

    @app.get("/boom", summary="Boom", status_code=500)
    async def boom() -> Record:
        return Record(name="x")

    assert _problems(app) == ["GET /boom documents no success response"]


def test_a_success_status_documented_without_content_fails() -> None:
    """201 is not a no-content status: it has to say what the response is."""
    app = FastAPI()

    @app.post("/nothing", summary="Nothing", status_code=201, response_class=Response)
    async def nothing() -> None: ...

    assert _problems(app, frozenset({"/nothing"})) == [
        "POST /nothing documents 201 with neither a schema nor a no-content status"
    ]


def test_a_schema_that_is_not_an_object_is_reported_not_crashed_on() -> None:
    """A malformed document is a problem to report, not an exception to raise."""
    app = FastAPI()

    @app.get(
        "/malformed",
        summary="Malformed",
        openapi_extra={
            "responses": {
                "200": {"content": {"application/json": {"schema": ["not", "a", "mapping"]}}}
            }
        },
    )
    async def malformed() -> Record:
        return Record(name="x")

    assert _problems(app) == ["GET /malformed documents 200 as application/json with no schema"]


def test_a_malformed_request_body_schema_is_reported_not_crashed_on() -> None:
    """A body that is not an object is a problem to report, and safe to render."""
    app = FastAPI()

    @app.post(
        "/malformed",
        summary="Malformed",
        openapi_extra={
            "requestBody": {"content": {"application/json": {"schema": ["not", "a", "mapping"]}}}
        },
    )
    async def malformed(record: Record) -> Record:
        return record

    assert _problems(app) == [
        "POST /malformed documents its request body as application/json with no schema"
    ]
    assert "| `POST` | `/malformed` |" in render_reference(app)


def test_a_path_level_parameter_list_is_not_an_operation(app: FastAPI) -> None:
    """OpenAPI allows a shared parameter list beside the methods; it is not one."""
    original = app.openapi

    def with_parameters() -> dict:
        schema = original()
        schema["paths"]["/healthz"]["parameters"] = [
            {"name": "verbose", "in": "query", "schema": {"type": "boolean"}}
        ]
        return schema

    app.openapi = with_parameters  # type: ignore[method-assign]
    assert documentation_problems(app) == []


def test_a_union_type_renders_once_and_skips_an_empty_arm(app: FastAPI) -> None:
    """A type cell is one readable line: no repeated arm, no empty union."""
    original = app.openapi

    def with_union() -> dict:
        schema = original()
        schema["components"]["schemas"]["UnionRecord"] = {
            "type": "object",
            "properties": {
                "name": {"anyOf": [], "oneOf": [{"type": "string"}, {"type": "string"}]}
            },
        }
        return schema

    app.openapi = with_union  # type: ignore[method-assign]
    section = render_reference(app).split("### `UnionRecord`", 1)[1]
    row = next(line for line in section.splitlines() if "`name`" in line)
    assert "`string`" in row
    assert " or " not in row


def test_a_pipe_in_a_summary_cannot_break_the_table() -> None:
    """A summary is free text; it must not be able to end a markdown row."""
    app = FastAPI()

    @app.get("/pipes", summary="Reads | writes\nboth")
    async def pipes() -> Record:
        return Record(name="x")

    row = next(line for line in render_reference(app).splitlines() if "`/pipes`" in line)
    assert "Reads \\| writes both" in row


# --- exemptions are asserted to still be needed -----------------------------


def test_an_exempt_route_with_an_operation_is_reported(app: FastAPI) -> None:
    """A fixed route left on the exempt list must not stay there unnoticed."""
    problems = documentation_problems(app, exempt={**EXEMPT_ROUTES, "/healthz": "believed exempt"})
    assert "/healthz is exempt but has an operation in the schema" in problems


def test_an_exempt_route_without_a_reason_is_reported(app: FastAPI) -> None:
    """An exemption has to say why, or it is just a hole."""
    problems = documentation_problems(app, exempt={**EXEMPT_ROUTES, "/healthz": " "})
    assert "/healthz is exempt from the schema without a reason" in problems


def test_an_exempt_route_that_is_not_served_is_reported(app: FastAPI) -> None:
    """A stale exemption for a route that no longer exists is a lie."""
    problems = documentation_problems(app, exempt={**EXEMPT_ROUTES, "/api/v1/gone": "removed"})
    assert "/api/v1/gone is exempt from the schema but is not served" in problems


def test_a_bodyless_exemption_that_is_not_needed_is_reported(app: FastAPI) -> None:
    """A GET does not need an exemption from documenting a request body."""
    problems = documentation_problems(app, bodyless=frozenset({*BODYLESS_POSTS, "/healthz"}))
    assert "/healthz is exempt from a request body but takes none" in problems


def test_a_bodyless_exemption_for_a_missing_route_is_reported(app: FastAPI) -> None:
    """Exempting a route that is not documented exempts nothing."""
    problems = documentation_problems(app, bodyless=frozenset({"/api/v1/gone"}))
    assert "/api/v1/gone is exempt from a request body but is not documented" in problems


def test_a_bodyless_exemption_for_a_documented_body_is_reported(app: FastAPI) -> None:
    """An exemption that contradicts the document is stale."""
    problems = documentation_problems(app, bodyless=frozenset({"/api/v1/ingest/flows"}))
    assert "/api/v1/ingest/flows is exempt from a request body but documents one" in problems


# --- the published reference ------------------------------------------------


def test_the_published_reference_is_current(app: FastAPI) -> None:
    """CI's check, in-process: the committed file equals a fresh render."""
    assert REFERENCE.read_text(encoding="utf-8") == render_reference(app)


def test_the_published_reference_says_it_is_generated() -> None:
    """A reader who lands on the file must know not to edit it."""
    assert "do not edit by hand" in REFERENCE.read_text(encoding="utf-8")


def test_the_render_ends_with_exactly_one_newline(app: FastAPI) -> None:
    """A blank line at the end is what the end-of-file hook strips; agree with it."""
    rendered = render_reference(app)
    assert rendered.endswith("|\n")
    assert not rendered.endswith("\n\n")


def test_the_renderer_is_deterministic(settings: Settings) -> None:
    """Two builds of the same application render the same bytes."""
    from app.main import create_app

    assert render_reference(create_app(settings)) == render_reference(create_app(settings))


def test_the_reference_publishes_every_documented_route(app: FastAPI) -> None:
    """Every operation in the schema has a row, and no exempt route has one."""
    reference = render_reference(app)
    for path in app.openapi()["paths"]:
        assert f"| `{path}` |" in reference, path
    for path in EXEMPT_ROUTES:
        assert f"| `{path}` |" not in reference, path


def test_the_reference_names_the_media_types_without_models(app: FastAPI) -> None:
    """The scrape and the event stream say what they are served as."""
    reference = render_reference(app)
    assert "| `GET` | `/metrics` | Prometheus metrics | unauthenticated | `200` `text/plain` |" in (
        reference
    )
    assert "| `GET` | `/api/v1/alerts/stream` |" in reference
    assert "`200` `text/event-stream`" in reference


def test_the_reference_renders_a_nested_body_field_type(app: FastAPI) -> None:
    """A nested enum in a declared body renders by name, not as ``any``."""
    assert "| `protocol` | `Protocol` | yes |" in render_reference(app)


def test_the_generator_check_passes_on_the_committed_reference() -> None:
    """The check CI runs, run here: the committed file is what the app renders."""
    assert _generator().main(["--check"]) == 0


def test_the_generator_check_fails_on_a_stale_reference(tmp_path: Path, capsys) -> None:
    """A hand-edited or outdated reference is a failure, not a warning."""
    stale = tmp_path / "api-reference.md"
    stale.write_text("stale\n", encoding="utf-8")
    assert _generator().main(["--check", "--output", str(stale)]) == 1
    assert "stale" in capsys.readouterr().err


def test_the_generator_check_fails_when_the_reference_is_missing(tmp_path: Path, capsys) -> None:
    """Forgetting to commit the rendered reference fails the same way."""
    absent = tmp_path / "absent.md"
    assert _generator().main(["--check", "--output", str(absent)]) == 1
    assert "missing" in capsys.readouterr().err


def test_the_generator_writes_the_reference(app: FastAPI, tmp_path: Path) -> None:
    """Writing it produces the same bytes as rendering it in-process."""
    target = tmp_path / "api-reference.md"
    assert _generator().main(["--output", str(target)]) == 0
    assert target.read_text(encoding="utf-8") == render_reference(app)


def test_the_declared_body_components_are_in_the_document(app: FastAPI) -> None:
    """The ingest bodies' models are components, so their ``$ref``s resolve."""
    components = app.openapi()["components"]["schemas"]
    assert {"FlowRecordIn", "LogRecordIn", "Protocol", "Direction"} <= set(components)


@pytest.mark.parametrize(
    ("path", "model"),
    [("/api/v1/ingest/flows", "FlowRecordIn"), ("/api/v1/ingest/logs", "LogRecordIn")],
)
def test_the_ingest_routes_declare_the_record_body(app: FastAPI, path: str, model: str) -> None:
    """A bulk ingest route accepts one record, an array, or NDJSON of both."""
    body = app.openapi()["paths"][path]["post"]["requestBody"]
    assert set(body["content"]) == {"application/x-ndjson", "application/json"}
    assert f"#/components/schemas/{model}" in json.dumps(body)
    assert f"`{model}`" in render_reference(app)


def test_the_ndjson_body_offers_a_record_or_an_array() -> None:
    """One media type, two shapes -- the schema says which."""
    schema = ndjson_batch_body(Record)["requestBody"]["content"]["application/x-ndjson"]["schema"]
    assert schema["oneOf"][0] == {"$ref": "#/components/schemas/Record"}
    assert schema["oneOf"][1]["type"] == "array"
