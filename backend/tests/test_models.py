"""T-315: model ops -- list, metrics, promote, rollback (FR-30…FR-33).

The acceptance criteria are two, and both are asserted through the API as well as
the service: **promotion to ``active`` requires ``admin``**, and **rollback is one
call**. Around them sit the rules that make a promotion reviewable -- R-68's
immutable ids, R-63's manifest, R-74's sourced metrics -- and the trail behaviour
D-041 establishes: a change is recorded, a no-op is not, and a note never is.

The service tests come first because they are where the state machine lives; the
API tests then assert that the refusals arrive as the right status codes and that
the audit rows say what changed and nothing more.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.auth.rbac import ROUTE_MATRIX, Role
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.main import create_app
from app.services.audit_log import AuditAction, InMemoryAuditTrail
from app.services.model_ops import (
    FORBIDDEN_MODEL_IDS,
    REQUIRED_METRICS,
    FloatingModelId,
    ImmutableArtifact,
    MetricPoint,
    MissingManifest,
    ModelMetrics,
    ModelOpsService,
    ModelVersion,
    NothingToRollBack,
    RefusedTransition,
    UnknownModel,
)
from fastapi.testclient import TestClient

SECRET = "m" * 48
APP_SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
AT = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
SHA_A = "a" * 64
SHA_B = "b" * 64
JUSTIFICATION = "canary looked better on the Q3 holdout"
ROLLBACK_REASON = "scores collapsed after the swap"


def metrics(*, split: str = "temporal:2025-Q4") -> ModelMetrics:
    """A complete FR-31 metric set, every value with its source (R-74)."""
    return ModelMetrics(
        points={
            name: MetricPoint(
                value=0.9, artifact="runs/eval-2025-10-01.json", field=f"metrics.{name}"
            )
            for name in REQUIRED_METRICS
        },
        split=split,
        evaluated_at=AT,
    )


def eval_report(model_id: str) -> dict[str, object]:
    """The serialized textbook run from evaluation.py's hand-checkable example."""
    return {
        "schema_version": "eval@2",
        "model_id": model_id,
        "threshold": 0.5,
        "positives": 2,
        "negatives": 2,
        "confusion": {"tp": 1, "fp": 0, "tn": 2, "fn": 1},
        "score_histogram": [
            {"lower": index / 10, "upper": (index + 1) / 10, "benign": benign, "threat": threat}
            for index, (benign, threat) in enumerate(
                [(0, 0), (1, 0), (0, 0), (0, 1), (1, 0), (0, 0), (0, 0), (0, 0), (0, 1), (0, 0)]
            )
        ],
        "precision": 1.0,
        "recall": 0.5,
        "f1": 2 / 3,
        "metrics": {"roc_auc": 0.75, "pr_auc": 5 / 6, "accuracy": 0.75},
    }


def version(
    model_id: str,
    *,
    kind: str = "flow",
    status: str = "staging",
    manifest: bool = True,
    sha256: str = SHA_A,
    with_metrics: bool = True,
) -> ModelVersion:
    """A registered version, promotable unless a test says otherwise."""
    return ModelVersion(
        model_id=model_id,
        kind=kind,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        artifact_uri=f"artifacts/{model_id}/model.onnx",
        sha256=sha256,
        manifest_present=manifest,
        metrics=metrics() if with_metrics else None,
    )


@pytest.fixture
def ops() -> ModelOpsService:
    """A service with one active flow model, one staging challenger and a log model."""
    service = ModelOpsService()
    service.register(version("flow-2026-08", status="active", sha256=SHA_A))
    service.register(version("flow-2026-10", status="staging", sha256=SHA_B))
    service.register(version("log-2026-09", kind="log", status="active", sha256="c" * 64))
    return service


# --- the service: registration and reads --------------------------------------


def test_an_empty_service_registers_nothing() -> None:
    """R-74: no metric is invented at startup, and no version either."""
    assert ModelOpsService().list() == ()


def test_versions_are_listed_by_kind_then_id() -> None:
    service = ModelOpsService()
    for model_id in ("flow-b", "log-a", "flow-a"):
        service.register(version(model_id, kind=model_id.split("-")[0]))
    assert [item.model_id for item in service.list()] == ["flow-a", "flow-b", "log-a"]


def test_listing_can_be_filtered_by_kind_and_status(ops: ModelOpsService) -> None:
    assert [item.model_id for item in ops.list(kind="flow")] == ["flow-2026-08", "flow-2026-10"]
    assert [item.model_id for item in ops.list(status="active")] == ["flow-2026-08", "log-2026-09"]
    assert [item.model_id for item in ops.list(kind="log", status="staging")] == []


