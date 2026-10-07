"""T-423: the dashboard reads the fields the API sends (R-14, R-92).

The frontend audit found five places where `dashboard/src/api/*.ts` declared a field
the server does not send, and two of them were rendered: the erasure report's
preserved list was typed `{store, reason}` against `PreservedLedgerOut{name, reason}`
and drew `undefined`, and a recalibration's toast read `window_days` against
`RecalibrationOut{since, until, quantile}` and said "over undefined days". Neither
could fail loudly: **TypeScript checks the dashboard against its own interfaces, and
a wrong name is a wrong name on both sides of that check.** The only way to catch it
is to compare the two dialects, which is what this file does.

How it works, and what it deliberately does not do:

* **The models are imported, not parsed.** Every `BaseModel` in `app.schemas` is
  collected through `model_fields`, so the comparison is against the running schema
  — the same objects FastAPI serialises with, inheritance included.
* **The interfaces are read from source.** The dashboard's types are erased at
  runtime, so the only description of them is the text; `_ts_interfaces` reads
  `*.ts` under `dashboard/src/api`, including interfaces nothing exports (a wire
  shape that is not exported is still on the wire).
* **Every interface is classified.** `SHAPES` pairs an interface with its model and
  `NOT_A_SHAPE` names the ones that are not a server shape at all, each with its
  reason. An interface in neither list fails, so a new API type has to be decided
  rather than slip past the check; a name in a list that no longer exists fails too.
* **Only one direction is an error.** A field the dashboard declares and the model
  does not have is the defect — the UI reads `undefined`, or its value never
  arrives. A model field the dashboard omits is *not* checked: the screens are
  allowed not to model data they do not read, and demanding the mirror image would
  force a type for every optional extra the API grows.
* **Nested objects are named, not inline.** `_inline_objects` refuses an object
  literal inside an interface body, because a nested shape written inline cannot be
  paired with a model and is therefore invisible to the comparison above. The two
  shapes this found (`AlertNotification`, and the erasure rows this file's docstring
  opens with) are now named.

Not runnable without the dashboard: the whole file skips when `dashboard/src/api`
is absent, which is the shape every other cross-artifact check in this repository
uses (see `tests/test_schema_conformance.py`).
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import re
from pathlib import Path

import app.schemas as schemas_package
import pytest
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "dashboard" / "src" / "api"

if not API_DIR.is_dir():  # pragma: no cover - the monorepo always has it
    pytest.skip("the dashboard is not part of this checkout", allow_module_level=True)


#: One dashboard interface, and the model the route that fills it returns.
#:
#: The names differ because the two vocabularies differ: the dashboard calls a user
#: `AdminUser` because `AdminUser` is what the panel renders, while the API calls the
#: resource `UserOut`. Pairing them is a decision, and a decision recorded here is
#: reviewable; fuzzy matching is not (it paired `AlertWindow`, a client-side walk,
#: with nothing and said nothing about it).
SHAPES: tuple[tuple[str, str], ...] = (
    # --- authentication --------------------------------------------------------
    ("AuthStatus", "AuthStatusOut"),
    ("SessionCredentials", "TokenPairOut"),
    # The refresh helper consumes the credential subset of the same token response.
    ("RefreshedCredentials", "TokenPairOut"),
    # --- admin: users, keys, thresholds, retention, audit -----------------------
    ("AdminUser", "UserOut"),
    ("UserList", "UserListOut"),
    ("RoleInfo", "RoleNameOut"),
    ("RoleList", "RoleListOut"),
    ("RoleChange", "RoleChangeOut"),
    ("ApiKey", "ApiKeyOut"),
    ("ApiKeyIssued", "ApiKeyIssuedOut"),
    ("ApiKeyList", "ApiKeyListOut"),
    ("ScopeInfo", "ScopeOut"),
    ("ScopeList", "ScopeListOut"),
    ("Threshold", "ThresholdOut"),
    ("ThresholdList", "ThresholdListOut"),
    ("ThresholdSet", "ThresholdSetOut"),
    ("ThresholdImpact", "ThresholdImpactOut"),
    ("RecalibrationOutcome", "ThresholdOutcomeOut"),
    ("RecalibrationResult", "RecalibrationOut"),
    ("RetentionPolicy", "RetentionPolicyOut"),
    ("WindowPartition", "DroppedPartitionOut"),
    ("Unevictable", "UnevictableOut"),
    ("RetentionPlan", "RetentionPlanOut"),
    ("RetentionRun", "RetentionRunOut"),
    ("ErasureTarget", "ErasureTargetOut"),
    ("PreservedLedger", "PreservedLedgerOut"),
    ("ErasureReport", "ErasureReportOut"),
    ("AuditEntry", "AuditEntryOut"),
    ("AuditPage", "AuditPageOut"),
    # --- alerts ----------------------------------------------------------------
    ("AlertRow", "AlertRow"),
    ("AlertPage", "AlertPage"),
    ("AlertExportBody", "AlertExportRequest"),
    # --- flows -----------------------------------------------------------------
    ("FlowBucket", "FlowBucketOut"),
    ("FlowEntity", "FlowEntityOut"),
    ("FlowEdge", "FlowEdgeOut"),
    ("FlowTotals", "FlowTotalsOut"),
    ("FlowWindow", "FlowWindowOut"),
    ("FlowFilters", "FlowFiltersOut"),
    ("FlowAggregate", "FlowAggregateOut"),
    # --- hunt ------------------------------------------------------------------
    ("HuntExportBody", "HuntExportRequest"),
    # --- logs ------------------------------------------------------------------
    ("LogLine", "LogLineOut"),
    ("LogCluster", "LogClusterOut"),
    # The shared subset of both log reads; checked against the clustered one, since
    # the store's own fields (`source`, `retained_*`, `dropped_lines`) are on both.
    ("LogRetention", "LogTailOut"),
    ("LogTail", "LogTailOut"),
    ("LogLines", "LogLinesOut"),
    # --- models ----------------------------------------------------------------
    ("MetricPoint", "MetricPointOut"),
    ("ConfusionMatrix", "ConfusionMatrixOut"),
    ("ScoreHistogramBin", "ScoreHistogramBinOut"),
    ("ScoreHistogram", "ScoreHistogramOut"),
    ("EvaluationDetails", "EvaluationDetailsOut"),
    ("ModelMetrics", "ModelMetricsOut"),
    ("ModelVersion", "ModelOut"),
    ("ModelList", "ModelListOut"),
    ("ModelTransition", "ModelTransitionOut"),
    # --- realtime --------------------------------------------------------------
    ("AlertNotification", "AlertNotificationOut"),
    ("NotificationsPayload", "AlertNotificationsOut"),
    # --- webhooks --------------------------------------------------------------
    ("WebhookTarget", "WebhookOut"),
    ("WebhookIssued", "WebhookCreatedOut"),
    ("WebhookList", "WebhookListOut"),
    ("DeliveryRecord", "DeliveryOut"),
    ("DeliveryList", "DeliveryListOut"),
    # A request rather than a response, and checked in the same direction on purpose:
    # `WebhookCreate` is `extra="forbid"`, so a field the dashboard sends that the
    # model does not have is a 422 rather than an ignored extra.
    ("WebhookCreate", "WebhookCreate"),
)

#: Interfaces that are not a server shape, and what each one is instead.
NOT_A_SHAPE: tuple[tuple[str, str], ...] = (
    (
        "AuditQuery",
        "the audit panel's filter state; the route takes them as individual query parameters",
    ),
    ("AlertListParams", "the `/alerts` list's filter bundle, in the client's spelling"),
    ("AlertWindow", "assembled by walking `/alerts` page by page; there is no window route"),
    ("WindowRequest", "that walk's own bounds, which are the client's"),
    ("RequestOptions", "the fetch wrapper's options (signal, headers), not a payload"),
    ("ExportDocument", "built in the browser from a fetched file (content, filename, rows)"),
    ("FlowParams", "camelCase client parameters; `flowsPath` maps them to the route's query names"),
    ("LogParams", "the same, for `/logs` and `/logs/lines`"),
    ("MetricsSnapshot", "parsed from the Prometheus exposition in the browser"),
    ("ModelListParams", "the registry list's filter bundle"),
    ("SocketLike", "the subset of `WebSocket` the realtime client uses, so a test can fake it"),
    ("SocketFactory", "how that socket is created"),
    ("Clock", "a timer source, so a test can drive the backoff"),
    ("StreamOptions", "the realtime client's own configuration"),
)

_TS_INTERFACE = re.compile(r"^(?:export )?interface (\w+)(?: extends (\w+))? \{", re.M)
_TS_FIELD = re.compile(r"^ {2}([a-z_][a-z0-9_]*)\??\s*:", re.M)
_TS_INLINE_OBJECT = re.compile(r"^ {2}([a-z_][a-z0-9_]*)\??\s*:\s*\{", re.M)


def _interface_body(text: str, start: int) -> str:
    """The lines of one interface, up to the brace that closes it.

    The end matters: without it every later interface's fields are read as this
    one's (the first run of this check reported `AdminUser.action`, a field of
    `AuditEntry`), and the comparison would be against a shape that does not exist.
    """
    lines: list[str] = []
    for line in text[start:].splitlines():
        if line.startswith("}"):
            break
        lines.append(line)
    return "\n".join(lines)


def _ts_interfaces() -> dict[str, set[str]]:
    """Every interface under `dashboard/src/api`, with its fields and its base's."""
    raw: dict[str, tuple[set[str], str | None]] = {}
    for path in sorted(API_DIR.glob("*.ts")):
        if path.name.endswith(".test.ts"):
            continue
        text = path.read_text(encoding="utf-8")
        for match in _TS_INTERFACE.finditer(text):
            name = match.group(1)
            body = _interface_body(text, match.end())
            fields = set(_TS_FIELD.findall(body))
            raw[name] = (fields, match.group(2))
    for name, (fields, base) in list(raw.items()):
        while base is not None and base in raw:
            borrowed, base = raw[base]
            fields |= borrowed
        raw[name] = (fields, None)
    return {name: fields for name, (fields, _) in raw.items()}


