"""T-322: the threshold routes, their authorisation, and the wiring they run on.

The service's own properties -- the window, the evidence, the guardrail -- live in
``test_recalibration.py``. What only the application can be wrong about is here:

* **Who may do what.** Reading the bars is every role's; moving one is admin's
  (R-53's ``models`` capability), and no role reaches the route without a token.
* **The guardrail is not a request parameter.** The request schema forbids extra
  fields, so a caller cannot ask for a wider guardrail, a different quantile or a
  lower minimum sample -- the three things an acceptance criterion is about.
* **The ledger the job reads is the ledger the verdict route writes.** Both come
  from the composition root; a test posts a verdict through the API and then sees
  it as the job's evidence, because two instances would look identical and fit on
  nothing.
* **Every change is audited, and only a change is.** One row per moved threshold
  with the requested and applied values; nothing when the run changed nothing.
* **A missing seam fails loudly.** No wired service, and no ML package behind the
  calibrator, each refuse rather than reporting a quiet run.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from app.auth.tokens import TokenService
from app.core.config import Settings
from app.db.models import Verdict
from app.main import create_app
from app.services.audit_log import AUDITED_ROUTES, AuditAction, InMemoryAuditTrail
from app.services.ml_calibration import CalibratorUnavailable, MlCalibrator
from app.services.recalibration import (
    BAND_DEFAULTS,
    BENIGN_LABELS,
    DEFAULT_TENANT_ID,
    DEFAULT_WINDOW,
    MIN_FEEDBACK,
    AlertVerdictFeedback,
    Calibration,
    InMemoryThresholdStore,
    OutcomeReason,
    RecalibrationService,
    ThresholdKey,
    ThresholdRecord,
)
from app.services.verdict_service import InMemoryVerdictLedger
from fastapi.testclient import TestClient

SECRET = "s" * 48
APP_SECRET = "test-secret-key-that-is-long-enough-0123456789"  # pragma: allowlist secret
FAMILY = "lateral-movement"
ROLES = ("viewer", "analyst", "responder", "admin")


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


@pytest.fixture
def client(settings: Settings, auth: TokenService) -> Iterator[TestClient]:
    with build(settings, auth) as test_client:
        yield test_client


def headers(auth: TokenService, role: str = "admin") -> dict[str, str]:
    pair = auth.issue(f"{role}@corp", role)
    return {"Authorization": f"Bearer {pair.access_token}"}


def recalibrate(client: TestClient, *, band: str = "high", role: str = "admin", **extra: object):
    """POST the recalibration route as ``role``."""
    body: dict[str, object] = {"band": band, **extra}
    return client.post(
        "/api/v1/thresholds/recalibrate",
        json=body,
        headers=headers(client.app.state.token_service, role),  # type: ignore[attr-defined]
    )


def audit_rows(client: TestClient, action: AuditAction) -> list[Any]:
    """The audit entries this test's requests produced, for one action."""
    trail: InMemoryAuditTrail = client.app.state.audit_trail  # type: ignore[attr-defined]
    now = datetime.now(UTC)
    return [
        entry
        for entry in trail.entries(start=now - timedelta(hours=1), end=now + timedelta(hours=1))
        if entry.record.action is action
    ]


def seed_feedback(
    client: TestClient,
    *,
    family: str = FAMILY,
    count: int = MIN_FEEDBACK,
    score: float = 0.99,
    verdict: Verdict = Verdict.benign,
    at: datetime | None = None,
) -> None:
    """Write ``count`` labelled alerts into the app's own alert store and ledger.

    Through the real seams rather than around them: the store the query API reads
    and the ledger the verdict route writes, so the job's evidence is the same
    evidence the API would show.
    """
    moment = at if at is not None else datetime.now(UTC) - timedelta(days=1)
    store = client.app.state.alert_store  # type: ignore[attr-defined]
    ledger: InMemoryVerdictLedger = client.app.state.verdict_ledger  # type: ignore[attr-defined]
    for index in range(count):
        row = store.save(
            f"case-{family}-{index}",
            {
                "entity_id": 1,
                "family": family,
                "severity": "high",
                "score": Decimal(str(score)),
                "window_ref": {"store": "stream", "id": f"case-{index}"},
                "explanation": {},
                "status": "open",
                "first_seen": moment + timedelta(seconds=index),
                "last_seen": moment + timedelta(seconds=index),
                "occurrence_count": 1,
            },
            created_at=moment + timedelta(seconds=index),
        )
        ledger.append(ledger_record(row, verdict, at=moment + timedelta(minutes=1)))