def test_active_returns_the_one_serving_version(ops: ModelOpsService) -> None:
    active = ops.active("flow")
    assert active is not None and active.model_id == "flow-2026-08"
    assert ops.active("log") is not None
    assert ModelOpsService().active("flow") is None


@pytest.mark.parametrize("model_id", sorted(FORBIDDEN_MODEL_IDS))
def test_a_floating_id_is_refused_wherever_it_is_addressed(model_id: str) -> None:
    """R-68: ``latest`` is not a missing model, it is a forbidden pattern."""
    service = ModelOpsService()
    with pytest.raises(FloatingModelId, match="R-68 forbids floating"):
        service.get(model_id)
    with pytest.raises(FloatingModelId):
        service.promote(model_id, actor="admin@corp", justification=JUSTIFICATION)


def test_an_unknown_id_names_what_is_registered(ops: ModelOpsService) -> None:
    with pytest.raises(UnknownModel, match="flow-2026-10"):
        ops.get("flow-2026-11")


def test_re_registering_the_same_bytes_is_a_noop(ops: ModelOpsService) -> None:
    """An unchanged redeploy is ordinary; it must not fail."""
    ops.register(version("flow-2026-10", sha256=SHA_B))
    assert len(ops.list()) == 3


def test_re_registering_an_id_against_other_bytes_is_refused(ops: ModelOpsService) -> None:
    """R-68: a silent content change under a stable name is how a swap hides."""
    with pytest.raises(ImmutableArtifact, match="R-68 forbids overwriting"):
        ops.register(version("flow-2026-10", sha256="d" * 64))


def test_two_actives_of_one_kind_cannot_be_registered(ops: ModelOpsService) -> None:
    with pytest.raises(ValueError, match="already active for kind 'flow'"):
        ops.register(version("flow-2026-11", status="active", sha256="e" * 64))


@pytest.mark.parametrize("bad", ["", "not-a-sha256", "A" * 64, "a" * 63])
def test_a_content_address_that_is_not_a_sha256_is_refused(bad: str) -> None:
    """R-68: a defaulted address would defeat content addressing entirely."""
    with pytest.raises(ValueError, match="content-addressed"):
        version("flow-2026-10", sha256=bad)


def test_a_version_with_no_artifact_location_is_refused() -> None:
    with pytest.raises(ValueError, match="names no artifact location"):
        ModelVersion(
            model_id="flow-2026-10",
            kind="flow",
            status="staging",
            artifact_uri="  ",
            sha256=SHA_A,
            manifest_present=True,
        )


# --- the service: metrics (FR-31, R-74) ---------------------------------------


def test_a_metric_set_must_carry_all_five_of_fr31s_metrics() -> None:
    points = metrics().points
    del points["pr_auc"]
    with pytest.raises(ValueError, match="missing FR-31's"):
        ModelMetrics(points=points, split="temporal:2025-Q4", evaluated_at=AT)


def test_a_metric_set_refuses_a_name_fr31_does_not_define() -> None:
    points = dict(metrics().points)
    points["accuracy"] = MetricPoint(value=0.5, artifact="runs/x.json", field="metrics.accuracy")
    with pytest.raises(ValueError, match="unknown metrics"):
        ModelMetrics(points=points, split="temporal:2025-Q4", evaluated_at=AT)


def test_an_unlabelled_metric_set_is_refused() -> None:
    """A value with no split named is not a claim anyone can check (R-74)."""
    with pytest.raises(ValueError, match="must name the split"):
        ModelMetrics(points=metrics().points, split="   ", evaluated_at=AT)


@pytest.mark.parametrize("value", [-0.01, 1.01, 12.5])
def test_a_metric_outside_the_unit_interval_is_refused(value: float) -> None:
    """FR-31's metrics are proportions; anything else is a units bug or a fabrication."""
    with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
        MetricPoint(value=value, artifact="runs/x.json", field="metrics.precision")


def test_a_metric_with_no_source_is_refused() -> None:
    """R-74: a number nobody can trace is a claim, not a measurement."""
    with pytest.raises(ValueError, match="R-74"):
        MetricPoint(value=0.9, artifact="  ", field="metrics.precision")
    with pytest.raises(ValueError, match="names no field"):
        MetricPoint(value=0.9, artifact="runs/x.json", field="")


def test_a_metric_renders_with_its_provenance() -> None:
    point = MetricPoint(value=0.9137, artifact="runs/eval.json", field="metrics.roc_auc")
    assert point.as_dict() == {
        "value": 0.9137,
        "artifact": "runs/eval.json",
        "field": "metrics.roc_auc",
    }