def _model_fields() -> dict[str, set[str]]:
    """Every `BaseModel` in `app.schemas`, by class name."""
    models: dict[str, set[str]] = {}
    for module_info in pkgutil.iter_modules(schemas_package.__path__, "app.schemas."):
        module = importlib.import_module(module_info.name)
        for name, value in vars(module).items():
            if (
                inspect.isclass(value)
                and issubclass(value, BaseModel)
                and value.__module__ == module.__name__
            ):
                models[name] = set(value.model_fields)
    return models


def _unmatched(declared: set[str], sent: set[str]) -> set[str]:
    """The fields the dashboard declares that the model does not send."""
    return declared - sent


def test_the_dashboard_is_where_this_thinks_it_is() -> None:
    interfaces = _ts_interfaces()

    # A path typo, a renamed directory or a moved file would otherwise turn this
    # whole file into a check that reads nothing and passes.
    assert len(interfaces) > 60, sorted(interfaces)
    assert "ErasureReport" in interfaces
    assert "RecalibrationResult" in interfaces


def test_every_api_interface_is_classified() -> None:
    interfaces = _ts_interfaces()
    classified = {name for name, _ in SHAPES} | {name for name, _ in NOT_A_SHAPE}

    unclassified = sorted(set(interfaces) - classified)
    gone = sorted(classified - set(interfaces))

    assert not unclassified, (
        f"{unclassified}: pair it with its model in SHAPES, or name it in NOT_A_SHAPE "
        "with its reason"
    )
    assert not gone, f"{gone}: the interface is gone; drop the entry"
    assert len(classified) == len(SHAPES) + len(NOT_A_SHAPE), "a name is listed twice"