def ledger_record(alert_row: Any, verdict: Verdict, *, at: datetime):
    """One append-only verdict record for a stored alert."""
    from app.services.verdict_service import VerdictRecord

    return VerdictRecord(
        id=f"{alert_row.id}-v1",
        alert_id=alert_row.id,
        alert_created_at=alert_row.created_at,
        verdict=verdict,
        actor="analyst@corp",
        at=at,
        note=None,
        supersedes=None,
    )


# --- the wiring ---------------------------------------------------------------


def test_the_composition_root_installs_the_store_the_feedback_and_the_calibrator(
    client: TestClient,
) -> None:
    service: RecalibrationService = client.app.state.recalibration  # type: ignore[attr-defined]
    assert isinstance(service.store, InMemoryThresholdStore)
    assert isinstance(service.calibrator, MlCalibrator), "the real T-207 calibrator, not a stub"
    assert isinstance(service.feedback, AlertVerdictFeedback)
    assert service.tenant_id == DEFAULT_TENANT_ID
    assert service.window == DEFAULT_WINDOW


def test_the_job_reads_the_ledger_the_verdict_route_writes(client: TestClient) -> None:
    """One ledger instance, or the job fits on feedback that never arrives."""
    store = client.app.state.alert_store  # type: ignore[attr-defined]
    stored = store.save(
        "case-shared",
        {
            "entity_id": 1,
            "family": FAMILY,
            "severity": "high",
            "score": Decimal("0.99"),
            "window_ref": {"store": "stream", "id": "case-shared"},
            "explanation": {},
            "status": "open",
            "first_seen": datetime.now(UTC) - timedelta(hours=2),
            "last_seen": datetime.now(UTC) - timedelta(hours=2),
            "occurrence_count": 1,
        },
        created_at=datetime.now(UTC) - timedelta(hours=2),
    )
    response = client.post(
        f"/api/v1/alerts/{stored.id}/verdict",
        json={"verdict": "benign", "created_at": stored.created_at.isoformat()},
        headers=headers(client.app.state.token_service),  # type: ignore[attr-defined]
    )
    assert response.status_code == 200, response.text

    service: RecalibrationService = client.app.state.recalibration  # type: ignore[attr-defined]
    now = datetime.now(UTC)
    found = service.feedback.labelled_scores(
        tenant_id=DEFAULT_TENANT_ID, since=now - DEFAULT_WINDOW, until=now
    )
    assert [entry.alert_id for entry in found] == [stored.id]
    assert found[0].verdict is Verdict.benign


# --- reading ------------------------------------------------------------------