def test_a_staging_version_may_have_no_recorded_evaluation() -> None:
    """A gap is a fact, not a zero: staged artifacts are often unmeasured yet."""
    assert version("flow-2026-10", with_metrics=False).metrics is None


def test_record_evaluation_ingests_the_recorded_report_and_preserves_sources() -> None:
    service = ModelOpsService()
    service.register(version("flow-2026-11", with_metrics=False, sha256="f" * 64))

    recorded = service.record_evaluation(
        "flow-2026-11",
        eval_report("flow-2026-11"),
        artifact="runs/flow-2026-11/eval.json",
        split="temporal:test",
        evaluated_at=AT,
    )
    result = recorded.metrics
    assert result is not None and result.evaluation is not None
    assert result.get("roc_auc").value == 0.75
    assert result.get("roc_auc").artifact == "runs/flow-2026-11/eval.json"
    assert result.get("roc_auc").field == "metrics.roc_auc"
    assert result.evaluation.confusion.tp == 1
    assert result.evaluation.confusion.fn == 1
    assert result.evaluation.confusion.artifact == "runs/flow-2026-11/eval.json"
    assert result.evaluation.confusion.field == "confusion"
    assert len(result.evaluation.score_histogram.bins) == 10
    assert result.evaluation.score_histogram.bins[3].threat == 1
    assert result.evaluation.score_histogram.artifact == "runs/flow-2026-11/eval.json"
    assert result.evaluation.score_histogram.field == "score_histogram"
    assert (
        service.record_evaluation(
            "flow-2026-11",
            eval_report("flow-2026-11"),
            artifact="runs/flow-2026-11/eval.json",
            split="temporal:test",
            evaluated_at=AT,
        )
        is recorded
    )


def test_evaluation_ingestion_rejects_wrong_schema_model_and_rewrites() -> None:
    service = ModelOpsService()
    service.register(version("flow-2026-11", with_metrics=False, sha256="f" * 64))
    base = {
        "artifact": "runs/flow-2026-11/eval.json",
        "split": "temporal:test",
        "evaluated_at": AT,
    }

    with pytest.raises(ValueError, match="eval@2"):
        service.record_evaluation(
            "flow-2026-11", {**eval_report("flow-2026-11"), "schema_version": "eval@1"}, **base
        )
    with pytest.raises(ValueError, match="does not match"):
        service.record_evaluation("flow-2026-11", eval_report("other-model"), **base)

    service.record_evaluation("flow-2026-11", eval_report("flow-2026-11"), **base)
    with pytest.raises(ImmutableArtifact, match="cannot be rewritten"):
        service.record_evaluation(
            "flow-2026-11",
            eval_report("flow-2026-11"),
            **{**base, "artifact": "runs/another/eval.json"},
        )


def test_evaluation_ingestion_rejects_inconsistent_histogram_counts() -> None:
    service = ModelOpsService()
    service.register(version("flow-2026-11", with_metrics=False, sha256="f" * 64))
    report = eval_report("flow-2026-11")
    report["score_histogram"] = []

    with pytest.raises(ValueError, match="needs 10 bins"):
        service.record_evaluation(
            "flow-2026-11",
            report,
            artifact="runs/flow-2026-11/eval.json",
            split="temporal:test",
            evaluated_at=AT,
        )


def test_evaluation_ingestion_rejects_variable_width_bins() -> None:
    service = ModelOpsService()
    service.register(version("flow-2026-11", with_metrics=False, sha256="f" * 64))
    report = eval_report("flow-2026-11")
    bins = report["score_histogram"]
    assert isinstance(bins, list)
    bins[0] = {**bins[0], "upper": 0.15}
    bins[1] = {**bins[1], "lower": 0.15}

    with pytest.raises(ValueError, match="fixed-width"):
        service.record_evaluation(
            "flow-2026-11",
            report,
            artifact="runs/flow-2026-11/eval.json",
            split="temporal:test",
            evaluated_at=AT,
        )


# --- the service: promotion ---------------------------------------------------


def test_promotion_retires_the_incumbent_in_one_call(ops: ModelOpsService) -> None:
    outcome = ops.promote("flow-2026-10", actor="admin@corp", justification=JUSTIFICATION, at=AT)
    assert outcome.changed is True
    assert outcome.model_id == "flow-2026-10"
    assert outcome.retired == "flow-2026-08"
    active = ops.active("flow")
    assert active is not None and active.model_id == "flow-2026-10"
    retired = ops.get("flow-2026-08")
    assert retired.status == "retired"
    # Its promotion provenance is empty because nobody promoted it through this
    # API: it was registered as the serving version, which is what a process that
    # starts with a model already loaded looks like. The gap is rendered as a gap
    # rather than filled with the actor who happened to retire it.
    assert (retired.promoted_at, retired.promoted_by) == (None, None)