def test_the_pairs_are_models_that_exist() -> None:
    models = _model_fields()

    missing = sorted(model for _, model in SHAPES if model not in models)
    assert not missing, missing


def test_no_interface_writes_a_nested_wire_object_inline() -> None:
    """A nested shape has to be named to be checkable.

    A field whose own type is an inline object literal (`preserved: {store: string}[]`)
    cannot be paired with a model, so the comparison above never sees it — which is
    how the erasure rows drifted. An object literal *inside* a function type is not
    that (`SocketLike.onmessage` takes an event), so only a type that opens with the
    brace is an offender.
    """
    offenders: list[str] = []
    for path in sorted(API_DIR.glob("*.ts")):
        if path.name.endswith(".test.ts"):
            continue
        text = path.read_text(encoding="utf-8")
        for match in _TS_INTERFACE.finditer(text):
            body = _interface_body(text, match.end())
            for field_match in _TS_INLINE_OBJECT.finditer(body):
                offenders.append(f"{path.name}: {match.group(1)}.{field_match.group(1)}")

    assert not offenders, (
        "name the nested interface and pair it in SHAPES: an inline object type is "
        "invisible to this check"
    )


def test_every_field_the_dashboard_reads_exists_on_the_model() -> None:
    interfaces = _ts_interfaces()
    models = _model_fields()

    findings: list[str] = []
    for interface, model in SHAPES:
        unknown = _unmatched(interfaces[interface], models[model])
        for field in sorted(unknown):
            findings.append(f"{interface}.{field} is not a field of {model}")

    assert not findings, "\n".join(findings)


def test_the_check_fails_on_the_two_drifts_it_was_written_for() -> None:
    """The detector, on the defects that are why it exists (R-92).

    Both are the real shapes: `PreservedLedgerOut` is `{name, reason}` and the
    dashboard said `{store, reason}`, so the erasure report drew `undefined`; and
    `RecalibrationOut` is `{since, until, quantile, ...}` while the dashboard said
    `window_days`, so the toast said "over undefined days".
    """
    preserved_drift = _unmatched({"store", "reason"}, {"name", "reason"})
    recalibration_drift = _unmatched(
        {"tenant_id", "at", "band", "window_days", "minimum_sample", "considered", "changed"},
        {
            "tenant_id",
            "band",
            "at",
            "since",
            "until",
            "quantile",
            "minimum_sample",
            "considered",
            "changed",
            "outcomes",
        },
    )

    assert preserved_drift == {"store"}
    assert recalibration_drift == {"window_days"}
    # And the check is quiet when the two agree, so a green run means something.
    assert _unmatched({"name", "reason"}, {"name", "reason"}) == set()