def test_the_listing_returns_the_defaults_and_the_rows_in_force(client: TestClient) -> None:
    store: InMemoryThresholdStore = client.app.state.threshold_store  # type: ignore[attr-defined]
    store.put(
        ThresholdRecord(
            key=ThresholdKey(DEFAULT_TENANT_ID, FAMILY, "high"),
            value=0.85,
            source="recalibration",
            updated_at=datetime.now(UTC),
        )
    )
    response = client.get(
        "/api/v1/thresholds",
        headers=headers(client.app.state.token_service),  # type: ignore[attr-defined]
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tenant_id"] == DEFAULT_TENANT_ID
    assert body["defaults"] == dict(BAND_DEFAULTS)
    assert [item["value"] for item in body["items"]] == [0.85]
    assert body["items"][0]["family"] == FAMILY


@pytest.mark.parametrize("role", ROLES)
def test_every_role_may_read_the_thresholds(client: TestClient, role: str) -> None:
    """An analyst interprets a score against the bar it was compared to."""
    response = client.get(
        "/api/v1/thresholds", headers=headers(client.app.state.token_service, role)  # type: ignore[attr-defined]
    )
    assert response.status_code == 200


def test_reading_without_a_token_is_a_401(client: TestClient) -> None:
    assert client.get("/api/v1/thresholds").status_code == 401


# --- the run ------------------------------------------------------------------


def test_a_run_moves_a_threshold_and_records_why(client: TestClient) -> None:
    seed_feedback(client)
    response = recalibrate(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["tenant_id"], body["band"], body["considered"], body["changed"]) == (
        DEFAULT_TENANT_ID,
        "high",
        1,
        1,
    )
    (outcome,) = body["outcomes"]
    assert outcome["family"] == FAMILY
    assert outcome["previous"] == BAND_DEFAULTS["high"]
    assert outcome["previous_was_default"] is True
    assert outcome["requested"] == pytest.approx(0.99)
    assert outcome["applied"] == pytest.approx(0.85)
    assert outcome["clamped"] is True
    assert outcome["sample_size"] == MIN_FEEDBACK
    assert outcome["reason"] == "fitted"

    rows = audit_rows(client, AuditAction.threshold_recalibrate)
    assert len(rows) == 1
    record = rows[0].record
    assert record.actor == "admin@corp"
    assert (record.target_type, record.target_id) == (
        "threshold",
        f"{DEFAULT_TENANT_ID}/{FAMILY}/high",
    )
    assert record.detail["applied"] == pytest.approx(0.85)
    assert record.detail["requested"] == pytest.approx(0.99)
    assert record.detail["clamped"] is True
    assert record.detail["previous"] == BAND_DEFAULTS["high"]
    assert record.detail["sample_size"] == MIN_FEEDBACK


def test_the_stored_row_is_the_value_the_run_applied(client: TestClient) -> None:
    seed_feedback(client)
    assert recalibrate(client).status_code == 200
    store: InMemoryThresholdStore = client.app.state.threshold_store  # type: ignore[attr-defined]
    stored = store.get(ThresholdKey(DEFAULT_TENANT_ID, FAMILY, "high"))
    assert stored is not None
    assert stored.value == pytest.approx(0.85)
    assert stored.source == "recalibration"


def test_a_run_is_readable_by_roles_that_cannot_start_one(client: TestClient) -> None:
    seed_feedback(client)
    assert recalibrate(client, role="analyst").status_code == 403
    assert recalibrate(client, role="viewer").status_code == 403
    assert recalibrate(client, role="responder").status_code == 403


def test_a_run_without_a_token_is_a_401(client: TestClient) -> None:
    assert client.post("/api/v1/thresholds/recalibrate", json={"band": "high"}).status_code == 401


@pytest.mark.parametrize("role", ("viewer", "analyst", "responder"))
def test_only_admin_may_move_a_threshold(client: TestClient, role: str) -> None:
    """R-53's `models` capability, which admin alone holds."""
    seed_feedback(client)
    assert recalibrate(client, role=role).status_code == 403
    assert audit_rows(client, AuditAction.threshold_recalibrate) == []


def test_a_run_that_changes_nothing_audits_nothing(client: TestClient) -> None:
    """The trail records changes (D-041); a refusal is reported, not logged."""
    seed_feedback(client, verdict=Verdict.true_positive)
    response = recalibrate(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["changed"] == 0
    (outcome,) = body["outcomes"]
    assert outcome["reason"] == OutcomeReason.insufficient_feedback.value
    assert outcome["sample_size"] == 0
    assert outcome["requested"] is None
    assert audit_rows(client, AuditAction.threshold_recalibrate) == []


def test_the_band_is_the_only_thing_a_caller_may_choose() -> None:
    """The guardrail, the quantile and the sample floor are policy, not parameters."""
    from app.schemas.thresholds import RecalibrationRequest

    with pytest.raises(ValueError, match="Extra inputs"):
        RecalibrationRequest.model_validate({"band": "high", "guardrail": 0.5})
    with pytest.raises(ValueError, match="Extra inputs"):
        RecalibrationRequest.model_validate({"band": "high", "minimum_sample": 1})


@pytest.mark.parametrize(
    ("band", "expected"),
    [
        ("high", 200),
        ("medium", 200),
        ("critical", 200),
        ("low", 200),
        ("HIGH", 200),
        ("urgent", 400),
        ("info", 400),
    ],
)
def test_the_band_is_the_documented_lower_bound_or_a_refusal(
    client: TestClient, band: str, expected: int
) -> None:
    """Four bands have a bound to move and a case-insensitive name; nothing else fits."""
    seed_feedback(client)
    response = recalibrate(client, band=band)
    assert response.status_code == expected, response.text
    if expected == 400:
        assert "band must be one of" in response.json()["detail"]
    else:
        assert response.json()["band"] == band.strip().lower()


def test_a_band_of_info_is_refused_rather_than_defaulted(client: TestClient) -> None:
    """FR-13 gives `info` no bound; recalibrating `high` instead would be a different act."""
    response = recalibrate(client, band="info")
    assert response.status_code == 400
    assert "critical, high, low, medium" in response.json()["detail"]
    assert audit_rows(client, AuditAction.threshold_recalibrate) == []


# --- the seams ----------------------------------------------------------------


def test_a_missing_service_fails_loudly(client: TestClient) -> None:
    del client.app.state.recalibration  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="recalibration is not configured"):
        client.get(
            "/api/v1/thresholds",
            headers=headers(client.app.state.token_service),  # type: ignore[attr-defined]
        )
    with pytest.raises(RuntimeError, match="recalibration is not configured"):
        recalibrate(client)


class Unavailable:
    """A calibrator whose backend is missing, as a deployment without ml-service."""

    @property
    def quantile(self) -> float:
        raise CalibratorUnavailable("aegis_ml is not installed in this deployment")

    def fit(self, scores: Sequence[float]) -> float:
        raise CalibratorUnavailable("aegis_ml is not installed in this deployment")

    def clamp(
        self, key: str, requested: float, *, previous: float, sample_size: int
    ) -> Calibration:
        raise CalibratorUnavailable("aegis_ml is not installed in this deployment")


def test_a_run_without_the_ml_package_is_refused_not_reported(
    settings: Settings, auth: TokenService
) -> None:
    """A deployment that cannot fit must not answer 200 with nothing moved."""
    app = create_app(settings)
    app.state.token_service = auth
    app.state.recalibration = RecalibrationService(
        store=InMemoryThresholdStore(),
        feedback=AlertVerdictFeedback(
            app.state.alert_store, app.state.verdict_ledger, tenant_id=DEFAULT_TENANT_ID
        ),
        calibrator=Unavailable(),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/thresholds/recalibrate",
            json={"band": "high"},
            headers=headers(auth),
        )
    assert response.status_code == 500


def test_the_calibrator_names_the_missing_package(monkeypatch: pytest.MonkeyPatch) -> None:
    """The message says what to install and what to inject instead."""
    # Both the package and the module: an import can be halted at either, and a
    # sibling test may already have the module cached.
    monkeypatch.setitem(sys.modules, "aegis_ml.scoring", None)  # type: ignore[arg-type]
    monkeypatch.setitem(sys.modules, "aegis_ml.scoring.thresholds", None)  # type: ignore[arg-type]
    calibrator = MlCalibrator()
    with pytest.raises(CalibratorUnavailable, match="not installed in this deployment") as raised:
        _ = calibrator.quantile
    assert "install ml-service" in str(raised.value)
    with pytest.raises(CalibratorUnavailable, match="inject a Calibrator"):
        _ = calibrator.fit([0.5])


# --- the route is classified and audited --------------------------------------


def test_the_routes_are_in_the_role_matrix() -> None:
    from app.auth.rbac import ROUTE_MATRIX, Role

    assert ROUTE_MATRIX["/api/v1/thresholds"] == frozenset(Role)
    assert ROUTE_MATRIX["/api/v1/thresholds/recalibrate"] == frozenset({Role.ADMIN})


def test_the_run_is_in_the_audit_table() -> None:
    """FR-42's completeness rule walks the app; the entry itself is asserted here."""
    assert (
        AUDITED_ROUTES[("POST", "/api/v1/thresholds/recalibrate")]
        is AuditAction.threshold_recalibrate
    )
    assert AuditAction.threshold_recalibrate.value == "threshold.recalibrate"


def test_the_service_is_constructed_with_the_documents_window_and_floor(
    client: TestClient,
) -> None:
    """The defaults a run uses are the module's, not the request's."""
    service: RecalibrationService = client.app.state.recalibration  # type: ignore[attr-defined]
    assert (service.window, service.minimum_sample) == (DEFAULT_WINDOW, MIN_FEEDBACK)
    assert service.calibrator.quantile == MlCalibrator().quantile


def test_benign_labels_are_what_the_service_fits_on() -> None:
    """The criterion, asserted on the set the service actually consults."""
    assert frozenset({Verdict.benign, Verdict.false_positive}) == BENIGN_LABELS