def test_promotion_records_who_when_and_why(ops: ModelOpsService) -> None:
    ops.promote("flow-2026-10", actor="admin@corp", justification=JUSTIFICATION, at=AT)
    promoted = ops.get("flow-2026-10")
    assert (promoted.promoted_at, promoted.promoted_by) == (AT, "admin@corp")
    assert promoted.justification == JUSTIFICATION
    entries = ops.history(kind="flow")
    assert [(entry.activated, entry.retired, entry.actor) for entry in entries] == [
        ("flow-2026-10", "flow-2026-08", "admin@corp")
    ]


def test_promoting_the_active_version_changes_nothing(ops: ModelOpsService) -> None:
    outcome = ops.promote("flow-2026-08", actor="admin@corp", justification=JUSTIFICATION, at=AT)
    assert outcome.changed is False
    assert outcome.retired is None
    assert ops.history(kind="flow") == ()


def test_a_promotion_with_no_justification_is_refused(ops: ModelOpsService) -> None:
    with pytest.raises(ValueError, match="written justification"):
        ops.promote("flow-2026-10", actor="admin@corp", justification="   ", at=AT)


def test_a_retired_version_cannot_be_promoted(ops: ModelOpsService) -> None:
    """R-68 keeps the set of versions that have served traffic append-only."""
    ops.promote("flow-2026-10", actor="admin@corp", justification=JUSTIFICATION, at=AT)
    with pytest.raises(RefusedTransition, match="Roll back to the version it displaced"):
        ops.promote("flow-2026-08", actor="admin@corp", justification=JUSTIFICATION, at=AT)


def test_a_version_without_a_manifest_cannot_be_promoted(ops: ModelOpsService) -> None:
    """R-63: no recorded dataset, seeds and baseline means no production traffic."""
    ops.register(version("flow-2026-11", manifest=False, sha256="f" * 64))
    with pytest.raises(MissingManifest, match="R-63"):
        ops.promote("flow-2026-11", actor="admin@corp", justification=JUSTIFICATION, at=AT)


def test_promoting_an_unknown_version_is_refused(ops: ModelOpsService) -> None:
    with pytest.raises(UnknownModel):
        ops.promote("flow-2026-99", actor="admin@corp", justification=JUSTIFICATION, at=AT)


def test_promoting_one_kind_leaves_the_other_alone(ops: ModelOpsService) -> None:
    """FR-30: the two models are versioned, promoted and rolled back independently."""
    ops.promote("flow-2026-10", actor="admin@corp", justification=JUSTIFICATION, at=AT)
    log = ops.active("log")
    assert log is not None and log.model_id == "log-2026-09"


# --- the service: rollback ----------------------------------------------------


def test_rollback_reverses_the_last_promotion_in_one_call(ops: ModelOpsService) -> None:
    ops.promote("flow-2026-10", actor="admin@corp", justification=JUSTIFICATION, at=AT)
    outcome = ops.rollback("flow", actor="responder@corp", reason=ROLLBACK_REASON, at=AT)
    assert outcome.changed is True
    assert outcome.model_id == "flow-2026-08"
    assert outcome.retired == "flow-2026-10"
    active = ops.active("flow")
    assert active is not None and active.model_id == "flow-2026-08"


def test_a_rollback_marks_the_promotion_it_reversed(ops: ModelOpsService) -> None:
    """The schema's ``rolled_back_at``: one fact in one place."""
    ops.promote("flow-2026-10", actor="admin@corp", justification=JUSTIFICATION, at=AT)
    ops.rollback("flow", actor="responder@corp", reason=ROLLBACK_REASON, at=AT + timedelta(hours=1))
    entry = ops.history(kind="flow")[0]
    assert entry.rolled_back_at == AT + timedelta(hours=1)
    assert entry.activated == "flow-2026-10"


def test_a_second_rollback_moves_further_back(ops: ModelOpsService) -> None:
    """Two promotions, two reversals; the second finds the promotion before."""
    ops.register(version("flow-2026-11", sha256="f" * 64))
    ops.promote("flow-2026-10", actor="admin@corp", justification=JUSTIFICATION, at=AT)
    ops.promote("flow-2026-11", actor="admin@corp", justification=JUSTIFICATION, at=AT)
    first = ops.rollback("flow", actor="admin@corp", reason=ROLLBACK_REASON, at=AT)
    second = ops.rollback("flow", actor="admin@corp", reason=ROLLBACK_REASON, at=AT)
    assert (first.model_id, first.retired) == ("flow-2026-10", "flow-2026-11")
    assert (second.model_id, second.retired) == ("flow-2026-08", "flow-2026-10")


def test_rollback_with_nothing_left_to_reverse_is_refused(ops: ModelOpsService) -> None:
    """The first version of a kind displaced nothing, so there is no version older."""
    with pytest.raises(NothingToRollBack, match="displaced nothing"):
        ops.rollback("flow", actor="admin@corp", reason=ROLLBACK_REASON, at=AT)


def test_rollback_of_a_kind_with_nothing_active_is_refused() -> None:
    service = ModelOpsService()
    service.register(version("flow-2026-10", sha256=SHA_B))
    with pytest.raises(NothingToRollBack, match="nothing to roll back"):
        service.rollback("flow", actor="admin@corp", reason=ROLLBACK_REASON, at=AT)


def test_a_rollback_with_no_reason_is_refused(ops: ModelOpsService) -> None:
    ops.promote("flow-2026-10", actor="admin@corp", justification=JUSTIFICATION, at=AT)
    with pytest.raises(ValueError, match="needs a reason"):
        ops.rollback("flow", actor="admin@corp", reason=" ", at=AT)


def test_a_rolled_back_version_stays_retired_and_a_new_artifact_replaces_it(
    ops: ModelOpsService,
) -> None:
    """A rollback is not a pause: R-68's terminal retirement still holds.

    The version that was serving before the rollback is retired for good, and the
    next promotion must be a new artifact -- so a deployment cannot bounce the same
    two versions back and forth and call each bounce a decision.
    """
    ops.promote("flow-2026-10", actor="admin@corp", justification=JUSTIFICATION, at=AT)
    ops.rollback("flow", actor="admin@corp", reason=ROLLBACK_REASON, at=AT)
    with pytest.raises(RefusedTransition):
        ops.promote("flow-2026-10", actor="admin@corp", justification=JUSTIFICATION, at=AT)
    ops.register(version("flow-2026-12", sha256="1" * 64))
    assert ops.promote(
        "flow-2026-12", actor="admin@corp", justification=JUSTIFICATION, at=AT
    ).changed


def test_history_is_oldest_first_and_filters_by_kind(ops: ModelOpsService) -> None:
    """Promoting the already-active log version appends nothing; a real one does."""
    ops.register(version("log-2026-10", kind="log", sha256="d" * 64))
    ops.promote("flow-2026-10", actor="admin@corp", justification=JUSTIFICATION, at=AT)
    noop = ops.promote("log-2026-09", actor="admin@corp", justification=JUSTIFICATION, at=AT)
    ops.promote("log-2026-10", actor="admin@corp", justification=JUSTIFICATION, at=AT)
    assert noop.changed is False
    assert [entry.activated for entry in ops.history(kind="flow")] == ["flow-2026-10"]
    assert [entry.activated for entry in ops.history()] == ["flow-2026-10", "log-2026-10"]


# --- through the API ----------------------------------------------------------


@pytest.fixture
def auth() -> TokenService:
    return TokenService(SECRET)


@pytest.fixture
def client(settings: Settings, auth: TokenService) -> TestClient:
    app = create_app(settings)
    app.state.token_service = auth
    with TestClient(app) as test_client:
        yield test_client


def headers(auth: TokenService, role: str = "admin") -> dict[str, str]:
    pair = auth.issue(f"{role}@corp", role)
    return {"Authorization": f"Bearer {pair.access_token}"}


def seed(client: TestClient) -> ModelOpsService:
    """Register the same three versions the service fixture uses."""
    service: ModelOpsService = client.app.state.model_ops  # type: ignore[attr-defined]
    service.register(version("flow-2026-08", status="active", sha256=SHA_A))
    service.register(version("flow-2026-10", status="staging", sha256=SHA_B))
    service.register(version("log-2026-09", kind="log", status="active", sha256="c" * 64))
    return service


def rows(client: TestClient) -> list[Any]:
    trail: InMemoryAuditTrail = client.app.state.audit_trail  # type: ignore[attr-defined]
    now = datetime.now(UTC)
    return [
        entry.record
        for entry in trail.entries(start=now - timedelta(hours=1), end=now + timedelta(hours=1))
    ]


def promote(client: TestClient, model_id: str, *, role: str = "admin", body: Any = None) -> Any:
    return client.post(
        f"/api/v1/models/{model_id}/promote",
        json=body if body is not None else {"justification": JUSTIFICATION},
        headers=headers(client.app.state.token_service, role),  # type: ignore[attr-defined]
    )


def rollback(
    client: TestClient, kind: str = "flow", *, role: str = "admin", body: Any = None
) -> Any:
    return client.post(
        f"/api/v1/models/{kind}/rollback",
        json=body if body is not None else {"reason": ROLLBACK_REASON},
        headers=headers(client.app.state.token_service, role),  # type: ignore[attr-defined]
    )


def test_the_listing_is_empty_until_something_registers(client: TestClient) -> None:
    """Nothing is seeded, so nothing can be quoted as a measurement (R-74)."""
    body = client.get("/api/v1/models", headers=headers(client.app.state.token_service)).json()  # type: ignore[attr-defined]
    assert body == {"items": [], "count": 0}


def test_the_listing_returns_the_version_table(client: TestClient, auth: TokenService) -> None:
    seed(client)
    body = client.get("/api/v1/models", headers=headers(auth)).json()
    assert body["count"] == 3
    assert [item["model_id"] for item in body["items"]] == [
        "flow-2026-08",
        "flow-2026-10",
        "log-2026-09",
    ]
    assert {item["status"] for item in body["items"]} == {"active", "staging"}
    first = body["items"][0]
    assert first["kind"] == "flow"
    assert first["manifest_present"] is True
    assert "metrics" not in first


def test_the_listing_filters_and_refuses_an_unknown_filter(
    client: TestClient, auth: TokenService
) -> None:
    seed(client)
    assert client.get("/api/v1/models?kind=log", headers=headers(auth)).json()["count"] == 1
    assert client.get("/api/v1/models?status=retired", headers=headers(auth)).json()["count"] == 0
    assert client.get("/api/v1/models?kind=lstm", headers=headers(auth)).status_code == 422


def test_metrics_come_with_their_provenance(client: TestClient, auth: TokenService) -> None:
    seed(client)
    body = client.get("/api/v1/models/flow-2026-10/metrics", headers=headers(auth)).json()
    assert body["split"] == "temporal:2025-Q4"
    assert sorted(body["metrics"]) == sorted(REQUIRED_METRICS)
    assert body["metrics"]["roc_auc"] == {
        "value": 0.9,
        "artifact": "runs/eval-2025-10-01.json",
        "field": "metrics.roc_auc",
    }
    assert body["evaluation"] is None


def test_metrics_endpoint_serves_recorded_confusion_and_score_histogram(
    client: TestClient, auth: TokenService
) -> None:
    service = seed(client)
    service.register(version("flow-2026-11", sha256="f" * 64, with_metrics=False))
    service.record_evaluation(
        "flow-2026-11",
        eval_report("flow-2026-11"),
        artifact="runs/flow-2026-11/eval.json",
        split="temporal:test",
        evaluated_at=AT,
    )

    body = client.get("/api/v1/models/flow-2026-11/metrics", headers=headers(auth)).json()
    assert body["evaluation"]["confusion"] == {
        "threshold": 0.5,
        "tp": 1,
        "fp": 0,
        "tn": 2,
        "fn": 1,
        "artifact": "runs/flow-2026-11/eval.json",
        "field": "confusion",
    }
    histogram = body["evaluation"]["score_histogram"]
    assert histogram["artifact"] == "runs/flow-2026-11/eval.json"
    assert histogram["field"] == "score_histogram"
    assert len(histogram["bins"]) == 10
    assert histogram["bins"][3] == {
        "lower": 0.3,
        "upper": 0.4,
        "benign": 0,
        "threat": 1,
    }


def test_metrics_for_an_unknown_version_are_a_404(client: TestClient, auth: TokenService) -> None:
    assert (
        client.get("/api/v1/models/flow-2026-99/metrics", headers=headers(auth)).status_code == 404
    )


def test_metrics_for_a_floating_id_are_a_400(client: TestClient, auth: TokenService) -> None:
    """R-68's refusal is not "not found": the two have different remedies."""
    response = client.get("/api/v1/models/latest/metrics", headers=headers(auth))
    assert response.status_code == 400
    assert "R-68" in response.json()["detail"]


def test_metrics_for_an_unmeasured_version_say_which_case_it_is(
    client: TestClient, auth: TokenService
) -> None:
    service = seed(client)
    service.register(version("flow-2026-11", sha256="f" * 64, with_metrics=False))
    response = client.get("/api/v1/models/flow-2026-11/metrics", headers=headers(auth))
    assert response.status_code == 404
    assert "has no recorded evaluation" in response.json()["detail"]


def test_promotion_through_the_api_swaps_in_one_call(
    client: TestClient, auth: TokenService
) -> None:
    seed(client)
    response = promote(client, "flow-2026-10")
    assert response.status_code == 200
    body = response.json()
    assert body["model_id"] == "flow-2026-10"
    assert body["retired"] == "flow-2026-08"
    assert body["status"] == "active"
    assert body["changed"] is True
    assert body["actor"] == "admin@corp"
    listing = client.get("/api/v1/models?kind=flow", headers=headers(auth)).json()
    assert {item["model_id"]: item["status"] for item in listing["items"]} == {
        "flow-2026-08": "retired",
        "flow-2026-10": "active",
    }


def test_a_promotion_is_audited_without_its_justification(client: TestClient) -> None:
    """The trail records changes (D-041) and the note stays out of it (R-58)."""
    seed(client)
    body = promote(client, "flow-2026-10").json()
    entries = rows(client)
    assert [entry.action for entry in entries] == [AuditAction.model_promote]
    entry = entries[0]
    assert entry.actor == "admin@corp"
    assert entry.target_type == "model"
    assert entry.target_id == "flow-2026-10"
    assert entry.detail == {"kind": "flow", "retired": "flow-2026-08", "status": "active"}
    assert JUSTIFICATION not in repr(entry)
    assert body["at"] is not None


def test_promoting_the_active_version_again_writes_nothing(client: TestClient) -> None:
    seed(client)
    promote(client, "flow-2026-08")  # already active
    assert rows(client) == []


def test_promotion_requires_admin(client: TestClient) -> None:
    seed(client)
    for role in ("viewer", "analyst", "responder"):
        assert promote(client, "flow-2026-10", role=role).status_code == 403, role


def test_promotion_requires_a_credential(client: TestClient) -> None:
    assert (
        client.post(
            "/api/v1/models/flow-2026-10/promote", json={"justification": JUSTIFICATION}
        ).status_code
        == 401
    )


def test_a_promotion_needs_a_justification(client: TestClient) -> None:
    seed(client)
    assert promote(client, "flow-2026-10", body={"justification": ""}).status_code == 422
    assert promote(client, "flow-2026-10", body={"justification": "   "}).status_code == 400
    assert rows(client) == []


def test_promoting_a_retired_version_is_a_409(client: TestClient) -> None:
    seed(client)
    promote(client, "flow-2026-10")
    response = promote(client, "flow-2026-08")
    assert response.status_code == 409
    assert "cannot be promoted" in response.json()["detail"]


def test_promoting_a_version_without_a_manifest_is_a_409(client: TestClient) -> None:
    service = seed(client)
    service.register(version("flow-2026-11", sha256="f" * 64, manifest=False))
    response = promote(client, "flow-2026-11")
    assert response.status_code == 409
    assert "R-63" in response.json()["detail"]


def test_promoting_an_unknown_version_is_a_404(client: TestClient) -> None:
    assert promote(client, "flow-2026-99").status_code == 404


def test_promoting_a_floating_id_is_a_400(client: TestClient) -> None:
    assert promote(client, "latest").status_code == 400


def test_rollback_through_the_api_is_one_call(client: TestClient) -> None:
    seed(client)
    promote(client, "flow-2026-10")
    response = rollback(client)
    assert response.status_code == 200
    body = response.json()
    assert (body["model_id"], body["retired"], body["status"]) == (
        "flow-2026-08",
        "flow-2026-10",
        "active",
    )
    assert body["actor"] == "admin@corp"


def test_a_rollback_is_audited_without_its_reason(client: TestClient) -> None:
    seed(client)
    promote(client, "flow-2026-10")
    rollback(client)
    entries = rows(client)
    # The trail reads newest first, so the rollback is the first row.
    assert [entry.action for entry in entries] == [
        AuditAction.model_rollback,
        AuditAction.model_promote,
    ]
    assert entries[0].target_id == "flow-2026-08"
    assert entries[0].detail == {"kind": "flow", "retired": "flow-2026-10", "status": "active"}
    assert ROLLBACK_REASON not in repr(entries)


def test_rollback_requires_admin(client: TestClient) -> None:
    seed(client)
    promote(client, "flow-2026-10")
    for role in ("viewer", "analyst", "responder"):
        assert rollback(client, role=role).status_code == 403, role


def test_rollback_needs_a_reason(client: TestClient) -> None:
    seed(client)
    promote(client, "flow-2026-10")
    assert rollback(client, body={"reason": ""}).status_code == 422
    assert rollback(client, body={"reason": "  "}).status_code == 400


def test_rollback_of_an_unknown_kind_names_the_allowed_ones(client: TestClient) -> None:
    response = rollback(client, kind="lstm")
    assert response.status_code == 400
    assert "flow, log" in response.json()["detail"]


def test_rollback_with_nothing_to_reverse_is_a_409(client: TestClient) -> None:
    seed(client)
    response = rollback(client)
    assert response.status_code == 409
    assert "displaced nothing" in response.json()["detail"]


def test_the_routes_require_the_right_roles(client: TestClient, auth: TokenService) -> None:
    """The behavioural check, then the matrix as intent — they can fail separately."""
    reads = [("get", "/api/v1/models"), ("get", "/api/v1/models/flow-2026-10/metrics")]
    for role in ("viewer", "analyst", "responder", "admin"):
        for method, path in reads:
            assert getattr(client, method)(path, headers=headers(auth, role)).status_code != 403, (
                role,
                path,
            )
    assert ROUTE_MATRIX["/api/v1/models"] == frozenset(Role)
    assert ROUTE_MATRIX["/api/v1/models/{model_id}/metrics"] == frozenset(Role)
    assert ROUTE_MATRIX["/api/v1/models/{model_id}/promote"] == frozenset({Role.ADMIN})
    assert ROUTE_MATRIX["/api/v1/models/{kind}/rollback"] == frozenset({Role.ADMIN})


def test_an_api_key_cannot_promote_a_model(client: TestClient, auth: TokenService) -> None:
    """Ingestion credentials reach the ingest routes and the alert list, nothing else."""
    seed(client)
    issued = client.post(
        "/api/v1/keys",
        json={"name": "collector", "scopes": ["ingest:write"]},
        headers=headers(auth),
    ).json()
    response = client.post(
        "/api/v1/models/flow-2026-10/promote",
        json={"justification": JUSTIFICATION},
        headers={"X-API-Key": issued["secret"]},
    )
    assert response.status_code == 403


def test_the_model_routes_are_in_the_mutating_route_table() -> None:
    """T-312's completeness check covers them; this states it where they live."""
    from app.services.audit_log import AUDITED_ROUTES

    assert (
        AUDITED_ROUTES[("POST", "/api/v1/models/{model_id}/promote")] is AuditAction.model_promote
    )
    assert AUDITED_ROUTES[("POST", "/api/v1/models/{kind}/rollback")] is AuditAction.model_rollback


def test_a_metric_can_be_read_by_name(ops: ModelOpsService) -> None:
    """The API layer reads them one at a time, so the accessor is part of the contract."""
    metrics = ops.get("flow-2026-10").metrics
    assert metrics is not None
    assert metrics.get("roc_auc").value == 0.9
    with pytest.raises(KeyError):
        metrics.get("accuracy")


def test_the_serving_flag_follows_the_status(ops: ModelOpsService) -> None:
    """Two names for one fact: the status is the state, ``is_serving`` is the question."""
    assert ops.get("flow-2026-08").is_serving is True
    assert ops.get("flow-2026-10").is_serving is False


def test_rollback_after_a_directly_registered_active_version_is_refused() -> None:
    """A process that starts with a model loaded has no promotion to reverse."""
    service = ModelOpsService()
    service.register(version("flow-2026-10", status="active", sha256=SHA_B))
    with pytest.raises(NothingToRollBack, match="displaced nothing"):
        service.rollback("flow", actor="admin@corp", reason=ROLLBACK_REASON, at=AT)


def test_a_version_with_no_id_is_refused() -> None:
    with pytest.raises(ValueError, match="needs an id"):
        version("   ")


def test_the_first_promotion_of_a_kind_retires_nothing() -> None:
    """FR-30's two models arrive at different times; the first has no incumbent."""
    service = ModelOpsService()
    service.register(version("log-2026-10", kind="log", sha256=SHA_B))
    outcome = service.promote("log-2026-10", actor="admin@corp", justification=JUSTIFICATION, at=AT)
    assert (outcome.changed, outcome.retired) == (True, None)
    entry = service.history(kind="log")[0]
    assert entry.retired is None


def test_a_missing_model_registry_fails_loudly(client: TestClient, auth: TokenService) -> None:
    """An empty registry must not be silently substituted for a missing one.

    A stand-in that answers "no models are registered" for a deployment that has
    some is a confident wrong answer, and the deployment's own misconfiguration
    would look like an empty model table.
    """
    del client.app.state.model_ops  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="model_ops is not configured"):
        client.get("/api/v1/models", headers=headers(auth))
    with pytest.raises(RuntimeError, match="model_ops is not configured"):
        promote(client, "flow-2026-10")
